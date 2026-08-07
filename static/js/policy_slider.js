// Legislative Analysis Platform - Policy Slider Component

/**
 * Policy Slider functionality for preference setup
 * Handles interactive sliders for policy category preferences
 */

class PolicySlider {
    constructor(element) {
        this.element = element;
        this.category = element.dataset.category;
        this.valueDisplay = document.getElementById(`value_${element.id.split('_').slice(1).join('_')}`);
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.updateDisplay();
        this.updateSliderAppearance();
    }
    
    setupEventListeners() {
        this.element.addEventListener('input', () => {
            this.updateDisplay();
            this.updateSliderAppearance();
            this.onValueChange();
        });
        
        this.element.addEventListener('mousedown', () => {
            this.element.classList.add('sliding');
        });
        
        this.element.addEventListener('mouseup', () => {
            this.element.classList.remove('sliding');
        });
        
        // Touch events for mobile
        this.element.addEventListener('touchstart', () => {
            this.element.classList.add('sliding');
        });
        
        this.element.addEventListener('touchend', () => {
            this.element.classList.remove('sliding');
        });
    }
    
    updateDisplay() {
        const value = parseInt(this.element.value);
        
        if (this.valueDisplay) {
            this.valueDisplay.textContent = `${value}%`;
            this.valueDisplay.className = `badge ${this.getValueColorClass(value)}`;
        }
    }
    
    updateSliderAppearance() {
        const value = parseInt(this.element.value);
        const percentage = ((value + 100) / 200) * 100;
        
        // Update slider track color based on position
        const hue = this.getValueHue(value);
        const saturation = Math.min(Math.abs(value), 70);
        const lightness = 50;
        
        this.element.style.setProperty('--slider-thumb-color', 
            `hsl(${hue}, ${saturation}%, ${lightness}%)`);
    }
    
    getValueColorClass(value) {
        if (value > 50) return 'bg-success';
        if (value > 10) return 'bg-info';
        if (value > -10) return 'bg-secondary';
        if (value > -50) return 'bg-warning';
        return 'bg-danger';
    }
    
    getValueHue(value) {
        // Green (120) for positive, Red (0) for negative
        if (value >= 0) {
            return 120;
        } else {
            return 0;
        }
    }
    
    onValueChange() {
        // Emit custom event for parent components
        this.element.dispatchEvent(new CustomEvent('policyValueChanged', {
            detail: {
                category: this.category,
                value: parseInt(this.element.value)
            },
            bubbles: true
        }));
        
        // Update form validity
        this.updateFormValidity();
    }
    
    updateFormValidity() {
        const form = this.element.closest('form');
        if (form) {
            // Check if at least one preference is set to non-zero
            const sliders = form.querySelectorAll('.policy-slider');
            const hasPreferences = Array.from(sliders).some(slider => 
                parseInt(slider.value) !== 0
            );
            
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) {
                if (hasPreferences) {
                    submitButton.classList.remove('btn-outline-success');
                    submitButton.classList.add('btn-success');
                } else {
                    submitButton.classList.remove('btn-success');
                    submitButton.classList.add('btn-outline-success');
                }
            }
        }
    }
    
    setValue(value) {
        this.element.value = Math.max(-100, Math.min(100, value));
        this.updateDisplay();
        this.updateSliderAppearance();
        this.onValueChange();
    }
    
    getValue() {
        return parseInt(this.element.value);
    }
    
    reset() {
        this.setValue(0);
    }
    
    animate(fromValue, toValue, duration = 500) {
        const startTime = performance.now();
        const valueRange = toValue - fromValue;
        
        const animateStep = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            // Easing function (ease-out)
            const easedProgress = 1 - Math.pow(1 - progress, 3);
            
            const currentValue = fromValue + (valueRange * easedProgress);
            this.setValue(Math.round(currentValue));
            
            if (progress < 1) {
                requestAnimationFrame(animateStep);
            }
        };
        
        requestAnimationFrame(animateStep);
    }
}

