/**
 * Legislative Analysis Platform - Main JavaScript
 * Handles client-side interactions and enhancements
 */

// Initialize application when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

/**
 * Main application initialization
 */
function initializeApp() {
    // Initialize Feather icons
    if (typeof feather !== 'undefined') {
        feather.replace();
    }
    
    // Initialize tooltips
    initializeTooltips();
    
    // Initialize search enhancements
    initializeSearch();
    
    // Initialize form enhancements
    initializeFormEnhancements();
    
    // Initialize loading states
    initializeLoadingStates();
    
    // Initialize accessibility features
    initializeA11y();
    
    // Initialize auto-refresh for dynamic content
    initializeAutoRefresh();
}

/**
 * Initialize Bootstrap tooltips
 */
function initializeTooltips() {
    if (typeof bootstrap !== 'undefined') {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function(tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
}

/**
 * Enhanced search functionality
 */
function initializeSearch() {
    const searchForm = document.querySelector('form[action*="bill_search"]');
    if (searchForm) {
        const searchInput = searchForm.querySelector('input[name="q"]');
        const searchType = searchForm.querySelector('select[name="type"]');
        
        // Add search suggestions
        if (searchInput) {
            addSearchSuggestions(searchInput, searchType);
        }
        
        // Add form validation
        searchForm.addEventListener('submit', function(e) {
            if (!validateSearchForm(searchForm)) {
                e.preventDefault();
            }
        });
    }
}

/**
 * Add search suggestions based on search type
 */
function addSearchSuggestions(searchInput, searchType) {
    const suggestions = {
        'bill_number': ['HR-1', 'S-1', 'HJRES-1', 'SJRES-1'],
        'keyword': ['healthcare', 'climate change', 'infrastructure', 'education', 'defense'],
        'sponsor': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones']
    };
    
    searchInput.addEventListener('focus', function() {
        const currentType = searchType ? searchType.value : 'keyword';
        showSearchSuggestions(searchInput, suggestions[currentType] || []);
    });
    
    // Hide suggestions when clicking outside
    document.addEventListener('click', function(e) {
        if (!searchInput.contains(e.target)) {
            hideSearchSuggestions();
        }
    });
}

/**
 * Show search suggestions dropdown
 */
function showSearchSuggestions(input, suggestions) {
    hideSearchSuggestions(); // Remove existing suggestions
    
    if (suggestions.length === 0) return;
    
    const dropdown = document.createElement('div');
    dropdown.className = 'search-suggestions position-absolute bg-dark border rounded shadow-sm';
    dropdown.style.cssText = `
        top: 100%;
        left: 0;
        right: 0;
        z-index: 1000;
        max-height: 200px;
        overflow-y: auto;
    `;
    
    suggestions.forEach(suggestion => {
        const item = document.createElement('div');
        item.className = 'p-2 border-bottom border-secondary cursor-pointer';
        item.style.cursor = 'pointer';
        item.textContent = suggestion;
        
        item.addEventListener('click', function() {
            input.value = suggestion;
            hideSearchSuggestions();
            input.focus();
        });
        
        item.addEventListener('mouseenter', function() {
            this.style.backgroundColor = 'var(--bs-secondary)';
        });
        
        item.addEventListener('mouseleave', function() {
            this.style.backgroundColor = '';
        });
        
        dropdown.appendChild(item);
    });
    
    input.parentNode.style.position = 'relative';
    input.parentNode.appendChild(dropdown);
}

/**
 * Hide search suggestions
 */
function hideSearchSuggestions() {
    const existing = document.querySelector('.search-suggestions');
    if (existing) {
        existing.remove();
    }
}

/**
 * Validate search form
 */
function validateSearchForm(form) {
    // Support both search forms - old search.html (name="q") and new bill_search.html (name="search_query")
    const searchInput = form.querySelector('input[name="q"]') || form.querySelector('input[name="search_query"]');
    const searchQuery = searchInput ? searchInput.value.trim() : '';
    const searchTypeEl = form.querySelector('select[name="type"]') || form.querySelector('select[name="search_type"]');
    const searchType = searchTypeEl ? searchTypeEl.value : '';
    
    if (!searchQuery) {
        showNotification('Please enter a search term', 'warning');
        return false;
    }
    
    // Validate bill number format - allow flexible formats
    if (searchType === 'bill_number') {
        // More flexible regex to allow "HR 1", "HR-1", "H.R.1", etc.
        const billRegex = /^(H\.?R\.?|S\.?|H\.?J\.?R?E?S\.?|S\.?J\.?R?E?S\.?)[-\s]*\d+$/i;
        if (!billRegex.test(searchQuery)) {
            showNotification('Please enter a valid bill number (e.g., HR 1, HR-1234, S-567)', 'warning');
            return false;
        }
    }
    
    return true;
}

/**
 * Enhanced form functionality
 */
function initializeFormEnhancements() {
    // Add auto-save for policy preferences
    const policyForm = document.querySelector('form[action*="profile"]');
    if (policyForm) {
        addAutoSave(policyForm);
    }
    
    // Add dynamic form validation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        addRealTimeValidation(form);
    });
    
    // Enhanced select elements
    enhanceSelectElements();
}

