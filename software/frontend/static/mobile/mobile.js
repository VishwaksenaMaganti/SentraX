/* ==========================================================================
   SentraX Drive (mobile)
   Map-first phone app that works anywhere:
     - real road routing (OpenStreetMap / OSRM) for car, bike and walking,
       with turn-by-turn steps and alternative routes
     - worldwide place search and reverse lookup (Nominatim), your location
     - live SentraX sensor telemetry over the WebSocket, or Test lab conditions
     - Sentri minimised as a chat head that pops up when the road needs you
   ========================================================================== */
(function () {
    'use strict';

    /* ------------------------------------------------------------------ */
    /* Icons: one consistent set, 1.8 stroke, rounded                      */
    /* ------------------------------------------------------------------ */
    const S = (d, extra = '') => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ${extra}>${d}</svg>`;
    const ICONS = {
        menu:    S('<path d="M4 7h16M4 12h16M4 17h11"/>'),
        swap:    S('<path d="M8 4v15M8 4 5 7M8 4l3 3M16 20V5M16 20l-3-3M16 20l3-3"/>'),
        pin:     `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.5a7 7 0 0 0-7 7c0 5 7 12 7 12s7-7 7-12a7 7 0 0 0-7-7Zm0 9.6a2.6 2.6 0 1 1 0-5.2 2.6 2.6 0 0 1 0 5.2Z"/></svg>`,
        car:     S('<path d="M5 16v2.5M19 16v2.5M4 16h16v-4.2l-1.8-4.6A2 2 0 0 0 16.3 6H7.7a2 2 0 0 0-1.9 1.2L4 11.8V16Z"/><path d="M4 12h16"/><circle cx="7.5" cy="14" r=".6" fill="currentColor"/><circle cx="16.5" cy="14" r=".6" fill="currentColor"/>'),
        walk:    S('<circle cx="13" cy="4.5" r="1.8"/><path d="m9.5 20 2.5-6.5 2.5 2.5V20M12 13.5l.8-5.5-3.3 1.6-1.5 3M12.8 8l2.2 3.2 2.5 1"/>'),
        bike:    S('<circle cx="6" cy="16" r="3.5"/><circle cx="18" cy="16" r="3.5"/><path d="M6 16l4-7h5l3 7M10 9l4 7h-8M13 5.5h2.5"/>'),
        ring:    S('<circle cx="12" cy="12" r="6.5"/><circle cx="12" cy="12" r="2" fill="currentColor"/>'),
        flag:    S('<path d="M6 21V4M6 4h10.5l-2 4 2 4H6"/>'),
        close:   S('<path d="M6 6l12 12M18 6 6 18"/>'),
        gauge:   S('<path d="M4.5 17.5a8.5 8.5 0 1 1 15 0"/><path d="m12 13 4-4.5"/><circle cx="12" cy="13" r="1.4" fill="currentColor"/>'),
        bell:    S('<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15l1.5-2ZM10 20.5a2 2 0 0 0 4 0"/>'),
        link:    S('<path d="m7 7 10 10-5 4.5V2.5l5 4.5L7 17"/>'),
        speed:   S('<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/>'),
        play:    S('<path d="M8 5.5v13l10.5-6.5L8 5.5Z"/>'),
        smile:   S('<circle cx="12" cy="12" r="8.5"/><circle cx="9" cy="10.5" r="1.1" fill="currentColor"/><circle cx="15" cy="10.5" r="1.1" fill="currentColor"/><path d="M10.2 10.5h3.6M9.5 14.6c1.4 1.3 3.6 1.3 5 0"/>'),
        layers:  S('<path d="m12 3.5 8.5 4.5L12 12.5 3.5 8 12 3.5Z"/><path d="m3.5 12 8.5 4.5 8.5-4.5M3.5 16l8.5 4.5 8.5-4.5"/>'),
        plus:    S('<path d="M12 5v14M5 12h14"/>'),
        minus:   S('<path d="M5 12h14"/>'),
        locate:  S('<circle cx="12" cy="12" r="6.5"/><circle cx="12" cy="12" r="2.2" fill="currentColor"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3"/>'),
        route:   S('<circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="6" r="2.2"/><path d="M8 18h7.5a3.5 3.5 0 0 0 0-7h-7a3.5 3.5 0 0 1 0-7H16"/>'),
        chevron: S('<path d="m6 15 6-6 6 6"/>'),
        chevL:   S('<path d="m15 6-6 6 6 6"/>'),
        chevR:   S('<path d="m9 6 6 6-6 6"/>'),
        nav:     `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.8 19.5 20 12 16.2 4.5 20 12 2.8Z"/></svg>`,
        monitor: S('<rect x="3" y="4.5" width="18" height="12" rx="2"/><path d="M9 20.5h6M12 16.5v4"/>'),
        warn:    S('<path d="M12 4 21 19.5H3L12 4Z"/><path d="M12 10v4.5"/><circle cx="12" cy="17" r=".7" fill="currentColor"/>', 'stroke-width="2.4"'),
        drop:    S('<path d="M12 3.5s6 6.4 6 10.5a6 6 0 0 1-12 0c0-4.1 6-10.5 6-10.5Z"/>'),
        thermo:  S('<path d="M14 14.5V5a2 2 0 0 0-4 0v9.5a4 4 0 1 0 4 0Z"/>'),
        sun:     S('<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>'),
        moon:    S('<path d="M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10Z"/>'),
        mic:     S('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>'),
        eye:     S('<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.8"/>'),
        camera:  S('<path d="M4 8h3l1.5-2.5h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z"/><circle cx="12" cy="13" r="3.5"/>'),
        search:  S('<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>'),
        cable:   S('<path d="M7 3v5M11 3v5M5.5 8h7v3a3.5 3.5 0 0 1-7 0V8ZM9 14.5V18a3 3 0 0 0 6 0V9a3 3 0 0 1 6 0v3"/>'),
        flask:   S('<path d="M9.5 3h5M10.5 3v6L5 18.5A1.7 1.7 0 0 0 6.5 21h11a1.7 1.7 0 0 0 1.5-2.5L13.5 9V3"/><path d="M7.5 15h9"/>'),
        cube:    S('<path d="m12 2.8 8 4.5v9.4l-8 4.5-8-4.5V7.3l8-4.5Z"/><path d="m4 7.3 8 4.5 8-4.5M12 11.8v9.4"/>'),
        crash:   S('<path d="M12 3 14 8l5-1.5-2.5 4.5L21 14l-5 .8.5 5.2-4.5-3-4.5 3 .5-5.2-5-.8 4.5-3L5 6.5 10 8l2-5Z"/>'),
        noentry: S('<circle cx="12" cy="12" r="8.5"/><path d="M7.5 12h9"/>', 'stroke-width="2.2"'),
        siren:   S('<path d="M7 17v-5a5 5 0 0 1 10 0v5M5 17h14v3H5zM12 3v2M4.5 6l1.4 1.4M19.5 6l-1.4 1.4"/>'),
        cone:    S('<path d="M10 4h4l4.5 15h-13L10 4ZM8.2 10.5h7.6M7 15h10M3.5 19.5h17"/>'),
        traffic: S('<rect x="8" y="2.5" width="8" height="19" rx="3"/><circle cx="12" cy="7" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="17" r="1.5"/>'),
        rain:    S('<path d="M7 15.5a4.5 4.5 0 1 1 1.2-8.8A6 6 0 0 1 19.5 9 3.5 3.5 0 0 1 18 15.5H7ZM8 18.5l-1 2M12 18.5l-1 2M16 18.5l-1 2"/>'),
        tl:      S('<path d="M15 20v-7a3 3 0 0 0-3-3H6M9.5 6.5 6 10l3.5 3.5"/>', 'stroke-width="2.2"'),
        tr:      S('<path d="M9 20v-7a3 3 0 0 1 3-3h6M14.5 6.5 18 10l-3.5 3.5"/>', 'stroke-width="2.2"'),
        st:      S('<path d="M12 20V5M7.5 9.5 12 5l4.5 4.5"/>', 'stroke-width="2.2"'),
        ut:      S('<path d="M8 20v-9a4 4 0 0 1 8 0v4M12.5 12 16 15.5 19.5 12"/>', 'stroke-width="2.2"'),
        rb:      S('<circle cx="12" cy="12" r="4"/><path d="M12 22v-6M16 12h5M18.5 9.5 21 12l-2.5 2.5"/>', 'stroke-width="2.2"'),
        arrive:  S('<path d="M6 21V4M6 4h10.5l-2 4 2 4H6"/>', 'stroke-width="2.2"'),
        rear:    S('<path d="M10 16.5v2M19.5 16.5v2M9 16.5h11.5v-3.8l-1.5-3.6a1.8 1.8 0 0 0-1.7-1.1h-5.1a1.8 1.8 0 0 0-1.7 1.1L9 12.7v3.8Z"/><path d="M2.5 10h4M3.5 13.5h3.5M2.5 17h4"/>')
    };
    function paintIcons(root = document) {
        root.querySelectorAll('[data-icon]').forEach(el => {
            if (el.dataset.painted) return;
            const svg = ICONS[el.dataset.icon];
            if (svg) { el.insertAdjacentHTML('afterbegin', svg); el.dataset.painted = '1'; }
        });
    }
    paintIcons();

    /* ------------------------------------------------------------------ */
    /* Helpers                                                             */
    /* ------------------------------------------------------------------ */
    const $ = (sel, root = document) => root.querySelector(sel);
    const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
    const app = $('#app');
    // the app shell never scrolls (focusing an input inside a sliding sheet would otherwise shift it)
    app.addEventListener('scroll', () => { if (app.scrollTop || app.scrollLeft) { app.scrollTop = 0; app.scrollLeft = 0; } });
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
    const store = {
        get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (_) { return d; } },
        set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* storage blocked */ } }
    };
    async function api(path, body) {
        const opts = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
        const res = await fetch(`/api${path}`, opts);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
        return data;
    }
    function fmtMins(m) {
        if (!isFinite(m)) return '--';
        m = Math.max(1, Math.round(m));
        return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')}`;
    }
    const fmtShort = (m) => isFinite(m) ? (Math.round(m) < 60 ? `${Math.max(1, Math.round(m))}m` : `${Math.floor(m / 60)}h${String(Math.round(m) % 60).padStart(2, '0')}`) : '--';
    function fmtDist(m) {
        if (!isFinite(m)) return '';
        if (m < 950) return `${Math.max(10, Math.round(m / 10) * 10)} m`;
        return `${(m / 1000).toFixed(m < 9500 ? 1 : 0)} km`;
    }
    function ago(ts) {
        const s = Math.max(0, Date.now() / 1000 - ts);
        if (s < 50) return 'now';
        if (s < 3600) return `${Math.round(s / 60)}m`;
        if (s < 86400) return `${Math.round(s / 3600)}h`;
        return `${Math.round(s / 86400)}d`;
    }
    function haversine(a, b) {
        const R = 6371000, toR = Math.PI / 180;
        const dLat = (b[0] - a[0]) * toR, dLng = (b[1] - a[1]) * toR;
        const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * toR) * Math.cos(b[0] * toR) * Math.sin(dLng / 2) ** 2;
        return 2 * R * Math.asin(Math.sqrt(h));
    }
    function bearing(a, b) {
        const toR = Math.PI / 180;
        const y = Math.sin((b[1] - a[1]) * toR) * Math.cos(b[0] * toR);
        const x = Math.cos(a[0] * toR) * Math.sin(b[0] * toR) - Math.sin(a[0] * toR) * Math.cos(b[0] * toR) * Math.cos((b[1] - a[1]) * toR);
        return (Math.atan2(y, x) / toR + 360) % 360;
    }
    let toastTimer = null;
    function toast(msg) {
        const el = $('#toast');
        el.textContent = msg;
        el.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => { el.hidden = true; }, 2800);
    }
    function vibrate(pattern) {
        if (settings.haptics && navigator.vibrate) navigator.vibrate(pattern);
    }

    /* ------------------------------------------------------------------ */
    /* State                                                               */
    /* ------------------------------------------------------------------ */
    const settings = {
        haptics: store.get('sx-haptics', true),
        autoPop: store.get('sx-autopop', true),
        mapTheme: store.get('sx-map-theme', 'auto'),
        mapType: store.get('sx-map-type', 'default'),
        traffic: store.get('sx-layer-traffic', true),
        hazards: store.get('sx-layer-hazards', true),
        health: store.get('sx-layer-health', true),
        limit: store.get('sx-limit', 40)
    };
    const DEMO_DEFAULT = { active: false, preset: null, speed: 40, alerts: [], temp: 27, night: false, lanes: [0, 0, 0, 0], hardware: false, speederSpeed: 120 };
    const demo = Object.assign({}, DEMO_DEFAULT, store.get('sx-demo', {}));
    const state = {
        liveTele: null,     // from the SentraX server
        tele: null,         // what the app shows: live, or Test lab conditions
        live: false,
        serverUp: false,
        hw: null,
        route: null,        // { points, cum, distance, duration, steps, mode }
        alts: [],
        etas: {},
        origin: store.get('sx-origin', { name: 'Woxsen North Roundabout', lat: 17.6638, lng: 77.9272 }),
        dest: store.get('sx-dest', { name: 'Woxsen Hostels & Blue Embers', lat: 17.6596, lng: 77.9248 }),
        tapMode: null,
        mode: store.get('sx-mode', 'drive'),
        events: [],
        eventsLoaded: false,
        selectedAlert: null,
        driving: false,
        stepIdx: 0,
        travelled: 0,       // metres along the route (simulated drive or GPS)
        gps: null,
        view: null,         // tele with the hazards you have already passed cleared
        stationAt: 0,       // metres along the route where the SentraX station sits
        zones: new Map(),   // alert id -> metres along the route where it sits
        cleared: new Set()  // alert ids you have driven past (cleared 25 m after)
    };

    /* ------------------------------------------------------------------ */
    /* Layout: keep panels from covering each other                        */
    /* ------------------------------------------------------------------ */
    const ro = new ResizeObserver(() => {
        app.style.setProperty('--planner-h', `${$('#planner').offsetHeight}px`);
        app.style.setProperty('--dock-h', `${$('#dock').offsetHeight}px`);
    });
    ro.observe($('#planner'));
    ro.observe($('#dock'));

    /* ------------------------------------------------------------------ */
    /* Map and base layers                                                 */
    /* ------------------------------------------------------------------ */
    // explicit zoom range: the vector layer has no maxZoom, which would make Leaflet's max zoom NaN
    // and break fitBounds (blank map, taps ignored)
    const map = L.map('map', { zoomControl: false, attributionControl: true, worldCopyJump: true, minZoom: 2, maxZoom: 19 })
        .setView([state.origin.lat, state.origin.lng], 15);
    map.attributionControl.setPrefix(false);
    // keep the map filling the screen through rotations and window resizes
    // (a route fit asked for while the map had no size yet runs once it gets one)
    new ResizeObserver(() => { map.invalidateSize({ pan: false }); if (pendingFit) fitRoute(); }).observe($('#map'));

    // Default map: OpenFreeMap vector styles (free, no key). Raster layers cover satellite and terrain,
    // and Esri streets stand in if the browser cannot run the vector map (no WebGL).
    const VECTOR_STYLE = { day: 'https://tiles.openfreemap.org/styles/liberty', night: 'https://tiles.openfreemap.org/styles/dark' };
    const VECTOR_ATTR = '<a href="https://openfreemap.org">OpenFreeMap</a> &copy; <a href="https://www.openmaptiles.org/">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
    const BASES = {
        streets: { url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', maxZoom: 19,
            attribution: 'Map &copy; Esri, HERE, Garmin, &copy; OpenStreetMap' },
        satellite: { url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', maxZoom: 19,
            attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics' },
        terrain: { url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', maxZoom: 17, subdomains: 'abc',
            attribution: '&copy; OpenStreetMap, SRTM | &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)' }
    };
    let baseLayer = null;
    let vectorTheme = null;
    function vectorOk() {
        if (!L.maplibreGL || !window.maplibregl) return false;
        try { const c = document.createElement('canvas'); return Boolean(c.getContext('webgl2') || c.getContext('webgl')); } catch (_) { return false; }
    }
    function setBase(type) {
        if (baseLayer) map.removeLayer(baseLayer);
        vectorTheme = null;
        if (type === 'default' && vectorOk()) {
            vectorTheme = resolvedTheme();
            baseLayer = L.maplibreGL({ style: VECTOR_STYLE[vectorTheme], attribution: VECTOR_ATTR, minZoom: 2, maxZoom: 19 }).addTo(map);
            app.dataset.mapType = 'default';
            return;
        }
        const cfg = BASES[type] || BASES.streets;
        baseLayer = L.tileLayer(cfg.url, { maxZoom: cfg.maxZoom, subdomains: cfg.subdomains || 'abc', attribution: cfg.attribution }).addTo(map);
        baseLayer.bringToBack();
        app.dataset.mapType = type === 'default' ? 'streets' : type;
    }
    function resolvedTheme() {
        if (settings.mapTheme !== 'auto') return settings.mapTheme;
        if (state.live && state.tele) return state.tele.night_mode ? 'night' : 'day';
        const h = new Date().getHours();
        return (h >= 19 || h < 6) ? 'night' : 'day';
    }
    function applyMapTheme() {
        const t = resolvedTheme();
        app.dataset.mapTheme = t;
        // the vector map swaps to its own dark style at night
        if (vectorTheme && vectorTheme !== t && baseLayer?.getMaplibreMap) {
            vectorTheme = t;
            baseLayer.getMaplibreMap().setStyle(VECTOR_STYLE[t]);
        }
    }
    setBase(settings.mapType);
    applyMapTheme();

    const altGroup = L.layerGroup().addTo(map);
    const routeGroup = L.layerGroup().addTo(map);
    const trafficGroup = L.layerGroup().addTo(map);
    const hazardGroup = L.layerGroup().addTo(map);
    const pinGroup = L.layerGroup().addTo(map);
    let stationMarker = null, carMarker = null, gpsMarker = null;

    const originIcon = L.divIcon({ className: '', html: '<div class="mk mk-origin"></div>', iconSize: [22, 22], iconAnchor: [11, 11] });
    const destIcon = L.divIcon({
        className: '',
        html: `<div class="mk mk-dest"><svg viewBox="0 0 30 40"><path d="M15 39C15 39 2 23.5 2 14a13 13 0 0 1 26 0c0 9.5-13 25-13 25Z" fill="#1E1A12" stroke="#FBF7EF" stroke-width="2"/><circle cx="15" cy="14" r="5.5" fill="#E1A43A"/></svg></div>`,
        iconSize: [30, 40], iconAnchor: [15, 39]
    });

    /* ------------------------------------------------------------------ */
    /* Routing: OSRM on OpenStreetMap data, works worldwide                */
    /* ------------------------------------------------------------------ */
    const ROUTERS = { drive: 'routed-car', bike: 'routed-bike', walk: 'routed-foot' };
    function osrmUrl(mode, a, b, full) {
        const coords = `${a.lng},${a.lat};${b.lng},${b.lat}`;
        const q = full ? 'overview=full&geometries=geojson&steps=true&alternatives=true' : 'overview=false';
        return `https://routing.openstreetmap.de/${ROUTERS[mode]}/route/v1/driving/${coords}?${q}`;
    }
    function dirWord(b) { return ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west'][Math.round(((b || 0) % 360) / 45) % 8]; }
    function stepText(s) {
        const m = s.maneuver || {};
        const name = s.name || s.ref || '';
        const on = name ? ` onto ${name}` : '';
        const mod = (m.modifier || '').replace('slight ', 'slightly ').replace('sharp ', 'sharp ');
        switch (m.type) {
            case 'depart': return `Head ${dirWord(m.bearing_after)}${name ? ` on ${name}` : ''}`;
            case 'arrive': return 'Arrive at your destination';
            case 'roundabout': case 'rotary': case 'exit roundabout': case 'exit rotary':
                return `At the roundabout, take exit ${m.exit || 1}${on}`;
            case 'merge': return `Merge ${mod}${on}`;
            case 'on ramp': return `Take the ramp${on}`;
            case 'off ramp': return `Take the exit${on}`;
            case 'fork': return `Keep ${String(m.modifier).includes('left') ? 'left' : 'right'}${on}`;
            case 'continue': case 'new name': return `Continue${name ? ` on ${name}` : ''}`;
            default:
                if (m.modifier === 'straight') return `Continue straight${name ? ` on ${name}` : ''}`;
                if (m.modifier === 'uturn') return 'Make a U-turn';
                return `Turn ${mod}${on}`;
        }
    }
    function stepIcon(s) {
        const m = s.maneuver || {};
        if (m.type === 'arrive') return 'arrive';
        if (m.type && m.type.includes('roundabout') || m.type === 'rotary') return 'rb';
        const mod = m.modifier || '';
        if (mod === 'uturn') return 'ut';
        if (mod.includes('left')) return 'tl';
        if (mod.includes('right')) return 'tr';
        return 'st';
    }
    function buildRoute(r, mode) {
        const points = r.geometry.coordinates.map(([lng, lat]) => [lat, lng]);
        const cum = [0];
        for (let i = 1; i < points.length; i++) cum.push(cum[i - 1] + haversine(points[i - 1], points[i]));
        let at = 0;
        const steps = (r.legs?.[0]?.steps || []).map(s => {
            const st = { text: stepText(s), icon: stepIcon(s), dist: s.distance, start: at, loc: [s.maneuver.location[1], s.maneuver.location[0]] };
            at += s.distance;
            return st;
        });
        return { points, cum, distance: r.distance, duration: r.duration / 60, steps, mode };
    }
    function straightRoute(mode) {
        const a = [state.origin.lat, state.origin.lng], b = [state.dest.lat, state.dest.lng];
        const d = haversine(a, b);
        const kmh = { drive: 40, bike: 15, walk: 5 }[mode];
        return { points: [a, b], cum: [0, d], distance: d, duration: d / 1000 / kmh * 60, mode, offline: true,
            steps: [{ text: `Head ${dirWord(bearing(a, b))} towards ${state.dest.name}`, icon: 'st', dist: d, start: 0, loc: a },
                    { text: 'Arrive at your destination', icon: 'arrive', dist: 0, start: d, loc: b }] };
    }

    let routeReq = 0;
    async function loadRoute(fit) {
        const id = ++routeReq;
        $('#trip-via').textContent = 'Finding the best route...';
        const mode = state.mode;
        try {
            const res = await fetch(osrmUrl(mode, state.origin, state.dest, true));
            const data = await res.json();
            if (id !== routeReq) return;
            if (data.code !== 'Ok' || !data.routes?.length) throw new Error(data.message || 'No route');
            state.route = buildRoute(data.routes[0], mode);
            state.alts = data.routes.slice(1, 3).map(r => buildRoute(r, mode));
        } catch (e) {
            if (id !== routeReq) return;
            state.route = straightRoute(mode);
            state.alts = [];
            toast('Road routing unavailable. Showing a straight line.');
        }
        state.etas[mode] = state.route.duration;
        state.stepIdx = 0;
        state.travelled = 0;
        state.stationAt = stationFor(state.route);
        resetZones();
        renderTrip();
        drawRoute();
        if (fit) fitRoute();
        loadEtas(id);
    }
    // travel time for the other modes (quick requests, no geometry)
    async function loadEtas(id) {
        await Promise.all(Object.keys(ROUTERS).filter(m => m !== state.mode).map(async (m) => {
            try {
                const data = await (await fetch(osrmUrl(m, state.origin, state.dest, false))).json();
                if (id === routeReq && data.routes?.[0]) state.etas[m] = data.routes[0].duration / 60;
            } catch (_) { state.etas[m] = NaN; }
        }));
        if (id === routeReq) renderTrip();
    }

    /* Point at a distance along the route */
    function along(route, metres) {
        const { points, cum } = route;
        const d = clamp(metres, 0, cum[cum.length - 1]);
        let i = 1;
        while (i < cum.length - 1 && cum[i] < d) i++;
        const seg = cum[i] - cum[i - 1] || 1;
        const f = (d - cum[i - 1]) / seg;
        const p = [points[i - 1][0] + (points[i][0] - points[i - 1][0]) * f, points[i - 1][1] + (points[i][1] - points[i - 1][1]) * f];
        return { p, i, heading: bearing(points[i - 1], points[i]) };
    }
    function slice(route, from, to) {
        const out = [along(route, from).p];
        route.cum.forEach((c, k) => { if (c > from && c < to) out.push(route.points[k]); });
        out.push(along(route, to).p);
        return out;
    }

    /* ------------------------------------------------------------------ */
    /* Road conditions: live sensors or the Test lab                       */
    /* ------------------------------------------------------------------ */
    const ALERTS = [
        { id: 'collision', name: 'Accident', icon: 'crash', sev: 'crit' },
        { id: 'wrong', name: 'Wrong way', icon: 'noentry', sev: 'crit' },
        { id: 'emergency', name: 'Ambulance', icon: 'siren', sev: 'crit' },
        { id: 'stall', name: 'Stalled car', icon: 'cone', sev: 'warn' },
        { id: 'congestion', name: 'Traffic jam', icon: 'traffic', sev: 'warn' },
        { id: 'wet', name: 'Wet road', icon: 'rain', sev: 'warn' },
        { id: 'heat', name: 'Heat', icon: 'sun', sev: 'warn' },
        { id: 'speeder', name: 'Speeder behind', icon: 'rear', sev: 'warn' }
    ];
    const PRESETS = [
        { id: 'normal', name: 'Normal drive', sub: '45 km/h, clear road', icon: 'car', speed: 45, alerts: [] },
        { id: 'speeding', name: 'Overspeeding', sub: '95 km/h on an 80 road', icon: 'speed', speed: 95, alerts: [] },
        { id: 'rain', name: 'Rainy road', sub: 'Wet surface, 55 km/h', icon: 'rain', speed: 55, alerts: ['wet'] },
        { id: 'traffic', name: 'Heavy traffic', sub: '3 lanes queued', icon: 'traffic', speed: 25, alerts: ['congestion'], lanes: [1, 1, 1, 0] },
        { id: 'accident', name: 'Accident ahead', sub: 'Impact at the station', icon: 'crash', speed: 55, alerts: ['collision'], sev: 'crit' },
        { id: 'wrongway', name: 'Wrong-way driver', sub: 'Vehicle against traffic', icon: 'noentry', speed: 50, alerts: ['wrong'], sev: 'crit' },
        { id: 'ambulance', name: 'Ambulance behind', sub: 'RFID priority vehicle', icon: 'siren', speed: 45, alerts: ['emergency'], sev: 'crit' },
        { id: 'stalled', name: 'Stalled vehicle', sub: 'Lane 2 blocked', icon: 'cone', speed: 40, alerts: ['stall'], lanes: [0, 1, 0, 0] },
        { id: 'heatwave', name: 'Heatwave', sub: '41 °C road surface', icon: 'sun', speed: 50, alerts: ['heat'], temp: 41 },
        { id: 'night', name: 'Night drive', sub: 'Low light, dark map', icon: 'moon', speed: 55, alerts: [], night: true },
        { id: 'speederbehind', name: 'Speeder behind', sub: 'Car closing at 120 km/h', icon: 'rear', speed: 50, alerts: ['speeder'], speeder: 120 }
    ];

    // Same speed rules as the ESP32 firmware (updateSpeedLimit)
    function adviseSpeed(a) {
        if (a.has('collision')) return 20;
        if (a.has('wrong')) return 25;
        if (a.has('stall')) return 30;
        if (a.has('heat')) return 35;
        if (a.has('wet')) return 40;
        if (a.has('congestion')) return 60;
        return 80;
    }
    function riskFor(t) {
        let s = 6;
        const why = [];
        if (t.collision) { s += 55; why.push('Collision detected by the impact mic'); }
        if (t.wrong_way) { s += 55; why.push('Vehicle travelling against traffic'); }
        if (t.emergency_vehicle) { s += 22; why.push('Emergency vehicle needs a clear lane'); }
        if (t.stalled_vehicle) { s += 30; why.push('Stationary vehicle blocking a lane'); }
        if (t.traffic_level === 'CONGESTED') { s += 18; why.push(`${t.traffic_count} of 4 lanes occupied`); }
        if (t.road_condition === 'WET') { s += 22; why.push('Wet surface: longer braking distance'); }
        if (t.temperature_c >= 30) { s += 12; why.push(`Hot road at ${Number(t.temperature_c).toFixed(0)} °C`); }
        if (t.night_mode) { s += 8; why.push('Low light'); }
        const over = t.measured_speed_kmh - t.recommended_speed_kmh;
        if (over > 2) { s += Math.min(30, over * 1.2); why.push(`${Math.round(over)} km/h over the advisory`); }
        if (!why.length) why.push('All sensors normal');
        return { score: Math.round(clamp(s, 0, 100)), reasons: why };
    }
    function demoTele() {
        const a = new Set(demo.alerts);
        let lanes = demo.lanes.slice();
        if (a.has('congestion') && lanes.filter(Boolean).length < 2) lanes = [1, 1, 1, 0];
        if (a.has('stall') && !lanes.some(Boolean)) lanes = [0, 1, 0, 0];
        const occupied = lanes.filter(Boolean).length;
        const t = {
            device_id: 'SENTRAX-DEMO', timestamp: Date.now() / 1000,
            measured_speed_kmh: demo.speed, recommended_speed_kmh: adviseSpeed(a), posted_speed_kmh: 80,
            traffic_count: occupied, traffic_level: a.has('congestion') || occupied >= 3 ? 'CONGESTED' : 'LIGHT',
            road_condition: a.has('wet') ? 'WET' : 'DRY',
            collision: a.has('collision'), wrong_way: a.has('wrong'), stalled_vehicle: a.has('stall'), emergency_vehicle: a.has('emergency'),
            temperature_c: a.has('heat') ? Math.max(demo.temp, 38) : demo.temp,
            humidity_pct: a.has('wet') ? 88 : 54, moisture_raw: a.has('wet') ? 1380 : 3120,
            ir_sensors: lanes.map(Boolean), sound_active: a.has('collision'), rfid_active: a.has('emergency'),
            night_mode: demo.night, speeder_behind_kmh: a.has('speeder') ? demo.speederSpeed : 0, cv_vehicle_count: occupied + (a.has('stall') ? 1 : 0),
            ultrasonic_state: { us1_active: demo.speed > 0, us2_active: false, measuring: demo.speed > 0 },
            hardware_standby: false, is_simulated: true, esp32_connected: false, esp8266_connected: false
        };
        const r = riskFor(t);
        t.risk_score = r.score;
        t.risk_reasons = r.reasons;
        return t;
    }

    // Road health for the active route, from whichever telemetry is showing
    function healthFor(t) {
        if (!state.live || !t) return { score: null, band: 'GOOD', summary: 'Sensors offline' };
        if (t.collision) return { score: 28, band: 'CRITICAL', summary: 'Accident on the road' };
        if (t.wrong_way) return { score: 32, band: 'CRITICAL', summary: 'Wrong-way vehicle' };
        if (t.stalled_vehicle) return { score: 52, band: 'POOR', summary: 'Stalled vehicle in lane' };
        if (t.emergency_vehicle) return { score: 60, band: 'MODERATE', summary: 'Emergency vehicle nearby' };
        if (t.road_condition === 'WET') return { score: 68, band: 'MODERATE', summary: 'Wet road surface' };
        if (t.traffic_level === 'CONGESTED') return { score: 64, band: 'MODERATE', summary: 'Heavy traffic' };
        if (t.temperature_c >= 30) return { score: 74, band: 'MODERATE', summary: 'Hot road surface' };
        return { score: 86, band: 'GOOD', summary: t.night_mode ? 'Clear road, low light' : 'Corridor clear' };
    }
    function healthColor(band) {
        return { GOOD: '#7FA35C', MODERATE: '#E1A43A', POOR: '#D9793A', CRITICAL: '#D0503F' }[band] || '#E1A43A';
    }
    // The SentraX roadside station sits at a fixed point on the route. Live sensor events have no
    // GPS position of their own, so they are pinned there.
    function stationFor(r) { return Math.min(r.cum[r.cum.length - 1] * 0.45, 1200); }
    function hazardDistance() { return state.route ? state.stationAt : 0; }

    /* ------------------------------------------------------------------ */
    /* Drawing                                                             */
    /* ------------------------------------------------------------------ */
    function drawRoute() {
        altGroup.clearLayers(); routeGroup.clearLayers(); trafficGroup.clearLayers(); pinGroup.clearLayers();
        if (state.origin) L.marker([state.origin.lat, state.origin.lng], { icon: originIcon, interactive: false }).addTo(pinGroup);
        if (state.dest) L.marker([state.dest.lat, state.dest.lng], { icon: destIcon, interactive: false }).addTo(pinGroup);
        const r = state.route;
        if (!r) { drawHazards(); return; }

        // alternative routes: grey, tap to switch
        state.alts.forEach((alt, k) => {
            L.polyline(alt.points, { color: '#8A8070', weight: 7, opacity: 0.75, lineCap: 'round' }).addTo(altGroup)
                .on('click', () => {
                    const cur = state.route;
                    state.route = alt; state.alts[k] = cur;
                    state.stationAt = stationFor(alt);
                    resetZones();
                    state.etas[state.mode] = alt.duration;
                    renderTrip(); drawRoute(); vibrate(15);
                    toast(`Switched route: ${fmtMins(alt.duration)}, ${fmtDist(alt.distance)}`);
                });
        });

        const total = r.cum[r.cum.length - 1];
        const v = state.view;
        const h = healthFor(v);
        L.polyline(r.points, { color: '#1E1A12', weight: 13, opacity: 0.3, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(routeGroup);
        const base = settings.health && state.live ? (h.band === 'MODERATE' && (v.road_condition === 'WET' || v.temperature_c >= 30) ? '#E1A43A' : '#7FA35C') : '#E1A43A';
        L.polyline(r.points, { color: base, weight: 8, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(routeGroup);
        if (settings.health && state.live && (h.band === 'CRITICAL' || h.band === 'POOR' || v.traffic_level === 'CONGESTED' || v.emergency_vehicle)) {
            const at = hazardDistance();
            const span = Math.min(260, total * 0.12);
            L.polyline(slice(r, at - span, at + span * 0.6), { color: healthColor(h.band === 'GOOD' ? 'MODERATE' : h.band), weight: 8, lineCap: 'round', interactive: false }).addTo(routeGroup);
        }
        // walked or driven part greys out
        if (state.travelled > 1) L.polyline(slice(r, 0, state.travelled), { color: '#8A8070', weight: 8, lineCap: 'round', interactive: false }).addTo(routeGroup);
        L.polyline(r.points, { color: '#FBF7EF', weight: 3, opacity: 0.9, className: 'route-flow', lineCap: 'round', interactive: false }).addTo(routeGroup);

        if (settings.traffic && state.live && v.traffic_level === 'CONGESTED') {
            const at = hazardDistance();
            L.polyline(slice(r, at - Math.min(500, total * 0.2), at), { color: '#D0503F', weight: 4, opacity: 0.9, dashArray: '2 8', lineCap: 'round', interactive: false }).addTo(trafficGroup);
        }

        // the SentraX roadside sensor station
        stationMarker = L.marker(along(r, hazardDistance()).p, {
            icon: L.divIcon({ className: '', html: `<div class="mk mk-station" data-live="${state.live ? 1 : 0}"></div>`, iconSize: [18, 18], iconAnchor: [9, 9] }),
            zIndexOffset: 200
        }).addTo(pinGroup).on('click', () => openSheet('twin'));
        drawHazards();
    }

    function drawHazards() {
        hazardGroup.clearLayers();
        if (!settings.hazards || !state.route) return;
        const all = activeAlerts();
        all.filter(a => a.onRoad).forEach((a) => {
            const pos = along(state.route, a.at ?? hazardDistance()).p;
            const icon = L.divIcon({
                className: '',
                html: `<div class="mk mk-alert ${a.id === state.selectedAlert ? 'is-selected' : ''}" data-sev="${a.sev}"><span>${ICONS[a.icon] || ICONS.warn}</span></div>`,
                iconSize: [26, 26], iconAnchor: [13, 13]
            });
            L.marker(pos, { icon, zIndexOffset: 300 }).addTo(hazardGroup).on('click', () => {
                state.selectedAlert = a.id;
                drawHazards();
                showSentriFor(a);
            });
        });
        // a fast car closing in behind you
        const sp = all.find(a => a.id === 'speeder');
        if (sp) {
            L.marker(along(state.route, Math.max(0, state.travelled - 35)).p, {
                icon: L.divIcon({ className: '', html: `<div class="mk mk-speeder">${ICONS.rear}</div>`, iconSize: [26, 26], iconAnchor: [13, 13] }),
                zIndexOffset: 450
            }).addTo(hazardGroup).on('click', () => showSentriFor(sp));
        }
    }

    let pendingFit = false;
    function fitRoute() {
        // fitting a 0x0 map gives a NaN zoom: blank map and dead taps
        map.invalidateSize({ pan: false });
        const sz = map.getSize();
        pendingFit = !sz.x || !sz.y;
        if (pendingFit) return;
        const pad = {
            paddingTopLeft: [56, ($('#planner').offsetHeight || 120) + 30],
            paddingBottomRight: [64, ($('#dock').offsetHeight || 170) + 30]
        };
        const pts = state.route?.points;
        if (pts && pts.length > 1) map.fitBounds(L.latLngBounds(pts), pad);
        else if (state.origin) map.setView([state.origin.lat, state.origin.lng], 15);
    }

    /* ------------------------------------------------------------------ */
    /* Trip card                                                           */
    /* ------------------------------------------------------------------ */
    function renderTrip() {
        $('#origin-name').textContent = state.origin.name;
        $('#dest-name').textContent = state.dest.name;
        $$('.mode').forEach(x => x.classList.toggle('is-active', x.dataset.mode === state.mode));
        Object.keys(ROUTERS).forEach(k => { $(`#eta-${k}`).textContent = fmtShort(state.etas[k]); });
        const r = state.route;
        if (!r) return;
        const left = Math.max(0, r.distance - state.travelled);
        $('#trip-time').textContent = atDestination() ? 'Arrived' : fmtMins(r.duration * (left / (r.distance || 1)));
        $('#trip-dist').textContent = atDestination() ? '' : `(${fmtDist(left)})`;
        const h = healthFor(state.view);
        const roadName = r.steps.find(s => /on |onto /.test(s.text))?.text.split(/ on | onto /)[1];
        $('#trip-via').textContent = `${roadName ? `via ${roadName} · ` : ''}${r.offline ? 'straight line' : h.summary}`;
        $('#health').dataset.band = h.band;
        $('#health-val').textContent = h.score ?? '--';
        $('#health-ring').style.strokeDashoffset = String(94.25 * (1 - (h.score || 0) / 100));
    }

    $$('.mode').forEach(b => b.addEventListener('click', () => {
        if (state.mode === b.dataset.mode) return;
        state.mode = b.dataset.mode; store.set('sx-mode', state.mode);
        loadRoute(true);
    }));
    $('#btn-swap').addEventListener('click', () => {
        [state.origin, state.dest] = [state.dest, state.origin];
        store.set('sx-origin', state.origin); store.set('sx-dest', state.dest);
        state.etas = {};
        renderTrip();
        loadRoute(true);
    });

    /* Tap the map to set start / destination */
    function setTapMode(mode) {
        state.tapMode = mode;
        $('#tap-hint').hidden = !state.tapMode;
        $('#tap-hint-what').textContent = state.tapMode === 'origin' ? 'start' : 'destination';
        map.getContainer().style.cursor = state.tapMode ? 'crosshair' : '';
    }
    async function reverseName(lat, lng) {
        try {
            const d = await (await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=17&lat=${lat}&lon=${lng}`, { headers: { 'Accept-Language': 'en' } })).json();
            const a = d.address || {};
            return d.name || [a.road, a.suburb || a.village || a.town || a.city].filter(Boolean).join(', ') || null;
        } catch (_) { return null; }
    }
    async function setPoint(which, lat, lng, name) {
        if (state.tapMode) setTapMode(null);   // a point chosen any other way ends tap-to-pick
        state[which] = { name: name || `${lat.toFixed(4)}, ${lng.toFixed(4)}`, lat, lng };
        store.set(which === 'origin' ? 'sx-origin' : 'sx-dest', state[which]);
        state.etas = {};
        renderTrip();
        loadRoute(false);
        if (!name) {
            const nice = await reverseName(lat, lng);
            if (nice && state[which].lat === lat) { state[which].name = nice; store.set(which === 'origin' ? 'sx-origin' : 'sx-dest', state[which]); renderTrip(); }
        }
    }
    // tap the hint (or press Escape) to cancel picking
    $('#tap-hint').addEventListener('click', () => setTapMode(null));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && state.tapMode) setTapMode(null); });
    map.on('click', (e) => {
        if (!state.tapMode) return;
        const which = state.tapMode;
        setTapMode(null);
        vibrate(15);
        setPoint(which, e.latlng.lat, e.latlng.lng);
    });
    // long-press anywhere drops a destination pin, like Google Maps
    map.on('contextmenu', (e) => { vibrate(20); setPoint('dest', e.latlng.lat, e.latlng.lng); toast('Destination dropped'); });

    /* Map controls */
    $('#btn-zoom-in').addEventListener('click', () => map.zoomIn());
    $('#btn-zoom-out').addEventListener('click', () => map.zoomOut());
    $('#btn-recenter').addEventListener('click', fitRoute);
    function locate(useAsOrigin) {
        if (!('geolocation' in navigator) || !window.isSecureContext) {
            toast('Location needs HTTPS. Open the app on localhost, or pick on the map.');
            return;
        }
        navigator.geolocation.getCurrentPosition((pos) => {
            const ll = [pos.coords.latitude, pos.coords.longitude];
            state.gps = ll;
            if (!gpsMarker) gpsMarker = L.marker(ll, { icon: L.divIcon({ className: '', html: '<div class="mk-gps"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }), zIndexOffset: 400 }).addTo(map);
            else gpsMarker.setLatLng(ll);
            map.setView(ll, 16);
            if (useAsOrigin) setPoint('origin', ll[0], ll[1], 'Your location');
        }, (err) => toast(err.code === 1 ? 'Location permission denied' : 'Could not get your location'), { enableHighAccuracy: true, timeout: 10000 });
    }
    $('#btn-locate').addEventListener('click', () => locate(false));

    const layersPop = $('#layers-pop');
    $('#btn-layers').addEventListener('click', (e) => {
        e.stopPropagation();
        const btn = $('#btn-layers');
        layersPop.hidden = !layersPop.hidden;
        btn.classList.toggle('is-on', !layersPop.hidden);
        layersPop.style.top = `${Math.min(btn.getBoundingClientRect().top, innerHeight - layersPop.offsetHeight - 20)}px`;
    });
    document.addEventListener('click', (e) => {
        if (!layersPop.hidden && !layersPop.contains(e.target)) { layersPop.hidden = true; $('#btn-layers').classList.remove('is-on'); }
    });
    $$('#map-type-seg button').forEach(b => {
        b.classList.toggle('is-active', b.dataset.type === settings.mapType);
        b.addEventListener('click', () => {
            settings.mapType = b.dataset.type; store.set('sx-map-type', settings.mapType);
            $$('#map-type-seg button').forEach(x => x.classList.toggle('is-active', x === b));
            setBase(settings.mapType);
        });
    });
    $$('#map-theme-seg button').forEach(b => {
        b.classList.toggle('is-active', b.dataset.theme === settings.mapTheme);
        b.addEventListener('click', () => {
            settings.mapTheme = b.dataset.theme; store.set('sx-map-theme', settings.mapTheme);
            $$('#map-theme-seg button').forEach(x => x.classList.toggle('is-active', x === b));
            applyMapTheme();
        });
    });
    [['layer-traffic', 'traffic'], ['layer-hazards', 'hazards'], ['layer-health', 'health']].forEach(([id, key]) => {
        const el = $(`#${id}`);
        el.checked = settings[key];
        el.addEventListener('change', () => { settings[key] = el.checked; store.set(`sx-${id}`, el.checked); drawRoute(); });
    });

    /* ------------------------------------------------------------------ */
    /* Driving: turn-by-turn banner, simulated drive or GPS                */
    /* ------------------------------------------------------------------ */
    const banner = document.createElement('div');
    banner.className = 'nav-banner';
    banner.innerHTML = `<span id="nav-icon">${ICONS.st}</span>
        <div class="nav-text"><b id="nav-next">Head off</b><span id="nav-sub"></span></div>
        <div class="nav-step-btns"><button type="button" id="nav-prev" aria-label="Previous step">${ICONS.chevL}</button><button type="button" id="nav-nextbtn" aria-label="Next step">${ICONS.chevR}</button></div>`;
    app.appendChild(banner);

    let simTimer = null, gpsWatch = null;
    const SIM_SPEEDUP = 4;   // simulated drive runs 4x real time so the demo moves
    function currentStep() {
        const r = state.route;
        if (!r || !r.steps.length) return null;
        let i = 0;
        while (i < r.steps.length - 1 && r.steps[i + 1].start <= state.travelled + 1) i++;
        return i;
    }
    function renderBanner() {
        const r = state.route;
        if (!r || !r.steps.length) return;
        const following = simTimer || gpsWatch;
        const i = following ? currentStep() : state.stepIdx;
        const next = following ? (r.steps[i + 1] || r.steps[i]) : r.steps[i];
        const dist = following ? next.start - state.travelled : r.steps[i].dist;
        $('#nav-icon').innerHTML = ICONS[next.icon] || ICONS.st;
        $('#nav-next').textContent = next.text;
        const rec = state.live && state.view ? Math.round(state.view.recommended_speed_kmh) : null;
        $('#nav-sub').textContent = `${following ? `In ${fmtDist(Math.max(0, dist))}` : `Step ${i + 1} of ${r.steps.length} · ${fmtDist(dist)}`}${rec ? ` · keep to ${rec} km/h` : ''}`;
        $('.nav-step-btns').style.display = following ? 'none' : '';
    }
    $('#nav-prev').addEventListener('click', () => { state.stepIdx = Math.max(0, state.stepIdx - 1); focusStep(); });
    $('#nav-nextbtn').addEventListener('click', () => { state.stepIdx = Math.min(state.route.steps.length - 1, state.stepIdx + 1); focusStep(); });
    function focusStep() {
        const s = state.route?.steps[state.stepIdx];
        if (s) map.flyTo(s.loc, 17, { duration: 0.5 });
        renderBanner();
    }

    function placeCar() {
        const r = state.route;
        if (!r) return;
        const { p, heading } = along(r, state.travelled);
        const html = `<div class="mk-car"><svg viewBox="0 0 24 24" fill="currentColor" style="transform:rotate(${heading}deg)"><path d="M12 2.8 19.5 20 12 16.2 4.5 20 12 2.8Z"/></svg></div>`;
        if (!carMarker) carMarker = L.marker(p, { icon: L.divIcon({ className: '', html, iconSize: [30, 30], iconAnchor: [15, 15] }), zIndexOffset: 500 }).addTo(map);
        else { carMarker.setLatLng(p); carMarker.setIcon(L.divIcon({ className: '', html, iconSize: [30, 30], iconAnchor: [15, 15] })); }
        map.panTo(p, { animate: true, duration: 0.25 });
    }
    function startDriving() {
        if (!state.route) { toast('Plan a route first'); return; }
        state.driving = true;
        app.classList.add('is-driving');
        $('#start-label').textContent = 'Stop';
        state.travelled = 0;
        state.stepIdx = 0;
        resetZones();
        if (demo.active) {
            // Test lab: drive the route at the chosen speed
            map.setView(state.route.points[0], 17);
            simTimer = setInterval(() => {
                const total = state.route.cum[state.route.cum.length - 1];
                state.travelled += Math.max(demo.speed, 0) / 3.6 * 0.25 * SIM_SPEEDUP;
                if (state.travelled >= total) {
                    state.travelled = total;
                    placeCar(); renderBanner();
                    arrive();
                    return;
                }
                placeCar();
                refresh();
            }, 250);
            placeCar();
        } else if ('geolocation' in navigator && window.isSecureContext) {
            gpsWatch = navigator.geolocation.watchPosition((pos) => {
                const ll = [pos.coords.latitude, pos.coords.longitude];
                // snap to the nearest route point for progress
                let best = 0, bestD = Infinity;
                state.route.points.forEach((pt, k) => { const d = haversine(pt, ll); if (d < bestD) { bestD = d; best = k; } });
                state.travelled = state.route.cum[best];
                if (!gpsMarker) gpsMarker = L.marker(ll, { icon: L.divIcon({ className: '', html: '<div class="mk-gps"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }), zIndexOffset: 400 }).addTo(map);
                else gpsMarker.setLatLng(ll);
                map.panTo(ll);
                const total = state.route.cum[state.route.cum.length - 1];
                if (haversine(ll, [state.dest.lat, state.dest.lng]) < 25 || state.travelled >= total - 25) { state.travelled = total; arrive(); return; }
                refresh();
            }, () => { toast('No GPS fix. Use the arrows to preview steps.'); navigator.geolocation.clearWatch(gpsWatch); gpsWatch = null; renderBanner(); },
            { enableHighAccuracy: true });
            map.setView(state.route.points[0], 17);
        } else {
            focusStep();
        }
        renderBanner();
        mini && mini.act('wave', 1400);
    }
    function stopDriving(keepPosition) {
        clearInterval(simTimer); simTimer = null;
        if (gpsWatch !== null) { navigator.geolocation.clearWatch(gpsWatch); gpsWatch = null; }
        state.driving = false;
        app.classList.remove('is-driving');
        $('#start-label').textContent = 'Start';
        if (!keepPosition) {
            state.travelled = 0;
            resetZones();
            if (carMarker) { map.removeLayer(carMarker); carMarker = null; }
        }
        refresh(true);
    }
    function atDestination() {
        const r = state.route;
        return Boolean(r) && !state.driving && state.travelled >= r.cum[r.cum.length - 1] - 1;
    }
    // Reached the destination: everything on the route is behind you. Sentri waves goodbye.
    function arrive() {
        stopDriving(true);
        state.zones.forEach((_, id) => state.cleared.add(id));
        refresh(true);
        [mini, big].forEach(s => s && s.act('bye', 5600));
        if (big) { big.play('bye'); big.say('You have arrived. Bye-bye, drive safe!'); }
        setPop(true, 6000, { sev: 'good', icon: 'arrive', title: 'You have arrived', sub: `${state.dest?.name || 'Destination'}. Bye-bye, drive safe!` });
        vibrate([60, 40, 60]);
    }
    $('#btn-start').addEventListener('click', () => { if (state.driving) { stopDriving(); fitRoute(); } else startDriving(); });

    /* ------------------------------------------------------------------ */
    /* Speed + limiter                                                     */
    /* ------------------------------------------------------------------ */
    function renderSpeed() {
        const t = state.view;
        const spd = state.live && t ? Math.round(t.measured_speed_kmh || 0) : 0;
        const rec = t ? Math.round(t.recommended_speed_kmh || 0) : 0;
        $('#speed-val').textContent = spd;
        $('#limit-val').textContent = state.live && rec ? rec : '--';
        $('.your-speed').classList.toggle('is-over', state.live && rec > 0 && spd > rec + 2);
    }
    function renderLimiter() {
        $$('.lim-chip').forEach(c => c.classList.toggle('is-active', Number(c.dataset.lim) === settings.limit));
    }
    async function sendLimit(enabled) {
        try {
            const r = await api('/speed/limit', { limit: settings.limit, enabled });
            toast(enabled
                ? `Limit ${r.limit} km/h ${r.sent_to_hardware ? 'sent to ESP32' : 'saved (ESP32 not linked)'}`
                : 'Limiter off: back to 80 km/h');
        } catch (e) { toast(e.message); }
    }
    $$('.lim-chip').forEach(c => c.addEventListener('click', () => {
        settings.limit = Number(c.dataset.lim); store.set('sx-limit', settings.limit);
        renderLimiter();
        if ($('#limiter-on').checked) sendLimit(true);
    }));
    $('#limiter-on').addEventListener('change', (e) => sendLimit(e.target.checked));
    renderLimiter();

    /* ------------------------------------------------------------------ */
    /* Alerts                                                              */
    /* ------------------------------------------------------------------ */
    const ZONE_CLEAR_M = 25;     // an event clears once you are this far past it
    const CLUSTER_M = 100;       // 3+ events this close together confuse Sentri
    const CLUSTER_MIN = 3;

    // Every alert the telemetry raises right now, before route zones are applied.
    // `sub` may depend on the advisory speed, which is only known once passed hazards are dropped.
    function rawAlerts() {
        const out = [];
        const t = state.tele;
        if (!(state.live && t)) return out;
        if (t.collision || t.sound_active) out.push({ id: 'collision', name: 'accident', sev: 'crit', icon: 'crash', onRoad: true, title: 'Accident ahead', sub: (rec) => `Impact detected. Slow to ${rec} km/h.`, mood: 'accident' });
        if (t.wrong_way) out.push({ id: 'wrong', name: 'wrong-way car', sev: 'crit', icon: 'noentry', onRoad: true, title: 'Wrong-way vehicle', sub: 'Keep left and slow down now.', mood: 'wrong_way' });
        if (t.emergency_vehicle || t.rfid_active) out.push({ id: 'emergency', name: 'ambulance', sev: 'crit', icon: 'siren', onRoad: true, title: 'Ambulance behind', sub: 'Move aside and give way.', mood: 'emergency' });
        if (t.stalled_vehicle) out.push({ id: 'stall', name: 'stalled car', sev: 'warn', icon: 'cone', onRoad: true, title: 'Stalled vehicle', sub: 'Lane blocked ahead. Merge early.', mood: 'stall' });
        if (t.traffic_level === 'CONGESTED') out.push({ id: 'traffic', name: 'traffic jam', sev: 'warn', icon: 'traffic', onRoad: true, title: 'Heavy traffic', sub: `${t.traffic_count} of 4 lanes occupied ahead.`, mood: 'congestion' });
        if (t.road_condition === 'WET') out.push({ id: 'wet', name: 'wet road', sev: 'warn', icon: 'rain', onRoad: true, title: 'Wet road', sub: (rec) => `Grip is low. Hold ${rec} km/h and brake early.`, mood: 'rain' });
        if (t.temperature_c >= 30) out.push({ id: 'heat', name: 'hot road', sev: 'info', icon: 'sun', title: 'Hot road surface', sub: `${Number(t.temperature_c).toFixed(1)} °C. Tyres soften.`, mood: 'heat' });
        return out;
    }

    // Each road event gets a spot on the route. Live events sit at the station; a Test lab event
    // switched on mid-drive appears just ahead of you. 25 m after you pass it, it clears.
    function resetZones() { state.zones.clear(); state.cleared.clear(); }
    function zoneFor(a) {
        if (state.zones.has(a.id)) return state.zones.get(a.id);
        const total = state.route.cum[state.route.cum.length - 1];
        let at = state.stationAt;
        if (demo.active && state.driving && state.travelled > at - 60) at = state.travelled + 180;
        const taken = [...state.zones.values()];
        while (taken.some(x => Math.abs(x - at) < 10)) at += 12;    // spread markers so they do not stack
        at = Math.min(at, total);
        state.zones.set(a.id, at);
        if (state.travelled > at + ZONE_CLEAR_M) state.cleared.add(a.id);   // already behind you
        return at;
    }

    // Advisory speed for what is still ahead (same rules as the firmware)
    const ADVISE_ID = { collision: 'collision', wrong: 'wrong', stall: 'stall', traffic: 'congestion', wet: 'wet', heat: 'heat' };
    function effectiveRec(list) {
        const t = state.tele;
        if (!t) return 0;
        if (!demo.active && !state.cleared.size) return Math.round(t.recommended_speed_kmh || 0);
        return adviseSpeed(new Set(list.map(a => ADVISE_ID[a.id]).filter(Boolean)));
    }

    let passedNow = [];          // ids cleared since the last refresh
    function activeAlerts() {
        const raw = rawAlerts();
        const t = state.tele;
        const ids = new Set(raw.map(a => a.id));
        // an event that stops firing loses its spot, so a new one is placed fresh
        [...state.zones.keys()].forEach(id => { if (!ids.has(id)) { state.zones.delete(id); state.cleared.delete(id); } });
        const list = [];
        raw.forEach(a => {
            if (a.onRoad && state.route) {
                a.at = zoneFor(a);
                if (!state.cleared.has(a.id) && state.travelled > a.at + ZONE_CLEAR_M) { state.cleared.add(a.id); passedNow.push(a.id); }
                if (state.cleared.has(a.id)) return;
                a.ahead = a.at - state.travelled;
            }
            list.push(a);
        });
        if (state.live && t) {
            const rec = effectiveRec(list);
            list.forEach(a => { if (typeof a.sub === 'function') a.sub = a.sub(rec); });
            const spd = Math.round(t.measured_speed_kmh || 0);
            // Live: once you are past the station, a fast reading there is a car closing in behind you
            const stationRec = Math.round(t.recommended_speed_kmh || t.posted_speed_kmh || 80);
            const behindStation = !demo.active && state.driving && state.route &&
                state.travelled > state.stationAt + ZONE_CLEAR_M && state.travelled - state.stationAt <= 300;
            const speederKmh = atDestination() ? 0 : t.speeder_behind_kmh > 0 ? Math.round(t.speeder_behind_kmh) : (behindStation && spd > stationRec + 2 ? spd : 0);
            if (speederKmh) list.push({ id: 'speeder', name: 'speeder behind', sev: 'warn', icon: 'rear', title: 'Speeding car behind', sub: `A car is closing in at ${speederKmh} km/h. Keep left and let it pass.`, mood: 'speeder' });
            if (!behindStation && rec > 0 && spd > rec + 2) list.push({ id: 'speed', name: 'overspeed', sev: 'warn', icon: 'speed', title: `Over the ${rec} km/h advisory`, sub: `You are at ${spd} km/h. Ease off.`, mood: 'slowdown' });
        }
        const rank = { crit: 0, warn: 1, info: 2 };
        return list.sort((a, b) => rank[a.sev] - rank[b.sev]);
    }

    // 3+ road events within 100 m of each other (live events without a route all sit at the station)
    function clusterOf(list) {
        const z = list.filter(a => a.onRoad).sort((a, b) => (a.at ?? 0) - (b.at ?? 0));
        let best = null;
        for (let i = 0; i < z.length; i++) {
            let j = i;
            while (j + 1 < z.length && (z[j + 1].at ?? 0) - (z[i].at ?? 0) <= CLUSTER_M) j++;
            if (j - i + 1 >= CLUSTER_MIN && (!best || j - i + 1 > best.length)) best = z.slice(i, j + 1);
        }
        return best;
    }
    function clusterAlert(c) {
        const names = c.map(a => a.name);
        const said = names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}` : names[0];
        const ahead = Math.min(...c.map(a => a.ahead ?? Infinity));
        return {
            id: 'cluster', sev: c.some(a => a.sev === 'crit') ? 'crit' : 'warn', icon: 'warn', mood: 'confused', ahead: isFinite(ahead) ? ahead : null,
            title: `${c.length} hazards within 100 m`,
            sub: `${said.charAt(0).toUpperCase()}${said.slice(1)}. Slow right down and stay alert.`
        };
    }

    let popMsg = null;           // what the swollen alert bar shows while Sentri peeks out
    function renderAlerts() {
        const list = activeAlerts();
        const cluster = clusterOf(list);
        const top = popMsg || (cluster ? clusterAlert(cluster) : list[0]);
        const strip = $('#alert-strip');
        strip.dataset.sev = top ? top.sev : 'none';
        const far = top && state.driving && top.ahead > 0 ? ` · ${fmtDist(top.ahead)}` : '';
        $('#alert-title').textContent = top ? `${top.title}${far}` : 'No alerts on your route';
        $('#alert-sub').textContent = top ? top.sub : (state.live ? 'Sentri is watching the road' : 'Sensors offline. Link the ESP32 or open the Test lab.');
        const count = $('#alert-count');
        count.hidden = popMsg ? true : list.length < 2;
        count.textContent = list.length;
        count.classList.toggle('is-cluster', Boolean(cluster));
        strip.querySelector('.alert-strip-icon').innerHTML = top ? (ICONS[top.icon] || ICONS.warn) : ICONS.bell;
        const badge = $('#rail-alert-badge');
        badge.hidden = list.length === 0;
        badge.textContent = list.length;
        return list;
    }
    $('#alert-strip').addEventListener('click', () => openSheet('alerts'));

    // Same event logged many times (older server builds wrote one every 0.5 s): show it once with a count
    function groupEvents(events) {
        const out = [];
        const at = new Map();
        events.forEach(e => {
            const k = `${e.title}|${e.description || ''}`;
            if (at.has(k)) out[at.get(k)].n++;
            else { at.set(k, out.length); out.push({ e, n: 1 }); }
        });
        return out;
    }

    async function loadEvents() {
        try { state.events = await api('/events?limit=80'); } catch (_) { /* keep what we have */ }
        state.eventsLoaded = true;
        if (currentSheet === 'alerts') renderSheet('alerts');
    }

    /* ------------------------------------------------------------------ */
    /* Sentri: chat head; on an alert she peeks out of the alert bar       */
    /* ------------------------------------------------------------------ */
    let mini = null, big = null, sheetBot = null;
    let popTimer = null;
    let lastMood = null;
    if (window.Sentri) {
        mini = Sentri.mount($('#sentri-mini'), { mood: 'standby', bubble: false });
        big = Sentri.mount($('#sentri-big'), { mood: 'standby', bubble: false });
    }
    // The alert bar swells into a bubble and Sentri peeks out of its circle, then it shrinks back.
    // `msg` pins what the bar says while it is open; without it the bar shows the top alert.
    function setPop(open, ms, msg) {
        if (open && app.classList.contains('is-popped')) { app.classList.remove('is-popped'); void app.offsetWidth; }  // peek again
        popMsg = open ? (msg || null) : null;
        app.classList.toggle('is-popped', open);
        clearTimeout(popTimer);
        if (open && ms) popTimer = setTimeout(() => setPop(false), ms);
        renderAlerts();
    }
    // What Sentri should feel about the road right now: confused by a cluster, else the top alert
    function moodNow() {
        if (!state.live || !state.tele) return ['standby', null];
        const list = activeAlerts();
        const c = clusterOf(list);
        if (c) return ['confused', clusterAlert(c).sub];
        return list[0] ? [list[0].mood, list[0].sub] : ['clear', null];
    }
    function showSentriFor(alert) {
        if (big && alert.mood) big.setMood(alert.mood, alert.sub);
        setPop(true, 6500, alert);
    }
    function popTop() {
        const [mood, detail] = moodNow();
        if (big) big.setMood(mood, detail);
        setPop(true, mood === 'clear' || mood === 'standby' ? 4000 : 6500);
    }
    $('#sentri-head').addEventListener('click', () => {
        if (activeAlerts().length) popTop();
        else setPop(true, 4500, state.live
            ? { sev: 'good', icon: 'smile', title: 'Road is clear', sub: 'All clear. I am watching the road with you.' }
            : { sev: 'none', icon: 'bell', title: 'Off duty', sub: 'Link the ESP32 or try the Test lab.' });
    });

    function updateSentri() {
        const [mood, detail] = moodNow();
        [mini, big, sheetBot].forEach(s => s && s.request(mood, detail));
        const tone = window.Sentri ? (Sentri.MOODS[mood]?.tone || 'idle') : 'idle';
        $('#sentri-head').dataset.tone = tone;
        if (mood !== lastMood) {
            const rank = { crit: 2, warn: 1 };
            if (settings.autoPop && rank[tone] && lastMood !== null) {
                setPop(true, tone === 'crit' ? 9000 : 6000);
                vibrate(tone === 'crit' ? [140, 70, 140] : 60);
            } else if (!rank[tone] && app.classList.contains('is-popped') && !popMsg) {
                setTimeout(() => { if (!popMsg) setPop(false); }, 2200);
            }
            lastMood = mood;
        }
    }

    // You drove 25 m past a hazard: move on to the next one, or let Sentri calm down
    function onPassed() {
        if (!passedNow.length) return;
        passedNow = [];
        if (activeAlerts().some(a => a.onRoad)) return;   // the next hazard pops up through its mood change
        setPop(true, 3600, { sev: 'good', icon: 'smile', title: 'Hazard passed', sub: 'The road behind you is clear. Back to normal driving.' });
        vibrate(30);
    }

    // The telemetry with the hazards you have already passed switched off
    function viewTele() {
        const t = state.tele;
        if (!t || !state.live || (!state.cleared.size && !demo.active)) return t;
        const gone = state.cleared;
        const v = Object.assign({}, t);
        if (gone.has('collision')) { v.collision = false; v.sound_active = false; }
        if (gone.has('wrong')) v.wrong_way = false;
        if (gone.has('emergency')) { v.emergency_vehicle = false; v.rfid_active = false; }
        if (gone.has('stall')) v.stalled_vehicle = false;
        if (gone.has('traffic')) v.traffic_level = 'LIGHT';
        if (gone.has('wet')) v.road_condition = 'DRY';
        v.recommended_speed_kmh = effectiveRec(activeAlerts());
        return v;
    }

    /* ------------------------------------------------------------------ */
    /* Telemetry: live from the server, or the Test lab                    */
    /* ------------------------------------------------------------------ */
    let lastRouteDraw = 0;
    function refresh(forceDraw) {
        if (demo.active) { state.tele = demoTele(); state.live = true; }
        else { state.tele = state.liveTele; state.live = Boolean(state.liveTele) && !state.liveTele.hardware_standby; }
        activeAlerts();              // moves zones on and notes what you have passed
        state.view = viewTele();
        renderSpeed();
        renderAlerts();
        renderTrip();
        onPassed();
        updateSentri();
        applyMapTheme();
        renderDemoPill();
        // route colours follow the conditions, throttled
        const since = Date.now() - lastRouteDraw;
        if (forceDraw || since > 1200 || (demo.active && since > 350)) { lastRouteDraw = Date.now(); drawRoute(); }
        if (currentSheet === 'sensors' || currentSheet === 'twin') renderSheet(currentSheet);
        if (state.driving) renderBanner();
    }
    function onTelemetry(t) {
        state.liveTele = t;
        if (!demo.active) refresh();
    }

    let ws = null, wsRetry = 0, pollTimer = null;
    function connectWS() {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        try { ws = new WebSocket(`${proto}://${location.host}/ws/telemetry`); } catch (_) { scheduleWS(); return; }
        ws.onopen = () => { wsRetry = 0; setServer(true); clearInterval(pollTimer); pollTimer = null; };
        ws.onmessage = (m) => {
            let msg; try { msg = JSON.parse(m.data); } catch (_) { return; }
            if (msg.telemetry) onTelemetry(msg.telemetry);
            if (msg.event) {
                state.events.unshift(msg.event);
                state.events = state.events.slice(0, 80);
                if (currentSheet === 'alerts') renderSheet('alerts');
            }
        };
        ws.onclose = () => { setServer(false); scheduleWS(); };
        ws.onerror = () => { try { ws.close(); } catch (_) {} };
    }
    function scheduleWS() {
        wsRetry = Math.min(wsRetry + 1, 6);
        setTimeout(connectWS, 800 * wsRetry);
        if (!pollTimer) pollTimer = setInterval(async () => {
            try { onTelemetry(await api('/telemetry/latest')); setServer(true); } catch (_) { setServer(false); }
        }, 2500);
    }
    setInterval(() => { if (ws && ws.readyState === 1) ws.send('ping'); }, 20000);

    function setServer(up) { state.serverUp = up; renderStatus(); }
    async function pollHardware() {
        try { state.hw = await api('/hardware/status'); setServer(true); } catch (_) { state.hw = null; }
        renderStatus();
        if (currentSheet === 'link') renderSheet('link');
    }
    function renderStatus() {
        const hw = state.hw;
        let s = 'down', text = 'SentraX server unreachable';
        if (demo.active) { s = 'partial'; text = 'Test lab conditions active'; }
        else if (state.serverUp) {
            if (hw?.esp32?.connected && hw?.esp8266?.connected) { s = 'live'; text = `Live · ESP32 over ${hw.esp32.transport}, ESP8266 linked`; }
            else if (hw?.esp32?.connected) { s = 'partial'; text = `Live · ESP32 over ${hw.esp32.transport}`; }
            else if (state.live) { s = 'partial'; text = 'Demo data · hardware not linked'; }
            else { s = 'idle'; text = 'Server online · hardware not linked'; }
        }
        $('#drawer-dot').dataset.state = s;
        $('#drawer-status').textContent = text;
        $('#rail-link-dot').dataset.state = hw?.esp32?.connected ? 'live' : (state.serverUp ? 'idle' : 'down');
    }

    /* ------------------------------------------------------------------ */
    /* Test lab (demo conditions)                                          */
    /* ------------------------------------------------------------------ */
    function saveDemo() { store.set('sx-demo', demo); }
    function renderDemoPill() {
        $('#demo-pill').hidden = !demo.active;
        $('#rail-demo-dot').hidden = !demo.active;
        if (!demo.active) return;
        const p = PRESETS.find(x => x.id === demo.preset);
        const names = demo.alerts.map(id => ALERTS.find(a => a.id === id)?.name).filter(Boolean);
        $('#demo-pill-text').textContent = p ? p.name : (names.length ? names.join(' + ') : `Custom · ${demo.speed} km/h`);
    }
    async function mirrorToHardware() {
        if (!demo.hardware) return;
        const map_ = { collision: 'COLLISION', wrong: 'WRONG_WAY', emergency: 'EMERGENCY', stall: 'STALLED', congestion: 'CONGESTION', wet: 'WET_ROAD', heat: 'HIGH_TEMP' };
        try {
            await api('/speed/override', { speed: demo.speed });
            const first = demo.alerts.find(id => map_[id]);
            if (first) await api('/alerts/trigger', { alert: map_[first] });
            else await api('/demo/reset', {});
        } catch (e) { toast(`ESP32: ${e.message}`); }
    }
    function applyDemo(reason) {
        demo.active = true;
        saveDemo();
        refresh(true);
        mirrorToHardware();
        // make Sentri react straight away
        if (activeAlerts().length && reason !== 'slider') popTop();
        else if (reason === 'preset') setPop(true, 3500, { sev: 'good', icon: 'smile', title: 'Road is clear', sub: state.tele.night_mode ? 'Night drive. Lights on, eyes open.' : 'Clear road. Enjoy the drive.' });
    }
    function clearDemo() {
        const wasHw = demo.hardware && demo.active;
        Object.assign(demo, DEMO_DEFAULT, { hardware: demo.hardware });
        saveDemo();
        if (simTimer) stopDriving();
        refresh(true);
        setPop(false);
        if (wasHw) api('/demo/reset', {}).catch(() => {});
        toast('Demo filters cleared. Showing live sensors.');
        if (currentSheet === 'lab') renderSheet('lab');
    }
    $('#demo-pill-open').addEventListener('click', () => openSheet('lab'));
    $('#demo-pill-clear').addEventListener('click', clearDemo);

    /* ------------------------------------------------------------------ */
    /* Aerial digital twin                                                 */
    /* ------------------------------------------------------------------ */
    const HOTSPOTS = [
        { id: 'eink', x: 7, y: 25, tag: 'INK', title: 'E-Ink speed sign (gantry)', pins: 'SPI: CS 16 | DC 17 | RST 21 | BUSY 22', desc: 'Overhead sign showing the live speed limit and warnings to approaching drivers.' },
        { id: 'us1', x: 9, y: 82, tag: 'US1', title: 'Ultrasonic US1 (speed entry)', pins: 'TRIG: GPIO 3 | ECHO: GPIO 34', desc: 'A vehicle passing under US1 starts the speed timer.' },
        { id: 'ir1', x: 14, y: 38, tag: 'IR1', title: 'IR sensor 1 (lane ingress)', pins: 'Digital in: GPIO 25', desc: 'Entrance occupancy. Blocked for 6 s or more raises a stalled-vehicle alert.' },
        { id: 'ir2', x: 33, y: 36, tag: 'IR2', title: 'IR sensor 2 (mid-left)', pins: 'Digital in: GPIO 26', desc: 'Mid-way occupancy. Works with IR1 and IR3 to detect queues.' },
        { id: 'dht', x: 42, y: 35, tag: 'DHT', title: 'DHT11 temperature + humidity', pins: 'Single-wire: GPIO 13', desc: 'Road heat above 30 °C drops the limit to 35 km/h.' },
        { id: 'sound', x: 48, y: 35, tag: 'MIC', title: 'Impact microphone', pins: 'Digital out: GPIO 32 (filtered)', desc: 'Fires only on a sustained loud impact, then raises a collision alert.' },
        { id: 'ir3', x: 54, y: 36, tag: 'IR3', title: 'IR sensor 3 (mid-right)', pins: 'Digital in: GPIO 27', desc: 'Wrong-way check: if IR4 fired in the last 15 s, IR3 raises the alarm.' },
        { id: 'moist', x: 61, y: 33, tag: 'H2O', title: 'Surface moisture sensor', pins: 'Analog in: GPIO 35', desc: 'Low readings mean a wet road: LEDs pulse and the limit drops to 40 km/h.' },
        { id: 'ir4', x: 80, y: 34, tag: 'IR4', title: 'IR sensor 4 (exit / reverse gate)', pins: 'Digital in: GPIO 33', desc: 'Vehicles driving against traffic trip IR4 first, arming the wrong-way window.' },
        { id: 'us2', x: 85, y: 88, tag: 'US2', title: 'Ultrasonic US2 (speed exit)', pins: 'TRIG: GPIO 14 | ECHO: GPIO 36', desc: 'Stops the speed timer across the test corridor.' },
        { id: 'leds', x: 49, y: 58, tag: 'LED', title: 'WS2812B roadway LEDs', pins: 'Data: GPIO 2 (60 pixels)', desc: 'Amber normally, red on collision, flashing at a stalled car, pulsing when wet.' },
        { id: 'esp32', x: 38, y: 88, tag: 'MCU', title: 'ESP32 controller', pins: 'ESP-WROOM-32, dual core 240 MHz', desc: 'Reads every sensor, runs the risk logic and streams telemetry over Bluetooth or USB.' }
    ];
    let twinSel = 'eink';
    function twinInfo(id, t) {
        const live = state.live && t;
        const ir = live ? t.ir_sensors || [] : [];
        const v = (x) => live ? x : '--';
        switch (id) {
            case 'eink': {
                const msg = !live ? 'STANDBY' : t.collision ? 'ACCIDENT AHEAD' : t.wrong_way ? 'WRONG WAY' : t.emergency_vehicle ? 'GIVE WAY' : t.stalled_vehicle ? 'LANE BLOCKED' : t.road_condition === 'WET' ? 'WET ROAD' : t.traffic_level === 'CONGESTED' ? 'CONGESTION' : t.temperature_c >= 30 ? 'HOT ROAD' : 'ROAD CLEAR';
                return { state: !live ? 'off' : t.collision || t.wrong_way ? 'crit' : t.recommended_speed_kmh < 80 || t.emergency_vehicle ? 'warn' : 'ok', rows: [['Sign shows', v(`${Math.round(t.recommended_speed_kmh)} km/h`)], ['Warning', msg]] };
            }
            case 'us1': case 'us2': {
                const on = live && t.ultrasonic_state?.[`${id}_active`];
                return { state: on ? 'warn' : 'ok', rows: [['Beam', live ? (on ? 'Vehicle present' : 'Clear') : '--'], ['Measured speed', v(`${Math.round(t.measured_speed_kmh)} km/h`)]] };
            }
            case 'ir1': case 'ir2': case 'ir3': case 'ir4': {
                const k = Number(id[2]) - 1;
                const occ = Boolean(ir[k]);
                const crit = live && ((t.stalled_vehicle && occ) || (t.wrong_way && (k === 2 || k === 3)));
                return { state: crit ? 'crit' : occ ? 'warn' : 'ok', rows: [['Lane', live ? (occ ? 'Occupied' : 'Clear') : '--'], ['Role', k === 3 ? 'Wrong-way arming gate' : k === 2 ? 'Wrong-way confirm' : 'Occupancy and stall timer']] };
            }
            case 'dht': return { state: live && (t.temperature_c >= 30 || t.humidity_pct >= 80) ? 'warn' : 'ok', rows: [['Temperature', v(`${Number(t.temperature_c).toFixed(1)} °C`)], ['Humidity', v(`${Math.round(t.humidity_pct)} %`)]] };
            case 'sound': return { state: live && (t.collision || t.sound_active) ? 'crit' : 'ok', rows: [['Impact', live ? (t.collision || t.sound_active ? 'Impact detected' : 'Quiet') : '--']] };
            case 'moist': return { state: live && t.road_condition === 'WET' ? 'warn' : 'ok', rows: [['Reading', v(String(t.moisture_raw))], ['Surface', live ? (t.road_condition === 'WET' ? 'Wet' : 'Dry') : '--']] };
            case 'leds': {
                const p = !live ? 'Off' : t.collision ? 'Solid red' : t.wrong_way ? 'Red flashing' : t.stalled_vehicle ? 'Flashing at the stalled car' : t.road_condition === 'WET' ? 'Blue pulse' : t.emergency_vehicle ? 'Emergency sweep' : 'Amber';
                return { state: !live ? 'off' : t.collision || t.wrong_way ? 'crit' : p === 'Amber' ? 'ok' : 'warn', rows: [['Pattern', p]] };
            }
            case 'esp32': {
                const hw = state.hw?.esp32;
                return { state: hw?.connected ? 'ok' : demo.active ? 'warn' : 'off', rows: [['Link', hw?.connected ? hw.transport : demo.active ? 'Test lab (simulated)' : 'Not linked'], ['Risk score', v(`${t.risk_score} / 100`)]] };
            }
        }
        return { state: 'ok', rows: [] };
    }

    /* ------------------------------------------------------------------ */
    /* Drawer                                                              */
    /* ------------------------------------------------------------------ */
    function openDrawer(open) {
        $('#drawer').classList.toggle('is-open', open);
        $('#drawer').setAttribute('aria-hidden', String(!open));
        $('#scrim').hidden = !open && !$('#sheet').classList.contains('is-open');
    }
    $('#btn-menu').addEventListener('click', () => openDrawer(true));
    $('#scrim').addEventListener('click', () => { openDrawer(false); closeSheet(); });

    /* ------------------------------------------------------------------ */
    /* Bottom sheets                                                       */
    /* ------------------------------------------------------------------ */
    let currentSheet = null;
    const TITLES = { sensors: 'Road sensors', camera: 'Camera AI', alerts: 'Alerts', link: 'Hardware link', speed: 'Speed limiter', lab: 'Test lab', twin: 'Aerial digital twin', sentri: 'Sentri', place: 'Choose a place' };

    function openSheet(name, arg) {
        openDrawer(false);
        if (sheetBot && name !== 'sentri') { sheetBot.destroy(); sheetBot = null; }
        stopCamera();
        currentSheet = name;
        $('#sheet-title').textContent = TITLES[name] || '';
        renderSheet(name, arg);
        $('#sheet').classList.add('is-open');
        $('#sheet').setAttribute('aria-hidden', 'false');
        $('#scrim').hidden = false;
        $$('.rail-btn[data-sheet]').forEach(b => b.classList.toggle('is-on', b.dataset.sheet === name));
        if (name === 'alerts') loadEvents();
        if (name === 'link') pollHardware();
    }
    function closeSheet() {
        if (sheetBot) { sheetBot.destroy(); sheetBot = null; }
        stopCamera();
        currentSheet = null;
        $('#sheet').classList.remove('is-open');
        $('#sheet').setAttribute('aria-hidden', 'true');
        $('#scrim').hidden = !$('#drawer').classList.contains('is-open');
        $$('.rail-btn[data-sheet]').forEach(b => b.classList.remove('is-on'));
    }
    $$('[data-sheet]').forEach(b => b.addEventListener('click', () => openSheet(b.dataset.sheet)));
    $('#sheet-close').addEventListener('click', closeSheet);

    (function dragToClose() {
        const sheet = $('#sheet');
        let y0 = null;
        $('#sheet-grip').addEventListener('pointerdown', (e) => { y0 = e.clientY; sheet.style.transition = 'none'; $('#sheet-grip').setPointerCapture(e.pointerId); });
        $('#sheet-grip').addEventListener('pointermove', (e) => { if (y0 !== null) sheet.style.transform = `translateY(${Math.max(0, e.clientY - y0)}px)`; });
        $('#sheet-grip').addEventListener('pointerup', (e) => {
            sheet.style.transition = ''; sheet.style.transform = '';
            if (y0 !== null && e.clientY - y0 > 90) closeSheet();
            y0 = null;
        });
    })();

    const row = (icon, label, value) => `<div class="row"><span class="row-label"><span data-icon="${icon}"></span>${esc(label)}</span><span class="row-value">${value}</span></div>`;
    const sevOf = (e) => ({ CRITICAL: 'crit', WARNING: 'warn' }[e.severity] || 'info');

    /* Camera AI sheet: live annotated feed, then a strip of vehicle snapshots with their speed,
       session totals and detector status. Polled once a second while the sheet is open. */
    let camTimer = null;
    function stopCamera() {
        clearInterval(camTimer); camTimer = null;
        const img = $('#cam-img');
        if (img) img.src = '';  // ends the MJPEG stream; it keeps downloading while the sheet is hidden otherwise
    }
    const CAM_HEADING = { Left: '← left', Right: 'right →', Up: '↑ up', Down: '↓ down' };
    const CAM_STATUS_SEV = { Moving: 'good', Stopped: 'warn', Stalled: 'crit', 'Wrong way': 'crit', Toppled: 'crit' };
    const fmtSecs = (s) => s < 60 ? `${Number(s).toFixed(1)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
    const camModelName = (m) => m.startsWith('yoloe') ? 'YOLOE' : m.replace(/^yolo/i, 'YOLO');

    function camCard(v, limit) {
        const over = v.speed_max > limit;
        const status = v.emergency_type ? 'Emergency' : v.status;
        const sev = v.emergency_type ? 'crit' : (CAM_STATUS_SEV[v.status] || 'good');
        const big = v.in_view ? v.speed_now : v.speed_avg;
        const meta = v.in_view
            ? `${CAM_HEADING[v.heading] ? CAM_HEADING[v.heading] + ' · ' : ''}${fmtSecs(v.seconds_in_view)} in view`
            : `${v.seconds_since_seen < 50 ? 'Just left' : `Left ${ago(Date.now() / 1000 - v.seconds_since_seen)} ago`} · ${fmtSecs(v.seconds_in_view)} in view`;
        return `<div class="cam-card${v.in_view ? '' : ' is-gone'}${v.emergency_type ? ' is-emergency' : ''}" data-label="${esc(v.label)}">
            <div class="cam-snap">${v.snapshot_url ? `<img alt="Snapshot of ${esc(v.label)}" src="${esc(v.snapshot_url)}">` : ''}
                <span class="cam-snap-id">${esc(v.label)}</span>${v.emergency_type ? '<span class="cam-snap-siren" data-icon="siren"></span>' : ''}</div>
            <div class="cam-card-body">
                <div class="cam-speed${over ? ' is-over' : ''}">${Number(big).toFixed(1)}<small>km/h ${v.in_view ? 'now' : 'avg'}</small></div>
                <div class="cam-card-title">${esc(v.type_label || 'Vehicle')}${v.colour ? ` · ${esc(v.colour)}` : ''}</div>
                ${v.emergency_reason ? `<div class="cam-card-reason">${esc(v.emergency_reason)}</div>` : ''}
                <div class="cam-card-meta">Top ${Number(v.speed_max).toFixed(1)} · Avg ${Number(v.speed_avg).toFixed(1)} km/h</div>
                <div class="cam-card-meta">${esc(meta)}</div>
                <div class="cam-card-tags"><span class="tag tag-${sev}">${status}</span>${over ? '<span class="tag tag-warn">Overspeed</span>' : ''}</div>
            </div></div>`;
    }

    // Updates cards in place so snapshots that did not change keep their <img> (no flicker)
    function renderCamCards(vehicles, limit) {
        const strip = $('#cam-cards');
        if (!strip) return;
        if (!vehicles.length) {
            strip.innerHTML = '<div class="empty cam-empty">Hold a car in front of the camera. Its snapshot and speed show up here.</div>';
            return;
        }
        strip.querySelector('.cam-empty')?.remove();
        const keep = new Set();
        vehicles.forEach((v, i) => {
            keep.add(v.label);
            const tmp = document.createElement('div');
            tmp.innerHTML = camCard(v, limit);
            const fresh = tmp.firstElementChild;
            const old = [...strip.children].find(c => c.dataset.label === v.label);
            if (old) {
                const oldImg = old.querySelector('.cam-snap img'), newImg = fresh.querySelector('.cam-snap img');
                if (oldImg && newImg && oldImg.getAttribute('src') === newImg.getAttribute('src')) newImg.replaceWith(oldImg);
                old.replaceWith(fresh);
            } else {
                strip.appendChild(fresh);
            }
            if (strip.children[i] !== fresh) strip.insertBefore(fresh, strip.children[i]);
        });
        [...strip.children].forEach(c => { if (!keep.has(c.dataset.label)) c.remove(); });
        paintIcons(strip);
    }

    async function refreshCamera() {
        let s, log;
        try { [s, log] = await Promise.all([api('/cv/stats'), api('/cv/vehicles')]); } catch (_) { return; }
        if (currentSheet !== 'camera') return;
        const d = s.detector || {};
        const limit = s.speed_limit_kmh ?? 4;
        let det;
        if (d.active === 'YOLO_BYTETRACK') det = `<span class="tag tag-good">${esc((d.models || []).map(camModelName).join(' + ') || 'YOLO')} · ByteTrack</span>${String(d.device || '').startsWith('cuda') ? '<small>GPU</small>' : ''}`;
        else if (d.backend === 'auto' && d.load_error && !d.is_weights_loaded) det = '<span class="tag tag-crit">AI unavailable</span>';
        else if (d.backend === 'auto' && s.camera_connected && !d.is_weights_loaded) det = '<span class="tag tag-warn">Loading AI models...</span>';
        else det = '<span class="tag">Colour &amp; motion</span>';
        $('#cam-stats').innerHTML = `
            ${row('eye', 'Detector', det)}
            ${row('camera', 'Source', s.camera_connected ? `<small>${esc(s.device_name || 'Camera')}</small>` : '<span class="tag">Synthetic scene</span>')}
            ${row('speed', 'Frame rate', `${Number(s.camera_fps || 0).toFixed(0)}<small>fps</small>`)}
            ${row('flag', 'Overspeed above', `${limit}<small>km/h</small>`)}
            ${row('warn', 'Stalled after standing still', `${s.stall_threshold_seconds ?? 3}<small>s</small>`)}`;
        $('#cam-note').hidden = s.camera_connected || d.backend !== 'auto';
        $$('#cam-det button').forEach(b => b.classList.toggle('is-active', b.dataset.det === s.detector_backend));

        const vehicles = log.vehicles || [];
        renderCamCards(vehicles, limit);
        const sm = log.summary || {};
        $('#cam-summary').innerHTML = [
            ['Vehicles seen', sm.vehicles_seen ?? 0, ''],
            ['Average km/h', sm.average_speed_kmh ?? 0, ''],
            ['Top km/h', sm.top_speed_kmh ?? 0, (sm.top_speed_kmh ?? 0) > limit ? 'warn' : ''],
            ['Overspeed', sm.overspeed_count ?? 0, 'warn'],
            ['Stalled', sm.stalled_count ?? 0, 'crit'],
            ['Wrong way', sm.wrong_way_count ?? 0, 'crit'],
            ['Emergency', sm.emergency_count ?? 0, 'crit'],
        ].map(([k, v, sev]) => `<div class="cam-chip${sev && Number(v) ? ' is-' + sev : ''}"><b>${esc(String(v))}</b><span>${k}</span></div>`).join('');
        const em = vehicles.find(v => v.in_view && v.emergency_type);
        const alert = $('#cam-alert');
        alert.hidden = !em;
        if (em) alert.lastElementChild.textContent = `${em.type_label} in view (${em.label}): ${em.emergency_reason || 'recognised visually'}. Give way.`;
        if (sm.reference_length_cm) $('#cam-ruler').textContent = `Speed uses the toy car's real size (${sm.reference_length_cm} cm long) as the ruler, so no calibration is needed.`;
        paintIcons($('#cam-stats'));
        return s;
    }

    function renderSheet(name, arg) {
        const body = $('#sheet-body');
        const t = state.tele;
        const live = state.live && t;

        if (name === 'sensors') {
            const ir = live ? (t.ir_sensors || []) : [];
            const risk = live ? Math.round(t.risk_score || 0) : 0;
            const level = risk >= 60 ? 'crit' : risk >= 30 ? 'warn' : 'good';
            const wet = live && (t.road_condition === 'WET' || t.moisture_raw < 2000);
            body.innerHTML = `
                ${live ? (demo.active ? '<p class="note">Showing Test lab conditions.</p>' : '') : '<p class="note">Sensors are offline. Link the ESP32 under Hardware link, or use the Test lab.</p>'}
                <div class="sec"><div class="sec-title">Lanes at the station</div>
                    <div class="lanes">${[0, 1, 2, 3].map(i => `<div class="lane ${ir[i] ? 'is-on' : ''}"><span class="lane-car"></span><span class="lane-tag">L${i + 1}</span></div>`).join('')}</div>
                    <p class="note" style="margin:8px 0 0">${live ? `${ir.filter(Boolean).length} of 4 lanes occupied · traffic ${esc(String(t.traffic_level).toLowerCase())}` : 'No lane data'}</p>
                </div>
                <div class="sec"><div class="sec-title">Road risk</div>
                    <div class="row" style="border:0;min-height:0"><span class="row-label" style="font-size:22px;font-weight:700;font-family:var(--mono)">${live ? risk : '--'}<small style="font-size:13px;color:var(--chalk-3);margin-left:4px">/ 100</small></span><span class="tag tag-${level}">${level === 'crit' ? 'High' : level === 'warn' ? 'Elevated' : 'Low'}</span></div>
                    <div class="risk" data-level="${level}">${Array.from({ length: 10 }, (_, i) => `<span class="${i < Math.round(risk / 10) ? 'on' : ''}"></span>`).join('')}</div>
                    ${live && t.risk_reasons?.length ? `<ul class="reasons">${t.risk_reasons.slice(0, 4).map(r => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
                </div>
                <div class="sec"><div class="sec-title">Conditions</div><div class="rows">
                    ${row('thermo', 'Temperature', live ? `${Number(t.temperature_c).toFixed(1)}<small>°C</small>` : '--')}
                    ${row('drop', 'Humidity', live ? `${Math.round(t.humidity_pct)}<small>%</small>` : '--')}
                    ${row('drop', 'Road surface', live ? `<span class="tag ${wet ? 'tag-warn' : 'tag-good'}">${wet ? 'Wet' : 'Dry'}</span> <small>${t.moisture_raw}</small>` : '--')}
                    ${row('sun', 'Light', live ? (t.night_mode ? 'Night' : 'Day') : '--')}
                    ${row('mic', 'Impact mic', live ? `<span class="tag ${t.sound_active ? 'tag-crit' : 'tag-good'}">${t.sound_active ? 'Impact' : 'Quiet'}</span>` : '--')}
                    ${row('eye', 'Camera: vehicles in view', live ? `${t.cv_vehicle_count ?? 0}` : '--')}
                </div></div>`;
        }

        else if (name === 'camera') {
            body.innerHTML = `
                <div class="cam-feed"><img id="cam-img" alt="Live camera with detected vehicles outlined" src="/api/cv/stream?t=${Date.now()}"></div>
                <div class="cam-alert" id="cam-alert" role="status" hidden><span data-icon="siren"></span><span></span></div>
                <div class="cam-log">
                    <div class="cam-log-head"><span class="sec-title" style="margin:0">Vehicles caught on camera</span><button class="cam-mini-btn" type="button" id="cam-clear">Clear</button></div>
                    <div class="cam-cards" id="cam-cards"><div class="skel cam-empty"></div></div>
                    <div class="cam-summary" id="cam-summary"></div>
                    <p class="note cam-ruler" id="cam-ruler"></p>
                </div>
                <div class="sec"><div class="rows" id="cam-stats"><div class="skel"></div></div>
                    <p class="note" id="cam-note" hidden>No camera selected, so this is the built-in test scene. The AI only runs on a live camera.</p>
                </div>
                <div class="sec"><div class="sec-title">Detector</div>
                    <div class="seg" id="cam-det">
                        <button type="button" data-det="auto">AI (YOLO)</button>
                        <button type="button" data-det="heuristic">Colour &amp; motion</button>
                    </div>
                    <p class="note" style="margin-top:8px">Two AI models run together: YOLO26 for everyday vehicles, and YOLOE, which also knows toy cars, ambulances and police cars from any side. Flashing red or blue lights also mark a vehicle as an emergency vehicle.</p>
                </div>
                <div class="sec"><div class="sec-title">Camera</div>
                    <div class="cam-src-row"><select class="btn" id="cam-src" aria-label="Camera source"><option value="">Looking for cameras...</option></select>
                    <button class="btn" type="button" id="cam-use"><span data-icon="camera"></span>Use camera</button></div>
                    <div class="err" id="cam-err" hidden></div>
                </div>`;
            const err = $('#cam-err');
            $('#cam-clear').addEventListener('click', async () => {
                try { await api('/cv/vehicles/clear', {}); } catch (e) { toast(e.message); }
                refreshCamera();
            });
            $$('#cam-det button', body).forEach(b => b.addEventListener('click', async () => {
                try { await api('/cv/config', { detector_backend: b.dataset.det }); toast(b.dataset.det === 'auto' ? 'AI detector on' : 'Colour and motion detector on'); }
                catch (e) { toast(e.message); }
                refreshCamera();
            }));
            $('#cam-use').addEventListener('click', async (ev) => {
                const src = $('#cam-src').value;
                if (!src) return;
                const btn = ev.currentTarget; btn.disabled = true; err.hidden = true;
                try {
                    const res = await api('/cv/config', { camera_source: src });
                    if (src !== '-1' && !res.config?.camera_connected) throw new Error('That camera did not open. Close other apps using it and try again.');
                    toast(src === '-1' ? 'Showing the test scene' : 'Camera connected');
                } catch (e) { err.textContent = e.message; err.hidden = false; }
                btn.disabled = false;
                refreshCamera();
            });
            refreshCamera().then(s => api('/cv/devices').then(devs => {
                const sel = $('#cam-src');
                if (!sel) return;
                const opts = [...devs.map(d => [d.source, d.name.replace(/^\[[^\]]+\]\s*/, '')]), ['-1', 'Test scene (no camera)']];
                const cur = s && s.camera_connected ? String(s.camera_source) : '-1';
                sel.innerHTML = opts.map(([v, n]) => `<option value="${esc(v)}" ${v === cur ? 'selected' : ''}>${esc(n)}</option>`).join('');
            })).catch(() => { const sel = $('#cam-src'); if (sel) sel.innerHTML = '<option value="-1">Test scene (no camera)</option>'; });
            camTimer = setInterval(refreshCamera, 1000);
        }

        else if (name === 'alerts') {
            const act = activeAlerts();
            const hist = groupEvents(state.events || []);
            body.innerHTML = `
                <div class="sec"><div class="sec-title">On your route now</div>
                    ${act.length ? `<div class="alist">${act.map(a => `
                        <button class="aitem" type="button" data-sev="${a.sev}" data-alert="${esc(a.id)}" style="text-align:left;width:100%">
                            <span class="aitem-bar"></span><span><div class="aitem-title">${esc(a.title)}</div><div class="aitem-desc">${esc(a.sub)}</div></span><span class="aitem-time">${a.ahead != null && state.driving ? fmtDist(Math.max(0, a.ahead)) : demo.active ? 'demo' : 'live'}</span>
                        </button>`).join('')}</div>`
                    : '<div class="empty">Nothing on your route right now.</div>'}
                </div>
                <div class="sec"><div class="sec-title">Recent events</div>
                    ${!state.eventsLoaded ? '<div class="skel"></div><div class="skel"></div><div class="skel"></div>'
                    : hist.length ? `<div class="alist">${hist.slice(0, 30).map(({ e, n }) => `
                        <div class="aitem" data-sev="${sevOf(e)}"><span class="aitem-bar"></span>
                            <span><div class="aitem-title">${esc(e.title)}${n > 1 ? `<span class="aitem-count">×${n}</span>` : ''}</div><div class="aitem-desc">${esc(e.description || e.source || '')}</div></span>
                            <span class="aitem-time">${ago(e.timestamp)}</span></div>`).join('')}</div>`
                    : '<div class="empty">No events recorded yet.</div>'}
                </div>`;
            $$('[data-alert]', body).forEach(b => b.addEventListener('click', () => {
                const a = act.find(x => x.id === b.dataset.alert);
                closeSheet();
                if (!a) return;
                state.selectedAlert = a.id; drawHazards();
                if (a.onRoad && state.route) map.flyTo(along(state.route, a.at ?? hazardDistance()).p, 17, { duration: 0.6 });
                showSentriFor(a);
            }));
        }

        else if (name === 'lab') {
            const a = new Set(demo.alerts);
            const rec = adviseSpeed(a);
            body.innerHTML = `
                <div class="lab-head">
                    <div><b>Use test conditions</b><span>${demo.active ? 'The map, alerts and Sentri follow these settings.' : 'Off: the app shows live sensor data.'}</span></div>
                    <label class="switch-wrap"><input type="checkbox" id="lab-on" ${demo.active ? 'checked' : ''}><span class="switch"></span></label>
                </div>
                <div class="sec"><div class="sec-title">Presets</div>
                    <div class="presets">${PRESETS.map(p => `<button class="preset ${demo.active && demo.preset === p.id ? 'is-active' : ''}" type="button" data-preset="${p.id}" data-sev="${p.sev || 'warn'}"><span data-icon="${p.icon}"></span><span><b>${esc(p.name)}</b><small>${esc(p.sub)}</small></span></button>`).join('')}</div>
                </div>
                <div class="sec"><div class="sec-title">Driver speed</div>
                    <div class="slider-row"><input type="range" id="lab-speed" min="0" max="140" step="5" value="${demo.speed}" aria-label="Driver speed">
                    <span class="slider-val" id="lab-speed-val">${demo.speed}<small>km/h</small></span></div>
                    <p class="note" id="lab-speed-note" style="margin:6px 0 0">Road advises ${rec} km/h${demo.speed > rec + 2 ? ' · over the limit, Sentri will ask you to slow down' : ''}</p>
                </div>
                <div class="sec"><div class="sec-title">Road alerts</div>
                    <div class="chips">${ALERTS.map(x => `<button class="chip ${a.has(x.id) ? 'is-on' : ''}" type="button" data-alert-toggle="${x.id}" data-sev="${x.sev}"><span data-icon="${x.icon}"></span>${esc(x.name)}</button>`).join('')}</div>
                    <p class="note" style="margin:8px 0 0">Road events sit on the route and clear 25 m after you pass them. Three or more within 100 m confuse Sentri.</p>
                </div>
                ${a.has('speeder') ? `<div class="sec"><div class="sec-title">Speeding car behind you</div>
                    <div class="slider-row"><input type="range" id="lab-speeder" min="60" max="180" step="5" value="${demo.speederSpeed}" aria-label="Speed of the car behind">
                    <span class="slider-val" id="lab-speeder-val">${demo.speederSpeed}<small>km/h</small></span></div>
                </div>` : ''}
                <div class="sec"><div class="sec-title">Environment</div>
                    <div class="slider-row"><input type="range" id="lab-temp" min="10" max="48" step="1" value="${demo.temp}" aria-label="Road temperature">
                    <span class="slider-val" id="lab-temp-val">${demo.temp}<small>°C</small></span></div>
                    <div class="chips" style="margin-top:10px"><button class="chip ${demo.night ? 'is-on' : ''}" type="button" id="lab-night"><span data-icon="moon"></span>Night</button></div>
                    <div class="sec-title" style="margin-top:14px">Lanes occupied (IR sensors)</div>
                    <div class="lane-toggles">${[0, 1, 2, 3].map(i => `<button class="chip ${demo.lanes[i] ? 'is-on' : ''}" type="button" data-lane="${i}">L${i + 1}</button>`).join('')}</div>
                </div>
                <div class="sec"><div class="rows">
                    <label class="row-toggle row"><span>Also send to the ESP32 (sign + LEDs)</span><input type="checkbox" id="lab-hw" ${demo.hardware ? 'checked' : ''}><span class="switch"></span></label>
                </div>
                    <button class="btn" type="button" id="lab-drive" style="width:100%;margin-top:8px"><span data-icon="car"></span>${simTimer ? 'Stop the test drive' : 'Drive this route at the test speed'}</button>
                    <button class="btn" type="button" id="lab-expo" style="width:100%;margin-top:8px"><span data-icon="play"></span>Run the scripted 8-step expo demo</button>
                </div>
                <div class="sticky-actions">
                    <button class="btn btn-danger" type="button" id="lab-clear"><span data-icon="close"></span>Clear filters</button>
                    <button class="btn btn-primary" type="button" id="lab-done">Done</button>
                </div>`;
            const repaint = () => { renderSheet('lab'); paintIcons(body); };
            $('#lab-on').addEventListener('change', (e) => { if (e.target.checked) applyDemo('toggle'); else clearDemo(); repaint(); });
            $$('[data-preset]', body).forEach(b => b.addEventListener('click', () => {
                const p = PRESETS.find(x => x.id === b.dataset.preset);
                Object.assign(demo, { preset: p.id, speed: p.speed, alerts: p.alerts.slice(), temp: p.temp ?? 27, night: Boolean(p.night), lanes: (p.lanes || [0, 0, 0, 0]).slice(), speederSpeed: p.speeder || DEMO_DEFAULT.speederSpeed });
                vibrate(15);
                applyDemo('preset');
                repaint();
            }));
            const sp = $('#lab-speed');
            sp.addEventListener('input', () => {
                demo.speed = Number(sp.value); demo.preset = null;
                $('#lab-speed-val').innerHTML = `${demo.speed}<small>km/h</small>`;
                const r = adviseSpeed(new Set(demo.alerts));
                $('#lab-speed-note').textContent = `Road advises ${r} km/h${demo.speed > r + 2 ? ' · over the limit, Sentri will ask you to slow down' : ''}`;
                applyDemo('slider');
            });
            sp.addEventListener('change', () => { if (activeAlerts().length) popTop(); });
            const sd = $('#lab-speeder');
            if (sd) {
                sd.addEventListener('input', () => { demo.speederSpeed = Number(sd.value); demo.preset = null; $('#lab-speeder-val').innerHTML = `${demo.speederSpeed}<small>km/h</small>`; applyDemo('slider'); });
                sd.addEventListener('change', popTop);
            }
            $$('[data-alert-toggle]', body).forEach(b => b.addEventListener('click', () => {
                const id = b.dataset.alertToggle;
                demo.alerts = demo.alerts.includes(id) ? demo.alerts.filter(x => x !== id) : [...demo.alerts, id];
                demo.preset = null;
                applyDemo('alert');
                repaint();
            }));
            const tp = $('#lab-temp');
            tp.addEventListener('input', () => { demo.temp = Number(tp.value); demo.preset = null; $('#lab-temp-val').innerHTML = `${demo.temp}<small>°C</small>`; applyDemo('slider'); });
            $('#lab-night').addEventListener('click', () => { demo.night = !demo.night; demo.preset = null; applyDemo('toggle'); repaint(); });
            $$('[data-lane]', body).forEach(b => b.addEventListener('click', () => {
                const i = Number(b.dataset.lane); demo.lanes[i] = demo.lanes[i] ? 0 : 1; demo.preset = null; applyDemo('toggle'); repaint();
            }));
            $('#lab-hw').addEventListener('change', (e) => { demo.hardware = e.target.checked; saveDemo(); if (demo.active) mirrorToHardware(); });
            $('#lab-drive').addEventListener('click', () => {
                if (simTimer) { stopDriving(); repaint(); return; }
                if (!demo.active) applyDemo('toggle');
                closeSheet(); if (state.driving) stopDriving(); startDriving();
            });
            $('#lab-expo').addEventListener('click', async () => {
                if (demo.active) clearDemo();
                try { await api('/simulation/start', {}); toast('Expo demo running on the server'); closeSheet(); } catch (e) { toast(e.message); }
            });
            $('#lab-clear').addEventListener('click', () => { clearDemo(); repaint(); });
            $('#lab-done').addEventListener('click', closeSheet);
        }

        else if (name === 'twin') {
            const sel = HOTSPOTS.find(h => h.id === twinSel) || HOTSPOTS[0];
            const info = twinInfo(sel.id, t);
            const eink = twinInfo('eink', t);
            const stateTag = { ok: '<span class="tag tag-good">Normal</span>', warn: '<span class="tag tag-warn">Active</span>', crit: '<span class="tag tag-crit">Alert</span>', off: '<span class="tag">Standby</span>' };
            body.innerHTML = `
                <div class="twin-photo">
                    <img src="/static/images/project_aerial.jpg" alt="SentraX test road from above">
                    ${HOTSPOTS.map(h => { const s = twinInfo(h.id, t).state; return `<button class="hs ${h.id === sel.id ? 'is-selected' : ''}" type="button" data-hs="${h.id}" data-state="${s}" style="left:${h.x}%;top:${h.y}%">${h.tag}</button>`; }).join('')}
                </div>
                <div class="twin-card">
                    <div class="twin-card-head"><div><b>${esc(sel.title)}</b><div class="twin-pins">${esc(sel.pins)}</div></div>${stateTag[info.state] || ''}</div>
                    <div class="rows">${info.rows.map(([k, v]) => `<div class="row"><span class="row-label">${esc(k)}</span><span class="row-value">${esc(v)}</span></div>`).join('')}</div>
                    <p class="note" style="margin:6px 0 0">${esc(sel.desc)}</p>
                </div>
                <div class="sec"><div class="sec-title">E-Ink sign twin</div>
                    <div class="eink"><div class="eink-ring"><div><b>${live ? Math.round(t.recommended_speed_kmh) : '--'}</b><small>km/h</small></div></div>
                    <div class="eink-msg"><b>${esc(eink.rows[1][1])}</b><span>MEASURED ${live ? Math.round(t.measured_speed_kmh) : 0} KM/H · ${demo.active ? 'TEST LAB' : 'LIVE'}</span></div></div>
                </div>`;
            $$('[data-hs]', body).forEach(b => b.addEventListener('click', () => { twinSel = b.dataset.hs; renderSheet('twin'); }));
        }

        else if (name === 'link') {
            const hw = state.hw;
            const e32 = hw?.esp32, e82 = hw?.esp8266;
            body.innerHTML = `
                <div class="sec"><div class="rows">
                    ${row('link', 'ESP32 controller', e32?.connected ? `<span class="tag tag-good">${esc(e32.transport)}</span>` : '<span class="tag">Not linked</span>')}
                    ${e32?.connected ? row('pin', 'Address', `<small>${esc(e32.port_or_address || '')}</small>`) : ''}
                    ${row('link', 'ESP8266 module', e82?.connected ? `<span class="tag tag-good">${esc(e82.transport)}</span>` : '<span class="tag">Not linked</span>')}
                    ${row('monitor', 'SentraX server', state.serverUp ? `<span class="tag tag-good">Online</span>` : '<span class="tag tag-crit">Offline</span>')}
                </div></div>
                <div class="sec"><div class="sec-title">Bluetooth</div>
                    <div class="btn-row">
                        <button class="btn btn-primary" type="button" id="ble-connect"><span data-icon="link"></span>${e32?.connected && e32.transport === 'BLE' ? 'Reconnect' : 'Connect ESP32'}</button>
                        <button class="btn" type="button" id="ble-disconnect">Disconnect</button>
                    </div>
                    <div class="err" id="link-err" hidden></div>
                    <p class="note" style="margin-top:10px">The SentraX PC links to the ESP32. Keep its server window open. The ESP32 accepts one Bluetooth connection at a time.</p>
                </div>
                <div class="sec"><div class="sec-title">USB cable</div>
                    <div class="btn-row"><select class="btn" id="usb-port" style="appearance:none;text-align:left"><option value="">Looking for ports...</option></select>
                    <button class="btn" type="button" id="usb-connect"><span data-icon="cable"></span>Connect</button></div>
                </div>`;
            const err = $('#link-err');
            $('#ble-connect').addEventListener('click', async (ev) => {
                const btn = ev.currentTarget; btn.disabled = true; btn.lastChild.textContent = 'Connecting...'; err.hidden = true;
                try { await api('/ble/connect', {}); toast('ESP32 linked over Bluetooth'); vibrate(30); }
                catch (e) { err.textContent = e.message; err.hidden = false; }
                btn.disabled = false; pollHardware();
            });
            $('#ble-disconnect').addEventListener('click', async () => {
                try { await api('/ble/disconnect', {}); toast('Bluetooth disconnected'); } catch (e) { toast(e.message); }
                pollHardware();
            });
            api('/serial/ports').then(ports => {
                const sel = $('#usb-port');
                if (!sel) return;
                sel.innerHTML = ports.length ? ports.map(p => `<option value="${esc(p.port)}">${esc(p.port)} · ${esc(p.description)}</option>`).join('') : '<option value="">No USB ports found</option>';
            }).catch(() => {});
            $('#usb-connect').addEventListener('click', async () => {
                const port = $('#usb-port').value;
                if (!port) { toast('Plug the ESP32 into the PC first'); return; }
                try { await api('/esp32/connect/serial', { port, baudrate: 115200 }); toast(`ESP32 linked on ${port}`); }
                catch (e) { err.textContent = e.message; err.hidden = false; }
                pollHardware();
            });
        }

        else if (name === 'speed') {
            const rec = live ? Math.round(t.recommended_speed_kmh) : null;
            body.innerHTML = `
                <div class="sec"><div class="rows">
                    ${row('speed', 'Your speed', live ? `${Math.round(t.measured_speed_kmh)}<small>km/h</small>` : '--')}
                    ${row('warn', 'Advisory from the road', rec ? `${rec}<small>km/h</small>` : '--')}
                    ${row('flag', 'Posted limit', live ? `${Math.round(t.posted_speed_kmh || 80)}<small>km/h</small>` : '--')}
                </div></div>
                <div class="sec"><div class="sec-title">Limiter on the ESP32</div>
                    <div class="seg" id="lim-seg">${[20, 30, 40, 50, 60].map(v => `<button type="button" data-v="${v}" class="${v === settings.limit ? 'is-active' : ''}">${v}</button>`).join('')}</div>
                    <label class="row-toggle" style="margin-top:8px"><span>Send limit to the road sign</span><input type="checkbox" id="lim-on" ${$('#limiter-on').checked ? 'checked' : ''}><span class="switch"></span></label>
                    <p class="note">The E-Ink sign and LED strip show this limit. Turning it off returns the sign to 80 km/h.</p>
                </div>
                <div class="sec"><div class="sec-title">Test vehicle speed on the hardware</div>
                    <div class="btn-grid">${[25, 45, 70, 95].map(v => `<button class="btn" type="button" data-test-speed="${v}">${v} km/h</button>`).join('')}</div>
                </div>`;
            $$('#lim-seg button', body).forEach(b => b.addEventListener('click', () => {
                settings.limit = Number(b.dataset.v); store.set('sx-limit', settings.limit);
                $$('#lim-seg button', body).forEach(x => x.classList.toggle('is-active', x === b));
                renderLimiter();
                if ($('#limiter-on').checked) sendLimit(true);
            }));
            $('#lim-on').addEventListener('change', (e) => { $('#limiter-on').checked = e.target.checked; sendLimit(e.target.checked); });
            $$('[data-test-speed]', body).forEach(b => b.addEventListener('click', async () => {
                try { await api('/speed/override', { speed: Number(b.dataset.testSpeed) }); toast(`Test speed ${b.dataset.testSpeed} km/h sent`); } catch (e) { toast(e.message); }
            }));
        }

        else if (name === 'sentri') {
            body.innerHTML = `
                <div class="sentri-stagebox"><div id="sentri-sheet-bot"></div></div>
                <div class="act-row">${[['laugh', 'Giggle'], ['wave', 'Wave'], ['highfive', 'High-five'], ['pet', 'Pet'], ['dizzy', 'Spin'], ['yawn', 'Yawn']].map(([a, l]) => `<button type="button" data-act="${a}">${l}</button>`).join('')}</div>
                <div class="sec"><div class="rows">
                    <label class="row-toggle row"><span>Chirps and sounds</span><input type="checkbox" id="opt-sound" ${big && !big.muted ? 'checked' : ''}><span class="switch"></span></label>
                    <label class="row-toggle row"><span>Read warnings aloud</span><input type="checkbox" id="opt-voice" ${big && big.voice ? 'checked' : ''}><span class="switch"></span></label>
                    <label class="row-toggle row"><span>Pop up on alerts</span><input type="checkbox" id="opt-pop" ${settings.autoPop ? 'checked' : ''}><span class="switch"></span></label>
                    <label class="row-toggle row"><span>Vibrate on alerts</span><input type="checkbox" id="opt-haptic" ${settings.haptics ? 'checked' : ''}><span class="switch"></span></label>
                </div></div>
                <p class="note">Tap her head to make her giggle, stroke it for heart eyes, press and hold for a high-five.</p>`;
            if (window.Sentri) {
                if (sheetBot) sheetBot.destroy();
                sheetBot = Sentri.mount($('#sentri-sheet-bot'), { mood: 'clear', size: 'md' });
                sheetBot.setMood(...moodNow());
            }
            $$('[data-act]', body).forEach(b => b.addEventListener('click', () => sheetBot && sheetBot.act(b.dataset.act, 1800)));
            $('#opt-sound').addEventListener('change', (e) => { [mini, big, sheetBot].forEach(s => s && s.setMuted(!e.target.checked)); });
            $('#opt-voice').addEventListener('change', (e) => { [mini, big, sheetBot].forEach(s => s && s.setVoice(e.target.checked)); if (e.target.checked && sheetBot) sheetBot.say('I will read warnings out loud.'); });
            $('#opt-pop').addEventListener('change', (e) => { settings.autoPop = e.target.checked; store.set('sx-autopop', settings.autoPop); });
            $('#opt-haptic').addEventListener('change', (e) => { settings.haptics = e.target.checked; store.set('sx-haptics', settings.haptics); vibrate(30); });
        }

        else if (name === 'place') {
            const which = arg;
            body.innerHTML = `
                <label class="search"><span data-icon="search"></span><input id="place-q" type="search" placeholder="Search any place, address or landmark" autocomplete="off"></label>
                <div class="places" id="place-list"></div>`;
            const recent = store.get('sx-recent', []);
            const known = [
                { name: 'Your location', sub: 'Use this phone’s GPS', gps: true },
                ...recent,
                { name: 'Woxsen North Roundabout', sub: 'Woxsen University, Sangareddy', lat: 17.6638, lng: 77.9272 },
                { name: 'Woxsen Hostels & Blue Embers', sub: 'Woxsen University, Sangareddy', lat: 17.6596, lng: 77.9248 }
            ].filter((p, i, arr) => arr.findIndex(q => q.name === p.name) === i);
            const list = $('#place-list');
            const paint = (items, extra = '') => {
                list.innerHTML = items.map((p, i) => `<button class="place" type="button" data-i="${i}"><span data-icon="${p.gps ? 'locate' : 'pin'}"></span><span><div class="place-name">${esc(p.name)}</div><div class="place-sub">${esc(p.sub || '')}</div></span></button>`).join('')
                    + `<button class="place" type="button" data-pick="1"><span data-icon="flag"></span><span><div class="place-name">Pick on the map</div><div class="place-sub">Tap anywhere, or long-press the map</div></span></button>` + extra;
                paintIcons(list);
                $$('[data-i]', list).forEach(b => b.addEventListener('click', () => {
                    const p = items[Number(b.dataset.i)];
                    closeSheet();
                    if (p.gps) { locate(which === 'origin'); if (which !== 'origin') toast('Your location set as the map centre'); return; }
                    const rec = [{ name: p.name, sub: p.sub, lat: p.lat, lng: p.lng }, ...store.get('sx-recent', []).filter(q => q.name !== p.name)].slice(0, 4);
                    store.set('sx-recent', rec);
                    setPoint(which, p.lat, p.lng, p.name);
                    map.flyTo([p.lat, p.lng], 14, { duration: 0.6 });
                    setTimeout(() => loadRoute(true), 50);
                }));
                $('[data-pick]', list).addEventListener('click', () => { closeSheet(); setTapMode(which); });
            };
            paint(known);
            let qTimer = null;
            $('#place-q').addEventListener('input', (e) => {
                const q = e.target.value.trim();
                clearTimeout(qTimer);
                if (q.length < 3) { paint(known); return; }
                list.innerHTML = '<div class="skel"></div><div class="skel"></div><div class="skel"></div>';
                qTimer = setTimeout(async () => {
                    try {
                        const c = map.getCenter();
                        // biased towards what is on screen, but searches the whole world
                        const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&limit=7&addressdetails=0&q=${encodeURIComponent(q)}&viewbox=${c.lng - 1},${c.lat + 1},${c.lng + 1},${c.lat - 1}`;
                        const data = await (await fetch(url, { headers: { 'Accept-Language': 'en' } })).json();
                        paint(data.map(d => ({ name: d.name || d.display_name.split(',')[0], sub: d.display_name, lat: Number(d.lat), lng: Number(d.lon) })),
                            data.length ? '' : '<div class="empty">No places found. Try another name, or pick on the map.</div>');
                    } catch (_) {
                        paint(known, '<div class="err">Place search needs internet. Pick on the map instead.</div>');
                    }
                }, 550);
            });
            setTimeout(() => $('#place-q')?.focus({ preventScroll: true }), 350);
        }

        paintIcons(body);
    }

    $('#field-origin').addEventListener('click', () => { openSheet('place', 'origin'); $('#sheet-title').textContent = 'Choose start'; });
    $('#field-dest').addEventListener('click', () => { openSheet('place', 'dest'); $('#sheet-title').textContent = 'Choose destination'; });

    /* ------------------------------------------------------------------ */
    /* Boot                                                                */
    /* ------------------------------------------------------------------ */
    renderTrip();
    refresh();
    loadRoute(true);
    connectWS();
    pollHardware();
    loadEvents();
    setInterval(pollHardware, 5000);
    setInterval(applyMapTheme, 60000);

    window.SentraXDrive = { state, demo, map, openSheet, clearDemo };
})();
