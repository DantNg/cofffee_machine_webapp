import os
import json
from threading import Lock
from datetime import datetime
import serial.tools.list_ports
# import cv2  # Temporarily disabled due to NumPy compatibility issues
from flask import Flask, render_template, jsonify, send_file, Response, redirect, url_for
from flask_socketio import SocketIO, emit

from serial_worker import SerialWorker
from logging_utils import CsvLogger

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


# Globals for logger
logger_lock = Lock()
csv_logger = None
logging_enabled = False

# Camera management
camera = None
camera_active = False
camera_source_type = "none"
camera_source = None

# COM port management
available_ports = []
serial_connected = False

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
    Callback from SerialWorker with a parsed JSON dict from the STM32.
    Broadcast to all clients and optionally log to CSV.
    """
    global csv_logger, logging_enabled

    # Envelope for frontend
    msg = {
        "type": "data_update",
        "payload": packet,
    }
    socketio.emit("message", msg)

    # Optional CSV logging
    if logging_enabled and csv_logger is not None:
        try:
            csv_logger.append(packet)
        except Exception as e:
            log_event(f"CSV logging error: {e}", level="error")


def on_serial_error(line, error):
    """
    Called when SerialWorker fails to parse a line as JSON.
    """
    log_event(f"Malformed JSON from serial: {line!r} ({error})", level="error")


def validate_and_map_command(payload):
    """
    Validate and map incoming command from frontend to
    JSON dict to send over serial.

    Frontend sends:
    {
      "cmd": "SEND_PULSES",
      "direction": "+",
      "count": 3000
    }

    For now, we just validate and pass the payload through.
    In the future, you can map to STM32-specific keys/structure here.
    """
    if not isinstance(payload, dict):
        raise ValueError("Command payload must be a JSON object")

    cmd = payload.get("cmd")
    if not cmd:
        raise ValueError("Command payload missing 'cmd'")

    if cmd == "SEND_PULSES":
        direction = payload.get("direction")
        count = payload.get("count")
        if direction not in ["+", "-"]:
            raise ValueError("direction must be '+' or '-'")
        if not isinstance(count, int) or not (1 <= count <= 5000):
            raise ValueError("count must be int in [1,5000]")
        # pass-through OK

    elif cmd == "STOP_MOTOR":
        pass

    elif cmd == "VALVE_SET":
        valve = payload.get("valve")
        state = payload.get("state")
        if not isinstance(valve, int) or valve < 0:
            raise ValueError("valve must be a non-negative integer")
        if state not in [0, 1]:
            raise ValueError("state must be 0 or 1")

    elif cmd == "RESET_COUNTERS":
        pass

    elif cmd == "EMERGENCY_STOP":
        pass

    # PID Settings Commands
    elif cmd == "SET_PID_SETPOINTS":
        setpoints = payload.get("setpoints")
        if not isinstance(setpoints, dict):
            raise ValueError("setpoints must be a dict")
        # Validate setpoint values
        for key in ["pid1", "pid2", "pid3"]:
            if key not in setpoints or not isinstance(setpoints[key], (int, float)):
                raise ValueError(f"setpoints.{key} must be a number")

    elif cmd == "SET_PID_GAINS":
        gains = payload.get("gains")
        if not isinstance(gains, dict):
            raise ValueError("gains must be a dict")
        for pid_key in ["pid1", "pid2", "pid3"]:
            if pid_key not in gains or not isinstance(gains[pid_key], dict):
                raise ValueError(f"gains.{pid_key} must be a dict")
            for gain_key in ["kp", "ki", "kd"]:
                if gain_key not in gains[pid_key]:
                    raise ValueError(f"gains.{pid_key}.{gain_key} is required")

    elif cmd == "SET_PID_LIMITS":
        limits = payload.get("limits")
        if not isinstance(limits, dict):
            raise ValueError("limits must be a dict")
        required_keys = ["output_max", "output_min", "windup_clamp"]
        for key in required_keys:
            if key not in limits:
                raise ValueError(f"limits.{key} is required")

    elif cmd == "SET_PID_SAMPLE_TIME":
        sample_time = payload.get("sample_time")
        if not isinstance(sample_time, int) or sample_time < 1:
            raise ValueError("sample_time must be a positive integer")

    # Motor Settings Commands
    elif cmd == "SET_MOTOR_SETTINGS":
        settings = payload.get("settings")
        if not isinstance(settings, dict):
            raise ValueError("motor settings must be a dict")

    # Sensor Settings Commands
    elif cmd == "SET_SENSOR_SETTINGS":
        settings = payload.get("settings")
        if not isinstance(settings, dict):
            raise ValueError("sensor settings must be a dict")

    # Valve & Button Settings Commands
    elif cmd == "SET_VALVE_BUTTON_SETTINGS":
        settings = payload.get("settings")
        if not isinstance(settings, dict):
            raise ValueError("valve/button settings must be a dict")

    # Emergency Settings Commands
    elif cmd == "SET_EMERGENCY_SETTINGS":
        settings = payload.get("settings")
        if not isinstance(settings, dict):
            raise ValueError("emergency settings must be a dict")

    # System Settings Commands
    elif cmd == "SET_SYSTEM_SETTINGS":
        settings = payload.get("settings")
        if not isinstance(settings, dict):
            raise ValueError("system settings must be a dict")

    # Global Settings Commands
    elif cmd == "SAVE_ALL_SETTINGS":
        settings = payload.get("settings")
        if not isinstance(settings, dict):
            raise ValueError("all settings must be a dict")

    elif cmd == "LOAD_DEFAULT_SETTINGS":
        pass

    else:
        raise ValueError(f"Unknown cmd: {cmd}")

    # If you need a different schema for STM32, transform here.
    # For now, we just send payload as-is.
    return payload


def ensure_logger():
    """
    Create CsvLogger instance if needed.
    """
    global csv_logger
    if csv_logger is None:
        filename = datetime.utcnow().strftime("espresso_log_%Y%m%d_%H%M%S.csv")
        path = os.path.join(LOG_DIR, filename)
        csv_logger = CsvLogger(path)
    return csv_logger


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
    global logging_enabled

    with logger_lock:
        ensure_logger()
        csv_logger.start()
        logging_enabled = True
        log_event("CSV logging started", level="info")
        return jsonify({"status": "ok", "logging": True})


@app.route("/api/logging/stop", methods=["POST"])
def stop_logging():
    global logging_enabled, csv_logger

    with logger_lock:
        if csv_logger is not None:
            csv_logger.stop()
        logging_enabled = False
        log_event("CSV logging stopped", level="info")
        return jsonify({"status": "ok", "logging": False})


@app.route("/api/logging/status", methods=["GET"])
def logging_status():
    return jsonify({"logging": logging_enabled})


@app.route("/api/logging/download", methods=["GET"])
def download_log():
    if csv_logger is None or csv_logger.file_path is None:
        return jsonify({"error": "No log file available"}), 404
    return send_file(csv_logger.file_path, as_attachment=True)


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
    global logging_enabled, csv_logger

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
            if action == "START":
                ensure_logger()
                csv_logger.start()
                logging_enabled = True
                log_event("CSV logging started via WebSocket", level="info")
            elif action == "STOP":
                if csv_logger is not None:
                    csv_logger.stop()
                logging_enabled = False
                log_event("CSV logging stopped via WebSocket", level="info")
            else:
                emit("error", {"message": "Unknown logging action"})
        emit("logging_status", {"logging": logging_enabled}, broadcast=True)

    else:
        emit("error", {"message": f"Unknown message type: {mtype}"})


# -----------------------------------------------------------------------------
# Main entry point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Initialize SerialWorker with callbacks
    serial_worker = SerialWorker(
        port=SERIAL_PORT,
        baudrate=SERIAL_BAUD,
        on_packet=on_serial_packet,
        on_error=on_serial_error,
        mock=MOCK_SERIAL,
    )
    serial_worker.start()

    log_event(
        f"Serial worker started on port={SERIAL_PORT} baud={SERIAL_BAUD}, mock={MOCK_SERIAL}",
        level="info",
    )

    # Run SocketIO (this wraps Flask run)
    # Use host='0.0.0.0' if you want to expose on LAN/RPi.
    socketio.run(app, host="0.0.0.0", port=5000)
