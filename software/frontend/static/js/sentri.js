/* ==========================================================================
   Sentri: the SentraX road co-pilot
   --------------------------------------------------------------------------
   A soft, inflatable care-bot with a big round body, two dot eyes joined by a
   line, lashes, rosy cheeks, a marigold bow and a reflective road-safety sash.
   Pure inline SVG + CSS, so it works offline in the car.

   Live behaviour
     - mood from telemetry (props, pose and face change per road situation)
     - her face and head follow your finger or cursor, and drift when idle
     - natural random blinks, the odd double blink, a yawn when left alone
     - tap her head: giggle. Tap fast: dizzy. Stroke her head: heart eyes.
     - tap her body: wink and wave. Press and hold: high-five (with a clap)
     - talks: her little mouth moves while a line is shown or spoken aloud

   Usage
     const s = Sentri.mount(el, { mood: 'standby', size: 'md' });
     s.fromTelemetry(t, connected);   // derive mood from live telemetry
     s.setMood('rain');               // force a mood
     s.say('Wet patch ahead');        // speak a custom line
     s.setVoice(true);                // read warnings aloud (speechSynthesis)
   ========================================================================== */
(function () {
    'use strict';

    const MOODS = {
        standby:    { title: 'Off duty',            line: 'Link the ESP32 and I will keep watch.',     tone: 'idle' },
        clear:      { title: 'Road is clear',       line: 'All good. I am watching the corridor.',     tone: 'good' },
        slowdown:   { title: 'Ease off a little',   line: 'You are above the advisory speed.',         tone: 'warn' },
        emergency:  { title: 'Ambulance behind',    line: 'Move aside and give way.',                  tone: 'crit' },
        accident:   { title: 'Accident ahead',      line: 'Slow right down. Hazard on the road.',      tone: 'crit' },
        wrong_way:  { title: 'Wrong-way vehicle',   line: 'Keep left and slow down now.',              tone: 'crit' },
        stall:      { title: 'Stalled vehicle',     line: 'Lane blocked ahead. Merge early.',          tone: 'warn' },
        congestion: { title: 'Traffic building',    line: 'Keep a safe gap. It will clear.',           tone: 'warn' },
        rain:       { title: 'Wet road',            line: 'Grip is low. Brake early and gently.',      tone: 'warn' },
        heat:       { title: 'Road is hot',         line: 'Tyres soften in heat. Ease the pace.',      tone: 'warn' },
        confused:   { title: 'Lots going on',       line: 'Several hazards close together. Slow right down.', tone: 'warn' },
        speeder:    { title: 'Speeding car behind', line: 'Keep left and let it pass.',                tone: 'warn' }
    };

    const POKE_LINES = [
        'Eyes on the road, not on me.',
        'Hey! I am on duty.',
        'Still here. Still watching.',
        'Hehe, that tickles!',
        'Both hands on the wheel, please.'
    ];

    let uidCounter = 0;

    function svgFor(u) {
        return `
<svg class="sentri-svg" viewBox="0 0 220 290" role="img" aria-label="Sentri, the SentraX road co-pilot">
  <defs>
    <radialGradient id="sx-skin-${u}" cx="38%" cy="28%" r="78%">
      <stop offset="0" stop-color="#FFFFFF"/>
      <stop offset="0.6" stop-color="var(--sx-shell)"/>
      <stop offset="1" stop-color="var(--sx-shell-shade)"/>
    </radialGradient>
    <clipPath id="sx-body-${u}">
      <path d="M110 112 C150 112 176 140 178 186 C180 232 158 258 110 258 C62 258 40 232 42 186 C44 140 70 112 110 112 Z"/>
    </clipPath>
  </defs>

  <!-- scene props behind the figure -->
  <g class="prop prop-sun">
    <g class="sun-rays" stroke="var(--sx-accent)" stroke-width="4" stroke-linecap="round">
      <line x1="30" y1="8" x2="30" y2="0"/><line x1="30" y1="56" x2="30" y2="64"/>
      <line x1="6" y1="32" x2="-2" y2="32"/><line x1="54" y1="32" x2="62" y2="32"/>
      <line x1="13" y1="15" x2="7" y2="9"/><line x1="47" y1="49" x2="53" y2="55"/>
      <line x1="47" y1="15" x2="53" y2="9"/><line x1="13" y1="49" x2="7" y2="55"/>
    </g>
    <circle cx="30" cy="32" r="15" fill="var(--sx-accent)"/>
  </g>
  <g class="prop prop-rain" stroke="var(--sx-rain)" stroke-width="3" stroke-linecap="round">
    <line class="drop d1" x1="26" y1="64" x2="22" y2="76"/>
    <line class="drop d2" x1="204" y1="104" x2="200" y2="116"/>
    <line class="drop d3" x1="14" y1="150" x2="10" y2="162"/>
    <line class="drop d4" x1="210" y1="176" x2="206" y2="188"/>
    <line class="drop d5" x1="30" y1="216" x2="26" y2="228"/>
  </g>
  <g class="prop prop-cars">
    <g class="car c1"><rect x="-6" y="254" width="38" height="16" rx="7" fill="var(--sx-ink-soft)"/>
      <rect x="2" y="248" width="20" height="9" rx="4" fill="var(--sx-ink-soft)"/>
      <circle cx="3" cy="272" r="4" fill="var(--sx-ink)"/><circle cx="23" cy="272" r="4" fill="var(--sx-ink)"/></g>
    <g class="car c2"><rect x="188" y="254" width="38" height="16" rx="7" fill="var(--sx-ink-soft)"/>
      <rect x="198" y="248" width="20" height="9" rx="4" fill="var(--sx-ink-soft)"/>
      <circle cx="197" cy="272" r="4" fill="var(--sx-ink)"/><circle cx="217" cy="272" r="4" fill="var(--sx-ink)"/></g>
  </g>

  <g class="prop prop-speeder">
    <g class="speeder-car">
      <path d="M-34 238 h20 M-42 247 h26 M-32 256 h18" stroke="var(--sx-ink-soft)" stroke-width="3" stroke-linecap="round"/>
      <rect x="-8" y="240" width="42" height="17" rx="7" fill="var(--sx-crit)"/>
      <rect x="2" y="233" width="22" height="10" rx="4" fill="var(--sx-crit)"/>
      <rect x="6" y="235.5" width="14" height="5" rx="2" fill="var(--sx-paper)" opacity="0.85"/>
      <circle cx="2" cy="259" r="4.5" fill="var(--sx-ink)"/><circle cx="25" cy="259" r="4.5" fill="var(--sx-ink)"/>
    </g>
  </g>

  <ellipse class="sx-shadow" cx="110" cy="279" rx="54" ry="7" fill="var(--sx-ink)" opacity="0.2"/>

  <g class="sx-rig">
    <!-- stubby legs -->
    <g class="legs" fill="url(#sx-skin-${u})" stroke="var(--sx-seam)" stroke-width="2">
      <g class="leg leg-l"><rect x="80" y="236" width="25" height="36" rx="12"/><ellipse cx="91" cy="272" rx="17" ry="8"/></g>
      <g class="leg leg-r"><rect x="115" y="236" width="25" height="36" rx="12"/><ellipse cx="129" cy="272" rx="17" ry="8"/></g>
    </g>

    <!-- puffy arms, behind the body -->
    <g class="arm arm-l">
      <ellipse cx="50" cy="178" rx="15" ry="38" fill="url(#sx-skin-${u})" stroke="var(--sx-seam)" stroke-width="2"/>
      <path d="M38 196 Q50 202 62 196" fill="none" stroke="var(--sx-seam)" stroke-width="1.6"/>
    </g>
    <g class="arm arm-r">
      <ellipse cx="170" cy="178" rx="15" ry="38" fill="url(#sx-skin-${u})" stroke="var(--sx-seam)" stroke-width="2"/>
      <path d="M158 196 Q170 202 182 196" fill="none" stroke="var(--sx-seam)" stroke-width="1.6"/>
      <g class="prop prop-paddle">
        <line x1="170" y1="214" x2="170" y2="256" stroke="var(--sx-ink)" stroke-width="4" stroke-linecap="round"/>
        <circle cx="170" cy="275" r="20" fill="var(--sx-crit)" stroke="var(--sx-paper)" stroke-width="3"/>
        <text x="170" y="280" text-anchor="middle" transform="rotate(180 170 275)" font-family="inherit" font-size="12.5" font-weight="800" fill="var(--sx-paper)" letter-spacing="0.5">SLOW</text>
      </g>
      <g class="prop prop-wand">
        <rect x="165.5" y="212" width="9" height="46" rx="4.5" class="wand-glow" fill="var(--sx-crit)"/>
        <rect x="167" y="212" width="6" height="12" rx="2" fill="var(--sx-ink)"/>
      </g>
      <g class="prop prop-umbrella">
        <line x1="170" y1="214" x2="200" y2="272" stroke="var(--sx-ink)" stroke-width="3.5" stroke-linecap="round"/>
        <path d="M145 272 Q200 330 255 272 Q243 278 231 272 Q219 280 207 272 Q195 280 183 272 Q171 280 159 272 Q152 277 145 272 Z" fill="var(--sx-accent)"/>
      </g>
    </g>

    <!-- inflatable body -->
    <path class="body" d="M110 112 C150 112 176 140 178 186 C180 232 158 258 110 258 C62 258 40 232 42 186 C44 140 70 112 110 112 Z"
          fill="url(#sx-skin-${u})" stroke="var(--sx-seam)" stroke-width="2"/>
    <g clip-path="url(#sx-body-${u})">
      <!-- soft seams -->
      <path d="M58 168 Q110 182 162 168" fill="none" stroke="var(--sx-seam)" stroke-width="1.6" opacity="0.8"/>
      <path d="M52 214 Q110 230 168 214" fill="none" stroke="var(--sx-seam)" stroke-width="1.6" opacity="0.8"/>
      <!-- reflective road-safety sash -->
      <path class="sash" d="M52 128 L70 116 L176 230 L158 244 Z" fill="var(--sx-accent)"/>
      <path d="M61 122 L167 237" stroke="var(--sx-reflect)" stroke-width="3" opacity="0.9"/>
    </g>
    <!-- chest badge -->
    <circle cx="86" cy="156" r="8.5" fill="var(--sx-paper)" stroke="var(--sx-seam)" stroke-width="1.6"/>
    <path d="M83 153.6 Q86 150.6 89 153.6 Q86 156 83 157.4 Q86 160.6 89 157.4" fill="none" stroke="var(--sx-accent)" stroke-width="2" stroke-linecap="round"/>

    <!-- head: outer group follows the pointer, inner group carries mood poses -->
    <g class="head-look">
      <g class="head">
        <ellipse cx="110" cy="86" rx="50" ry="39" fill="url(#sx-skin-${u})" stroke="var(--sx-seam)" stroke-width="2"/>
        <path d="M70 70 Q110 54 150 70" fill="none" stroke="#FFFFFF" stroke-width="5" stroke-linecap="round" opacity="0.7"/>

        <!-- bow -->
        <g class="bow">
          <path d="M140 50 L124 38 Q120 50 124 60 Z" fill="var(--sx-accent)"/>
          <path d="M140 50 L156 38 Q160 50 156 60 Z" fill="var(--sx-accent)"/>
          <path d="M126 42 L135 49 M154 42 L145 49" stroke="var(--sx-accent-dark)" stroke-width="1.6" stroke-linecap="round"/>
          <circle cx="140" cy="50" r="5" fill="var(--sx-accent-dark)"/>
        </g>

        <!-- everything on the face moves together when she looks around -->
        <g class="face-look">
          <ellipse class="cheek" cx="80" cy="99" rx="8" ry="5" fill="var(--sx-blush)"/>
          <ellipse class="cheek" cx="140" cy="99" rx="8" ry="5" fill="var(--sx-blush)"/>

          <!-- signature eyes: two dots joined by a line, with lashes -->
          <g class="eyes eyes-normal">
            <g class="blinker">
              <ellipse cx="94" cy="86" rx="6.6" ry="8" fill="var(--sx-ink)"/>
              <ellipse cx="126" cy="86" rx="6.6" ry="8" fill="var(--sx-ink)"/>
              <circle cx="96.2" cy="82.6" r="2" fill="#FFFFFF"/>
              <circle cx="128.2" cy="82.6" r="2" fill="#FFFFFF"/>
            </g>
            <path class="lash" d="M88.4 80 L84.2 76.8 M90 77.4 L87.6 73.4" stroke="var(--sx-ink)" stroke-width="2" stroke-linecap="round"/>
            <path class="lash" d="M131.6 80 L135.8 76.8 M130 77.4 L132.4 73.4" stroke="var(--sx-ink)" stroke-width="2" stroke-linecap="round"/>
          </g>
          <g class="eyes eyes-happy" fill="none" stroke="var(--sx-ink)" stroke-width="3.4" stroke-linecap="round">
            <path d="M87 89 Q94 79 101 89"/><path d="M119 89 Q126 79 133 89"/>
          </g>
          <g class="eyes eyes-closed" fill="none" stroke="var(--sx-ink)" stroke-width="3.2" stroke-linecap="round">
            <path d="M87 85 Q94 92 101 85"/><path d="M119 85 Q126 92 133 85"/>
            <path d="M88 87 L85 90 M132 87 L135 90" stroke-width="2"/>
          </g>
          <g class="eyes eyes-shock">
            <circle cx="94" cy="86" r="9.5" fill="var(--sx-paper)" stroke="var(--sx-ink)" stroke-width="3"/>
            <circle cx="126" cy="86" r="9.5" fill="var(--sx-paper)" stroke="var(--sx-ink)" stroke-width="3"/>
            <circle cx="94" cy="86" r="3.6" fill="var(--sx-ink)"/><circle cx="126" cy="86" r="3.6" fill="var(--sx-ink)"/>
          </g>
          <g class="eyes eyes-squint" fill="none" stroke="var(--sx-ink)" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">
            <path d="M88 81 L100 86 L88 91"/><path d="M132 81 L120 86 L132 91"/>
          </g>
          <g class="eyes eyes-heart" fill="var(--sx-heart)">
            <path d="M94 94 L86 86 Q82 80 88 78 Q92 77 94 81 Q96 77 100 78 Q106 80 102 86 Z"/>
            <path d="M126 94 L118 86 Q114 80 120 78 Q124 77 126 81 Q128 77 132 78 Q138 80 134 86 Z"/>
          </g>
          <g class="eyes eyes-wink">
            <ellipse cx="94" cy="86" rx="6.6" ry="8" fill="var(--sx-ink)"/>
            <circle cx="96.2" cy="82.6" r="2" fill="#FFFFFF"/>
            <path d="M119 88 Q126 79 133 88" fill="none" stroke="var(--sx-ink)" stroke-width="3.4" stroke-linecap="round"/>
          </g>
          <g class="eyes eyes-confused">
            <ellipse cx="94" cy="85" rx="7.2" ry="8.8" fill="var(--sx-ink)"/>
            <circle cx="96.6" cy="81.4" r="2.2" fill="#FFFFFF"/>
            <path d="M119 87 Q126 83.5 133 87" fill="none" stroke="var(--sx-ink)" stroke-width="3.2" stroke-linecap="round"/>
          </g>
          <g class="eyes eyes-dizzy" fill="none" stroke="var(--sx-ink)" stroke-width="2.4" stroke-linecap="round">
            <path class="spiral" d="M94 86 m-1 0 a1 1 0 1 1 2 0 a3 3 0 1 1 -6 0 a5 5 0 1 1 10 0 a7 7 0 1 1 -14 0"/>
            <path class="spiral" d="M126 86 m-1 0 a1 1 0 1 1 2 0 a3 3 0 1 1 -6 0 a5 5 0 1 1 10 0 a7 7 0 1 1 -14 0"/>
          </g>
          <!-- the connecting line, shared by every eye style -->
          <line class="eye-bridge" x1="100" y1="86" x2="120" y2="86" stroke="var(--sx-ink)" stroke-width="3" stroke-linecap="round"/>
          <!-- worried / stern brows -->
          <g class="brows" fill="none" stroke="var(--sx-ink)" stroke-width="2.6" stroke-linecap="round">
            <path class="brow brow-l" d="M86 72 L101 76"/>
            <path class="brow brow-r" d="M134 72 L119 76"/>
          </g>

          <!-- a tiny mouth for expressions -->
          <g class="mouth">
            <path class="m m-smile" d="M105 100 Q110 104.5 115 100" fill="none" stroke="var(--sx-ink)" stroke-width="2.4" stroke-linecap="round"/>
            <path class="m m-cat" d="M102.5 99.5 Q106.2 104 110 99.5 Q113.8 104 117.5 99.5" fill="none" stroke="var(--sx-ink)" stroke-width="2.4" stroke-linecap="round"/>
            <ellipse class="m m-talk" cx="110" cy="102" rx="3.8" ry="2.8" fill="var(--sx-mouth)"/>
            <ellipse class="m m-o" cx="110" cy="102.5" rx="3.2" ry="4" fill="var(--sx-mouth)"/>
            <path class="m m-flat" d="M106 102 L114 102" stroke="var(--sx-ink)" stroke-width="2.4" stroke-linecap="round"/>
            <path class="m m-worry" d="M105 104 Q110 99.5 115 104" fill="none" stroke="var(--sx-ink)" stroke-width="2.4" stroke-linecap="round"/>
            <ellipse class="m m-yawn" cx="110" cy="103" rx="5" ry="6.4" fill="var(--sx-mouth)"/>
            <path class="m m-wavy" d="M103.5 102 Q106.75 98.8 110 102 Q113.25 105.2 116.5 102" fill="none" stroke="var(--sx-ink)" stroke-width="2.4" stroke-linecap="round"/>
          </g>
        </g>

        <!-- sweat -->
        <g class="prop prop-sweat" fill="var(--sx-rain)">
          <path class="sweat s1" d="M152 62 Q158 72 152 78 Q146 72 152 62 Z"/>
          <path class="sweat s2" d="M66 70 Q71 78 66 83 Q61 78 66 70 Z"/>
        </g>
      </g>
    </g>
  </g>

  <!-- ground and floating props -->
  <g class="prop prop-cone"><g transform="translate(184 218)">
    <path d="M14 0 L26 50 L2 50 Z" fill="var(--sx-accent)"/>
    <path d="M9 21 L19 21 L21 31 L7 31 Z" fill="var(--sx-reflect)"/>
    <rect x="-4" y="48" width="36" height="8" rx="3" fill="var(--sx-ink)"/></g>
  </g>
  <g class="prop prop-alert">
    <path d="M190 10 L214 52 L166 52 Z" fill="var(--sx-crit)" stroke="var(--sx-paper)" stroke-width="3" stroke-linejoin="round"/>
    <rect x="187.5" y="23" width="5" height="16" rx="2.5" fill="var(--sx-paper)"/>
    <circle cx="190" cy="45" r="3" fill="var(--sx-paper)"/>
  </g>
  <g class="prop prop-uturn" fill="none" stroke="var(--sx-crit)" stroke-width="7" stroke-linecap="round" stroke-linejoin="round">
    <path d="M170 64 L170 34 Q170 14 188 14 Q206 14 206 34 L206 48"/>
    <path d="M195 38 L206 52 L217 38"/>
  </g>
  <g class="prop prop-zzz" fill="var(--sx-ink-soft)" font-family="inherit" font-weight="800">
    <text class="z z1" x="160" y="44" font-size="16">z</text>
    <text class="z z2" x="174" y="28" font-size="21">z</text>
    <text class="z z3" x="190" y="10" font-size="27">Z</text>
  </g>
  <g class="prop prop-hearts" fill="var(--sx-heart)">
    <path class="heart h1" d="M184 60 c-4 -6 -12 -2 -8 5 l8 8 l8 -8 c4 -7 -4 -11 -8 -5 z"/>
    <path class="heart h2" d="M36 66 c-3 -5 -9 -2 -6 4 l6 6 l6 -6 c3 -6 -3 -9 -6 -4 z"/>
    <path class="heart h3" d="M168 30 c-2.5 -4 -7 -1.5 -5 3 l5 5 l5 -5 c2 -4.5 -2.5 -7 -5 -3 z"/>
  </g>
  <g class="prop prop-question" fill="var(--sx-accent)" font-family="inherit" font-weight="800">
    <text class="q q1" x="64" y="52" font-size="24">?</text>
    <text class="q q2" x="160" y="40" font-size="30">?</text>
  </g>
  <g class="prop prop-sparkle" fill="var(--sx-accent)">
    <path class="spark k1" d="M34 70 L37 79 L46 82 L37 85 L34 94 L31 85 L22 82 L31 79 Z"/>
    <path class="spark k2" d="M190 54 L192 60 L198 62 L192 64 L190 70 L188 64 L182 62 L188 60 Z"/>
  </g>
</svg>`;
    }

    /* ------------------------------------------------------------------ */
    /* Sound: short synthesised chirps, no audio files                     */
    /* ------------------------------------------------------------------ */
    const N = { C4: 261.6, E4: 329.6, G4: 392.0, A4: 440.0, C5: 523.3, D5: 587.3, E5: 659.3,
                F5: 698.5, G5: 784.0, A5: 880.0, C6: 1046.5, D6: 1174.7, E6: 1318.5, G6: 1568.0 };

    // [startSec, freq, durSec, type, glideToFreq?]
    const SONGS = {
        standby:    [[0, N.E4, 0.35, 'sine', N.C4], [0.3, N.C4, 0.45, 'sine', 220]],
        clear:      [[0, N.C5, 0.1, 'triangle'], [0.09, N.E5, 0.1, 'triangle'], [0.18, N.G5, 0.14, 'triangle']],
        slowdown:   [[0, N.G5, 0.18, 'triangle', N.E5], [0.2, N.D5, 0.3, 'triangle', N.A4]],
        emergency:  [[0, N.A5, 0.13, 'square'], [0.15, N.E5, 0.13, 'square'], [0.3, N.A5, 0.13, 'square'], [0.45, N.E5, 0.13, 'square']],
        accident:   [[0, N.C6, 0.08, 'square'], [0.11, N.C6, 0.08, 'square'], [0.22, N.C6, 0.08, 'square'], [0.36, N.F5, 0.35, 'sawtooth', N.C5]],
        wrong_way:  [[0, N.E5, 0.12, 'square', N.C5], [0.16, N.E5, 0.12, 'square', N.C5], [0.34, N.G4, 0.3, 'triangle']],
        stall:      [[0, N.D5, 0.14, 'triangle'], [0.16, N.A5, 0.22, 'triangle', N.D6]],
        congestion: [[0, N.C5, 0.22, 'sine'], [0, N.E5, 0.22, 'sine'], [0.24, N.G4, 0.3, 'sine']],
        rain:       [[0, N.E6, 0.06, 'sine'], [0.1, N.C6, 0.06, 'sine'], [0.18, N.G6, 0.06, 'sine'], [0.3, N.D6, 0.06, 'sine']],
        heat:       [[0, N.A5, 0.5, 'sine', N.D5]],
        confused:   [[0, N.E5, 0.16, 'triangle', N.C5], [0.2, N.C5, 0.16, 'triangle', N.G5], [0.42, N.A5, 0.22, 'triangle', N.F5]],
        speeder:    [[0, N.C5, 0.35, 'sawtooth', N.C6], [0.36, N.C6, 0.25, 'triangle', N.G5]],
        bye:        [[0, N.C6, 0.1, 'triangle'], [0.12, N.A5, 0.1, 'triangle'], [0.24, N.F5, 0.1, 'triangle'], [0.4, N.C6, 0.3, 'triangle', N.G6]],
        giggle:     [[0, N.E5, 0.07, 'triangle', N.G5], [0.09, N.E5, 0.07, 'triangle', N.A5], [0.18, N.G5, 0.09, 'triangle', N.C6]],
        dizzy:      [[0, N.C6, 0.6, 'sine', N.C4], [0.05, N.E6, 0.55, 'sine', N.E4]],
        purr:       [[0, N.G4, 0.25, 'sine', N.A4], [0.22, N.A4, 0.3, 'sine', N.G4]],
        clap:       [[0, 1900, 0.04, 'square', 900], [0.06, 2200, 0.05, 'square', 800]],
        hello:      [[0, N.G5, 0.09, 'triangle'], [0.1, N.C6, 0.16, 'triangle', N.E6]],
        yawn:       [[0, N.G4, 0.7, 'sine', N.C4]]
    };

    let ctx = null;
    let master = null;
    let muted = false;
    let voiceOn = false;
    try {
        muted = localStorage.getItem('sentri-muted') === '1';
        voiceOn = localStorage.getItem('sentri-voice') === '1';
    } catch (_) { /* storage blocked */ }

    function audio() {
        if (!ctx) {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return null;
            ctx = new AC();
            master = ctx.createGain();
            master.gain.value = 0.13;
            master.connect(ctx.destination);
        }
        if (ctx.state === 'suspended') ctx.resume();
        return ctx;
    }
    // Browsers only allow audio after a gesture: unlock on the first one.
    ['pointerdown', 'keydown'].forEach(ev =>
        window.addEventListener(ev, () => audio(), { once: true, passive: true }));

    function play(name) {
        if (muted) return;
        const ac = audio();
        if (!ac || ac.state !== 'running') return;
        const now = ac.currentTime + 0.02;
        (SONGS[name] || []).forEach(([at, f, dur, type, glide]) => {
            const o = ac.createOscillator();
            const g = ac.createGain();
            o.type = type;
            o.frequency.setValueAtTime(f, now + at);
            if (glide) o.frequency.exponentialRampToValueAtTime(glide, now + at + dur);
            const peak = type === 'square' || type === 'sawtooth' ? 0.32 : 0.8;
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
            default:          return null;
        }
    }

    const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* ------------------------------------------------------------------ */
    /* Mount                                                               */
    /* ------------------------------------------------------------------ */
    function mount(root, opts = {}) {
        const u = `${++uidCounter}`;
        root.classList.add('sentri');
        if (opts.size) root.dataset.size = opts.size;
        const withBubble = opts.bubble !== false;
        root.innerHTML = `
            <div class="sentri-stage">${svgFor(u)}</div>
            ${withBubble ? `<div class="sentri-bubble" aria-live="polite">
                <div class="sentri-bubble-title"></div>
                <div class="sentri-bubble-line"></div>
            </div>` : ''}`;
        const titleEl = root.querySelector('.sentri-bubble-title');
        const lineEl = root.querySelector('.sentri-bubble-line');
        const stage = root.querySelector('.sentri-stage');
        const svg = root.querySelector('.sentri-svg');
        const headLook = svg.querySelector('.head-look');
        const faceLook = svg.querySelector('.face-look');

        let current = null;
        let lastSwitch = 0;
        let pending = null;
        let pendingTimer = null;
        const HOLD_MS = opts.holdMs ?? 2500;
        const timers = new Set();
        const later = (fn, ms) => { const id = setTimeout(() => { timers.delete(id); fn(); }, ms); timers.add(id); return id; };

        /* -------- acting: short reactions layered over the mood -------- */
        let actTimer = null;
        function act(name, ms) {
            root.dataset.act = name;
            clearTimeout(actTimer);
            actTimer = setTimeout(() => { delete root.dataset.act; }, ms);
        }

        /* -------- talking: mouth moves while a line is "spoken" -------- */
        let talkTimer = null;
        function talk(ms) {
            root.classList.add('sentri-talking');
            clearTimeout(talkTimer);
            talkTimer = setTimeout(() => root.classList.remove('sentri-talking'), ms);
        }
        function speak(text, force) {
            if (!text) return;
            talk(Math.min(3200, 400 + text.length * 45));
            if (!(voiceOn || force) || !('speechSynthesis' in window)) return;
            try {
                window.speechSynthesis.cancel();
                const ut = new SpeechSynthesisUtterance(text);
                ut.rate = 1.04;
                ut.pitch = 1.05;
                ut.onstart = () => root.classList.add('sentri-talking');
                ut.onend = () => root.classList.remove('sentri-talking');
                window.speechSynthesis.speak(ut);
            } catch (_) { /* speech not available */ }
        }

        function show(title, line) {
            if (titleEl) titleEl.textContent = title;
            if (lineEl) lineEl.textContent = line;
        }

        function apply(mood, detail) {
            const m = MOODS[mood] ? mood : 'clear';
            const changed = m !== current;
            root.dataset.mood = m;
            root.dataset.tone = MOODS[m].tone;
            const line = detail || MOODS[m].line;
            show(MOODS[m].title, line);
            if (changed) {
                current = m;
                lastSwitch = Date.now();
                root.classList.remove('sentri-pop'); void root.offsetWidth; root.classList.add('sentri-pop');
                play(m);
                if (MOODS[m].tone === 'crit' || MOODS[m].tone === 'warn') speak(`${MOODS[m].title}. ${line}`);
                else talk(900);
                root.dispatchEvent(new CustomEvent('sentri:mood', { detail: { mood: m }, bubbles: true }));
            }
        }

        // Debounced: a new mood must wait out the hold, except a more urgent one.
        const RANK = { accident: 5, wrong_way: 5, confused: 4, emergency: 4, stall: 3, slowdown: 3, speeder: 3, congestion: 2, rain: 2, heat: 2, clear: 1, standby: 0 };
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

        /* -------- gaze: eyes and head follow the pointer -------- */
        let gx = 0, gy = 0;          // target, -1..1
        let cx = 0, cy = 0;          // eased
        let lastPointer = 0;
        let raf = 0;
        function lookAt(nx, ny) {
            gx = Math.max(-1, Math.min(1, nx));
            gy = Math.max(-1, Math.min(1, ny));
            if (!raf) raf = requestAnimationFrame(step);
        }
        function step() {
            raf = 0;
            cx += (gx - cx) * 0.22;
            cy += (gy - cy) * 0.22;
            faceLook.style.transform = `translate(${cx * 7}px, ${cy * 5}px)`;
            headLook.style.transform = `rotate(${cx * 5}deg) translate(${cx * 2}px, ${cy * 1.5}px)`;
            if (Math.abs(gx - cx) > 0.01 || Math.abs(gy - cy) > 0.01) raf = requestAnimationFrame(step);
        }
        function onPointer(e) {
            if (!root.isConnected) return;
            const r = svg.getBoundingClientRect();
            if (!r.width) return;
            // head centre sits ~30% down the figure
            const hx = r.left + r.width * 0.5;
            const hy = r.top + r.height * 0.3;
            const reach = Math.max(260, r.width * 2.2);
            lastPointer = Date.now();
            lookAt((e.clientX - hx) / reach, (e.clientY - hy) / reach);
        }
        if (!reduceMotion) {
            window.addEventListener('pointermove', onPointer, { passive: true });
            window.addEventListener('pointerdown', onPointer, { passive: true });
        }
        // Phone tilt (Android, no permission prompt needed)
        function onTilt(e) {
            if (Date.now() - lastPointer < 2500 || e.gamma == null) return;
            lookAt(e.gamma / 35, (e.beta - 45) / 45);
        }
        if (!reduceMotion && 'DeviceOrientationEvent' in window &&
            typeof window.DeviceOrientationEvent.requestPermission !== 'function') {
            window.addEventListener('deviceorientation', onTilt, { passive: true });
        }

        // Idle: glance around now and then
        function idleGlance() {
            if (Date.now() - lastPointer > 3500 && !reduceMotion) {
                const spots = [[0, 0], [-0.8, 0.1], [0.8, 0.1], [0.3, -0.6], [-0.4, 0.5], [0, 0]];
                const [x, y] = spots[Math.floor(Math.random() * spots.length)];
                lookAt(x, y);
            }
            later(idleGlance, 1800 + Math.random() * 2600);
        }
        later(idleGlance, 1500);

        /* -------- blinking -------- */
        function blink() {
            root.classList.add('sentri-blink');
            later(() => root.classList.remove('sentri-blink'), 130);
        }
        function blinkLoop() {
            blink();
            if (Math.random() < 0.2) later(blink, 260);   // double blink
            later(blinkLoop, 2200 + Math.random() * 3800);
        }
        later(blinkLoop, 1200);

        /* -------- yawn when left alone -------- */
        let lastTouch = Date.now();
        function boredCheck() {
            if (Date.now() - lastTouch > 45000 && current !== 'standby' && RANK[current] <= 1 && !root.dataset.act) {
                act('yawn', 2200);
                play('yawn');
                lastTouch = Date.now();
            }
            later(boredCheck, 5000);
        }
        later(boredCheck, 5000);

        /* -------- wave hello when the app comes back -------- */
        function onVisible() {
            if (document.visibilityState === 'visible') { act('wave', 1600); play('hello'); }
        }
        document.addEventListener('visibilitychange', onVisible);

        /* -------- touch: giggle, dizzy, pet, wave, high-five -------- */
        let taps = [];
        let holdTimer = null;
        let held = false;
        let petDistance = 0;
        let lastMove = null;
        let downOnHead = false;

        function onHead(e) {
            const r = svg.getBoundingClientRect();
            return (e.clientY - r.top) < r.height * 0.43;
        }
        stage.addEventListener('pointerdown', (e) => {
            audio();
            lastTouch = Date.now();
            held = false;
            downOnHead = onHead(e);
            petDistance = 0;
            lastMove = [e.clientX, e.clientY];
            clearTimeout(holdTimer);
            holdTimer = setTimeout(() => {
                held = true;
                act('highfive', 1500);
                later(() => play('clap'), 380);
                if (navigator.vibrate) navigator.vibrate(25);
            }, 550);
        });
        stage.addEventListener('pointermove', (e) => {
            if (!lastMove) return;
            const d = Math.hypot(e.clientX - lastMove[0], e.clientY - lastMove[1]);
            lastMove = [e.clientX, e.clientY];
            if (d > 2) clearTimeout(holdTimer);
            if (downOnHead) {
                petDistance += d;
                if (petDistance > 140 && root.dataset.act !== 'pet') {
                    act('pet', 1800);
                    play('purr');
                    petDistance = -400;   // one purr per stroke
                }
            }
        });
        const endPress = () => { clearTimeout(holdTimer); lastMove = null; };
        stage.addEventListener('pointerup', (e) => {
            endPress();
            if (held || petDistance > 40 || petDistance < 0) return;
            const now = Date.now();
            taps = taps.filter(t => now - t < 1400);
            taps.push(now);
            root.classList.remove('sentri-poke'); void root.offsetWidth; root.classList.add('sentri-poke');
            if (taps.length >= 5) {
                taps = [];
                act('dizzy', 2300);
                play('dizzy');
                show('Whoa, easy!', 'The road is spinning. Give me a second.');
                talk(1200);
                later(() => apply(current || 'clear'), 2600);
                return;
            }
            if (downOnHead) {
                act('laugh', 1200);
                play('giggle');
            } else {
                act('wave', 1400);
                play('hello');
            }
            if (taps.length === 3) {
                show(MOODS[current || 'clear'].title, POKE_LINES[Math.floor(Math.random() * POKE_LINES.length)]);
                talk(1400);
                later(() => apply(current || 'clear'), 3200);
            }
        });
        stage.addEventListener('pointercancel', endPress);
        stage.addEventListener('pointerleave', endPress);
        stage.addEventListener('contextmenu', (e) => e.preventDefault());

        apply(opts.mood || 'standby');

        return {
            setMood: (mood, detail) => apply(mood, detail),
            fromTelemetry: (t, connected) => { const m = moodFrom(t, connected); request(m, detailFor(m, t)); },
            // like setMood, but a less urgent mood waits out the hold so she does not flicker
            request: (mood, detail) => request(mood, detail),
            say: (text, title) => { show(title || MOODS[current || 'clear'].title, text); speak(text); },
            act: (name, ms) => act(name, ms || 1400),
            get mood() { return current; },
            setMuted: (v) => { muted = Boolean(v); try { localStorage.setItem('sentri-muted', muted ? '1' : '0'); } catch (_) {} },
            get muted() { return muted; },
            setVoice: (v) => {
                voiceOn = Boolean(v);
                try { localStorage.setItem('sentri-voice', voiceOn ? '1' : '0'); } catch (_) {}
                if (!voiceOn && 'speechSynthesis' in window) window.speechSynthesis.cancel();
            },
            get voice() { return voiceOn; },
            play: (m) => { audio(); play(m || current); },
            destroy: () => {
                timers.forEach(clearTimeout); timers.clear();
                clearTimeout(actTimer); clearTimeout(talkTimer); clearTimeout(pendingTimer); clearTimeout(holdTimer);
                window.removeEventListener('pointermove', onPointer);
                window.removeEventListener('pointerdown', onPointer);
                window.removeEventListener('deviceorientation', onTilt);
                document.removeEventListener('visibilitychange', onVisible);
                root.innerHTML = '';
            }
        };
    }

    window.Sentri = { mount, moods: Object.keys(MOODS), MOODS, moodFrom };
})();
