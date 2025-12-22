// Global state
let isHealthy = true;
let eventCounter = 0;

// Initialize dashboard
document.addEventListener('DOMContentLoaded', function() {
    addEvent('System', 'Dashboard initialized. Monitoring started.', 'success');
    startMetricsSimulation();
});

// Simulate realistic metrics changes
function startMetricsSimulation() {
    setInterval(function() {
        if (isHealthy) {
            // Normal operation
            const uptime = (99 + Math.random()).toFixed(2);
            const responseTime = Math.floor(40 + Math.random() * 20);
            const requestRate = Math.floor(1000 + Math.random() * 500);
            const errorRate = (Math.random() * 0.15).toFixed(2);
            const cpuUsage = Math.floor(20 + Math.random() * 30);
            const mttd = Math.floor(8 + Math.random() * 8);

            updateMetrics(uptime, responseTime, requestRate, errorRate, cpuUsage, mttd);
        }
    }, 5000);
}

// Update metrics display
function updateMetrics(uptime, responseTime, requestRate, errorRate, cpuUsage, mttd) {
    document.getElementById('uptime').textContent = uptime + '%';
    document.getElementById('responseTime').textContent = responseTime + 'ms';
    document.getElementById('requestRate').textContent = (requestRate / 1000).toFixed(1) + 'K';
    document.getElementById('errorRate').textContent = errorRate + '%';
    document.getElementById('cpuUsage').textContent = cpuUsage + '%';
    document.getElementById('cpuBar').style.width = cpuUsage + '%';
    document.getElementById('mttd').textContent = mttd + 's';

    // Dynamic threshold logic - if error rate spikes abnormally
    if (parseFloat(errorRate) > 1.5) {
        const dynamicAlerts = parseInt(document.getElementById('dynamicAlerts').textContent) || 0;
        if (dynamicAlerts === 0) {
            addEvent('Dynamic Alert', 'Error rate spike detected: ' + errorRate + '% (abnormal pattern)', 'warning');
            document.getElementById('dynamicAlerts').textContent = '1';
        }
    }
}

// Simulate high load incident
function simulateHighLoad() {
    isHealthy = false;
    addEvent('Incident', 'High load incident triggered. Metrics degrading.', 'warning');
    document.getElementById('statusIndicator').classList.remove('healthy');
    document.getElementById('statusIndicator').classList.add('warning');
    document.getElementById('statusText').textContent = 'Degraded';
    
    let i = 0;
    const interval = setInterval(function() {
        if (i >= 5) {
            clearInterval(interval);
            return;
        }
        
        const uptime = (95 - i * 2).toFixed(2);
        const responseTime = Math.floor(200 + i * 150);
        const requestRate = Math.floor(5000 + i * 2000);
        const errorRate = (0.5 + i * 1.2).toFixed(2);
        const cpuUsage = Math.floor(60 + i * 10);
        const mttd = '5s';

        updateMetrics(uptime, responseTime, requestRate, errorRate, cpuUsage, mttd);
        
        if (parseFloat(errorRate) > 2) {
            const staticAlerts = parseInt(document.getElementById('staticAlerts').textContent) || 0;
            if (staticAlerts === 0) {
                addEvent('Static Alert', 'Error rate exceeds threshold (>2%)', 'error');
                document.getElementById('staticAlerts').textContent = '1';
            }
        }
        
        i++;
    }, 2000);

    setTimeout(function() {
        addEvent('AIOps', 'Application Insights detected anomalies. See Application Map for root cause analysis.', 'warning');
    }, 6000);
}

