"""
POLARIS - Phase 3: Satellite Data Processing

Turns a locally-stored, already-validated MODIS Aqua raster into a clean,
cropped, correctly-referenced processed dataset (D2 - Processed Data Storage).

Scope is strictly limited to Phase 3 of the POLARIS roadmap:
    Validated MODIS Aqua Dataset -> Read -> Validate -> Crop (Antarctica)
    -> Reproject (if required) -> Resample (if required) -> Extract bands
    -> Extract metadata -> NumPy processing -> Save to D2.

No downloading, detection, tracking, prediction, risk, navigation or UI
code lives here - those belong to other phases.
"""

from .pipeline import run_phase3_pipeline

__all__ = ["run_phase3_pipeline"]
