// Uses the Tauri v2 JS API if available; falls back to local mock data
// so the dashboard also previews fine in a plain browser.

const hasTauri = !!(window.__TAURI__ && window.__TAURI__.core);

async function fetchSnapshot() {
  if (hasTauri) {
    return await window.__TAURI__.core.invoke("get_dashboard_snapshot");
  }
  // Fallback mock (mirrors src-tauri/src/main.rs) for browser preview
  return {
    system_online: true,
    vessel_name: "RV Explorer",
    position_lat: -72.345,
    position_lng: -38.123,
    utc_time: new Date().toUTCString(),
    total_iceberg_hazards: 24,
    hazard_delta_pct: 12,
    safe_navigation_zones: 6,
    safe_zone_delta_pct: 8,
    water_temp_c: 1.8,
    water_temp_delta_c: -1.2,
    ice_coverage_c: -1.8,
    ice_coverage_delta_c: 0.6,
    hazard_zones: [
      { id: 1, lat: 76, lng: -60, risk: "high", label: "North Atlantic" },
      { id: 2, lat: 78.2, lng: 12.4, risk: "high", label: "Svalbard Approach" },
      { id: 3, lat: -55, lng: -65, risk: "medium", label: "Drake Passage" },
      { id: 4, lat: -63, lng: 170, risk: "medium", label: "Ross Sea Margin" },
      { id: 5, lat: -66.5, lng: 60, risk: "low", label: "Cooperation Sea" },
    ],
    safe_zones: [
      { id: 1, lat: 10, lng: -40, label: "Mid-Atlantic Corridor" },
      { id: 2, lat: -20, lng: -30, label: "South Atlantic Basin" },
      { id: 3, lat: -20, lng: 100, label: "Indian Ocean Lane" },
    ],
    alerts: [
      { id: 1, severity: "high", title: "High Iceberg Activity Detected", detail: "Near Arctic Region", timestamp: "12:34 UTC" },
      { id: 2, severity: "high", title: "Unsafe Zone Identified", detail: "Lat 78.2°N, Long 12.4°W", timestamp: "11:20 UTC" },
      { id: 3, severity: "medium", title: "Water Temperature Drop", detail: "-1.2°C in last 6 hours", timestamp: "09:30 UTC" },
    ],
    high_risk_count: 6,
    medium_risk_count: 10,
    low_risk_count: 8,
    safe_count: 4,
    monitor_count: 2,
    ship_lat: 74.6,
    ship_lng: -18.3,
    ship_speed_knots: 14.2,
    depth_profile: [
      ["0-200 m", 4],
      ["200-1,000 m", 2],
      ["1,000-3,000 m", 1],
      ["3,000+ m", -1],
    ],
    ocean_depth_pct: [
      ["Shallow", 18],
      ["Moderate", 48],
      ["Deep", 28],
      ["Very Deep", 12],
    ],
  };
}

function fmtSigned(n, unit = "") {
  const sign = n >= 0 ? "▲" : "▼";
  return `${sign} ${Math.abs(n).toFixed(1)}${unit} vs last 24h`;
}

function lngLatToXY(lat, lng, w = 1000, h = 500) {
  const x = (lng + 180) * (w / 360);
  const y = (90 - lat) * (h / 180);
  return [x, y];
}

function riskColor(risk) {
  return risk === "high" ? "#e0544c" : risk === "medium" ? "#f0a63c" : "#f5c6b0";
}

