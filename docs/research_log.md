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
- 343 contain at least 8,760 historical QC-valid hours (manifest-stage FILTER checks), equivalent to one full year of hourly data;
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

### 3.1 Outputs and discussion on preparing sensor observations
**03 script output:** [04.09.2026]

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

Inspection of the results fortunately report a low extreme value count. However, 696 records are equal or above 250µg/m³ which most likely is not plausible for the Sofia context. Furthermore repeated values of exactly 999.9µg/m³ from individual Sensor.Community sensors, including during the summer do not resemble genuine pollution episodes. Instead, corresponding to the upper measurement range of the SDS011 sensor and QC check -> likely indicates sensor saturation or malfunction. These observations should be omitted before moving on. For this project, daily PM₂.₅ means equal to or above 250 µg/m³ will be excluded from the analytical dataset.

**Second run 03** [05.09.2026]
After second run, no sensor-day combines FILTER and Sensor.Community data. All daily means ≥ 250 µg/m³ are removed.  Running with the implemented changes, the number of accepted daily observations declined from 622,594 to 621,884 rather than by the full 822 observations. 

```text
Mixed-source sensor-days: 0
Daily means >=250 before screening: 822
Accepted values >=250: 0
Accepted daily observations: 621,884
```
The 822 observations include all calculated daily means reaching the threshold before final daily QC. Some already failed the 18-hour requirement. The earlier count of 696 referred only to observations classified as valid under the preceding workflow. The values are therefore not directly equivalent.


### 3.2 Output and discussion on sensor completeness 
In-line with the decisions discussed previously, the completeness calculation was subsequently revised so that daily completeness is derived from the final QC output. Therefore, incorporating both the requirement for at least 18 valid hours and the exclusion of daily PM₂.₅ means equal to or above 250 µg/m³. Hourly completeness remains based on the hourly QC output.

**Output scripts/04_check_sensor_completeness** [06.09.2026]
```text
Sensor-year rows: 3,807
Sensor-season rows: 4,653 
```
Across sensor-year combinations, mean daily completeness was 49.0% and median completeness was 58.1%. 
These values include all 423 candidate pairs in every period, including sensors that had not yet started operating or had stopped reporting. Therefore -> describe total availability of the network rather than the reliability of individual sensors while active. 

Coverage appears to have increased between 2018 - 2024, with the main exception being 2019-2020 (heating season). Interestingly, the 2019-2020 heating season contains a network-wide data discontinuity. Whilst, October and November 2019 provide comparable coverage, December 2019 provides only 361 hours records across 183 sensor-location pairs with no daily observations that reach the minimum requirement of 18 valid hours. Furthermore, no observations are available from January to March 2020. 

```text
HOURLY RECORDS AND QC
  month  hourly_records  reporting_pairs  valid_hours  qc_source_code_failed  qc_range_failed  qc_spread_failed
2019-10          131242              193       124978                   4965                0              1798
2019-11          125406              202       115793                   6533                0              4575
2019-12             361              183          160                    200                0                32
2020-01               0                0            0                      0                0                 0
2020-02               0                0            0                      0                0                 0
2020-03               0                0            0                      0                0                 0
```
Due to time constraints that pertain this work, further investigation of this anomaly will not be conducted. Valid observations
from October and November 2019 will be retained. The missing PM₂.₅ observations will not imputed downstream, and the incomplete 
season will not be used as an independent validation period further on in this work. 

Post-intervention coverage is considerably stronger. January–March 2025 period, 259 pairs met the 60% completeness threshold. 
During October 2025–March 2026, 212 pairs met the threshold. Median completeness among reporting pairs was 90.0% and 95.6%, 
respectively. In total, 202 pairs met the threshold during both post-intervention periods. By contrast, the aggregate 
pre-intervention period from 2018 - 2024, median completeness was 48.3%, 

