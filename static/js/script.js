/* ================================
   COLLEGE TIMETABLE SYSTEM - COMMON SCRIPTS
   ================================ */

// ================================
// GLOBAL UTILITIES
// ================================

const App = {
    // Initialize all common functionality
    init() {
        this.setupMobileMenu();
        this.setupModals();
        this.setupTabs();
        this.setupCheckboxes();
        this.setupFormValidation();
        this.setupSearchDebounce();
        this.setupTimeDisplay();
        this.setupAlertDismiss();
        this.setupTooltips();
        this.setupTableSorting();
        this.setupDropdowns();
        this.setupLoadingStates();
    },

    // Mobile menu toggle - Updated for consistent behavior
    setupMobileMenu() {
        const menuBtn = document.getElementById('menu-btn') || document.getElementById('sidebar-toggle');
        const sidebar = document.querySelector('.sidebar') || document.getElementById('sidebar');
        const overlay = document.getElementById('overlay');

        if (!menuBtn || !sidebar) return;

        menuBtn.addEventListener('click', () => {
            if (window.innerWidth < 768) {
                // Mobile behavior
                sidebar.classList.toggle('-translate-x-full');
                if (overlay) overlay.classList.toggle('hidden');
            } else {
                // Desktop behavior - handled by individual layout scripts
                // This prevents conflicts with admin layout's custom toggle
                return;
            }
        });

        if (overlay) {
            overlay.addEventListener('click', () => {
                sidebar.classList.add('-translate-x-full');
                overlay.classList.add('hidden');
            });
        }

        // Handle window resize
        window.addEventListener('resize', () => {
            if (window.innerWidth >= 768) {
                sidebar.classList.remove('-translate-x-full');
                if (overlay) overlay.classList.add('hidden');
            }
        });
    },

    // Modal management
    setupModals() {
        const modals = document.querySelectorAll('.modal');
        
        modals.forEach(modal => {
            const closeBtn = modal.querySelector('.close-modal-btn, .cancel-btn');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => this.hideModal(modal));
            }

            // Close on backdrop click
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.hideModal(modal);
                }
            });
        });

        // Escape key to close modal
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const openModal = document.querySelector('.modal.flex');
                if (openModal) this.hideModal(openModal);
            }
        });
    },

    showModal(modal) {
        if (!modal) return;
        modal.classList.remove('hidden');
        modal.classList.add('flex');
        document.body.style.overflow = 'hidden';
    },

    hideModal(modal) {
        if (!modal) return;
        modal.classList.add('hidden');
        modal.classList.remove('flex');
        document.body.style.overflow = 'auto';
    },

    // Tab switching
    setupTabs() {
        const tabs = document.querySelectorAll('.tab');
        const panels = document.querySelectorAll('.tab-panel');

        tabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
                e.preventDefault();
                
                // Remove active class from all tabs
                tabs.forEach(t => {
                    t.classList.remove('border-indigo-500', 'text-indigo-600', 'active');
                    t.classList.add('border-transparent', 'text-gray-500');
                });
                
                // Add active class to clicked tab
                tab.classList.remove('border-transparent', 'text-gray-500');
                tab.classList.add('border-indigo-500', 'text-indigo-600', 'active');
                
                // Hide all panels
                panels.forEach(p => p.classList.add('hidden'));
                
                // Show target panel
                const targetId = tab.dataset.target;
                const targetPanel = document.getElementById(targetId);
                if (targetPanel) {
                    targetPanel.classList.remove('hidden');
                }
            });
        });
    },

    // Checkbox functionality
    setupCheckboxes() {
        const selectAllCheckbox = document.getElementById('select-all-checkbox');
        const rowCheckboxes = document.querySelectorAll('.row-checkbox');

        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', (e) => {
                rowCheckboxes.forEach(checkbox => {
                    checkbox.checked = e.target.checked;
                });
                this.updateBulkActionButtons();
            });
        }

        rowCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                this.updateSelectAllState();
                this.updateBulkActionButtons();
            });
        });
    },

    updateSelectAllState() {
        const selectAllCheckbox = document.getElementById('select-all-checkbox');
        const rowCheckboxes = document.querySelectorAll('.row-checkbox');
        
        if (!selectAllCheckbox || rowCheckboxes.length === 0) return;

        const allChecked = Array.from(rowCheckboxes).every(cb => cb.checked);
        const someChecked = Array.from(rowCheckboxes).some(cb => cb.checked);

        selectAllCheckbox.checked = allChecked;
        selectAllCheckbox.indeterminate = someChecked && !allChecked;
    },

    updateBulkActionButtons() {
        const checkedCount = document.querySelectorAll('.row-checkbox:checked').length;
        const bulkActions = document.querySelectorAll('.bulk-action-btn');
        
        bulkActions.forEach(btn => {
            if (checkedCount > 0) {
                btn.classList.remove('opacity-50', 'cursor-not-allowed');
                btn.disabled = false;
            } else {
                btn.classList.add('opacity-50', 'cursor-not-allowed');
                btn.disabled = true;
            }
        });
    },

    // Form validation
    setupFormValidation() {
        const forms = document.querySelectorAll('form[data-validate]');
        
        forms.forEach(form => {
            form.addEventListener('submit', (e) => {
                if (!this.validateForm(form)) {
                    e.preventDefault();
                }
            });
        });
    },

    validateForm(form) {
        let isValid = true;
        const inputs = form.querySelectorAll('input[required], select[required], textarea[required]');
        
        inputs.forEach(input => {
            if (!input.value.trim()) {
                isValid = false;
                this.showFieldError(input, 'This field is required');
            } else {
                this.clearFieldError(input);
            }
        });

        return isValid;
    },

    showFieldError(input, message) {
        input.classList.add('border-red-500');
        let errorEl = input.parentElement.querySelector('.field-error');
        
        if (!errorEl) {
            errorEl = document.createElement('p');
            errorEl.className = 'field-error text-red-500 text-xs mt-1';
            input.parentElement.appendChild(errorEl);
        }
        
        errorEl.textContent = message;
    },

    clearFieldError(input) {
        input.classList.remove('border-red-500');
        const errorEl = input.parentElement.querySelector('.field-error');
        if (errorEl) errorEl.remove();
    },

    // Search with debounce
    setupSearchDebounce() {
        const searchInputs = document.querySelectorAll('input[type="search"], input[name="search"]');
        
        searchInputs.forEach(input => {
            let timeout;
            input.addEventListener('input', (e) => {
                clearTimeout(timeout);
                timeout = setTimeout(() => {
                    // Submit parent form
                    const form = input.closest('form');
                    if (form && form.dataset.autoSubmit) {
                        form.submit();
                    }
                }, 500);
            });
        });
    },

    // Time display
    setupTimeDisplay() {
        const updateTime = () => {
            const timeEl = document.getElementById('current-time');
            if (!timeEl) return;
            
            const now = new Date();
            const timeStr = now.toLocaleTimeString('en-US', { 
                hour: '2-digit', 
                minute: '2-digit'
            });
            timeEl.textContent = timeStr;
        };

        updateTime();
        setInterval(updateTime, 60000); // Update every minute
    },

    // Alert dismiss
    setupAlertDismiss() {
        const alerts = document.querySelectorAll('.alert');
        
        alerts.forEach(alert => {
            // Auto dismiss after 5 seconds
            setTimeout(() => {
                alert.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => alert.remove(), 300);
            }, 5000);
        });
    },

    // Tooltips
    setupTooltips() {
        const tooltipElements = document.querySelectorAll('[data-tooltip]');
        
        tooltipElements.forEach(el => {
            el.classList.add('tooltip');
        });
    },

    // Table sorting
    setupTableSorting() {
        const sortableHeaders = document.querySelectorAll('th[data-sortable]');
        
        sortableHeaders.forEach(header => {
            header.style.cursor = 'pointer';
            header.addEventListener('click', () => {
                const table = header.closest('table');
                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                const columnIndex = Array.from(header.parentElement.children).indexOf(header);
                const currentOrder = header.dataset.order || 'asc';
                const newOrder = currentOrder === 'asc' ? 'desc' : 'asc';
                
                rows.sort((a, b) => {
                    const aVal = a.children[columnIndex].textContent.trim();
                    const bVal = b.children[columnIndex].textContent.trim();
                    
                    if (newOrder === 'asc') {
                        return aVal.localeCompare(bVal, undefined, { numeric: true });
                    } else {
                        return bVal.localeCompare(aVal, undefined, { numeric: true });
                    }
                });
                
                rows.forEach(row => tbody.appendChild(row));
                header.dataset.order = newOrder;
                
                // Update sort icon
                sortableHeaders.forEach(h => {
                    h.querySelector('.sort-icon')?.remove();
                });
                
                const icon = document.createElement('i');
                icon.className = `fas fa-sort-${newOrder === 'asc' ? 'up' : 'down'} ml-2 sort-icon`;
                header.appendChild(icon);
            });
        });
    },

    // Dropdown menus
    setupDropdowns() {
        const dropdownToggles = document.querySelectorAll('[data-dropdown-toggle]');
        
        dropdownToggles.forEach(toggle => {
            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                const targetId = toggle.dataset.dropdownToggle;
                const menu = document.getElementById(targetId);
                
                if (menu) {
                    menu.classList.toggle('show');
                    menu.classList.toggle('hidden');
                }
            });
        });

        // Close dropdowns when clicking outside
        document.addEventListener('click', () => {
            document.querySelectorAll('.dropdown-menu.show').forEach(menu => {
                menu.classList.remove('show');
                menu.classList.add('hidden');
            });
        });
    },

    // Loading states
    setupLoadingStates() {
        const forms = document.querySelectorAll('form[data-loading]');
        
        forms.forEach(form => {
            form.addEventListener('submit', (e) => {
                const submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Processing...';
                }
            });
        });
    }
};

