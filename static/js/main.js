// main.js

let socket = null;

// Chart.js instances
let chartPressure, chartGrams, chartTemp;
let lastChartUpdate = 0;
const CHART_UPDATE_INTERVAL_MS = 50;  // Faster updates for smoother charts
const HISTORY_LENGTH = 600;           // More history for better visualization
const CONNECTION_RETRY_INTERVAL = 2000; // Retry connection every 2 seconds

// Store last data for debug
let latestData = {};

function appendLog(message, level = "info") {
  const logEl = document.getElementById("event-log");
  const ts = new Date().toISOString();
  const line = `[${ts}] [${level.toUpperCase()}] ${message}`;
  if (logEl) {
    try {
      logEl.value += line + "\n";
      logEl.scrollTop = logEl.scrollHeight;
    } catch (e) {
      console.log(line);
    }
  } else {
    console.log(line);
  }
}

function setWsStatus(connected) {
  const el = document.getElementById("ws-status");
  if (connected) {
    el.textContent = "Connected";
    el.classList.remove("status-disconnected");
    el.classList.add("status-connected");
  } else {
    el.textContent = "Disconnected";
    el.classList.remove("status-connected");
    el.classList.add("status-disconnected");
  }
}

function setLoggingStatus(logging) {
  const el = document.getElementById("log-status");
  if (logging) {
    el.textContent = "On";
    el.classList.remove("status-off");
    el.classList.add("status-on");
  } else {
    el.textContent = "Off";
    el.classList.remove("status-on");
    el.classList.add("status-off");
  }
}

function initSocket() {
  console.log("Initializing WebSocket connection...");
  
  if (socket && socket.connected) {
    console.log("Socket already connected");
    return; // Already connected
  }
  
  try {
    socket = io({
      autoConnect: true,
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 5,
      timeout: 5000
    });
    
    console.log("Socket.IO instance created");

    socket.on("connect", () => {
      console.log("WebSocket connected successfully");
      setWsStatus(true);
      appendLog("WebSocket connected - receiving real-time data");
    });

    socket.on("disconnect", (reason) => {
      console.log("WebSocket disconnected:", reason);
      setWsStatus(false);
      appendLog(`WebSocket disconnected: ${reason}`, "warn");
      
      // Auto-retry connection
      setTimeout(() => {
        if (!socket.connected) {
          console.log("Attempting to reconnect...");
          appendLog("Attempting to reconnect...", "info");
          socket.connect();
        }
      }, CONNECTION_RETRY_INTERVAL);
    });

    socket.on("server_info", (msg) => {
      console.log("Server info received:", msg);
      appendLog(`Server info: ${JSON.stringify(msg)}`);
    });

    socket.on("event_log", (msg) => {
      console.log("Event log received:", msg);
      appendLog(msg.message, msg.level || "info");
    });

    socket.on("error", (msg) => {
      console.error("Socket error:", msg);
      appendLog(`Error from server: ${msg.message || msg}`, "error");
    });

    socket.on("logging_status", (msg) => {
      console.log("Logging status received:", msg);
      setLoggingStatus(!!msg.logging);
    });

    socket.on("message", (msg) => {
      if (!msg || typeof msg !== "object") {
        console.warn("Received invalid message format:", msg);
        appendLog("Received invalid message format", "warn");
        return;
      }

      console.log("Message received:", msg.type, msg.payload ? "with payload" : "no payload");

      if (msg.type === "data_update") {
        try {
          handleDataUpdate(msg.payload);
          // Also feed combined brew chart
          updateBrewChart(msg.payload);
        } catch (error) {
          console.error("Error processing data update:", error);
          appendLog(`Error processing data update: ${error.message}`, "error");
        }
      } else {
        console.warn("Unknown message type:", msg.type);
        appendLog(`Unknown message type: ${msg.type}`, "warn");
      }
    });
    
    socket.on("connect_error", (error) => {
      console.error("Socket connection error:", error);
      appendLog(`Connection error: ${error.message}`, "error");
      setWsStatus(false);
    });
    
    console.log("Socket event listeners registered");
  } catch (error) {
    console.error("Error initializing socket:", error);
    appendLog(`Socket initialization error: ${error.message}`, "error");
  }
}

