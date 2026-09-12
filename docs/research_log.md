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

## 5. Random Forest workflow design 

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

### 5.1 Model table and initial validation

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

Candidate 14, run 2 shows an improvement over the strongest scoring depth-10 and depth-5 models from run across every metric. Nevertheless R² < 0 implies the current RF model underperforms a naive mean baseline. 
This work was initially was conceived as meteorological normalised counterfactual assessment of PM₂.₅. Train the relationship between PM₂.₅ and meteorology in the pre LEZ-intervention period to predict the concentrations for the relevant heating period post LEZ-intervention. However, using solely meteorological (at least the relatively easily accessible ERA5 dataset) and the QC-filtered 77 stations for training has lead to an unexpected issue. ERA5 data is at this scale coarse. The 77 sensor-location pairs are assigned to only five unique ERA 5 grid cells. 

| ERA5 latitude | ERA5 longitude | Sensors assigned |
| ------------: | -------------: | ---------------: |
|         42.75 |          23.25 |               59 |
|         42.75 |          23.50 |               11 |
|         42.50 |          23.25 |                4 |
|         42.50 |          23.50 |                2 |
|         42.75 |          23.00 |                1 |
|     **Total** |                |           **77** |

Over 70% of which are assigned to only one of them, leaving the model little to differentiate on and could in part plausibly explain the low scoring validation R². This considered, the decision was made to include to further predictor datasets. 

