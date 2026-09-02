// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use chrono::Utc;
use serde::Serialize;

#[derive(Serialize, Clone)]
struct HazardZone {
    id: u32,
    lat: f64,
    lng: f64,
    risk: String, // high | medium | low
    label: String,
}

#[derive(Serialize, Clone)]
struct SafeZone {
    id: u32,
    lat: f64,
    lng: f64,
    label: String,
}

#[derive(Serialize, Clone)]
struct AlertItem {
    id: u32,
    severity: String, // high | medium | low
    title: String,
    detail: String,
    timestamp: String,
}

#[derive(Serialize, Clone)]
struct DashboardSnapshot {
    system_online: bool,
    vessel_name: String,
    position_lat: f64,
    position_lng: f64,
    utc_time: String,
    total_iceberg_hazards: u32,
    hazard_delta_pct: f64,
    safe_navigation_zones: u32,
    safe_zone_delta_pct: f64,
    water_temp_c: f64,
    water_temp_delta_c: f64,
    ice_coverage_c: f64,
    ice_coverage_delta_c: f64,
    hazard_zones: Vec<HazardZone>,
    safe_zones: Vec<SafeZone>,
    alerts: Vec<AlertItem>,
    high_risk_count: u32,
    medium_risk_count: u32,
    low_risk_count: u32,
    safe_count: u32,
    monitor_count: u32,
    ship_lat: f64,
    ship_lng: f64,
    ship_speed_knots: f64,
    depth_profile: Vec<(String, f64)>, // depth band -> temperature C
    ocean_depth_pct: Vec<(String, f64)>, // band -> percentage
}

#[tauri::command]
fn get_dashboard_snapshot() -> DashboardSnapshot {
    DashboardSnapshot {
        system_online: true,
        vessel_name: "RV Explorer".into(),
        position_lat: -72.345,
        position_lng: -38.123,
        utc_time: Utc::now().format("%d %b %Y, %H:%M:%S").to_string(),
        total_iceberg_hazards: 24,
        hazard_delta_pct: 12.0,
        safe_navigation_zones: 6,
        safe_zone_delta_pct: 8.0,
        water_temp_c: 1.8,
        water_temp_delta_c: -1.2,
        ice_coverage_c: -1.8,
        ice_coverage_delta_c: 0.6,
        hazard_zones: vec![
            HazardZone { id: 1, lat: 76.0, lng: -60.0, risk: "high".into(), label: "North Atlantic".into() },
            HazardZone { id: 2, lat: 78.2, lng: 12.4, risk: "high".into(), label: "Svalbard Approach".into() },
            HazardZone { id: 3, lat: -55.0, lng: -65.0, risk: "medium".into(), label: "Drake Passage".into() },
            HazardZone { id: 4, lat: -63.0, lng: 170.0, risk: "medium".into(), label: "Ross Sea Margin".into() },
            HazardZone { id: 5, lat: -66.5, lng: 60.0, risk: "low".into(), label: "Cooperation Sea".into() },
        ],
        safe_zones: vec![
            SafeZone { id: 1, lat: 10.0, lng: -40.0, label: "Mid-Atlantic Corridor".into() },
            SafeZone { id: 2, lat: -20.0, lng: -30.0, label: "South Atlantic Basin".into() },
            SafeZone { id: 3, lat: -20.0, lng: 100.0, label: "Indian Ocean Lane".into() },
        ],
        alerts: vec![
            AlertItem { id: 1, severity: "high".into(), title: "High Iceberg Activity Detected".into(), detail: "Near Arctic Region".into(), timestamp: "12:34 UTC".into() },
            AlertItem { id: 2, severity: "high".into(), title: "Unsafe Zone Identified".into(), detail: "Lat 78.2°N, Long 12.4°W".into(), timestamp: "11:20 UTC".into() },
            AlertItem { id: 3, severity: "medium".into(), title: "Water Temperature Drop".into(), detail: "-1.2°C in last 6 hours".into(), timestamp: "09:30 UTC".into() },
        ],
        high_risk_count: 6,
        medium_risk_count: 10,
        low_risk_count: 8,
        safe_count: 4,
        monitor_count: 2,
        ship_lat: 74.6,
        ship_lng: -18.3,
        ship_speed_knots: 14.2,
        depth_profile: vec![
            ("0-200 m".into(), 4.0),
            ("200-1,000 m".into(), 2.0),
            ("1,000-3,000 m".into(), 1.0),
            ("3,000+ m".into(), -1.0),
        ],
        ocean_depth_pct: vec![
            ("Shallow".into(), 18.0),
            ("Moderate".into(), 48.0),
            ("Deep".into(), 28.0),
            ("Very Deep".into(), 12.0),
        ],
    }
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![get_dashboard_snapshot])
        .run(tauri::generate_context!())
        .expect("error while running Polaris Antarctic Navigation DSS");
}