// ---------------------------------------------------------------------------
// Data update handling
// ---------------------------------------------------------------------------
function handleDataUpdate(data) {
  latestData = data || {};

  // Update text values (fallback to --)
  setText("pressure-val", data.pressure, 2);
  setText("flow-val", data.flow, 2);
  setText("grams-val", data.grams, 2);

  setText("t1-in-val", data.t1_in, 1);
  setText("t1-out-val", data.t1_out, 1);
  setText("t-final-val", data.t_final, 1);

  setText("pot-val", data.pot, 1);

  setText("pulses-batch-val", data.pulses_batch);
  setText("pulses-total-val", data.pulses_total);
  setText("encoder-val", data.encoder);

  setText("pid1-val", data.pid1, 1);
  setText("pid2-val", data.pid2, 1);
  setText("pid3-val", data.pid3, 1);

  // Indicators (0/1)
  setIndicator("limit-top-dot", data.limit_top);
  setIndicator("limit-bottom-dot", data.limit_bottom);

  setIndicator("btn1-dot", data.btn1);
  setIndicator("btn2-dot", data.btn2);
  setIndicator("btn3-dot", data.btn3);

  setIndicator("led1-dot", data.led1);
  setIndicator("led2-dot", data.led2);
  setIndicator("led3-dot", data.led3);

  // Emergency indicator: we re-use event log for clear notifications
  if (data.emergency === 1) {
    appendLog("EMERGENCY: emergency flag set in data!", "error");
  }

  // Chart updates (throttled)
  const now = performance.now();
  if (now - lastChartUpdate > CHART_UPDATE_INTERVAL_MS) {
    lastChartUpdate = now;
    updateCharts(data);
  }
}

function setText(id, value, decimals) {
  const el = document.getElementById(id);
  if (!el) return;
  if (value === undefined || value === null || isNaN(value)) {
    el.textContent = "--";
  } else if (typeof decimals === "number") {
    el.textContent = Number(value).toFixed(decimals);
  } else {
    el.textContent = value;
  }
}

function setIndicator(id, on) {
  const el = document.getElementById(id);
  if (!el) return;
  if (on) {
    el.classList.add("indicator-on");
  } else {
    el.classList.remove("indicator-on");
  }
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------
function sendCommand(payload) {
  if (!socket || !socket.connected) {
    appendLog("Cannot send command: WebSocket not connected", "error");
    return;
  }
  const msg = {
    type: "command",
    payload: payload,
  };
  socket.emit("message", msg);
}

function initControls() {
  // Pulses
  const pulseInput = document.getElementById("pulse-count-input");
  document.getElementById("btn-send-plus").addEventListener("click", () => {
    const count = parseInt(pulseInput.value, 10) || 0;
    sendCommand({ cmd: "SEND_PULSES", direction: "+", count });
    appendLog(`SEND_PULSES +${count}`);
  });

  document.getElementById("btn-send-minus").addEventListener("click", () => {
    const count = parseInt(pulseInput.value, 10) || 0;
    sendCommand({ cmd: "SEND_PULSES", direction: "-", count });
    appendLog(`SEND_PULSES -${count}`);
  });

  // Motor
  document.getElementById("btn-start-motor").addEventListener("click", () => {
    sendCommand({ cmd: "SEND_PULSES", direction: "+", count: 0 }); // or your own START command
    appendLog("Start motor command sent");
  });

  document.getElementById("btn-stop-motor").addEventListener("click", () => {
    sendCommand({ cmd: "STOP_MOTOR" });
    appendLog("STOP_MOTOR command sent");
  });

  document.getElementById("btn-reset-counters").addEventListener("click", () => {
    sendCommand({ cmd: "RESET_COUNTERS" });
    appendLog("RESET_COUNTERS command sent");
  });

  document.getElementById("btn-emergency").addEventListener("click", () => {
    sendCommand({ cmd: "EMERGENCY_STOP" });
    appendLog("EMERGENCY_STOP command sent", "error");
  });

  // Valve toggles
  document.querySelectorAll(".valve-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const valveIndex = parseInt(btn.dataset.valve, 10);
      const isActive = btn.classList.toggle("active");
      const state = isActive ? 1 : 0;
      sendCommand({ cmd: "VALVE_SET", valve: valveIndex, state });
      appendLog(`VALVE_SET valve=${valveIndex} state=${state}`);
    });
  });

  // Logging controls via REST
  document.getElementById("btn-start-logging").addEventListener("click", () => {
    fetch("/api/logging/start", { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        setLoggingStatus(!!data.logging);
        appendLog("Logging started via REST");
      })
      .catch((err) => appendLog(`Error starting logging: ${err}`, "error"));
  });

  document.getElementById("btn-stop-logging").addEventListener("click", () => {
    fetch("/api/logging/stop", { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        setLoggingStatus(!!data.logging);
        appendLog("Logging stopped via REST");
      })
      .catch((err) => appendLog(`Error stopping logging: ${err}`, "error"));
  });

  // On load, query logging status
  fetch("/api/logging/status")
    .then((r) => r.json())
    .then((data) => setLoggingStatus(!!data.logging))
    .catch(() => {});
}

