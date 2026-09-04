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

## 3. Sensor Processing
**03 script output:**

**Overall diagnostics:**

```text
Date range:

2018-01-01 00:00:00 to 2026-03-31 00:00:00

Sensor-location pairs:

423

Daily observations:

Total: 711,242

QC-valid: 622,594

QC-valid share: 87.5%

PM2.5 distribution among valid days:

count    622594.000000

mean         10.647916

std          29.817539

min           0.000000

1%            0.295444

5%            1.501827

50%           6.703333

95%          27.603333

99%          60.215708

max         999.900000

Name: pm2_5, dtype: float64

Missing PM2.5 consistency:

Invalid days: 88648

Invalid days with missing PM2.5: 88648

Valid days with missing PM2.5: 0
```

Outputs suggest a promising baseline for continuing the employment of community sensor-network approach for the methodology. However inspection of diagnostics observe that the 423 sensor-location pairs, did not have continuous observations throughout the entire period. The 711,242 observed sensor-days represent approximately 55.8% of a hypothetical complete panel in which all 423 sensor-location pairs reported every day. The dataset therefore forms an unbalanced temporal panel.

```text
filter: 10,169,730 / 11,357,223 passed (89.5%)

sensor_community: 5,025,906 / 5,122,500 passed (98.1%)
```

Hourly QC produced 11,357,223 FILTER observations and 5,122,500 Sensor.Community observations. Of these, 89.5% and 98.1%, respectively, passed all applicable checks. Various  reasons can be attributed to the difference in passing QC between the two datasets, however, it is most likely attributable to the difference in QC procedure. The lower QC rejection rate in the Sensor.Community dataset does not imply that it is better than the FILTER dataset. 

**FILTER:**

```text
qc_source_code: 1,067,744 failed of 11,357,223 (9.4%)

qc_range: 257 failed of 11,357,223 (0.0%)

qc_spread: 178,232 failed of 11,357,223 (1.6%)

qc_pass: 1,187,493 failed of 11,357,223 (10.5%)
```

**sensor_community:**

```text
qc_range: 590 failed of 5,122,500 (0.0%)

qc_spread: 88,946 failed of 5,122,500 (1.7%)

qc_temporal: 7,750 failed of 5,122,500 (0.2%)

qc_pass: 96,594 failed of 5,122,500 (1.9%)
```

Further inspection of the QC fails supports this. Most FILTER rejections resulted from the quality flags included in the FILTER dataset. When adjusting for this, the QC fail rate difference between both datasets is substantially reduced. FILTER ≈ 1.1% and Sensor.Community ≈ 1.9%, which amounts to a difference of ≈ 0.7 percentage points. Most Sensor.Community rejections occurred because measurements did not cover all three twenty-minute intervals within an hour. Very few observations fall outside the accepted PM₂.₅ range or were identified as temporal spikes.

Extreme values and those close to 1,000 µg/m³ and repeated zero values require further inspection. 

**Extreme value diagnostics:**

Regulatory monitoring and the body of literature on the matter indicate that PM₂.₅ peak episodes in Sofia occur mainly during the winter heating season. They commonly result from domestic solid-fuel heating/traffic emission/unfavourable meteorological conditions e.g. temperature inversion -> lasting several hours to a few days.

Review of  regulatory monitoring data as a baseline is complicated due to its limited spatial coverage. Although nine regulatory stations are located in Sofia, Hipodruma is the only urban station with a validated historical PM₂.₅ record suitable for direct comparison. Kopitoto also measures PM₂.₅, but it is a rural-background station located on Vitosha Mountain at approximately 1,321 m above sea level. It therefore represents regional background conditions rather than typical exposure within the built-up city.

Qualitative observation of the area surrounding Hipodruma can  describe it as a relatively green neighbourhood with low- to mid-rise construction and moderate building density for Sofia. Measurements from this single urban location cannot represent the full range of conditions across the city, particularly neighbourhood-scale hotspots. 

```text
Valid-day distribution by source:

                             count       mean  ...         99%         max

data_source                                  ...                        

filter                    417485.0  10.642712  ...   61.152483  631.773333

sensor_community          204802.0  10.617271  ...   56.112091  999.900000
```

This withstanding, the Hipodruma record confirms provide insights on elevated  PM₂.₅ episodes. Primary validated EEA data for 2018–2024 give a 99th percentile of 75.02 µg/m³ and a maximum daily concentration of 199.77 µg/m³. Fourteen valid days exceeded 100 µg/m³ during this period. For comparison, the 99th percentile at the mountain-background Kopitoto station was only 22.80 µg/m³. The sensor-network percentiles of 56–61 µg/m³ are therefore plausible, and observations above 100 µg/m³ should most likely not be rejected. However, the sparse regulatory coverage makes it difficult to verify whether an extreme observation from an individual community sensor represents a local pollution event or a sensor fault. .

A [bTV report from 8 January 2018](https://btvnovinite.bg/bulgaria/kakav-vazduh-dishat-i-dnes-v-sofija.html) also reported PM₂.₅ concentrations above 100 µg/m³ in Sofia. These values were based on community-network measurements rather than regulatory daily observations and therefore provide contextual evidence rather than independent regulatory verification. The regulatory calculations use primary validated data from the [European Environment Agency Air Quality Download Service](https://www.eea.europa.eu/en/datahub/datahubitem-view/778ef9f5-6293-4846-badd-56a29c70880d).

```text
Extreme-value counts:

equal to 0 µg/m³: 126 (0.0202%)

>= 100 µg/m³: 2,307 (0.3705%)

>= 250 µg/m³: 696 (0.1118%)

>= 500 µg/m³: 487 (0.0782%)

>= 900 µg/m³: 425 (0.0683%)
```

```text
Twenty highest valid daily observations:

      date  location_id  sensor_id      data_source  valid_hours  pm2_5

2024-09-02        14474      25804 sensor_community           24  999.9

2024-09-04        14474      25804 sensor_community           24  999.9

2024-09-06        14474      25804 sensor_community           24  999.9

2024-09-07        14474      25804 sensor_community           24  999.9

2024-09-08        14474      25804 sensor_community           24  999.9

2024-09-12        14474      25804 sensor_community           24  999.9

2024-09-13        14474      25804 sensor_community           24  999.9

2024-09-14        14474      25804 sensor_community           24  999.9

2024-09-15        14474      25804 sensor_community           24  999.9

2024-09-16        14474      25804 sensor_community           24  999.9

2024-09-17        14474      25804 sensor_community           24  999.9

2024-09-18        14474      25804 sensor_community           24  999.9

2024-09-19        14474      25804 sensor_community           24  999.9

2024-09-20        14474      25804 sensor_community           24  999.9

2024-09-21        14474      25804 sensor_community           24  999.9

2024-09-22        14474      25804 sensor_community           24  999.9

2024-09-23        14474      25804 sensor_community           24  999.9

2024-09-25        14474      25804 sensor_community           24  999.9

2024-09-26        14474      25804 sensor_community           24  999.9

2024-09-27        14474      25804 sensor_community           21  999.9
```

Inspection of the results fortunately report a low extreme value count. However, 696 records are equal or above 250µg/m³ which most likely is not plausible for the Sofia context. Furthermore repeated values of exactly 999.9µg/m³ from individual Sensor.Community sensors, including during the summer do not resemble genuine pollution episodes. Instead, corresponding to the upper measurement range of the SDS011 sensor and QC check -> likely indicates sensor saturation or malfunction. These observations should be omitted before moving on. In the context of this project, measurements ≥ 250 µg/m³ will be left out.


