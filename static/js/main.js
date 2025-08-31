// FIXED: Better Socket.IO connection with proper error handling
const socket = io({
    autoConnect: true,
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: 5,
    timeout: 20000
});

// Global variables
let isMonitoring = false;
let totalAlerts = 0;
let detectionCount = 0;

// DOM elements
const videoStream = document.getElementById('video-stream');
const videoOverlay = document.getElementById('video-overlay');
const startBtn = document.getElementById('start-monitoring');
const stopBtn = document.getElementById('stop-monitoring');
const fileInput = document.getElementById('video-file');
const rtspInput = document.getElementById('rtsp-url');
const alertsContainer = document.getElementById('alerts-container');
const frameCountEl = document.getElementById('frame-count');
const detectionCountEl = document.getElementById('detection-count');
const totalAlertsEl = document.getElementById('total-alerts');
const statusText = document.getElementById('status-text');
const statusDot = document.getElementById('status-dot');

// FIXED: Comprehensive Socket.IO event handlers
socket.on('connect', function() {
    console.log('✅ Connected to server - Socket ID:', socket.id);
    updateStatus('Connected to server', 'ready');
});

socket.on('connected', function(data) {
    console.log('🔌 Server confirmed connection:', data);
});

socket.on('disconnect', function(reason) {
    console.log('❌ Disconnected from server:', reason);
    updateStatus('Disconnected from server', 'ready');
});

socket.on('connect_error', function(error) {
    console.error('❌ Connection error:', error);
    updateStatus('Connection error', 'ready');
});

// Source handling (same as before)
document.querySelectorAll('input[name="source"]').forEach(radio => {
    radio.addEventListener('change', function() {
        const fileSection = document.getElementById('file-upload-section');
        const rtspSection = document.getElementById('rtsp-input-section');
        
        if (this.value === 'file') {
            fileSection.style.display = 'flex';
            rtspSection.style.display = 'none';
        } else {
            fileSection.style.display = 'none';
            rtspSection.style.display = 'flex';
        }
        checkStartButtonState();
    });
});

// File upload
fileInput.addEventListener('change', function() {
    if (this.files[0]) {
        const formData = new FormData();
        formData.append('video', this.files[0]);
        
        updateStatus('Uploading video...', 'monitoring');
        
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            console.log('Upload response:', data);
            if (data.success) {
                updateStatus('Video uploaded successfully', 'ready');
                startBtn.disabled = false;
            } else {
                updateStatus('Upload failed', 'ready');
                alert('Upload failed: ' + data.error);
            }
        })
        .catch(error => {
            updateStatus('Upload error', 'ready');
            console.error('Upload error:', error);
        });
    }
});

// RTSP handling
rtspInput.addEventListener('input', checkStartButtonState);

function checkStartButtonState() {
    const sourceType = document.querySelector('input[name="source"]:checked').value;
    
    if (sourceType === 'file') {
        startBtn.disabled = !fileInput.files[0];
    } else {
        startBtn.disabled = !rtspInput.value.trim();
    }
}

// Start monitoring
startBtn.addEventListener('click', function() {
    const sourceType = document.querySelector('input[name="source"]:checked').value;
    let source = sourceType === 'file' ? 'file_source' : rtspInput.value.trim();
    
    console.log('🚀 Starting monitoring:', { source, type: sourceType });
    
    socket.emit('start_monitoring', {
        source: source,
        type: sourceType
    });
    
    startBtn.disabled = true;
    updateStatus('Starting monitoring...', 'monitoring');
});

// Stop monitoring
stopBtn.addEventListener('click', function() {
    console.log('⏹️ Stopping monitoring');
    socket.emit('stop_monitoring');
    stopBtn.disabled = true;
});

// FIXED: Socket event handlers with detailed logging
socket.on('monitoring_started', function(data) {
    console.log('✅ Monitoring started:', data);
    isMonitoring = true;
    startBtn.disabled = true;
    stopBtn.disabled = false;
    updateStatus('Monitoring active', 'monitoring');
    videoOverlay.style.display = 'none';
});

socket.on('monitoring_stopped', function(data) {
    console.log('⏹️ Monitoring stopped:', data);
    isMonitoring = false;
    startBtn.disabled = false;
    stopBtn.disabled = true;
    
    if (data.final_stats) {
        updateStatus(
            `Stopped - ${data.final_stats.frames_processed} frames, ${data.final_stats.total_detections} detections`, 
            'ready'
        );
    } else {
        updateStatus('Monitoring stopped', 'ready');
    }
    
    videoOverlay.style.display = 'flex';
    videoStream.src = '';
});

socket.on('monitoring_error', function(data) {
    console.error('❌ Monitoring error:', data);
    updateStatus('Error: ' + data.error, 'ready');
    startBtn.disabled = false;
    stopBtn.disabled = true;
});

