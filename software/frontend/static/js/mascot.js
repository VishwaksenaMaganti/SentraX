/* ==========================================================================
   Sentri: the SentraX driver co-pilot mascot
   --------------------------------------------------------------------------
   A slim white two-legged body with Baymax's face, a faceted rock crown
   (Rocky) and an orange core (Claude Code's Clawd). Pure inline SVG + CSS so it
   works offline in the car. Each mood swaps eyes, props and pose, and plays a
   short musical chirp, Rocky-style, through Web Audio.

   Usage
     const s = Sentri.mount(el);          // render into a container
     s.setMood('rain');                   // force a mood
     s.fromTelemetry(t, connected);       // derive mood from live telemetry
   ========================================================================== */
(function () {
    'use strict';

    const MOODS = {
        standby:    { title: 'Napping',            line: 'Pair the ESP32 and I will keep watch.',      tone: 'idle' },
        clear:      { title: 'Road is clear',      line: 'Smooth driving. I am watching the corridor.', tone: 'good' },
        slowdown:   { title: 'Ease off a little',  line: 'You are above the advisory speed.',          tone: 'warn' },
        emergency:  { title: 'Ambulance behind',   line: 'Move aside and give way.',                    tone: 'crit' },
        accident:   { title: 'Accident ahead',     line: 'Slow right down. Hazard on the road.',        tone: 'crit' },
        wrong_way:  { title: 'Wrong-way vehicle',  line: 'Stay left and slow down now.',                tone: 'crit' },
        stall:      { title: 'Stalled vehicle',    line: 'Lane blocked ahead. Merge early.',            tone: 'warn' },
        congestion: { title: 'Traffic building',   line: 'Keep a safe gap. Patience pays.',             tone: 'warn' },
        rain:       { title: 'Wet road',           line: 'Grip is low. Brake early, go gentle.',        tone: 'warn' },
        heat:       { title: 'Road is hot',        line: 'Tyres soften in heat. Ease the pace.',        tone: 'warn' }
    };

    const SVG = `
<svg class="sentri-svg" viewBox="0 0 240 300" role="img" aria-label="Sentri, the SentraX co-pilot">
  <defs>
    <radialGradient id="sentri-body" cx="40%" cy="30%" r="80%">
      <stop offset="0" stop-color="#FFFFFF"/>
      <stop offset="0.62" stop-color="#F6F3EF"/>
      <stop offset="1" stop-color="#DCD5CC"/>
    </radialGradient>
    <radialGradient id="sentri-core" cx="50%" cy="50%" r="50%">
      <stop offset="0" stop-color="#FFE2C7"/>
      <stop offset="0.45" stop-color="#FF8A2A"/>
      <stop offset="1" stop-color="#F26B0F"/>
    </radialGradient>
    <filter id="sentri-glow" x="-100%" y="-100%" width="300%" height="300%">
      <feGaussianBlur stdDeviation="7"/>
    </filter>
  </defs>

  <!-- weather / scene props behind the body -->
  <g class="prop prop-heat-sun">
    <g class="sun-rays" stroke="#FF8A2A" stroke-width="4" stroke-linecap="round">
      <line x1="40" y1="14" x2="40" y2="4"/><line x1="40" y1="66" x2="40" y2="76"/>
      <line x1="14" y1="40" x2="4" y2="40"/><line x1="66" y1="40" x2="76" y2="40"/>
      <line x1="22" y1="22" x2="15" y2="15"/><line x1="58" y1="58" x2="65" y2="65"/>
      <line x1="58" y1="22" x2="65" y2="15"/><line x1="22" y1="58" x2="15" y2="65"/>
    </g>
    <circle cx="40" cy="40" r="17" fill="#FF8A2A"/>
  </g>
  <g class="prop prop-rain-drops" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round" opacity="0.85">
    <line class="drop d1" x1="30" y1="40" x2="26" y2="52"/>
    <line class="drop d2" x1="214" y1="70" x2="210" y2="82"/>
    <line class="drop d3" x1="18" y1="140" x2="14" y2="152"/>
    <line class="drop d4" x1="224" y1="170" x2="220" y2="182"/>
    <line class="drop d5" x1="46" y1="210" x2="42" y2="222"/>
  </g>
  <g class="prop prop-congestion" transform="translate(0 0)">
    <rect class="car c1" x="6"   y="262" width="34" height="16" rx="7" fill="#FFFFFF" opacity="0.9"/>
    <rect class="car c2" x="200" y="262" width="34" height="16" rx="7" fill="#FFFFFF" opacity="0.9"/>
    <circle cx="14" cy="280" r="4" fill="#3A3330"/><circle cx="32" cy="280" r="4" fill="#3A3330"/>
    <circle cx="208" cy="280" r="4" fill="#3A3330"/><circle cx="226" cy="280" r="4" fill="#3A3330"/>
  </g>

  <ellipse class="sentri-shadow" cx="120" cy="288" rx="46" ry="7" fill="#000" opacity="0.28"/>

  <g class="sentri-rig">
    <!-- two legs with little feet -->
    <g class="legs" fill="#ECE7E0" stroke="#D3CBC0" stroke-width="2">
      <g class="leg leg-l">
        <rect x="94" y="222" width="20" height="56" rx="10"/>
        <ellipse cx="101" cy="278" rx="15" ry="8"/>
      </g>
      <g class="leg leg-r">
        <rect x="126" y="222" width="20" height="56" rx="10"/>
        <ellipse cx="139" cy="278" rx="15" ry="8"/>
      </g>
    </g>

    <!-- arms -->
    <g class="arm arm-l"><ellipse cx="58" cy="174" rx="11" ry="36" fill="url(#sentri-body)" stroke="#D9D1C6" stroke-width="2"/></g>
    <g class="arm arm-r"><ellipse cx="182" cy="174" rx="11" ry="36" fill="url(#sentri-body)" stroke="#D9D1C6" stroke-width="2"/></g>

    <!-- umbrella held in the right arm -->
    <g class="prop prop-umbrella">
      <line x1="188" y1="150" x2="182" y2="46" stroke="#3A3330" stroke-width="4" stroke-linecap="round"/>
      <path d="M114 64 Q180 -6 248 40 Q232 36 218 50 Q202 34 182 46 Q162 36 146 52 Q132 40 114 64 Z" fill="#FF8A2A"/>
      <path d="M182 46 Q180 20 182 10" stroke="#FFFFFF" stroke-width="2" fill="none" opacity="0.6"/>
    </g>

    <!-- body -->
    <path class="body" d="M120 112 C150 112 170 124 172 150 C174 176 166 186 168 204 C170 228 152 240 120 240 C88 240 70 228 72 204 C74 186 66 176 68 150 C70 124 90 112 120 112 Z"
          fill="url(#sentri-body)" stroke="#D9D1C6" stroke-width="2"/>

    <!-- orange core -->
    <g class="core">
      <circle class="core-glow" cx="120" cy="166" r="18" fill="#FF8A2A" filter="url(#sentri-glow)"/>
      <circle cx="120" cy="166" r="12" fill="url(#sentri-core)" stroke="#FFFFFF" stroke-width="3"/>
      <path d="M114.5 166 L120 159.5 L125.5 166 L120 172.5 Z" fill="#FFFFFF" opacity="0.85"/>
    </g>

    <!-- head -->
    <g class="head">
      <ellipse cx="120" cy="80" rx="52" ry="42" fill="url(#sentri-body)" stroke="#D9D1C6" stroke-width="2"/>
      <!-- Rocky crown: faceted rock plates -->
      <g class="crown">
        <path d="M80 56 L92 32 L113 22 L134 24 L152 34 L162 56 L144 49 L120 45 L98 49 Z" fill="#EFEAE3" stroke="#CFC6BA" stroke-width="2" stroke-linejoin="round"/>
        <path d="M92 32 L98 49 M113 22 L120 45 M134 24 L120 45 M152 34 L144 49" stroke="#CFC6BA" stroke-width="2" fill="none"/>
      </g>
      <!-- siren for emergency -->
      <g class="prop prop-siren">
        <rect x="104" y="6" width="32" height="10" rx="3" fill="#3A3330"/>
        <path d="M108 8 Q120 -16 132 8 Z" class="siren-dome" fill="#FF8A2A"/>
      </g>

      <!-- eyes -->
      <g class="eyes eyes-normal">
        <g class="blink">
          <ellipse cx="98" cy="88" rx="7" ry="8.5" fill="#26211E"/>
          <ellipse cx="142" cy="88" rx="7" ry="8.5" fill="#26211E"/>
          <line x1="105" y1="88" x2="135" y2="88" stroke="#26211E" stroke-width="3"/>
          <circle cx="100" cy="85" r="2" fill="#FFFFFF"/><circle cx="144" cy="85" r="2" fill="#FFFFFF"/>
        </g>
      </g>
      <g class="eyes eyes-happy" fill="none" stroke="#26211E" stroke-width="5" stroke-linecap="round">
        <path d="M89 92 Q98 78 107 92"/><path d="M133 92 Q142 78 151 92"/>
      </g>
      <g class="eyes eyes-shock">
        <circle cx="98" cy="88" r="11" fill="#FFFFFF" stroke="#26211E" stroke-width="4"/>
        <circle cx="142" cy="88" r="11" fill="#FFFFFF" stroke="#26211E" stroke-width="4"/>
        <circle cx="98" cy="88" r="4.5" fill="#26211E"/><circle cx="142" cy="88" r="4.5" fill="#26211E"/>
      </g>
      <g class="eyes eyes-worry">
        <ellipse cx="98" cy="90" rx="7" ry="8" fill="#26211E"/>
        <ellipse cx="142" cy="90" rx="7" ry="8" fill="#26211E"/>
        <path d="M86 74 L106 80 M154 74 L134 80" stroke="#26211E" stroke-width="4" stroke-linecap="round"/>
        <line x1="105" y1="90" x2="135" y2="90" stroke="#26211E" stroke-width="3"/>
      </g>
      <g class="eyes eyes-squint" fill="none" stroke="#26211E" stroke-width="5" stroke-linecap="round">
        <path d="M88 86 L106 90 L88 94"/><path d="M152 86 L134 90 L152 94"/>
      </g>
      <g class="eyes eyes-closed" fill="none" stroke="#26211E" stroke-width="4" stroke-linecap="round">
        <path d="M89 88 Q98 96 107 88"/><path d="M133 88 Q142 96 151 88"/>
      </g>

      <!-- cheeks -->
      <circle class="cheek" cx="86" cy="100" r="6" fill="#FF8A2A" opacity="0.3"/>
      <circle class="cheek" cx="154" cy="100" r="6" fill="#FF8A2A" opacity="0.3"/>
      <!-- mouth: small o for shock -->
      <ellipse class="mouth-o" cx="120" cy="106" rx="4.5" ry="5.5" fill="#26211E"/>

      <!-- sweat drops -->
      <g class="prop prop-sweat" fill="#FFFFFF" stroke="#BFD9EA" stroke-width="2">
        <path class="sweat s1" d="M176 60 Q182 70 176 76 Q170 70 176 60 Z"/>
        <path class="sweat s2" d="M64 66 Q69 74 64 79 Q59 74 64 66 Z"/>
      </g>
    </g>

    <!-- traffic cone for stalled vehicle -->
    <g class="prop prop-cone"><g transform="translate(196 214)">
      <path d="M14 0 L26 52 L2 52 Z" fill="#FF8A2A"/>
      <path d="M9 22 L19 22 L21 32 L7 32 Z" fill="#FFFFFF"/>
      <rect x="-4" y="50" width="36" height="8" rx="3" fill="#3A3330"/></g>
    </g>
  </g>

  <!-- floating symbols -->
  <g class="prop prop-alert">
    <circle cx="206" cy="38" r="20" fill="#FF8A2A"/>
    <rect x="203" y="24" width="6" height="18" rx="3" fill="#FFFFFF"/>
    <circle cx="206" cy="50" r="3.5" fill="#FFFFFF"/>
  </g>
  <g class="prop prop-uturn" fill="none" stroke="#FF8A2A" stroke-width="7" stroke-linecap="round" stroke-linejoin="round">
    <path d="M30 70 L30 40 Q30 18 52 18 Q74 18 74 40 L74 54"/>
    <path d="M62 44 L74 58 L86 44"/>
  </g>
  <g class="prop prop-zzz" fill="#FFFFFF" font-family="Geist, sans-serif" font-weight="800">
    <text class="z z1" x="176" y="56" font-size="18">z</text>
    <text class="z z2" x="192" y="38" font-size="24">z</text>
    <text class="z z3" x="210" y="18" font-size="30">Z</text>
  </g>
  <g class="prop prop-sparkle" fill="#FF8A2A">
    <path class="spark k1" d="M34 50 L38 62 L50 66 L38 70 L34 82 L30 70 L18 66 L30 62 Z"/>
    <path class="spark k2" d="M206 34 L209 43 L218 46 L209 49 L206 58 L203 49 L194 46 L203 43 Z" fill="#FFFFFF"/>
    <path class="spark k3" d="M214 120 L216 126 L222 128 L216 130 L214 136 L212 130 L206 128 L212 126 Z"/>
  </g>
  <g class="prop prop-slow">
    <rect x="160" y="10" width="72" height="34" rx="17" fill="#FF8A2A"/>
    <text x="196" y="33" text-anchor="middle" font-family="Geist, sans-serif" font-size="16" font-weight="800" fill="#FFFFFF" letter-spacing="1">SLOW</text>
  </g>
</svg>`;

    /* ------------------------------------------------------------------ */
    /* Sound: short musical chirps (Rocky speaks in chords)                */
    /* ------------------------------------------------------------------ */
    const N = { C4: 261.6, D4: 293.7, E4: 329.6, G4: 392.0, A4: 440.0, C5: 523.3, D5: 587.3, E5: 659.3,
                F5: 698.5, G5: 784.0, A5: 880.0, C6: 1046.5, D6: 1174.7, E6: 1318.5, G6: 1568.0 };

    // [startSec, freq, durSec, type, glideToFreq?]
    const SONGS = {
        standby:    [[0, N.E4, 0.35, 'sine', N.C4], [0.3, N.C4, 0.45, 'sine', 220]],
        clear:      [[0, N.C5, 0.1, 'triangle'], [0.09, N.E5, 0.1, 'triangle'], [0.18, N.G5, 0.12, 'triangle'], [0.28, N.C6, 0.22, 'triangle']],
        slowdown:   [[0, N.G5, 0.18, 'triangle', N.E5], [0.2, N.D5, 0.3, 'triangle', N.A4], [0.2, N.G4, 0.3, 'sine']],
        emergency:  [[0, N.A5, 0.13, 'square'], [0.15, N.E5, 0.13, 'square'], [0.3, N.A5, 0.13, 'square'], [0.45, N.E5, 0.13, 'square'], [0.62, N.C6, 0.2, 'triangle', N.G6]],
        accident:   [[0, N.C6, 0.08, 'square'], [0.11, N.C6, 0.08, 'square'], [0.22, N.C6, 0.08, 'square'], [0.36, N.F5, 0.35, 'sawtooth', N.C5], [0.36, N.G5 * 1.06, 0.35, 'triangle']],
        wrong_way:  [[0, N.E5, 0.12, 'square', N.C5], [0.16, N.E5, 0.12, 'square', N.C5], [0.34, N.G4, 0.3, 'triangle']],
        stall:      [[0, N.D5, 0.14, 'triangle'], [0.16, N.A5, 0.22, 'triangle', N.D6]],
        congestion: [[0, N.C5, 0.22, 'sine'], [0, N.E5, 0.22, 'sine'], [0.24, N.D5, 0.3, 'sine'], [0.24, N.G4, 0.3, 'sine']],
        rain:       [[0, N.E6, 0.06, 'sine'], [0.1, N.C6, 0.06, 'sine'], [0.18, N.G6, 0.06, 'sine'], [0.3, N.D6, 0.06, 'sine'], [0.38, N.A5, 0.08, 'sine']],
        heat:       [[0, N.A5, 0.5, 'sine', N.D5], [0.05, N.E5, 0.45, 'triangle', N.A4]]
    };

    let ctx = null;
    let master = null;
    let muted = false;
    try { muted = localStorage.getItem('sentri-muted') === '1'; } catch (_) { /* storage blocked */ }

    function audio() {
        if (!ctx) {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return null;
            ctx = new AC();
            master = ctx.createGain();
            master.gain.value = 0.14;
            master.connect(ctx.destination);
        }
        if (ctx.state === 'suspended') ctx.resume();
        return ctx;
    }
    // Browsers only allow audio after a gesture: unlock on the first one.
    ['pointerdown', 'keydown'].forEach(ev =>
        window.addEventListener(ev, () => audio(), { once: true, passive: true }));

    function play(mood) {
        if (muted) return;
        const ac = audio();
        if (!ac || ac.state !== 'running') return;
        const now = ac.currentTime + 0.02;
        (SONGS[mood] || []).forEach(([at, f, dur, type, glide]) => {
            const o = ac.createOscillator();
            const g = ac.createGain();
            o.type = type;
            o.frequency.setValueAtTime(f, now + at);
            if (glide) o.frequency.exponentialRampToValueAtTime(glide, now + at + dur);
            const peak = type === 'square' || type === 'sawtooth' ? 0.35 : 0.8;
            g.gain.setValueAtTime(0.0001, now + at);
            g.gain.exponentialRampToValueAtTime(peak, now + at + 0.015);
            g.gain.exponentialRampToValueAtTime(0.0001, now + at + dur);
            o.connect(g).connect(master);
            o.start(now + at);
            o.stop(now + at + dur + 0.05);
        });
    }

    /* ------------------------------------------------------------------ */
    /* Telemetry to mood                                                   */
    /* ------------------------------------------------------------------ */
    function moodFrom(t, connected) {
        if (!connected || !t) return 'standby';
        if (t.collision || t.sound_active) return 'accident';
        if (t.wrong_way) return 'wrong_way';
        if (t.emergency_vehicle || t.rfid_active) return 'emergency';
        if (t.stalled_vehicle) return 'stall';
        const spd = Number(t.measured_speed_kmh) || 0;
        const rec = Number(t.recommended_speed_kmh) || 0;
        if (rec > 0 && spd > rec + 2) return 'slowdown';
        if (t.traffic_level === 'CONGESTED') return 'congestion';
        if (t.road_condition === 'WET') return 'rain';
        if (Number(t.temperature_c) >= 30) return 'heat';
        return 'clear';
    }

    function detailFor(mood, t) {
        if (!t) return null;
        const rec = Math.round(Number(t.recommended_speed_kmh) || 0);
        switch (mood) {
            case 'slowdown':  return `Advisory is ${rec} km/h. You are at ${Number(t.measured_speed_kmh).toFixed(0)}.`;
            case 'heat':      return `Road at ${Number(t.temperature_c).toFixed(1)} °C. Ease to ${rec} km/h.`;
            case 'rain':      return `Grip is low. Hold ${rec} km/h and brake early.`;
            case 'emergency': return 'Move aside and let the ambulance through.';
            default:          return null;
        }
    }

    /* ------------------------------------------------------------------ */
    /* Mount                                                               */
    /* ------------------------------------------------------------------ */
    function mount(root, opts = {}) {
        root.classList.add('sentri');
        root.innerHTML = `
            <div class="sentri-stage">${SVG}</div>
            <div class="sentri-bubble" aria-live="polite">
                <div class="sentri-bubble-title"></div>
                <div class="sentri-bubble-line"></div>
            </div>`;
        const titleEl = root.querySelector('.sentri-bubble-title');
        const lineEl = root.querySelector('.sentri-bubble-line');
        const stage = root.querySelector('.sentri-stage');

        let current = null;
        let lastSwitch = 0;
        let pending = null;
        let pendingTimer = null;
        const HOLD_MS = opts.holdMs ?? 2500;

        function apply(mood, detail) {
            const m = MOODS[mood] ? mood : 'clear';
            const changed = m !== current;
            root.dataset.mood = m;
            root.dataset.tone = MOODS[m].tone;
            titleEl.textContent = MOODS[m].title;
            lineEl.textContent = detail || MOODS[m].line;
            if (changed) {
                current = m;
                lastSwitch = Date.now();
                // retrigger the entrance pop
                root.classList.remove('sentri-pop');
                void root.offsetWidth;
                root.classList.add('sentri-pop');
                play(m);
                root.dispatchEvent(new CustomEvent('sentri:mood', { detail: { mood: m } }));
            }
        }

        // Debounced: a new mood must wait out the hold, except a more urgent one.
        const RANK = { accident: 5, wrong_way: 5, emergency: 4, stall: 3, slowdown: 3, congestion: 2, rain: 2, heat: 2, clear: 1, standby: 0 };
        function request(mood, detail) {
            if (mood === current) { apply(mood, detail); return; }
            const since = Date.now() - lastSwitch;
            if (current === null || since >= HOLD_MS || (RANK[mood] ?? 0) > (RANK[current] ?? 0)) {
                clearTimeout(pendingTimer); pending = null;
                apply(mood, detail);
                return;
            }
            pending = [mood, detail];
            clearTimeout(pendingTimer);
            pendingTimer = setTimeout(() => { if (pending) apply(...pending); pending = null; }, HOLD_MS - since);
        }

        // Poke him for a little chirp.
        stage.addEventListener('click', () => {
            audio();
            root.classList.remove('sentri-poke'); void root.offsetWidth; root.classList.add('sentri-poke');
            play(current || 'clear');
        });

        apply(opts.mood || 'standby');

        return {
            setMood: (mood, detail) => apply(mood, detail),
            fromTelemetry: (t, connected) => { const m = moodFrom(t, connected); request(m, detailFor(m, t)); },
            get mood() { return current; },
            setMuted: (v) => { muted = Boolean(v); try { localStorage.setItem('sentri-muted', muted ? '1' : '0'); } catch (_) {} },
            get muted() { return muted; },
            play: (m) => { audio(); play(m || current); }
        };
    }

    window.Sentri = { mount, moods: Object.keys(MOODS), MOODS, moodFrom };
})();