// Policy Slider Manager
class PolicySliderManager {
    constructor() {
        this.sliders = new Map();
        this.presets = {
            progressive: {
                'Healthcare': 80, 'Environment': 90, 'Education': 85, 'Civil Rights': 90,
                'Social Services': 75, 'Immigration': 60, 'Technology': 50, 'Justice': 40,
                'Defense': -20, 'Economy': 30, 'Energy': 70, 'Agriculture': 40,
                'Transportation': 60, 'Tax Policy': 50, 'Trade': 30
            },
            conservative: {
                'Defense': 85, 'Economy': 80, 'Tax Policy': -60, 'Trade': 70,
                'Agriculture': 60, 'Energy': 40, 'Transportation': 50, 'Justice': 75,
                'Healthcare': -30, 'Environment': -40, 'Social Services': -50, 'Immigration': -40,
                'Education': 20, 'Technology': 30, 'Civil Rights': 10
            },
            libertarian: {
                'Economy': 90, 'Tax Policy': -80, 'Trade': 85, 'Technology': 70,
                'Civil Rights': 60, 'Justice': -30, 'Defense': -20, 'Healthcare': -60,
                'Education': -40, 'Social Services': -70, 'Environment': 20, 'Immigration': 40,
                'Agriculture': -30, 'Transportation': -20, 'Energy': 50
            },
            moderate: {
                'Healthcare': 20, 'Environment': 30, 'Economy': 40, 'Education': 50,
                'Defense': 30, 'Immigration': 10, 'Technology': 40, 'Agriculture': 20,
                'Transportation': 30, 'Energy': 20, 'Justice': 20, 'Social Services': 25,
                'Tax Policy': 0, 'Trade': 30, 'Civil Rights': 40
            }
        };
        
        this.init();
    }
    
    init() {
        this.initializeSliders();
        this.setupGlobalEventListeners();
        this.loadSavedPreferences();
    }
    
    initializeSliders() {
        const sliderElements = document.querySelectorAll('.policy-slider');
        
        sliderElements.forEach(element => {
            const slider = new PolicySlider(element);
            this.sliders.set(slider.category, slider);
        });
        
        console.log(`Initialized ${this.sliders.size} policy sliders`);
    }
    
    setupGlobalEventListeners() {
        // Listen for policy value changes
        document.addEventListener('policyValueChanged', (event) => {
            this.onPolicyValueChanged(event.detail);
        });
        
        // Setup preset buttons
        document.addEventListener('click', (event) => {
            if (event.target.matches('[onclick*="applyPreset"]')) {
                const presetName = event.target.getAttribute('onclick').match(/applyPreset\('(\w+)'\)/)[1];
                this.applyPreset(presetName);
                event.preventDefault();
            }
        });
    }
    
    loadSavedPreferences() {
        const saved = sessionStorage.getItem('policyPreferences');
        if (saved) {
            try {
                const preferences = JSON.parse(saved);
                this.setPreferences(preferences, false);
            } catch (e) {
                console.warn('Failed to load saved preferences:', e);
            }
        }
    }
    
    onPolicyValueChanged(detail) {
        // Save preferences to session storage
        this.savePreferences();
        
        // Update UI indicators
        this.updateProgressIndicator();
        
        // Trigger analysis preview update
        this.debounce(() => {
            this.updateAnalysisPreview();
        }, 500)();
    }
    
    savePreferences() {
        const preferences = this.getAllPreferences();
        sessionStorage.setItem('policyPreferences', JSON.stringify(preferences));
    }
    
    updateProgressIndicator() {
        const preferences = this.getAllPreferences();
        const setCount = Object.values(preferences).filter(v => v !== 0).length;
        const totalCount = Object.keys(preferences).length;
        const percentage = (setCount / totalCount) * 100;
        
        const progressBar = document.querySelector('.setup-progress-bar');
        if (progressBar) {
            progressBar.style.width = `${percentage}%`;
            progressBar.setAttribute('aria-valuenow', percentage);
        }
        
        const progressText = document.querySelector('.setup-progress-text');
        if (progressText) {
            progressText.textContent = `${setCount} of ${totalCount} preferences set`;
        }
    }
    
    updateAnalysisPreview() {
        const preferences = this.getAllPreferences();
        
        // Update preview cards
        this.updatePreviewCards(preferences);
        
        // Update preference strength meter
        this.updateStrengthMeter(preferences);
    }
    
    updatePreviewCards(preferences) {
        const strongSupport = [];
        const moderateSupport = [];
        const neutral = [];
        const moderateOpposition = [];
        const strongOpposition = [];
        
        Object.entries(preferences).forEach(([category, value]) => {
            if (value >= 70) strongSupport.push(category);
            else if (value >= 30) moderateSupport.push(category);
            else if (value > -30) neutral.push(category);
            else if (value >= -70) moderateOpposition.push(category);
            else strongOpposition.push(category);
        });
        
        // Update preview sections
        this.updatePreviewSection('strong-support-preview', strongSupport, 'success');
        this.updatePreviewSection('moderate-support-preview', moderateSupport, 'info');
        this.updatePreviewSection('moderate-opposition-preview', moderateOpposition, 'warning');
        this.updatePreviewSection('strong-opposition-preview', strongOpposition, 'danger');
    }
    
