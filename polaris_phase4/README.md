# Phase 4 — Iceberg & Sea-Ice Detection

Part of the **POLARIS** system (AI-Enabled Antarctic Sea Ice & Iceberg Trajectory
and Navigation Decision Support System). This module implements **only Phase 4**
of the project roadmap, as scoped by the SRD and Level-1 DFD process `3.0 Sea Ice
& Iceberg Detection`.

## Scope

Implements the workflow:

```
Processed MODIS Image
  -> Image Enhancement
  -> Noise Reduction
  -> Image Segmentation
  -> Computer-Vision Ice Detection
  -> AI/ML Detection Model
  -> Detection Evaluation
  -> Iceberg/Sea-Ice Regions
  -> Boundary Extraction
  -> Position Extraction
  -> Phase 4 Detection Output
```

**Not included** (out of scope, later phases): feature engineering/fusion,
trajectory prediction, risk assessment, navigation decision logic, dashboards,
databases, or APIs.

## Project Structure

```
Phase-4/
├── detection.py          # Main pipeline: input, position extraction, orchestration, output
├── image_processing.py   # Enhancement, noise reduction, segmentation, boundary extraction (OpenCV/NumPy)
├── ai_detection.py       # AI/ML detection model (KMeans-based) + detection evaluation
├── requirements.txt
└── README.md
```

## Input Contract (from Phase 3)

Phase 4 expects Phase 3 to supply a single-band, cropped/reprojected Antarctic
MODIS image plus its geotransform, wrapped via:

```python
from detection import load_processed_modis_data

processed = load_processed_modis_data(
    image=my_2d_numpy_array,          # single-band processed MODIS image
    geotransform=(origin_x, pixel_width, 0.0, origin_y, 0.0, pixel_height),  # GDAL-style
    timestamp="2024-07-15T10:30:00Z", # optional, passed through only
)
```

No real MODIS data is bundled with this module — Phase 3 is responsible for
producing the processed array from actual NASA Aqua/MODIS observations.

## Installation

```bash
cd Phase-4
pip install -r requirements.txt
```

## Running

The module includes a self-contained demo using **minimal synthetic test
data** (clearly separated from the real pipeline — see
`create_synthetic_test_image()` in `detection.py`), since no real Phase 3
output is bundled here:

```bash
python3 detection.py
```

Example output:

```
PHASE 4 — Iceberg & Sea-Ice Detection
Running on MINIMAL SYNTHETIC TEST DATA (not real MODIS imagery).
Timestamp:            synthetic-test-observation
Regions detected:     2
Model confidence:     0.844
Detected positions (lat, lon):
  Region 1: lat=-65.22427, lon=-59.61573
  Region 2: lat=-65.44357, lon=-59.84000

Phase 4 output summary (ready for Phase 5 Feature Extraction):
{...}
```

## Using with real Phase 3 output

```python
from detection import load_processed_modis_data, run_phase4_pipeline

processed = load_processed_modis_data(image=phase3_array, geotransform=phase3_geotransform)
output = run_phase4_pipeline(processed)

output.detection_mask   # 2D NumPy binary mask of detected ice/iceberg pixels
output.boundaries        # list of (row, col) contour arrays, one per region
output.positions         # list of {"latitude", "longitude", "centroid_row", "centroid_col"}
output.model_confidence  # AI/ML model confidence score
output.evaluation        # detection metrics, only if ground_truth_mask was supplied
output.summary()         # compact dict, ready to hand to Phase 5 Feature Extraction
```

To evaluate detection accuracy against a labeled reference mask:

```python
output = run_phase4_pipeline(processed, ground_truth_mask=my_ground_truth_mask)
print(output.evaluation)  # {'accuracy', 'iou', 'precision', 'recall', 'f1_score'}
```

## Output

Phase 4 produces a `Phase4DetectionOutput` object containing exactly:

- **detected sea-ice/iceberg regions** — binary detection mask
- **iceberg boundaries** — per-region pixel contours
- **iceberg latitude / longitude** — per-region geographic position
- (plus AI/ML model confidence and, if requested, evaluation metrics)

This output is designed to be passed directly into **Phase 5 — Feature
Extraction**, which is not implemented here.
