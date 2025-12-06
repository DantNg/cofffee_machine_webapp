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
      A.initControls();
      A.initCameraControls();
      A.initHeaderSerialControls();
      A.appendLog('Dashboard ready', 'info');
    } catch (e) {
      console.error('Dashboard init error:', e);
      window.EspressoApp && window.EspressoApp.appendLog(`Dashboard init error: ${e.message}`, 'error');
    }
  });
})();