/**
 * Add auto-save functionality to forms
 */
function addAutoSave(form) {
    const inputs = form.querySelectorAll('select, input[type="checkbox"]');
    let autoSaveTimeout;
    
    inputs.forEach(input => {
        input.addEventListener('change', function() {
            clearTimeout(autoSaveTimeout);
            autoSaveTimeout = setTimeout(() => {
                saveFormData(form);
            }, 2000); // Auto-save after 2 seconds of inactivity
        });
    });
}

/**
 * Save form data to localStorage
 */
function saveFormData(form) {
    const formData = new FormData(form);
    const data = {};
    
    for (let [key, value] of formData.entries()) {
        data[key] = value;
    }
    
    localStorage.setItem('policyPreferences', JSON.stringify(data));
    showNotification('Preferences auto-saved', 'info', 2000);
}

/**
 * Add real-time validation to forms
 */
function addRealTimeValidation(form) {
    const inputs = form.querySelectorAll('input, select, textarea');
    
    inputs.forEach(input => {
        input.addEventListener('blur', function() {
            validateInput(input);
        });
        
        input.addEventListener('input', function() {
            clearValidationState(input);
        });
    });
}

/**
 * Validate individual input
 */
function validateInput(input) {
    const value = input.value.trim();
    let isValid = true;
    let message = '';
    
    // Required field validation
    if (input.hasAttribute('required') && !value) {
        isValid = false;
        message = 'This field is required';
    }
    
    // Email validation
    if (input.type === 'email' && value) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(value)) {
            isValid = false;
            message = 'Please enter a valid email address';
        }
    }
    
    // Show validation state
    if (isValid) {
        input.classList.remove('is-invalid');
        input.classList.add('is-valid');
    } else {
        input.classList.remove('is-valid');
        input.classList.add('is-invalid');
        showFieldError(input, message);
    }
    
    return isValid;
}

/**
 * Clear validation state
 */
function clearValidationState(input) {
    input.classList.remove('is-valid', 'is-invalid');
    hideFieldError(input);
}

/**
 * Show field error message
 */
function showFieldError(input, message) {
    hideFieldError(input);
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'invalid-feedback';
    errorDiv.textContent = message;
    
    input.parentNode.appendChild(errorDiv);
}

/**
 * Hide field error message
 */
function hideFieldError(input) {
    const existingError = input.parentNode.querySelector('.invalid-feedback');
    if (existingError) {
        existingError.remove();
    }
}

/**
 * Enhance select elements with search functionality
 */
function enhanceSelectElements() {
    const selects = document.querySelectorAll('select[data-searchable="true"]');
    
    selects.forEach(select => {
        // This would integrate with a library like Choices.js in production
        // For now, just add some basic enhancements
        select.addEventListener('focus', function() {
            this.style.borderColor = 'var(--bs-primary)';
        });
        
        select.addEventListener('blur', function() {
            this.style.borderColor = '';
        });
    });
}

/**
 * Initialize loading states for async operations
 */
