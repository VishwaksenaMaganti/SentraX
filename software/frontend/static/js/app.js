/**
 * SentraX Command Center & Ecosystem Dashboard Client
 * Pure Live Hardware Platform:
 * 1. Single-Module Live Platform: Displays live telemetry as soon as ESP32 Core Controller is connected.
 * 2. Dedicated Pairing Controls for ESP32 Core Gateway (Web Bluetooth, PC BLE, or COM Port).
 * 3. Zero Simulated Data: Zero synthetic jitter, clean unpopulated standby state until hardware verified.
 */

// Service UUIDs defined in ESP32 firmware
const SENTRAX_SERVICE_UUID = '73656e74-7261-7800-0001-000000000000';
const CHAR_TELEMETRY_UUID  = '73656e74-7261-7800-0002-000000000002';
const CHAR_EVENTS_UUID     = '73656e74-7261-7800-0002-000000000003';
const CHAR_COMMANDS_UUID   = '73656e74-7261-7800-0002-000000000004';

// State Store
const state = {
    activeTab: 'command-center',
    telemetry: {},
    events: [],
    history: [],
    devices: [],
    map: null,
    routeLayer: null,
    charts: {},
    esp32Connected: false,
    esp8266Connected: false,
    bothModulesConnected: false,
    lastPacketTime: 0,
    webBluetoothDevice: null,
    webBluetoothServer: null,
    webBluetoothCharCommands: null,
    lastEinkKey: null,
    // Sensor-Camera Fusion & CV Extensions
    detectionMode: 'FUSION',
    bypassStandby: false,
    demoStallMode: true,
    cvStats: null,
    cvConfig: null
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initWebSocket();
    initCharts();
    initMap();
    fetchInitialData();
    initHardwareModals();
    initAerialControls();
    pollHardwareStatus();
    setInterval(pollHardwareStatus, 2000);
    setInterval(checkTelemetryWatchdog, 500);
    initFusionAndCV();
    initCopilot();
});

// ==========================================
// SENTRI CO-PILOT (mascot dock)
// ==========================================
let sentri = null;

function initCopilot() {
    const root = document.getElementById('sentri-root');
    if (!root || !window.Sentri) return;
    sentri = window.Sentri.mount(root, { mood: 'standby' });

    const dock = document.getElementById('copilot-dock');
    const log = document.getElementById('sentri-log');
    const syncTone = () => { if (dock) dock.dataset.tone = root.dataset.tone || 'idle'; };
    syncTone();

    root.addEventListener('sentri:mood', (e) => {
        syncTone();
        const mood = e.detail.mood;
        if (!log || mood === 'standby') return;
        log.querySelector('.dock-log-empty')?.remove();
        const li = document.createElement('li');
        li.dataset.tone = window.Sentri.MOODS[mood].tone;
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        li.innerHTML = `<span class="dot"></span><span></span><span class="t">${time}</span>`;
        li.children[1].textContent = window.Sentri.MOODS[mood].title;
        log.prepend(li);
        while (log.children.length > 4) log.lastElementChild.remove();
    });

    const mute = document.getElementById('sentri-mute');
    if (mute) {
        const paint = () => {
            mute.setAttribute('aria-pressed', String(sentri.muted));
            mute.innerHTML = `<i class="ph ${sentri.muted ? 'ph-speaker-slash' : 'ph-speaker-high'}" aria-hidden="true"></i>`;
            mute.title = sentri.muted ? "Unmute Sentri's chirps" : "Mute Sentri's chirps";
        };
        paint();
        mute.addEventListener('click', () => {
            sentri.setMuted(!sentri.muted);
            paint();
            if (!sentri.muted) sentri.play();
        });
    }
}

function updateCopilot(t) {
    if (!sentri) return;
    const live = state.esp32Connected || state.detectionMode === 'CAMERA' || state.bypassStandby;
    sentri.fromTelemetry(t, live);
}

// Telemetry stream watchdog: zeroes dashboard if ESP32 disconnects or freezes for > 2 seconds
function checkTelemetryWatchdog() {
    if (state.detectionMode === 'CAMERA' || state.bypassStandby) {
        return;
    }
    if (state.esp32Connected && state.lastPacketTime > 0) {
        if (Date.now() - state.lastPacketTime > 2000) {
            console.warn('[SentraX Watchdog] Telemetry signal lost (>2s without packets). Locking into Hardware Standby.');
            resetDashboardToStandby('Hardware Signal Lost: ESP32 disconnected or stopped transmitting.');
        }
    }
}

// Resets every DOM telemetry meter, sensor pill, and chart directly to 0 / Standby
function resetDashboardToStandby(reasonMessage) {
    state.bothModulesConnected = false;
    state.lastPacketTime = 0;

    // If in CAMERA mode or user bypassed standby for demonstration, do not lock screen
    if (state.detectionMode === 'CAMERA' || state.bypassStandby) {
        return;
    }

    const standbyOverlay = document.getElementById('hardware-standby-overlay');
    if (standbyOverlay) standbyOverlay.classList.remove('hidden');
    if (sentri) sentri.fromTelemetry(null, false);

    // Force zero all primary meters
    setText('val-current-speed', '0.0');
    setText('val-rec-speed', '--');
    setText('val-risk-score', '0');
    setText('val-traffic-level', 'STANDBY');
    setText('val-road-cond', 'STANDBY');

    const circle = document.getElementById('risk-meter-circle');
    if (circle) circle.className = 'risk-circle';

    const reasonsContainer = document.getElementById('risk-reasons-list');
    if (reasonsContainer) {
        const msg = reasonMessage || 'Awaiting connection of ESP32 Core Controller.';
        reasonsContainer.innerHTML = `<li>${msg}</li>`;
    }

    // Zero out environmental sensors
    setText('tel-temp', '-- °C');
    setText('tel-humidity', '-- %');
    setText('tel-moisture', 'STANDBY');
    setText('tel-sound', 'STANDBY');
    setText('tel-rfid', 'STANDBY');
    setText('tel-night', 'STANDBY');
    setText('tel-us1', 'STANDBY');
    setText('tel-us2', 'STANDBY');
    setText('tel-speed', 'STANDBY');
    speedReading.last = null;

    // Reset IR pills to neutral STANDBY
    for (let i = 1; i <= 4; i++) {
        const pill = document.getElementById(`ir-${i}-status`);
        if (pill) {
            pill.textContent = 'STANDBY';
            pill.style.color = 'var(--text-muted)';
        }
    }

    // Reset chart data so old spikes do not persist
    if (state.charts.speed) {
        state.charts.speed.data.datasets[0].data = Array(15).fill(0);
        state.charts.speed.data.datasets[1].data = Array(15).fill(0);
        state.charts.speed.update('none');
    }
    if (state.charts.risk) {
        state.charts.risk.data.datasets[0].data = Array(15).fill(0);
        state.charts.risk.update('none');
    }

    // Reset corridor incident alert banner
    const banner = document.getElementById('live-incident-alert-banner');
    if (banner) {
        banner.className = 'live-incident-banner clear';
        const iconEl = document.getElementById('incident-banner-icon');
        const titleEl = document.getElementById('incident-banner-title');
        const descEl = document.getElementById('incident-banner-desc');
        const badgeEl = document.getElementById('incident-banner-badge');
        const auditBtn = document.getElementById('btn-banner-inspect-audit');
        if (iconEl) iconEl.textContent = '🛡️';
        if (titleEl) titleEl.textContent = 'CORRIDOR STATUS: STANDBY';
        if (descEl) descEl.textContent = 'Awaiting ESP32 hardware connection or test execution.';
        if (badgeEl) badgeEl.textContent = 'STANDBY';
        if (auditBtn) auditBtn.style.display = 'none';
    }

    updateHardwarePills();
    resetAerialTwinToStandby();
}

// Navigation Handling
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetTab = item.getAttribute('data-tab');
            switchTab(targetTab);
        });
    });
}

function switchTab(tabId) {
    state.activeTab = tabId;
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.querySelector(`[data-tab="${tabId}"]`)?.classList.add('active');

    document.querySelectorAll('.page-container').forEach(el => el.classList.remove('active'));
    const targetPage = document.getElementById(`page-${tabId}`);
    if (targetPage) {
        targetPage.classList.add('active');
        const titleEl = document.getElementById('current-page-title');
        if (titleEl) titleEl.textContent = targetPage.getAttribute('data-title') || 'Command Center';
    }

    if (tabId === 'navigation') {
        setTimeout(() => {
            if (typeof navState !== 'undefined' && navState.isGoogleActive && navState.googleMap) {
                google.maps.event.trigger(navState.googleMap, 'resize');
                if (navState.bounds) navState.googleMap.fitBounds(navState.bounds);
            } else if (typeof navState !== 'undefined' && navState.leafletMap) {
                navState.leafletMap.invalidateSize();
                if (navState.polylineLayer) navState.leafletMap.fitBounds(navState.polylineLayer.getBounds(), { padding: [35, 35] });
            } else if (state.map && typeof state.map.invalidateSize === 'function') {
                state.map.invalidateSize();
            }
        }, 200);
    }
}

// WebSocket Live Stream
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;
    let socket;

    function connect() {
        socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            console.log('[SentraX WS] Connected to backend gateway');
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'telemetry_update' || data.type === 'initial_state') {
                    if (data.telemetry) updateTelemetryUI(data.telemetry);
                    if (data.event) prependEventTimeline(data.event);
                }
            } catch (err) {
                console.error('[SentraX WS] Parsing error:', err);
            }
        };

        socket.onclose = () => {
            console.warn('[SentraX WS] Disconnected. Reconnecting in 2s...');
            setTimeout(connect, 2000);
        };

        socket.onerror = (err) => {
            console.error('[SentraX WS] Error:', err);
            socket.close();
        };
    }

    connect();
}

// Update UI Elements with Live Telemetry
function updateTelemetryUI(t) {
    state.telemetry = t;
    state.esp32Connected = Boolean(t.esp32_connected);
    state.esp8266Connected = false;
    state.bothModulesConnected = Boolean(t.esp32_connected);

    updateHardwarePills();
    updateCopilot(t);

    const standbyOverlay = document.getElementById('hardware-standby-overlay');

    if (state.esp32Connected || state.detectionMode === 'CAMERA' || state.bypassStandby) {
        state.lastPacketTime = Date.now();
        // UNLOCK DASHBOARD: Display live sensor/vision stream
        if (standbyOverlay) standbyOverlay.classList.add('hidden');

        setText('val-current-speed', t.measured_speed_kmh.toFixed(1));
        setText('val-rec-speed', t.recommended_speed_kmh.toFixed(0));
        setText('val-risk-score', t.risk_score);
        setText('val-traffic-level', t.traffic_level);
        setText('val-road-cond', t.road_condition);

        const circle = document.getElementById('risk-meter-circle');
        if (circle) {
            circle.className = 'risk-circle ' + (t.risk_score >= 65 ? 'critical' : (t.risk_score >= 35 ? 'warning' : ''));
        }

        const reasonsContainer = document.getElementById('risk-reasons-list');
        if (reasonsContainer && t.risk_reasons) {
            reasonsContainer.innerHTML = t.risk_reasons.map(r => `<li>${r}</li>`).join('');
        }

        // Environmental Telemetry
        setText('tel-temp', `${t.temperature_c.toFixed(1)} °C`);
        setText('tel-humidity', `${t.humidity_pct.toFixed(0)} %`);
        setText('tel-moisture', `${t.moisture_raw} (${t.road_condition})`);
        setText('tel-sound', t.sound_active ? 'IMPACT DETECTED' : 'CLEAR');
        setText('tel-rfid', t.rfid_active ? 'PRIORITY AMBULANCE' : 'NONE');
        setText('tel-night', t.night_mode ? 'ACTIVE' : 'DAYTIME');

        // IR Sensors
        if (t.ir_sensors) {
            for (let i = 0; i < 4; i++) {
                const pill = document.getElementById(`ir-${i+1}-status`);
                if (pill) {
                    pill.textContent = t.ir_sensors[i] ? 'OCCUPIED' : 'CLEAR';
                    pill.style.color = t.ir_sensors[i] ? 'var(--accent-rose)' : 'var(--accent-emerald)';
                }
            }
        }

        updateSpeedReading(t);

        // Update real-time corridor incident alert banner
        updateIncidentBanner(t);

        updateChartsStream(t);
        updateAerialTwinUI(t);
        updateNavigationScreenTelemetry(t);

    } else {
        const reason = (t.risk_reasons && t.risk_reasons.length > 0)
            ? t.risk_reasons[0]
            : 'Awaiting connection of ESP32 Core Controller.';
        resetDashboardToStandby(reason);
        updateIncidentBanner(t);
        updateNavigationScreenTelemetry(t);
    }
}

// The ESP32 sends a speed only after a vehicle crosses US1 then US2, and its telemetry has no
// beam states. A new speed value therefore marks a fresh measurement: the gate shows both beams
// as crossed and highlights the reading for SPEED_HOLD_MS so it can be read during a demo.
const SPEED_HOLD_MS = 1500;
const speedReading = { last: null, at: 0 };

function updateSpeedReading(t) {
    const speed = Number(t.measured_speed_kmh || 0);
    const now = Date.now();
    if (speedReading.last !== null && speed > 0 && speed !== speedReading.last) {
        speedReading.at = now;
    }
    speedReading.last = speed;
    const fresh = now - speedReading.at < SPEED_HOLD_MS;

    setText('tel-us1', (t.ultrasonic_state?.us1_active || fresh) ? 'INTERRUPTED' : 'CLEAR');
    setText('tel-us2', (t.ultrasonic_state?.us2_active || fresh) ? 'INTERRUPTED' : 'CLEAR');
    setText('tel-speed', speed > 0 ? `${speed.toFixed(1)} km/h` : 'NO READING');
    document.getElementById('tel-speed')?.classList.toggle('is-fresh', fresh);
}

