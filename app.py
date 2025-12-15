import os
import json
from threading import Lock
from datetime import datetime
from typing import Optional
import serial.tools.list_ports
# import cv2  # Temporarily disabled due to NumPy compatibility issues
from flask import Flask, render_template, jsonify, send_file, Response, redirect, url_for
from flask_socketio import SocketIO, emit

from workers.serial_worker import SerialWorker
from workers.logging_worker import LoggingWorker
from workers.data_processing_worker import DataProcessingWorker
from workers.config_worker import ConfigWorker

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
SERIAL_PORT = os.environ.get("SERIAL_PORT", "COM1")
SERIAL_BAUD = int(os.environ.get("SERIAL_BAUD", "115200"))
LOG_DIR = os.environ.get("LOG_DIR", "./logs")
MOCK_SERIAL = os.environ.get("MOCK_SERIAL", "0") == "1"

os.makedirs(LOG_DIR, exist_ok=True)

# -----------------------------------------------------------------------------
# Flask + SocketIO
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "development-secret")

# Use eventlet or gevent if you prefer; threading also works for modest loads.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


# Workers and logging state
logger_lock = Lock()
logging_worker: Optional[LoggingWorker] = None
data_worker: Optional[DataProcessingWorker] = None
config_worker: Optional[ConfigWorker] = None

# Camera management
camera = None
camera_active = False
camera_source_type = "none"
camera_source = None

# COM port management
available_ports = []
serial_connected = False
current_serial_port = SERIAL_PORT
current_serial_baud = SERIAL_BAUD

# Serial worker will be initialized after SocketIO
serial_worker = None


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------
def log_event(message, level="info"):
    ts = datetime.utcnow().isoformat() + "Z"
    payload = {"ts": ts, "level": level, "message": message}
    print(f"[{ts}] [{level.upper()}] {message}")
    # No broadcast kwarg: emitting from server context already goes to all clients
    socketio.emit("event_log", payload)



def on_serial_packet(packet):
    """
    Callback for processed/normalized packet from MCU (can be wired directly
    from SerialWorker or via DataProcessingWorker).
    """
    # Broadcast to UI
    socketio.emit("message", {"type": "data_update", "payload": packet})
    # Forward to logging worker (CSV)
    if logging_worker is not None:
        logging_worker.append_packet(packet)


def on_serial_error(line, error):
    """
    Called when SerialWorker fails to parse a line as JSON.
    """
    log_event(f"Malformed JSON from serial: {line!r} ({error})", level="error")


def on_serial_raw(line):
    """Raw serial line listener: forward to logging worker and UI terminal."""
    if logging_worker is not None:
        logging_worker.on_raw_line(line)
    else:
        socketio.emit("event_log", {"ts": datetime.utcnow().isoformat() + "Z", "level": "serial", "message": line})


from schema.schema import validate_and_map_command


def ensure_log_file_path():
    filename = datetime.utcnow().strftime("espresso_log_%Y%m%d_%H%M%S.csv")
    return os.path.join(LOG_DIR, filename)


# -----------------------------------------------------------------------------
# HTTP Routes
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    # Redirect root to dashboard
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard_page.html", current_tab="dashboard")


@app.route("/settings")
def settings():
    return render_template("settings_page.html", current_tab="settings")


@app.route("/api/logging/start", methods=["POST"])
def start_logging():
    global logging_worker
    with logger_lock:
        if logging_worker is None:
            return jsonify({"error": "Logging worker not ready"}), 503
        path = ensure_log_file_path()
        logging_worker.start_csv(path)
        log_event("CSV logging started", level="info")
        return jsonify({"status": "ok", "logging": True, "file": path})


@app.route("/api/logging/stop", methods=["POST"])
def stop_logging():
    global logging_worker
    with logger_lock:
        if logging_worker is not None:
            logging_worker.stop_csv()
        log_event("CSV logging stopped", level="info")
        return jsonify({"status": "ok", "logging": False})


@app.route("/api/logging/status", methods=["GET"])
def logging_status():
    if logging_worker is None:
        return jsonify({"logging": False})
    st = logging_worker.status()
    return jsonify({"logging": st["enabled"], "file": st["file_path"]})


@app.route("/api/logging/download", methods=["GET"])
def download_log():
    if logging_worker is None or logging_worker.csv_logger is None:
        return jsonify({"error": "No log file available"}), 404
    return send_file(logging_worker.csv_logger.file_path, as_attachment=True)

@app.route("/api/serial/logs", methods=["GET"])
def get_serial_logs():
    count = 200
    try:
        from flask import request
        count = int(request.args.get("count", count))
    except Exception:
        pass
    if logging_worker is None:
        return jsonify({"logs": []})
    return jsonify({"logs": logging_worker.get_recent_logs(count)})


@app.route("/api/config/apply", methods=["POST"])
def apply_config():
    """Apply configuration payload to MCU via ConfigWorker."""
    global config_worker
    try:
        from flask import request
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON"}), 400
    if config_worker is None:
        return jsonify({"error": "Config worker not ready"}), 503
    ok = config_worker.apply_config(payload)
    if not ok:
        return jsonify({"error": "Failed to apply config"}), 500
    return jsonify({"status": "ok"})


