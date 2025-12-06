// settings.js

(function(){
  document.addEventListener('DOMContentLoaded', () => {
    try {
      const A = window.EspressoApp;
      A.appendLog('Init settings...', 'info');
      A.initSettingsTab();
      A.appendLog('Settings ready', 'info');
    } catch (e) {
      console.error('Settings init error:', e);
      window.EspressoApp && window.EspressoApp.appendLog(`Settings init error: ${e.message}`, 'error');
    }
  });
})();