// Updates the Real-Time Corridor Incident Alert Banner (Collisions, Stalls, Topples, Wrong-Way)
function updateIncidentBanner(t) {
    const banner = document.getElementById('live-incident-alert-banner');
    if (!banner || !t) return;
    const iconEl = document.getElementById('incident-banner-icon');
    const titleEl = document.getElementById('incident-banner-title');
    const descEl = document.getElementById('incident-banner-desc');
    const badgeEl = document.getElementById('incident-banner-badge');
    const auditBtn = document.getElementById('btn-banner-inspect-audit');

    if (t.vehicle_toppled) {
        banner.className = 'live-incident-banner critical';
        if (iconEl) iconEl.textContent = '🔄';
        if (titleEl) titleEl.textContent = '🚨 CRITICAL: VEHICLE TOPPLED OVER / ROLLOVER';
        if (descEl) descEl.textContent = 'Camera vision detected toy vehicle rollover (abnormal aspect ratio) on roadway corridor! Enforcing emergency 20 km/h advisory & warning strobe.';
        if (badgeEl) badgeEl.textContent = 'CRITICAL ROLLOVER';
        if (auditBtn) auditBtn.style.display = 'inline-block';
    } else if (t.collision) {
        banner.className = 'live-incident-banner critical';
        if (iconEl) iconEl.textContent = '💥';
        if (titleEl) titleEl.textContent = '🚨 CRITICAL ALERT: VEHICLE COLLISION DETECTED';
        if (descEl) descEl.textContent = 'Multi-modal collision confirmed on corridor! Dynamic warning active, speed advisory reduced to 20 km/h.';
        if (badgeEl) badgeEl.textContent = 'CRITICAL COLLISION';
        if (auditBtn) auditBtn.style.display = 'inline-block';
    } else if (t.wrong_way) {
        banner.className = 'live-incident-banner critical';
        if (iconEl) iconEl.textContent = '⛔';
        if (titleEl) titleEl.textContent = '⛔ CRITICAL: WRONG-WAY VEHICLE DETECTED';
        if (descEl) descEl.textContent = 'Vehicle trajectory analysis detected vehicle traveling against prescribed traffic direction!';
        if (badgeEl) badgeEl.textContent = 'WRONG-WAY';
        if (auditBtn) auditBtn.style.display = 'inline-block';
    } else if (t.emergency_vehicle || t.rfid_active) {
        banner.className = 'live-incident-banner warning';
        if (iconEl) iconEl.textContent = '🚑';
        if (titleEl) titleEl.textContent = '🚑 PRIORITY: EMERGENCY VEHICLE IN TRANSIT';
        if (descEl) descEl.textContent = 'RFID tagged emergency vehicle passing through corridor. Green wave corridor priority signaled.';
        if (badgeEl) badgeEl.textContent = 'EMERGENCY PASS';
        if (auditBtn) auditBtn.style.display = 'inline-block';
    } else if (t.stalled_vehicle) {
        banner.className = 'live-incident-banner warning';
        if (iconEl) iconEl.textContent = '⚠️';
        if (titleEl) titleEl.textContent = '⚠️ WARNING: STALLED VEHICLE ON ROADWAY';
        if (descEl) descEl.textContent = 'Vehicle stationary in roadway lane exceeding threshold duration. Corridor advisory speed reduced.';
        if (badgeEl) badgeEl.textContent = 'STALLED VEHICLE';
        if (auditBtn) auditBtn.style.display = 'inline-block';
    } else if (t.road_condition === 'WET' || t.road_condition === 'SLIPPERY') {
        banner.className = 'live-incident-banner warning';
        if (iconEl) iconEl.textContent = '🌧️';
        if (titleEl) titleEl.textContent = '🌧️ ADVISORY: WET / SLIPPERY SURFACE DETECTED';
        if (descEl) descEl.textContent = 'Moisture sensor registers wet road surface. Speed advisory reduced to 50 km/h.';
        if (badgeEl) badgeEl.textContent = 'WET SURFACE';
        if (auditBtn) auditBtn.style.display = 'inline-block';
    } else {
        banner.className = 'live-incident-banner clear';
        if (iconEl) iconEl.textContent = '🛡️';
        if (titleEl) titleEl.textContent = 'CORRIDOR STATUS: NORMAL & CLEAR';
        if (descEl) descEl.textContent = 'Physical sensors and camera perception reporting all clear. No active collisions, stalled vehicles, or hazards.';
        if (badgeEl) badgeEl.textContent = 'ALL CLEAR';
        if (auditBtn) auditBtn.style.display = 'none';
    }
}

// Updates Top Header & Modal Status Badges
function updateHardwarePills() {
    // 1. ESP32 Pill
    const btnEsp32 = document.getElementById('btn-menu-esp32');
    const labelEsp32 = document.getElementById('label-esp32');
    const dotEsp32 = document.getElementById('dot-esp32');
    const chipStandbyEsp32 = document.getElementById('chip-standby-esp32');
    const cardStandbyEsp32 = document.getElementById('card-standby-esp32');
    const modalBadgeEsp32 = document.getElementById('modal-badge-esp32');

    if (state.esp32Connected) {
        if (btnEsp32) { btnEsp32.className = 'btn-hw-pill connected'; }
        if (labelEsp32) labelEsp32.textContent = 'ESP32: Connected';
        if (dotEsp32) dotEsp32.className = 'status-indicator-dot green';
        if (chipStandbyEsp32) { chipStandbyEsp32.textContent = 'CONNECTED'; chipStandbyEsp32.className = 'standby-chip connected'; }
        if (cardStandbyEsp32) cardStandbyEsp32.classList.add('connected');
        if (modalBadgeEsp32) { modalBadgeEsp32.textContent = 'CONNECTED'; modalBadgeEsp32.className = 'standby-chip connected'; }
    } else {
        if (btnEsp32) { btnEsp32.className = 'btn-hw-pill disconnected'; }
        if (labelEsp32) labelEsp32.textContent = 'ESP32: Disconnected';
        if (dotEsp32) dotEsp32.className = 'status-indicator-dot red';
        if (chipStandbyEsp32) { chipStandbyEsp32.textContent = 'DISCONNECTED'; chipStandbyEsp32.className = 'standby-chip disconnected'; }
        if (cardStandbyEsp32) cardStandbyEsp32.classList.remove('connected');
        if (modalBadgeEsp32) { modalBadgeEsp32.textContent = 'DISCONNECTED'; modalBadgeEsp32.className = 'standby-chip disconnected'; }
    }

    // 2. Master Gate Liveness Badge
    const masterBadge = document.getElementById('master-gate-badge');
    const masterLabel = document.getElementById('master-gate-label');
    if (masterBadge && masterLabel) {
        if (state.esp32Connected) {
            masterBadge.className = 'master-gate-badge armed';
            masterLabel.textContent = 'System armed';
        } else {
            masterBadge.className = 'master-gate-badge standby';
            masterLabel.textContent = 'Standby';
        }
    }
}

