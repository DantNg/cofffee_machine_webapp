"""
Centralized definitions for normalized MCU packet fields and related schema.

Use these constants across the app for consistent processing, CSV logging,
and downstream integrations (UI, storage, analytics).
"""
import os
import json
from typing import List, Dict, Any, Tuple

# Resolve schema.json next to static folder (used by frontend)
_SCHEMA_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "static", "schema", "schema.json")
)
_SCHEMA: Dict[str, Any] = {}


def _load_schema() -> Dict[str, Any]:
    global _SCHEMA
    if _SCHEMA:
        return _SCHEMA
    try:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            _SCHEMA = json.load(f)
    except Exception:
        _SCHEMA = {}
    return _SCHEMA


def _derive_fields(schema: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    fields: List[str] = []
    defaults: Dict[str, Any] = {}
    try:
        for item in schema.get("data", {}).get("fields", []):
            name = item.get("name")
            if not name:
                continue
            fields.append(name)
            defaults[name] = item.get("default")
    except Exception:
        pass
    if not fields:
        # Fallback to built-in defaults
        fields = [
            "ts", "pressure", "flow", "grams", "t1_in", "t1_out", "t_final", "pot",
            "pulses_batch", "pulses_total", "encoder", "limit_top", "limit_bottom",
            "btn1", "btn2", "btn3", "led1", "led2", "led3", "pid1", "pid2", "pid3", "emergency",
        ]
        defaults = {
            "ts": None, "pressure": None, "flow": None, "grams": None,
            "t1_in": None, "t1_out": None, "t_final": None, "pot": None,
            "pulses_batch": 0, "pulses_total": 0, "encoder": 0,
            "limit_top": 0, "limit_bottom": 0, "btn1": 0, "btn2": 0, "btn3": 0,
            "led1": 0, "led2": 0, "led3": 0,
            "pid1": None, "pid2": None, "pid3": None, "emergency": 0,
        }
    return fields, defaults


SCHEMA = _load_schema()
DATA_FIELDS, DEFAULTS = _derive_fields(SCHEMA)
CSV_FIELDNAMES: List[str] = list(DATA_FIELDS)


def normalize_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new dict containing only known fields with defaults filled.

    Unknown keys are ignored; missing keys get DEFAULTS values.
    """
    out: Dict[str, Any] = {}
    for k in DATA_FIELDS:
        out[k] = packet.get(k, DEFAULTS.get(k))
    return out


# -----------------------------------------------------------------------------
# Command schema and validation/mapping
# -----------------------------------------------------------------------------

def _validate_send_pulses(payload: Dict[str, Any]) -> None:
    direction = payload.get("direction")
    count = payload.get("count")
    if direction not in ["+", "-"]:
        raise ValueError("direction must be '+' or '-'")
    if not isinstance(count, int) or not (1 <= count <= 5000):
        raise ValueError("count must be int in [1,5000]")


def _validate_valve_set(payload: Dict[str, Any]) -> None:
    valve = payload.get("valve")
    state = payload.get("state")
    if not isinstance(valve, int) or valve < 0:
        raise ValueError("valve must be a non-negative integer")
    if state not in [0, 1]:
        raise ValueError("state must be 0 or 1")


def _validate_pid_setpoints(payload: Dict[str, Any]) -> None:
    setpoints = payload.get("setpoints")
    if not isinstance(setpoints, dict):
        raise ValueError("setpoints must be a dict")
    for key in ["pid1", "pid2", "pid3"]:
        if key not in setpoints or not isinstance(setpoints[key], (int, float)):
            raise ValueError(f"setpoints.{key} must be a number")


def _validate_pid_gains(payload: Dict[str, Any]) -> None:
    gains = payload.get("gains")
    if not isinstance(gains, dict):
        raise ValueError("gains must be a dict")
    for pid_key in ["pid1", "pid2", "pid3"]:
        if pid_key not in gains or not isinstance(gains[pid_key], dict):
            raise ValueError(f"gains.{pid_key} must be a dict")
        for gain_key in ["kp", "ki", "kd"]:
            if gain_key not in gains[pid_key]:
                raise ValueError(f"gains.{pid_key}.{gain_key} is required")


def _validate_pid_limits(payload: Dict[str, Any]) -> None:
    limits = payload.get("limits")
    if not isinstance(limits, dict):
        raise ValueError("limits must be a dict")
    required_keys = ["output_max", "output_min", "windup_clamp"]
    for key in required_keys:
        if key not in limits:
            raise ValueError(f"limits.{key} is required")


def _validate_pid_sample_time(payload: Dict[str, Any]) -> None:
    sample_time = payload.get("sample_time")
    if not isinstance(sample_time, int) or sample_time < 1:
        raise ValueError("sample_time must be a positive integer")


def _validate_settings_dict(payload: Dict[str, Any], field: str) -> None:
    settings = payload.get(field)
    if not isinstance(settings, dict):
        raise ValueError(f"{field} must be a dict")


_CMD_VALIDATORS = {
    "SEND_PULSES": _validate_send_pulses,
    "STOP_MOTOR": lambda p: None,
    "VALVE_SET": _validate_valve_set,
    "RESET_COUNTERS": lambda p: None,
    "EMERGENCY_STOP": lambda p: None,
    "SET_PID_SETPOINTS": _validate_pid_setpoints,
    "SET_PID_GAINS": _validate_pid_gains,
    "SET_PID_LIMITS": _validate_pid_limits,
    "SET_PID_SAMPLE_TIME": _validate_pid_sample_time,
    "SET_MOTOR_SETTINGS": lambda p: _validate_settings_dict(p, "settings"),
    "SET_SENSOR_SETTINGS": lambda p: _validate_settings_dict(p, "settings"),
    "SET_VALVE_BUTTON_SETTINGS": lambda p: _validate_settings_dict(p, "settings"),
    "SET_EMERGENCY_SETTINGS": lambda p: _validate_settings_dict(p, "settings"),
    "SET_SYSTEM_SETTINGS": lambda p: _validate_settings_dict(p, "settings"),
    "SAVE_ALL_SETTINGS": lambda p: _validate_settings_dict(p, "settings"),
    "LOAD_DEFAULT_SETTINGS": lambda p: None,
}


def _py_type_ok(value, typ: str) -> bool:
    if typ == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if typ == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if typ == "string":
        return isinstance(value, str)
    if typ == "boolean":
        return isinstance(value, bool)
    if typ == "object":
        return isinstance(value, dict)
    return True


def _validate_with_json_schema(cmd: str, payload: Dict[str, Any]) -> None:
    spec = SCHEMA.get("commands", {}).get(cmd)
    if not spec:
        return
    params = spec.get("params") or {}
    for key, rule in params.items():
        if key not in payload:
            continue
        val = payload.get(key)
        typ = rule.get("type")
        if typ and not _py_type_ok(val, typ):
            raise ValueError(f"{cmd}.{key}: expected {typ}")
        if "enum" in rule and val not in rule["enum"]:
            raise ValueError(f"{cmd}.{key}: must be one of {rule['enum']}")
        if isinstance(val, (int, float)):
            if "min" in rule and val < rule["min"]:
                raise ValueError(f"{cmd}.{key}: must be >= {rule['min']}")
            if "max" in rule and val > rule["max"]:
                raise ValueError(f"{cmd}.{key}: must be <= {rule['max']}")


def validate_and_map_command(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and map incoming frontend command to MCU schema.

    Currently returns payload as-is after validation. Customize here to
    transform command names or fields to match firmware expectations.
    """
    if not isinstance(payload, dict):
        raise ValueError("Command payload must be a JSON object")

    cmd = payload.get("cmd")
    if not cmd:
        raise ValueError("Command payload missing 'cmd'")

    # Prefer JSON schema if present; fallback to built-ins
    try:
        _validate_with_json_schema(cmd, payload)
    except Exception:
        validator = _CMD_VALIDATORS.get(cmd)
        if validator is None:
            raise ValueError(f"Unknown cmd: {cmd}")
        validator(payload)

    # Apply MCU mapping if defined in schema: remap command name and params
    spec = SCHEMA.get("commands", {}).get(cmd, {})
    mcu = spec.get("mcu", {}) if isinstance(spec, dict) else {}
    mcu_name = mcu.get("name", cmd)
    param_map = mcu.get("param_map", {}) if isinstance(mcu, dict) else {}

    mapped: Dict[str, Any] = {"cmd": mcu_name}
    for k, v in payload.items():
        if k == "cmd":
            continue
        mapped[param_map.get(k, k)] = v
    return mapped
