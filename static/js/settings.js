// settings.js

(function(){
  document.addEventListener('DOMContentLoaded', () => {
    try {
      const A = window.EspressoApp;
      A.appendLog('Init settings...', 'info');
      // Ensure WebSocket + header serial controls are active on settings page
      if (A.initSocket) A.initSocket();
      if (A.initHeaderSerialControls) A.initHeaderSerialControls();
      // Load schema in case commands/settings need constraints
      const afterSchema = () => {
        A.initSettingsTab();
        // Wire Serial Command & Monitor controls
        initSettingsSerialCommandUI();
        initSettingsSerialMonitor();
        A.appendLog('Settings ready', 'info');
      };
      if (A.loadAppSchema) {
        A.loadAppSchema().finally(afterSchema);
      } else {
        afterSchema();
      }
    } catch (e) {
      console.error('Settings init error:', e);
      window.EspressoApp && window.EspressoApp.appendLog(`Settings init error: ${e.message}`, 'error');
    }
  });
})();

// -----------------------------
// Serial Command UI (manual + quick)
// -----------------------------
function initSettingsSerialCommandUI() {
  const sendBtn = document.getElementById('send-manual-command');
  const input = document.getElementById('manual-command');
  // Helper to enable/disable serial command UI based on WS connection
  function setSerialUiEnabled(enabled) {
    try {
      if (sendBtn) sendBtn.disabled = !enabled;
      if (input) input.disabled = !enabled;
      document.querySelectorAll('.quick-cmd').forEach(btn => { btn.disabled = !enabled; });
    } catch(_) {}
  }

  // Initialize UI state based on current socket state
  if (window.socket) {
    setSerialUiEnabled(!!window.socket.connected);
    try {
      window.socket.off && window.socket.off('connect');
      window.socket.off && window.socket.off('disconnect');
    } catch(_) {}
    try {
      window.socket.on('connect', () => setSerialUiEnabled(true));
      window.socket.on('disconnect', () => setSerialUiEnabled(false));
    } catch(_) {}
  }
  if (sendBtn && input) {
    sendBtn.addEventListener('click', () => {
      const txt = input.value.trim();
      if (!txt) return;
      try {
        const payload = JSON.parse(txt);
        if (!payload || typeof payload !== 'object') throw new Error('Invalid JSON');
        window.EspressoApp && window.EspressoApp.appendLog(`Manual send: ${txt}`);
        // Send via shared sender
        if (window.EspressoApp && typeof window.EspressoApp.sendCommand === 'function') {
          const s = window.socket;
          if (!s || !s.connected) {
            window.EspressoApp.appendLog('Cannot send: WebSocket not connected', 'error');
            return;
          }
          window.EspressoApp.sendCommand(payload);
        } else if (window.socket) {
          if (!window.socket.connected) {
            window.EspressoApp && window.EspressoApp.appendLog('Cannot send: WebSocket not connected', 'error');
            return;
          }
          window.socket.emit('message', { type: 'command', payload });
        }
      } catch (err) {
        window.EspressoApp && window.EspressoApp.appendLog(`Manual command error: ${err.message}`, 'error');
      }
    });
    // Enter to send
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendBtn.click();
      }
    });
  }

  document.querySelectorAll('.quick-cmd').forEach(btn => {
    btn.addEventListener('click', () => {
      const str = btn.getAttribute('data-cmd');
      if (!str) return;
      try {
        const payload = JSON.parse(str);
        window.EspressoApp && window.EspressoApp.appendLog(`Quick cmd: ${str}`);
        if (window.EspressoApp && typeof window.EspressoApp.sendCommand === 'function') {
          const s = window.socket;
          if (!s || !s.connected) {
            window.EspressoApp.appendLog('Cannot send: WebSocket not connected', 'error');
            return;
          }
          window.EspressoApp.sendCommand(payload);
        } else if (window.socket) {
          if (!window.socket.connected) {
            window.EspressoApp && window.EspressoApp.appendLog('Cannot send: WebSocket not connected', 'error');
            return;
          }
          window.socket.emit('message', { type: 'command', payload });
        }
      } catch (err) {
        window.EspressoApp && window.EspressoApp.appendLog(`Quick command parse error: ${err.message}`, 'error');
      }
    });
  });
}

// -----------------------------
// Serial Monitor on settings page
// -----------------------------
function initSettingsSerialMonitor() {
  const container = document.getElementById('serial-monitor');
  if (!container) return;
  const autoScroll = document.getElementById('auto-scroll-monitor');
  const showTs = document.getElementById('show-timestamps-monitor');
  const clearBtn = document.getElementById('clear-monitor');
  const saveBtn = document.getElementById('save-monitor');

  function appendLine(line, ts) {
    try {
      const div = document.createElement('div');
      div.className = 'monitor-line';
      div.textContent = (showTs && showTs.checked && ts ? `[${ts}] ` : '') + line;
      container.appendChild(div);
      if (!document.getElementById('show-raw-data')?.checked) {
        // keep all lines for now; advanced filtering could be added later
      }
      if (!autoScroll || autoScroll.checked) {
        container.scrollTop = container.scrollHeight;
      }
    } catch(_) {}
  }

  // Load recent logs for context
  try {
    fetch('/api/serial/logs?count=200').then(r => r.json()).then(res => {
      const logs = Array.isArray(res.logs) ? res.logs : [];
      logs.forEach(entry => appendLine(entry.line || entry.message || '', entry.ts));
    }).catch(() => {});
  } catch(_) {}

  // Listen to real-time serial logs
  if (window.socket) {
    try {
      window.socket.on('event_log', (msg) => {
        if (!msg) return;
        appendLine(msg.message || '', msg.ts);
      });
      window.socket.on('connect', () => {
        // Backfill a few lines on reconnect
        try {
          fetch('/api/serial/logs?count=50').then(r => r.json()).then(res => {
            const logs = Array.isArray(res.logs) ? res.logs : [];
            logs.forEach(entry => appendLine(entry.line || entry.message || '', entry.ts));
          });
        } catch(_) {}
      });
    } catch(_) {}
  }

  if (clearBtn) clearBtn.addEventListener('click', () => { container.innerHTML = '<div class="monitor-placeholder">Serial data will appear here...</div>'; });
  if (saveBtn) saveBtn.addEventListener('click', () => {
    const lines = Array.from(container.querySelectorAll('.monitor-line')).map(n => n.textContent);
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `serial_monitor_${new Date().toISOString().replace(/[:.]/g,'-')}.log`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });
}