// ---------------------------------------------------------------------------
// Charts
// ---------------------------------------------------------------------------
function initCharts() {
  // Check if Chart.js is loaded
  if (typeof Chart === 'undefined') {
    appendLog("Chart.js not loaded, charts disabled", "warn");
    return;
  }

  try {
    const ctxP = document.getElementById("chart-pressure").getContext("2d");
    const ctxG = document.getElementById("chart-grams").getContext("2d");
    const ctxT = document.getElementById("chart-temp").getContext("2d");

    const baseConfig = {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "",
            data: [],
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.2,
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            fill: false,
          },
        ],
      },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: true, // prevent uncontrolled vertical growth
        aspectRatio: 4/3,
        interaction: {
          intersect: false,
          mode: 'index',
        },
        scales: {
          x: {
            display: true,
            type: 'linear',
            position: 'bottom',
            title: {
              display: true,
              text: 'Time (ms)',
              color: '#9ca3af'
            },
            ticks: {
              color: '#6b7280',
              maxTicksLimit: 8,
              callback: function(value) {
                return new Date(value).toLocaleTimeString();
              }
            },
            grid: {
              color: 'rgba(55, 65, 81, 0.3)'
            }
          },
          y: {
            beginAtZero: false,
            title: {
              display: true,
              text: 'Value',
              color: '#9ca3af'
            },
            ticks: {
              color: '#6b7280'
            },
            grid: {
              color: 'rgba(55, 65, 81, 0.3)'
            }
          },
        },
        plugins: {
          legend: {
            display: false,
          },
          tooltip: {
            enabled: true,
            mode: 'nearest',
            intersect: false,
          }
        },
        elements: {
          line: {
            tension: 0.2
          },
          point: {
            radius: 0,
            hitRadius: 10,
            hoverRadius: 4
          }
        }
      },
    };

    // Pressure Chart - Blue
    const pressureConfig = JSON.parse(JSON.stringify(baseConfig));
    pressureConfig.data.datasets[0].borderColor = '#3b82f6';
    pressureConfig.data.datasets[0].backgroundColor = 'rgba(59, 130, 246, 0.1)';
    pressureConfig.options.scales.y.title.text = 'Pressure (bar)';
    pressureConfig.options.scales.y.suggestedMin = 0;
    pressureConfig.options.scales.y.suggestedMax = 12;
    chartPressure = new Chart(ctxP, pressureConfig);

    // Grams Chart - Green
    const gramsConfig = JSON.parse(JSON.stringify(baseConfig));
    gramsConfig.data.datasets[0].borderColor = '#22c55e';
    gramsConfig.data.datasets[0].backgroundColor = 'rgba(34, 197, 94, 0.1)';
    gramsConfig.options.scales.y.title.text = 'Weight (grams)';
    gramsConfig.options.scales.y.suggestedMin = 0;
    gramsConfig.options.scales.y.suggestedMax = 50;
    chartGrams = new Chart(ctxG, gramsConfig);

    // Temperature Chart - Orange
    const tempConfig = JSON.parse(JSON.stringify(baseConfig));
    tempConfig.data.datasets[0].borderColor = '#f59e0b';
    tempConfig.data.datasets[0].backgroundColor = 'rgba(245, 158, 11, 0.1)';
    tempConfig.options.scales.y.title.text = 'Temperature (°C)';
    tempConfig.options.scales.y.suggestedMin = 80;
    tempConfig.options.scales.y.suggestedMax = 100;
    chartTemp = new Chart(ctxT, tempConfig);

    appendLog("Charts initialized successfully", "info");
  } catch (error) {
    appendLog(`Chart initialization error: ${error.message}`, "error");
  }
}