```text
Pairs meeting 50%: 202 / 423
Pairs meeting 60%: 145 / 423
Pairs meeting 70%: 90 / 423
```

The 60% threshold came about as a comprise between temporal completeness and sensor retention. Seeing that still 145/423 
passed the 60% threshold, it will not be relaxed. A sensor-location pair will be included in the stable panel when it 
meets this threshold across both the aggregate pre-intervention period and both post-intervention periods.

From here, final panel selection will be performed by script/05_select_stable_panel.py

**Output script/05_select_stable_panel** [07.09.2026]
```text
Candidate sensor-location pairs: 423
Pairs passing aggregate 2018–2024 completeness: 145
Pairs passing post_2025_jan_mar: 259
Pairs passing post_2025_oct_mar: 212
Pairs passing all criteria: 77
```
Final stable panel contains 77 sensor-location pairs -> corresponds to 18.2% of the original candidates. These pairs 
do not necessarily provide uninterrupted observations throughout the study period. Rather, each pair meets three separate 
completeness criteria: at least 60% across the pooled pre-intervention period from 2018 to 2024, at least 60% during 
January–March 2025, and at least 60% during October 2025–March 2026. As model training will be restricted to the heating 
months, their pre-intervention heating-month coverage was also inspected. Mean completeness was 72.4% and median 
completeness was 69.5%. Of the 77 pairs, 71 met the 60% threshold and all met at least 50%, corresponding to a minimum 
of 655 valid sensor-days -> decision: existing panel will therefore be retained.

Before model construction their spatial distribution will assessed, to inform, if necessary changes in the methodology 
and/or interpretation later on. 

[**Spatial distribution of stable panel sensors**](outputs/figures/stable_panel_sensors.pdf) 

Most sensor-location pairs are concentrated in the central, western and southern districts, with observations 
located both within and outside the nine districts covered by the residential-heating LEZ. The northern and
outer parts of the municipality remain sparsely represented. The panel therefore captures different parts of Sofia's
urban area, but cannot be considered spatially representative of the municipality as a whole. Within the districts
covered by the LEZ, the retained sensor-location pairs are also unevenly distributed. They appear more concentrated 
in the southwestern and southern districts, while the northern LEZ districts contain fewer locations.

Although the observed distribution, at least one sensor-location pair exist per LEZ district. No changes to sensor 
pre-processing will be taken. Remains however important to take note of in later interpretation, in combination 
with further validation and spatial diagnostics. 

## 4. Meteorological Data Extraction and Processing

### 4.1 ERA5 retrieval and predictor preparation

**Output scripts/06_download_era5 and 07_prepare_predictors** [07. - 09.09.2026]

ERA5 hourly single-level data was downloaded in 101 monthly chunks covering the required period and its temporal 
buffer. Monthly requests were used to satisfy the maximum monthly range -> CDS request limit. All requested chunks 
were downloaded, validated and retained locally.

```text
ERA5 chunks: 101
Stable sensor-location pairs: 77
Daily predictor rows: 231,924
Date range: 2018-01-01 to 2026-03-31
Duplicate sensor-days: 0
Missing meteorological values: 0
```

Each of the 77 stable sensor-location pairs are assigned to its nearest ERA5 grid cell. In total, the sensors
were represented by five 0.25° grid cells. The meteorological variables therefore describe broader conditions 
across Sofia rather than neighbourhood-scale differences. The spatial mismatch this brings about for some of 
the LEZ administrative districts should be considered in later interpretation of the results.   

Hourly observations are aggregated to Sofia local calendar days. All dates contain the expected 23, 24 or 25 
observations, including the daylight-saving transitions. The resulting predictor dataset forms a complete 
panel of 3,012 days for each sensor-location pair.

The 112,728 missing values in `heating_season` are expected: the variable is defined only for the 
October–March heating period, leaving dates between April and September unassigned. No missing values 
are observed among the meteorological predictors. The dataset can therefore be taken forward for construction 
of the model table.

