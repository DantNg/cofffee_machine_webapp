import csv
import os
from typing import List

from schema.schema import CSV_FIELDNAMES


class CsvLogger:
    """
    Very simple CSV logger for data packets using centralized field names.
    """

    def __init__(self, file_path: str, fieldnames: List[str] = None):
        self.file_path = file_path
        self.fieldnames = list(fieldnames) if fieldnames else list(CSV_FIELDNAMES)
        self._file = None
        self._writer = None
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def start(self) -> None:
        if self._file is not None:
            return
        self._file = open(self.file_path, mode="w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self.fieldnames)
        self._writer.writeheader()

    def append(self, packet: dict) -> None:
        if self._writer is None:
            return
        row = {k: packet.get(k, "") for k in self.fieldnames}
        self._writer.writerow(row)
        self._file.flush()

    def stop(self) -> None:
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
        self._file = None
        self._writer = None