// ================================
// API HELPERS
// ================================

const API = {
    async get(url) {
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error('Network response was not ok');
            return await response.json();
        } catch (error) {
            console.error('GET request failed:', error);
            this.showError('Failed to fetch data');
            throw error;
        }
    },

    async post(url, data) {
        try {
            const csrfInput = document.querySelector('input[name="csrf_token"]');
            const csrfTokenFromInput = csrfInput ? csrfInput.value : '';
            const csrfTokenFromCookie = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || '';
            const csrfToken = csrfTokenFromInput || csrfTokenFromCookie;

            const response = await fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(data)
            });

            const contentType = response.headers.get('content-type') || '';
            const isJson = contentType.includes('application/json');
            const payload = isJson ? await response.json() : await response.text();

            if (!response.ok) {
                const details = isJson
                    ? (payload && (payload.error || payload.message)) || 'Request failed'
                    : String(payload || '').slice(0, 180);
                throw new Error(`HTTP ${response.status}: ${details}`);
            }

            if (!isJson) {
                throw new Error('Expected JSON response but received HTML/text response');
            }

            return payload;
        } catch (error) {
            console.error('POST request failed:', error);
            this.showError('Failed to submit data');
            throw error;
        }
    },

    showError(message) {
        // Show error notification
        const alert = document.createElement('div');
        alert.className = 'alert fixed top-4 right-4 bg-red-50 text-red-800 px-6 py-4 rounded-lg shadow-lg z-50';
        alert.innerHTML = `
            <div class="flex items-center">
                <i class="fas fa-exclamation-circle mr-3"></i>
                <span>${message}</span>
            </div>
        `;
        document.body.appendChild(alert);
        
        setTimeout(() => alert.remove(), 3000);
    },

    showSuccess(message) {
        // Show success notification
        const alert = document.createElement('div');
        alert.className = 'alert fixed top-4 right-4 bg-green-50 text-green-800 px-6 py-4 rounded-lg shadow-lg z-50';
        alert.innerHTML = `
            <div class="flex items-center">
                <i class="fas fa-check-circle mr-3"></i>
                <span>${message}</span>
            </div>
        `;
        document.body.appendChild(alert);
        
        setTimeout(() => alert.remove(), 3000);
    }
};

