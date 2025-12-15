from typing import Dict, Any

class ConfigWorker:
    """
    Handles configuration read/apply from the app to MCU via SerialWorker.
    """

    def __init__(self, serial_worker_getter):
        """
        serial_worker_getter: callable that returns the active SerialWorker
        (to avoid circular import or stale references)
        """
        self._get_serial_worker = serial_worker_getter

    def apply_config(self, config: Dict[str, Any]) -> bool:
        """
        Send configuration to MCU as a JSON command. Adjust schema as needed.
        """
        worker = self._get_serial_worker()
        if worker is None:
            return False
        try:
            # Example unified command envelope (customize to your STM32 firmware)
            payload = {"cmd": "SET_SYSTEM_SETTINGS", "settings": config}
            worker.send_command(payload)
            return True
        except Exception:
            return False

    def send_command(self, command: Dict[str, Any]) -> bool:
        worker = self._get_serial_worker()
        if worker is None:
            return False
        try:
            worker.send_command(command)
            return True
        except Exception:
            return False
