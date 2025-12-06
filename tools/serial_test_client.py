import re
import time
import json
import serial

# Fixed COM port for test client
TEST_PORT = "COM2"
BAUD = 115200

# Map parsed values into the JSON schema expected by the webapp
# Unknown fields will be omitted.

def parse_log_line(line):
    line = line.strip()
    out = {}

    # Example patterns from the log
    # "Sequence 2: LS_BOT, 1, Flow, 13.71, T1_IN, 93.56, ML_Filled, 4.98, T1_OUT_Avg, 92.38, Time(s), 0.66"
    m = re.search(r"Flow,\s*([0-9.]+)", line)
    if m:
        out["flow"] = float(m.group(1))
    m = re.search(r"T1_IN,\s*([0-9.]+)", line)
    if m:
        out["t1_in"] = float(m.group(1))
    m = re.search(r"T1_OUT_Avg,\s*([0-9.]+)", line)
    if m:
        out["t1_out"] = float(m.group(1))
    m = re.search(r"ML_Filled,\s*([0-9.]+)", line)
    if m:
        # Treat as grams approximation
        out["grams"] = float(m.group(1))
    m = re.search(r"Pressure=([0-9.]+)\s*bar", line)
    if m:
        out["pressure"] = float(m.group(1))
    m = re.search(r"Final\s+Depressurization\s+Pressure:\s*([0-9.]+)\s*bar", line)
    if m:
        out["pressure"] = float(m.group(1))

    # CSV-like lines: "Time(s),MLDispensed(ml),TotalGrams(g),GramsPerSec(g/s),Flow(ml/s), Pressure(bar), T_Final(C)"
    # followed by rows
    if "," in line and not line.startswith("Examples"):
        parts = [p.strip() for p in line.split(',')]
        try:
            if len(parts) >= 6:
                # Map typical columns where available
                t = float(parts[0])
                ml_disp = float(parts[1])
                grams_total = float(parts[2])
                grams_per_sec = float(parts[3])
                flow = float(parts[4])
                pressure = float(parts[5])
                out.update({
                    "flow": flow,
                    "pressure": pressure,
                    "grams": grams_total,
                    "t_final": float(parts[6]) if len(parts) > 6 and parts[6] else None,
                })
            
        except Exception:
            pass

    return out


def main():
    ser = serial.Serial(TEST_PORT, BAUD, timeout=0.1)
    print(f"[TEST] Writing JSON packets to {TEST_PORT} @ {BAUD}")

    # Stream synthesized data based on patterns; in practice, you can load the file and iterate
    # For demo, we simulate a sequence with changing values
    ts0 = time.time()
    t = 0.0
    try:
        while True:
            now = time.time()
            ts_ms = int((now - ts0) * 1000)
            # Simple waveforms
            pressure = 8.0 + 1.0 * (1 + time.time() % 1)  # pseudo varying
            flow = 12.0 + 0.5 * ((time.time() * 0.7) % 1)
            grams = 10.0 + (time.time() % 10) * 0.5
            t1_in = 93.0 + (time.time() % 2)
            t1_out = 92.0 + (time.time() % 1.5)
            t_final = 72.0 + (time.time() % 0.8)

            packet = {
                "ts": ts_ms,
                "pressure": round(pressure, 2),
                "flow": round(flow, 2),
                "grams": round(grams, 2),
                "t1_in": round(t1_in, 2),
                "t1_out": round(t1_out, 2),
                "t_final": round(t_final, 2),
                "pot": 45.0,
                "pulses_batch": 0,
                "pulses_total": int((time.time() - ts0) * 100),
                "encoder": int((time.time() - ts0) * 10),
                "limit_top": 0,
                "limit_bottom": 0,
                "btn1": 0,
                "btn2": 0,
                "btn3": 0,
                "led1": 1,
                "led2": 0,
                "led3": 1,
                "pid1": 120.0,
                "pid2": -30.0,
                "pid3": 5.0,
                "emergency": 0,
            }
            line = json.dumps(packet) + "\n"
            ser.write(line.encode("utf-8"))
            ser.flush()
            time.sleep(0.02)  # ~50 Hz
    finally:
        ser.close()


if __name__ == "__main__":
    main()