// Periodically syncs hardware connection telemetry with backend REST status
async function pollHardwareStatus() {
    try {
        const res = await fetch('/api/hardware/status');
        if (!res.ok) return;
        const data = await res.json();

        state.esp32Connected = Boolean(data.esp32?.connected);
        state.bothModulesConnected = state.esp32Connected;

        // Sync Modal 1 (ESP32) Controls
        const pcBleStatus = document.getElementById('pc-ble-status');
        const autoBleBtn = document.getElementById('btn-pc-ble-autoconnect');
        const disconnBleBtn = document.getElementById('btn-pc-ble-disconnect');
        const serialStatusEsp32 = document.getElementById('esp32-serial-status');
        const connSerialEsp32 = document.getElementById('btn-connect-esp32-serial');
        const disconnSerialEsp32 = document.getElementById('btn-disconnect-esp32-serial');

        if (data.esp32?.connected) {
            if (data.esp32.transport === 'BLE') {
                if (pcBleStatus) {
                    pcBleStatus.textContent = `Connected: ${data.esp32.device_id || 'SENTRAX-ESP32'} (${data.esp32.port_or_address}) [Live BLE Ingestion Active]`;
                    pcBleStatus.style.color = 'var(--accent-emerald)';
                }
                if (autoBleBtn) autoBleBtn.style.display = 'none';
                if (disconnBleBtn) disconnBleBtn.style.display = 'inline-block';
            } else if (data.esp32.transport === 'SERIAL') {
                if (serialStatusEsp32) {
                    serialStatusEsp32.textContent = `Connected on ${data.esp32.port_or_address}`;
                    serialStatusEsp32.style.color = 'var(--accent-emerald)';
                }
                if (connSerialEsp32) connSerialEsp32.style.display = 'none';
                if (disconnSerialEsp32) disconnSerialEsp32.style.display = 'inline-block';
            }
        } else {
            if (!state.webBluetoothDevice) {
                if (autoBleBtn) autoBleBtn.style.display = 'inline-block';
                if (disconnBleBtn) disconnBleBtn.style.display = 'none';
                if (connSerialEsp32) connSerialEsp32.style.display = 'inline-block';
                if (disconnSerialEsp32) disconnSerialEsp32.style.display = 'none';
            }
        }

        updateHardwarePills();

        if (state.esp32Connected) {
            const standbyOverlay = document.getElementById('hardware-standby-overlay');
            if (standbyOverlay) standbyOverlay.classList.add('hidden');
        } else {
            resetDashboardToStandby('Awaiting connection of ESP32 Core Controller.');
        }
    } catch (err) {
        // Backend temporarily busy
    }
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function prependEventTimeline(evt) {
    const timeline = document.getElementById('timeline-container');
    if (!timeline) return;

    const esc = window.SentraxUI ? window.SentraxUI.escapeHtml : (v) => v;
    const timeStr = new Date(evt.timestamp * 1000).toLocaleTimeString();
    const item = document.createElement('div');
    item.className = `timeline-item ${evt.severity}`;
    item.innerHTML = `
        <div>
            <div class="timeline-title">${esc(evt.title)}</div>
            <div class="timeline-desc">${esc(evt.description)}</div>
        </div>
        <div class="timeline-meta">
            <div class="timeline-time">${timeStr}</div>
            <span>${esc(evt.source)}</span>
        </div>
    `;

    timeline.insertBefore(item, timeline.firstChild);
    while (timeline.children.length > 25) {
        timeline.removeChild(timeline.lastChild);
    }
}

// Chart.js Setup
function initCharts() {
    const speedCtx = document.getElementById('chart-speed-history')?.getContext('2d');
    if (speedCtx) {
        state.charts.speed = new Chart(speedCtx, {
            type: 'line',
            data: {
                labels: Array(15).fill(''),
                datasets: [{
                    label: 'Measured Speed (km/h)',
                    data: Array(15).fill(0),
                    borderColor: '#8EA2E8',
                    backgroundColor: 'rgba(142, 162, 232, 0.10)',
                    fill: true,
                    tension: 0.3
                }, {
                    label: 'Recommended Speed (km/h)',
                    data: Array(15).fill(0),
                    borderColor: '#3FB68B',
                    borderDash: [5, 5],
                    fill: false
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, max: 100 }
                }
            }
        });
    }

    const riskCtx = document.getElementById('chart-risk-trend')?.getContext('2d');
    if (riskCtx) {
        state.charts.risk = new Chart(riskCtx, {
            type: 'line',
            data: {
                labels: Array(15).fill(''),
                datasets: [{
                    label: 'Road Risk Score (0-100)',
                    data: Array(15).fill(0),
                    borderColor: '#E5342B',
                    backgroundColor: 'rgba(229, 52, 43, 0.12)',
                    fill: true,
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, max: 100 }
                }
            }
        });
    }
}

function updateChartsStream(t) {
    if (state.charts.speed) {
        const d1 = state.charts.speed.data.datasets[0].data;
        const d2 = state.charts.speed.data.datasets[1].data;
        d1.push(t.measured_speed_kmh);
        d2.push(t.recommended_speed_kmh);
        if (d1.length > 15) { d1.shift(); d2.shift(); }
        state.charts.speed.update('none');
    }

    if (state.charts.risk) {
        const rdata = state.charts.risk.data.datasets[0].data;
        rdata.push(t.risk_score);
        if (rdata.length > 15) rdata.shift();
        state.charts.risk.update('none');
    }
}

// =====================================================================
// GOOGLE MAPS PLATFORM & IN-CAR NAVIGATION SYSTEM
// (Exact replica of mobile navigation interface with live hardware sensors)
// =====================================================================

// Source: Google Maps Platform Code Assist
let navState = {
    googleMap: null,
    leafletMap: null,
    isGoogleActive: false,
    googleKey: '',
    polylineLayer: null,
    markersLayer: null,
    currentLayerMode: 'dark', // 'dark' or 'satellite'
    routeData: null,
    startCoords: [17.6638, 77.9272],
    destCoords: [17.6596, 77.9248]
};

function initMap() {
    initNavigationMap();
}

function initNavigationMap() {
    const mapContainer = document.getElementById('sentrax-nav-map');
    if (!mapContainer) return;

    // 1. Start Live Clock on iPhone Status Bar
    function updateClock() {
        const now = new Date();
        let hours = now.getHours();
        let minutes = now.getMinutes();
        const str = `${hours}:${minutes < 10 ? '0' : ''}${minutes}`;
        const clockEl = document.getElementById('nav-live-clock');
        if (clockEl) clockEl.textContent = str;
    }
    updateClock();
    setInterval(updateClock, 30000);

    // 2. Setup Route Presets & Controls
    setupNavControls();

    // 3. Check for Google Maps API Key
    checkAndInitGoogleMaps();
}

async function checkAndInitGoogleMaps() {
    const mapContainer = document.getElementById('sentrax-nav-map');
    if (!mapContainer) return;

    // Check backend and localStorage for API key
    let apiKey = localStorage.getItem('sentrax_gmaps_key') || '';
    try {
        const cfgRes = await fetch('/api/maps/config');
        const cfg = await cfgRes.json();
        if (cfg.google_maps_configured && !apiKey) {
            apiKey = 'BACKEND_CONFIGURED';
        }
        if (cfg.origin_coords) navState.startCoords = cfg.origin_coords;
        if (cfg.dest_coords) navState.destCoords = cfg.dest_coords;
    } catch (e) {
        console.warn('Could not reach /api/maps/config:', e);
    }

    if (apiKey && apiKey !== 'BACKEND_CONFIGURED' && apiKey.length > 10) {
        loadGoogleMapsScript(apiKey);
    } else {
        // Fall back seamlessly to high-fidelity dark navigation map
        initLeafletNavMap();
        loadRouteHealth();
    }
}

function loadGoogleMapsScript(apiKey) {
    if (window.google && window.google.maps) {
        initGoogleMapInstance(apiKey);
        return;
    }

    const script = document.createElement('script');
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&v=weekly&libraries=places,routes,geometry`;
    script.async = true;
    script.defer = true;
    script.onload = () => {
        console.log('[Google Maps] Maps JavaScript API loaded successfully');
        initGoogleMapInstance(apiKey);
    };
    script.onerror = () => {
        console.warn('[Google Maps] Failed to load with provided key, using interactive dark fallback');
        initLeafletNavMap();
        loadRouteHealth();
    };
    document.head.appendChild(script);
}

function initGoogleMapInstance(apiKey) {
    const mapContainer = document.getElementById('sentrax-nav-map');
    if (!mapContainer || !window.google || !window.google.maps) return;

    try {
        // Clear previous map if any
        mapContainer.innerHTML = '';

        const mapOptions = {
            center: { lat: 17.6618, lng: 77.9260 },
            zoom: 17,
            mapId: 'DEMO_MAP_ID', // Mandatory for AdvancedMarkerElement
            disableDefaultUI: true,
            zoomControl: false,
            mapTypeControl: false,
            streetViewControl: false,
            fullscreenControl: false,
            // Mandatory Google Maps Platform usage attribution
            internalUsageAttributionIds: ['gmp_git_agentskills_v1'],
            styles: [
                { elementType: "geometry", stylers: [{ color: "#161b26" }] },
                { elementType: "labels.text.stroke", stylers: [{ color: "#161b26" }] },
                { elementType: "labels.text.fill", stylers: [{ color: "#748398" }] },
                { featureType: "administrative.locality", elementType: "labels.text.fill", stylers: [{ color: "#9aa9be" }] },
                { featureType: "poi", elementType: "labels.text.fill", stylers: [{ color: "#8a99ae" }] },
                { featureType: "poi.park", elementType: "geometry", stylers: [{ color: "#13212f" }] },
                { featureType: "road", elementType: "geometry", stylers: [{ color: "#232d3f" }] },
                { featureType: "road", elementType: "geometry.stroke", stylers: [{ color: "#1b2331" }] },
                { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#2d3a52" }] },
                { featureType: "transit", elementType: "geometry", stylers: [{ color: "#1c2433" }] },
                { featureType: "water", elementType: "geometry", stylers: [{ color: "#0d131c" }] }
            ]
        };

        navState.googleMap = new google.maps.Map(mapContainer, mapOptions);
        navState.isGoogleActive = true;
        state.map = navState.googleMap;

        const badge = document.getElementById('nav-gmaps-badge');
        if (badge) {
            badge.textContent = 'Google Maps Platform Connected';
            badge.style.background = 'rgba(16, 185, 129, 0.2)';
            badge.style.color = '#34d399';
            badge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
        }

        const statusText = document.getElementById('nav-gmaps-key-status');
        if (statusText) {
            statusText.textContent = 'Photorealistic Google Maps JavaScript API active with dark theme.';
            statusText.style.color = '#34d399';
        }

        loadRouteHealth();
    } catch (err) {
        console.error('Error initializing Google Maps:', err);
        initLeafletNavMap();
        loadRouteHealth();
    }
}

function initLeafletNavMap() {
    const mapContainer = document.getElementById('sentrax-nav-map');
    if (!mapContainer || typeof L === 'undefined') return;

    if (navState.leafletMap) {
        navState.leafletMap.remove();
        navState.leafletMap = null;
    }

    mapContainer.innerHTML = '';
    navState.leafletMap = L.map('sentrax-nav-map', {
        zoomControl: false,
        attributionControl: false
    }).setView([17.6618, 77.9260], 17);

    // Dark midnight navigation tiles matching reference design
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        subdomains: 'abcd',
        maxZoom: 20
    }).addTo(navState.leafletMap);

    state.map = navState.leafletMap;
    navState.isGoogleActive = false;
}

function setupNavControls() {
    // 1. Swap Locations button
    const btnSwap = document.getElementById('btn-swap-locations');
    if (btnSwap) {
        btnSwap.addEventListener('click', () => {
            const originInput = document.getElementById('nav-input-origin');
            const destInput = document.getElementById('nav-input-dest');
            if (originInput && destInput) {
                const tmp = originInput.value;
                originInput.value = destInput.value;
                destInput.value = tmp;

                const tmpCoords = navState.startCoords;
                navState.startCoords = navState.destCoords;
                navState.destCoords = tmpCoords;

                loadRouteHealth();
            }
        });
    }

    // 2. Recompute Route button
    const btnRecompute = document.getElementById('btn-recompute-route');
    if (btnRecompute) {
        btnRecompute.addEventListener('click', () => {
            loadRouteHealth();
        });
    }

    // 3. Quick Route Presets
    document.querySelectorAll('.nav-preset-pill').forEach(pill => {
        pill.addEventListener('click', (e) => {
            document.querySelectorAll('.nav-preset-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');

            const preset = pill.getAttribute('data-preset');
            const originInput = document.getElementById('nav-input-origin');
            const destInput = document.getElementById('nav-input-dest');

            if (preset === 'woxsen-campus') {
                if (originInput) originInput.value = 'Woxsen North Roundabout';
                if (destInput) destInput.value = 'Woxsen Hostels & Blue Embers';
                navState.startCoords = [17.6638, 77.9272];
                navState.destCoords = [17.6596, 77.9248];
            } else if (preset === 'woxsen-gate') {
                if (originInput) originInput.value = 'Woxsen Main Entrance';
                if (destInput) destInput.value = 'Academic Block Spine';
                navState.startCoords = [17.6582, 77.9268];
                navState.destCoords = [17.6620, 77.9270];
            } else if (preset === 'corridor-test') {
                if (originInput) originInput.value = 'Sensor Track (US1 / Entry)';
                if (destInput) destInput.value = 'Sensor Track (IR4 / Exit)';
                navState.startCoords = [17.6640, 77.9274];
                navState.destCoords = [17.6590, 77.9245];
            }
            loadRouteHealth();
        });
    });

    // 4. Floating Action Buttons (Layers, Center, Compass)
    const btnLayers = document.getElementById('btn-map-layers');
    if (btnLayers) {
        btnLayers.addEventListener('click', () => {
            if (navState.isGoogleActive && navState.googleMap) {
                const currentType = navState.googleMap.getMapTypeId();
                const nextType = (currentType === 'satellite') ? 'roadmap' : 'satellite';
                navState.googleMap.setMapTypeId(nextType);
            } else if (navState.leafletMap) {
                // Toggle between dark and standard OSM
                if (navState.currentLayerMode === 'dark') {
                    navState.currentLayerMode = 'satellite';
                    if (navState.satelliteTile) navState.leafletMap.removeLayer(navState.satelliteTile);
                    navState.satelliteTile = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19 }).addTo(navState.leafletMap);
                } else {
                    navState.currentLayerMode = 'dark';
                    if (navState.satelliteTile) {
                        navState.leafletMap.removeLayer(navState.satelliteTile);
                        navState.satelliteTile = null;
                    }
                }
            }
        });
    }

    const btnCar = document.getElementById('btn-map-car');
    if (btnCar) {
        btnCar.addEventListener('click', () => {
            const centerPt = navState.destCoords;
            if (navState.isGoogleActive && navState.googleMap) {
                navState.googleMap.panTo({ lat: centerPt[0], lng: centerPt[1] });
                navState.googleMap.setZoom(18);
            } else if (navState.leafletMap) {
                navState.leafletMap.setView(centerPt, 18, { animate: true });
            }
        });
    }

    const btnCompass = document.getElementById('btn-map-compass');
    if (btnCompass) {
        btnCompass.addEventListener('click', () => {
            if (navState.isGoogleActive && navState.googleMap && navState.bounds) {
                navState.googleMap.fitBounds(navState.bounds);
            } else if (navState.leafletMap && navState.polylineLayer) {
                navState.leafletMap.fitBounds(navState.polylineLayer.getBounds(), { padding: [40, 40] });
            }
        });
    }

    // 5. Drawer Toggle & Close
    const btnClose = document.getElementById('btn-close-directions');
    const drawerHandle = document.getElementById('nav-drawer-toggle');
    const drawer = document.getElementById('nav-bottom-drawer');
    if (drawer) {
        const toggleDrawer = () => {
            drawer.classList.toggle('minimized');
            if (drawer.classList.contains('minimized')) {
                drawer.style.maxHeight = '75px';
            } else {
                drawer.style.maxHeight = '52%';
            }
        };
        if (btnClose) btnClose.addEventListener('click', toggleDrawer);
        if (drawerHandle) drawerHandle.addEventListener('click', toggleDrawer);
    }

    // 6. Cockpit View Toggle
    const btnExpand = document.getElementById('btn-toggle-expanded-view');
    const layoutWrapper = document.getElementById('nav-layout-wrapper');
    if (btnExpand && layoutWrapper) {
        btnExpand.addEventListener('click', () => {
            layoutWrapper.classList.toggle('expanded-mode');
            btnExpand.textContent = layoutWrapper.classList.contains('expanded-mode') ? 'Show Phone Frame' : 'Toggle Cockpit View';
            setTimeout(() => {
                if (navState.isGoogleActive && navState.googleMap) {
                    google.maps.event.trigger(navState.googleMap, 'resize');
                } else if (navState.leafletMap) {
                    navState.leafletMap.invalidateSize();
                }
            }, 300);
        });
    }

    // 7. Save Google Maps Key button
    const btnSaveKey = document.getElementById('btn-save-gmaps-key');
    const keyInput = document.getElementById('nav-gmaps-key-input');
    if (btnSaveKey && keyInput) {
        btnSaveKey.addEventListener('click', async () => {
            const key = keyInput.value.trim();
            if (!key) return;

            localStorage.setItem('sentrax_gmaps_key', key);
            try {
                await fetch('/api/maps/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key })
                });
            } catch (e) {
                console.warn('Could not post key to /api/maps/config:', e);
            }

            loadGoogleMapsScript(key);
        });
    }
}

async function loadRouteHealth() {
    const origin = document.getElementById('nav-input-origin')?.value || 'Woxsen North Roundabout';
    const destination = document.getElementById('nav-input-dest')?.value || 'Woxsen Hostels & Blue Embers';

    try {
        const res = await fetch('/api/route-health', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                origin,
                destination,
                origin_lat: navState.startCoords[0],
                origin_lng: navState.startCoords[1],
                dest_lat: navState.destCoords[0],
                dest_lng: navState.destCoords[1]
            })
        });
        const data = await res.json();
        navState.routeData = data;
        renderRouteOnMap(data);
    } catch (err) {
        console.error('Failed to load route health:', err);
    }
}

function renderRouteOnMap(routeData) {
    if (!routeData) return;

    const coords = routeData.route_polyline_points || [
        [17.6644, 77.9273],
        [17.6636, 77.9272],
        [17.6620, 77.9271],
        [17.6607, 77.9255],
        [17.6597, 77.9249],
        [17.6594, 77.9248]
    ];

    // ==========================================
    // RENDER ON GOOGLE MAPS PLATFORM
    // ==========================================
    if (navState.isGoogleActive && navState.googleMap && window.google) {
        // Clear old overlays
        if (navState.googlePolyline) navState.googlePolyline.setMap(null);
        if (navState.googleMarkers) {
            navState.googleMarkers.forEach(m => m.setMap(null));
        }
        navState.googleMarkers = [];

        const gCoords = coords.map(pt => ({ lat: pt[0], lng: pt[1] }));

        // Vibrant electric blue polyline with white directional chevrons matching reference
        navState.googlePolyline = new google.maps.Polyline({
            path: gCoords,
            geodesic: true,
            strokeColor: '#2F80ED',
            strokeOpacity: 0.95,
            strokeWeight: 7,
            icons: [{
                icon: {
                    path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
                    scale: 2.2,
                    strokeColor: '#FFFFFF',
                    fillColor: '#FFFFFF',
                    fillOpacity: 0.9
                },
                offset: '20%',
                repeat: '65px'
            }]
        });
        navState.googlePolyline.setMap(navState.googleMap);

        // Fit Bounds
        const bounds = new google.maps.LatLngBounds();
        gCoords.forEach(pt => bounds.extend(pt));
        navState.bounds = bounds;
        navState.googleMap.fitBounds(bounds);

        // Origin Marker (Start)
        const startMarker = new google.maps.Marker({
            position: gCoords[0],
            map: navState.googleMap,
            title: routeData.origin_name,
            icon: {
                path: google.maps.SymbolPath.CIRCLE,
                scale: 8,
                fillColor: '#10B981',
                fillOpacity: 1,
                strokeColor: '#FFFFFF',
                strokeWeight: 2.5
            }
        });
        navState.googleMarkers.push(startMarker);

        // Destination Marker (End)
        const endMarker = new google.maps.Marker({
            position: gCoords[gCoords.length - 1],
            map: navState.googleMap,
            title: routeData.destination_name,
            icon: {
                path: google.maps.SymbolPath.CIRCLE,
                scale: 9,
                fillColor: '#EF4444',
                fillOpacity: 1,
                strokeColor: '#FFFFFF',
                strokeWeight: 3
            }
        });
        navState.googleMarkers.push(endMarker);
    }

    // ==========================================
    // RENDER ON LEAFLET DARK VECTOR FALLBACK
    // ==========================================
    else if (navState.leafletMap) {
        if (navState.polylineLayer) {
            navState.leafletMap.removeLayer(navState.polylineLayer);
        }
        if (navState.markersLayer) {
            navState.leafletMap.removeLayer(navState.markersLayer);
        }

        // Draw glowing blue route polyline with matching aesthetic
        navState.polylineLayer = L.polyline(coords, {
            color: '#2F80ED',
            weight: 7,
            opacity: 0.95,
            lineJoin: 'round',
            lineCap: 'round'
        }).addTo(navState.leafletMap);

        navState.markersLayer = L.featureGroup().addTo(navState.leafletMap);

        // Start Beacon Marker (Green)
        const startIcon = L.divIcon({
            className: 'custom-beacon',
            html: `<div style="width:16px;height:16px;border-radius:50%;background:#10B981;border:2.5px solid #FFFFFF;box-shadow:0 0 12px #10B981;"></div>`,
            iconSize: [16, 16],
            iconAnchor: [8, 8]
        });
        L.marker(coords[0], { icon: startIcon }).addTo(navState.markersLayer);

        // End Beacon Marker (Red)
        const endIcon = L.divIcon({
            className: 'custom-beacon',
            html: `<div style="width:18px;height:18px;border-radius:50%;background:#EF4444;border:3px solid #FFFFFF;box-shadow:0 0 14px #EF4444;"></div>`,
            iconSize: [18, 18],
            iconAnchor: [9, 9]
        });
        L.marker(coords[coords.length - 1], { icon: endIcon }).addTo(navState.markersLayer);

        // Landmark labels matching screenshot: Woxsen Hostels & Blue Embers
        const hostelIcon = L.divIcon({
            className: 'poi-pill',
            html: `<div style="background:rgba(26,31,44,0.9);color:#e2e8f0;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;border:1px solid rgba(255,255,255,0.15);white-space:nowrap;display:flex;align-items:center;gap:4px;"><span style="color:#a855f7;">🛏️</span> Woxsen Hostels</div>`,
            iconAnchor: [45, 10]
        });
        L.marker([17.6607, 77.9255], { icon: hostelIcon }).addTo(navState.markersLayer);

        const emberIcon = L.divIcon({
            className: 'poi-pill',
            html: `<div style="background:rgba(26,31,44,0.9);color:#e2e8f0;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;border:1px solid rgba(255,255,255,0.15);white-space:nowrap;display:flex;align-items:center;gap:4px;"><span style="color:#f97316;">🍽️</span> Blue Embers</div>`,
            iconAnchor: [45, 10]
        });
        L.marker([17.6598, 77.9249], { icon: emberIcon }).addTo(navState.markersLayer);

        navState.leafletMap.fitBounds(navState.polylineLayer.getBounds(), { padding: [35, 35] });
    }

    // ==========================================
    // UPDATE DRAWER METRIC CARDS
    // ==========================================
    const healthScore = routeData.overall_health_score !== undefined ? routeData.overall_health_score : 68;
    const healthBand = routeData.overall_health_band || 'Fair';
    setText('nav-road-health-val', `${healthScore}% (${healthBand})`);

    const healthBar = document.getElementById('nav-road-health-bar');
    if (healthBar) {
        healthBar.style.width = `${healthScore}%`;
        if (healthScore >= 80) {
            healthBar.style.background = 'linear-gradient(90deg, #10B981, #34D399)';
        } else if (healthScore >= 60) {
            healthBar.style.background = 'linear-gradient(90deg, #F59E0B, #EAB308)';
        } else {
            healthBar.style.background = 'linear-gradient(90deg, #EF4444, #F87171)';
        }
    }

    const recSpeed = Math.round(routeData.recommended_speed_kmh || 80);
    setText('nav-sign-limit-val', recSpeed);
    setText('nav-speed-rec-badge', `LIMIT: ${recSpeed} km/h`);

    setText('nav-road-anatomy-val', routeData.road_anatomy_text || 'Surface: Asphalt | Lanes: 2 | Shoulder: Concrete');

    if (routeData.measured_speed_kmh !== undefined) {
        setText('nav-current-speed', routeData.measured_speed_kmh.toFixed(1));
    }

    setText('nav-route-dist-eta', `${routeData.total_distance_km} km | ${routeData.estimated_duration_mins} mins`);

    if (routeData.weather_temp_c !== undefined) {
        setText('nav-weather-temp', Math.round(routeData.weather_temp_c));
    }
    if (routeData.weather_aqi !== undefined) {
        setText('nav-weather-aqi', routeData.weather_aqi);
    }
}

// Live telemetry link from hardware (WebSocket event)
function updateNavigationScreenTelemetry(t) {
    if (!t) return;

    // 1. Live Weather Pill Temperature (DHT11 sensor)
    if (t.temperature_c !== undefined && !isNaN(t.temperature_c)) {
        setText('nav-weather-temp', Math.round(t.temperature_c));
    }

    // 2. Measured Vehicle Speed (Ultrasonic Sensors)
    if (t.measured_speed_kmh !== undefined) {
        setText('nav-current-speed', t.measured_speed_kmh.toFixed(1));
    }

    // 3. Recommended Speed Limit & Anatomy Sign
    const recSpeed = Math.round(t.recommended_speed_kmh || 80);
    setText('nav-sign-limit-val', recSpeed);
    setText('nav-speed-rec-badge', `LIMIT: ${recSpeed} km/h`);

    // 4. Dynamic Road Health computation from live hardware sensors
    let health = 84;
    let band = 'Good';
    let isWet = (t.road_condition === 'WET' || (t.moisture_raw !== undefined && t.moisture_raw < 2000));
    let isCongested = (t.traffic_level === 'CONGESTED');
    let isStalled = Boolean(t.stalled_vehicle);
    let isCollision = Boolean(t.collision);

    let anatomy = 'Surface: Asphalt | Lanes: 2 | Shoulder: Concrete';

    if (isCollision) {
        health = 28;
        band = 'Critical';
        anatomy = 'Surface: Impact Zone | Obstruction Ahead';
    } else if (isStalled) {
        health = 52;
        band = 'Poor';
        anatomy = 'Surface: Asphalt | Stationary Vehicle on Lane';
    } else if (isWet) {
        health = 68; // Exactly matches reference image: 68% (Fair)
        band = 'Fair';
        anatomy = 'Surface: Wet Asphalt | Lanes: 2 | Low Friction';
    } else if (isCongested) {
        health = 64;
        band = 'Fair';
        anatomy = 'Surface: Asphalt | Dense Traffic Queue';
    } else {
        health = 88;
        band = 'Good';
        anatomy = 'Surface: Asphalt | Lanes: 2 | Shoulder: Concrete';
    }

    setText('nav-road-health-val', `${health}% (${band})`);
    const bar = document.getElementById('nav-road-health-bar');
    if (bar) {
        bar.style.width = `${health}%`;
        if (health >= 80) {
            bar.style.background = 'linear-gradient(90deg, #10B981, #34D399)';
        } else if (health >= 60) {
            bar.style.background = 'linear-gradient(90deg, #F59E0B, #EAB308)';
        } else {
            bar.style.background = 'linear-gradient(90deg, #EF4444, #F87171)';
        }
    }

    setText('nav-road-anatomy-val', anatomy);
}

// Initial Data Fetch
async function fetchInitialData() {
    try {
        const [devicesRes, eventsRes] = await Promise.all([
            fetch('/api/devices'),
            fetch('/api/events?limit=20')
        ]);

        const devices = await devicesRes.json();
        renderDevicesUI(devices);

        const events = await eventsRes.json();
        events.forEach(prependEventTimeline);
    } catch (err) {
        console.error('Initial data fetch error:', err);
    }
}

function renderDevicesUI(devices) {
    const container = document.getElementById('device-cards-container');
    if (!container) return;

    const esc = window.SentraxUI ? window.SentraxUI.escapeHtml : (v) => v;
    container.innerHTML = devices.map(d => {
        const live = d.connection_state === 'CONNECTED';
        return `
        <div class="card device-card">
            <div class="card-head">
                <div class="device-id">
                    <span class="sensor-icon"><i class="ph ph-cpu"></i></span>
                    <div>
                        <div class="card-title">${esc(d.display_name)}</div>
                        <div class="card-sub mono">${esc(d.device_id)}</div>
                    </div>
                </div>
                <span class="live-badge ${live ? 'live' : 'simulated'}">${esc(d.connection_state)}</span>
            </div>
            <dl class="device-meta">
                <div><dt>Port / address</dt><dd>${esc(d.port_or_address || 'BLE / COM')}</dd></div>
                <div><dt>RSSI</dt><dd>${esc(d.rssi || -60)} dBm</dd></div>
                <div><dt>Firmware</dt><dd>${esc(d.firmware_version)}</dd></div>
                <div><dt>Last event</dt><dd>${esc(d.last_event || 'NORMAL')}</dd></div>
            </dl>
        </div>`;
    }).join('');
}

// =====================================================================
// DEDICATED HARDWARE PAIRING MENU (ESP32 CORE CONTROLLER)
// =====================================================================
function initHardwareModals() {
    refreshCOMPorts('select-esp32-com-port');

    // -------------------------------------------------------------
    // ESP32 CORE GATEWAY CONTROLS
    // -------------------------------------------------------------
    const modalEsp32 = document.getElementById('modal-esp32-pairing');
    const openBtnEsp32 = document.getElementById('btn-menu-esp32');
    const openStandbyBtnEsp32 = document.getElementById('btn-open-esp32-modal');
    const closeBtnEsp32 = document.getElementById('btn-close-esp32-modal');
    const closeFooterBtnEsp32 = document.getElementById('btn-close-esp32-footer');

    const openEsp32 = () => {
        if (modalEsp32) {
            modalEsp32.classList.add('open');
            refreshCOMPorts('select-esp32-com-port');
            const selectBle = document.getElementById('select-pc-ble-device');
            if (selectBle && selectBle.children.length <= 1) {
                scanPCBluetoothDevices();
            }
        }
    };
    const closeEsp32 = () => modalEsp32?.classList.remove('open');

    if (openBtnEsp32) openBtnEsp32.addEventListener('click', openEsp32);
    if (openStandbyBtnEsp32) openStandbyBtnEsp32.addEventListener('click', openEsp32);
    if (closeBtnEsp32) closeBtnEsp32.addEventListener('click', closeEsp32);
    if (closeFooterBtnEsp32) closeFooterBtnEsp32.addEventListener('click', closeEsp32);

    // ESP32 Windows PC Bluetooth Gateway
    const autoBleBtn = document.getElementById('btn-pc-ble-autoconnect');
    const scanBleBtn = document.getElementById('btn-scan-pc-ble');
    const connectSelBleBtn = document.getElementById('btn-connect-pc-ble-selected');
    const disconnectBleBtn = document.getElementById('btn-pc-ble-disconnect');

    if (autoBleBtn) autoBleBtn.addEventListener('click', () => connectPCBluetooth(null));
    if (scanBleBtn) scanBleBtn.addEventListener('click', scanPCBluetoothDevices);
    if (connectSelBleBtn) connectSelBleBtn.addEventListener('click', () => {
        const sel = document.getElementById('select-pc-ble-device');
        connectPCBluetooth(sel ? sel.value : null);
    });
    if (disconnectBleBtn) disconnectBleBtn.addEventListener('click', disconnectPCBluetooth);

    // ESP32 Web Bluetooth
    const pairBtBtn = document.getElementById('btn-web-ble-esp32-pair');
    const disconnectBtBtn = document.getElementById('btn-web-ble-esp32-disconnect');
    if (pairBtBtn) pairBtBtn.addEventListener('click', pairWebBluetooth);
    if (disconnectBtBtn) disconnectBtBtn.addEventListener('click', disconnectWebBluetooth);

    // ESP32 Serial COM
    const refreshPortsBtnEsp32 = document.getElementById('btn-refresh-esp32-ports');
    const connectSerialBtnEsp32 = document.getElementById('btn-connect-esp32-serial');
    const disconnectSerialBtnEsp32 = document.getElementById('btn-disconnect-esp32-serial');

    if (refreshPortsBtnEsp32) refreshPortsBtnEsp32.addEventListener('click', () => refreshCOMPorts('select-esp32-com-port'));
    if (connectSerialBtnEsp32) connectSerialBtnEsp32.addEventListener('click', connectESP32Serial);
    if (disconnectSerialBtnEsp32) disconnectSerialBtnEsp32.addEventListener('click', disconnectESP32Serial);
}

// -------------------------------------------------------------
// ESP32 Windows PC Bluetooth Gateway Implementation
// -------------------------------------------------------------
async function scanPCBluetoothDevices() {
    const statusEl = document.getElementById('pc-ble-status');
    const selectEl = document.getElementById('select-pc-ble-device');
    const scanBtn = document.getElementById('btn-scan-pc-ble');

    if (scanBtn) {
        scanBtn.disabled = true;
        scanBtn.textContent = 'Scanning';
    }
    if (statusEl) {
        statusEl.textContent = 'Scanning Windows Bluetooth adapter for nearby BLE devices (3.5s)...';
        statusEl.style.color = 'var(--accent-cyan)';
    }

    try {
        const res = await fetch('/api/ble/scan');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const devices = await res.json();

        if (selectEl) {
            selectEl.innerHTML = '';
            if (!devices || devices.length === 0) {
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = 'No Bluetooth devices detected in range.';
                selectEl.appendChild(opt);
                if (statusEl) {
                    statusEl.textContent = 'No devices found. Ensure ESP32 is powered on and within range.';
                    statusEl.style.color = 'var(--text-muted)';
                }
            } else {
                let sentraxOption = null;
                devices.forEach(d => {
                    const opt = document.createElement('option');
                    opt.value = d.address;
                    const isSentrax = d.is_sentrax || (d.name && d.name.toUpperCase().includes('SENTRAX'));
                    opt.textContent = `${d.name} (${d.address}) [RSSI: ${d.rssi} dBm]${isSentrax ? ' ★ SENTRAX' : ''}`;
                    if (isSentrax) {
                        opt.style.fontWeight = 'bold';
                        opt.style.color = 'var(--accent-emerald)';
                        if (!sentraxOption) sentraxOption = opt;
                    }
                    selectEl.appendChild(opt);
                });

                if (sentraxOption) {
                    sentraxOption.selected = true;
                    if (statusEl) {
                        statusEl.textContent = `Found ${devices.length} devices. SENTRAX-ESP32 detected and ready!`;
                        statusEl.style.color = 'var(--accent-emerald)';
                    }
                } else if (statusEl) {
                    statusEl.textContent = `Found ${devices.length} Bluetooth devices.`;
                    statusEl.style.color = 'var(--text-secondary)';
                }
            }
        }
    } catch (err) {
        console.error('BLE Scan Error:', err);
        if (statusEl) {
            statusEl.textContent = `Scan failed: ${err.message}. Ensure Windows Bluetooth is turned ON.`;
            statusEl.style.color = 'var(--accent-rose)';
        }
    } finally {
        if (scanBtn) {
            scanBtn.disabled = false;
            scanBtn.textContent = 'Scan';
        }
    }
}

async function connectPCBluetooth(targetAddress = null) {
    const statusEl = document.getElementById('pc-ble-status');
    const autoBtn = document.getElementById('btn-pc-ble-autoconnect');
    const connSelBtn = document.getElementById('btn-connect-pc-ble-selected');
    const disconnBtn = document.getElementById('btn-pc-ble-disconnect');

    if (autoBtn) autoBtn.disabled = true;
    if (connSelBtn) connSelBtn.disabled = true;

    if (statusEl) {
        statusEl.textContent = targetAddress
            ? `Connecting to BLE address ${targetAddress} via Windows radio...`
            : 'Scanning and auto-connecting to SENTRAX-ESP32 via Windows Bluetooth...';
        statusEl.style.color = 'var(--accent-cyan)';
    }

    try {
        const bodyPayload = targetAddress ? { address: targetAddress } : {};
        const res = await fetch('/api/ble/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyPayload)
        });

        const data = await res.json();
        if (res.ok && data.status === 'connected') {
            if (statusEl) {
                statusEl.textContent = `Connected to ${data.device || 'SENTRAX-ESP32'} (${data.address})! Subscribed to live GATT.`;
                statusEl.style.color = 'var(--accent-emerald)';
            }
            if (autoBtn) autoBtn.style.display = 'none';
            if (disconnBtn) disconnBtn.style.display = 'inline-block';

            state.esp32Connected = true;
            updateHardwarePills();
            pollHardwareStatus();
            fetchInitialData();
        } else {
            throw new Error(data.detail || 'Connection refused or timed out');
        }
    } catch (err) {
        console.error('PC BLE Connect Error:', err);
        if (statusEl) {
            statusEl.textContent = `Connection failed: ${err.message}`;
            statusEl.style.color = 'var(--accent-rose)';
        }
    } finally {
        if (autoBtn) autoBtn.disabled = false;
        if (connSelBtn) connSelBtn.disabled = false;
    }
}

async function disconnectPCBluetooth() {
    const statusEl = document.getElementById('pc-ble-status');
    const autoBtn = document.getElementById('btn-pc-ble-autoconnect');
    const disconnBtn = document.getElementById('btn-pc-ble-disconnect');

    try {
        await fetch('/api/ble/disconnect', { method: 'POST' });
        if (statusEl) {
            statusEl.textContent = 'Disconnected from PC Bluetooth.';
            statusEl.style.color = 'var(--text-muted)';
        }
        if (autoBtn) autoBtn.style.display = 'inline-block';
        if (disconnBtn) disconnBtn.style.display = 'none';

        state.esp32Connected = false;
        state.bothModulesConnected = false;
        updateHardwarePills();
        pollHardwareStatus();
        resetDashboardToStandby('ESP32 Bluetooth connection disconnected.');
    } catch (err) {
        console.error('PC BLE Disconnect Error:', err);
    }
}

// -------------------------------------------------------------
// ESP32 Web Bluetooth Implementation
// -------------------------------------------------------------
async function pairWebBluetooth() {
    const statusEl = document.getElementById('web-ble-esp32-status');
    const pairBtn = document.getElementById('btn-web-ble-esp32-pair');
    const disconnectBtn = document.getElementById('btn-web-ble-esp32-disconnect');

    if (!navigator.bluetooth) {
        if (statusEl) {
            statusEl.innerHTML = `<span style="color:var(--accent-rose);">Web Bluetooth is unavailable in this browser.</span><br><span style="font-size:11px;color:var(--text-muted)">Please use Google Chrome or Microsoft Edge on <b>http://localhost:8000</b>.<br>You can also connect via <b>Option B (Bluetooth / USB COM Port)</b> below!</span>`;
        }
        return;
    }

    try {
        if (statusEl) statusEl.textContent = 'Requesting Bluetooth device (SENTRAX-ESP32)...';

        let device;
        try {
            device = await navigator.bluetooth.requestDevice({
                filters: [
                    { name: 'SENTRAX-ESP32' },
                    { namePrefix: 'SENTRAX' },
                    { namePrefix: 'SentraX' },
                    { namePrefix: 'ESP32' },
                    { services: [SENTRAX_SERVICE_UUID] }
                ],
                optionalServices: [SENTRAX_SERVICE_UUID]
            });
        } catch (filterErr) {
            if (filterErr.name === 'NotFoundError' && (filterErr.message.includes('User cancelled') || filterErr.message.includes('cancelled'))) {
                throw filterErr;
            }
            console.warn('Filtered device request fallback to acceptAllDevices:', filterErr);
            device = await navigator.bluetooth.requestDevice({
                acceptAllDevices: true,
                optionalServices: [SENTRAX_SERVICE_UUID]
            });
        }

        state.webBluetoothDevice = device;
        device.addEventListener('gattserverdisconnected', onWebBluetoothDisconnected);

        // Windows GATT Server Connection with Automatic Retry Loop
        let server = null;
        let lastConnectErr = null;
        for (let attempt = 1; attempt <= 3; attempt++) {
            try {
                if (statusEl) statusEl.textContent = `Connecting to ${device.name || 'SENTRAX-ESP32'} (Attempt ${attempt}/3)...`;
                server = await device.gatt.connect();
                if (server && server.connected) break;
            } catch (connErr) {
                lastConnectErr = connErr;
                console.warn(`[SentraX BLE] GATT connect attempt ${attempt} failed:`, connErr);
                if (attempt < 3) {
                    await new Promise(r => setTimeout(r, 650));
                }
            }
        }

        if (!server || !server.connected) {
            throw lastConnectErr || new Error("Could not establish GATT connection to ESP32.");
        }

        state.webBluetoothServer = server;

        if (statusEl) statusEl.textContent = 'Discovering SentraX GATT Services...';
        const service = await server.getPrimaryService(SENTRAX_SERVICE_UUID);

        // Telemetry characteristic notifications
        const charTelemetry = await service.getCharacteristic(CHAR_TELEMETRY_UUID);
        await charTelemetry.startNotifications();
        charTelemetry.addEventListener('characteristicvaluechanged', handleWebBluetoothTelemetryPacket);

        // Events characteristic notifications
        try {
            const charEvents = await service.getCharacteristic(CHAR_EVENTS_UUID);
            await charEvents.startNotifications();
            charEvents.addEventListener('characteristicvaluechanged', handleWebBluetoothEventPacket);
        } catch (e) {
            console.warn('Events characteristic optional subscribe skipped:', e);
        }

        // Commands characteristic for bidirectional writes
        try {
            state.webBluetoothCharCommands = await service.getCharacteristic(CHAR_COMMANDS_UUID);
            console.log('[SentraX BLE] Command GATT characteristic ready for bidirectional control.');
        } catch (e) {
            console.warn('Commands characteristic optional subscribe skipped:', e);
        }

        state.esp32Connected = true;
        state.lastPacketTime = Date.now();
        if (statusEl) {
            statusEl.textContent = `Connected to ${device.name || 'SENTRAX-ESP32'} via Web Bluetooth!`;
            statusEl.style.color = 'var(--accent-emerald)';
        }
        if (pairBtn) pairBtn.style.display = 'none';
        if (disconnectBtn) disconnectBtn.style.display = 'inline-block';

        updateHardwarePills();
        fetchInitialData();
    } catch (err) {
        console.error('Web Bluetooth Pairing Error:', err);
        if (statusEl) {
            if (err.name === 'NotFoundError') {
                statusEl.textContent = 'Pairing cancelled or device not selected.';
                statusEl.style.color = 'var(--text-muted)';
            } else if (err.message && err.message.toLowerCase().includes('globally disabled')) {
                statusEl.innerHTML = `<span style="color:var(--accent-rose);">Web Bluetooth is disabled in your Windows browser.</span><div style="font-size:11px; color:var(--text-secondary); margin-top:4px; line-height:1.4;">To enable: Open <code>chrome://flags/#enable-web-bluetooth-new-permissions-backend</code> in Chrome/Edge, set to <b>Enabled</b>, and relaunch.<br>Or connect via <b>Option B (COM Port)</b> below with Arduino IDE Serial Monitor closed.</div>`;
            } else if (err.name === 'NetworkError' || (err.message && err.message.toLowerCase().includes('connection failed'))) {
                statusEl.innerHTML = `<span style="color:var(--accent-rose);">GATT Connection Error: Windows Bluetooth radio rejected connection.</span><div style="font-size:11px; color:var(--text-secondary); margin-top:5px; line-height:1.4;"><b>Fix on Windows:</b><br>1. If <b>SENTRAX-ESP32</b> is paired in Windows Settings &rarr; <i>Bluetooth & devices</i>, click <b>Remove device</b> so Chrome has exclusive GATT access.<br>2. Ensure ESP32 is powered on (blue/red LED lit).<br>3. Or use <b>Option B (PC Bluetooth / Serial Port)</b> below!</div>`;
            } else {
                statusEl.textContent = `Pairing failed: ${err.message}`;
                statusEl.style.color = 'var(--accent-rose)';
            }
        }
    }
}