function drawWorldMap(snapshot) {
  const svg = document.getElementById("world-map");
  const W = 1000, H = 500;
  let parts = [];

  // simple ocean/landmass suggestion via soft blobs (stylised, not geographically exact)
  parts.push(`<rect width="${W}" height="${H}" fill="url(#oceanGrad)" />`);
  parts.push(`
    <defs>
      <linearGradient id="oceanGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#eaf2fb"/>
        <stop offset="100%" stop-color="#cfe0f7"/>
      </linearGradient>
      <radialGradient id="hazardGlow"><stop offset="0%" stop-color="#e0544c" stop-opacity="0.55"/><stop offset="100%" stop-color="#e0544c" stop-opacity="0"/></radialGradient>
      <radialGradient id="safeGlow"><stop offset="0%" stop-color="#2ea86f" stop-opacity="0.45"/><stop offset="100%" stop-color="#2ea86f" stop-opacity="0"/></radialGradient>
    </defs>
  `);

  // faint continents (rough placeholder silhouettes)
  const continents = [
    "M120,120 Q180,90 260,110 Q320,130 300,190 Q260,230 200,220 Q140,210 120,160 Z", // N America-ish
    "M230,260 Q270,240 300,280 Q310,340 270,380 Q230,360 220,310 Z", // S America-ish
    "M470,120 Q560,90 620,120 Q640,160 590,180 Q520,190 480,160 Z", // Europe-ish
    "M480,190 Q560,190 600,240 Q610,300 560,330 Q500,320 480,260 Z", // Africa-ish
    "M650,120 Q780,100 860,140 Q850,190 760,190 Q680,170 650,140 Z", // Asia-ish
    "M780,340 Q830,330 850,360 Q830,390 790,380 Z" // Australia-ish
  ];
  continents.forEach(d => {
    parts.push(`<path d="${d}" fill="#ffffff" opacity="0.55" />`);
  });

  // graticule
  for (let gx = 0; gx <= W; gx += 100) {
    parts.push(`<line x1="${gx}" y1="0" x2="${gx}" y2="${H}" stroke="#ffffff" stroke-opacity="0.4"/>`);
  }
  for (let gy = 0; gy <= H; gy += 100) {
    parts.push(`<line x1="0" y1="${gy}" x2="${W}" y2="${gy}" stroke="#ffffff" stroke-opacity="0.4"/>`);
  }

  // hazard zones
  snapshot.hazard_zones.forEach(z => {
    const [x, y] = lngLatToXY(z.lat, z.lng, W, H);
    const r = z.risk === "high" ? 34 : z.risk === "medium" ? 26 : 18;
    parts.push(`<circle cx="${x}" cy="${y}" r="${r * 1.8}" fill="url(#hazardGlow)"/>`);
    parts.push(`<circle cx="${x}" cy="${y}" r="${r}" fill="${riskColor(z.risk)}" opacity="0.85"><title>${z.label}</title></circle>`);
  });

  // safe zones
  snapshot.safe_zones.forEach(z => {
    const [x, y] = lngLatToXY(z.lat, z.lng, W, H);
    parts.push(`<circle cx="${x}" cy="${y}" r="40" fill="url(#safeGlow)"/>`);
    parts.push(`<circle cx="${x}" cy="${y}" r="22" fill="#2ea86f" opacity="0.75"><title>${z.label}</title></circle>`);
  });

  // vessel position
  const [sx, sy] = lngLatToXY(snapshot.position_lat, snapshot.position_lng, W, H);
  parts.push(`<circle cx="${sx}" cy="${sy}" r="16" fill="#173e8a"/>`);
  parts.push(`<circle cx="${sx}" cy="${sy}" r="16" fill="none" stroke="#173e8a" stroke-width="2" opacity="0.4"><animate attributeName="r" values="16;28;16" dur="2.4s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.5;0;0.5" dur="2.4s" repeatCount="indefinite"/></circle>`);
  parts.push(`<text x="${sx}" y="${sy + 4}" text-anchor="middle" font-size="14" fill="#fff">⛴</text>`);

  svg.innerHTML = parts.join("");
}

function drawTempChart(snapshot) {
  const svg = document.getElementById("temp-chart");
  const points = [1.5, 0.8, 1.2, 2.2, 1.6, 2.4]; // sample recent trend around water_temp_c
  const W = 260, H = 90, pad = 10;
  const max = Math.max(...points), min = Math.min(...points);
  const stepX = (W - pad * 2) / (points.length - 1);
  const coords = points.map((v, i) => {
    const x = pad + i * stepX;
    const y = H - pad - ((v - min) / (max - min || 1)) * (H - pad * 2);
    return [x, y];
  });
  const path = coords.map((c, i) => (i === 0 ? `M${c[0]},${c[1]}` : `L${c[0]},${c[1]}`)).join(" ");
  const area = `${path} L${coords[coords.length - 1][0]},${H} L${coords[0][0]},${H} Z`;
  const dots = coords.map(c => `<circle cx="${c[0]}" cy="${c[1]}" r="3" fill="#3a7bd5"/>`).join("");
  svg.innerHTML = `
    <defs>
      <linearGradient id="tempFill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#3a7bd5" stop-opacity="0.25"/>
        <stop offset="100%" stop-color="#3a7bd5" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <path d="${area}" fill="url(#tempFill)"/>
    <path d="${path}" fill="none" stroke="#3a7bd5" stroke-width="2"/>
    ${dots}
  `;
}

