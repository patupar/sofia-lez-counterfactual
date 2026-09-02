# Am I breathing cleaner air? | Дишам ли по-чист въздух?

## Prelude

This repository holds the codebase for a seminar paper initially conceived for the Institute of Geography, Ruprecht-Karl-University Heidelberg. Goal of the work is to present a reproducible counterfactual study of Sofia, Bulgaria 
recently introduced residential heating low emission zone (LEZ). Later versions will aim to bring this academic work to public use. Ultimately, residents of Sofia should be able to observe on a day-by-day basis whether the air quality in their neighbourhood has actually improved as a result of the LEZ intervention.   

## General information: 'Counterfactual Assessment of Sofia's Residential Heating Low Emission Zone'
On the 1 January 2025, Sofia implemented Europe’s first low-emission zone (LEZ) targeting residential heating. The
intervention prohibits the use of solid-fuels in buildings across nine districts, given operational district-
heating or gas distribution networks are available. The codebase for the above mentioned study presents an exploratory counterfactual assessment of changes in ambient PM2.5 concentrations following the intervention. To the author’s
knowledge, it is the first such assessment of Sofia’s residential-heating LEZ to use post-intervention
PM2.5 measurements.

Daily PM2.5 observations from BGAir’s community-operated sensor network, as at the point writing, Sofia's regulatory monitoring network exhibits an unsatisfactory level of spatial coverage. A secondary objective of this work is to observe whether community-operate sensor networks and volunteered geographic information as a whole, can be leveraged in the study of Sofia's urban environment and potentially inform public decision making.    

Random forest models trained on pre-intervention observations from 2018–2024 predict PM2.5 concentrations during the heating
periods between January 2025 and March 2026, accounting for meteorological and temporal variation.
Model predictions reflect expected PM2.5 concentrations in absence of the LEZ intervention.

## Getting started

Requirements: Python 3.11 or newer.

```bash
git clone https://github.com/patupar/sofia-lez-counterfactual.git
cd sofia-lez-counterfactual
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

Prepare the two historical FILTER inputs:

```text
data/raw/filter/Sensor_Location.csv
data/raw/filter/BGR/SC<location_id>_<sensor_id>.csv
```

The 1,958 BGR files represent **location-sensor pairs**, not necessarily 1,958 physically
distinct stations: a sensor can appear at more than one location over time. The exact pair is
therefore retained throughout. Review all dates, thresholds, and paths in
[`configs/pipeline.yaml`](configs/pipeline.yaml) before the full run.

## How to run

Run the stages separately so every decision can be inspected:

```bash
# 1–2: municipality manifest plus historical first/last observations
sofia-lez --config configs/pipeline.yaml manifest

# 3: 2024-01-01 through 2026-03-31 for plausible continuations
sofia-lez --config configs/pipeline.yaml download

# 4a: reconstruct and consistently QC hourly archive P2 (PM2.5)
sofia-lez --config configs/pipeline.yaml qc-hourly

# 4b: sensor-year and sensor-season/phase completeness
sofia-lez --config configs/pipeline.yaml completeness

# 5: select pairs meeting the threshold in every configured pre/post period
sofia-lez --config configs/pipeline.yaml select-panel

# 6: aggregate passing local hours to daily PM2.5
sofia-lez --config configs/pipeline.yaml aggregate-daily
```

Or run the complete sequence:

```bash
sofia-lez --config configs/pipeline.yaml run
```

Downloads are resumable. If the archive is already cached, use `run --skip-download`.
Each command prints a small machine-readable JSON summary and writes a CSV output. Use
`sofia-lez --help` or `sofia-lez COMMAND --help` for command help.

## Data workflow

```text
src/sofia_lez/
├── manifest.py       municipality filtering and historical coverage
├── downloader.py     resumable daily archive retrieval
├── qc.py             exact-pair extraction, hourly reconstruction, QC
├── completeness.py   sensor-year/season metrics and stable panel
├── daily.py          post-QC daily aggregation
└── cli.py            stage commands and complete runner
```

| Stage | Main output | Purpose |
|---|---|---|
| Manifest | `data/interim/sofia_sensor_manifest.csv` | Sofia polygon membership, coordinates, pair coverage, continuation flag |
| Download | `data/raw/sensor_community/` | Immutable daily source cache |
| Hourly QC | `data/interim/pm25_hourly_qc.csv` | Embedded hourly raw PM2.5 and transparent QC flags |
| Completeness | `data/processed/completeness_sensor_*.csv` | Expected, observed, and valid hours/days by pair and period |
| Panel | `data/processed/stable_panel.csv` | Threshold decision for every candidate pair |
| Daily | `data/processed/pm25_daily.csv` | Local-date PM2.5 after hourly QC and daily coverage check |

The default municipality geometry is derived from SofiaPlan. The downloader tries
both known Sensor.Community layouts (year-nested and root date folders) and both `.csv` and
`.csv.gz` files.

## Documentation

The full methodology, QC definitions, data contracts, limitations, and reproducibility notes
are in [`docs/methodology.md`](docs/methodology.md). The central caveat is important:
Sensor.Community's 2024+ archive provides raw `P2`, not FILTER's model-based
`corrected_pm2_5`. This code therefore never substitutes `spread` or a QC code for a corrected
concentration and never labels raw values as corrected.

## Sample data and tests

`sample_data/` contains a tiny synthetic polygon, location table, historical pair files, and
one Sensor.Community-style archive file. It is intentionally small and exists only to test the
software contract:

```bash
make sample
make test
make lint
```

Continuous integration repeats linting, unit tests, and the sample end-to-end workflow on every
push and pull request.

## Data sources

- [SofiaPlan API](https://sofiaplan.bg/api/) — official Sofia municipality boundary
- [Sensor.Community archive](https://archive.sensor.community/) — daily SDS011 observations
- [AirBG station information](https://airbg.info/en/build-a-station/) — Bulgarian community
  network and SDS011 context
- Historical BGR FILTER exports and `Sensor_Location.csv` — supplied separately; not committed

## License

Code is released under the [MIT License](LICENSE). Source-data licenses and attribution remain
with their respective providers; verify them before redistribution.