function disconnectWebBluetooth() {
    if (state.webBluetoothDevice && state.webBluetoothDevice.gatt.connected) {
        state.webBluetoothDevice.gatt.disconnect();
    }
    onWebBluetoothDisconnected();
}

function onWebBluetoothDisconnected() {
    const statusEl = document.getElementById('web-ble-esp32-status');
    const pairBtn = document.getElementById('btn-web-ble-esp32-pair');
    const disconnectBtn = document.getElementById('btn-web-ble-esp32-disconnect');

    if (statusEl) {
        statusEl.textContent = 'Disconnected from Bluetooth.';
        statusEl.style.color = 'var(--text-muted)';
    }
    if (pairBtn) pairBtn.style.display = 'inline-block';
    if (disconnectBtn) disconnectBtn.style.display = 'none';

    state.webBluetoothDevice = null;
    state.webBluetoothServer = null;
    state.webBluetoothCharCommands = null;
    state.esp32Connected = false;
    state.bothModulesConnected = false;

    fetch('/api/telemetry/reset', { method: 'POST' }).catch(() => {});
    resetDashboardToStandby('ESP32 Bluetooth connection disconnected.');
    updateHardwarePills();
}

// Matches the backend's IR_INVERTED setting: the testbed's IR modules report the opposite of
// the firmware's "1 = vehicle" mapping, so readings are flipped on arrival.
const IR_INVERTED = true;