function updateCharts(data) {
  if (typeof Chart === 'undefined') return;

  const t = data.ts !== undefined ? data.ts : Date.now();

  function pushData(chart, value, name) {
    if (!chart || value === undefined || value === null || isNaN(value)) return;
    
    try {
      const dataset = chart.data.datasets[0];
      
      // Add new data point
      dataset.data.push({
        x: t,
        y: parseFloat(value.toFixed(3))
      });

      // Cap history length
      if (dataset.data.length > HISTORY_LENGTH) {
        dataset.data.shift();
      }

      // Update chart without animation for smooth real-time updates
      chart.update('none');
    } catch (error) {
      console.warn(`Error updating ${name} chart:`, error);
    }
  }

  // Update charts with validation
  if (data.pressure !== undefined) {
    pushData(chartPressure, data.pressure, 'pressure');
  }
  if (data.grams !== undefined) {
    pushData(chartGrams, data.grams, 'grams');
  }
  if (data.t1_in !== undefined) {
    pushData(chartTemp, data.t1_in, 'temperature');
  }
}

// ---------------------------------------------------------------------------
// Live Brew Chart (single combined chart)
// ---------------------------------------------------------------------------
let brewChart = null;
function initBrewChart() {
  const canvas = document.getElementById('brew-chart');
  if (!canvas || typeof Chart === 'undefined') {
    appendLog('Brew chart unavailable (canvas/Chart.js missing)', 'warn');
    return;
  }
  try {
    brewChart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        datasets: [
          { label: 'Flow (ml/s)', data: [], borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.1)', tension: 0.2, pointRadius: 0 },
          { label: 'Grams', data: [], borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,0.1)', tension: 0.2, pointRadius: 0 },
          { label: 'Pressure (bar)', data: [], borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', tension: 0.2, pointRadius: 0 },
          { label: 'Temperature (°C)', data: [], borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.1)', tension: 0.2, pointRadius: 0 },
        ]
      },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        scales: {
          x: { type: 'linear', position: 'bottom', ticks: { color: '#6b7280' }, grid: { color: 'rgba(55,65,81,0.3)' } },
          y: { ticks: { color: '#6b7280' }, grid: { color: 'rgba(55,65,81,0.3)' } }
        },
        plugins: { legend: { display: true } }
      }
    });
    appendLog('Brew chart initialized', 'info');
  } catch (e) {
    appendLog(`Brew chart init error: ${e.message}`, 'error');
  }
}