// ================================
// FORM HANDLERS
// ================================

const FormHandlers = {
    // Handle add/edit modal forms
    setupModalForm(modalId, getUrl, addUrl, updateUrl) {
        const modal = document.getElementById(modalId);
        if (!modal) return;

        const form = modal.querySelector('form');
        const modalTitle = modal.querySelector('.modal-title');
        const addBtns = document.querySelectorAll(`[data-modal-target="${modalId.replace('-modal', '')}"]`);
        const editBtns = document.querySelectorAll('.edit-btn');

        // Handle add button
        addBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                modalTitle.textContent = `Add New ${this.capitalize(modalId.replace('-modal', ''))}`;
                form.action = addUrl;
                form.reset();
                App.showModal(modal);
            });
        });

        // Handle edit buttons
        editBtns.forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.dataset.id;
                const type = btn.dataset.type;
                
                try {
                    const data = await API.get(getUrl.replace(':id', id));
                    modalTitle.textContent = `Edit ${this.capitalize(type)}`;
                    form.action = updateUrl.replace(':id', id);
                    
                    // Populate form fields
                    Object.keys(data).forEach(key => {
                        const input = form.querySelector(`[name="${key}"]`);
                        if (input) input.value = data[key];
                    });
                    
                    App.showModal(modal);
                } catch (error) {
                    console.error('Failed to fetch data for editing:', error);
                }
            });
        });
    },

    capitalize(str) {
        return str.charAt(0).toUpperCase() + str.slice(1);
    },

    // Handle bulk delete confirmation
    confirmBulkDelete(message = 'Are you sure you want to delete selected items?') {
        const checkedCount = document.querySelectorAll('.row-checkbox:checked').length;
        if (checkedCount === 0) {
            API.showError('Please select at least one item to delete');
            return false;
        }
        return confirm(`${message}\n\nYou have selected ${checkedCount} item(s).`);
    }
};