function readIR(raw, alreadyCorrected = false) {
    if (!Array.isArray(raw)) return [0, 0, 0, 0];  // no IR data: clear, not inverted
    const flags = raw.map(v => (v ? 1 : 0));
    return (IR_INVERTED && !alreadyCorrected) ? flags.map(f => 1 - f) : flags;
}

function handleWebBluetoothTelemetryPacket(event) {
    try {
        const rawBytes = event.target.value;
        const decoder = new TextDecoder('utf-8');
        const chunk = decoder.decode(rawBytes);
        state.bleRxBuffer = (state.bleRxBuffer || '') + chunk;

        const startIdx = state.bleRxBuffer.indexOf('{');
        const endIdx = state.bleRxBuffer.indexOf('}', startIdx);

        if (startIdx === -1 || endIdx === -1) {
            return; // Wait for complete chunk
        }

        const jsonStr = state.bleRxBuffer.substring(startIdx, endIdx + 1);
        state.bleRxBuffer = state.bleRxBuffer.substring(endIdx + 1);
        if (state.bleRxBuffer.length > 2048) state.bleRxBuffer = '';

        const parsed = JSON.parse(jsonStr);

        state.lastPacketTime = Date.now();
        // Firmware with the on-board mic filter sends sndfix:1; older firmware's raw mic flag
        // flickers on room noise, so its sound/collision state is left to the backend's filter.
        state.soundFiltered = Boolean(parsed.sndfix);

        // Forward to backend ingestion
        fetch('/api/telemetry/ingest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(parsed)
        }).catch(() => {});

        state.esp32Connected = true;
        state.bothModulesConnected = true;

        updateTelemetryUI({
            ...state.telemetry,
            device_id: 'SENTRAX-ESP32',
            is_simulated: false,
            esp32_connected: true,
            esp8266_connected: false,
            both_modules_connected: true,
            hardware_standby: false,
            recommended_speed_kmh: parseFloat(parsed.rec_speed || 80.0),
            temperature_c: parseFloat(parsed.temp || 26.5),
            humidity_pct: parseFloat(parsed.hum || 55.0),
            moisture_raw: parseInt(parsed.moist || 3100),
            ir_sensors: readIR(parsed.ir, Boolean(parsed.irfix)).map(x => Boolean(x)),
            sound_active: state.soundFiltered ? Boolean(parsed.sound || 0) : Boolean(state.telemetry.sound_active),
            night_mode: Boolean(parsed.night || 0),
            road_condition: (parsed.alert === 'WET_ROAD' || (parsed.moist && parsed.moist < 2000)) ? 'WET' : 'DRY',
            traffic_level: (parsed.alert === 'CONGESTION' || readIR(parsed.ir, Boolean(parsed.irfix)).reduce((a,b)=>a+b,0) >= 2) ? 'CONGESTED' : 'LIGHT'
        });
    } catch (err) {
        console.warn('Error decoding BLE packet:', err);
    }
}

function handleWebBluetoothEventPacket(event) {
    try {
        const rawBytes = event.target.value;
        const decoder = new TextDecoder('utf-8');
        const alertName = decoder.decode(rawBytes).trim();

        if (alertName === 'EMERGENCY') {
            fetch('/api/events', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source: 'ESP32',
                    type: 'EMERGENCY',
                    severity: 'CRITICAL',
                    title: 'Hardware Event: EMERGENCY',
                    description: 'RFID emergency notification received over Web Bluetooth'
                })
            }).catch(() => {});
        }

        if (alertName === 'COLLISION' && !state.soundFiltered) {
            return;  // old firmware raises this on every mic flicker; the backend decides instead
        }

        prependEventTimeline({
            type: alertName,
            title: `PHYSICAL EVENT: ${alertName}`,
            description: `Triggered directly by physical microcontrollers over BLE`,
            severity: (alertName === 'COLLISION' || alertName === 'WRONG_WAY') ? 'CRITICAL' : 'WARNING',
            timestamp: Date.now() / 1000,
            source: 'ESP32-HARDWARE'
        });
    } catch (err) {
        console.error('Error handling BLE event packet:', err);
    }
}

// -------------------------------------------------------------
// COM Port Helpers & Serial Handlers
// -------------------------------------------------------------
async function refreshCOMPorts(selectId) {
    const selectEl = document.getElementById(selectId);
    if (!selectEl) return;

    try {
        const res = await fetch('/api/serial/ports');
        const ports = await res.json();

        if (!ports || ports.length === 0) {
            selectEl.innerHTML = '<option value="">No COM ports detected on Windows</option>';
            return;
        }

        selectEl.innerHTML = ports.map(p => `
            <option value="${p.port}">${p.port} - ${p.description}</option>
        `).join('');
    } catch (err) {
        console.error('Error refreshing COM ports:', err);
    }
}

