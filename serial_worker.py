import json
import time
import random
import math
from threading import Thread, Lock

import serial


class SerialWorker(Thread):
    """
    Background thread that:
      - Opens a serial port
      - Continuously reads JSON lines
      - Parses them and invokes on_packet(dict)
      - Handles malformed JSON via on_error(line, exc)
      - Provides send_command(dict) to send JSON lines to STM32

    If mock=True, it will not open a real serial port, but instead
    generate synthetic data for testing the dashboard.
    """

    def __init__(
        self,
        port,
        baudrate,
        on_packet,
        on_error,
        mock=False,
        read_timeout=0.1,
    ):
        super().__init__(daemon=True)
        self.port = port
        self.baudrate = baudrate
        self.on_packet = on_packet
        self.on_error = on_error
        self.mock = mock
        self.read_timeout = read_timeout

        self._stop_flag = False
        self._ser = None
        self._write_lock = Lock()

    def stop(self):
        self._stop_flag = True
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass

    def run(self):
        if self.mock:
            print("Starting SerialWorker in MOCK mode")
            self._run_mock()
        else:
            self._run_real()

    # -------------------------------------------------------------------------
    # Real serial mode
    # -------------------------------------------------------------------------
    def _run_real(self):
        while not self._stop_flag:
            try:
                if self._ser is None or not self._ser.is_open:
                    self._ser = serial.Serial(
                        self.port,
                        self.baudrate,
                        timeout=self.read_timeout,
                    )

                line = self._ser.readline()
                if not line:
                    continue

                decoded = line.decode("utf-8", errors="replace").strip()
                if not decoded:
                    continue

                try:
                    packet = json.loads(decoded)
                    if isinstance(packet, dict):
                        self.on_packet(packet)
                except Exception as e:
                    self.on_error(decoded, e)
            except serial.SerialException as e:
                # Port error; wait and retry
                self.on_error("SerialException", e)
                time.sleep(1.0)
            except Exception as e:
                self.on_error("Unknown error in SerialWorker", e)
                time.sleep(0.5)

    # -------------------------------------------------------------------------
    # Mock mode: generate fake sensor data at ~100 Hz with realistic espresso brewing patterns
    # -------------------------------------------------------------------------
    def _run_mock(self):
        ts_start = time.time()
        pulses_total = 0
        encoder = 0
        brew_cycle = 0  # Simulate brewing cycles
        
        while not self._stop_flag:
            now = time.time()
            ts_ms = int((now - ts_start) * 1000)
            
            # Create realistic brewing cycle (30 seconds per cycle)
            cycle_time = (now - ts_start) % 30.0
            
            # Simulate different phases of espresso brewing
            if cycle_time < 5:  # Pre-infusion phase
                pressure_base = 2.0 + (cycle_time / 5.0) * 6.0
                flow_base = 0.5 + (cycle_time / 5.0) * 1.0
                grams_rate = 0.2
            elif cycle_time < 20:  # Extraction phase
                pressure_base = 8.0 + math.sin(cycle_time * 0.5) * 1.0
                flow_base = 1.5 + math.cos(cycle_time * 0.3) * 0.5
                grams_rate = 1.2
            else:  # Cool down phase
                pressure_base = 8.0 - ((cycle_time - 20) / 10.0) * 7.0
                flow_base = 1.5 - ((cycle_time - 20) / 10.0) * 1.2
                grams_rate = 0.3

            pulses_batch = random.randint(0, 50)
            pulses_total += pulses_batch
            encoder += random.randint(-2, 2)
            
            # Add realistic noise and variations
            packet = {
                "ts": ts_ms,
                "pressure": max(0, pressure_base + random.uniform(-0.3, 0.3)),
                "flow": max(0, flow_base + random.uniform(-0.1, 0.1)),
                "grams": 18.0 + (cycle_time * grams_rate) + random.uniform(-0.2, 0.2),
                "t1_in": 92.0 + math.sin(cycle_time * 0.1) * 2.0 + random.uniform(-0.5, 0.5),
                "t1_out": 89.0 + math.sin(cycle_time * 0.1) * 1.5 + random.uniform(-0.5, 0.5),
                "t_final": 87.0 + math.sin(cycle_time * 0.1) * 1.0 + random.uniform(-0.5, 0.5),
                "pot": 45.0 + math.sin(cycle_time * 0.2) * 30.0,
                "pulses_batch": pulses_batch,
                "pulses_total": pulses_total,
                "encoder": encoder,
                "limit_top": 1 if cycle_time > 25 else 0,
                "limit_bottom": 1 if cycle_time < 5 else 0,
                "btn1": 1 if 5 < cycle_time < 20 else 0,
                "btn2": random.choice([0, 1]),
                "btn3": 1 if cycle_time > 20 else 0,
                "led1": 1 if cycle_time < 25 else 0,
                "led2": 1 if 5 < cycle_time < 20 else 0,
                "led3": 1 if cycle_time > 15 else 0,
                "pid1": pressure_base * 25.0 + random.uniform(-10, 10),
                "pid2": flow_base * -20.0 + random.uniform(-5, 5),
                "pid3": (cycle_time - 15) * 2.0 + random.uniform(-3, 3),
                "emergency": 0,
            }

            self.on_packet(packet)
            time.sleep(0.01)  # 100 Hz

    # -------------------------------------------------------------------------
    # Sending commands
    # -------------------------------------------------------------------------
    def send_command(self, cmd_dict):
        """
        Serialize cmd_dict as JSON line and write to serial.
        """
        line = json.dumps(cmd_dict) + "\n"

        if self.mock:
            # In mock mode, just pretend to send.
            print(f"[MOCK SERIAL] Would send: {line.strip()}")
            return

        with self._write_lock:
            if self._ser is None or not self._ser.is_open:
                raise RuntimeError("Serial port is not open")
            self._ser.write(line.encode("utf-8"))
            self._ser.flush()
