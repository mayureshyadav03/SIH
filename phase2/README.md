POLARIS

Antarctic sea-ice / iceberg trajectory and navigation decision support.

Core pipeline:
  MODIS Acquisition -> Processing -> Detection -> Features
  -> Tracking -> Prediction -> Risk -> Navigation -> ECDIS/Dashboard

Modules
-------
acquisition  : NASA Earthdata / LAADS DAAC retrieval of MODIS Aqua products
processing   : GDAL/Rasterio raster pipeline (crop, reproject, resample, bands)
detection    : OpenCV / AI-ML sea-ice and iceberg detection
features     : spatial, spectral, environmental, temporal feature extraction
tracking     : multi-temporal iceberg association and trajectory building
prediction   : AI/ML time-series trajectory forecasting
risk         : ship-iceberg closest approach and risk classification
navigation   : safer-route recommendation and ECDIS decision-support output
storage      : local processed/feature persistence + offline sync
dashboard    : interactive Antarctic map interface

Usage
-----
1. Install dependencies:
     pip install -r requirements-gdal.txt
     pip install -r requirements.txt
2. Configure environment:
     cp .env.example .env   # add NASA Earthdata credentials
3. Run the pipeline (see scripts/).

Configuration lives in config/; runtime credentials in .env.