async function connectESP32Serial() {
    const selectEl = document.getElementById('select-esp32-com-port');
    const statusEl = document.getElementById('esp32-serial-status');
    const connectBtn = document.getElementById('btn-connect-esp32-serial');
    const disconnectBtn = document.getElementById('btn-disconnect-esp32-serial');

    const port = selectEl?.value;
    if (!port) {
        alert('Please select a COM port for ESP32.');
        return;
    }

    if (statusEl) statusEl.textContent = `Connecting to ${port} at 115200 baud...`;

    try {
        const res = await fetch('/api/esp32/connect/serial', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ port: port, baudrate: 115200 })
        });
        const data = await res.json();

        if (res.ok) {
            state.esp32Connected = true;
            if (statusEl) {
                statusEl.textContent = `Connected to ${port}! Streaming ESP32 packets.`;
                statusEl.style.color = 'var(--accent-emerald)';
            }
            if (connectBtn) connectBtn.style.display = 'none';
            if (disconnectBtn) disconnectBtn.style.display = 'inline-block';
            updateHardwarePills();
            pollHardwareStatus();
        } else {
            if (statusEl) {
                statusEl.textContent = `Failed: ${data.detail || 'Access denied'}`;
                statusEl.style.color = 'var(--accent-rose)';
            }
        }
    } catch (err) {
        if (statusEl) statusEl.textContent = `Error: ${err.message}`;
    }
}

async function disconnectESP32Serial() {
    const statusEl = document.getElementById('esp32-serial-status');
    const connectBtn = document.getElementById('btn-connect-esp32-serial');
    const disconnectBtn = document.getElementById('btn-disconnect-esp32-serial');

    try {
        await fetch('/api/esp32/disconnect', { method: 'POST' });
        state.esp32Connected = false;
        state.bothModulesConnected = false;
        if (statusEl) {
            statusEl.textContent = 'Disconnected from ESP32.';
            statusEl.style.color = 'var(--text-muted)';
        }
        if (connectBtn) connectBtn.style.display = 'inline-block';
        if (disconnectBtn) disconnectBtn.style.display = 'none';
        resetDashboardToStandby('ESP32 serial connection disconnected.');
        updateHardwarePills();
        pollHardwareStatus();
    } catch (err) {
        console.error('ESP32 disconnect error:', err);
    }
}

// =====================================================================
// AERIAL DIGITAL TWIN & HARDWARE COMMAND CONTROLS
// =====================================================================

function initAerialControls() {
    // 1. Speed Slider & Presets
    const slider = document.getElementById('input-speed-slider');
    const sliderVal = document.getElementById('ctrl-slider-val');
    const applyBtn = document.getElementById('btn-apply-speed');
    const presets = document.querySelectorAll('.btn-preset');
    const feedbackBanner = document.getElementById('ctrl-feedback-banner');

    if (slider && sliderVal) {
        slider.addEventListener('input', (e) => {
            sliderVal.textContent = e.target.value;
            presets.forEach(p => {
                p.classList.toggle('active', p.getAttribute('data-speed') === e.target.value);
            });
        });
    }

    presets.forEach(p => {
        p.addEventListener('click', () => {
            const spd = p.getAttribute('data-speed');
            if (slider) slider.value = spd;
            if (sliderVal) sliderVal.textContent = spd;
            presets.forEach(btn => btn.classList.remove('active'));
            p.classList.add('active');
        });
    });

    if (applyBtn) {
        applyBtn.addEventListener('click', async () => {
            const speed = parseFloat(slider ? slider.value : 80);
            applyBtn.disabled = true;
            try {
                if (feedbackBanner) {
                    feedbackBanner.textContent = `Sending test vehicle speed ${speed.toFixed(1)} km/h...`;
                    feedbackBanner.className = 'ctrl-feedback-banner';
                }

                // A. Direct Web Bluetooth GATT Command
                sendHardwareCommand(`SPEED:${speed.toFixed(1)}`);

                // B. Backend REST API override
                const res = await fetch('/api/speed/override', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ speed: speed })
                });

                if (res.ok) {
                    if (feedbackBanner) {
                        feedbackBanner.textContent = `Test vehicle speed ${speed.toFixed(1)} km/h sent to the ESP32.`;
                        feedbackBanner.className = 'ctrl-feedback-banner success';
                    }
                } else {
                    const errData = await res.json().catch(() => ({}));
                    if (feedbackBanner) {
                        feedbackBanner.textContent = `Speed sent: ${errData.detail || 'Saved'}`;
                        feedbackBanner.className = 'ctrl-feedback-banner';
                    }
                }
            } catch (err) {
                console.error('Speed override error:', err);
                if (feedbackBanner) {
                    feedbackBanner.textContent = `Error: ${err.message}`;
                    feedbackBanner.className = 'ctrl-feedback-banner error';
                }
            } finally {
                applyBtn.disabled = false;
            }
        });
    }

    // 2. Alert Trigger Buttons
    const alertBtns = document.querySelectorAll('.btn-alert-cmd');
    alertBtns.forEach(btn => {
        btn.addEventListener('click', async () => {
            const alertType = btn.getAttribute('data-alert');
            const selectStalled = document.getElementById('select-stalled-ir');
            const sensorIndex = selectStalled ? parseInt(selectStalled.value) : 1;

            alertBtns.forEach(b => b.classList.remove('active-trigger'));
            btn.classList.add('active-trigger');

            // Bypass standby to immediately inspect triggered manual alert
            state.bypassStandby = true;
            const standbyOverlay = document.getElementById('hardware-standby-overlay');
            if (standbyOverlay) standbyOverlay.classList.add('hidden');

            try {
                if (feedbackBanner) {
                    feedbackBanner.textContent = `Triggering ${alertType} alert on physical ESP32 & LEDs...`;
                    feedbackBanner.className = 'ctrl-feedback-banner';
                }

                // A. Direct Web Bluetooth GATT Command
                const bleCmd = (alertType === 'STALLED') ? `ALERT:STALLED:${sensorIndex}` : `ALERT:${alertType}`;
                sendHardwareCommand(bleCmd);

                // B. Backend REST API Alert Trigger
                const res = await fetch('/api/alerts/trigger', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        alert: alertType,
                        sensor_index: sensorIndex
                    })
                });

                if (res.ok) {
                    const data = await res.json();
                    if (feedbackBanner) {
                        feedbackBanner.textContent = `Alert '${alertType}' armed. LEDs and E-Ink updated (risk ${data.risk_score || 0}).`;
                        feedbackBanner.className = 'ctrl-feedback-banner success';
                    }
                } else {
                    const errData = await res.json().catch(() => ({}));
                    if (feedbackBanner) {
                        feedbackBanner.textContent = `Alert sent: ${errData.detail || 'Processed'}`;
                    }
                }
            } catch (err) {
                console.error('Alert trigger error:', err);
                if (feedbackBanner) {
                    feedbackBanner.textContent = `Trigger error: ${err.message}`;
                    feedbackBanner.className = 'ctrl-feedback-banner error';
                }
            }
        });
    });

    // 3. Reset Demo: clears every alert and test speed applied from this console
    const resetBtn = document.getElementById('btn-reset-demo');
    if (resetBtn) {
        resetBtn.addEventListener('click', async () => {
            resetBtn.disabled = true;
            try {
                if (feedbackBanner) {
                    feedbackBanner.textContent = 'Resetting demo modes on the ESP32, LEDs and E-Ink...';
                    feedbackBanner.className = 'ctrl-feedback-banner';
                }

                // A. Direct Web Bluetooth GATT Command
                sendHardwareCommand('ALERT:NORMAL');

                // B. Backend: same ALERT:NORMAL to the board, plus clears emergency and test speed
                const res = await fetch('/api/demo/reset', { method: 'POST' });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);

                if (slider) slider.value = 80;
                if (sliderVal) sliderVal.textContent = '80';
                presets.forEach(p => p.classList.toggle('active', p.getAttribute('data-speed') === '80'));
                alertBtns.forEach(b => b.classList.remove('active-trigger'));
                const selectStalled = document.getElementById('select-stalled-ir');
                if (selectStalled) selectStalled.value = '1';

                if (feedbackBanner) {
                    feedbackBanner.textContent = 'Demo reset. Alerts cleared, test speed removed, LEDs and E-Ink back to normal.';
                    feedbackBanner.className = 'ctrl-feedback-banner success';
                }
            } catch (err) {
                console.error('Demo reset error:', err);
                if (feedbackBanner) {
                    feedbackBanner.textContent = `Reset error: ${err.message}`;
                    feedbackBanner.className = 'ctrl-feedback-banner error';
                }
            } finally {
                resetBtn.disabled = false;
            }
        });
    }
}

async function sendHardwareCommand(cmdString) {
    if (state.webBluetoothCharCommands) {
        try {
            const encoder = new TextEncoder();
            const payload = encoder.encode(cmdString + '\n');
            await state.webBluetoothCharCommands.writeValue(payload);
            console.log(`[SentraX BLE] Wrote command to ESP32: ${cmdString}`);
        } catch (e) {
            console.warn(`[SentraX BLE] Error writing GATT command: ${e.message}`);
        }
    }
}

function updateAerialTwinUI(t) {
    if (!t) return;

    // Header badge
    const badge = document.getElementById('aerial-hw-status-badge');
    if (badge) {
        badge.textContent = state.esp32Connected ? 'LIVE TRACK' : 'STANDBY';
        badge.className = 'live-badge ' + (state.esp32Connected ? 'live' : 'simulated');
    }

    // 1. Hotspot: E-Ink Sign
    const speedLimit = t.recommended_speed_kmh ? t.recommended_speed_kmh.toFixed(0) : '80';
    setText('tt-val-eink-speed', `${speedLimit} km/h`);

    // Determine active alert label
    let alertName = 'ROAD CLEAR';
    let alertSeverity = 'NORMAL';
    let ledPattern = 'NORMAL (AMBER)';
    let einkIcon = 'check-circle';
    let einkSub = `NORMAL LIMIT: ${speedLimit} KM/H`;

    if (t.collision || t.sound_active) {
        alertName = 'ACCIDENT AHEAD';
        alertSeverity = 'CRITICAL';
        ledPattern = 'COLLISION (RED FLASH 10..13)';
        einkIcon = 'warning';
        einkSub = 'SLOW DOWN / ACCIDENT';
    } else if (t.wrong_way) {
        alertName = 'WRONG WAY VEHICLE';
        alertSeverity = 'CRITICAL';
        ledPattern = 'WRONG WAY (DUAL RED FLASH)';
        einkIcon = 'prohibit';
        einkSub = 'STOP & TURN AROUND';
    } else if (t.stalled_vehicle) {
        alertName = 'STALLED VEHICLE';
        alertSeverity = 'WARNING';
        ledPattern = 'LOCALIZED STALL FLASH';
        einkIcon = 'traffic-cone';
        einkSub = 'LANE OBSTRUCTION';
    } else if (t.rfid_active || t.emergency_vehicle) {
        alertName = 'EMERGENCY VEHICLE';
        alertSeverity = 'HIGH';
        ledPattern = 'EMERGENCY CADENCE';
        einkIcon = 'siren';
        einkSub = 'YIELD RIGHT OF WAY';
    } else if (t.traffic_level === 'CONGESTED') {
        alertName = 'CONGESTION';
        alertSeverity = 'WARNING';
        ledPattern = 'CONGESTION (HIGH DENSITY)';
        einkIcon = 'car-profile';
        einkSub = 'SPEED REDUCED: 60 KM/H';
    } else if (t.road_condition === 'WET') {
        alertName = 'WET ROAD SURFACE';
        alertSeverity = 'WARNING';
        ledPattern = 'WET ROAD (SAFETY PULSE)';
        einkIcon = 'cloud-rain';
        einkSub = 'SPEED LIMIT: 40 KM/H';
    } else if (t.temperature_c >= 30.0) {
        alertName = 'HIGH ROAD TEMP';
        alertSeverity = 'CAUTION';
        ledPattern = 'HIGH TEMP (OVERHEAT)';
        einkIcon = 'sun';
        einkSub = 'SPEED LIMIT: 35 KM/H';
    }

    setText('tt-val-eink-alert', alertName);
    setText('tt-chip-eink', alertSeverity);
    const chipEink = document.getElementById('tt-chip-eink');
    if (chipEink) {
        chipEink.className = 'tooltip-chip ' + (alertSeverity === 'CRITICAL' ? 'danger' : (alertSeverity === 'WARNING' ? 'warning' : ''));
    }

    // 2. Hotspot: US1 (Speed Entry)
    const us1Active = Boolean(t.ultrasonic_state?.us1_active);
    setText('tt-val-us1', us1Active ? 'VEHICLE PRESENT (BEAM INTERRUPTED)' : 'CLEAR (>15cm)');
    setText('tt-val-us1-timer', us1Active ? 'TIMING ACTIVE' : 'READY');
    const hotspotUs1 = document.getElementById('hotspot-us1');
    const chipUs1 = document.getElementById('tt-chip-us1');
    if (hotspotUs1) hotspotUs1.className = 'aerial-hotspot' + (us1Active ? ' triggered' : '');
    if (chipUs1) {
        chipUs1.textContent = us1Active ? 'ACTIVE' : 'IDLE';
        chipUs1.className = 'tooltip-chip ' + (us1Active ? 'warning' : '');
    }

    // 3, 4, 7, 9. Hotspots: IR1..IR4
    const irStarts = [2, 10, 17, 24];
    const irEnds   = [6, 14, 21, 28];
    if (t.ir_sensors) {
        for (let i = 0; i < 4; i++) {
            const occ = Boolean(t.ir_sensors[i]);
            const hs = document.getElementById(`hotspot-ir${i+1}`);
            const chip = document.getElementById(`tt-chip-ir${i+1}`);
            setText(`tt-val-ir${i+1}`, occ ? 'OCCUPIED (BEAM BLOCKED)' : 'CLEAR');

            if (hs) {
                hs.className = 'aerial-hotspot' + (occ ? ' triggered' : '');
            }
            if (chip) {
                chip.textContent = occ ? 'OCCUPIED' : 'CLEAR';
                chip.className = 'tooltip-chip ' + (occ ? 'danger' : '');
            }

            if (i === 0) setText('tt-val-ir1-stall', occ ? 'TIMING OCCUPANCY...' : '0.0s / 6.0s');
            if (i === 1) setText('tt-val-ir2-stall', occ ? 'TIMING OCCUPANCY...' : '0.0s / 6.0s');
            if (i === 2) setText('tt-val-ir3-ww', t.wrong_way ? 'WRONG-WAY TRIGGERED!' : 'ARMED');
            if (i === 3) setText('tt-val-ir4-ww', occ ? 'WINDOW ARMED (15s)' : 'IDLE');

            if (occ && t.stalled_vehicle) {
                ledPattern = `LOCALIZED STALL (IR${i+1} LEDs ${irStarts[i]}..${irEnds[i]})`;
                setText('tt-val-led-stalled-target', `IR${i+1} (LEDs ${irStarts[i]}..${irEnds[i]})`);
            }
        }
    }

    // 5. Hotspot: DHT11
    setText('tt-val-dht-temp', `${t.temperature_c.toFixed(1)} °C`);
    setText('tt-val-dht-hum', `${t.humidity_pct.toFixed(0)} %`);
    const hotspotDht = document.getElementById('hotspot-dht');
    const chipDht = document.getElementById('tt-chip-dht');
    const highTemp = t.temperature_c >= 30.0;
    if (hotspotDht) hotspotDht.className = 'aerial-hotspot' + (highTemp ? ' warning' : '');
    if (chipDht) {
        chipDht.textContent = highTemp ? 'HIGH HEAT' : 'NOMINAL';
        chipDht.className = 'tooltip-chip ' + (highTemp ? 'warning' : '');
    }

    // 6. Hotspot: Sound / Crash
    const soundActive = Boolean(t.sound_active);
    setText('tt-val-sound', soundActive ? 'HIGH DECIBEL IMPACT' : 'NORMAL');
    setText('tt-val-collision', t.collision ? 'COLLISION ALERT' : 'CLEAR');
    const hotspotSound = document.getElementById('hotspot-sound');
    const chipSound = document.getElementById('tt-chip-sound');
    if (hotspotSound) hotspotSound.className = 'aerial-hotspot' + (soundActive || t.collision ? ' triggered' : '');
    if (chipSound) {
        chipSound.textContent = (soundActive || t.collision) ? 'IMPACT' : 'QUIET';
        chipSound.className = 'tooltip-chip ' + (soundActive || t.collision ? 'danger' : '');
    }

    // 8. Hotspot: Moisture
    setText('tt-val-moist', `${t.moisture_raw} (${t.road_condition})`);
    const isWet = t.road_condition === 'WET';
    const hotspotMoist = document.getElementById('hotspot-moist');
    const chipMoist = document.getElementById('tt-chip-moist');
    if (hotspotMoist) hotspotMoist.className = 'aerial-hotspot' + (isWet ? ' warning' : '');
    if (chipMoist) {
        chipMoist.textContent = isWet ? 'WET ROAD' : 'DRY';
        chipMoist.className = 'tooltip-chip ' + (isWet ? 'warning' : '');
    }

    // 10. Hotspot: US2
    const us2Active = Boolean(t.ultrasonic_state?.us2_active);
    setText('tt-val-us2', us2Active ? 'VEHICLE PRESENT (GATE EXIT)' : 'CLEAR (>15cm)');
    setText('tt-val-measured-spd', `${t.measured_speed_kmh.toFixed(1)} km/h`);
    const isOverspeed = t.measured_speed_kmh > 4.0;
    setText('tt-val-speed-eval', isOverspeed ? `OVERSPEED (${t.measured_speed_kmh.toFixed(1)} > 4.0)` : 'NORMAL');
    const hotspotUs2 = document.getElementById('hotspot-us2');
    const chipUs2 = document.getElementById('tt-chip-us2');
    if (hotspotUs2) hotspotUs2.className = 'aerial-hotspot' + (us2Active || isOverspeed ? ' warning' : '');
    if (chipUs2) {
        chipUs2.textContent = isOverspeed ? 'OVERSPEED' : (us2Active ? 'ACTIVE' : 'IDLE');
        chipUs2.className = 'tooltip-chip ' + (isOverspeed ? 'danger' : (us2Active ? 'warning' : ''));
    }

    // 11. Hotspot: WS2812B LEDs
    setText('tt-val-led-pattern', ledPattern);
    const hotspotLeds = document.getElementById('hotspot-leds');
    if (hotspotLeds) {
        const isAlertLeds = t.collision || t.wrong_way || t.stalled_vehicle || isWet;
        hotspotLeds.className = 'aerial-hotspot' + (isAlertLeds ? ' warning' : '');
    }

    // 12. Hotspot: ESP32
    const chipEsp32 = document.getElementById('tt-chip-esp32');
    if (chipEsp32) {
        chipEsp32.textContent = state.esp32Connected ? 'CONNECTED' : 'STANDBY';
        chipEsp32.className = 'tooltip-chip ' + (state.esp32Connected ? '' : 'warning');
    }

    // ==============================================================
    // RENDER LIVE 1.54" GxEPD2 E-INK DIGITAL TWIN
    // ==============================================================
    renderEInkTwin(speedLimit, alertName, einkIcon, einkSub, t.measured_speed_kmh.toFixed(1), alertSeverity);
}