function updateBrewChart(data) {
  if (!brewChart || !data) return;
  const t = data.ts !== undefined ? data.ts : Date.now();
  const ds = brewChart.data.datasets;
  const push = (idx, val) => {
    if (val === undefined || val === null || isNaN(val)) return;
    ds[idx].data.push({ x: t, y: Number(val) });
    if (ds[idx].data.length > HISTORY_LENGTH) ds[idx].data.shift();
  };
  push(0, data.flow);
  push(1, data.grams);
  push(2, data.pressure);
  push(3, data.t1_in);
  try { brewChart.update('none'); } catch {}
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Settings Tab Management
// ---------------------------------------------------------------------------
function initSettingsTab() {
  console.log("Initializing Settings Tab...");
  
  // Settings Event Listeners (only initialize if settings content is present)
  const settingsContent = document.getElementById("settings-content");
  if (settingsContent) {
    try {
      initSettingsControls();
      console.log("Settings controls initialized");
    } catch (error) {
      console.error("Error initializing settings controls:", error);
    }
  }
}

function initSettingsControls() {
  console.log("Initializing settings controls...");
  
  // Helper function to safely add event listener
  function safeAddEventListener(id, handler, description) {
    const element = document.getElementById(id);
    if (element) {
      element.addEventListener("click", handler);
      console.log(`${description} listener added`);
    } else {
      console.warn(`Element ${id} not found for ${description}`);
    }
  }
  
  // PID Settings
  safeAddEventListener("apply-setpoints", applyPidSetpoints, "PID Setpoints");
  safeAddEventListener("apply-gains", applyPidGains, "PID Gains");
  safeAddEventListener("apply-limits", applyPidLimits, "PID Limits");
  safeAddEventListener("apply-sample-time", applyPidSampleTime, "PID Sample Time");

  // Motor Settings
  safeAddEventListener("apply-motor-settings", applyMotorSettings, "Motor Settings");

  // Sensor Settings
  safeAddEventListener("apply-sensor-settings", applySensorSettings, "Sensor Settings");

  // Valve & Button Settings
  safeAddEventListener("apply-valve-button-settings", applyValveButtonSettings, "Valve Button Settings");

  // Emergency Settings
  safeAddEventListener("apply-emergency-settings", applyEmergencySettings, "Emergency Settings");

  // System Settings
  safeAddEventListener("apply-system-settings", applySystemSettings, "System Settings");

  // Global Settings Actions
  safeAddEventListener("save-all-settings", saveAllSettings, "Save All Settings");
  safeAddEventListener("load-default-settings", loadDefaultSettings, "Load Default Settings");
  safeAddEventListener("export-settings", exportSettings, "Export Settings");
  safeAddEventListener("import-settings", importSettings, "Import Settings");
  
  console.log("Settings controls initialization complete");
}

// PID Settings Functions
function applyPidSetpoints() {
  const setpoints = {
    pid1: parseFloat(document.getElementById("pid1-setpoint").value),
    pid2: parseFloat(document.getElementById("pid2-setpoint").value),
    pid3: parseFloat(document.getElementById("pid3-setpoint").value)
  };

  sendCommand({
    cmd: "SET_PID_SETPOINTS",
    setpoints: setpoints
  });
  appendLog(`PID Setpoints applied: P1=${setpoints.pid1}, P2=${setpoints.pid2}, P3=${setpoints.pid3}`);
}

function applyPidGains() {
  const gains = {
    pid1: {
      kp: parseFloat(document.getElementById("pid1-kp").value),
      ki: parseFloat(document.getElementById("pid1-ki").value),
      kd: parseFloat(document.getElementById("pid1-kd").value)
    },
    pid2: {
      kp: parseFloat(document.getElementById("pid2-kp").value),
      ki: parseFloat(document.getElementById("pid2-ki").value),
      kd: parseFloat(document.getElementById("pid2-kd").value)
    },
    pid3: {
      kp: parseFloat(document.getElementById("pid3-kp").value),
      ki: parseFloat(document.getElementById("pid3-ki").value),
      kd: parseFloat(document.getElementById("pid3-kd").value)
    }
  };

  sendCommand({
    cmd: "SET_PID_GAINS",
    gains: gains
  });
  appendLog(`PID Gains applied successfully`);
}

function applyPidLimits() {
  const limits = {
    output_max: parseInt(document.getElementById("pid-output-max").value),
    output_min: parseInt(document.getElementById("pid-output-min").value),
    windup_clamp: parseInt(document.getElementById("pid-windup-clamp").value)
  };

  sendCommand({
    cmd: "SET_PID_LIMITS",
    limits: limits
  });
  appendLog(`PID Limits applied: Max=${limits.output_max}, Min=${limits.output_min}, Clamp=${limits.windup_clamp}`);
}

function applyPidSampleTime() {
  const sampleTime = parseInt(document.getElementById("pid-sample-time").value);
  
  sendCommand({
    cmd: "SET_PID_SAMPLE_TIME",
    sample_time: sampleTime
  });
  appendLog(`PID Sample Time set to ${sampleTime}ms`);
}

// Motor Settings Functions
function applyMotorSettings() {
  const settings = {
    base_freq: parseInt(document.getElementById("motor-base-freq").value),
    max_freq: parseInt(document.getElementById("motor-max-freq").value),
    max_pulses: parseInt(document.getElementById("motor-max-pulses").value),
    max_batch: parseInt(document.getElementById("motor-max-batch").value),
    emergency_behavior: document.getElementById("motor-emergency-behavior").value,
    invert_direction: document.getElementById("motor-invert-direction").checked
  };

  sendCommand({
    cmd: "SET_MOTOR_SETTINGS",
    settings: settings
  });
  appendLog(`Motor settings applied: Base=${settings.base_freq}Hz, Max=${settings.max_freq}Hz`);
}

// Sensor Settings Functions
function applySensorSettings() {
  const settings = {
    temperature_offsets: {
      temp1: parseFloat(document.getElementById("temp1-offset").value),
      temp2: parseFloat(document.getElementById("temp2-offset").value),
      temp3: parseFloat(document.getElementById("temp3-offset").value)
    },
    pressure_calibration: {
      offset: parseFloat(document.getElementById("pressure-offset").value),
      scale: parseFloat(document.getElementById("pressure-scale").value)
    },
    loadcell_factor: parseFloat(document.getElementById("loadcell-factor").value),
    refresh_rate: parseInt(document.getElementById("sensor-refresh-rate").value),
    filter_type: document.getElementById("sensor-filter-type").value,
    units: {
      temperature: document.getElementById("temp-units").value,
      pressure: document.getElementById("pressure-units").value
    }
  };

  sendCommand({
    cmd: "SET_SENSOR_SETTINGS",
    settings: settings
  });
  appendLog(`Sensor settings applied: Refresh=${settings.refresh_rate}ms, Filter=${settings.filter_type}`);
}

// Valve & Button Settings Functions
function applyValveButtonSettings() {
  const settings = {
    valve_invert: {
      valve1: document.getElementById("valve1-invert").checked,
      valve2: document.getElementById("valve2-invert").checked,
      valve3: document.getElementById("valve3-invert").checked
    },
    button_debounce: parseInt(document.getElementById("button-debounce").value)
  };

  sendCommand({
    cmd: "SET_VALVE_BUTTON_SETTINGS",
    settings: settings
  });
  appendLog(`Valve & Button settings applied: Debounce=${settings.button_debounce}ms`);
}

// Emergency Settings Functions
function applyEmergencySettings() {
  const settings = {
    limit_switches: {
      top_emergency: document.getElementById("top-limit-emergency").checked,
      bottom_emergency: document.getElementById("bottom-limit-emergency").checked
    },
    reset_mode: document.querySelector('input[name="emergency-reset"]:checked').value
  };

  sendCommand({
    cmd: "SET_EMERGENCY_SETTINGS",
    settings: settings
  });
  appendLog(`Emergency settings applied: Reset mode=${settings.reset_mode}`);
}

// System Settings Functions
function applySystemSettings() {
  const settings = {
    logging: {
      enabled: document.getElementById("csv-logging-enable").checked,
      interval: parseInt(document.getElementById("log-interval").value),
      auto_split: document.getElementById("auto-split-log").checked,
      fields: {
        pressure: document.getElementById("log-pressure").checked,
        flow: document.getElementById("log-flow").checked,
        grams: document.getElementById("log-grams").checked,
        temperature: document.getElementById("log-temperature").checked,
        pid: document.getElementById("log-pid").checked,
        motor: document.getElementById("log-motor").checked
      }
    },
    communication: {
      serial_port: document.getElementById("serial-port").value,
      baud_rate: parseInt(document.getElementById("serial-baudrate").value),
      ws_reconnect_timeout: parseInt(document.getElementById("ws-reconnect-timeout").value)
    }
  };

  sendCommand({
    cmd: "SET_SYSTEM_SETTINGS",
    settings: settings
  });
  appendLog(`System settings applied: Port=${settings.communication.serial_port}, Baud=${settings.communication.baud_rate}`);
}

// Global Settings Actions
function saveAllSettings() {
  const allSettings = gatherAllSettings();
  
  sendCommand({
    cmd: "SAVE_ALL_SETTINGS",
    settings: allSettings
  });
  
  // Also save to localStorage for persistence
  localStorage.setItem('espresso_settings', JSON.stringify(allSettings));
  appendLog("All settings saved successfully", "info");
}

function loadDefaultSettings() {
  if (confirm("Are you sure you want to load default settings? This will overwrite all current settings.")) {
    sendCommand({ cmd: "LOAD_DEFAULT_SETTINGS" });
    loadDefaultValuesToForm();
    appendLog("Default settings loaded", "info");
  }
}

function exportSettings() {
  const settings = gatherAllSettings();
  const dataStr = JSON.stringify(settings, null, 2);
  const dataBlob = new Blob([dataStr], {type: 'application/json'});
  
  const link = document.createElement('a');
  link.href = URL.createObjectURL(dataBlob);
  link.download = `espresso_settings_${new Date().toISOString().slice(0,10)}.json`;
  link.click();
  
  appendLog("Settings exported to file", "info");
}

function importSettings() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  
  input.onchange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const settings = JSON.parse(e.target.result);
          applySettingsToForm(settings);
          appendLog("Settings imported successfully", "info");
        } catch (error) {
          appendLog(`Error importing settings: ${error.message}`, "error");
        }
      };
      reader.readAsText(file);
    }
  };
  
  input.click();
}