// Simulate complete service down incident
function simulateIncident() {
    isHealthy = false;
    
    addEvent('CRITICAL', '🚨 Service Down incident triggered!', 'error');
    addEvent('System', 'Azure Access Restriction applied (mimicking service block)', 'error');
    
    document.getElementById('statusIndicator').classList.remove('healthy', 'warning');
    document.getElementById('statusIndicator').classList.add('critical');
    document.getElementById('statusText').textContent = 'Critical';
    
    const alertBanner = document.getElementById('alertBanner');
    document.getElementById('alertMessage').textContent = 'Service is down. All requests failing.';
    alertBanner.classList.add('show');
    
    // Immediately trigger alerts
    document.getElementById('staticAlerts').textContent = '1';
    document.getElementById('dynamicAlerts').textContent = '1';
    
    // Degrade all metrics
    updateMetrics('0.0', '∞', '0', '100.0', '0', '2s');
    
    // Update dependencies
    updateDependencyStatus('dbStatus', 'Failed', 'error');
    updateDependencyStatus('cacheStatus', 'Failed', 'error');
    updateDependencyStatus('gatewayStatus', 'Failed', 'error');
    
    // Timeline of incident response
    setTimeout(() => {
        addEvent('Monitoring', 'Global availability test failed from 3/5 locations (London, Tokyo, NY)', 'error');
        document.getElementById('availabilitySLI').textContent = '60%';
    }, 1000);
    
    setTimeout(() => {
        addEvent('Alert', 'Static threshold alert: Availability < 90% - EMAIL SENT', 'error');
    }, 2000);
    
    setTimeout(() => {
        addEvent('AIOps', 'Dynamic threshold alert: Abnormal spike in failed requests - AI DETECTED', 'error');
    }, 3000);
    
    setTimeout(() => {
        addEvent('RCA', 'Application Insights Application Map shows red node. Investigating failures...', 'warning');
    }, 4000);
    
    setTimeout(() => {
        addEvent('RCA', 'Top response codes: 403 (Access Denied) - 100% of requests', 'error');
    }, 5000);
    
    setTimeout(() => {
        addEvent('Analysis', 'Root cause identified: Access Restriction policy denying all traffic', 'error');
    }, 6000);
    
    setTimeout(() => {
        addEvent('Remediation', 'Awaiting manual intervention: Remove access restrictions', 'warning');
        document.getElementById('totalIncidents').textContent = '1';
    }, 7000);
}

// Reset metrics to healthy state
function resetMetrics() {
    isHealthy = true;
    
    addEvent('System', 'Metrics reset. Service recovery initiated.', 'success');
    
    document.getElementById('statusIndicator').classList.remove('warning', 'critical');
    document.getElementById('statusIndicator').classList.add('healthy');
    document.getElementById('statusText').textContent = 'Healthy';
    
    const alertBanner = document.getElementById('alertBanner');
    alertBanner.classList.remove('show');
    
    // Reset metrics
    updateMetrics('99.9', '45', '1.2K', '0.1', '32', '12');
    document.getElementById('staticAlerts').textContent = '0';
    document.getElementById('dynamicAlerts').textContent = '0';
    document.getElementById('availabilitySLI').textContent = '100%';
    
    // Reset dependencies
    updateDependencyStatus('dbStatus', 'Connected', 'success');
    updateDependencyStatus('cacheStatus', 'Connected', 'success');
    updateDependencyStatus('gatewayStatus', 'Connected', 'success');
}

// Helper function to update dependency status
function updateDependencyStatus(elementId, status, type) {
    const element = document.getElementById(elementId);
    element.textContent = status;
    // You could add visual indicators here if needed
}

// Add event to the activity log
function addEvent(source, message, type) {
    eventCounter++;
    const eventLog = document.getElementById('eventLog');
    
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    
    // Map type to emoji and styling
    const icons = {
        'success': '✅',
        'error': '❌',
        'warning': '⚠️',
        'info': 'ℹ️'
    };
    
    const icon = icons[type] || icons['info'];
    
    const eventElement = document.createElement('div');
    eventElement.className = `event ${type}`;
    eventElement.innerHTML = `
        <div class="event-icon">${icon}</div>
        <div class="event-content">
            <div class="event-time">${timeStr} • ${source}</div>
            <div class="event-message">${message}</div>
        </div>
    `;
    
    // Add to top of log
    eventLog.insertBefore(eventElement, eventLog.firstChild);
    
    // Keep only the last 20 events
    while (eventLog.children.length > 20) {
        eventLog.removeChild(eventLog.lastChild);
    }
    
    // Log to console for debugging
    console.log(`[${source}] ${message}`);
}

// Analytics tracking (would send to Application Insights)
function trackEvent(eventName, properties = {}) {
    if (window.appInsights) {
        window.appInsights.trackEvent({
            name: eventName,
            properties: properties
        });
    } else {
        console.log('Tracking:', eventName, properties);
    }
}

// Track page view on load
window.addEventListener('load', function() {
    trackEvent('DashboardLoaded', {
        timestamp: new Date().toISOString(),
        url: window.location.href
    });
});