    updatePreviewSection(sectionId, items, colorClass) {
        const section = document.getElementById(sectionId);
        if (!section) return;
        
        section.innerHTML = '';
        
        if (items.length === 0) {
            section.innerHTML = '<small class="text-muted">None</small>';
            return;
        }
        
        items.forEach(item => {
            const badge = document.createElement('span');
            badge.className = `badge bg-${colorClass} me-1 mb-1`;
            badge.textContent = item;
            section.appendChild(badge);
        });
    }
    
    updateStrengthMeter(preferences) {
        const values = Object.values(preferences);
        const avgStrength = values.reduce((sum, val) => sum + Math.abs(val), 0) / values.length;
        
        const strengthMeter = document.querySelector('.preference-strength-meter');
        if (strengthMeter) {
            const bar = strengthMeter.querySelector('.progress-bar');
            if (bar) {
                bar.style.width = `${avgStrength}%`;
                bar.className = `progress-bar ${this.getStrengthColorClass(avgStrength)}`;
            }
        }
        
        const strengthText = document.querySelector('.preference-strength-text');
        if (strengthText) {
            strengthText.textContent = this.getStrengthDescription(avgStrength);
        }
    }
    
    getStrengthColorClass(strength) {
        if (strength > 70) return 'bg-success';
        if (strength > 40) return 'bg-info';
        if (strength > 20) return 'bg-warning';
        return 'bg-secondary';
    }
    
    getStrengthDescription(strength) {
        if (strength > 70) return 'Very Strong Preferences';
        if (strength > 40) return 'Strong Preferences';
        if (strength > 20) return 'Moderate Preferences';
        return 'Mild Preferences';
    }
    
    applyPreset(presetName) {
        if (!this.presets[presetName]) {
            console.warn(`Unknown preset: ${presetName}`);
            return;
        }
        
        const preset = this.presets[presetName];
        this.setPreferences(preset, true);
        
        // Show success message
        if (window.LegislativeUtils) {
            window.LegislativeUtils.showAlert(
                `Applied ${presetName} preset successfully!`, 
                'success'
            );
        }
    }
    
    setPreferences(preferences, animate = false) {
        Object.entries(preferences).forEach(([category, value]) => {
            const slider = this.sliders.get(category);
            if (slider) {
                if (animate) {
                    const currentValue = slider.getValue();
                    slider.animate(currentValue, value, 800);
                } else {
                    slider.setValue(value);
                }
            }
        });
    }
    
    getAllPreferences() {
        const preferences = {};
        this.sliders.forEach((slider, category) => {
            preferences[category] = slider.getValue();
        });
        return preferences;
    }
    
    resetAll() {
        this.sliders.forEach(slider => {
            slider.reset();
        });
        
        // Clear saved preferences
        sessionStorage.removeItem('policyPreferences');
        
        if (window.LegislativeUtils) {
            window.LegislativeUtils.showAlert(
                'All preferences reset to neutral', 
                'info'
            );
        }
    }
    
    validatePreferences() {
        const preferences = this.getAllPreferences();
        const setPreferences = Object.values(preferences).filter(v => v !== 0);
        
        return {
            isValid: setPreferences.length > 0,
            setCount: setPreferences.length,
            totalCount: Object.keys(preferences).length,
            message: setPreferences.length === 0 ? 
                'Please set at least one policy preference' : 
                `${setPreferences.length} preferences configured`
        };
    }
    
    // Utility method for debouncing
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
    }
}

// Global functions for template usage
function updateSliderDisplay(slider) {
    const manager = window.policySliderManager;
    if (manager) {
        const policySlider = manager.sliders.get(slider.dataset.category);
        if (policySlider) {
            policySlider.updateDisplay();
            policySlider.updateSliderAppearance();
        }
    }
}

function applyPreset(presetName) {
    const manager = window.policySliderManager;
    if (manager) {
        if (!confirm(`Apply the ${presetName} preset? This will override your current settings.`)) {
            return;
        }
        manager.applyPreset(presetName);
    }
}

function resetToDefaults() {
    const manager = window.policySliderManager;
    if (manager) {
        if (!confirm('Reset all preferences to neutral (0%)? This will clear your current settings.')) {
            return;
        }
        manager.resetAll();
    }
}

function getCurrentPreferences() {
    const manager = window.policySliderManager;
    return manager ? manager.getAllPreferences() : {};
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    if (document.querySelector('.policy-slider')) {
        window.policySliderManager = new PolicySliderManager();
        console.log('Policy slider manager initialized');
    }
});

// Export for use in other modules
window.PolicySlider = PolicySlider;
window.PolicySliderManager = PolicySliderManager;