function renderEInkTwin(speedVal, alertMain, alertIcon, alertSub, measuredSpd, statusLabel) {
    const einkSurface = document.getElementById('eink-screen-surface');
    const einkSpeedVal = document.getElementById('eink-speed-val');
    const einkAlertIcon = document.getElementById('eink-alert-icon');
    const einkAlertMain = document.getElementById('eink-alert-main');
    const einkAlertSub = document.getElementById('eink-alert-sub');
    const einkMeasuredSpd = document.getElementById('eink-measured-spd');
    const einkStatusLabel = document.getElementById('eink-status-label');

    // Trigger authentic e-paper partial refresh inversion flash if content changed
    const key = `${speedVal}_${alertMain}`;
    if (state.lastEinkKey && state.lastEinkKey !== key && einkSurface) {
        einkSurface.classList.add('refreshing');
        setTimeout(() => einkSurface.classList.remove('refreshing'), 160);
    }
    state.lastEinkKey = key;

    if (einkSpeedVal) einkSpeedVal.textContent = speedVal;
    if (einkAlertIcon) einkAlertIcon.innerHTML = `<i class="ph-bold ph-${alertIcon}"></i>`;
    if (einkAlertMain) einkAlertMain.textContent = alertMain;
    if (einkAlertSub) einkAlertSub.textContent = alertSub;
    if (einkMeasuredSpd) einkMeasuredSpd.textContent = measuredSpd;
    if (einkStatusLabel) einkStatusLabel.textContent = statusLabel;
}

function resetAerialTwinToStandby() {
    const badge = document.getElementById('aerial-hw-status-badge');
    if (badge) {
        badge.textContent = 'STANDBY';
        badge.className = 'live-badge simulated';
    }

    document.querySelectorAll('.aerial-hotspot').forEach(el => {
        el.className = 'aerial-hotspot standby';
    });

    renderEInkTwin('--', 'STANDBY', 'hourglass', 'CONNECT ESP32 HARDWARE', '0.0', 'OFFLINE');
}

// ==============================================================
// SENSOR-CAMERA FUSION & COMPUTER VISION EXTENSIONS
// ==============================================================

// The demo batch file starts the simulator's 8-step sequence through the API. While it runs the
// dashboard unlocks (no ESP32 needed), jumps to the Command Center and shows the current step.
const demoWatch = { running: false };

async function pollDemoStatus() {
    try {
        const res = await fetch('/api/simulation/status');
        if (!res.ok) return;
        const s = await res.json();
        const chip = document.getElementById('demo-chip');
        if (s.auto_demo_running) {
            if (!demoWatch.running) {
                demoWatch.running = true;
                state.bypassStandby = true;
                document.getElementById('hardware-standby-overlay')?.classList.add('hidden');
                switchTab('command-center');
            }
            if (chip) {
                chip.hidden = false;
                chip.textContent = `Demo step ${s.active_step} of ${s.total_steps}`;
            }
        } else if (demoWatch.running) {
            demoWatch.running = false;
            if (state.detectionMode !== 'CAMERA') state.bypassStandby = false;
            if (chip) chip.hidden = true;
        }
    } catch (err) {
        // server restarting
    }
}

async function initFusionAndCV() {
    // 1. Detection Mode Switcher Buttons (Section 31)
    const btnFusion = document.getElementById('btn-mode-fusion');
    const btnSensor = document.getElementById('btn-mode-sensor');
    const btnCamera = document.getElementById('btn-mode-camera');

    if (btnFusion) btnFusion.addEventListener('click', () => setDetectionMode('FUSION'));
    if (btnSensor) btnSensor.addEventListener('click', () => setDetectionMode('SENSOR'));
    if (btnCamera) btnCamera.addEventListener('click', () => setDetectionMode('CAMERA'));

    // 2. Standby Overlay Bypass Button
    const btnBypass = document.getElementById('btn-bypass-standby');
    if (btnBypass) {
        btnBypass.addEventListener('click', () => {
            state.bypassStandby = true;
            const overlay = document.getElementById('hardware-standby-overlay');
            if (overlay) overlay.classList.add('hidden');
            setDetectionMode('FUSION');
        });
    }

    // 3. Demo Stalled Vehicle Timer Toggle (Section 6 & 34)
    const btnToggleStall = document.getElementById('btn-toggle-demo-stall');
    if (btnToggleStall) {
        btnToggleStall.addEventListener('click', async () => {
            const nextMode = !state.demoStallMode;
            await setDemoStallMode(nextMode);
        });
    }

    const btnStall5s = document.getElementById('btn-cv-stall-5s');
    const btnStall15s = document.getElementById('btn-cv-stall-15s');
    if (btnStall5s) btnStall5s.addEventListener('click', () => setDemoStallMode(true));
    if (btnStall15s) btnStall15s.addEventListener('click', () => setDemoStallMode(false));

    // 4. Camera Device & Source Selector (Section 2)
    await loadCameraDevices();
    const btnApplySource = document.getElementById('btn-cv-apply-source');
    if (btnApplySource) {
        btnApplySource.addEventListener('click', async () => {
            const customInput = document.getElementById('cv-input-custom-source');
            const selectDevice = document.getElementById('cv-select-device');
            const source = (customInput && customInput.value.trim()) ? customInput.value.trim() : (selectDevice?.value || '0');
            await applyCameraSource(source);
        });
    }

    const selectDeviceEl = document.getElementById('cv-select-device');
    if (selectDeviceEl) {
        selectDeviceEl.addEventListener('change', () => {
            const customInput = document.getElementById('cv-input-custom-source');
            if (customInput) customInput.value = selectDeviceEl.value;
        });
    }

    const btnRefreshDevices = document.getElementById('btn-cv-refresh-devices');
    if (btnRefreshDevices) {
        btnRefreshDevices.addEventListener('click', async () => {
            btnRefreshDevices.disabled = true;
            btnRefreshDevices.textContent = 'Scanning';
            try {
                await loadCameraDevices(true);
            } finally {
                btnRefreshDevices.disabled = false;
                btnRefreshDevices.textContent = 'Rescan';
            }
        });
    }

    document.querySelectorAll('.cv-btn-preset').forEach(btn => {
        btn.addEventListener('click', async () => {
            const src = btn.getAttribute('data-source');
            const customInput = document.getElementById('cv-input-custom-source');
            if (customInput) customInput.value = src;
            await applyCameraSource(src);
        });
    });

    const btnReloadStream = document.getElementById('btn-cv-reload-stream');
    if (btnReloadStream) {
        btnReloadStream.addEventListener('click', () => {
            const feedImg = document.getElementById('cv-feed-img');
            if (feedImg) feedImg.src = '/api/cv/feed?t=' + Date.now();
        });
    }

    // 5. Virtual Speed Calibration (Section 11)
    initSpeedCalibration();

    // 6. 13-Scenario Interactive Test Deck (Section 43)
    initScenarioDeck();

    // 7. Section 58 Forensic Decision Audit Modal
    initDecisionAuditModal();

    // 8. Initial Fetch & Periodic Polling (every 1.5s)
    await pollFusionAndCV();
    setInterval(pollFusionAndCV, 1500);
    pollDemoStatus();
    setInterval(pollDemoStatus, 1500);
}

async function setDetectionMode(mode) {
    try {
        const res = await fetch('/api/fusion/mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });
        if (res.ok) {
            state.detectionMode = mode;
            // Update mode buttons UI
            const btns = {
                'FUSION': document.getElementById('btn-mode-fusion'),
                'SENSOR': document.getElementById('btn-mode-sensor'),
                'CAMERA': document.getElementById('btn-mode-camera')
            };
            Object.keys(btns).forEach(m => {
                const b = btns[m];
                if (b) b.classList.toggle('active', m === mode);
            });

            const badgeLabel = document.getElementById('badge-fusion-mode-label');
            if (badgeLabel) badgeLabel.textContent = `MODE: ${mode}`;

            if (mode === 'CAMERA') {
                state.bypassStandby = true;
                const overlay = document.getElementById('hardware-standby-overlay');
                if (overlay) overlay.classList.add('hidden');
            }

            await pollFusionAndCV();
        }
    } catch (err) {
        console.error('Error setting detection mode:', err);
    }
}

async function setDemoStallMode(isDemo) {
    try {
        const res = await fetch('/api/cv/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ demo_mode: isDemo })
        });
        if (res.ok) {
            state.demoStallMode = isDemo;
            const btnToggle = document.getElementById('btn-toggle-demo-stall');
            if (btnToggle) btnToggle.textContent = isDemo ? 'Demo: 5 s stall' : 'Production: 15 s stall';
            document.getElementById('btn-cv-stall-5s')?.classList.toggle('active', isDemo);
            document.getElementById('btn-cv-stall-15s')?.classList.toggle('active', !isDemo);
        }
    } catch (err) {
        console.error('Error setting demo stall mode:', err);
    }
}

