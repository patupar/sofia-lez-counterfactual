# Data directories

The full datasets are kept outside Git. The workflow uses the following structure:

```text
data/
├── raw/
│   ├── filter/             BGR files and Sensor_Location.csv
│   ├── sensor_community/   downloaded daily archive files
│   ├── meteorology/        future weather inputs
│   ├── background/         optional regional PM2.5 background
│   └── policy/             future LEZ and district boundaries
├── interim/
│   ├── sensors/            manifest and unified hourly observations
│   ├── diagnostics/        QC and completeness tables
│   └── predictors/         future processed predictors
└── processed/
    ├── daily_pm25.csv
    ├── model_table.csv
    └── counterfactual_predictions.csv
```

Only the synthetic files under `sample_data/` are committed.
