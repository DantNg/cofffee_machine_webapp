from flask import Blueprint, jsonify, current_app

config_bp = Blueprint("config_bp", __name__)

@config_bp.route("/api/config/apply", methods=["POST"]) 
def apply_config():
    from flask import request
    config_worker = current_app.config.get("CONFIG_WORKER")
    if config_worker is None:
        return jsonify({"error": "Config worker not ready"}), 503
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON"}), 400
    ok = config_worker.apply_config(payload)
    if not ok:
        return jsonify({"error": "Failed to apply config"}), 500
    return jsonify({"status": "ok"})