// ================================
// DYNAMIC CASCADING DROPDOWNS
// ================================

const CascadingDropdowns = {
    // Setup course -> class -> division cascading
    setupCourseClassDivision() {
        const courseSelect = document.getElementById('course');
        const classSelect = document.getElementById('class');
        const divisionSelect = document.getElementById('division');

        if (!courseSelect || !classSelect || !divisionSelect) return;

        courseSelect.addEventListener('change', async () => {
            const courseId = courseSelect.value;
            classSelect.innerHTML = '<option disabled selected>Loading classes...</option>';
            divisionSelect.innerHTML = '<option disabled selected>Select a division</option>';
            
            try {
                const data = await API.get(`/admin/api/classes?course_id=${courseId}`);
                classSelect.innerHTML = '<option disabled selected>Select a class</option>';
                data.forEach(cls => {
                    const opt = document.createElement('option');
                    opt.value = cls.id;
                    opt.textContent = cls.name;
                    classSelect.appendChild(opt);
                });
            } catch (error) {
                classSelect.innerHTML = '<option disabled selected>Select a class</option>';
                console.error('Failed to load classes:', error);
            }
        });

        classSelect.addEventListener('change', async () => {
            const classId = classSelect.value;
            divisionSelect.innerHTML = '<option disabled selected>Loading divisions...</option>';
            
            try {
                const data = await API.get(`/admin/api/divisions?class_id=${classId}`);
                divisionSelect.innerHTML = '<option disabled selected>Select a division</option>';
                data.forEach(div => {
                    const opt = document.createElement('option');
                    opt.value = div.id;
                    opt.textContent = div.name;
                    divisionSelect.appendChild(opt);
                });
            } catch (error) {
                divisionSelect.innerHTML = '<option disabled selected>Select a division</option>';
                console.error('Failed to load divisions:', error);
            }
        });
    },

    // Setup subject filtering by course
    setupSubjectByCourse() {
        const courseSelect = document.getElementById('course_filter');
        const subjectSelect = document.getElementById('subject_id');

        if (!courseSelect || !subjectSelect) return;

        courseSelect.addEventListener('change', async () => {
            const courseId = courseSelect.value;
            subjectSelect.innerHTML = '<option disabled selected>Loading subjects...</option>';
            
            try {
                const data = await API.get(`/admin/api/subjects?course_id=${courseId}`);
                subjectSelect.innerHTML = '<option disabled selected>Select a subject</option>';
                data.forEach(subject => {
                    const opt = document.createElement('option');
                    opt.value = subject.id;
                    opt.textContent = subject.name;
                    subjectSelect.appendChild(opt);
                });
            } catch (error) {
                subjectSelect.innerHTML = '<option disabled selected>Select a subject</option>';
                console.error('Failed to load subjects:', error);
            }
        });
    }
};

// ================================
// TIMETABLE PREVIEW
// ================================