function initializeLoadingStates() {
    // Add loading states to buttons that trigger async operations
    const asyncButtons = document.querySelectorAll('[data-async]');
    
    asyncButtons.forEach(button => {
        button.addEventListener('click', function() {
            showButtonLoading(button);
        });
    });
    
    // Add loading states to forms
    const asyncForms = document.querySelectorAll('form[data-async]');
    
    asyncForms.forEach(form => {
        form.addEventListener('submit', function() {
            showFormLoading(form);
        });
    });
}

/**
 * Show loading state on button
 */
function showButtonLoading(button) {
    const originalText = button.innerHTML;
    button.setAttribute('data-original-text', originalText);
    button.disabled = true;
    
    button.innerHTML = `
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        Loading...
    `;
    
    // Reset after 30 seconds as fallback
    setTimeout(() => {
        hideButtonLoading(button);
    }, 30000);
}

/**
 * Hide loading state on button
 */
function hideButtonLoading(button) {
    const originalText = button.getAttribute('data-original-text');
    if (originalText) {
        button.innerHTML = originalText;
        button.disabled = false;
        button.removeAttribute('data-original-text');
    }
}

/**
 * Show loading state on form
 */
function showFormLoading(form) {
    const submitButton = form.querySelector('button[type="submit"]');
    if (submitButton) {
        showButtonLoading(submitButton);
    }
    
    // Disable all form inputs
    const inputs = form.querySelectorAll('input, select, textarea');
    inputs.forEach(input => {
        input.disabled = true;
        input.setAttribute('data-was-disabled', input.disabled);
    });
}

/**
 * Initialize accessibility features
 */
function initializeA11y() {
    // Add ARIA labels to elements that need them
    addAriaLabels();
    
    // Enhance keyboard navigation
    enhanceKeyboardNavigation();
    
    // Add focus management
    manageFocus();
    
    // Add screen reader announcements
    addScreenReaderSupport();
}

/**
 * Add ARIA labels to elements
 */
function addAriaLabels() {
    // Add labels to buttons without text
    const iconButtons = document.querySelectorAll('button:not([aria-label]):has(i[data-feather])');
    iconButtons.forEach(button => {
        const icon = button.querySelector('i[data-feather]');
        if (icon) {
            const iconName = icon.getAttribute('data-feather');
            button.setAttribute('aria-label', getAriaLabelForIcon(iconName));
        }
    });
}

/**
 * Get appropriate ARIA label for Feather icons
 */
function getAriaLabelForIcon(iconName) {
    const labels = {
        'search': 'Search',
        'bell': 'Notifications',
        'user': 'User profile',
        'settings': 'Settings',
        'home': 'Home',
        'eye': 'View details',
        'edit': 'Edit',
        'trash-2': 'Delete',
        'check': 'Mark as complete',
        'x': 'Close',
        'arrow-left': 'Go back',
        'arrow-right': 'Go forward',
        'download': 'Download',
        'upload': 'Upload',
        'share-2': 'Share'
    };
    
    return labels[iconName] || iconName.replace('-', ' ');
}

/**
 * Enhance keyboard navigation
 */
function enhanceKeyboardNavigation() {
    // Add keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd + K for search
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            const searchInput = document.querySelector('input[name="search_query"]');
            if (searchInput) {
                searchInput.focus();
            }
        }
        
        // Escape to close modals or clear search
        if (e.key === 'Escape') {
            hideSearchSuggestions();
            
            // Close any open Bootstrap modals
            const openModal = document.querySelector('.modal.show');
            if (openModal && typeof bootstrap !== 'undefined') {
                const modal = bootstrap.Modal.getInstance(openModal);
                if (modal) {
                    modal.hide();
                }
            }
        }
    });
    
    // Improve focus visibility
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Tab') {
            document.body.classList.add('keyboard-navigation');
        }
    });
    
    document.addEventListener('mousedown', function() {
        document.body.classList.remove('keyboard-navigation');
    });
}

/**
 * Manage focus for better accessibility
 */
