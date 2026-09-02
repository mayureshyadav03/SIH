# POLARIS — Antarctic Navigation DSS (Tauri 2.0)

A desktop rebuild of the Polaris dashboard using **Tauri 2.0** (Rust backend + HTML/CSS/JS frontend, no framework required).

## Project structure

```
polaris-dashboard/
├── package.json              # npm scripts (dev/build via Tauri CLI)
├── src/                       # frontend (loaded into the webview)
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── src-tauri/                 # Rust backend
    ├── Cargo.toml
    ├── build.rs
    ├── tauri.conf.json
    ├── icons/                 # add your app icons here (see below)
    └── src/
        └── main.rs            # exposes `get_dashboard_snapshot` command
```

## Prerequisites

- [Rust](https://www.rust-lang.org/tools/install) (stable toolchain)
- [Node.js](https://nodejs.org/) 18+
- Tauri 2.0 system dependencies for your OS: see
  https://v2.tauri.app/start/prerequisites/

## Setup

```bash
cd polaris-dashboard
npm install
```

### Add icons

Tauri needs app icons before it will bundle. The fastest way is the Tauri CLI icon generator — point it at any square PNG (≥1024×1024):

```bash
npx tauri icon path/to/your-logo.png
```

This fills `src-tauri/icons/` with all required sizes/formats.

## Run in development

```bash
npm run dev
```

This launches the Tauri window with hot-reloading of `src/`.

## Build a native app

```bash
npm run build
```

Produces a platform-native installer/bundle under `src-tauri/target/release/bundle/`.

## How the data flows

- `src-tauri/src/main.rs` exposes a `get_dashboard_snapshot` **Tauri command** that returns hazard zones, safe zones, KPIs, alerts, and chart data as JSON.
- `src/app.js` calls it via `window.__TAURI__.core.invoke("get_dashboard_snapshot")` and renders:
  - KPI cards (iceberg hazards, safe zones, water temperature, ice coverage)
  - A stylised world map (SVG) plotting hazard/safe zones and the vessel's live position
  - Water temperature profile + temperature-by-depth bars
  - Iceberg hazard / safe navigation zone donut charts
  - Ocean depth analysis bar chart
  - Ship position & planned route panel
  - Recent activity & alerts feed
- If opened directly in a plain browser (no Tauri runtime), `app.js` automatically falls back to bundled mock data so you can preview the UI with just `src/index.html`.

## Wiring in real data

Replace the hard-coded values in `get_dashboard_snapshot()` (`src-tauri/src/main.rs`) with calls to your actual data sources (NASA, NSIDC, USNIC, NOAA, EUMETSAT feeds, AIS/vessel telemetry, etc.), or add new `#[tauri::command]` functions for things like live alert streams, satellite sync status, and route planning, and call them from `app.js` the same way.

## Notes

- The map, charts, and donuts are hand-drawn SVG (no external chart library), so the app has zero runtime frontend dependencies beyond `@tauri-apps/api`.
- Content-Security-Policy in `tauri.conf.json` is locked down to `'self'` — if you add external map tiles or fonts, extend the CSP accordingly.