// Helper Functions
function gatherAllSettings() {
  // Gather all settings from form inputs
  return {
    pid: {
      setpoints: {
        pid1: parseFloat(document.getElementById("pid1-setpoint").value),
        pid2: parseFloat(document.getElementById("pid2-setpoint").value),
        pid3: parseFloat(document.getElementById("pid3-setpoint").value)
      },
      gains: {
        pid1: {
          kp: parseFloat(document.getElementById("pid1-kp").value),
          ki: parseFloat(document.getElementById("pid1-ki").value),
          kd: parseFloat(document.getElementById("pid1-kd").value)
        },
        pid2: {
          kp: parseFloat(document.getElementById("pid2-kp").value),
          ki: parseFloat(document.getElementById("pid2-ki").value),
          kd: parseFloat(document.getElementById("pid2-kd").value)
        },
        pid3: {
          kp: parseFloat(document.getElementById("pid3-kp").value),
          ki: parseFloat(document.getElementById("pid3-ki").value),
          kd: parseFloat(document.getElementById("pid3-kd").value)
        }
      },
      limits: {
        output_max: parseInt(document.getElementById("pid-output-max").value),
        output_min: parseInt(document.getElementById("pid-output-min").value),
        windup_clamp: parseInt(document.getElementById("pid-windup-clamp").value)
      },
      sample_time: parseInt(document.getElementById("pid-sample-time").value)
    },
    // Add other settings sections here...
    timestamp: new Date().toISOString()
  };
}