async function loadCameraDevices(forceRefresh = false) {
    const select = document.getElementById('cv-select-device');
    if (!select) return;
    try {
        const url = forceRefresh ? '/api/cv/devices?refresh=true' : '/api/cv/devices';
        const res = await fetch(url);
        if (res.ok) {
            const devices = await res.json();
            if (Array.isArray(devices) && devices.length > 0) {
                select.innerHTML = devices.map(d => {
                    const isIriun = (d.name && d.name.toLowerCase().includes('iriun')) || d.index === 4;
                    const resTag = d.resolution ? ` [${d.resolution}]` : '';
                    const cleanName = d.name.replace('[Phone] ', '').replace('[Camera] ', '');
                    return `<option value="${d.source || d.index}" ${isIriun ? 'selected' : ''}>${cleanName}${resTag}</option>`;
                }).join('');

                // Also populate custom input with selected device source
                const customInput = document.getElementById('cv-input-custom-source');
                if (customInput && !customInput.value) {
                    customInput.value = select.value;
                }
            } else {
                select.innerHTML = '<option value="4">Iriun webcam (device 4)</option><option value="0">Camera 0 (default webcam)</option><option value="synthetic">Synthetic test scene</option>';
            }
        }
    } catch (err) {
        console.warn('Could not load camera devices list:', err);
    }
}

async function applyCameraSource(source) {
    const msgEl = document.getElementById('cv-source-msg');
    if (msgEl) {
        msgEl.textContent = `Connecting to camera source: ${source}...`;
        msgEl.className = 'field-msg '.trim();
    }
    try {
        const res = await fetch('/api/cv/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ camera_source: source })
        });
        if (res.ok) {
            if (msgEl) {
                msgEl.textContent = `Applied source: ${source}`;
                msgEl.className = 'field-msg is-good'.trim();
            }
            const feedImg = document.getElementById('cv-feed-img');
            if (feedImg) feedImg.src = '/api/cv/feed?t=' + Date.now();
            await pollFusionAndCV();
        } else {
            if (msgEl) {
                msgEl.textContent = 'Failed to apply camera source';
                msgEl.className = 'field-msg is-bad'.trim();
            }
        }
    } catch (err) {
        if (msgEl) {
            msgEl.textContent = `Error: ${err.message}`;
            msgEl.className = 'field-msg is-bad'.trim();
        }
    }
}

function initSpeedCalibration() {
    const rangeA = document.getElementById('cv-range-line-a');
    const rangeB = document.getElementById('cv-range-line-b');
    const lblA = document.getElementById('cv-lbl-line-a');
    const lblB = document.getElementById('cv-lbl-line-b');
    const numDist = document.getElementById('cv-num-distance');
    const btnSave = document.getElementById('btn-cv-save-cal');
    const msgEl = document.getElementById('cv-cal-msg');

    if (rangeA && lblA) {
        rangeA.addEventListener('input', () => { lblA.textContent = `${rangeA.value} px`; });
    }
    if (rangeB && lblB) {
        rangeB.addEventListener('input', () => { lblB.textContent = `${rangeB.value} px`; });
    }

    document.querySelectorAll('.cv-btn-dist-preset').forEach(btn => {
        btn.addEventListener('click', () => {
            const d = btn.getAttribute('data-dist');
            if (numDist) numDist.value = d;
        });
    });

    if (btnSave) {
        btnSave.addEventListener('click', async () => {
            const a = parseInt(rangeA?.value || '140');
            const b = parseInt(rangeB?.value || '260');
            const dist = parseFloat(numDist?.value || '0.30');

            if (a >= b) {
                if (msgEl) {
                    msgEl.textContent = 'Line A must be above Line B (A < B).';
                    msgEl.className = 'field-msg is-bad'.trim();
                }
                return;
            }

            try {
                const res = await fetch('/api/cv/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        speed_calibration: {
                            line_a_y: a,
                            line_b_y: b,
                            distance_meters: dist
                        }
                    })
                });
                if (res.ok) {
                    if (msgEl) {
                        msgEl.textContent = `Saved: Line A=${a}px, Line B=${b}px, Distance=${dist}m`;
                        msgEl.className = 'field-msg is-good'.trim();
                    }
                }
            } catch (err) {
                if (msgEl) {
                    msgEl.textContent = `Error: ${err.message}`;
                    msgEl.className = 'field-msg is-bad'.trim();
                }
            }
        });
    }

    // Load initial calibration from backend
    fetch('/api/cv/config').then(r => r.json()).then(cfg => {
        if (cfg && cfg.speed_calibration) {
            if (rangeA) rangeA.value = cfg.speed_calibration.line_a_y;
            if (lblA) lblA.textContent = `${cfg.speed_calibration.line_a_y} px`;
            if (rangeB) rangeB.value = cfg.speed_calibration.line_b_y;
            if (lblB) lblB.textContent = `${cfg.speed_calibration.line_b_y} px`;
            if (numDist) numDist.value = cfg.speed_calibration.distance_meters;
        }
        if (cfg && cfg.demo_mode !== undefined) {
            state.demoStallMode = cfg.demo_mode;
            document.getElementById('btn-cv-stall-5s')?.classList.toggle('active', cfg.demo_mode);
            document.getElementById('btn-cv-stall-15s')?.classList.toggle('active', !cfg.demo_mode);
            const btnToggle = document.getElementById('btn-toggle-demo-stall');
            if (btnToggle) {
                btnToggle.textContent = cfg.demo_mode ? 'Demo: 5 s stall' : 'Production: 15 s stall';
            }
        }
    }).catch(e => console.warn('Could not load CV config:', e));
}

async function executeTestCase(tcNum) {
    if (!tcNum) return;

    // Unlock standby overlay for test inspection
    state.bypassStandby = true;
    const overlay = document.getElementById('hardware-standby-overlay');
    if (overlay) overlay.classList.add('hidden');

    // Sync select dropdown
    const selectPicker = document.getElementById('select-scenario-picker');
    if (selectPicker) selectPicker.value = String(tcNum);

    // Highlight active test case buttons
    const buttons = document.querySelectorAll('.btn-test-case');
    buttons.forEach(b => b.classList.toggle('is-active', parseInt(b.getAttribute('data-test')) === tcNum));

    try {
        const res = await fetch('/api/cv/trigger-test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ test_case: tcNum })
        });
        if (res.ok) {
            const data = await res.json();
            console.log(`[SentraX Test Suite] Triggered Test Case ${tcNum}:`, data);
            if (data.fused_telemetry) {
                updateTelemetryUI(data.fused_telemetry);
            }
            if (data.fusion_table) {
                renderFusionTable(data.fusion_table);
            }
            await pollFusionAndCV();
        }
    } catch (err) {
        console.error(`Error triggering test case ${tcNum}:`, err);
    }
}

function initScenarioDeck() {
    const buttons = document.querySelectorAll('.btn-test-case');
    buttons.forEach(btn => {
        btn.addEventListener('click', async () => {
            const tcNum = parseInt(btn.getAttribute('data-test'));
            if (tcNum) await executeTestCase(tcNum);
        });
    });

    const btnRunSelected = document.getElementById('btn-run-selected-scenario');
    const selectPicker = document.getElementById('select-scenario-picker');
    if (btnRunSelected && selectPicker) {
        btnRunSelected.addEventListener('click', async () => {
            const tcNum = parseInt(selectPicker.value);
            if (tcNum) await executeTestCase(tcNum);
        });
    }

    const btnToggleDrawer = document.getElementById('btn-toggle-scenario-drawer');
    const drawer = document.getElementById('scenario-full-drawer');
    if (btnToggleDrawer && drawer) {
        btnToggleDrawer.addEventListener('click', () => {
            const open = drawer.classList.toggle('open');
            btnToggleDrawer.textContent = open ? 'Hide cases' : 'All 14 cases';
        });
    }
}

async function pollFusionAndCV() {
    try {
        // 1. Poll Live 5-Column Fusion Table
        const resTable = await fetch('/api/fusion/table');
        if (resTable.ok) {
            const tableRows = await resTable.json();
            renderFusionTable(tableRows);
        }

        // 2. Poll CV Telemetry & Tracking Stats
        const resStats = await fetch('/api/cv/stats');
        if (resStats.ok) {
            const stats = await resStats.json();
            state.cvStats = stats;
            renderCVStats(stats);
        }
    } catch (err) {
        // Silent catch for background poll
    }
}

function renderFusionTable(rows) {
    const tbody = document.getElementById('tbody-fusion-matrix');
    if (!tbody || !Array.isArray(rows) || rows.length === 0) return;
    const esc = window.SentraxUI ? window.SentraxUI.escapeHtml : (v) => v;

    tbody.innerHTML = rows.map(r => {
        const fUpper = (r.final || '').toUpperCase();
        let result = `<span class="result-muted">${esc(r.final)}</span>`;
        if (fUpper.includes('CONFIRMED')) {
            result = `<span class="chip chip-good">${esc(r.final)}</span>`;
        } else if (fUpper.includes('MISMATCH') || fUpper.includes('POSSIBLE')) {
            result = `<span class="chip chip-warn">${esc(r.final)}</span>`;
        } else if (fUpper.includes('SENSOR ONLY') || fUpper.includes('CAMERA ONLY') || fUpper.includes('CAMERA DETECTED')) {
            result = `<span class="chip">${esc(r.final)}</span>`;
        }
        const conf = r.confidence && r.confidence !== '--' ? r.confidence : '--';
        return `
            <tr class="fusion-table-row" title="Open the decision audit">
                <td class="event-type">${esc(r.event)}</td>
                <td>${esc(r.sensor)}</td>
                <td>${esc(r.camera)}</td>
                <td>${result}</td>
                <td class="mono">${esc(conf)}</td>
            </tr>
        `;
    }).join('');

    tbody.querySelectorAll('.fusion-table-row').forEach(tr => {
        tr.addEventListener('click', () => {
            openDecisionAudit("latest");
        });
    });
}

function initDecisionAuditModal() {
    const btnInspect = document.getElementById('btn-inspect-latest-decision');
    const btnBannerAudit = document.getElementById('btn-banner-inspect-audit');
    const modal = document.getElementById('modal-explain-audit');
    const btnClose = document.getElementById('btn-close-audit');
    const btnCloseFooter = document.getElementById('btn-close-audit-footer');

    if (btnInspect) {
        btnInspect.addEventListener('click', async () => {
            await openDecisionAudit("latest");
        });
    }
    if (btnBannerAudit) {
        btnBannerAudit.addEventListener('click', async () => {
            await openDecisionAudit("latest");
        });
    }

    const closeModal = () => {
        if (modal) modal.classList.remove('active');
    };

    if (btnClose) btnClose.addEventListener('click', closeModal);
    if (btnCloseFooter) btnCloseFooter.addEventListener('click', closeModal);
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
    }
}

async function openDecisionAudit(eventId = "latest") {
    const modal = document.getElementById('modal-explain-audit');
    if (!modal) return;

    try {
        const res = await fetch(`/api/fusion/explain/${eventId}`);
        if (!res.ok) return;
        const data = await res.json();

        setText('audit-event-title', data.title || 'Decision Audit');
        setText('audit-event-time', `Timestamp: ${data.formatted_time || '--'}`);
        setText('audit-event-id', `ID: ${data.event_id || '--'}`);

        const badgeStatus = document.getElementById('audit-badge-status');
        if (badgeStatus) {
            badgeStatus.textContent = data.match_status || 'CONFIRMED';
            badgeStatus.className = 'chip ' + ((data.match_status || '').includes('CONFIRMED') ? 'chip-good' : 'chip-warn');
        }

        const badgeSev = document.getElementById('audit-event-severity');
        if (badgeSev) {
            badgeSev.textContent = data.severity || 'INFO';
            badgeSev.className = 'chip ' + ((data.severity === 'CRITICAL' || data.severity === 'HIGH') ? 'chip-crit' : 'chip-muted');
        }

        const audit = data.audit || {};
        setText('audit-q1', audit['1_sensor_detection'] || '--');
        setText('audit-q2', audit['2_camera_detection'] || '--');
        setText('audit-q3', audit['3_did_they_agree'] || '--');
        setText('audit-q4', audit['4_confidence_score'] || '--');
        setText('audit-q5', audit['5_confirmation_reason'] || '--');
        setText('audit-q6', audit['6_risk_score_impact'] || '--');
        setText('audit-q7', audit['7_road_health_impact'] || '--');
        setText('audit-q8', audit['8_recommended_speed_rationale'] || '--');

        modal.classList.add('active');
    } catch (err) {
        console.error('Error fetching decision audit:', err);
    }
}

function renderCVStats(s) {
    if (!s) return;
    const esc = window.SentraxUI ? window.SentraxUI.escapeHtml : (v) => v;

    const elConn = document.getElementById('cv-stat-connected');
    if (elConn) {
        elConn.textContent = s.camera_connected ? 'LIVE' : 'SYNTHETIC';
        elConn.className = 'chip ' + (s.camera_connected ? 'chip-good' : 'chip-warn');
    }

    const elSrc = document.getElementById('cv-stat-source-name');
    if (elSrc) elSrc.textContent = s.device_name || s.camera_source || 'Webcam';

    setText('cv-stat-fps', typeof s.camera_fps === 'number' ? s.camera_fps.toFixed(1) : (s.camera_fps || '0.0'));
    setText('cv-stat-resolution', s.camera_resolution || '640x360');
    setText('cv-stat-latency', typeof s.camera_latency_ms === 'number' ? Math.round(s.camera_latency_ms) : (s.camera_latency_ms || '0'));
    setText('cv-stat-detection', s.detection_status || 'ACTIVE');
    setText('cv-stat-tracking', s.tracking_status || '0 OBJECTS');

    const list = document.getElementById('tbody-cv-tracks');
    if (!list) return;
    const tracks = s.tracks || [];
    if (tracks.length === 0) {
        list.innerHTML = '<div class="empty-inline">No vehicles in view. Point the camera at the road or pick the synthetic source.</div>';
        return;
    }
    list.innerHTML = tracks.map(t => {
        let status = '<span class="chip chip-good">Moving</span>';
        if (t.is_stalled || (t.is_stationary && t.stationary_duration_seconds >= 5)) {
            status = '<span class="chip chip-crit">Stalled</span>';
        } else if (t.is_stationary) {
            status = `<span class="chip chip-warn">Stopped ${t.stationary_duration_seconds.toFixed(0)} s</span>`;
        } else if (t.direction === 'OPPOSITE') {
            status = '<span class="chip chip-crit">Wrong way</span>';
        }
        const speed = t.estimated_speed_kmh > 0 ? `${t.estimated_speed_kmh.toFixed(1)} km/h` : '--';
        return `
            <div class="track-row">
                <span class="track-id">${esc(t.tracking_id)}</span>
                <span class="track-class">${esc(t.classification)} <em>${Math.round(t.confidence * 100)}%</em></span>
                <span class="track-speed">${speed}</span>
                ${status}
            </div>
        `;
    }).join('');
}