# -----------------------------------------------------------------------------
# Serial control REST endpoints
# -----------------------------------------------------------------------------
@app.route("/api/serial/ports", methods=["GET"])
def list_serial_ports():
    ports = [p.device for p in serial.tools.list_ports.comports()]
    return jsonify(ports)


@app.route("/api/serial/connect", methods=["POST"])
def serial_connect():
    global serial_worker, serial_connected, current_serial_port, current_serial_baud
    data = None
    try:
        # Try standard Flask JSON parsing
        from flask import request
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    port = data.get("port", SERIAL_PORT)
    baud = int(data.get("baud", SERIAL_BAUD))

    # Stop existing worker if any
    try:
        if serial_worker is not None:
            serial_worker.stop()
    except Exception:
        pass

    # Start new worker
    serial_worker = SerialWorker(
        port=port,
        baudrate=baud,
        on_packet=data_worker.on_packet if data_worker is not None else on_serial_packet,
        on_error=on_serial_error,
        on_raw_line=on_serial_raw,
        mock=False,
    )
    serial_worker.start()

    current_serial_port = port
    current_serial_baud = baud
    serial_connected = True
    log_event(f"Serial connected on {port} @ {baud}", level="info")
    return jsonify({"connected": True, "port": port, "baud": baud})


@app.route("/api/serial/disconnect", methods=["POST"])
def serial_disconnect():
    global serial_worker, serial_connected
    try:
        if serial_worker is not None:
            serial_worker.stop()
            serial_worker = None
        serial_connected = False
        log_event("Serial disconnected", level="info")
        return jsonify({"disconnected": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/serial/status", methods=["GET"])
def serial_status():
    """Return current serial connection status for UI initialization."""
    return jsonify({
        "connected": bool(serial_connected),
        "port": current_serial_port if serial_connected else None,
        "baud": current_serial_baud if serial_connected else None,
    })


# -----------------------------------------------------------------------------
# SocketIO Events
# -----------------------------------------------------------------------------
@socketio.on("connect")
def handle_connect():
    emit("server_info", {"status": "connected"})
    log_event("Client connected", level="info")


@socketio.on("disconnect")
def handle_disconnect():
    log_event("Client disconnected", level="info")


@socketio.on("message")
def handle_message(msg):
    """
    Expect messages of the form:
    {
      "type": "command",
      "payload": { ... }
    }
    or:
    {
      "type": "logging_control",
      "payload": { "action": "START" | "STOP" }
    }
    """
    global logging_worker

    if not isinstance(msg, dict):
        emit("error", {"message": "Invalid message format"})
        return

    mtype = msg.get("type")
    payload = msg.get("payload", {})

    if mtype == "command":
        try:
            serial_cmd = validate_and_map_command(payload)
            if serial_worker is not None:
                serial_worker.send_command(serial_cmd)
                log_event(f"Command sent: {serial_cmd}", level="info")
            else:
                log_event("Serial worker not initialized; command not sent", level="error")
        except Exception as e:
            log_event(f"Command validation error: {e}", level="error")
            emit("error", {"message": str(e)})

    elif mtype == "logging_control":
        action = payload.get("action")
        with logger_lock:
            if logging_worker is None:
                emit("error", {"message": "Logging worker not ready"})
                return
            if action == "START":
                path = ensure_log_file_path()
                logging_worker.start_csv(path)
                log_event("CSV logging started via WebSocket", level="info")
            elif action == "STOP":
                logging_worker.stop_csv()
                log_event("CSV logging stopped via WebSocket", level="info")
            else:
                emit("error", {"message": "Unknown logging action"})
        emit("logging_status", {"logging": logging_worker.logging_enabled if logging_worker else False}, broadcast=True)

    else:
        emit("error", {"message": f"Unknown message type: {mtype}"})


# -----------------------------------------------------------------------------
# Main entry point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Initialize workers
    logging_worker = LoggingWorker(socketio)
    data_worker = DataProcessingWorker(on_parsed=on_serial_packet, socketio=socketio)
    config_worker = ConfigWorker(lambda: serial_worker)

    # Start in mock mode only; otherwise wait for manual connect from UI
    if MOCK_SERIAL:
        serial_worker = SerialWorker(
            port=SERIAL_PORT,
            baudrate=SERIAL_BAUD,
            on_packet=data_worker.on_packet,
            on_error=on_serial_error,
            on_raw_line=on_serial_raw,
            mock=True,
        )
        serial_worker.start()
        log_event(
            f"Serial worker started in MOCK mode (baud={SERIAL_BAUD})",
            level="info",
        )
    else:
        log_event("Waiting for manual serial connect from UI...", level="info")

    # Run SocketIO (this wraps Flask run)
    # Use host='0.0.0.0' if you want to expose on LAN/RPi.
    socketio.run(app, host="0.0.0.0", port=5000)