### 4.2 Random Forest workflow design [09.09.2026]

Model training and validation only use QC-valid observations from the pre-LEZ heating
months. Validation will use later blocked heating periods rather than a random split of individual
sensor-days, as neighbouring dates in a random split are expected to provide an optimistic result.
The Random Forest (RF) will be tuned according to MAE and additionally evaluated using RMSE, R² and
mean error. Three complete heating seasons between October 2021 and March 2024 will be used as
expanding validation blocks. 2019-2020 heating season due to the previously described data discontinuity
(see section 3.2).  All available earlier heating-month observations, beginning in 2018,
remain part of the corresponding training blocks.

October–December 2024 will be retained as a recent pre-LEZ test period. It will be assessed only
after parameter selection and will therefore not receive the same tuning weight as a complete
six-month heating season. This was decided as the heating period 2024/2025 ends on 31.12.2024 with the
succeeding period January-March 2025 already belonging to the post-LEZ period. This early-winter range
should not influence hyperparameter selection. It only test model performance on the most recent
pre-LEZ observations. 

A sensor-specific historical mean will provide a simple benchmark. After validation and testing, the final
model will be fitted to all accepted pre-LEZ heating-month observations, including autumn 2024. Post-LEZ PM₂.₅ 
observations will not be used for tuning or fitting and remain reserved for comparison against the no-LEZ predictions.

### 5.1 Model table 

**Output `scripts/08_build_model_table.py`** [09.09.2026]

The resulting model table contains 231,924 rows, corresponding to 77 stable sensor-location pairs across 3,012 days. 
PM₂.₅ observations passed quality control for 182,328 rows, or 78.6% of the complete predictor panel. The 
remaining 21.4% reflect missing or rejected sensor observations, while the corresponding meteorological records are retained.

Restricting the data to QC-valid observations during the pre-LEZ heating months from 2018 to 2024 leaves 71,152 observations 
for model training. This corresponds to 72.4% of the 98,252 theoretically possible sensor-days within the training period.

**Output `scripts/09_validate_random_forest.py`** [run 1: 09.09.2026]
The Random Forest was tuned using 16 parameter combinations across three blocked validation folds, resulting in 48 model fits. 
The selected configuration used 200 trees, a maximum tree depth of 10, one minimum observation per leaf and the square root of 
the available features at each split.
Across the combined validation folds, the Random Forest achieved an MAE of 8.10 µg/m³, compared with 9.23 µg/m³ for the historical
sensor-mean benchmark. This corresponds to an improvement of approximately 12.3%. The Random Forest achieved a lower MAE in each 
validation fold, with no consistent deterioration across the three periods.
However, both approaches produced negative R² values and systematically overpredicted PM₂.₅. The Random Forest had a mean error 
of +6.00 µg/m³ across validation. During the separate October–December 2024 test period, it performed worse than the benchmark: 
its MAE was 7.80 µg/m³, compared with 7.39 µg/m³ for the benchmark. Its mean error also increased to +6.47 µg/m³.
The validation therefore shows that the Random Forest improves average performance across the earlier folds but does not generalise 
reliably to the most recent pre-intervention period. Final model training is postponed until the temporal bias and the difference 
between validation and test performance have been examined.

**Changes in modelling approach** [10.09.2026]

The first model run automatically selected the parameter combination with the lowest mean validation MAE. However, the selected 
depth-10 Random Forest had a training MAE of 5.22 µg/m³ and a validation MAE of 8.11 µg/m³, resulting in a difference of 2.89 µg/m³. 
A simpler depth-5 model achieved an only slightly higher validation MAE of 8.18 µg/m³, while showing a considerably smaller 
difference between training and validation error.

