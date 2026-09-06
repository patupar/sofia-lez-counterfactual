# Am I breathing cleaner air? | Дишам ли по-чист въздух?

## Prelude

This repository holds the codebase for a seminar paper initially conceived for the Institute of Geography, Ruprecht-Karl-University Heidelberg. The goal of this work is to present a reproducible counterfactual study of the recently introduced residential-heating low-emission zone (LEZ) in Sofia, Bulgaria. Later versions will aim to bring this academic work to public use. Ultimately, residents of Sofia should be able to observe on a day-by-day basis whether air quality in their neighbourhood has actually improved as a result of the LEZ intervention.   

## General information: 'Counterfactual Assessment of Sofia's Residential Heating Low Emission Zone'
On the 1 January 2025, Sofia implemented Europe’s first low-emission zone (LEZ) targeting residential heating. The
intervention prohibits the use of solid-fuels in buildings across nine districts, given operational district-heating or gas distribution networks are available. The codebase for the above mentioned study presents an exploratory counterfactual assessment of changes in ambient PM2.5 concentrations following the intervention. To the author’s
knowledge, it is the first such assessment of Sofia’s residential-heating LEZ to use post-intervention
PM2.5 measurements.

Daily PM2.5 observations from BGAir’s community-operated sensor network are used, as at the point writing, Sofia's regulatory monitoring network exhibits spatial coverage to an unsatisfactory extend. A secondary objective that has arisen through this work is exploring whether community-operate sensor networks and volunteered geographic information as a whole, can be leveraged in the study of Sofia's urban environment and potentially inform public decision making.    

Random forest models trained on pre-intervention observations from 2018–2024 predict PM2.5 concentrations during the heating
periods between January 2025 and March 2026, accounting for meteorological and temporal variation.
Model predictions reflect expected PM2.5 concentrations in absence of the LEZ intervention.

## Getting started

The following setup is used on macOS. Python 3.11 or newer is required.

```bash
git clone https://github.com/patupar/sofia-lez-counterfactual.git
cd sofia-lez-counterfactual

python -m venv .venv
source .venv/bin/activate          
python -m pip install -e ".[dev]"
```

Prepare the two historical FILTER inputs:

```text
data/raw/filter/Sensor_Location.csv
data/raw/filter/BGR/SC<location_id>_<sensor_id>.csv
```

The 1,958 BGR files represent location-sensor pairs, not necessarily 1,958 physically
distinct stations. One sensor may have operated at more than one location over time. `location_id`
and `sensor_id` are there retained throughout the workflow.
Review all dates, thresholds, and paths in [`configs/pipeline.yaml`](configs/pipeline.yaml) before the full run.

## How to run

Run the stages separately so every decision can be inspected:

```bash
[...]
```

Or run the complete sequence:

```bash
[...]
```

## Workflow

| Stage | Main output | Purpose |
|---|---|---|
| Sensor manifest | `data/interim/sensors/sofia_sensor_manifest.csv` | Identify sensor-location pairs within Sofia and summarise historical coverage |
| Archive retrieval | `data/raw/sensor_community/` | Store daily Sensor.Community source files |
| Observation preparation | `data/interim/sensors/pm25_hourly_unified.csv` | Combine the two sensor sources and retain hourly QC results |
| Daily aggregation | `data/processed/daily_pm25.csv` | Calculate daily PM₂.₅ and apply daily coverage and upper-bound checks |
| Completeness assessment | `data/interim/diagnostics/completeness_sensor_year.csv` and `completeness_sensor_season.csv` | Measure sensor availability across the required periods |
| Stable-panel selection | `data/interim/diagnostics/stable_panel.csv` | Identify sensor-location pairs meeting the completeness requirement |

The subsequent workflow will:

1. obtain and harmonise meteorological data;
2. construct the daily model table;
3. tune and validate the Random Forest model;
4. train the selected model on pre-LEZ heating periods;
5. predict the post-LEZ no-intervention baseline; and
6. compare observed and predicted PM₂.₅ concentrations.
[...]

## Documentation
The repository contains two complementary records:

- [`docs/seminar_methodology.md`](docs/seminar_methodology.md) describes the technical
  methodology, data-processing rules and relationship between the methodological stages and the
  code;
- [`docs/research_log.md`](docs/research_log.md) records commands, outputs, data checks,
  methodological decisions and problems encountered during the development of the project.

The [`scripts/README.md`](scripts/README.md) lists the numbered workflow stages, while
[`data/README.md`](data/README.md) describes the data-directory structure.

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

- [BGAir/FILTER dataset](https://figshare.com/articles/dataset/_i_Harmonized_Standardized_and_Corrected_Crowd-Sourced_Low-Cost_Sensor_i_PM_sub_2_5_sub_i_Data_f_i_i_rom_i_i_Sensor_community_and_PurpleAir_Networks_i_i_Across_Europe_i_/27195720/1) — historical sensor observations and sensor-location information
- [Sensor.Community archive](https://archive.sensor.community/) — daily SDS011 observations from
  2024 onwards
- [SofiaPlan API](https://sofiaplan.bg/api/) — Sofia Municipality boundary
- [AirBG](https://airbg.info/en/build-a-station/) — information about Sofia’s community-operated
  sensor network

[ToDO: meteorological data sources].

## License

Code is released under the [MIT License](LICENSE). Source-data licences and attribution remain
with their respective providers and must be checked before redistribution.