const TimetablePreview = {
    setup() {
        const previewBtn = document.getElementById('previewBtn');
        const previewModal = document.getElementById('previewModal');
        const closePreview = document.getElementById('closePreview');
        const previewContent = document.getElementById('previewContent');

        if (!previewBtn || !previewModal) return;
        if (previewBtn.dataset.inlinePreview === 'true') return;

        previewBtn.addEventListener('click', async () => {
            const course = document.getElementById('course')?.value;
            const cls = document.getElementById('class')?.value;
            const division = document.getElementById('division')?.value;

            if (!course || !cls || !division) {
                API.showError('Please select course, class and division to preview.');
                return;
            }

            previewContent.innerHTML = '<div class="flex justify-center items-center py-8"><div class="spinner"></div></div>';
            App.showModal(previewModal);

            try {
                const data = await API.post('/admin/api/generate_preview', {
                    course,
                    class: cls,
                    division
                });

                this.renderPreview(data, previewContent);
            } catch (error) {
                previewContent.innerHTML = `
                    <div class="text-red-600 text-center py-8">
                        <i class="fas fa-exclamation-triangle text-4xl mb-3"></i>
                        <p>Failed to generate preview. Please try again.</p>
                    </div>
                `;
            }
        });

        if (closePreview) {
            closePreview.addEventListener('click', () => {
                App.hideModal(previewModal);
            });
        }
    },

    renderPreview(data, container) {
        if (!data.days || Object.keys(data.days).length === 0) {
            container.innerHTML = '<div class="text-center py-8 text-gray-500">No timetable data available.</div>';
            return;
        }

        let html = '<div class="space-y-6">';

        for (const [day, slots] of Object.entries(data.days)) {
            html += `
                <div class="border rounded-lg overflow-hidden">
                    <div class="bg-gradient-to-r from-blue-500 to-purple-600 text-white px-4 py-3">
                        <h4 class="font-bold text-lg">${day}</h4>
                    </div>
                    <div class="divide-y">
            `;

            slots.forEach(slot => {
                html += `
                    <div class="px-4 py-3 hover:bg-gray-50 transition-colors">
                        <div class="flex items-center justify-between">
                            <div class="flex-1">
                                <p class="font-semibold text-gray-800">${slot.subject_name}</p>
                                <p class="text-sm text-gray-600">
                                    <i class="fas fa-user-tie mr-1"></i>${slot.faculty_name}
                                </p>
                            </div>
                            <div class="text-right">
                                <p class="text-sm font-medium text-gray-700">
                                    <i class="fas fa-clock mr-1"></i>
                                    ${slot.start_time} - ${slot.end_time}
                                </p>
                            </div>
                        </div>
                    </div>
                `;
            });

            html += '</div></div>';
        }

        if (data.unassigned && data.unassigned.length > 0) {
            html += `
                <div class="border border-yellow-300 rounded-lg overflow-hidden bg-yellow-50">
                    <div class="bg-yellow-400 text-yellow-900 px-4 py-3">
                        <h4 class="font-bold flex items-center">
                            <i class="fas fa-exclamation-triangle mr-2"></i>
                            Unassigned Subjects
                        </h4>
                    </div>
                    <ul class="divide-y divide-yellow-200">
            `;

            data.unassigned.forEach(item => {
                html += `
                    <li class="px-4 py-2 text-sm text-yellow-900">
                        ${item.subject_name} 
                        ${item.faculty_name ? `(${item.faculty_name})` : '(No faculty assigned)'}
                    </li>
                `;
            });

            html += '</ul></div>';
        }

        html += '</div>';
        container.innerHTML = html;
    }
};

// ================================
// FILE UPLOAD HANDLER
// ================================

const FileUpload = {
    setup() {
        const uploadBtns = document.querySelectorAll('[data-upload-btn]');
        
        uploadBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const inputId = btn.dataset.uploadBtn;
                const input = document.getElementById(inputId);
                if (input) input.click();
            });
        });

        const fileInputs = document.querySelectorAll('input[type="file"]');
        
        fileInputs.forEach(input => {
            input.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (file) {
                    this.showFileName(input, file.name);
                    this.validateFile(file, input);
                }
            });
        });
    },

    showFileName(input, fileName) {
        const label = input.parentElement.querySelector('.file-name-label');
        if (label) {
            label.textContent = fileName;
        }
    },

    validateFile(file, input) {
        const uploadType = input.dataset.uploadType || 'spreadsheet';
        
        // Different rules depending on type
        let allowedTypes = [];
        let maxSize = 5 * 1024 * 1024;
        let errorMsg = '';

        if (uploadType === 'image') {
            allowedTypes = ['image/jpeg', 'image/png', 'image/jpg', 'image/gif'];
            maxSize = 2 * 1024 * 1024;
            errorMsg = 'Only JPG, PNG, or GIF images allowed (max 2MB)';
        } else if (uploadType === 'spreadsheet') {
            allowedTypes = [
                'application/vnd.ms-excel',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'text/csv'
            ];
            maxSize = 5 * 1024 * 1024;
            errorMsg = 'Only Excel or CSV files allowed (max 5MB)';
        }

        if (file.size > maxSize) {
            API.showError(`File size must be less than ${Math.round(maxSize / 1024 / 1024)}MB`);
            return false;
        }

        if (!allowedTypes.includes(file.type)) {
            API.showError(errorMsg);
            return false;
        }

        return true;
    }
};