| Model                              | Training MAE (µg/m³) | Validation MAE (µg/m³) | Train–validation difference (µg/m³) |
| ---------------------------------- | -------------------: | ---------------------: | ----------------------------------: |
| Random Forest, depth 10            |                 5.22 |                   8.11 |                                2.89 |
| Random Forest, depth 5             |         Not reported |                   8.18 |               Smaller than depth 10 |
| Difference between validation MAEs |                    — |                 ≈ 0.08 |                                   — |

The difference of 0.07 µg/m³ between both validation results is small compared with the variation across folds. Selecting the 
model only according to its numerical rank could therefore favour a more strongly overfitted configuration.

The modelling workflow was adjusted so that Stage 9 no longer selects a model automatically. Instead, all 54 configured Random 
Forest parameter combinations are evaluated across the three blocked validation folds, resulting in 162 model fits. For each 
candidate, the output records training and validation MAE, validation RMSE and R², variation between folds, fitting time and 
the difference between training and validation error. Candidates whose validation MAE falls within one standard error of the 
lowest result are also identified. This allows model performance and model complexity to be considered together.

After inspecting these results, one candidate must be selected explicitly in Stage 9b by providing its rank and a brief reason 
for the decision (acting as a selection gate). The selection is linked to the corresponding Stage 9 run, preventing an older 
selection from being used if the parameter search is repeated. The selected candidate is then compared with the historical 
sensor-mean benchmark and evaluated by validation fold, month, heating-season part and sensor-location pair. Predictor 
distributions are also compared between training and evaluation periods to identify possible temporal shifts in the meteorological 
conditions.

Only after the candidate has been recorded is it evaluated on the October–December 2024 holdout period. As this period was already 
inspected during the first model run, it can no longer be treated as a completely untouched final test. It will instead be used as 
a recent robustness check and should not be used to change the selected model. An optional Gradient Boosting comparison is also added 
(whether it will be used, compared with the RF and discussed in the report will be determined by remaining time left for the project). 
It represents a separate tree-based ensemble approach and uses the same predictors and blocked validation folds. 

**Output `scripts/09_validate_random_forest.py`** [run 2: 10.09.2026]

```text
Pre-LEZ training rows available: 71152
Blocked validation folds: 3
Parameter sets tested: 54
Lowest cross-validation MAE: 7.972 ug/m3
Candidates within one standard error: 30
Candidate diagnostics: /Users/ptupar/sofia-lez-counterfactual/data/interim/model/rf_tuning_results.csv
No candidate from this search has been selected.
The recent holdout has not been evaluated; any earlier selection is now stale.
```

The second Random Forest validation run evaluated 54 parameter combinations across three temporally blocked validation folds, 
resulting in 162 model fits. The lowest mean validation MAE was 7.97 µg/m³, and 30 candidates fell within one standard error of this result.

The numerically highest-ranked model used unrestricted tree depth. Although it achieved the lowest validation MAE, its training MAE was 1.59 µg/m³ 
compared with 7.97 µg/m³ during validation. The resulting difference of 6.38 µg/m³ indicates substantial overfitting.

Candidate 14 provided a more balanced result. It used 200 trees, a maximum depth of 5, the square root of the available predictors at each split 
and at least five observations per leaf. Its training MAE was 7.66 µg/m³ and its validation MAE was 8.18 µg/m³, producing a difference 
of 0.52 µg/m³. It also achieved a lower validation RMSE and a less negative R² than the highest-ranked candidate. Candidate 14 is therefore 
preferred because it gives up little average accuracy while showing greater stability and considerably less overfitting. 
The recent October–December 2024 holdout was not evaluated during this run.

| Measure                    | Candidate 1 | Candidate 14 |
| -------------------------- | ----------: | -----------: |
| Validation MAE             |        7.97 |         8.18 |
| Training MAE               |        1.59 |         7.66 |
| Training–validation gap    |        6.38 |         0.52 |
| Validation RMSE            |       11.63 |        10.74 |
| Validation R²              |       −0.27 |        −0.10 |
| Fold-to-fold MAE variation |        0.56 |         0.46 |







