from flask import Blueprint, jsonify, current_app
import serial.tools.list_ports

serial_bp = Blueprint("serial_bp", __name__)

@serial_bp.route("/api/serial/ports", methods=["GET"]) 
def list_serial_ports():
    ports = [p.device for p in serial.tools.list_ports.comports()]
    return jsonify(ports)


@serial_bp.route("/api/serial/connect", methods=["POST"]) 
def serial_connect():
    from flask import request
    log_event = current_app.config.get("LOG_EVENT")

    serial_worker = current_app.config.get("SERIAL_WORKER")
    serial_connected = current_app.config.get("SERIAL_CONNECTED")
    current_serial_port = current_app.config.get("CURRENT_SERIAL_PORT")
    current_serial_baud = current_app.config.get("CURRENT_SERIAL_BAUD")

    SerialWorker = current_app.config.get("SerialWorkerClass")
    data_worker = current_app.config.get("DATA_WORKER")

    default_port = current_app.config.get("SERIAL_PORT")
    default_baud = current_app.config.get("SERIAL_BAUD")

    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    port = data.get("port", default_port)
    baud = int(data.get("baud", default_baud))

    if serial_connected and serial_worker is not None:
        try:
            if current_serial_port == port and current_serial_baud == baud:
                log_event(f"Serial already connected on {port} @ {baud}", level="info")
                return jsonify({"connected": True, "port": port, "baud": baud})
        except Exception:
            pass

    try:
        if serial_worker is not None:
            serial_worker.stop()
    except Exception:
        pass

    serial_worker = SerialWorker(
        port=port,
        baudrate=baud,
        on_packet=data_worker.on_packet if data_worker is not None else current_app.config.get("ON_SERIAL_PACKET"),
        on_error=current_app.config.get("ON_SERIAL_ERROR"),
        on_raw_line=current_app.config.get("ON_SERIAL_RAW"),
        mock=False,
    )
    serial_worker.start()

    current_app.config.update({
        "SERIAL_WORKER": serial_worker,
        "SERIAL_CONNECTED": True,
        "CURRENT_SERIAL_PORT": port,
        "CURRENT_SERIAL_BAUD": baud,
    })

    log_event(f"Serial connected on {port} @ {baud}", level="info")
    return jsonify({"connected": True, "port": port, "baud": baud})


@serial_bp.route("/api/serial/disconnect", methods=["POST"]) 
def serial_disconnect():
    log_event = current_app.config.get("LOG_EVENT")
    serial_worker = current_app.config.get("SERIAL_WORKER")
    try:
        if serial_worker is not None:
            serial_worker.stop()
            current_app.config.update({"SERIAL_WORKER": None})
        current_app.config.update({"SERIAL_CONNECTED": False})
        log_event("Serial disconnected", level="info")
        return jsonify({"disconnected": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@serial_bp.route("/api/serial/status", methods=["GET"]) 
def serial_status():
    return jsonify({
        "connected": bool(current_app.config.get("SERIAL_CONNECTED")),
        "port": current_app.config.get("CURRENT_SERIAL_PORT") if current_app.config.get("SERIAL_CONNECTED") else None,
        "baud": current_app.config.get("CURRENT_SERIAL_BAUD") if current_app.config.get("SERIAL_CONNECTED") else None,
    })
