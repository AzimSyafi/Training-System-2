/**
 * Table Pagination Script - Google-style pagination
 * Automatically paginates tables with 50 items per page
 */

class TablePagination {
    constructor(tableId, itemsPerPage = 50) {
        this.tableId = tableId;
        this.itemsPerPage = itemsPerPage;
        this.currentPage = 1;
        this.table = document.getElementById(tableId);

        if (!this.table) {
            console.warn(`Table with id "${tableId}" not found`);
            return;
        }

        this.tbody = this.table.querySelector('tbody');
        if (!this.tbody) {
            console.warn(`No tbody found in table "${tableId}"`);
            return;
        }

        this.rows = Array.from(this.tbody.querySelectorAll('tr'));
        this.totalPages = Math.ceil(this.rows.length / this.itemsPerPage);

       // ALWAYS inject controls when there are any rows so the page number (eg. "1") is visible
        if (this.rows.length > 0) {
            this.injectStyles();
            this.createPaginationControls();
            this.showPage(1);
        }
    }

    injectStyles() {
        // Check if styles already injected
        if (document.getElementById('pagination-custom-styles')) return;

        const style = document.createElement('style');
        style.id = 'pagination-custom-styles';
        style.textContent = `
            .table-pagination-controls {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1rem;
                padding: 0 0.75rem;
                flex-wrap: wrap;
                gap: 0.5rem;
            }
            
            .pagination-info {
                color: var(--text-secondary, #64748b);
                font-size: 0.875rem;
            }
            
            .pagination-nav {
                display: flex;
                align-items: center;
                gap: 0.25rem;
                list-style: none;
                padding: 0;
                margin: 0;
            }
            
            .pagination-link {
                color: var(--link-color, #1d4ed8);
                text-decoration: none;
                padding: 0.375rem 0.625rem;
                cursor: pointer;
                border-radius: 0.25rem;
                transition: all 0.15s ease;
                font-size: 0.875rem;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 32px;
                user-select: none;
            }
            
            .pagination-link:hover:not(.disabled):not(.active) {
                background-color: rgba(59, 130, 246, 0.1);
                color: var(--primary, #3b82f6);
            }
            
            .pagination-link.active {
                background-color: transparent;
                color: var(--primary, #3b82f6);
                font-weight: 700;
                pointer-events: none;
                border: 2px solid var(--primary, #3b82f6);
            }
            
            .pagination-link.disabled {
                color: var(--text-muted, #94a3b8);
                pointer-events: none;
                cursor: default;
                opacity: 0.5;
            }
            
            .pagination-link.ellipsis {
                pointer-events: none;
                cursor: default;
                color: var(--text-muted, #94a3b8);
            }
            
            .pagination-link i {
                font-size: 0.75rem;
            }
            
            /* Dark mode support */
            body.dark-mode .pagination-link,
            html.darkmode .pagination-link {
                color: var(--link-color, #60a5fa);
            }
            
            body.dark-mode .pagination-link:hover:not(.disabled):not(.active),
            html.darkmode .pagination-link:hover:not(.disabled):not(.active) {
                background-color: rgba(96, 165, 250, 0.15);
                color: #93c5fd;
            }
            
            body.dark-mode .pagination-link.active,
            html.darkmode .pagination-link.active {
                background-color: transparent;
                color: var(--text-color, #f1f5f9);
                font-weight: 700;
                border: 2px solid var(--primary, #60a5fa);
            }
            
            @media (max-width: 576px) {
                .table-pagination-controls {
                    font-size: 0.75rem;
                    padding: 0 0.5rem;
                }
                
                .pagination-link {
                    padding: 0.25rem 0.5rem;
                    min-width: 28px;
                    font-size: 0.75rem;
                }
            }
        `;
        document.head.appendChild(style);
    }

    createPaginationControls() {
        // Create pagination container
        const paginationDiv = document.createElement('div');
        paginationDiv.id = `pagination-${this.tableId}`;
        paginationDiv.className = 'table-pagination-controls';
        paginationDiv.innerHTML = `
            <div class="pagination-info">
                Showing <span class="fw-bold" id="start-${this.tableId}">1</span>–<span class="fw-bold" id="end-${this.tableId}">0</span> of <span class="fw-bold" id="total-${this.tableId}">${this.rows.length}</span>
            </div>
            <nav aria-label="Table pagination">
                <ul class="pagination-nav" id="pagination-list-${this.tableId}">
                    <!-- Pagination buttons will be inserted here -->
                </ul>
            </nav>
        `;

        // Insert BEFORE the table's parent container
        const tableParent = this.table.closest('.table-responsive') || this.table.parentElement;
        tableParent.insertAdjacentElement('beforebegin', paginationDiv);

        this.paginationList = document.getElementById(`pagination-list-${this.tableId}`);
        this.updatePaginationButtons();
    }

