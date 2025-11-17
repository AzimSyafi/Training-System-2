/**
 * Responsive Table System
 * Transforms desktop tables into mobile-friendly cards on screens ≤768px
 * Integrates with existing TablePagination system
 */

class ResponsiveTable {
  constructor(tableElement) {
    this.table = tableElement;
    this.wrapper = this.createWrapper();
    this.mobileContainer = this.createMobileContainer();
    this.isMobile = false;
    
    // Get column labels from headers
    this.columnLabels = this.extractColumnLabels();
    
    // Get primary columns (for card display)
    this.primaryColumns = this.getPrimaryColumns();
    
    // Initialize
    this.checkViewport();
    this.attachResizeListener();
    
    // Listen for pagination changes to update cards
    this.observeTableChanges();
  }
  
  createWrapper() {
    // Wrap table in responsive wrapper if not already wrapped
    if (!this.table.closest('.responsive-table-wrapper')) {
      const wrapper = document.createElement('div');
      wrapper.className = 'responsive-table-wrapper';
      this.table.parentNode.insertBefore(wrapper, this.table);
      wrapper.appendChild(this.table);
      return wrapper;
    }
    return this.table.closest('.responsive-table-wrapper');
  }
  
  createMobileContainer() {
    // Create container for mobile cards
    const container = document.createElement('div');
    container.className = 'mobile-table-cards';
    container.style.display = 'none';
    this.wrapper.appendChild(container);
    return container;
  }
  
  extractColumnLabels() {
    // Get labels from th elements or data-label attributes
    const headers = this.table.querySelectorAll('thead th');
    return Array.from(headers).map(th => {
      return th.getAttribute('data-label') || th.textContent.trim();
    });
  }
  
  getPrimaryColumns() {
    // Get which columns should be shown in card preview
    const headers = this.table.querySelectorAll('thead th');
    const primary = [];
    
    headers.forEach((th, index) => {
      const isPrimary = th.getAttribute('data-primary') === 'true';
      const isSecondary = th.getAttribute('data-secondary') === 'true';
      
      if (isPrimary) {
        primary.push({ index, type: 'primary', label: this.columnLabels[index] });
      } else if (isSecondary) {
        primary.push({ index, type: 'secondary', label: this.columnLabels[index] });
      }
    });
    
    // If no columns marked, use first 2 columns as primary/secondary
    if (primary.length === 0) {
      if (this.columnLabels.length > 0) {
        primary.push({ index: 0, type: 'primary', label: this.columnLabels[0] });
      }
      if (this.columnLabels.length > 1) {
        primary.push({ index: 1, type: 'secondary', label: this.columnLabels[1] });
      }
    }
    
    return primary;
  }
  
  checkViewport() {
    const wasMobile = this.isMobile;
    this.isMobile = window.innerWidth <= 768;
    
    if (this.isMobile !== wasMobile) {
      if (this.isMobile) {
        this.switchToMobile();
      } else {
        this.switchToDesktop();
      }
    }
  }
  
  switchToMobile() {
    this.table.style.display = 'none';
    this.mobileContainer.style.display = 'block';
    this.renderMobileCards();
  }
  
  switchToDesktop() {
    this.table.style.display = '';
    this.mobileContainer.style.display = 'none';
  }
  
  renderMobileCards() {
    // Clear existing cards
    this.mobileContainer.innerHTML = '';
    
    // Get all visible rows (pagination might hide some)
    const rows = Array.from(this.table.querySelectorAll('tbody tr'))
      .filter(row => row.style.display !== 'none');
    
    if (rows.length === 0) {
      this.mobileContainer.innerHTML = '<div class="text-center text-muted py-4"><p>No data available</p></div>';
      return;
    }
    
    // Create a card for each visible row
    rows.forEach((row, index) => {
      const card = this.createCardFromRow(row, index);
      this.mobileContainer.appendChild(card);
    });
  }
  
