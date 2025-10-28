(function(){
  function clamp(n, min, max){ return Math.max(min, Math.min(max, n)); }

  function computeScales(w){
    let fontScale = 1;
    let spacingScale = 1;
    if (w <= 1024) {
      const t = clamp((1024 - w) / (1024 - 768), 0, 1);
      fontScale += t * 0.04;
      spacingScale += t * 0.06;
    }
    if (w <= 768) {
      const t = clamp((768 - w) / (768 - 360), 0, 1);
      fontScale += t * 0.08;
      spacingScale += t * 0.10;
    }
    return { fontScale, spacingScale };
  }

  function applyScales(scales){
    const root = document.documentElement;
    root.style.setProperty('--rs-font-scale', scales.fontScale.toFixed(3));
    root.style.setProperty('--rs-spacing-scale', scales.spacingScale.toFixed(3));
  }

  function run(){
    const w = window.innerWidth || document.documentElement.clientWidth || 1024;
    applyScales(computeScales(w));
  }

  let resizeRAF = null;
  window.addEventListener('resize', function(){
    if (resizeRAF) return;
    resizeRAF = requestAnimationFrame(function(){ resizeRAF = null; run(); });
  });
  window.addEventListener('orientationchange', run, { passive: true });
  document.addEventListener('DOMContentLoaded', run);

  // ========================================
  // UNIVERSAL HAMBURGER MENU (ALL SCREENS)
  // ========================================

  function initUniversalNav() {
    // Check if we're on a page with sidebar
    if (document.body.classList.contains('no-sidebar')) {
      return;
    }

    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;

    let navToggle = null;
    let overlay = null;

    function createNavElements() {
      // Create hamburger button
      if (!navToggle) {
        navToggle = document.createElement('button');
        navToggle.className = 'desktop-nav-toggle';
        navToggle.setAttribute('aria-label', 'Toggle navigation menu');
        navToggle.setAttribute('aria-expanded', 'false');
        navToggle.innerHTML = '<i class="fas fa-bars"></i>';
        document.body.appendChild(navToggle);

        navToggle.addEventListener('click', function(e) {
          e.stopPropagation();
          if (sidebar.classList.contains('menu-open')) {
            closeMenu();
          } else {
            openMenu();
          }
        });
      }

      // Create overlay
      if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'nav-overlay';
        overlay.setAttribute('aria-hidden', 'true');
        document.body.appendChild(overlay);

        overlay.addEventListener('click', closeMenu);
      }
    }

    function openMenu() {
      sidebar.classList.add('menu-open');
      document.body.classList.add('sidebar-open'); // Add class to body for hamburger positioning
      if (overlay) overlay.classList.add('active');
      if (navToggle) {
        navToggle.classList.add('active');
        navToggle.setAttribute('aria-expanded', 'true');
        navToggle.innerHTML = '<i class="fas fa-times"></i>'; // Change to times icon
      }
      document.body.style.overflow = 'hidden';
    }

    function closeMenu() {
      sidebar.classList.remove('menu-open');
      document.body.classList.remove('sidebar-open'); // Remove class from body
      if (overlay) overlay.classList.remove('active');
      if (navToggle) {
        navToggle.classList.remove('active');
        navToggle.setAttribute('aria-expanded', 'false');
        navToggle.innerHTML = '<i class="fas fa-bars"></i>'; // Change back to bars icon
      }
      document.body.style.overflow = '';
    }

    // Close menu when nav link is clicked
    const navLinks = sidebar.querySelectorAll('.nav-link');
    navLinks.forEach(function(link) {
      link.addEventListener('click', function(e) {
        // Don't prevent default - let the link navigate normally
        // Just close the menu immediately
        closeMenu();
      });
    });

    // Also close menu when clicking inside the sidebar (but not on the toggle button)
    sidebar.addEventListener('click', function(e) {
      // If clicked element is a link or inside a link, close menu
      if (e.target.closest('.nav-link')) {
        // Let the navigation happen, menu will close
        setTimeout(closeMenu, 100);
      }
    });

    // Close menu on Escape key
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && sidebar.classList.contains('menu-open')) {
        closeMenu();
      }
    });

    // Initialize navigation elements
    createNavElements();
  }

  // Initialize after DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initUniversalNav);
  } else {
    initUniversalNav();
  }

  // ========================================
  // MOBILE TABLE RESPONSIVE HANDLING
  // ========================================

  function initMobileTables() {
    const isMobile = window.innerWidth <= 768;
    const tables = document.querySelectorAll('table');

    tables.forEach(table => {
      const tbody = table.querySelector('tbody');
      if (!tbody) return;

      const rows = tbody.querySelectorAll('tr');
      rows.forEach(row => {
        const nameCell = row.querySelector('.name-column');
        const emailCell = row.querySelector('.email-column');

        if (isMobile) {
          // Hide other cells except name
          const cells = row.querySelectorAll('td');
          cells.forEach((cell) => {
            if (cell !== nameCell) {
              cell.style.display = 'none';
            }
          });
        } else {
          // Desktop: show all cells except email (hidden by CSS)
          const cells = row.querySelectorAll('td');
          cells.forEach(cell => {
            if (!cell.classList.contains('email-column')) {
              cell.style.display = '';
            }
          });
        }

        // Always stack name and email in name cell
        if (!nameCell.classList.contains('mobile-processed') && emailCell) {
          const nameText = nameCell.textContent.trim();
          const emailText = emailCell.textContent.trim();
          nameCell.innerHTML = `<div class="mobile-name">${nameText}</div><div class="mobile-email">${emailText}</div>`;
          nameCell.dataset.originalName = nameText;
          nameCell.classList.add('mobile-processed');
          nameCell.style.cursor = 'pointer';
          nameCell.title = 'Click to view details';

          // Add click handler
          nameCell.addEventListener('click', () => showDetailsModal(row, table));
        }
      });
    });
  }

  function showDetailsModal(row, table) {
    const cells = row.querySelectorAll('td');
    const headers = table.querySelectorAll('thead th');

    let modalContent = '<div class="modal fade" id="detailsModal" tabindex="-1"><div class="modal-dialog modal-dialog-centered"><div class="modal-content"><div class="modal-header"><h5 class="modal-title">Details</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body">';

    headers.forEach((header, index) => {
      if (cells[index]) {
        if (header.textContent === 'Name') {
          modalContent += `<p><strong>Name:</strong> ${cells[index].dataset.originalName || cells[index].textContent}</p>`;
        } else {
          modalContent += `<p><strong>${header.textContent}:</strong> ${cells[index].innerHTML}</p>`;
        }
      }
    });

    modalContent += '</div></div></div></div>';

    // Remove existing modal if any
    const existing = document.getElementById('detailsModal');
    if (existing) existing.remove();

    document.body.insertAdjacentHTML('beforeend', modalContent);
    const modal = new bootstrap.Modal(document.getElementById('detailsModal'));
    modal.show();
  }

  // Call initMobileTables on load and resize
  document.addEventListener('DOMContentLoaded', initMobileTables);
  window.addEventListener('resize', () => {
    // Use RAF for resize
    if (window.resizeRAF) return;
    window.resizeRAF = requestAnimationFrame(() => {
      window.resizeRAF = null;
      initMobileTables();
    });
  });

})();