    updatePaginationButtons() {
        if (!this.paginationList) return;

        this.paginationList.innerHTML = '';

        // Previous button
        const prevLi = document.createElement('li');
        const prevLink = document.createElement('a');
        prevLink.className = `pagination-link ${this.currentPage === 1 ? 'disabled' : ''}`;
        prevLink.href = '#';
        prevLink.innerHTML = '<i class="fas fa-chevron-left"></i>';
        prevLink.setAttribute('aria-label', 'Previous');
        prevLink.addEventListener('click', (e) => {
            e.preventDefault();
            if (this.currentPage > 1) this.showPage(this.currentPage - 1);
        });
        prevLi.appendChild(prevLink);
        this.paginationList.appendChild(prevLi);

        // Page numbers with ellipsis
        const pageNumbers = this.getPageNumbers();
        pageNumbers.forEach(pageNum => {
            const pageLi = document.createElement('li');
            const pageLink = document.createElement('a');

            if (pageNum === '...') {
                pageLink.className = 'pagination-link ellipsis';
                pageLink.textContent = '...';
            } else {
                pageLink.className = `pagination-link ${this.currentPage === pageNum ? 'active' : ''}`;
                pageLink.href = '#';
                pageLink.textContent = pageNum;
                pageLink.setAttribute('aria-label', `Page ${pageNum}`);
                if (this.currentPage === pageNum) {
                    pageLink.setAttribute('aria-current', 'page');
                }
                pageLink.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.showPage(pageNum);
                });
            }

            pageLi.appendChild(pageLink);
            this.paginationList.appendChild(pageLi);
        });

        // Next button
        const nextLi = document.createElement('li');
        const nextLink = document.createElement('a');
        nextLink.className = `pagination-link ${this.currentPage === this.totalPages || this.totalPages === 0 ? 'disabled' : ''}`;
        nextLink.href = '#';
        nextLink.innerHTML = '<i class="fas fa-chevron-right"></i>';
        nextLink.setAttribute('aria-label', 'Next');
        nextLink.addEventListener('click', (e) => {
            e.preventDefault();
            if (this.currentPage < this.totalPages) this.showPage(this.currentPage + 1);
        });
        nextLi.appendChild(nextLink);
        this.paginationList.appendChild(nextLi);
    }

    getPageNumbers() {
        const pages = [];
        const maxVisible = 7; // Maximum page buttons to show

        if (this.totalPages <= maxVisible) {
            // Show all pages if total is small
            for (let i = 1; i <= this.totalPages; i++) {
                pages.push(i);
            }
            // If there are zero pages (no rows), still show a single page '1' for consistency
            if (this.totalPages === 0) pages.push(1);
        } else {
            // Always show first page
            pages.push(1);

            if (this.currentPage > 3) {
                pages.push('...');
            }

            // Show pages around current page
            let startPage = Math.max(2, this.currentPage - 1);
            let endPage = Math.min(this.totalPages - 1, this.currentPage + 1);

            for (let i = startPage; i <= endPage; i++) {
                pages.push(i);
            }

            if (this.currentPage < this.totalPages - 2) {
                pages.push('...');
            }

            // Always show last page
            pages.push(this.totalPages);
        }

        return pages;
    }

    showPage(pageNum) {
        // Guard pageNum bounds
        if (this.totalPages === 0) {
            this.currentPage = 1;
        } else {
            this.currentPage = Math.min(Math.max(1, pageNum), Math.max(1, this.totalPages));
        }

        const startIndex = (this.currentPage - 1) * this.itemsPerPage;
        const endIndex = startIndex + this.itemsPerPage;

        // Hide all rows
        this.rows.forEach(row => {
            row.style.display = 'none';
        });

        // Show rows for current page (or all if only one page)
        if (this.totalPages <= 1) {
            // If only one page, show all rows
            this.rows.forEach(row => row.style.display = '');
        } else {
            for (let i = startIndex; i < endIndex && i < this.rows.length; i++) {
                this.rows[i].style.display = '';
            }
        }

        // Update pagination info
        const start = this.rows.length === 0 ? 0 : (this.totalPages <= 1 ? 1 : (startIndex + 1));
        const end = this.rows.length === 0 ? 0 : (this.totalPages <= 1 ? this.rows.length : Math.min(endIndex, this.rows.length));

        const startEl = document.getElementById(`start-${this.tableId}`);
        const endEl = document.getElementById(`end-${this.tableId}`);
        const totalEl = document.getElementById(`total-${this.tableId}`);

        if (startEl) startEl.textContent = start;
        if (endEl) endEl.textContent = end;
        if (totalEl) totalEl.textContent = this.rows.length;

        // Update pagination buttons
        this.updatePaginationButtons();

        // Ensure pagination controls are visible
        const paginationDiv = document.getElementById(`pagination-${this.tableId}`);
        if (paginationDiv) paginationDiv.style.display = '';

        // Scroll to table top for multi-page navigation
        if (this.totalPages > 1) {
            this.table.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    // Method to refresh pagination (useful after filtering/searching)
    refresh() {
        // Recompute rows and totalPages based on current DOM
        this.rows = Array.from(this.tbody.querySelectorAll('tr'));
        this.totalPages = Math.ceil(this.rows.length / this.itemsPerPage);
        this.currentPage = 1;

        // Update total count
        const totalEl = document.getElementById(`total-${this.tableId}`);
        if (totalEl) totalEl.textContent = this.rows.length;

        // Always show pagination controls (even for single page), and update display
        if (this.rows.length > 0) {
            // Rebuild buttons and show first page
            this.updatePaginationButtons();
            this.showPage(1);
        } else {
            // No rows: update info and keep controls visible with zeros
            const startEl = document.getElementById(`start-${this.tableId}`);
            const endEl = document.getElementById(`end-${this.tableId}`);
            const totalEl2 = document.getElementById(`total-${this.tableId}`);
            if (startEl) startEl.textContent = 0;
            if (endEl) endEl.textContent = 0;
            if (totalEl2) totalEl2.textContent = 0;
            const paginationDiv = document.getElementById(`pagination-${this.tableId}`);
            if (paginationDiv) paginationDiv.style.display = '';
            if (this.paginationList) this.paginationList.innerHTML = '<li><a class="pagination-link active">1</a></li>';
        }
    }
}

// Auto-initialize pagination for tables with data-paginate attribute
document.addEventListener('DOMContentLoaded', function() {
    const paginateTables = document.querySelectorAll('[data-paginate="true"]');

    paginateTables.forEach(table => {
        const itemsPerPage = parseInt(table.getAttribute('data-items-per-page')) || 50;
        new TablePagination(table.id, itemsPerPage);
    });
});
