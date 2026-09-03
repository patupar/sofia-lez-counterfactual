# Research Log: A counterfactual assessment of Sofia's Residential Heating Low Emission Zone

## 1. Prelude
This document records the development of the Sofia residential-heating LEZ counterfactual project in relation 
to its corresponding GeoML seminar project. It documents commands run, outputs obtained, data checks, methodological decisions, problems encountered and resulting amendments to the methodology. It serves as a chronological record 
of the research process. Unless otherwise stated, results recorded here are preliminary. 

## 2. Sensor Extraction

### 2.1 Compute manifest on FILTER data [01.09.2026]

**After running:**

```bash
python scripts/01_build_sensor_manifest.py --config configs/pipeline.yaml
```

**Output:**

```text
Sofia location-sensor pairs: 1024
Plausible continuing pairs: 423
```

**Further relevant information:**

```text
Historical FILTER files: 1,958
Unique candidate sensor IDs: 420
Distinct candidate coordinates: approximately 415
```

Suggests relatively strong initial position to continue pursuing the route of using sensor-community dataset. There are 423 location records with 415 distinct coordinate positions. Further inspection of `sofia_sensor_manifest.csv` suggests that initial historical coverage is encouraging.

- 133 started reporting in 2018;
- 204 started before 2020;
- 343 contain at least 8,760 historical QC-valid hours, equivalent to one full year of hourly data;
- median candidate contains 28,623 raw historical hours;
- median historical QC-pass rate is 96.5%.

**Further considerations:**

Considering 133 started reporting in 2018, and 204 before 2020, methodology could relax the 2018 date to 2020. Theoretically, four years of data should be sufficient for training.

### 2.2 Spatial inspection [01.09.2026]

[**sensor_candidate_distriubtion.pdf**](../outputs/figures/sensor_candidate_distribution.pdf)

### 2.3 Extract Sensor.Community archive data [02.09.2026]

Following section reads the computed `sofia_sensor_manifest.csv`, retains 423 rows marked as `plausible_continuing`, reduce these to the 420 available unique sensor IDs and requests one archive file per sensor and date.

**Note:** this considers the files for the period 01.2024 - 31.03.2026.

**After running:**

```bash
python scripts/02_download_archive.py --config configs/pipeline.yaml
```

**Note:**
Long runtime for this process > 12 hours: Keep tabs on progress by displaying Live ticker. Updates every ten seconds.
```bash
ledger="$HOME/sofia-lez-counterfactual/data/raw/sensor_community/download_ledger.jsonl"

while true; do
    clear

    completed=$(wc -l < "$ledger" | tr -d ' ')
    downloaded=$(grep -c '"status": "downloaded"' "$ledger")
    cached=$(grep -c '"status": "cached"' "$ledger")
    missing=$(grep -c '"status": "missing"' "$ledger")
    percentage=$(awk -v c="$completed" 'BEGIN {printf "%.1f", c / 344820 * 100}')

    date
    echo
    echo "Completed:  $completed / 344820 ($percentage%)"
    echo "Downloaded: $downloaded"
    echo "Cached:     $cached"
    echo "Missing:    $missing"

    sleep 10
done
```

