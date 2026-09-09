# Data directories

The full datasets are kept outside Git. The workflow uses the following structure:

```text
data/
├── raw/
│   ├── filter/             BGR files and Sensor_Location.csv
│   ├── sensor_community/   downloaded daily archive files
│   ├── meteorology/era5/   monthly hourly ERA5 NetCDF chunks and download ledger
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
sensor-day is unavailable or fails daily QC; missing outcomes are not imputed. Generated files in
`data/interim/` and `data/processed/` remain local and can be reproduced from the numbered scripts.

Only the synthetic files under `sample_data/` are committed.
