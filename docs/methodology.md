# Methodology and reproducibility guide

## 1. Scope

The pipeline constructs the outcome panel needed for a counterfactual analysis of Sofia's
residential-heating LEZ. Its temporal scope is 1 January 2024 through 31 March 2026, inclusive.
It does not fit the final counterfactual model: it establishes the sensor identities,
coordinates, availability diagnostics, hourly QC decisions, and daily PM2.5 outcome on which
that model can safely depend.

All settings with methodological consequences are in `configs/pipeline.yaml`. Paths are
resolved relative to the repository, whereas absolute paths are also accepted. A full run can
therefore be reproduced with a frozen configuration plus the separately acquired raw inputs.

## 2. Identity and spatial study area

FILTER filenames have the form `SC<location_id>_<sensor_id>.csv`. They are interpreted as
location-sensor pairs, rather than unique physical stations. This matters because the same
sensor can move; joining on sensor ID alone can attach observations to the wrong coordinates.
The archive extractor consequently retains a row only when both its numeric `sensor_id` and
numeric `location` match a historical pair.

`manifest` downloads the official Sofia municipality GeoJSON (unless already cached), reads
`Sensor_Location.csv`, and applies a point-in-polygon test in WGS84 longitude/latitude. A
polygon filter is used instead of the municipality bounding rectangle because the rectangle
also contains locations outside the administrative study area. Each surviving BGR pair is
then scanned for:

- first and last observed UTC hour;
- number of historical hours;
- first and last historically QC-eligible hour; and
- number of historically QC-eligible hours.

Historical QC eligibility is defined by the configured `raw_qc` prefix (`1233` by default),
`spread == 3`, and non-missing `raw_pm2_5`. The prefix preserves the first four FILTER-stage
decisions while not pretending that a fifth code digit is universally equivalent across
files. No `corrected_pm2_5` is inferred when that field is empty.

## 3. Plausible continuing sensors and acquisition

A pair is marked `plausible_continuing` when its last historical observation is on or after
`manifest.continuing_after` (default 1 October 2023). This is deliberately permissive. Its only
role is to avoid requesting 821 daily files for every discontinued historical sensor. It does
not guarantee post-2023 availability and does not decide the final panel.

The downloader creates one job for every unique candidate sensor and project date. A daily
Sensor.Community file can contain more than one location for a sensor, so the unmodified source
file is cached once by sensor and day; exact-pair filtering happens later. For compatibility
with archive changes, four URL variants are attempted:

1. root date folder, plain CSV;
2. root date folder, gzipped CSV;
3. year/date folder, plain CSV; and
4. year/date folder, gzipped CSV.

Existing non-empty files are skipped. Transfers use a temporary `.part` file and are renamed
only after successful completion. Every attempt is appended to `download_ledger.jsonl`, making
missing dates and resumptions auditable. A 404 is recorded as missing rather than converted to
a zero concentration.

## 4. Hourly reconstruction and QC

For SDS011 files, Sensor.Community `P2` is read as raw PM2.5 in µg/m³. `P1` is not used. UTC
timestamps are parsed first, then converted to `Europe/Sofia` for local reporting. Within each
UTC hour, the observations are assigned to three bins (minutes 0–19, 20–39, 40–59). The hourly
value is the arithmetic mean of numeric `P2`; `spread` is the number of represented bins.

The same explicit archive QC is applied to every 2024–March 2026 hour:

1. **Physical/configured range:** the hourly mean must lie between `pm25_min` and `pm25_max`
   (defaults 0 and 1000 µg/m³).
2. **Within-hour coverage:** all three twenty-minute bins must be represented by default.
3. **Temporal spike screen:** within each location-sensor series, a centered rolling median and
   rolling median absolute deviation (MAD) are calculated. An observation passes when its
   absolute residual is no larger than the maximum of an absolute floor and the configured
   scaled-MAD threshold. Hours without enough local history to calculate the screen are not
   failed merely for being near a series endpoint.

Every component is retained as `qc_range`, `qc_spread`, and `qc_temporal`; `qc_pass` is their
logical conjunction. Thus alternative thresholds can be rerun and compared. The output also
retains raw observation count and coordinates.

This is a transparent project QC for the later raw archive, **not a claim of bit-for-bit FILTER
replication**. FILTER's spatial checks and correction model are not present in the archive. A
primary analysis should use this consistent archive QC and treat any comparison to historical
FILTER-corrected products as a sensitivity analysis rather than merge the two measurement
definitions without qualification.

## 5. Completeness and panel selection

Expected hours are generated in Sofia local time, so daylight-saving transitions are counted
correctly. For each exact pair the pipeline reports observed hours, passing hours, passing
fraction, expected local days, and days meeting the daily-hour minimum.

Two tables are produced:

- **sensor-year:** 2024, 2025, and the partial project year ending 31 March 2026;
- **sensor-season:** conventional October–March heating seasons plus explicitly configured
  intervention-aligned panel periods.

The default panel periods avoid hiding the intervention boundary inside a single winter:

| Role | Period |
|---|---|
| Pre | January–March 2024 |
| Pre | October–December 2024 |
| Post | January–March 2025 |
| Post | October–December 2025 |
| Post | January–March 2026 |

`select-panel` requires at least the configured valid-hour fraction (default 60%) in **every**
panel period. It writes all candidates and a Boolean `stable_panel`, rather than deleting failed
pairs. This makes attrition inspectable and permits threshold sensitivity analysis. The final
counterfactual design can additionally restrict dates, use balanced subpanels, or weight by
availability, but those choices should be made after examining these diagnostics.

## 6. Daily aggregation

Only hours with `qc_pass == True` contribute to the local sensor-day mean. A default minimum of
18 valid hours is required. The row is still retained when this threshold is missed, but its
`pm2_5` is set to missing and `daily_qc_pass` is false. Missingness is never filled with zero.
Coordinates and both sensor and location IDs remain attached, so the table can be converted to
a spatial layer with WGS84 (`EPSG:4326`) or projected later to a suitable metric CRS.

## 7. Outputs and provenance

| File | Unit of observation |
|---|---|
| `sofia_sensor_manifest.csv` | historical location-sensor pair |
| `pm25_hourly_qc.csv` | location-sensor-hour |
| `completeness_sensor_year.csv` | location-sensor-year |
| `completeness_sensor_season.csv` | location-sensor-period |
| `stable_panel.csv` | candidate location-sensor pair |
| `pm25_daily.csv` | location-sensor-local date |

Raw archive files are immutable inputs, interim files expose transformation decisions, and
processed files are analysis-ready outputs. Git ignores every full-data directory. The
synthetic `sample_data/` fixtures exercise the same data contracts without redistributing the
real observations.

For a frozen analysis, record the Git commit SHA, configuration file, Python environment, raw
input checksums, and download ledger. Run `pytest` before producing the final panel. The GitHub
Actions workflow independently repeats linting, unit tests, and the sample end-to-end run.

## 8. Known limitations

- Sensors installed only after the historical FILTER inventory cannot enter this continuity
  cohort. That is appropriate for a stable pre/post panel but should be stated as a design
  restriction.
- Community sensors are not regulatory monitors; humidity, placement, maintenance, and local
  sources can affect readings.
- Coordinate constancy is inherited from `Sensor_Location.csv` for each location ID. Suspected
  moves should be represented as a new location pair or excluded.
- The default temporal QC parameters are defensible starting values, not universal truth. Report
  robustness to the completeness, valid-hours, and spike thresholds.
- Weather, official monitors, intervention geometry, treatment intensity, and counterfactual
  covariates are separate project inputs and are not fabricated by this data-preparation stage.
