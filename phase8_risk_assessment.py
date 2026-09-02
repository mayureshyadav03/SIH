"""
POLARIS - Phase 8: Risk Assessment
===================================

Scope (per POLARIS Project Development Roadmap, Phase 8):
    1. Combine ship position with predicted iceberg trajectory.
    2. Calculate separation / closest approach.
    3. Estimate risk level.
    4. Classify situations as Low, Medium, or High Risk.

Inputs (assumed already produced by earlier phases):
    - Predicted iceberg trajectory (Phase 7 output).
    - Current ship position (from GPS, per SRD Section 3).

This module does NOT implement satellite acquisition, detection, tracking,
trajectory prediction, navigation/route recommendation, alerting, storage,
APIs, or any other phase. It is independent of the Phase-7 implementation
and only consumes its output format.

NOTE ON RISK THRESHOLDS:
The supplied SRD and Roadmap do not define numerical distance thresholds
for Low/Medium/High risk. The threshold values below (RiskThresholds) are
therefore implementation parameters only -- not values derived from the
project requirements documents -- and must be configured/tuned by the
project team.
"""

from dataclasses import dataclass
from math import radians, sin, cos, sqrt, atan2
from typing import List, Optional, Dict, Any


# ---------------------------------------------------------------------------
# Step 5 support: Risk threshold configuration
# ---------------------------------------------------------------------------

@dataclass
class RiskThresholds:
    """
    Configurable distance thresholds (in kilometers) used to classify risk
    based on closest-approach separation between ship and iceberg.

    IMPLEMENTATION PARAMETERS ONLY:
    The supplied SRD / Roadmap do not specify numerical values for these
    thresholds. They are provided here so the system is runnable, and must
    be reviewed/configured by the project/domain team -- they are not
    project requirements.
    """
    high_risk_km: float = 5.0    # separation <= this  -> High Risk
    medium_risk_km: float = 20.0  # separation <= this (and > high) -> Medium Risk
    # separation > medium_risk_km -> Low Risk


# ---------------------------------------------------------------------------
# Step 1: Input validation / combine inputs
# ---------------------------------------------------------------------------

def _validate_position(position: Dict[str, Any], label: str) -> None:
    if not isinstance(position, dict):
        raise ValueError(f"{label} must be a dict with 'latitude' and 'longitude'.")
    for key in ("latitude", "longitude"):
        if key not in position:
            raise ValueError(f"{label} is missing required field '{key}'.")
        value = position[key]
        if not isinstance(value, (int, float)):
            raise ValueError(f"{label} field '{key}' must be numeric.")
    lat, lon = position["latitude"], position["longitude"]
    if not (-90 <= lat <= 90):
        raise ValueError(f"{label} latitude {lat} out of valid range [-90, 90].")
    if not (-180 <= lon <= 180):
        raise ValueError(f"{label} longitude {lon} out of valid range [-180, 180].")


def validate_ship_position(ship_position: Dict[str, Any]) -> None:
    """Validate the current ship position input."""
    _validate_position(ship_position, "ship_position")