function applySettingsToForm(settings) {
  if (settings.pid) {
    if (settings.pid.setpoints) {
      document.getElementById("pid1-setpoint").value = settings.pid.setpoints.pid1 || 8.5;
      document.getElementById("pid2-setpoint").value = settings.pid.setpoints.pid2 || 2.0;
      document.getElementById("pid3-setpoint").value = settings.pid.setpoints.pid3 || 90.0;
    }
    // Apply other settings...
  }
}

function loadDefaultValuesToForm() {
  // Reset all form values to defaults
  document.getElementById("pid1-setpoint").value = 8.5;
  document.getElementById("pid2-setpoint").value = 2.0;
  document.getElementById("pid3-setpoint").value = 90.0;
  // Add more defaults...
}

function loadCurrentSettings() {
  // Try to load settings from localStorage
  const saved = localStorage.getItem('espresso_settings');
  if (saved) {
    try {
      const settings = JSON.parse(saved);
      applySettingsToForm(settings);
    } catch (error) {
      console.warn('Error loading saved settings:', error);
    }
  }
}

// ---------------------------------------------------------------------------
// Global Initialization
// ---------------------------------------------------------------------------
// Expose initializers for other scripts
window.EspressoApp = {
  initCharts,
  initBrewChart,
  initSocket,
  initControls,
  initSettingsTab,
  initCameraControls,
  initHeaderSerialControls,
  appendLog
};

// ---------------------------------------------------------------------------
// Camera Controls
// ---------------------------------------------------------------------------
function initCameraControls() {
  const sourceSel = document.getElementById('camera-source');
  const localConfig = document.getElementById('local-config');
  const ipConfig = document.getElementById('ip-config');
  const localSelect = document.getElementById('local-camera-select');
  const ipUrlInput = document.getElementById('ip-camera-url');
  const videoEl = document.getElementById('camera-video');
  const imgEl = document.getElementById('camera-img');
  const placeholder = document.getElementById('camera-placeholder');
  const btnStart = document.getElementById('start-camera');
  const btnStop = document.getElementById('stop-camera');
  const btnSnapshot = document.getElementById('snapshot-camera');

  let currentStream = null;
  let currentMode = 'none'; // 'none' | 'local' | 'ip'

  async function listCameras() {
    try {
      await navigator.mediaDevices.getUserMedia({ video: true });
      const devices = await navigator.mediaDevices.enumerateDevices();
      const cams = devices.filter(d => d.kind === 'videoinput');
      localSelect.innerHTML = '<option value="">Select Camera</option>';
      cams.forEach(cam => {
        const opt = document.createElement('option');
        opt.value = cam.deviceId;
        opt.textContent = cam.label || `Camera ${localSelect.length}`;
        localSelect.appendChild(opt);
      });
    } catch (err) {
      appendLog(`Unable to list cameras: ${err.message}`, 'warn');
    }
  }

  function showMode(mode) {
    currentMode = mode;
    localConfig.style.display = mode === 'local' ? 'block' : 'none';
    ipConfig.style.display = mode === 'ip' ? 'block' : 'none';
  }

  sourceSel.addEventListener('change', () => {
    const v = sourceSel.value;
    showMode(v);
    if (v === 'local') {
      listCameras();
    }
  });

  async function startLocalCamera() {
    try {
      const deviceId = localSelect.value || undefined;
      const constraints = deviceId ? { video: { deviceId: { exact: deviceId } } } : { video: true };
      if (currentStream) stopStream();
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      currentStream = stream;
      videoEl.srcObject = stream;
      videoEl.style.display = 'block';
      imgEl.style.display = 'none';
      placeholder.style.display = 'none';
      appendLog('Local camera started');
    } catch (err) {
      appendLog(`Start local camera failed: ${err.message}`, 'error');
    }
  }

  function startIpCamera() {
    const url = ipUrlInput.value.trim();
    if (!url) {
      appendLog('Please enter an IP camera URL', 'warn');
      return;
    }
    if (currentStream) stopStream();
    imgEl.src = url; // Assumes MJPEG/HTTP stream
    imgEl.style.display = 'block';
    videoEl.style.display = 'none';
    placeholder.style.display = 'none';
    appendLog('IP camera started');
  }

  function stopStream() {
    if (currentStream) {
      currentStream.getTracks().forEach(t => t.stop());
      currentStream = null;
    }
    videoEl.srcObject = null;
    videoEl.style.display = 'none';
    imgEl.src = '';
    imgEl.style.display = 'none';
    placeholder.style.display = 'block';
    appendLog('Camera stopped');
  }

  function snapshot() {
    try {
      if (videoEl.style.display === 'block' && videoEl.videoWidth > 0) {
        const canvas = document.createElement('canvas');
        canvas.width = videoEl.videoWidth;
        canvas.height = videoEl.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(videoEl, 0, 0);
        imgEl.src = canvas.toDataURL('image/png');
        imgEl.style.display = 'block';
        videoEl.style.display = 'none';
        appendLog('Snapshot captured from local camera');
      } else if (imgEl.style.display === 'block' && imgEl.src) {
        appendLog('Snapshot already displayed from IP camera');
      } else {
        appendLog('No active camera to snapshot', 'warn');
      }
    } catch (err) {
      appendLog(`Snapshot error: ${err.message}`, 'error');
    }
  }

  btnStart.addEventListener('click', () => {
    if (currentMode === 'local') startLocalCamera();
    else if (currentMode === 'ip') startIpCamera();
    else appendLog('Select a camera source first', 'warn');
  });
  btnStop.addEventListener('click', stopStream);
  btnSnapshot.addEventListener('click', snapshot);
}

