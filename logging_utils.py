# logging_utils.py

import csv
import os


class CsvLogger:
    """
    Very simple CSV logger for data packets.

    Predefined columns:
    ts,pressure,flow,grams,t1_in,t1_out,t_final,pulses_batch,pulses_total,
    encoder,limit_top,limit_bottom,btn1,btn2,btn3,led1,led2,led3,pid1,pid2,pid3,emergency
    """

    FIELDNAMES = [
        "ts",
        "pressure",
        "flow",
        "grams",
        "t1_in",
        "t1_out",
        "t_final",
        "pot",
        "pulses_batch",
        "pulses_total",
        "encoder",
        "limit_top",
        "limit_bottom",
        "btn1",
        "btn2",
        "btn3",
        "led1",
        "led2",
        "led3",
        "pid1",
        "pid2",
        "pid3",
        "emergency",
    ]

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._file = None
        self._writer = None
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def start(self) -> None:
        """
        Open CSV file and prepare writer. Overwrites any existing file.
        """
        if self._file is not None:
            return

        self._file = open(self.file_path, mode="w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self.FIELDNAMES)
        self._writer.writeheader()

    def append(self, packet: dict) -> None:
        """
        Append one data packet dict to CSV.
        """
        if self._writer is None:
            return

        row = {k: packet.get(k, "") for k in self.FIELDNAMES}
        self._writer.writerow(row)
        self._file.flush()

    def stop(self) -> None:
        """
        Close CSV file.
        """
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
        self._file = None
        self._writer = None
