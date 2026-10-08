/**
 * SentraX UI layer
 * Visual behaviour that sits on top of app.js (which owns hardware pairing and telemetry):
 *  - Chart.js theme, risk gauge, state coloring of live readings
 *  - Page subtitles, lazy camera stream, Road Intelligence data + scroll-spy
 *  - Event History table and Settings copilot status
 * app.js keeps writing values into the DOM; this file observes those writes instead of
 * re-implementing them, so the pairing / telemetry logic stays untouched.
 */

(() => {
    const css = getComputedStyle(document.documentElement);
    const token = (name) => css.getPropertyValue(name).trim();

    // ---------------------------------------------------------------------
    // Chart.js theme (runs before app.js creates its charts)
    // ---------------------------------------------------------------------
    if (window.Chart) {
        Chart.defaults.font.family = '"Geist Mono", ui-monospace, monospace';
        Chart.defaults.font.size = 11;
        Chart.defaults.color = token('--muted') || '#8A93AD';
        Chart.defaults.borderColor = token('--border') || '#1F2842';
        Chart.defaults.plugins.legend.display = false;
        Chart.defaults.plugins.tooltip.backgroundColor = '#141B2F';
        Chart.defaults.plugins.tooltip.borderColor = '#2C3757';
        Chart.defaults.plugins.tooltip.borderWidth = 1;
        Chart.defaults.plugins.tooltip.titleColor = '#E8ECF5';
        Chart.defaults.plugins.tooltip.bodyColor = '#B4BCD0';
        Chart.defaults.plugins.tooltip.padding = 10;
        Chart.defaults.plugins.tooltip.cornerRadius = 8;
        Chart.defaults.elements.point.radius = 0;
        Chart.defaults.elements.point.hoverRadius = 4;
        Chart.defaults.elements.line.borderWidth = 2;
        Chart.defaults.scale.grid.color = 'rgba(31, 40, 66, 0.7)';
        Chart.defaults.scale.border.display = false;
        Chart.defaults.animation.duration = 400;
    }

    const $ = (id) => document.getElementById(id);

    const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));

    const titleCase = (s) => String(s || '').toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

    // ---------------------------------------------------------------------
    // Live state coloring: map the text app.js writes to a semantic state
    // ---------------------------------------------------------------------
    const STATE_MAP = {
        good: ['LIGHT', 'DRY', 'CLEAR', 'NONE', 'CONNECTED'],
        warn: ['CONGESTED', 'WET', 'INTERRUPTED', 'HIGH_TEMP', 'MODERATE'],
        crit: ['STANDSTILL', 'IMPACT DETECTED', 'OCCUPIED', 'PRIORITY AMBULANCE', 'PRIORITY'],
        info: ['DAYTIME', 'ACTIVE', 'NIGHT'],
        muted: ['STANDBY', '--']
    };

    function stateFor(text) {
        const t = String(text || '').trim().toUpperCase();
        for (const [state, words] of Object.entries(STATE_MAP)) {
            if (words.some((w) => t === w || t.startsWith(w + ' ') || t.endsWith('(' + w + ')'))) return state;
        }
        return '';
    }

    function watchText(el, onChange) {
        if (!el) return;
        onChange(el.textContent);
        new MutationObserver(() => onChange(el.textContent))
            .observe(el, { childList: true, characterData: true, subtree: true });
    }

    function initStateText() {
        document.querySelectorAll('.state-text').forEach((el) => {
            watchText(el, (txt) => { el.dataset.state = stateFor(txt); });
        });
        for (let i = 1; i <= 4; i++) {
            const el = $(`ir-${i}-status`);
            watchText(el, (txt) => {
                const s = stateFor(txt);
                if (el && el.parentElement) el.parentElement.dataset.state = s;
            });
        }
    }

    const hasGsap = typeof window.gsap !== 'undefined';
    const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const animate = hasGsap && !reduceMotion;
    if (hasGsap) document.documentElement.classList.add('has-gsap');

    // ---------------------------------------------------------------------
    // Telemetry events: app.js owns the data, visuals listen for these
    // ---------------------------------------------------------------------
    function hookTelemetry() {
        if (typeof window.updateTelemetryUI === 'function') {
            const original = window.updateTelemetryUI;
            window.updateTelemetryUI = function (t) {
                original(t);
                if (t && t.esp32_connected) {
                    document.dispatchEvent(new CustomEvent('sx:telemetry', { detail: t }));
                }
            };
        }
        if (typeof window.resetDashboardToStandby === 'function') {
            const original = window.resetDashboardToStandby;
            window.resetDashboardToStandby = function (reason) {
                original(reason);
                document.dispatchEvent(new CustomEvent('sx:standby'));
            };
        }
    }

    function initConditions() {
        const set = (id, v) => { const el = $(id); if (el && el.textContent !== v) el.textContent = v; };
        document.addEventListener('sx:telemetry', (e) => {
            const t = e.detail;
            set('cc-temp', `${Number(t.temperature_c || 0).toFixed(1)} °C`);
            set('cc-hum', `${Number(t.humidity_pct || 0).toFixed(0)} %`);
            set('cc-rfid', t.rfid_active ? 'PRIORITY' : 'NONE');
            set('cc-night', t.night_mode ? 'NIGHT' : 'DAYTIME');
        });
        document.addEventListener('sx:standby', () => {
            set('cc-temp', '--');
            set('cc-hum', '--');
            set('cc-rfid', 'STANDBY');
            set('cc-night', 'STANDBY');
        });
    }

    // ---------------------------------------------------------------------
    // Risk dial: ticks, sprung needle, band label
    // ---------------------------------------------------------------------
    const DIAL_C = 110;
    const dialAngle = (score) => -120 + score * 2.4;

    function buildDialTicks() {
        const g = $('dial-ticks');
        if (!g) return;
        const ns = 'http://www.w3.org/2000/svg';
        for (let v = 0; v <= 100; v += 5) {
            const a = (dialAngle(v) * Math.PI) / 180;
            const major = v % 25 === 0;
            const r0 = major ? 63 : 67;
            const r1 = 72;
            const line = document.createElementNS(ns, 'line');
            line.setAttribute('x1', DIAL_C + r0 * Math.sin(a));
            line.setAttribute('y1', DIAL_C - r0 * Math.cos(a));
            line.setAttribute('x2', DIAL_C + r1 * Math.sin(a));
            line.setAttribute('y2', DIAL_C - r1 * Math.cos(a));
            if (major) line.setAttribute('class', 'major');
            g.appendChild(line);
            if (major) {
                const text = document.createElementNS(ns, 'text');
                text.setAttribute('x', DIAL_C + 53 * Math.sin(a));
                text.setAttribute('y', DIAL_C - 53 * Math.cos(a));
                text.textContent = v;
                g.appendChild(text);
            }
        }
    }

    function initGauge() {
        buildDialTicks();
        const fill = $('gauge-fill');
        const needle = $('dial-needle');
        const band = $('risk-band-label');
        const overlay = $('hardware-standby-overlay');
        let lastScore = null;

        const setNeedle = (score) => {
            if (animate) {
                gsap.to(needle, { rotation: dialAngle(score), svgOrigin: `${DIAL_C} ${DIAL_C}`, duration: 1.2, ease: 'elastic.out(1, 0.5)', overwrite: true });
                gsap.to(fill, { strokeDashoffset: 100 - score, duration: 0.9, ease: 'power3.out', overwrite: true });
            } else {
                needle?.setAttribute('transform', `rotate(${dialAngle(score)} ${DIAL_C} ${DIAL_C})`);
                if (fill) fill.style.strokeDashoffset = String(100 - score);
            }
        };

        watchText($('val-risk-score'), (txt) => {
            const score = Math.max(0, Math.min(100, parseFloat(txt) || 0));
            if (score !== lastScore) {
                lastScore = score;
                setNeedle(score);
            }
            if (!band) return;
            const standby = overlay && !overlay.classList.contains('hidden');
            let label = 'Low risk';
            let key = 'good';
            if (standby) { label = 'Standby'; key = 'standby'; }
            else if (score >= 65) { label = 'Critical risk'; key = 'critical'; }
            else if (score >= 35) { label = 'Elevated risk'; key = 'warning'; }
            if (band.textContent !== label) band.textContent = label;
            band.dataset.band = key;
        });
    }

    // Speed sign flips like a variable message sign when the advisory changes
    function initSpeedSign() {
        const sign = $('speed-sign');
        let last = null;
        watchText($('val-rec-speed'), (txt) => {
            const v = txt.trim();
            if (last !== null && v !== last && animate && sign) {
                gsap.fromTo(sign, { rotationY: -90, transformPerspective: 700 }, { rotationY: 0, duration: 0.8, ease: 'back.out(1.6)' });
            }
            last = v;
        });
    }

    // Cursor spotlight on cards (one listener, rAF-throttled)
    function initSpotlight() {
        if (reduceMotion || matchMedia('(hover: none)').matches) return;
        let pending = null;
        let queued = false;
        document.addEventListener('pointermove', (e) => {
            pending = e;
            if (queued) return;
            queued = true;
            requestAnimationFrame(() => {
                queued = false;
                const ev = pending;
                const card = ev.target && ev.target.closest ? ev.target.closest('.card') : null;
                if (card) {
                    const r = card.getBoundingClientRect();
                    card.style.setProperty('--mx', `${ev.clientX - r.left}px`);
                    card.style.setProperty('--my', `${ev.clientY - r.top}px`);
                }
            });
        }, { passive: true });
    }

    // ---------------------------------------------------------------------
    // Entrances
    // ---------------------------------------------------------------------
    const REVEAL_SELECTOR = [
        ':scope > .corridor-hero', ':scope > .grid-12 > *', ':scope > .aerial-layout-grid > .card',
        ':scope > .aerial-layout-grid > .aerial-sidebar-column > .card', ':scope > .settings-grid > *',
        ':scope > .placeholder', ':scope > .subnav', ':scope > section.card',
        '#intel-risk .section-head', '#intel-risk .card'
    ].join(', ');

    function revealPage(page) {
        if (!animate || !page) return;
        const items = [...page.querySelectorAll(REVEAL_SELECTOR)].slice(0, 16);
        gsap.fromTo(items, { y: 22, opacity: 0 }, {
            y: 0, opacity: 1, duration: 0.8, ease: 'expo.out', stagger: 0.045, clearProps: 'transform,opacity', overwrite: true
        });
    }

    function initSectionReveals() {
        if (!animate) return;
        const scroller = $('content-scroll');
        const io = new IntersectionObserver((entries) => {
            entries.forEach((en) => {
                if (!en.isIntersecting || en.target.dataset.revealed) return;
                en.target.dataset.revealed = '1';
                const items = en.target.querySelectorAll('.section-head, .card, .metric-cell');
                gsap.fromTo(items, { y: 28, opacity: 0 }, { y: 0, opacity: 1, duration: 0.9, ease: 'expo.out', stagger: 0.06, clearProps: 'transform,opacity' });
            });
        }, { root: scroller, rootMargin: '0px 0px -12% 0px' });
        document.querySelectorAll('.intel-section:not(#intel-risk)').forEach((s) => io.observe(s));
    }

    function initGateIntro() {
        const overlay = $('hardware-standby-overlay');
        if (!overlay) return;
        if (animate && !overlay.classList.contains('hidden')) {
            const tl = gsap.timeline({ defaults: { ease: 'expo.out' } });
            tl.from('.gate-lockup', { opacity: 0, y: 16, duration: 0.7 })
                .from('.gate-title .line > span', { yPercent: 110, duration: 0.9, stagger: 0.08 }, '-=0.5')
                .from('.gate-lede, .gate-actions', { opacity: 0, y: 18, duration: 0.7, stagger: 0.07 }, '-=0.6')
                .from('.gate-module', { opacity: 0, x: 40, duration: 0.9 }, '-=0.7')
                .from('.gate-subsystems li', { opacity: 0, x: 16, duration: 0.5, stagger: 0.05 }, '-=0.6');
        }
        // When the ESP32 starts streaming, the dashboard "unlocks" with a staggered entrance
        let wasHidden = overlay.classList.contains('hidden');
        new MutationObserver(() => {
            const hidden = overlay.classList.contains('hidden');
            if (hidden && !wasHidden) revealPage(document.querySelector('.page-container.active'));
            wasHidden = hidden;
        }).observe(overlay, { attributes: true, attributeFilter: ['class'] });
    }

    function countUp(el, to, decimals, suffixHtml) {
        if (!el) return;
        if (!animate) { el.innerHTML = `${Number(to).toFixed(decimals)}${suffixHtml}`; return; }
        const obj = { v: parseFloat(el.textContent) || 0 };
        gsap.to(obj, {
            v: Number(to), duration: 1.2, ease: 'power3.out',
            onUpdate: () => { el.innerHTML = `${obj.v.toFixed(decimals)}${suffixHtml}`; }
        });
    }

    // Risk factor rows: tint the marker by the weight in "(+NN)"
    function initFactorList(listId) {
        const list = $(listId);
        if (!list) return;
        const tag = () => {
            list.querySelectorAll('li').forEach((li) => {
                const m = li.textContent.match(/\(\+(\d+)\)/);
                const w = m ? parseInt(m[1], 10) : 0;
                if (/clear|normal|baseline/i.test(li.textContent) && !m) li.dataset.weight = 'good';
                else li.dataset.weight = w >= 40 ? 'crit' : (w >= 15 ? 'warn' : '');
            });
        };
        tag();
        new MutationObserver(tag).observe(list, { childList: true });
    }

    // ---------------------------------------------------------------------
    // Page switching hooks (subtitle, scroll reset, per-page data)
    // ---------------------------------------------------------------------
    const pageHooks = {
        intelligence: { enter: enterIntelligence, leave: leaveIntelligence },
        events: { enter: () => loadEvents() },
        settings: { enter: loadAiStatus }
    };
    let currentTab = 'command-center';

    function onTabChanged(tabId) {
        if (tabId === currentTab) return;
        pageHooks[currentTab]?.leave?.();
        currentTab = tabId;
        const page = $(`page-${tabId}`);
        const sub = $('current-page-sub');
        if (page && sub) sub.textContent = page.dataset.sub || '';
        const scroller = $('content-scroll');
        if (scroller) scroller.scrollTop = 0;
        pageHooks[tabId]?.enter?.();
        revealPage(page);
        document.dispatchEvent(new CustomEvent('sx:tab', { detail: tabId }));
    }

    function hookNavigation() {
        // app.js's switchTab is a global function declaration; wrap it so every caller
        // (nav clicks and programmatic switches) also runs the UI hooks.
        if (typeof window.switchTab === 'function' && !window.switchTab.__sxWrapped) {
            const original = window.switchTab;
            const wrapped = function (tabId) {
                original(tabId);
                onTabChanged(tabId);
            };
            wrapped.__sxWrapped = true;
            window.switchTab = wrapped;
        }
        $('rail-brand')?.addEventListener('click', (e) => {
            e.preventDefault();
            window.switchTab?.('command-center');
        });
    }

    // ---------------------------------------------------------------------
    // Road Intelligence
    // ---------------------------------------------------------------------
    let intelTimer = null;
    let cvTimer = null;

    function enterIntelligence() {
        const feed = $('cv-feed');
        if (feed && !feed.getAttribute('src')) feed.src = feed.dataset.src;
        loadAnalytics();
        loadRoadHealth();
        loadCvStats();
        intelTimer = setInterval(() => { loadAnalytics(); loadRoadHealth(); }, 15000);
        cvTimer = setInterval(loadCvStats, 3000);
    }

    function leaveIntelligence() {
        // Close the MJPEG connection while the camera is off-screen
        const feed = $('cv-feed');
        if (feed) feed.removeAttribute('src');
        clearInterval(intelTimer);
        clearInterval(cvTimer);
    }

    const CRIT_TYPES = new Set(['COLLISION', 'WRONG_WAY', 'NEAR_COLLISION']);
    const WARN_TYPES = new Set(['STALLED', 'OVERSPEED', 'CONGESTION', 'WET_ROAD', 'POTHOLE', 'HIGH_TEMP', 'TRAFFIC_JAM']);

    async function loadAnalytics() {
        try {
            const res = await fetch('/api/analytics');
            if (!res.ok) return;
            const a = await res.json();
            countUp($('an-total'), a.total_events_logged ?? 0, 0, '');
            countUp($('an-speed'), a.average_speed_kmh ?? 0, 1, '<small class="metric-unit"> km/h</small>');
            const types = Object.entries(a.events_by_type || {}).sort((x, y) => y[1] - x[1]);
            const box = $('an-by-type');
            if (!types.length) {
                box.innerHTML = '<div class="empty-inline">No incidents recorded yet. Counts appear here as the corridor logs events.</div>';
            } else {
                const max = Math.max(...types.map(([, n]) => n));
                box.innerHTML = types.map(([type, n]) => {
                    const tone = CRIT_TYPES.has(type) ? 'crit' : (WARN_TYPES.has(type) ? 'warn' : '');
                    const pct = Math.max(2, Math.round((n / max) * 100));
                    return `<div class="type-bar">
                        <span class="type-bar-label">${escapeHtml(titleCase(type))}</span>
                        <span><span class="type-bar-fill ${tone}" style="display:block;width:${pct}%"></span></span>
                        <span class="type-bar-count">${n}</span>
                    </div>`;
                }).join('');
            }
            $('an-updated').textContent = `Updated ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
        } catch (err) {
            console.warn('[SentraX UI] analytics unavailable', err);
        }
    }

    const BAND_CHIP = { GOOD: 'chip-good', MODERATE: 'chip-warn', POOR: 'chip-poor', CRITICAL: 'chip-crit' };

    async function loadRoadHealth() {
        try {
            const res = await fetch('/api/road-health');
            if (!res.ok) return;
            const h = await res.json();
            const band = String(h.health_band || '').toUpperCase();
            const chip = $('rh-band');
            chip.textContent = band ? `${titleCase(band)} health` : 'Unknown';
            chip.className = `chip ${BAND_CHIP[band] || 'chip-muted'}`;
            const factors = h.deterioration_factors || [];
            $('rh-factors').innerHTML = factors.length
                ? factors.map((f) => `<li data-weight="warn">${escapeHtml(f)}</li>`).join('')
                : '<li data-weight="good">No deterioration factors detected</li>';
            countUp($('an-health'), h.road_health_score ?? 0, 0, '<small class="metric-unit"> /100</small>');
            countUp($('rh-score'), h.road_health_score ?? 0, 0, '');
            $('an-health-band').textContent = band ? `${titleCase(band)} band, prototype score` : 'Prototype score';
        } catch (err) {
            console.warn('[SentraX UI] road health unavailable', err);
        }
    }

    async function loadCvStats() {
        try {
            const res = await fetch('/api/cv/stats');
            if (!res.ok) return;
            const s = await res.json();
            $('cv-vehicles').textContent = s.vehicle_count ?? 0;
            $('cv-potholes').textContent = s.pothole_count ?? 0;
            $('cv-stopped').textContent = s.stopped_vehicle_count ?? 0;
            $('cv-wrongway').textContent = s.wrong_way_count ?? 0;
        } catch (err) {
            /* camera pipeline busy; keep last values */
        }
    }

    function initSubnav() {
        const nav = $('intel-subnav');
        const scroller = $('content-scroll');
        if (!nav || !scroller) return;
        const links = [...nav.querySelectorAll('.subnav-link')];
        const setActive = (id) => links.forEach((l) => l.classList.toggle('active', l.getAttribute('href') === `#${id}`));

        links.forEach((link) => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const target = document.querySelector(link.getAttribute('href'));
                if (!target) return;
                setActive(target.id);
                const top = target.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop - 64;
                scroller.scrollTo({ top, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
            });
        });

        const io = new IntersectionObserver((entries) => {
            const visible = entries.filter((en) => en.isIntersecting)
                .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
            if (visible[0]) setActive(visible[0].target.id);
        }, { root: scroller, rootMargin: '-90px 0px -55% 0px', threshold: 0 });
        document.querySelectorAll('.intel-section').forEach((s) => io.observe(s));
    }

    // ---------------------------------------------------------------------
    // Event History
    // ---------------------------------------------------------------------
    let eventSeverity = '';
    const SEVERITY_CHIP = { CRITICAL: 'chip-crit', WARNING: 'chip-warn', INFO: 'chip-muted' };

    async function loadEvents() {
        const body = $('events-table-body');
        if (!body) return;
        try {
            const qs = new URLSearchParams({ limit: '200' });
            if (eventSeverity) qs.set('severity', eventSeverity);
            const res = await fetch(`/api/events?${qs}`);
            const events = res.ok ? await res.json() : [];
            if (!events.length) {
                body.innerHTML = `<tr class="empty-row"><td colspan="5">${eventSeverity ? 'No events at this severity.' : 'No incidents logged yet. Events appear here once the ESP32 reports them.'}</td></tr>`;
                return;
            }
            body.innerHTML = events.map((e) => {
                const d = new Date((e.timestamp || 0) * 1000);
                const when = `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })}, ${d.toLocaleTimeString()}`;
                const sev = String(e.severity || 'INFO').toUpperCase();
                return `<tr>
                    <td class="mono">${escapeHtml(when)}</td>
                    <td class="event-type">${escapeHtml(titleCase(e.type))}</td>
                    <td><span class="chip ${SEVERITY_CHIP[sev] || 'chip-muted'}">${escapeHtml(titleCase(sev))}</span></td>
                    <td class="mono">${escapeHtml(e.source)}</td>
                    <td>${escapeHtml(e.title)}${e.description ? `<div class="card-sub">${escapeHtml(e.description)}</div>` : ''}</td>
                </tr>`;
            }).join('');
        } catch (err) {
            body.innerHTML = '<tr class="empty-row"><td colspan="5">Could not load the event log. Check that the SentraX server is running.</td></tr>';
        }
    }

    function initEvents() {
        const filter = $('events-filter');
        filter?.querySelectorAll('.seg').forEach((btn) => {
            btn.addEventListener('click', () => {
                filter.querySelectorAll('.seg').forEach((b) => b.classList.toggle('active', b === btn));
                eventSeverity = btn.dataset.severity || '';
                loadEvents();
            });
        });
        $('btn-refresh-events')?.addEventListener('click', () => loadEvents());
    }

    // ---------------------------------------------------------------------
    // Settings: copilot status
    // ---------------------------------------------------------------------
    async function loadAiStatus() {
        try {
            const res = await fetch('/api/ai/status');
            if (!res.ok) return;
            const s = await res.json();
            $('ai-model').textContent = s.model;
            $('ai-effort').textContent = titleCase(s.effort);
            const chip = $('ai-key-state');
            chip.textContent = s.api_key_configured ? 'Configured' : 'Not set';
            chip.className = `chip ${s.api_key_configured ? 'chip-good' : 'chip-warn'}`;
        } catch (err) {
            /* backend restarting */
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        hookNavigation();
        hookTelemetry();
        initStateText();
        initConditions();
        initGauge();
        initSpeedSign();
        initSpotlight();
        initSectionReveals();
        initGateIntro();
        initFactorList('risk-reasons-list');
        initSubnav();
        initEvents();
        const kbd = $('kbd-hint');
        if (kbd && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)) kbd.textContent = '⌘ K';
    });

    window.SentraxUI = { escapeHtml };
})();
