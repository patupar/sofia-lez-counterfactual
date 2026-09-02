# Sofia LEZ seminar MVP workflow

## Implemented data stage

The current code prepares one hourly PM2.5 record from two sources:

1. FILTER BGR files from 2018 through 2023;
2. Sensor.Community archive files from 2024 through 31 March 2026.

The source transition is defined at 1 January 2024 UTC because both source archives are stored
in UTC. Analytical dates and the final 31 March 2026 cutoff are evaluated in Sofia local time.

Both sources use the same response variable: raw PM2.5. FILTER's empty corrected columns are not
used. The exact `(location_id, sensor_id)` pair is preserved to avoid treating relocated sensors
as one fixed station.

The QC methods remain explicit because the later archive cannot reproduce every FILTER step:

- FILTER: configured `raw_qc` prefix, `spread == 3`, and PM2.5 range;
- archive: PM2.5 range, three twenty-minute bins, and rolling-MAD temporal check.

The unified table records `data_source`, `source_qc_code`, `qc_method`, each QC flag, and the
final `qc_pass`. This allows source-specific sensitivity checks later.

## Planned modelling stage

The seminar MVP will use eligible heating-period sensor-days before 1 January 2025 to validate
and train a Random Forest. The fitted model will predict expected no-LEZ PM2.5 for:

- 1 January–31 March 2025;
- 1 October 2025–31 March 2026.

The main result will be `observed_pm2_5 - expected_no_lez_pm2_5`. Predictor preparation,
time-aware validation, model fitting, prediction and result summaries are intentionally not
implemented until the sensor completeness table has been reviewed.