def validate_predicted_trajectory(predicted_trajectory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate the predicted iceberg trajectory (Phase 7 output) and return
    only the well-formed records. Malformed/incomplete records are skipped
    rather than raising, so a single bad record does not block risk
    assessment for the rest of the trajectory.
    """
    if not isinstance(predicted_trajectory, list) or len(predicted_trajectory) == 0:
        raise ValueError("predicted_trajectory must be a non-empty list of position records.")

    valid_records = []
    for record in predicted_trajectory:
        try:
            _validate_position(record, "predicted_trajectory record")
            valid_records.append(record)
        except ValueError:
            # Skip invalid/missing trajectory records; do not fail the
            # whole assessment because of one bad point.
            continue

    if not valid_records:
        raise ValueError("predicted_trajectory contained no valid position records.")

    return valid_records


def combine_inputs(
    ship_position: Dict[str, Any],
    predicted_trajectory: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Step 1 - Combine Inputs.

    Validates and packages the current ship position and predicted iceberg
    trajectory so they can be compared position-by-position in Step 2.
    """
    validate_ship_position(ship_position)
    valid_trajectory = validate_predicted_trajectory(predicted_trajectory)

    return {
        "ship_position": {
            "latitude": ship_position["latitude"],
            "longitude": ship_position["longitude"],
        },
        "predicted_trajectory": valid_trajectory,
    }


# ---------------------------------------------------------------------------
# Step 2: Calculate separation
# ---------------------------------------------------------------------------

EARTH_RADIUS_KM = 6371.0088  # mean Earth radius, used for Haversine distance


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance between two lat/lon points, in kilometers,
    using the Haversine formula. This is the geographic separation
    calculation required by Step 2.
    """
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)

    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return EARTH_RADIUS_KM * c


def calculate_separations(
    ship_position: Dict[str, Any],
    predicted_trajectory: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Step 2 - Calculate Separation.

    Computes the geographic separation (km) between the ship position and
    every predicted iceberg position in the trajectory.

    Returns a list of records: {latitude, longitude, timestamp, distance}
    """
    separations = []
    for record in predicted_trajectory:
        distance_km = haversine_distance_km(
            ship_position["latitude"],
            ship_position["longitude"],
            record["latitude"],
            record["longitude"],
        )
        separations.append({
            "latitude": record["latitude"],
            "longitude": record["longitude"],
            "timestamp": record.get("timestamp"),  # optional, per Step 1/3
            "distance": distance_km,
        })
    return separations


# ---------------------------------------------------------------------------
# Step 3: Find closest approach
# ---------------------------------------------------------------------------

def find_closest_approach(separations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Step 3 - Find Closest Approach.

    From all ship-iceberg separation values, identifies the minimum
    separation distance and its corresponding position/timestamp.
    """
    closest = min(separations, key=lambda s: s["distance"])
    return {
        "latitude": closest["latitude"],
        "longitude": closest["longitude"],
        "distance": closest["distance"],
        "timestamp": closest["timestamp"],
    }


# ---------------------------------------------------------------------------
# Step 4 & 5: Estimate and classify risk
# ---------------------------------------------------------------------------

def classify_risk(
    closest_approach_distance_km: float,
    thresholds: Optional[RiskThresholds] = None,
) -> str:
    """
    Steps 4-5 - Estimate Risk Level / Risk Classification.

    Classifies the closest-approach separation into exactly one of:
    "Low Risk", "Medium Risk", "High Risk".

    Threshold values come from `thresholds` (RiskThresholds), which are
    documented implementation parameters -- not project-specified values,
    since the SRD/Roadmap do not define numeric thresholds.
    """
    if thresholds is None:
        thresholds = RiskThresholds()

    if closest_approach_distance_km <= thresholds.high_risk_km:
        return "High Risk"
    elif closest_approach_distance_km <= thresholds.medium_risk_km:
        return "Medium Risk"
    else:
        return "Low Risk"


# ---------------------------------------------------------------------------
# Step 6: Generate risk assessment output
# ---------------------------------------------------------------------------

def generate_risk_assessment_output(
    ship_position: Dict[str, Any],
    closest_approach: Dict[str, Any],
    risk_level: str,
) -> Dict[str, Any]:
    """
    Step 6 - Generate Risk Assessment Output.

    Produces the structured Phase-8 result to be passed to Phase 9.
    """
    return {
        "ship_position": {
            "latitude": ship_position["latitude"],
            "longitude": ship_position["longitude"],
        },
        "closest_approach": {
            "latitude": closest_approach["latitude"],
            "longitude": closest_approach["longitude"],
            "distance": closest_approach["distance"],
            "timestamp": closest_approach["timestamp"],
        },
        "risk_level": risk_level,
    }


# ---------------------------------------------------------------------------
# Phase 8 entry point
# ---------------------------------------------------------------------------

def run_phase8_risk_assessment(
    ship_position: Dict[str, Any],
    predicted_trajectory: List[Dict[str, Any]],
    thresholds: Optional[RiskThresholds] = None,
) -> Dict[str, Any]:
    """
    Runs the complete Phase 8 workflow:

        Combine Inputs
            -> Calculate Separation
            -> Find Closest Approach
            -> Estimate Risk Level
            -> Classify Risk
            -> Generate Risk Assessment Output

    Args:
        ship_position: {"latitude": float, "longitude": float}
        predicted_trajectory: list of
            {"latitude": float, "longitude": float, "timestamp": <optional>}
        thresholds: optional RiskThresholds override (implementation
            parameters; see RiskThresholds docstring).

    Returns:
        Structured risk assessment result, ready to be sent to Phase 9.
    """
    combined = combine_inputs(ship_position, predicted_trajectory)
    separations = calculate_separations(
        combined["ship_position"], combined["predicted_trajectory"]
    )
    closest_approach = find_closest_approach(separations)
    risk_level = classify_risk(closest_approach["distance"], thresholds)

    return generate_risk_assessment_output(
        combined["ship_position"], closest_approach, risk_level
    )


# ---------------------------------------------------------------------------
# Minimal example
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ship_position = {
        "latitude": -65.000,
        "longitude": -60.000,
    }

    predicted_trajectory = [
        {"latitude": -65.010, "longitude": -60.020, "timestamp": "2026-09-02T00:00:00Z"},
        {"latitude": -65.050, "longitude": -60.100, "timestamp": "2026-09-02T01:00:00Z"},
        {"latitude": -65.150, "longitude": -60.300, "timestamp": "2026-09-02T02:00:00Z"},
    ]

    result = run_phase8_risk_assessment(ship_position, predicted_trajectory)

    import json
    print(json.dumps(result, indent=4))
