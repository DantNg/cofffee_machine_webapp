import json
from datetime import datetime
from typing import Callable, Optional


class DataProcessingWorker:
    """
    Consumes raw serial lines, parses MCU JSON packets, and pushes
    normalized data to the app via a callback (or directly to Socket.IO).
    """

    def __init__(self, on_parsed: Optional[Callable[[dict], None]] = None, socketio=None):
        self.on_parsed = on_parsed
        self.socketio = socketio

    def on_raw_line(self, line: str) -> None:
        line = (line or "").strip()
        if not line:
            return
        try:
            data = json.loads(line)
            if isinstance(data, dict):
                # If MCU already sends in UI-friendly schema, forward as-is
                self._emit_packet(data)
        except Exception:
            # Swallow parse errors here; SerialWorker/App can also report malformed JSON
            pass

    def on_packet(self, packet: dict) -> None:
        # Allow wiring directly from SerialWorker.on_packet if desired
        self._emit_packet(packet)

    def _emit_packet(self, packet: dict) -> None:
        if self.on_parsed:
            try:
                self.on_parsed(packet)
                return
            except Exception:
                pass
        # Fallback to Socket.IO broadcast if provided
        if self.socketio is not None:
            msg = {"type": "data_update", "payload": packet}
            try:
                self.socketio.emit("message", msg)
            except Exception:
                pass
