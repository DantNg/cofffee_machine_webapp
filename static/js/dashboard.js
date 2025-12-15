// dashboard.js

(function(){
  document.addEventListener('DOMContentLoaded', () => {
    try {
      // Only initialize on pages that contain the dashboard content
      const hasDashboard = !!document.getElementById('dashboard-content');
      if (!hasDashboard) {
        return;
      }
      const A = window.EspressoApp;
      A.appendLog('Init dashboard...', 'info');
      A.initBrewChart();
      A.initCharts();
      A.initSocket();
      // Load last serial logs for context
      if (A.loadRecentSerialLogs) A.loadRecentSerialLogs(200);
      // Load schema first so controls can clamp inputs
      const afterSchema = () => {
        try {
          // Apply schema limits to pulse input if available
          const pulse = document.getElementById('pulse-count-input');
          if (pulse && A.loadAppSchema) {
            // If schema already loaded, set attributes now; otherwise noop
            const rule = (window.AppSchemaGetter && window.AppSchemaGetter('SEND_PULSES','count')) || null;
            if (rule) {
              if (typeof rule.min === 'number') pulse.min = String(rule.min);
              if (typeof rule.max === 'number') pulse.max = String(rule.max);
              if (pulse.value) {
                const v = Math.min(Math.max(parseInt(pulse.value,10)||0, rule.min||1), rule.max||5000);
                pulse.value = String(v);
              }
            }
          }
        } catch(_){}
        A.initControls();
        A.initCameraControls();
        A.initHeaderSerialControls();
        A.appendLog('Dashboard ready', 'info');
      };
      if (A.loadAppSchema) {
        A.loadAppSchema().finally(afterSchema);
      } else {
        afterSchema();
      }
    } catch (e) {
      console.error('Dashboard init error:', e);
      window.EspressoApp && window.EspressoApp.appendLog(`Dashboard init error: ${e.message}`, 'error');
    }
  });
})();
