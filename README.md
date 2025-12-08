# Espresso Rig WebApp

A Flask-based dashboard for monitoring and controlling an espresso piston rig. It renders real-time charts, device status, camera feed, and a rich Settings panel. The app reads data from a serial COM port and forwards parsed updates to the UI.

## Features
- Dashboard with real-time charts (Pressure, Grams, Temperature) and a combined Live Brew Chart
- Terminal Log showing raw serial messages
- Header COM controls: list ports, connect/disconnect, baud selection
- Settings page with configurable Motor, Sensors, Valves, Limits, Logging, and System options
- Camera feed (local USB or IP MJPEG)
- CSV logging and download

## Requirements
- Windows (tested) + Python 3.10+
- COM port available (e.g., `COM2`)
- Install Python dependencies:

```cmd
cd d:\MyProjects\Coffee_Machine\Coffee_Machine_App
pip install -r requirements.txt
```

## Quick Start
1. Start the webapp:
```cmd
cd d:\MyProjects\Coffee_Machine\Coffee_Machine_App
python app.py
```
2. Open the UI:
- Go to `http://127.0.0.1:5000/dashboard`
3. Connect the serial worker:
- In the header, click `⟳` to refresh COM ports
- Select your COM (e.g., `COM2`) and baud (e.g., `115200`)
- Click `Connect`
4. (Optional) Use the bundled serial test client to stream sample JSON over `COM2`:
```cmd
cd d:\MyProjects\Coffee_Machine\Coffee_Machine_App\tools
python serial_test_client.py
```
5. Verify:
- Live Brew Chart and small charts begin updating
- Terminal Log shows raw serial lines and status messages

## Routes & Pages
- `GET /dashboard`: Main dashboard (charts, controls, camera)
- `GET /settings`: Settings page (system configuration)
- `GET /`: Redirects to `/dashboard`

## Serial Control API
These endpoints allow connecting/disconnecting the SerialWorker via REST.
- `GET /api/serial/ports` → `["COM3", "COM5", ...]`
- `POST /api/serial/connect` `{ "port": "COM2", "baud": 115200 }` → `{ "connected": true }`
- `POST /api/serial/disconnect` → `{ "disconnected": true }`

## Logging API
- `POST /api/logging/start` → Enables CSV logging
- `POST /api/logging/stop` → Disables CSV logging
- `GET /api/logging/status` → `{ "logging": true|false }`
- `GET /api/logging/download` → Downloads current CSV file

## File Structure (key paths)
- `app.py` → Flask app + Socket.IO + routes
- `serial_worker.py` → Reads COM lines; emits parsed JSON + raw lines
- `logging_utils.py` → CSV logging
- `templates/` → Jinja templates (`layout`, `dashboard_page`, `settings_page`)
- `static/js/` → Frontend scripts (`main.js`, `dashboard.js`, `settings.js`)
- `static/css/styles.css` → UI styling
- `tools/serial_test_client.py` → Test client writing JSON to `COM2`
- `logs/` → CSV outputs

## Known Notes
- Browser UI receives data via Socket.IO (WebSocket). The source of truth is always the serial COM stream handled by `SerialWorker`.
- If COM2 is used by the test client, ensure the webapp connects to COM2 and both share the same baud.
- Camera IP feeds expect MJPEG/HTTP streams via `<img>` (e.g., `http://host:port/video`).

## Support
- Please share the COM port details, baud rate, and a short description of the hardware setup when reporting issues.
