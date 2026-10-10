/**
 * SentraX live visuals
 *  1. Corridor canvas (Command Center): a top-down twin of the physical testbed driven by
 *     telemetry. Cars appear only where an IR sensor reports occupancy, LED strips follow the
 *     firmware's alert patterns, and lane markings move at a rate tied to the measured speed.
 *  2. Gate light trails: long-exposure night traffic behind the pairing screen.
 *  3. Sensor sparklines on Live Telemetry.
 * Telemetry arrives through the `sx:telemetry` / `sx:standby` events dispatched by ui.js.
 */

(() => {
    const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const $ = (id) => document.getElementById(id);

    const COLORS = {
        good: [63, 182, 139],
        warn: [224, 166, 59],
        amber: [235, 160, 70],
        crit: [229, 52, 43],
        info: [142, 162, 232],
        white: [243, 239, 233],
        off: [52, 47, 42]
    };
    const rgba = (c, a) => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})`;

    let telemetry = null;      // latest telemetry while the ESP32 is live, else null
    let lastSpeed = 0;

    // -----------------------------------------------------------------
    // Corridor state (mirrors the E-Ink alert priority in app.js)
    // -----------------------------------------------------------------
    function corridorState(t) {
        if (!t) return { tone: 'standby', label: 'Awaiting signal', sub: 'Pair the ESP32 to stream live data', pattern: 'off' };
        const occupied = (t.ir_sensors || []).map(Boolean);
        const stalledIdx = occupied.findIndex(Boolean);
        if (t.vehicle_toppled) return { tone: 'crit', label: 'Vehicle toppled', sub: 'Rollover on the corridor', pattern: 'collision' };
        if (t.collision || t.sound_active) return { tone: 'crit', label: 'Accident ahead', sub: 'Slow down, impact detected', pattern: 'collision' };
        if (t.wrong_way) return { tone: 'crit', label: 'Wrong-way vehicle', sub: 'Stop and turn around', pattern: 'wrongway' };
        if (t.stalled_vehicle) return { tone: 'warn', label: 'Stalled vehicle', sub: stalledIdx >= 0 ? `Lane obstruction at IR${stalledIdx + 1}` : 'Lane obstruction', pattern: 'stalled' };
        if (t.rfid_active || t.emergency_vehicle) return { tone: 'crit', label: 'Emergency vehicle', sub: 'Yield right of way', pattern: 'emergency' };
        if (t.traffic_level === 'CONGESTED' || t.traffic_level === 'STANDSTILL') return { tone: 'warn', label: 'Congestion', sub: 'Advisory speed 60 km/h', pattern: 'congestion' };
        if (t.road_condition === 'WET') return { tone: 'info', label: 'Wet road surface', sub: 'Advisory speed 40 km/h', pattern: 'wet' };
        if ((t.temperature_c || 0) >= 30) return { tone: 'warn', label: 'High road temperature', sub: 'Advisory speed 35 km/h', pattern: 'heat' };
        return { tone: 'clear', label: 'Road clear', sub: 'All sensors nominal', pattern: 'normal' };
    }

    // -----------------------------------------------------------------
    // 1. Corridor canvas
    // -----------------------------------------------------------------
    const corridor = {
        canvas: null, ctx: null, w: 0, h: 0, dpr: 1,
        phase: 0, comets: [], impacts: [], running: false, last: 0, state: corridorState(null),

        // LED clusters per IR sensor (from firmware mapping, halves swapped 0..29 / 30..59)
        irLed: [4, 12, 19, 26],

        init() {
            this.canvas = $('corridor-canvas');
            if (!this.canvas) return;
            this.ctx = this.canvas.getContext('2d');
            new ResizeObserver(() => this.resize()).observe(this.canvas);
            this.resize();
            document.addEventListener('visibilitychange', () => this.kick());
            // Start animating as soon as the pairing screen clears
            new MutationObserver(() => this.kick()).observe($('hardware-standby-overlay'), { attributes: true, attributeFilter: ['class'] });
            this.kick();
        },

        resize() {
            const r = this.canvas.getBoundingClientRect();
            if (!r.width || !r.height) return;
            this.dpr = Math.min(window.devicePixelRatio || 1, 2);
            this.w = r.width;
            this.h = r.height;
            this.canvas.width = Math.round(r.width * this.dpr);
            this.canvas.height = Math.round(r.height * this.dpr);
            this.draw(0);
        },

        visible() {
            const gate = $('hardware-standby-overlay');
            const gateUp = gate && !gate.classList.contains('hidden');
            return !document.hidden && !gateUp && this.canvas && this.canvas.offsetParent !== null;
        },

        kick() {
            if (reduceMotion) { this.draw(0); return; }
            if (this.running || !this.visible()) return;
            this.running = true;
            this.last = performance.now();
            const loop = (now) => {
                if (!this.visible()) { this.running = false; return; }
                const dt = Math.min(0.05, (now - this.last) / 1000);
                this.last = now;
                this.draw(dt, now / 1000);
                requestAnimationFrame(loop);
            };
            requestAnimationFrame(loop);
        },

        onTelemetry(t) {
            const prev = this.state.pattern;
            this.state = corridorState(t);
            // One comet per new ultrasonic measurement; at most two on the road at once
            if (t) {
                const speed = Number(t.measured_speed_kmh || 0);
                if (speed > 0 && Math.abs(speed - lastSpeed) > 0.05) {
                    this.comets.push({ p: 0, speed });
                    if (this.comets.length > 2) this.comets.shift();
                }
                lastSpeed = speed;
            }
            if (t && this.state.pattern === 'collision' && prev !== 'collision') {
                this.impacts.push({ age: 0 });
            }
            if (reduceMotion) this.draw(0);
        },

        roadBox() {
            const top = this.h * 0.6;
            const bottom = this.h - 30;
            return { x0: 0, x1: this.w, top, bottom, mid: (top + bottom) / 2 };
        },

        ledX(i) {
            const k = i % 30;
            return 18 + (k / 29) * (this.w - 36);
        },

        ledColor(i, time, s) {
            const t = telemetry;
            if (!t) return { c: COLORS.off, a: 0.9, glow: 0 };
            const k = i % 30;
            const blink = (hz) => (Math.sin(time * Math.PI * 2 * hz) > 0 ? 1 : 0);
            const occ = (t.ir_sensors || []).map(Boolean);
            const near = (idx) => Math.abs(k - this.irLed[idx]) <= 2;
            const night = t.night_mode ? 1.25 : 1;
            switch (s.pattern) {
                case 'collision':
                    if (k >= 10 && k <= 13) return { c: COLORS.crit, a: 1, glow: blink(4) ? 1 : 0.2 };
                    return { c: COLORS.amber, a: 0.35, glow: 0.15 };
                case 'wrongway': {
                    const on = blink(3) ? i < 30 : i >= 30;
                    return { c: COLORS.crit, a: on ? 1 : 0.25, glow: on ? 1 : 0 };
                }
                case 'stalled': {
                    const idx = occ.findIndex(Boolean);
                    if (idx >= 0 && near(idx)) return { c: COLORS.warn, a: 1, glow: blink(2.5) ? 1 : 0.1 };
                    return { c: COLORS.amber, a: 0.35, glow: 0.15 };
                }
                case 'emergency': {
                    const chase = Math.floor(time * 12 + k) % 6;
                    const c = chase < 3 ? COLORS.crit : COLORS.white;
                    return { c, a: 0.95, glow: 0.8 };
                }
                case 'congestion': {
                    const pulse = 0.5 + 0.5 * Math.sin(time * 3 - k * 0.35);
                    return { c: COLORS.warn, a: 0.45 + pulse * 0.55, glow: pulse };
                }
                case 'wet': {
                    const wave = 0.5 + 0.5 * Math.sin(time * 4 - k * 0.5);
                    return { c: COLORS.info, a: 0.35 + wave * 0.65, glow: wave };
                }
                case 'heat':
                    return { c: [224, 122, 59], a: 0.9, glow: 0.6 };
                default:
                    return { c: COLORS.amber, a: 0.55 * night, glow: 0.35 * night };
            }
        },

        draw(dt, time = performance.now() / 1000) {
            const { ctx, w, h, dpr } = this;
            if (!ctx || !w) return;
            const t = telemetry;
            const s = this.state;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, w, h);
            const road = this.roadBox();

            // Lane motion tied to measured speed (still when the car is stopped)
            const speed = t ? Number(t.measured_speed_kmh || 0) : 0;
            const pxPerSec = speed > 0 ? Math.min(420, 60 + speed * 38) : 0;
            this.phase = (this.phase + pxPerSec * dt) % 64;

            // Asphalt
            const asphalt = ctx.createLinearGradient(0, road.top, 0, road.bottom);
            asphalt.addColorStop(0, '#1A1816');
            asphalt.addColorStop(1, '#121110');
            ctx.fillStyle = asphalt;
            ctx.fillRect(0, road.top, w, road.bottom - road.top);

            // Edge lines
            ctx.fillStyle = t ? 'rgba(232, 236, 245, 0.55)' : 'rgba(232, 236, 245, 0.18)';
            ctx.fillRect(0, road.top + 6, w, 2);
            ctx.fillRect(0, road.bottom - 8, w, 2);

            // Center dashes
            ctx.fillStyle = t ? 'rgba(232, 236, 245, 0.7)' : 'rgba(232, 236, 245, 0.2)';
            for (let x = -64 + this.phase; x < w + 64; x += 64) {
                ctx.fillRect(x, road.mid - 1.5, 32, 3);
            }

            // Wrong-way chevrons travelling against traffic
            if (s.pattern === 'wrongway') {
                ctx.strokeStyle = rgba(COLORS.crit, 0.85);
                ctx.lineWidth = 3;
                const lane = (road.top + road.mid) / 2;
                for (let x = w - ((time * 140) % 90); x > -40; x -= 90) {
                    ctx.beginPath();
                    ctx.moveTo(x + 12, lane - 10);
                    ctx.lineTo(x, lane);
                    ctx.lineTo(x + 12, lane + 10);
                    ctx.stroke();
                }
            }

            // IR gates
            const occ = t ? (t.ir_sensors || []).map(Boolean) : [false, false, false, false];
            this.irLed.forEach((led, i) => {
                const x = this.ledX(led);
                const hot = occ[i];
                if (hot) {
                    const g = ctx.createLinearGradient(x - 26, 0, x + 26, 0);
                    g.addColorStop(0, rgba(COLORS.crit, 0));
                    g.addColorStop(0.5, rgba(COLORS.crit, 0.35));
                    g.addColorStop(1, rgba(COLORS.crit, 0));
                    ctx.fillStyle = g;
                    ctx.fillRect(x - 26, road.top, 52, road.bottom - road.top);
                }
                ctx.strokeStyle = hot ? rgba(COLORS.crit, 0.95) : (t ? 'rgba(142, 162, 232, 0.35)' : 'rgba(142, 162, 232, 0.12)');
                ctx.lineWidth = hot ? 2 : 1;
                ctx.setLineDash(hot ? [] : [4, 5]);
                ctx.beginPath();
                ctx.moveTo(x, road.top + 2);
                ctx.lineTo(x, road.bottom - 2);
                ctx.stroke();
                ctx.setLineDash([]);

                ctx.font = '500 10px "Geist Mono", monospace';
                ctx.textAlign = 'center';
                ctx.fillStyle = hot ? rgba(COLORS.crit, 1) : 'rgba(138, 147, 173, 0.8)';
                ctx.fillText(`IR${i + 1}`, x, road.bottom + 22);

                if (hot) this.drawCar(x, (road.mid + road.bottom) / 2, s.pattern === 'stalled', time);
            });

            // Ultrasonic speed gate markers
            const us = t ? (t.ultrasonic_state || {}) : {};
            [['US1', 0.035, us.us1_active], ['US2', 0.965, us.us2_active]].forEach(([label, fx, active]) => {
                const x = fx * w;
                ctx.fillStyle = active ? rgba(COLORS.info, 1) : 'rgba(138, 147, 173, 0.45)';
                ctx.font = '500 10px "Geist Mono", monospace';
                ctx.textAlign = 'center';
                ctx.fillText(label, x, road.top - 26);
                if (active) {
                    const r = 10 + ((time * 30) % 18);
                    ctx.strokeStyle = rgba(COLORS.info, 1 - (r - 10) / 18);
                    ctx.lineWidth = 1.5;
                    ctx.beginPath();
                    ctx.arc(x, road.mid, r, 0, Math.PI * 2);
                    ctx.stroke();
                }
            });

            // Speed comet: replays each new ultrasonic measurement from US1 to US2
            const laneY = (road.mid + road.bottom) / 2;
            this.comets = this.comets.filter((c) => c.p <= 1.15);
            this.comets.forEach((c) => {
                c.p += dt * 0.85;
                const x = (0.035 + Math.min(c.p, 1) * 0.93) * w;
                const g = ctx.createLinearGradient(x - 140, 0, x, 0);
                g.addColorStop(0, rgba(COLORS.white, 0));
                g.addColorStop(1, rgba(COLORS.white, 0.85 * (1 - Math.max(0, c.p - 1) * 6)));
                ctx.strokeStyle = g;
                ctx.lineWidth = 3;
                ctx.lineCap = 'round';
                ctx.beginPath();
                ctx.moveTo(x - 140, laneY);
                ctx.lineTo(x, laneY);
                ctx.stroke();
                ctx.fillStyle = 'rgba(232, 236, 245, 0.9)';
                ctx.font = '500 11px "Geist Mono", monospace';
                ctx.textAlign = 'left';
                ctx.fillText(`${c.speed.toFixed(1)} km/h`, x + 8, laneY + 4);
            });

            // Impact ring at the acoustic sensor
            this.impacts = this.impacts.filter((im) => im.age < 1.6);
            this.impacts.forEach((im) => {
                im.age += dt;
                const x = 0.48 * w;
                const r = 12 + im.age * 120;
                ctx.strokeStyle = rgba(COLORS.crit, Math.max(0, 1 - im.age / 1.6));
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(x, road.mid, r, 0, Math.PI * 2);
                ctx.stroke();
            });

            // Roadside LED strips: 0..29 on the far edge, 30..59 on the near edge
            for (let i = 0; i < 60; i++) {
                const x = this.ledX(i);
                const y = i < 30 ? road.top - 9 : road.bottom + 6;
                const { c, a, glow } = this.ledColor(i, time, s);
                if (glow > 0.05) {
                    const g = ctx.createRadialGradient(x, y, 0, x, y, 14);
                    g.addColorStop(0, rgba(c, 0.45 * glow));
                    g.addColorStop(1, rgba(c, 0));
                    ctx.fillStyle = g;
                    ctx.fillRect(x - 14, y - 14, 28, 28);
                }
                ctx.fillStyle = rgba(c, a);
                ctx.beginPath();
                ctx.arc(x, y, 2.6, 0, Math.PI * 2);
                ctx.fill();
            }

            // Standby: a slow scan across the dark road while waiting for the ESP32
            if (!t) {
                const sx = ((time * 0.18) % 1.4 - 0.2) * w;
                const g = ctx.createLinearGradient(sx - 120, 0, sx + 120, 0);
                g.addColorStop(0, 'rgba(142, 162, 232, 0)');
                g.addColorStop(0.5, 'rgba(142, 162, 232, 0.12)');
                g.addColorStop(1, 'rgba(142, 162, 232, 0)');
                ctx.fillStyle = g;
                ctx.fillRect(sx - 120, road.top - 20, 240, road.bottom - road.top + 40);
            }
        },

        drawCar(x, y, hazard, time) {
            const ctx = this.ctx;
            const L = 46, W = 22;
            ctx.save();
            ctx.translate(x, y);
            // headlight throw
            const beam = ctx.createLinearGradient(L / 2, 0, L / 2 + 70, 0);
            beam.addColorStop(0, 'rgba(232, 236, 245, 0.28)');
            beam.addColorStop(1, 'rgba(232, 236, 245, 0)');
            ctx.fillStyle = beam;
            ctx.beginPath();
            ctx.moveTo(L / 2, -W / 2 + 3);
            ctx.lineTo(L / 2 + 70, -W);
            ctx.lineTo(L / 2 + 70, W);
            ctx.lineTo(L / 2, W / 2 - 3);
            ctx.fill();
            // body
            ctx.fillStyle = '#D9DEEA';
            ctx.beginPath();
            ctx.roundRect(-L / 2, -W / 2, L, W, 6);
            ctx.fill();
            ctx.fillStyle = '#2A2623';
            ctx.beginPath();
            ctx.roundRect(-L / 2 + 12, -W / 2 + 3, 20, W - 6, 3);
            ctx.fill();
            // tail lights, hazards blink amber when stalled
            const blinkOn = Math.sin(time * Math.PI * 2 * 1.6) > 0;
            ctx.fillStyle = hazard && blinkOn ? rgba(COLORS.warn, 1) : rgba(COLORS.crit, 0.9);
            ctx.fillRect(-L / 2, -W / 2 + 2, 3, 5);
            ctx.fillRect(-L / 2, W / 2 - 7, 3, 5);
            if (hazard && blinkOn) {
                ctx.fillRect(L / 2 - 3, -W / 2 + 2, 3, 5);
                ctx.fillRect(L / 2 - 3, W / 2 - 7, 3, 5);
            }
            ctx.restore();
        }
    };

    // -----------------------------------------------------------------
    // 2. Gate light trails (long-exposure traffic)
    // -----------------------------------------------------------------
    const trails = {
        canvas: null, ctx: null, w: 0, h: 0, dpr: 1, cars: [], running: false,

        init() {
            this.canvas = $('gate-trails');
            if (!this.canvas) return;
            this.ctx = this.canvas.getContext('2d');
            new ResizeObserver(() => this.resize()).observe(this.canvas);
            this.resize();
            const lanes = 6;
            for (let i = 0; i < 44; i++) {
                const lane = i % lanes;
                this.cars.push({
                    lane,
                    t: Math.random(),
                    v: 0.05 + Math.random() * 0.05,
                    away: lane < 3
                });
            }
            document.addEventListener('visibilitychange', () => this.kick());
            new MutationObserver(() => this.kick()).observe($('hardware-standby-overlay'), { attributes: true, attributeFilter: ['class'] });
            this.kick();
        },

        resize() {
            const r = this.canvas.getBoundingClientRect();
            if (!r.width || !r.height) return;
            this.dpr = Math.min(window.devicePixelRatio || 1, 2);
            this.w = r.width;
            this.h = r.height;
            this.canvas.width = Math.round(r.width * this.dpr);
            this.canvas.height = Math.round(r.height * this.dpr);
            if (reduceMotion) this.drawStatic();
        },

        // Lanes sweep from the lower left foreground toward a horizon on the right
        point(lane, t) {
            const { w, h } = this;
            const off = (lane - 2.5) * 14;
            const p0 = [w * 0.18, h * 1.08 + off * 2.2];
            const p1 = [w * 0.55, h * 0.95 + off * 1.4];
            const p2 = [w * 0.7, h * 0.5 + off * 0.6];
            const p3 = [w * 1.05, h * 0.38 + off * 0.25];
            const u = 1 - t;
            return [
                u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]
            ];
        },

        visible() {
            const overlay = $('hardware-standby-overlay');
            return !document.hidden && overlay && !overlay.classList.contains('hidden');
        },

        kick() {
            if (reduceMotion) { this.drawStatic(); return; }
            if (this.running || !this.visible()) return;
            this.running = true;
            let last = performance.now();
            const loop = (now) => {
                if (!this.visible()) { this.running = false; return; }
                const dt = Math.min(0.05, (now - last) / 1000);
                last = now;
                this.step(dt);
                requestAnimationFrame(loop);
            };
            requestAnimationFrame(loop);
        },

        step(dt) {
            const { ctx, dpr, w, h } = this;
            if (!ctx || !w) return;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, w, h);
            ctx.globalCompositeOperation = 'lighter';
            this.cars.forEach((c) => {
                // vehicles accelerate toward the camera, slow toward the horizon
                const dir = c.away ? 1 : -1;
                c.t += dir * c.v * dt * (c.away ? 1.2 - c.t * 0.6 : 0.6 + c.t * 0.6);
                if (c.t > 1.02) c.t = -0.02;
                if (c.t < -0.02) c.t = 1.02;
                this.drawTrail(c);
            });
            ctx.globalCompositeOperation = 'source-over';
        },

        drawTrail(c) {
            const ctx = this.ctx;
            const len = 0.16;
            const steps = 14;
            const color = c.away ? COLORS.crit : [255, 236, 214];
            const tail = c.away ? -len : len;
            for (let k = 0; k < steps; k++) {
                const a0 = c.t + (tail * k) / steps;
                const a1 = c.t + (tail * (k + 1)) / steps;
                if (a0 < 0 || a0 > 1 || a1 < 0 || a1 > 1) continue;
                const [x0, y0] = this.point(c.lane, a0);
                const [x1, y1] = this.point(c.lane, a1);
                const near = 1 - a0;
                const alpha = (1 - k / steps) * (c.away ? 0.55 : 0.5);
                ctx.strokeStyle = rgba(color, alpha * 0.35);
                ctx.lineWidth = 1 + near * 7;
                ctx.lineCap = 'round';
                ctx.beginPath();
                ctx.moveTo(x0, y0);
                ctx.lineTo(x1, y1);
                ctx.stroke();
                ctx.strokeStyle = rgba(color, alpha);
                ctx.lineWidth = 0.6 + near * 1.8;
                ctx.stroke();
            }
        },

        drawStatic() {
            if (!this.ctx || !this.w) return;
            this.cars.forEach((c, i) => { c.t = (i * 0.137) % 1; });
            this.step(0);
        }
    };

    // -----------------------------------------------------------------
    // 3. Sparklines (Live Telemetry)
    // -----------------------------------------------------------------
    const sparks = {
        series: {
            'spark-temp': { values: [], color: COLORS.info, key: (t) => t.temperature_c },
            'spark-hum': { values: [], color: COLORS.info, key: (t) => t.humidity_pct },
            'spark-moist': { values: [], color: COLORS.info, key: (t) => t.moisture_raw },
            'spark-sound': { values: [], color: COLORS.crit, key: (t) => (t.sound_active ? 1 : 0), step: true }
        },
        lastPush: 0,

        push(t) {
            const now = performance.now();
            if (now - this.lastPush < 250) return;
            this.lastPush = now;
            Object.entries(this.series).forEach(([id, s]) => {
                const v = Number(s.key(t));
                if (!Number.isFinite(v)) return;
                s.values.push(v);
                if (s.values.length > 80) s.values.shift();
            });
            this.drawAll();
        },

        clear() {
            Object.values(this.series).forEach((s) => { s.values = []; });
            this.drawAll();
        },

        drawAll() {
            Object.entries(this.series).forEach(([id, s]) => {
                const canvas = $(id);
                if (!canvas || canvas.offsetParent === null) return;
                const dpr = Math.min(window.devicePixelRatio || 1, 2);
                const w = canvas.clientWidth, h = canvas.clientHeight;
                if (!w) return;
                if (canvas.width !== Math.round(w * dpr)) {
                    canvas.width = Math.round(w * dpr);
                    canvas.height = Math.round(h * dpr);
                }
                const ctx = canvas.getContext('2d');
                ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
                ctx.clearRect(0, 0, w, h);
                const vals = s.values;
                if (vals.length < 2) {
                    ctx.strokeStyle = 'rgba(142, 162, 232, 0.15)';
                    ctx.setLineDash([3, 4]);
                    ctx.beginPath();
                    ctx.moveTo(0, h - 2);
                    ctx.lineTo(w, h - 2);
                    ctx.stroke();
                    ctx.setLineDash([]);
                    return;
                }
                let min = Math.min(...vals), max = Math.max(...vals);
                if (s.step) { min = 0; max = 1; }
                if (max - min < 1e-6) { max += 1; min -= 1; }
                const x = (i) => (i / (80 - 1)) * w + (w - ((vals.length - 1) / (80 - 1)) * w);
                const y = (v) => h - 3 - ((v - min) / (max - min)) * (h - 8);
                ctx.beginPath();
                vals.forEach((v, i) => {
                    if (i === 0) ctx.moveTo(x(i), y(v));
                    else if (s.step) { ctx.lineTo(x(i), y(vals[i - 1])); ctx.lineTo(x(i), y(v)); }
                    else ctx.lineTo(x(i), y(v));
                });
                ctx.strokeStyle = rgba(s.color, 0.95);
                ctx.lineWidth = 1.6;
                ctx.lineJoin = 'round';
                ctx.stroke();
                ctx.lineTo(x(vals.length - 1), h);
                ctx.lineTo(x(0), h);
                ctx.closePath();
                const g = ctx.createLinearGradient(0, 0, 0, h);
                g.addColorStop(0, rgba(s.color, 0.22));
                g.addColorStop(1, rgba(s.color, 0));
                ctx.fillStyle = g;
                ctx.fill();
                const lx = x(vals.length - 1), ly = y(vals[vals.length - 1]);
                ctx.fillStyle = rgba(s.color, 1);
                ctx.beginPath();
                ctx.arc(lx - 1.5, ly, 2.5, 0, Math.PI * 2);
                ctx.fill();
            });
        }
    };

    // -----------------------------------------------------------------
    // Wiring
    // -----------------------------------------------------------------
    function applyState() {
        const s = corridor.state;
        const hero = $('corridor-hero');
        if (hero && hero.dataset.tone !== s.tone) hero.dataset.tone = s.tone;
        const label = $('corridor-state');
        if (label && label.textContent !== s.label) label.textContent = s.label;
        const sub = $('corridor-state-sub');
        if (sub && sub.textContent !== s.sub) sub.textContent = s.sub;
    }

    document.addEventListener('sx:telemetry', (e) => {
        telemetry = e.detail;
        corridor.onTelemetry(telemetry);
        applyState();
        sparks.push(telemetry);
    });

    document.addEventListener('sx:standby', () => {
        if (telemetry === null) return;
        telemetry = null;
        corridor.onTelemetry(null);
        applyState();
        sparks.clear();
    });

    document.addEventListener('sx:tab', (e) => {
        if (e.detail === 'command-center') { corridor.resize(); corridor.kick(); }
        if (e.detail === 'live-telemetry') requestAnimationFrame(() => sparks.drawAll());
    });

    document.addEventListener('DOMContentLoaded', () => {
        corridor.init();
        trails.init();
        applyState();
        sparks.drawAll();
    });
})();