// ---------------------------------------------------------------------------
// Header Serial Controls (UI only; sends commands via WebSocket/REST)
// ---------------------------------------------------------------------------
function initHeaderSerialControls() {
  const portSel = document.getElementById('header-com-port');
  const baudSel = document.getElementById('header-baud-rate');
  const btnConnect = document.getElementById('header-connect-serial');
  const btnDisconnect = document.getElementById('header-disconnect-serial');
  const btnRefresh = document.getElementById('header-refresh-ports');
  const statusEl = document.getElementById('serial-header-status');

  function setSerialHeaderStatus(connected) {
    statusEl.textContent = connected ? 'Connected' : 'Disconnected';
    statusEl.classList.toggle('status-connected', !!connected);
    statusEl.classList.toggle('status-disconnected', !connected);
  }

  // Try to fetch available COM ports via REST if backend provides it
  function loadPorts() {
    fetch('/api/serial/ports')
      .then(r => r.json())
      .then(list => {
        if (Array.isArray(list)) {
          portSel.innerHTML = '<option value="">Select COM</option>';
          list.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p;
            opt.textContent = p;
            portSel.appendChild(opt);
          });
          appendLog(`Ports refreshed: ${list.join(', ')}`);
        }
      })
      .catch(() => {
        appendLog('Port list not available; enter manually if needed', 'warn');
      });
  }
  loadPorts();
  if (btnRefresh) btnRefresh.addEventListener('click', loadPorts);

  btnConnect.addEventListener('click', () => {
    const port = portSel.value;
    const baud = parseInt(baudSel.value, 10) || 115200;
    if (!port) {
      appendLog('Please select a COM port', 'warn');
      return;
    }
    // Prefer REST if available
    fetch('/api/serial/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ port, baud })
    }).then(r => r.json()).then(res => {
      const ok = !!res.connected;
      setSerialHeaderStatus(ok);
      appendLog(ok ? `Serial connected: ${port} @ ${baud}` : `Serial connect failed`, ok ? 'info' : 'error');
    }).catch(() => {
      // Fallback to WebSocket command
      sendCommand({ cmd: 'SET_SYSTEM_SETTINGS', settings: { communication: { serial_port: port, baud_rate: baud } } });
      appendLog(`Requested serial connect via command: ${port} @ ${baud}`);
    });
  });

  btnDisconnect.addEventListener('click', () => {
    fetch('/api/serial/disconnect', { method: 'POST' }).then(r => r.json()).then(res => {
      const ok = !!res.disconnected || !res.connected;
      setSerialHeaderStatus(false);
      appendLog('Serial disconnected', 'info');
    }).catch(() => {
      sendCommand({ cmd: 'SERIAL_DISCONNECT' });
      appendLog('Requested serial disconnect via command');
    });
  });
}

