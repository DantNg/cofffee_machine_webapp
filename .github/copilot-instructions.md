You are an expert full-stack engineer.  
Your task is to design and implement a Flask web application that acts as a real-time dashboard and controller for an STM32-based espresso test rig.

## 1. High-level architecture

Build the system with this architecture:

- Backend:
  - Python + Flask
  - Uses pyserial (or similar) to communicate with an STM32 board over a serial port (USB).
  - Runs a background task / thread that:
    - Continuously reads JSON messages from the STM32 via serial.
    - Parses these messages into Python dicts.
    - Broadcasts the parsed data to all connected web clients via WebSocket.
  - Receives control commands from the frontend via WebSocket and forwards them as JSON strings over serial to the STM32.

- Frontend:
  - HTML/CSS/JavaScript served by Flask.
  - Uses WebSocket (or Flask-SocketIO) to:
    - Receive real-time data updates and refresh the UI + charts.
    - Send control commands (motor pulses, valve states, emergency stop, etc.) back to the backend.
  - The UI layout must reserve a dedicated area (panel) to embed or display an IP camera stream in the future (for now, just a placeholder area).

The code should be clean, modular, and easy to extend for Step 2 (video/data sync <100 ms).

---

## 2. Data model & JSON protocol

Assume the STM32 periodically sends JSON lines over serial, e.g. 5–10 ms per update.

### 2.1. Example data packet from STM32 → backend → frontend

Use a structure like:


json
{
  "ts": 123456789,               // timestamp in milliseconds (monotonic or epoch)
  "pressure": 8.42,              // bar
  "flow": 2.15,                  // ml/s or similar
  "grams": 18.3,                 // load cell (g)
  "t1_in": 91.2,                 // temperature1 (C)
  "t1_out": 88.5,                // temperature2 (C)
  "t_final": 86.9,               // temperature3 (C)
  "pot": 45.0,                   // potentiometer (% or raw)
  "pulses_batch": 1240,          // pulses sent in current batch
  "pulses_total": 52340,         // pulses total
  "encoder": 430,                // encoder position
  "limit_top": 0,                // digital input
  "limit_bottom": 1,             // digital input
  "btn1": 0,
  "btn2": 1,
  "btn3": 0,
  "led1": 1,
  "led2": 0,
  "led3": 1,
  "pid1": 120.0,
  "pid2": -30.0,
  "pid3": 5.0,
  "emergency": 0                // 1 if emergency stop active
}
The backend should:

Read each line from serial.

Safely parse it as JSON (with error handling).

Emit it over WebSocket as a message with type "data_update".

2.2. WebSocket message formats
Use a simple envelope:

From backend → frontend:

json
Copy code
{
  "type": "data_update",
  "payload": { ... the JSON data from MCU ... }
}
From frontend → backend (commands):

json
Copy code
{
  "type": "command",
  "payload": {
    "cmd": "SEND_PULSES",
    "direction": "+",     // "+" or "-"
    "count": 3000         // max 5000
  }
}
Other command examples:

json
Copy code
{
  "type": "command",
  "payload": {
    "cmd": "STOP_MOTOR"
  }
}

{
  "type": "command",
  "payload": {
    "cmd": "VALVE_SET",
    "valve": 1,           // valve index
    "state": 1            // 1=ON, 0=OFF
  }
}

{
  "type": "command",
  "payload": {
    "cmd": "RESET_COUNTERS"
  }
}

{
  "type": "command",
  "payload": {
    "cmd": "EMERGENCY_STOP"
  }
}
The backend should:

Validate the cmd and parameters.

Serialize an appropriate JSON line for the STM32.

Write that JSON line to the serial port.

3. Backend details (Flask + WebSocket + Serial)
Implement:

Flask app:

A main app.py file that:

Creates a Flask application.

Serves the main HTML page at /.

Serves static JS/CSS files.

WebSocket / Socket layer:

Use one of:

Flask-SocketIO, or

websockets + separate thread, or

flask-sock.

There should be:

A handler for client connections/disconnections.

A handler for receiving command messages from the frontend and sending them to serial.

A mechanism to broadcast data_update messages to all connected clients.

Serial reading loop:

Use pyserial.

Configure port name & baudrate via config or environment variables.

Implement a background thread (or async task) that:

Opens the serial port.

Continuously reads lines.

On each line:

Try to parse JSON.

If valid, broadcast via WebSocket (type: "data_update").

Optionally append this data to a CSV log file if logging is enabled.

Command writing:

From WebSocket handler, when a command is received:

Map the payload to a JSON command suitable for the STM32.