// FIXED: Video frame handler with better error handling
socket.on('video_frame', function(data) {
    console.log('📹 Received frame:', data.frame_count, 'detections:', data.detections?.length || 0);
    
    try {
        if (data.frame) {
            videoStream.src = 'data:image/jpeg;base64,' + data.frame;
            videoOverlay.style.display = 'none';
        }
        
        if (frameCountEl) {
            frameCountEl.textContent = `Frame: ${data.frame_count}`;
        }
        
        if (data.detections && data.detections.length > 0) {
            detectionCount += data.detections.length;
            if (detectionCountEl) {
                detectionCountEl.textContent = `Detections: ${detectionCount}`;
            }
        }
    } catch (error) {
        console.error('Error processing video frame:', error);
    }
});

socket.on('alert_processing', function(data) {
    console.log('⏳ Processing alert:', data);
    showProcessingAlert(data.type);
});

socket.on('emergency_alert', function(data) {
    console.log('🚨 Emergency alert received:', data);
    
    removeProcessingAlert();
    addEmergencyAlert(data);
    totalAlerts++;
    
    if (totalAlertsEl) {
        totalAlertsEl.textContent = `Total: ${totalAlerts}`;
    }
    
    updateStatus(`${data.type} Alert #${totalAlerts}`, 'alert');
    playAlertSound();
});

socket.on('alert_error', function(data) {
    console.error('❌ Alert error:', data);
    removeProcessingAlert();
});

// Helper functions (same as before)
function updateStatus(text, type) {
    console.log(`Status: ${text} (${type})`);
    if (statusText) statusText.textContent = text;
    if (statusDot) statusDot.className = `status-dot ${type}`;
}

function showProcessingAlert(type) {
    const processingHtml = `
        <div class="processing-alert" id="processing-indicator">
            <i class="fas fa-spinner"></i>
            <strong>Processing ${type.toUpperCase()} incident...</strong>
            <p>AI analysis in progress...</p>
        </div>
    `;
    
    const noAlerts = alertsContainer.querySelector('.no-alerts');
    if (noAlerts) noAlerts.style.display = 'none';
    
    alertsContainer.insertAdjacentHTML('afterbegin', processingHtml);
}

function removeProcessingAlert() {
    const processing = document.getElementById('processing-indicator');
    if (processing) processing.remove();
}

function addEmergencyAlert(alertData) {
    const alertHtml = `
        <div class="alert-item ${alertData.type.toLowerCase()}" onclick="showAlertModal('${alertData.alert_id}', ${JSON.stringify(alertData).replace(/"/g, '&quot;')})">
            <div class="alert-header">
                <span class="alert-type">${alertData.type}</span>
                <span class="alert-time">${alertData.timestamp}</span>
            </div>
            <div class="alert-confidence">
                Confidence: ${(alertData.confidence * 100).toFixed(1)}%
            </div>
            <div class="alert-analysis">
                ${alertData.analysis.substring(0, 100)}${alertData.analysis.length > 100 ? '...' : ''}
            </div>
        </div>
    `;
    
    const noAlerts = alertsContainer.querySelector('.no-alerts');
    if (noAlerts) noAlerts.style.display = 'none';
    
    alertsContainer.insertAdjacentHTML('afterbegin', alertHtml);
}

function showAlertModal(alertId, alertData) {
    const modal = document.getElementById('alert-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalContent = document.getElementById('modal-content');
    
    modalTitle.textContent = `${alertData.type} Emergency Alert`;
    
    const modalHtml = `
        <div class="alert-details">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px;">
                <div><strong>Alert ID:</strong> ${alertData.alert_id}</div>
                <div><strong>Timestamp:</strong> ${alertData.timestamp}</div>
                <div><strong>Type:</strong> ${alertData.type}</div>
                <div><strong>Confidence:</strong> ${(alertData.confidence * 100).toFixed(1)}%</div>
            </div>
            <div style="margin-bottom: 20px;">
                <strong>AI Analysis:</strong>
                <p style="margin-top: 10px; line-height: 1.5;">${alertData.analysis}</p>
            </div>
            <div>
                <strong>Evidence Image:</strong>
                <img src="data:image/jpeg;base64,${alertData.image}" alt="Evidence" style="max-width: 100%; border-radius: 10px; margin-top: 10px;">
            </div>
        </div>
    `;
    
    modalContent.innerHTML = modalHtml;
    modal.style.display = 'block';
}

function playAlertSound() {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        oscillator.frequency.value = 800;
        oscillator.type = 'sine';
        
        gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 1);
        
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 1);
    } catch (error) {
        console.log('Could not play alert sound:', error);
    }
}

// Modal close
document.addEventListener('DOMContentLoaded', function() {
    const closeBtn = document.querySelector('.close');
    if (closeBtn) {
        closeBtn.addEventListener('click', function() {
            document.getElementById('alert-modal').style.display = 'none';
        });
    }
});

window.addEventListener('click', function(event) {
    const modal = document.getElementById('alert-modal');
    if (event.target === modal) {
        modal.style.display = 'none';
    }
});

// Initialize
checkStartButtonState();
console.log('🚀 Emergency Detection System loaded');