As such, a local climate zone dataset (LCZ) data will consequently be introduced as an additional spatial predictor. LCZ classes describe differences in urban form and land cover that can influence ventilation, pollutant dispersion and the spatial distribution of PM₂.₅. Existing literature supports evaluating LCZ variables for explaining urban PM₂.₅ patterns (https://doi.org/10.1016/j.scitotenv.2023.161677; https://doi.org/10.1016/j.scs.2026.107314)

Integrating a dataset for households using solid fuels for heating in Sofia was considered. However the data stems from Bulgaria's 2011 census and was therefore considered not recent enough. Future related work could employ this dataset if more recent record is published. This dataset will however not be used for the project at this stage.  

### 5.2 Updated Random Forest workflow design with LCZ
To accommodate for LCZ, the Random Forest workflow design is adjusted in the following manner:
- New Stage 7b calculates LCZ composition within a 500 m circular buffer around each of the 77 stable sensor-location pairs. A buffer is applied instead of the single corresponding raster pixel at sensor-location, to records the surrounding neighbourhood and reduce sensitivity to individual pixel assignments. 
- The original 17 LCZ class fractions are retained in the intermediate output for inspection. However, using all 17 classes as separate model predictors is considered excessive given that LCZ varies across only 77 sensor locations. Several individual classes are also only sparsely represented in the spatial unit.

Therefore, classes are combined into five fixed groups:
  
| Model predictor | LCZ classes | Included LCZ types |
|---|---:|---|
| Compact built | 1–3 | Compact high-rise, compact mid-rise, compact low-rise |
| Open built | 4–6 | Open high-rise, open mid-rise, open low-rise |
| Other built | 7–10 | Lightweight low-rise, large low-rise, sparsely built, heavy industry |
| Vegetation | 11–14 | Dense trees, scattered trees, bush or scrub, low plants |
| Bare surfaces and water | 15–17 | Bare rock or paved surfaces, bare soil or sand, water |

- Stage 8 joins the five static LCZ fractions to the daily model table using sensor and location IDs. The values are repeated across the daily observations belonging to the same sensor-location pair.
- The Random Forest now uses 18 predictors: the previous 13 predictors and the five grouped LCZ fractions. As the predictor set has changed, the previous parameter search and candidate selection are considered stale. The Random Forest validation will be repeated using the same blocked temporal folds, allowing the LCZ-enhanced results to be compared directly with the previous model.

**Output `scripts/08_build_model_table.py` [run 3: 11.09.2026]**

The model table was rebuilt, adjusted for the five grouped LCZ predictors. Accordingly, it now contains 18 predictors in total: 13 meteorological, temporal and coordinate predictors, alongside the new five LCZ fractions.

| Output | Result |
|---|---:|
| Model-table rows | 231,924 |
| Stable sensor-location pairs | 77 |
| Grouped LCZ predictors | 5 |
| QC-valid PM$_{2.5}$ rows | 182,328 |
| Eligible pre-LEZ training rows | 71,152 |
| Post-LEZ prediction rows | 20,944 |

The number of rows, sensor-location pairs and eligible training observations remained unchanged from the previous model table. This confirms that LCZ was added as static spatial information without removing or duplicating observations.

No sensor-date duplicates or missing predictor values were found in either the training or post-intervention periods. The LCZ values remain constant through time for each sensor-location pair, while the five fractions sum to one for every observation. Ergo, model table is considered complete and suitable for repeating the Random Forest validation.

**Output `scripts/09_validate_random_forest.py` [run 3: 11.09.2026]**

With the new model table applied, RF search evaluated 54 parameter combinations across three blocked validation folds, resulting in 162 model fits. The models used 71,152 pre-LEZ observations and the updated set of 18 predictors.

The lowest mean validation MAE attained = 8.121 µg/m³. However, 30 candidates fell within one standard error of this result, indicating that many parameter combinations performed similarly.

| Metric                                 | Rank 1 | Candidate 7 |
| -------------------------------------- | -----: | ----------: |
| Number of trees                        |    100 |         200 |
| Maximum depth                          |      5 |           5 |
| Maximum features                       |    0.5 |      `sqrt` |
| Minimum observations per leaf          |      3 |           5 |
| Training MAE (µg/m³)                   |  7.376 |       7.643 |
| Validation MAE (µg/m³)                 |  8.121 |       8.133 |
| Validation RMSE (µg/m³)                | 11.558 |      10.467 |
| Mean validation R²                     | −0.261 |      −0.053 |
| Fold-to-fold MAE variation             |  0.632 |       0.470 |
| Training–validation difference (µg/m³) |  0.745 |       0.491 |

Candidate 1 attained the lowest validation MAE, but performed only marginally better (0.012 µg/m³) over candidate 7. Candidate 7 produced a considerably lower RMSE, a less negative R², lower variation between folds and a smaller difference between training and validation error. It is therefore identified as a more balanced and suggests less evidence of overfitting. 

Candidate 7 also uses the same RF parameters as the preferred (candidate 14) depth-5 model from run 2. When brought into comparison, it is possible to asses the impact as a result from introducing LCZ.  

| Metric | Run 2 without LCZ: candidate 14 | Run 3 with LCZ: candidate 7 | Change |
|---|---:|---:|---:|
| Validation MAE (µg/m³) | 8.183 | 8.133 | −0.050 |
| Validation RMSE (µg/m³) | 10.740 | 10.467 | −0.272 |
| Mean validation R² | −0.105 | −0.053 | +0.052 |
| Training–validation difference (µg/m³) | 0.521 | 0.491 | −0.030 |
| Fold-to-fold MAE variation | 0.457 | 0.470 | +0.012 |

Adding LCZ reduces validation MAE by 0.050 µg/m³ and the RMSE by 0.272 µg/m³. The mean validation R² moves closer to zero and the difference between training and validation error decreases slightly. This suggests that LCZ adds some useful spatial information and particularly helped reduce larger prediction errors. However, the attained improvements remain small and the variation between folds increases slightly

A particularly unfortunate point to note stands in relation to the continued mean negative validation R² results. Further inspection showed that this result can be primarily attributed to the first validation fold. 

| Validation fold                    | Heating period | Validation MAE (µg/m³) | Validation RMSE (µg/m³) | Validation R² | Interpretation                                                        |
| ---------------------------------- | -------------- | ---------------------: | ----------------------: | ------------: | --------------------------------------------------------------------- |
| Fold 1                             | 2021–2022      |                  8.365 |                  10.919 |        −0.329 | Performs considerably worse than the mean reference according to R²   |
| Fold 2                             | 2022–2023      |                  8.557 |                  11.151 |         0.163 | Has the largest absolute errors, but explains some variation in PM₂.₅ |
| Fold 3                             | 2023–2024      |                  7.478 |                   9.332 |         0.007 | Performs approximately as well as the mean reference                  |
| Mean across all folds          | —              |              8.133 |              10.467 |    −0.053 | Negative mean R²                                                      |

Fold 2 produced the highest MAE and RMSE, meaning that it had the largest absolute prediction errors. Fold 1 nevertheless performed worst relative to the variation present in its validation observations, as shown by its R² of −0.329. Since the R² values for folds 2 and 3 were both positive, the negative mean R² is entirely attributable to the result in fold 1. Without this fold, the mean R² would be 0.085. 

This indicates that the model did not perform consistently across heating seasons, with the 2021–2022 validation period presenting the main limitation in relation to R². This result could be explained by the smaller training dataset available for the first fold and/or differences in conditions between winters. The model should therefore be described as showing limited and uneven temporal generalisation. 

Including LCZ has broadly retained model performance and produced modest improvements in MAE, RMSE and R² in comparison to candidate 14, run 2. The intended improvement in predictive capacity is therefore partially met. The core issue to be improved--capacity in explaining variation in unseen periods, is observed, albeit not substantially. Therefore, taking everything into consideration, LCZ will be retained, with candidate 7 as the preferred configuration for the following stages. 

Further experiments and alterations are not possible within the remaining project timeframe. Future iterations are advised to test meteorological data with increased spatial resolution, and explore using more direct emission-related predictors to determine whether these improve the model’s temporal and spatial differentiation. 

Output scripts/09b_select_random_forest.py [run 3: 11.09.2026]
Candidate 7 is formally selected and evaluated against the historical sensor-mean benchmark. 

Stage 9b combined the predictions from all three validation folds into 37,418 out-of-fold predictions. The resulting pooled metrics differ slightly from the mean-fold metrics reported in Stage 9 because they are calculated across all validation observations rather than averaged across three separate folds.

| Metric                  | Random Forest | Sensor-mean benchmark | Difference |
| ----------------------- | ------------: | --------------------: | ---------: |
| Validation MAE (µg/m³)  |         8.134 |                 9.233 |     −1.099 |
| Validation RMSE (µg/m³) |        10.501 |                11.741 |     −1.240 |
| Validation R²           |        −0.008 |                −0.260 |     +0.252 |
| Mean error (µg/m³)      |        +5.942 |                +5.376 |     +0.566 |

Candiate 7 RF model reduced MAE by 1.099 µg/m³ and RMSE by 1.240 µg/m³ compared with the sensor-mean benchmark. It therefore produced smaller typical errors and fewer large errors across the combined validation observations. The pooled R² also moved considerably closer to zero, although it remained slightly negative.

Candiate 7 RF model performed better than the benchmark according to MAE, RMSE and R² in all three validation folds.

| Validation period | RF MAE | Benchmark MAE | RF RMSE | Benchmark RMSE |  RF R² | Benchmark R² |
| ----------------- | -----: | ------------: | ------: | -------------: | -----: | -----------: |
| 2021–2022         |  8.365 |         9.360 |  10.919 |         11.664 | −0.329 |       −0.517 |
| 2022–2023         |  8.557 |         9.678 |  11.151 |         12.722 |  0.163 |       −0.089 |
| 2023–2024         |  7.478 |         8.663 |   9.332 |         10.776 |  0.007 |       −0.324 |

This implies that the chosen RF does provide predictive value beyond assigning each sensor its historical mean. However, as noted at an earlier stage, performance remains uneven between heating seasons. Furthermore, performance is not spatially uniform. The model achieves a lower MAE than the benchmark at only 44 of the 77 sensor-location pairs. As such, this overall improvement therefore does not apply consistently across the complete sensor panel. A further limitation to note is the produced prediction bias. + 5.942 µg/m³ indicates that the model systematically inflates concentrations during validation. Although its absolute errors were lower than those of the benchmark, its average overprediction was slightly larger.

The selected model was subsequently evaluated on the October–December 2024 holdout period. As this period had already been inspected during the first model run, it is treated as a recent robustness check rather than a test dataset in the conventional sense.


| Metric               | Random Forest | Sensor-mean benchmark | Difference |
| -------------------- | ------------: | --------------------: | ---------: |
| Holdout MAE (µg/m³)  |         7.939 |                 7.389 |     +0.550 |
| Holdout RMSE (µg/m³) |         9.744 |                 9.163 |     +0.581 |
| Holdout R²           |        −0.417 |                −0.253 |     −0.164 |
| Mean error (µg/m³)   |        +6.677 |                +4.693 |     +1.984 |

In contrast to the blocked-validation results, the Random Forest performed worse than the sensor-mean benchmark during the holdout period. It produced higher MAE and RMSE, a more negative R² and a larger positive mean error. Only 32 of the 77 sensor-location pairs achieved a lower Random Forest MAE than the benchmark.

Interestingly, monthly inspection shows that the result was not consistent across the holdout period.

| Month         | Observed mean (µg/m³) | RF predicted mean (µg/m³) | RF MAE | Benchmark MAE |
| ------------- | --------------------: | ------------------------: | -----: | ------------: |
| October 2024  |                 7.529 |                    12.389 |  6.102 |         7.991 |
| November 2024 |                10.608 |                    18.972 |  9.163 |         6.323 |
| December 2024 |                11.624 |                    18.492 |  8.615 |         7.833 |

RF outperforms the benchmark in October, in contrast with November where it performs considerably worse. December shows a mixed result, with a higher MAE but a slightly lower RMSE. The model inflates mean PM₂.₅ in all three months, with the largest difference occurring in November. The fact that autumn 2024 is not consistent with the validation folds could be attributed, at least to two related conditions. 

  | Predictor             | Training mean | Autumn 2024 mean |              Difference | Standardised difference |
| --------------------- | ------------: | ---------------: | ----------------------: | ----------------------: |
| Relative humidity     |        77.04% |           80.40% | +3.36 percentage points |                  +0.286 |
| Wind speed            |      1.96 m/s |         1.74 m/s |               −0.22 m/s |                  −0.322 |
| Surface pressure      |    918.36 hPa |       921.85 hPa |               +3.49 hPa |                  +0.447 |
| Boundary-layer height |      347.97 m |         264.94 m |                −83.03 m |                  −0.400 |

Compared with the complete October–March training dataset, 
1. the autumn 2024 holdout was more humid, less windy and characterised by higher surface pressure and a lower boundary-layer height, with 
2. these differences may have arisen due to the exclusion of January–March from the holdout rather than unusual conditions during autumn 2024. 
Nevertheless no substantiated claims can be made in this regard. This would require a comparison restricted to October-December training observations across all heating seasons.

The holdout results doe however, reduce the outlook for the later stages of this work. The results currently suggest that the counterfactual baseline is systematically inflated, therefore the difference between observed and counterfactual PM₂.₅ may overstate the apparent post-intervention reduction -> kept in mind for later interpretation of the results. 

As such, the final results must therefore be interpreted as exploratory (this however remains in-line with the initial expectations of this work). The magnitude of any estimated post-LEZ reduction should be considered in relation to the model's observed existing positive bias of ≈ 6 µg/m³ and examined for consistency across months and sensor locations. 

No additional tuning or on the fly bias correction will be performed at this stage. Candidate 7 will be carried forward to final training and counterfactual prediction. 

### 5.2 Training Candidate 7 and feature importance

**Output `scripts/10_train_random_forest.py`** [12.09.2026]
Following formal selection and holdout assessment, candidate 7 was trained on all 71,152 available pre-LEZ observations from 2018 - 2024. This includes the 77 sensor-location pairs and the complete set of 18 predictors. Autumn 2024 was reincorporated, as it was only held pit throughout candidate selection. Otherwise, this period still forms part of the pre-intervention data period. 

```text
Training rows: 71152
Sensor-location pairs: 77
Training period: 2018-01-01 to 2024-12-31
```
From the this run, metadata and feature importance results were consequently saved.

| Predictor or group          | Raw feature importance | Percentage importance |
| --------------------------- | ---------------------: | --------------------: |
| Boundary-layer height       |               0.406849 |                40.68% |
| Wind speed                  |               0.157802 |                15.78% |
| Seasonal cosine             |               0.077241 |                 7.72% |
| Latitude                    |               0.072040 |                 7.20% |
| Temperature                 |               0.054736 |                 5.47% |
| Five LCZ fractions combined |               0.031205 |                 3.12% |

Further inspection of feature importance provides insight into which predictors the model relied on when accounting for spatial and temporal variation in PM₂.₅. This reliance was unevenly distributed. Boundary-layer height and wind speed alone accounted for approximately 56.5% of the total importance. The final model therefore relied predominantly on meteorological conditions related to atmospheric mixing and dispersion. This is physically plausible, as a lower boundary layer and weaker wind can allow pollutants to accumulate near the surface.

| LCZ predictor                  | Raw feature importance | Percentage of total feature importance |
| ------------------------------ | ---------------------: | -------------------------------------: |
| Compact built fraction         |               0.011655 |                                  1.17% |
| Open built fraction            |               0.009990 |                                  1.00% |
| Vegetation fraction            |               0.006758 |                                  0.68% |
| Other built fraction           |               0.002790 |                                  0.28% |
| Bare land/water fraction       |               0.000012 |                                 0.001% |
| All LCZ fractions combined     |               0.031205 |                         3.12% |


The five LCZ fractions together accounted for only 3.12% of the total importance (significance outside compact / open built categories is negligible). This is consistent with the modest improvement observed after adding LCZ during validation. The LCZ variables appear to provide some additional spatial information, but their contribution remained secondary and did not substantially change model performance.

It is important to note that these values describe the relative contribution of each predictor to the model’s predictions. They do not indicate the direction or magnitude of the predictor’s relationship with PM₂.₅ and do not establish causal effects.

### 5.3 Post-LEZ counterfactual predictions
At this stage the chosen RF is applied to the two post-LEZ heating periods. Total: 20,944 predictions produced; cover all 77 sensor-location pairs across January–March 2025 and October 2025–March 2026. 

**Output scripts/11_predict_counterfactual.py** [12.09.2026]
```text
Counterfactual prediction rows: 20944
Observed comparison rows: 19638
Periods: post_2025_jan_mar, post_2025_oct_mar
```
QC-valid observed PM₂.₅ concentrations are available for 19,638 rows, corresponding to 93.76% of the prediction panel. Of the remaining 1,306 rows, 543 -> no sensor observation /  763 did not pass the daily QC requirements.

The computed predictions represent concentrations expected in the post-LEZ period, assuming that the relationship between meteorological / temporal conditions and PM₂.₅ learned in the pre-LEZ period had continued. Core of the output is the difference calculated between observed ("real") and predicted PM₂.₅. Negative values therefore indicate lower observed concentrations relative to predicted concentrations. 

| Counterfactual period   | Prediction rows | Observed comparison rows |   Coverage | Observed mean (µg/m³) | Predicted mean without LEZ (µg/m³) | Observed − predicted (µg/m³) | Relative difference | Median row-level difference (µg/m³) | Sensor-location pairs below prediction |
| ----------------------- | --------------: | -----------------------: | ---------: | --------------------: | ---------------------------------: | ---------------------------: | ------------------: | ----------------------------------: | -------------------------------------: |
| January–March 2025      |           6,930 |                    6,240 |     90.04% |                14.941 |                             16.555 |                       −1.614 |              −9.75% |                              −3.690 |                               43 of 77 |
| October 2025–March 2026 |          14,014 |                   13,398 |     95.60% |                 8.693 |                             15.430 |                       −6.738 |             −43.66% |                              −6.405 |                               74 of 77 |
| **Total**               |      **20,944** |               **19,638** | **93.76%** |                     — |                                  — |                            — |                   — |                                   — |                                      — |

When pooling the mean for both post-LEZ periods, January - March 2025 reveals a reduction of -1.614 µg/m³ in PM₂.₅ concentration when calculating the difference between predicted and observed. The heating period October 2025 - March 2026 reveals a reduction of −6.405 µg/m³ in PM₂.₅. Further inspection on a month by month basis provides a clearer picture as to how this discrepancy between both of the heating periods arose. 

| Month         | Prediction rows | Observed comparison rows | Coverage | Observed mean (µg/m³) | Predicted mean without LEZ (µg/m³) | Observed − predicted (µg/m³) | Relative difference |
| ------------- | --------------: | -----------------------: | -------: | --------------------: | ---------------------------------: | ---------------------------: | ------------------: |
| January 2025  |           2,387 |                    2,226 |   93.26% |                22.240 |                             22.644 |                       −0.404 |              −1.79% |
| February 2025 |           2,156 |                    2,091 |   96.99% |                13.995 |                             13.759 |                       +0.236 |              +1.72% |
| March 2025    |           2,387 |                    1,923 |   80.56% |                 7.520 |                             12.547 |                       −5.027 |             −40.06% |
| October 2025  |           2,387 |                    2,237 |   93.72% |                 6.428 |                             10.799 |                       −4.371 |             −40.47% |
| November 2025 |           2,310 |                    2,213 |   95.80% |                 7.728 |                             17.705 |                       −9.977 |             −56.35% |
| December 2025 |           2,387 |                    2,309 |   96.73% |                13.104 |                             23.061 |                       −9.958 |             −43.18% |
| January 2026  |           2,387 |                    2,290 |   95.94% |                 9.025 |                             15.276 |                       −6.251 |             −40.92% |
| February 2026 |           2,156 |                    2,090 |   96.94% |                 8.131 |                             13.281 |                       −5.151 |             −38.78% |
| March 2026    |           2,387 |                    2,259 |   94.64% |                 7.554 |                             12.132 |                       −4.578 |             −37.73% |

 