  createCardFromRow(row, rowIndex) {
    const card = document.createElement('div');
    card.className = 'mobile-table-card';
    
    const cells = row.querySelectorAll('td');
    
    // Build card content
    let cardHTML = '';
    
    // Add primary/secondary columns prominently
    this.primaryColumns.forEach(col => {
      if (cells[col.index]) {
        const content = cells[col.index].innerHTML;
        const className = col.type === 'primary' ? 'mobile-card-primary' : 'mobile-card-secondary';
        cardHTML += `<div class="${className}">${content}</div>`;
      }
    });
    
    card.innerHTML = cardHTML;
    
    // Store row data for detail modal
    card.setAttribute('data-row-index', rowIndex);
    card.setAttribute('data-row-id', row.getAttribute('data-id') || '');
    
    // ALWAYS make cards clickable - show detail modal with all data
    card.style.cursor = 'pointer';
    card.addEventListener('click', (e) => {
      // Don't trigger if clicking on an interactive element
      if (!e.target.closest('a, button, .badge, input, select')) {
        this.showDetailModal(row, cells);
      }
    });
    
    return card;
  }
  
  showDetailModal(row, cells) {
    // Create or get detail modal
    let modal = document.getElementById('mobile-table-detail-modal');
    
    if (!modal) {
      modal = this.createDetailModal();
      document.body.appendChild(modal);
    }
    
    // Build modal content with all row data
    let content = '<div class="list-group list-group-flush">';
    
    cells.forEach((cell, index) => {
      if (this.columnLabels[index]) {
        const label = this.columnLabels[index];
        const value = cell.innerHTML;
        
        content += `
          <div class="list-group-item px-3 py-2">
            <div class="d-flex justify-content-between align-items-start">
              <div>
                <small class="text-muted d-block mb-1">${label}</small>
                <div>${value}</div>
              </div>
            </div>
          </div>
        `;
      }
    });
    
    content += '</div>';
    
    // Update modal content
    const modalBody = modal.querySelector('.modal-body');
    if (modalBody) {
      modalBody.innerHTML = content;
    }
    
    // Show modal
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
  }
  
  createDetailModal() {
    const modal = document.createElement('div');
    modal.id = 'mobile-table-detail-modal';
    modal.className = 'modal fade';
    modal.setAttribute('tabindex', '-1');
    modal.setAttribute('aria-labelledby', 'mobileTableDetailLabel');
    modal.setAttribute('aria-hidden', 'true');
    
    modal.innerHTML = `
      <div class="modal-dialog modal-dialog-scrollable modal-mobile-fullscreen">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title" id="mobileTableDetailLabel">
              <i class="fas fa-info-circle"></i> Details
            </h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body">
            <!-- Content will be inserted here -->
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
          </div>
        </div>
      </div>
    `;
    
    return modal;
  }
  
  attachResizeListener() {
    let resizeTimeout;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(() => {
        this.checkViewport();
      }, 150);
    });
  }
  
  observeTableChanges() {
    // Watch for changes to tbody (pagination, filtering, etc.)
    const tbody = this.table.querySelector('tbody');
    if (!tbody) return;
    
    const observer = new MutationObserver(() => {
      if (this.isMobile) {
        this.renderMobileCards();
      }
    });
    
    observer.observe(tbody, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['style']
    });
    
    // Also watch for pagination changes
    const paginationContainer = document.querySelector(`#pagination-${this.table.id}`);
    if (paginationContainer) {
      const paginationObserver = new MutationObserver(() => {
        if (this.isMobile) {
          // Small delay to let pagination finish
          setTimeout(() => this.renderMobileCards(), 50);
        }
      });
      
      paginationObserver.observe(paginationContainer, {
        childList: true,
        subtree: true
      });
    }
  }
  
  // Public method to refresh cards (call after data changes)
  refresh() {
    if (this.isMobile) {
      this.renderMobileCards();
    }
  }
}

// Auto-initialize all tables with data-responsive-table attribute
document.addEventListener('DOMContentLoaded', function() {
  const tables = document.querySelectorAll('table[data-responsive-table="true"]');
  
  tables.forEach(table => {
    if (table.id) {
      new ResponsiveTable(table);
    } else {
      console.warn('Responsive table requires an ID attribute:', table);
    }
  });
});