function manageFocus() {
    // Return focus to trigger element when modals close
    if (typeof bootstrap !== 'undefined') {
        document.addEventListener('hidden.bs.modal', function(e) {
            const trigger = document.querySelector(`[data-bs-target="#${e.target.id}"]`);
            if (trigger) {
                trigger.focus();
            }
        });
    }
    
    // Focus management for dynamic content
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                // Focus first focusable element in new content
                const newContent = Array.from(mutation.addedNodes).find(node => 
                    node.nodeType === Node.ELEMENT_NODE
                );
                
                if (newContent) {
                    const focusable = newContent.querySelector('button, a, input, select, textarea, [tabindex]');
                    if (focusable && newContent.classList.contains('focus-new-content')) {
                        focusable.focus();
                    }
                }
            }
        });
    });
    
    observer.observe(document.body, { childList: true, subtree: true });
}

/**
 * Add screen reader support
 */
function addScreenReaderSupport() {
    // Create live region for announcements
    const liveRegion = document.createElement('div');
    liveRegion.setAttribute('aria-live', 'polite');
    liveRegion.setAttribute('aria-atomic', 'true');
    liveRegion.className = 'sr-only';
    liveRegion.id = 'live-region';
    document.body.appendChild(liveRegion);
}

/**
 * Announce message to screen readers
 */
function announceToScreenReader(message) {
    const liveRegion = document.getElementById('live-region');
    if (liveRegion) {
        liveRegion.textContent = message;
        
        // Clear after announcement
        setTimeout(() => {
            liveRegion.textContent = '';
        }, 1000);
    }
}

/**
 * Initialize auto-refresh for dynamic content
 */
function initializeAutoRefresh() {
    // Only auto-refresh when page is visible
    let refreshInterval;
    
    function startAutoRefresh() {
        // Refresh alerts every 5 minutes
        refreshInterval = setInterval(() => {
            if (document.visibilityState === 'visible') {
                refreshDynamicContent();
            }
        }, 300000); // 5 minutes
    }
    
    function stopAutoRefresh() {
        if (refreshInterval) {
            clearInterval(refreshInterval);
        }
    }
    
    // Start/stop based on page visibility
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            stopAutoRefresh();
        } else {
            startAutoRefresh();
        }
    });
    
    // Initial start
    if (!document.hidden) {
        startAutoRefresh();
    }
}

/**
 * Refresh dynamic content
 */
function refreshDynamicContent() {
    // Check for new alerts
    const alertsSection = document.querySelector('.alerts-section');
    if (alertsSection) {
        // In a real app, this would make an API call
        // For now, just update the timestamp
        const timestamp = alertsSection.querySelector('.last-updated');
        if (timestamp) {
            timestamp.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
        }
    }
}

/**
 * Show notification to user
 */
function showNotification(message, type = 'info', duration = 5000) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 1055; min-width: 300px; max-width: 500px;';
    alertDiv.innerHTML = `
        <div class="d-flex align-items-start">
            <i data-feather="${getIconForType(type)}" class="me-2 mt-1 flex-shrink-0"></i>
            <div class="flex-grow-1">${message}</div>
            <button type="button" class="btn-close ms-2" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
    
    document.body.appendChild(alertDiv);
    
    // Initialize feather icons in the notification
    if (typeof feather !== 'undefined') {
        feather.replace();
    }
    
    // Announce to screen readers
    announceToScreenReader(message);
    
    // Auto-remove after duration
    if (duration > 0) {
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.classList.remove('show');
                setTimeout(() => {
                    if (alertDiv.parentNode) {
                        alertDiv.remove();
                    }
                }, 150);
            }
        }, duration);
    }
}

/**
 * Get appropriate icon for notification type
 */
function getIconForType(type) {
    const icons = {
        'success': 'check-circle',
        'info': 'info',
        'warning': 'alert-triangle',
        'danger': 'alert-circle',
        'error': 'alert-circle'
    };
    
    return icons[type] || 'info';
}

/**
 * Utility function to debounce function calls
 */
function debounce(func, wait, immediate) {
    let timeout;
    return function executedFunction() {
        const context = this;
        const args = arguments;
        
        const later = function() {
            timeout = null;
            if (!immediate) func.apply(context, args);
        };
        
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        
        if (callNow) func.apply(context, args);
    };
}

/**
 * Utility function to throttle function calls
 */
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Export functions for use in other scripts
window.LegislativeApp = {
    showNotification,
    announceToScreenReader,
    showButtonLoading,
    hideButtonLoading,
    debounce,
    throttle
};
