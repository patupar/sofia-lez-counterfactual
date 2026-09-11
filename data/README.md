# Data directories

The full datasets are kept outside Git. The workflow uses the following structure:

```text
data/
├── raw/
│   ├── filter/             BGR files and Sensor_Location.csv
│   ├── sensor_community/   downloaded daily archive files
│   ├── meteorology/era5/   monthly hourly ERA5 NetCDF chunks and download ledger
│   ├── lcz/                supplied clipped Global LCZ GeoTIFF
│   ├── background/         optional regional PM2.5 background
│   └── policy/             future LEZ and district boundaries
├── interim/
│   ├── sensors/            manifest and unified hourly observations
│   ├── diagnostics/        QC and completeness tables
│   ├── predictors/         daily meteorological, temporal and spatial predictors
│   └── model/              validation predictions, tuning results and selected parameters
└── processed/
    ├── daily_pm25.csv
    ├── model_table.csv
    └── counterfactual_predictions.csv
```

The model table keeps the complete stable-pair predictor panel. PM₂.₅ remains missing when a
sensor-day is unavailable or fails daily QC; missing outcomes are not imputed. Stage 9 writes the
complete RF candidate table but no selected model. Stage 9b writes the audited selection, detailed
validation and recent-holdout predictions, and only then permits final training. The optional
Gradient Boosting table is kept separately and does not replace the RF automatically. Generated
files in `data/interim/` and `data/processed/` remain local and can be reproduced from the numbered
scripts.

Only the synthetic files under `sample_data/` are committed.

## Local Climate Zones

The supplied filtered Global LCZ version 3 raster belongs at
`data/raw/lcz/lcz_sofia_clipped.tif`. Stage 7b calculates class proportions from valid pixel
centres inside a 500 m circular buffer around each stable sensor-location pair. All 17 original
class fractions and the dominant class are retained in the interim LCZ table for checking. The
model uses five pre-defined groups:

| Model predictor | Original LCZ classes |
|---|---|
| `lcz_compact_built_fraction` | 1–3 |
| `lcz_open_built_fraction` | 4–6 |
| `lcz_other_built_fraction` | 7–10 |
| `lcz_vegetation_fraction` | 11–14 |
| `lcz_bare_water_fraction` | 15–17 |

These five fractions must lie between zero and one and sum to one for every pair. LCZ is static,
so its values are calculated once per sensor-location pair and then repeated only when Stage 8
joins them to the daily model table.
