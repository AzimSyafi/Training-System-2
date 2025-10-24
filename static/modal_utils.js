/**
 * Modal Utilities - Custom modal dialogs for confirmations and alerts
 * Replaces native confirm() and alert() with Bootstrap modals
 */

class ModalUtils {
    constructor() {
        this.injectStyles();
        this.createModalContainer();
    }

    injectStyles() {
        if (document.getElementById('modal-utils-styles')) return;

        const style = document.createElement('style');
        style.id = 'modal-utils-styles';
        style.textContent = `
            .custom-modal-backdrop {
                background-color: rgba(0, 0, 0, 0.5);
                backdrop-filter: blur(2px);
            }
            
            .custom-modal .modal-content {
                border-radius: 0.5rem;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
            }
            
            .custom-modal .modal-header {
                border-bottom: 1px solid #dee2e6;
                padding: 1rem 1.5rem;
            }
            
            .custom-modal .modal-body {
                padding: 1.5rem;
                font-size: 0.95rem;
            }
            
            .custom-modal .modal-footer {
                border-top: 1px solid #dee2e6;
                padding: 1rem 1.5rem;
            }
            
            .modal-icon {
                width: 48px;
                height: 48px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 1rem;
                font-size: 1.5rem;
            }
            
            .modal-icon.warning {
                background-color: #fff3cd;
                color: #856404;
            }
            
            .modal-icon.danger {
                background-color: #f8d7da;
                color: #721c24;
            }
            
            .modal-icon.success {
                background-color: #d4edda;
                color: #155724;
            }
            
            .modal-icon.info {
                background-color: #d1ecf1;
                color: #0c5460;
            }
            
            body.dark-mode .custom-modal .modal-content,
            html.darkmode .custom-modal .modal-content {
                background-color: #1e293b;
                color: #f1f5f9;
            }
            
            body.dark-mode .custom-modal .modal-header,
            html.darkmode .custom-modal .modal-header,
            body.dark-mode .custom-modal .modal-footer,
            html.darkmode .custom-modal .modal-footer {
                border-color: #334155;
            }
        `;
        document.head.appendChild(style);
    }

    createModalContainer() {
        if (document.getElementById('customModalContainer')) return;

        const modalContainer = document.createElement('div');
        modalContainer.id = 'customModalContainer';

        // Ensure document.body exists before appending
        if (document.body) {
            document.body.appendChild(modalContainer);
        } else {
            // If body doesn't exist yet, wait for DOM to be ready
            document.addEventListener('DOMContentLoaded', () => {
                if (!document.getElementById('customModalContainer')) {
                    document.body.appendChild(modalContainer);
                }
            });
        }
    }

    /**
     * Show a confirmation dialog
     * @param {string} message - The message to display
     * @param {string} title - The title of the modal (default: "Confirm Action")
     * @param {object} options - Additional options (confirmText, cancelText, type)
     * @returns {Promise<boolean>} - Resolves to true if confirmed, false if cancelled
     */
    confirm(message, title = 'Confirm Action', options = {}) {
        return new Promise((resolve) => {
            const modalId = 'confirmModal_' + Date.now();
            const {
                confirmText = 'Confirm',
                cancelText = 'Cancel',
                type = 'warning',
                confirmClass = 'btn-primary',
                cancelClass = 'btn-secondary'
            } = options;

            const iconMap = {
                warning: 'fa-exclamation-triangle',
                danger: 'fa-exclamation-circle',
                info: 'fa-info-circle',
                success: 'fa-check-circle'
            };

            const modalHTML = `
                <div class="modal fade custom-modal" id="${modalId}" tabindex="-1" data-bs-backdrop="static" data-bs-keyboard="false">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">${this.escapeHtml(title)}</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body text-center">
                                <div class="modal-icon ${type}">
                                    <i class="fas ${iconMap[type] || iconMap.warning}"></i>
                                </div>
                                <p class="mb-0">${this.escapeHtml(message)}</p>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn ${cancelClass}" data-bs-dismiss="modal">${this.escapeHtml(cancelText)}</button>
                                <button type="button" class="btn ${confirmClass}" id="${modalId}_confirm">${this.escapeHtml(confirmText)}</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            const container = document.getElementById('customModalContainer');
            container.insertAdjacentHTML('beforeend', modalHTML);

            const modalElement = document.getElementById(modalId);
            const modal = new bootstrap.Modal(modalElement);

            const confirmBtn = document.getElementById(`${modalId}_confirm`);

            confirmBtn.addEventListener('click', () => {
                modal.hide();
                resolve(true);
            });

            modalElement.addEventListener('hidden.bs.modal', () => {
                modalElement.remove();
                resolve(false);
            });

            modal.show();
        });
    }

    /**
     * Show an alert dialog
     * @param {string} message - The message to display
     * @param {string} title - The title of the modal (default: "Notice")
     * @param {object} options - Additional options (type, buttonText)
     * @returns {Promise<void>}
     */
    alert(message, title = 'Notice', options = {}) {
        return new Promise((resolve) => {
            const modalId = 'alertModal_' + Date.now();
            const {
                type = 'info',
                buttonText = 'OK',
                buttonClass = 'btn-primary'
            } = options;

            const iconMap = {
                warning: 'fa-exclamation-triangle',
                danger: 'fa-times-circle',
                info: 'fa-info-circle',
                success: 'fa-check-circle'
            };

            const modalHTML = `
                <div class="modal fade custom-modal" id="${modalId}" tabindex="-1" data-bs-backdrop="static" data-bs-keyboard="false">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">${this.escapeHtml(title)}</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body text-center">
                                <div class="modal-icon ${type}">
                                    <i class="fas ${iconMap[type] || iconMap.info}"></i>
                                </div>
                                <p class="mb-0">${this.escapeHtml(message)}</p>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn ${buttonClass}" data-bs-dismiss="modal">${this.escapeHtml(buttonText)}</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            const container = document.getElementById('customModalContainer');
            container.insertAdjacentHTML('beforeend', modalHTML);

            const modalElement = document.getElementById(modalId);
            const modal = new bootstrap.Modal(modalElement);

            modalElement.addEventListener('hidden.bs.modal', () => {
                modalElement.remove();
                resolve();
            });

            modal.show();
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Create global instance after DOM is ready
let modalUtils;

function initModalUtils() {
    if (!modalUtils) {
        modalUtils = new ModalUtils();
    }
    return modalUtils;
}

// Initialize immediately if DOM is ready, otherwise wait
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initModalUtils);
} else {
    initModalUtils();
}

// Create global wrapper functions for easy use
window.customConfirm = (message, title, options) => {
    if (!modalUtils) initModalUtils();
    return modalUtils.confirm(message, title, options);
};
window.customAlert = (message, title, options) => {
    if (!modalUtils) initModalUtils();
    return modalUtils.alert(message, title, options);
};