function drawDepthTempList(snapshot) {
  const list = document.getElementById("depth-temp-list");
  const maxAbs = Math.max(...snapshot.depth_profile.map(([, t]) => Math.abs(t)), 1);
  list.innerHTML = snapshot.depth_profile.map(([band, temp]) => {
    const pct = Math.max(8, (Math.abs(temp) / maxAbs) * 100);
    return `<li><span class="band">${band}</span><span class="bar-track"><span class="bar-fill" style="width:${pct}%"></span></span><span class="val">${temp > 0 ? temp + "°C" : temp + "°C"}</span></li>`;
  }).join("");
}

function drawDonut(elId, segments) {
  const svg = document.getElementById(elId);
  const total = segments.reduce((s, seg) => s + seg.value, 0) || 1;
  const cx = 60, cy = 60, r = 46, stroke = 16;
  const circumference = 2 * Math.PI * r;
  let offset = 0;
  const arcs = segments.map(seg => {
    const frac = seg.value / total;
    const dash = frac * circumference;
    const el = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${seg.color}" stroke-width="${stroke}"
      stroke-dasharray="${dash} ${circumference - dash}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${cx} ${cy})" stroke-linecap="butt"/>`;
    offset += dash;
    return el;
  }).join("");
  svg.innerHTML = `${arcs}<text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="20" font-weight="700" fill="#1c2536">${total}</text>
    <text x="${cx}" y="${cy + 14}" text-anchor="middle" font-size="8.5" fill="#7c8698">Total Zones</text>`;
}

function drawBarChart(snapshot) {
  const svg = document.getElementById("depth-bar");
  const W = 220, H = 130, padBottom = 22, padTop = 10;
  const bw = 34, gap = 20;
  const max = 60;
  const colors = ["#cfe3fb", "#3a7bd5", "#2f6fd6", "#173e8a"];
  let parts = [];
  snapshot.ocean_depth_pct.forEach(([label, pct], i) => {
    const x = 14 + i * (bw + gap);
    const h = ((H - padTop - padBottom) * pct) / max;
    const y = H - padBottom - h;
    parts.push(`<rect x="${x}" y="${y}" width="${bw}" height="${h}" rx="4" fill="${colors[i % colors.length]}"/>`);
    parts.push(`<text x="${x + bw / 2}" y="${H - 6}" text-anchor="middle" font-size="9" fill="#7c8698">${label}</text>`);
  });
  // y gridlines
  [0, 20, 40, 60].forEach(v => {
    const y = H - padBottom - ((H - padTop - padBottom) * v) / max;
    parts.unshift(`<line x1="0" y1="${y}" x2="${W}" y2="${y}" stroke="#eef1f6" stroke-width="1"/>`);
    parts.unshift(`<text x="0" y="${y - 3}" font-size="8" fill="#b7bfcc">${v}%</text>`);
  });
  svg.innerHTML = parts.join("");
}

function drawRouteMap(snapshot) {
  const svg = document.getElementById("route-map");
  svg.innerHTML = `
    <defs>
      <radialGradient id="safeBlob"><stop offset="0%" stop-color="#2ea86f" stop-opacity="0.35"/><stop offset="100%" stop-color="#2ea86f" stop-opacity="0"/></radialGradient>
      <radialGradient id="hazardBlob"><stop offset="0%" stop-color="#e0544c" stop-opacity="0.35"/><stop offset="100%" stop-color="#e0544c" stop-opacity="0"/></radialGradient>
    </defs>
    <rect width="220" height="110" rx="10" fill="#eef4fb"/>
    <ellipse cx="40" cy="35" rx="34" ry="24" fill="url(#safeBlob)"/>
    <ellipse cx="175" cy="35" rx="34" ry="24" fill="url(#hazardBlob)"/>
    <path d="M40,60 Q90,90 130,60 T200,50" fill="none" stroke="#2f6fd6" stroke-width="2" stroke-dasharray="5 5"/>
    <circle cx="40" cy="60" r="5" fill="#173e8a"/>
    <text x="40" y="63" text-anchor="middle" font-size="7" fill="#fff">⛴</text>
    <circle cx="200" cy="50" r="4" fill="#e0544c"/>
  `;
}

async function refresh() {
  const s = await fetchSnapshot();

  document.getElementById("utc-time").textContent = s.utc_time;
  document.getElementById("vessel-name").textContent = s.vessel_name;
  document.getElementById("position-value").textContent =
    `${Math.abs(s.position_lat).toFixed(3)}° ${s.position_lat < 0 ? "S" : "N"}, ${Math.abs(s.position_lng).toFixed(3)}° ${s.position_lng < 0 ? "W" : "E"}`;

  document.getElementById("kpi-hazards").textContent = s.total_iceberg_hazards;
  document.getElementById("kpi-hazards-delta").textContent = fmtSigned(s.hazard_delta_pct, "%");
  document.getElementById("kpi-safe").textContent = s.safe_navigation_zones;
  document.getElementById("kpi-safe-delta").textContent = fmtSigned(s.safe_zone_delta_pct, "%");
  document.getElementById("kpi-temp").textContent = `${s.water_temp_c}°C`;
  document.getElementById("kpi-temp-delta").textContent = fmtSigned(s.water_temp_delta_c, "°C");
  document.getElementById("kpi-ice").textContent = `${s.ice_coverage_c}°C`;
  document.getElementById("kpi-ice-delta").textContent = fmtSigned(s.ice_coverage_delta_c, "°C");

  document.getElementById("high-risk-val").textContent = s.high_risk_count;
  document.getElementById("medium-risk-val").textContent = s.medium_risk_count;
  document.getElementById("low-risk-val").textContent = s.low_risk_count;
  document.getElementById("safe-val").textContent = s.safe_count;
  document.getElementById("monitor-val").textContent = s.monitor_count;

  document.getElementById("ship-pos").textContent =
    `Lat ${s.ship_lat}°N, Long ${Math.abs(s.ship_lng)}°W`;
  document.getElementById("ship-speed").textContent = `${s.ship_speed_knots} knots`;

  document.getElementById("last-updated").textContent = `Last Updated: ${s.utc_time}`;
  document.getElementById("nav-alert-badge").textContent = s.alerts.length;

  const alertList = document.getElementById("alert-list");
  alertList.innerHTML = s.alerts.map(a => `
    <li class="${a.severity}">
      <b>${a.title}</b>
      <span>${a.detail} – ${a.timestamp}</span>
    </li>
  `).join("");

  drawWorldMap(s);
  drawTempChart(s);
  drawDepthTempList(s);
  drawDonut("hazard-donut", [
    { value: s.high_risk_count, color: "#e0544c" },
    { value: s.medium_risk_count, color: "#f0a63c" },
    { value: s.low_risk_count, color: "#f5c6b0" },
  ]);
  drawDonut("safe-donut", [
    { value: s.safe_count, color: "#2ea86f" },
    { value: s.monitor_count, color: "#8fd1ae" },
  ]);
  drawBarChart(s);
  drawRouteMap(s);
}

document.addEventListener("DOMContentLoaded", () => {
  refresh();
  setInterval(refresh, 15000); // periodic refresh, mirrors "Auto Refresh ON"

  document.querySelectorAll(".toggle-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".toggle-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });

  document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", (e) => {
      e.preventDefault();
      document.querySelectorAll(".nav-item").forEach(i => i.classList.remove("active"));
      item.classList.add("active");
      // Additional views (Live Map, Alerts, etc.) can be implemented as
      // separate routes/components as this app grows.
    });
  });

  document.getElementById("sync-btn").addEventListener("click", (e) => {
    const btn = e.currentTarget;
    const original = btn.textContent;
    btn.textContent = "Syncing…";
    btn.disabled = true;
    setTimeout(() => {
      btn.textContent = "Synced ✓";
      document.getElementById("queue-count").textContent = "0 items";
      setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 1500);
    }, 1200);
  });
});
