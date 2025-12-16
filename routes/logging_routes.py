from flask import Blueprint, jsonify, send_file
from flask import current_app
from datetime import datetime, timezone

logging_bp = Blueprint("logging_bp", __name__)


def _ensure_log_file_path():
    filename = datetime.now(timezone.utc).strftime("espresso_log_%Y%m%d_%H%M%S.csv")
    return current_app.config.get("LOG_DIR", "./logs") + "/" + filename


@logging_bp.route("/api/logging/start", methods=["POST"]) 
def start_logging():
    logger_lock = current_app.config.get("LOGGER_LOCK")
    logging_worker = current_app.config.get("LOGGING_WORKER")
    log_event = current_app.config.get("LOG_EVENT")

    with logger_lock:
        if logging_worker is None:
            return jsonify({"error": "Logging worker not ready"}), 503
        path = _ensure_log_file_path()
        logging_worker.start_csv(path)
        log_event("CSV logging started", level="info")
        return jsonify({"status": "ok", "logging": True, "file": path})


@logging_bp.route("/api/logging/stop", methods=["POST"]) 
def stop_logging():
    logger_lock = current_app.config.get("LOGGER_LOCK")
    logging_worker = current_app.config.get("LOGGING_WORKER")
    log_event = current_app.config.get("LOG_EVENT")

    with logger_lock:
        if logging_worker is not None:
            logging_worker.stop_csv()
        log_event("CSV logging stopped", level="info")
        return jsonify({"status": "ok", "logging": False})


@logging_bp.route("/api/logging/status", methods=["GET"]) 
def logging_status():
    logging_worker = current_app.config.get("LOGGING_WORKER")
    if logging_worker is None:
        return jsonify({"logging": False})
    st = logging_worker.status()
    return jsonify({"logging": st["enabled"], "file": st["file_path"]})


@logging_bp.route("/api/logging/download", methods=["GET"]) 
def download_log():
    logging_worker = current_app.config.get("LOGGING_WORKER")
    if logging_worker is None or logging_worker.csv_logger is None:
        return jsonify({"error": "No log file available"}), 404
    return send_file(logging_worker.csv_logger.file_path, as_attachment=True)


@logging_bp.route("/api/serial/logs", methods=["GET"]) 
def get_serial_logs():
    from flask import request
    logging_worker = current_app.config.get("LOGGING_WORKER")
    count = 200
    try:
        count = int(request.args.get("count", count))
    except Exception:
        pass
    if logging_worker is None:
        return jsonify({"logs": []})
    return jsonify({"logs": logging_worker.get_recent_logs(count)})
