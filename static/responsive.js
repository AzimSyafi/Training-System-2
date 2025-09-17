(function(){
  function clamp(n, min, max){ return Math.max(min, Math.min(max, n)); }

  function computeScales(w){
    let fontScale = 1;
    let spacingScale = 1;
    if (w <= 1024) {
      const t = clamp((1024 - w) / (1024 - 768), 0, 1); // 0..1 in tablet band
      fontScale += t * 0.04;     // up to +4%
      spacingScale += t * 0.06;  // up to +6%
    }
    if (w <= 768) {
      const t = clamp((768 - w) / (768 - 360), 0, 1); // 0..1 in mobile band (down to 360px)
      fontScale += t * 0.08;     // additional up to +8%
      spacingScale += t * 0.10;  // additional up to +10%
    }
    return { fontScale, spacingScale };
  }

  function applyScales(scales){
    const root = document.documentElement;
    root.style.setProperty('--rs-font-scale', scales.fontScale.toFixed(3));
    root.style.setProperty('--rs-spacing-scale', scales.spacingScale.toFixed(3));
  }

  function autoSidebarCollapse(w){
    const sidebar = document.getElementById('sidebar');
    const main = document.getElementById('main-content');
    if (!sidebar || !main || document.body.classList.contains('no-sidebar')) return;

    if (w <= 768) {
      if (!sidebar.classList.contains('collapsed')) {
        sidebar.dataset.rsWasCollapsed = 'false'; // remember expanded state
        sidebar.classList.add('collapsed');
        main.classList.add('collapsed');
      } else {
        sidebar.dataset.rsWasCollapsed = 'true';
      }
    } else {
      if (sidebar.dataset.rsWasCollapsed === 'false') {
        sidebar.classList.remove('collapsed');
        main.classList.remove('collapsed');
      }
      delete sidebar.dataset.rsWasCollapsed;
    }
  }

  function run(){
    const w = window.innerWidth || document.documentElement.clientWidth || 1024;
    applyScales(computeScales(w));
    autoSidebarCollapse(w);
  }

  let resizeRAF = null;
  window.addEventListener('resize', function(){
    if (resizeRAF) return;
    resizeRAF = requestAnimationFrame(function(){ resizeRAF = null; run(); });
  });
  window.addEventListener('orientationchange', run, { passive: true });
  document.addEventListener('DOMContentLoaded', run);
})();
