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
Long runtime for this process > 12 hours: Keep tabs on progress by displaying status ticker. Updates every ten seconds.

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

**Output:**

```text
Completed:  344820 / 344820 (100.0%)
Downloaded: 229575
Cached:     0
Missing:    115245
```

Download finished with a runtime > 24 hours (with interruptions). The ledger contains 344,820 valid records, covering 420 sensor IDs across 821 dates. Each sensor-date combination occurs once, with no malformed or duplicate records. Of all requested files, 66.6% were downloaded and 33.4% were recorded as missing.

Further inspection shows that 115,168 missing records returned an HTTP 404 response. These files were not available at the requested archive location. A further 77 requests failed because of a temporary DNS error but were also recorded as `missing`. A subsequent check against the Sensor.Community archive found that 43 of these files are available and should be retrieved separately. For the purposes of this project, the value of this figure compared to the total scale of records collected is perceived as permissible. An [issue](https://github.com/patupar/sofia-lez-counterfactual/issues/1) has been submitted, which at a later stage of this project should be addressed. 

Archive availability is also reduced on several individual dates. The archive contains fewer SDS011 files on 14 and 15 March 2024 than on the surrounding dates. No SDS011 files are available for 16 March 2025, while only one is available for 17 March 2025. Upon inspection, these gaps appear to be archive-level gaps rather than a problem with the local download.

File availability declines over the requested period: 73.8% of sensor-date combinations are available in 2024, 66.3% during January to March 2025 and 57.6% during October 2025 to March 2026. Nevertheless, 220 sensors provide files for at least 60% of the dates in each of these three periods. This suggests that a sufficiently large stable panel may remains available.