// ================================
// DATA TABLE ENHANCEMENTS
// ================================

const DataTable = {
    setup() {
        this.addRowNumbers();
        this.addHoverEffects();
        this.setupQuickSearch();
    },

    addRowNumbers() {
        const tables = document.querySelectorAll('table[data-row-numbers]');
        
        tables.forEach(table => {
            const tbody = table.querySelector('tbody');
            const rows = tbody.querySelectorAll('tr');
            
            rows.forEach((row, index) => {
                const cell = document.createElement('td');
                cell.className = 'py-3 px-4 text-gray-500 font-medium';
                cell.textContent = index + 1;
                row.insertBefore(cell, row.firstChild);
            });
        });
    },

    addHoverEffects() {
        const rows = document.querySelectorAll('tbody tr');
        
        rows.forEach(row => {
            row.addEventListener('mouseenter', () => {
                row.style.transition = 'all 0.2s ease';
            });
        });
    },

    setupQuickSearch() {
        const searchInputs = document.querySelectorAll('[data-table-search]');
        
        searchInputs.forEach(input => {
            const tableId = input.dataset.tableSearch;
            const table = document.getElementById(tableId);
            
            if (!table) return;

            input.addEventListener('input', (e) => {
                const searchTerm = e.target.value.toLowerCase();
                const rows = table.querySelectorAll('tbody tr');
                
                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    row.style.display = text.includes(searchTerm) ? '' : 'none';
                });
            });
        });
    }
};

// ================================
// UTILITY FUNCTIONS
// ================================

const Utils = {
    // Format date
    formatDate(date, format = 'YYYY-MM-DD') {
        const d = new Date(date);
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        
        return format
            .replace('YYYY', year)
            .replace('MM', month)
            .replace('DD', day);
    },

    // Format time
    formatTime(time, format12hr = true) {
        const [hours, minutes] = time.split(':');
        const h = parseInt(hours);
        
        if (format12hr) {
            const period = h >= 12 ? 'PM' : 'AM';
            const hour12 = h % 12 || 12;
            return `${hour12}:${minutes} ${period}`;
        }
        
        return `${hours}:${minutes}`;
    },

    // Debounce function
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    // Copy to clipboard
    copyToClipboard(text) {
        navigator.clipboard.writeText(text).then(() => {
            API.showSuccess('Copied to clipboard!');
        }).catch(() => {
            API.showError('Failed to copy to clipboard');
        });
    },

    // Export table to CSV
    exportTableToCSV(tableId, filename = 'export.csv') {
        const table = document.getElementById(tableId);
        if (!table) return;

        let csv = [];
        const rows = table.querySelectorAll('tr');
        
        rows.forEach(row => {
            const cols = row.querySelectorAll('td, th');
            const rowData = Array.from(cols).map(col => {
                return '"' + col.textContent.trim().replace(/"/g, '""') + '"';
            });
            csv.push(rowData.join(','));
        });

        const csvContent = csv.join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        window.URL.revokeObjectURL(url);
    }
};

// ================================
// INITIALIZE ON DOM READY
// ================================

document.addEventListener('DOMContentLoaded', () => {
    // Initialize core app functionality
    App.init();
    
    // Initialize cascading dropdowns
    CascadingDropdowns.setupCourseClassDivision();
    CascadingDropdowns.setupSubjectByCourse();
    
    // Initialize timetable preview
    TimetablePreview.setup();
    
    // Initialize file upload
    FileUpload.setup();
    
    // Initialize data table enhancements
    DataTable.setup();
    
    console.log('✅ Timetable System initialized successfully');
});

// Export for use in other scripts
window.App = App;
window.API = API;
window.FormHandlers = FormHandlers;
window.CascadingDropdowns = CascadingDropdowns;
window.TimetablePreview = TimetablePreview;
window.FileUpload = FileUpload;
window.DataTable = DataTable;
window.Utils = Utils;