Write that JSON as a line over serial.

CSV logging:

Add simple logging:

A global/per-session log file with columns, e.g.:

ts,pressure,flow,grams,t1_in,t1_out,t_final,pulses_batch,pulses_total,encoder,limit_top,limit_bottom,pid1,pid2,pid3,emergency

Provide REST endpoints or WebSocket commands to:

Start logging.

Stop logging.

Download the current log file (HTTP endpoint that sends the CSV).

4. Frontend UI requirements
Build a single-page dashboard (plain HTML/JS/CSS is OK, no heavy frameworks required, but you may use a lightweight charting library like Chart.js).

Layout suggestion:

4.1. Page structure
Use a responsive layout, for example:

Top bar:

App title (e.g., “Espresso Rig Dashboard”).

Serial/WebSocket connection status indicator.

Logging status indicator.

Main grid with panels:

Real-time sensor panel

Show:

Pressure

Flow

Grams (load cell)

Temperatures (T1_in, T1_out, T_final)

Potentiometer (0–100%)

Each as cards with label + value + unit.

Motor & encoder panel

Displays:

Pulses batch

Pulses total

Encoder position

Controls:

Numeric input: pulse count (1–5000).

Buttons: Send +Pulses, Send –Pulses.

Buttons: Start Motor, Stop Motor.

Button: Reset Counters.

Valves & digital IO panel

Show:

Valve 1..N states (toggle buttons).

Limit switches: top/bottom (with green/red indicators).

Buttons 1–3 states.

LED1–LED3 states.

Provide toggle buttons for valves, with immediate feedback.

PID panel

Show:

PID1, PID2, PID3 outputs.

Optionally show setpoints or current values.

For Step 1, simple numeric display is enough.

Charts panel

Real-time charts (at least):

Pressure over time.

Grams (or flow) over time.

One temperature over time.

Use downsampled updates:

Data arrives at 5–10 ms, but charts can update every 50–100 ms for performance.

Event log / console

Scrollable text area or table that shows:

Connection events.

Emergency events.

Commands sent.

Any errors parsing data.

Camera placeholder panel

A box reserved for an IP camera view, e.g.:

html
Copy code
<div id="camera-panel">
  <h3>Video / Camera (Future)</h3>
  <div class="camera-placeholder">
    <!-- In the future: embed IP camera stream here -->
    <p>Camera stream placeholder</p>
  </div>
</div>
For now, no real video integration is needed, just a clearly marked placeholder.

4.2. WebSocket client logic
On page load:

Open a WebSocket to the backend.

Show connection status (connected / disconnected).

When receiving data_update:

Update:

Sensor cards.

Motor/encoder/valves/limit switches/buttons LEDs.

PID outputs.

Charts (append new data, keep fixed history window, e.g. last 10–30 seconds).

Optionally append a row in the event log (for debugging).

When user presses control buttons:

Build a command JSON (as described in section 2.2).

Send it via WebSocket to the backend.

Optionally log the action to the event log panel.

4.3. Styling
Clean, modern dashboard style.

Color hints:

Emergency / errors: red.

OK / connected: green.

Warnings: orange.

All panels should be responsive and readable on:

Desktop browser.

Tablet.

A screen connected to a Raspberry Pi Zero 3B.

5. Non-functional requirements
The system should:

Handle data rates up to 100 Hz (10 ms updates) without UI freezing.

Be robust against malformed JSON lines (ignore and log errors).

Allow multiple browsers to connect and view the same data simultaneously.

Code should be structured roughly as:

app.py (Flask + WebSocket + serial threads)

static/ (JS, CSS)

templates/index.html

serial_worker.py (optional, for serial logic)

logging_utils.py (optional, for CSV logging)

6. Deliverables
A working Flask application that can:

Connect to a serial device.

Read JSON lines from it.

Broadcast them via WebSocket.

Accept commands from frontend and send them to the serial device.

A web dashboard (HTML/JS/CSS) that:

Connects to the WebSocket.

Displays real-time sensor/motor/PID/IO data.

Provides controls for pulses, motor, valves, emergency.

Plots key signals in real-time charts.

Logs events and allows CSV data logging.

Contains a clear placeholder panel for an IP camera stream (to be implemented in Step 2).

Please generate the full project structure (Python + HTML/JS/CSS) and include example implementations and comments so that it can be run and extended easily.
## note
when you want to test the code please run the code in Command Prompt (cmd) with this comaand to enable virtual environment
"D:\MyProjects\ESPRESSO_PISTON_BAR_CREW_app\.venv\Scripts\activate"