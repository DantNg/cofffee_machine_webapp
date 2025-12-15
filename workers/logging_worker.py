from collections import deque
from datetime import datetime
from typing import Optional

from utils.logging_utils import CsvLogger


class LoggingWorker:
    """
    Handles serial log monitoring and CSV logging.
    - Maintains a ring buffer of recent raw serial lines for the UI terminal
    - Provides start/stop CSV logging of processed packets
    - Emits serial log lines to Socket.IO for real-time display
    """

    def __init__(self, socketio, max_buffer: int = 500):
        self.socketio = socketio
        self.buffer = deque(maxlen=max_buffer)
        self.csv_logger: Optional[CsvLogger] = None
        self.logging_enabled: bool = False

    # ---- Serial log handling ----
    def on_raw_line(self, line: str) -> None:
        ts = datetime.utcnow().isoformat() + "Z"
        self.buffer.append({"ts": ts, "line": line})
        try:
            # Broadcast to all clients for terminal view
            self.socketio.emit(
                "event_log",
                {"ts": ts, "level": "serial", "message": line}
            )
        except Exception:
            pass

    def get_recent_logs(self, count: int = 200):
        if count <= 0:
            return []
        return list(self.buffer)[-count:]

    # ---- CSV logging of processed packets ----
    def start_csv(self, file_path: str) -> None:
        if self.csv_logger is None:
            self.csv_logger = CsvLogger(file_path)
        self.csv_logger.start()
        self.logging_enabled = True

    def stop_csv(self) -> None:
        if self.csv_logger:
            self.csv_logger.stop()
        self.logging_enabled = False

    def append_packet(self, packet: dict) -> None:
        if self.logging_enabled and self.csv_logger is not None:
            self.csv_logger.append(packet)

    def status(self):
        return {
            "enabled": self.logging_enabled,
            "file_path": getattr(self.csv_logger, "file_path", None) if self.csv_logger else None
        }
