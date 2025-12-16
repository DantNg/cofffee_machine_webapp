import os
import json
from threading import Lock
from datetime import datetime, timezone
from typing import Optional
import serial.tools.list_ports
# import cv2  # Temporarily disabled due to NumPy compatibility issues
from flask import Flask, redirect, url_for
from flask_socketio import SocketIO, emit

from workers.serial_worker import SerialWorker
from workers.logging_worker import LoggingWorker
from workers.data_processing_worker import DataProcessingWorker
from workers.config_worker import ConfigWorker
from routes.dashboard import dashboard_bp
from routes.settings import settings_bp
from routes.logging_routes import logging_bp
from routes.serial_routes import serial_bp
from routes.config_routes import config_bp

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
app.config["LOG_DIR"] = LOG_DIR

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
    ts = datetime.now(timezone.utc).isoformat()
    payload = {"ts": ts, "level": level, "message": message}
    print(f"[{ts}] [{level.upper()}] {message}")
    socketio.emit("event_log", payload)



def on_serial_packet(packet):
    socketio.emit("message", {"type": "data_update", "payload": packet})
    if logging_worker is not None:
        logging_worker.append_packet(packet)


def on_serial_error(line, error):
    log_event(f"Malformed JSON from serial: {line!r} ({error})", level="error")


def on_serial_raw(line):
    if logging_worker is not None:
        logging_worker.on_raw_line(line)
    else:
        socketio.emit("event_log", {"ts": datetime.now(timezone.utc).isoformat(), "level": "serial", "message": line})


from schema.schema import validate_and_map_command


# -----------------------------------------------------------------------------
# HTTP Routes
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("dashboard_bp.dashboard"))


# Note: actual routes are provided by Blueprints; avoid duplicating paths


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
            if app.config.get("SERIAL_WORKER") is not None:
                app.config["SERIAL_WORKER"].send_command(serial_cmd)
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
                path = os.path.join(LOG_DIR, datetime.now(timezone.utc).strftime("espresso_log_%Y%m%d_%H%M%S.csv"))
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

    # Expose helpers and state in app.config for routes
    app.config.update({
        "LOGGER_LOCK": logger_lock,
        "LOGGING_WORKER": logging_worker,
        "DATA_WORKER": data_worker,
        "CONFIG_WORKER": config_worker,
        "LOG_EVENT": log_event,
        "ON_SERIAL_PACKET": on_serial_packet,
        "ON_SERIAL_ERROR": on_serial_error,
        "ON_SERIAL_RAW": on_serial_raw,
        "SERIAL_WORKER": None,
        "SERIAL_CONNECTED": False,
        "CURRENT_SERIAL_PORT": SERIAL_PORT,
        "CURRENT_SERIAL_BAUD": SERIAL_BAUD,
        "SERIAL_PORT": SERIAL_PORT,
        "SERIAL_BAUD": SERIAL_BAUD,
        "SerialWorkerClass": SerialWorker,
    })

    # Register Blueprints
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(logging_bp)
    app.register_blueprint(serial_bp)
    app.register_blueprint(config_bp)

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
