# A Multi-Source Dataset Integrating Crop Production, Climate, Soil, and Market Prices for Northern Kazakhstan's Grain Belt (1990–2025)

**Authors:** Akezhan Kumarov ¹\*, Nurzhamal Kashkimbayeva ¹

¹ School of Software Engineering, Astana IT University, Astana, Kazakhstan

\* Correspondence: 255662@astanait.edu.kz

**Keywords:** crop yield; agricultural statistics; Kazakhstan; grain belt; climate data; soil data; market prices; data descriptor; open data

---

## Abstract

*(target: ≤170 words, no citations, no claims of novel findings)*

Data-driven decision support for grain producers requires integrating production, climate, soil, and market data, typically scattered across incompatible national and international sources. We present a compiled, cross-validated dataset for Kazakhstan's northern grain belt (Akmola, Kostanay, and North Kazakhstan regions), combining regional crop production statistics (1990–2025) from the national statistics agency with FAOSTAT, ERA5-Land climate reanalysis, ISRIC SoilGrids soil properties, World Bank commodity prices, and weekly domestic market bulletins collected since May 2026. The dataset comprises a merged analysis-ready table (382 rows × 44 columns) and ten intermediate and derived files, including a district-level breakdown (57 districts, 6,067 rows) and an independent cross-validation of regional against national totals. Three data-quality issues found during compilation — an incorrect country code, an unapplied unit-conversion factor, and an unconverted cumulative climate variable — are documented and corrected. All scripts, validation routines, and licensing terms are openly available, supporting yield-forecasting and recommendation research in Kazakhstan and comparable grain-producing regions.

---

## Background & Summary

Farmers and agricultural policymakers in Kazakhstan's northern grain belt — Akmola, Kostanay, and North Kazakhstan regions, together referred to as the "northern grain triangle" — make sowing and marketing decisions with limited access to integrated, analysis-ready data. Existing open sources cover production, climate, soil, or price information separately, each with its own reporting granularity, temporal coverage, and units of measurement. Assembling them into a coherent dataset requires resolving inconsistencies that are easy to overlook: mismatched country codes, undocumented unit-conversion factors, and reporting periods that do not align across sources.

This data descriptor presents a compiled dataset that integrates six primary sources — national and regional production statistics, global commodity prices, climate reanalysis, soil properties, and weekly domestic market bulletins — into a single, cross-validated resource covering three grain-producing regions of Kazakhstan. The dataset was developed as part of ongoing dissertation research on a crop-and-market recommendation system for farmers in this region. Unlike aggregate national statistics (e.g., FAOSTAT), this dataset provides regional and, for two of the three regions, district-level granularity, cross-validated against national totals. The compilation methodology and three data-quality issues discovered and corrected during collection are documented in detail (Technical Validation), consistent with the goal of promoting transparent and reusable agricultural data for the region.

---

## Methods

Data were collected between May and September 2026 using automated Python scripts, each corresponding to one source. The pipeline (scripts `01`–`10`) is openly available in the accompanying code repository (see Code Availability). All scripts write outputs to a common `output/` directory and log data-quality checks to the console; a description of the pipeline structure is provided in Table 1.

**Table 1.** Pipeline scripts, data sources, and update frequency.

| Script | Source | Level | Temporal coverage | Update frequency |
|---|---|---|---|---|
| 01 | FAOSTAT (FAO bulk data) | National (Kazakhstan) | 1992–2024 | ~1-year lag |
| 02 | World Bank Pink Sheet | Global commodity prices | 1990–2025 | Monthly |
| 03 | ERA5-Land (Copernicus/ECMWF) | Grain-belt bounding box | 1991–2025 | ~3-month lag |
| 04 | ISRIC SoilGrids v2.0 | 20-point grid, grain belt | Static | ~3-year revision cycle |
| 05 | Bureau of National Statistics of Kazakhstan (stat.gov.kz) | Regional (3 oblasts) | 1990–2025 | Annual |
| 05 (districts) | Same source, district breakdown | 57 districts | 1990/1999–2025 | Annual |
| 06 | Merge of 01–05 | Regional | 1990–2025 | — |
| 07 | Cross-validation, 05 vs. 01 | Regional vs. national | 1990–2025 | — |
| 08 | Grain Union of Kazakhstan (grainunion.kz) | Domestic market (3 oblasts) + export | From 2026-05-25 | Weekly |
| 09 | Derived from 08 + 02 | Domestic/export/world price spread | From 2026-05-25 | Weekly |

**Figure 1.** Temporal coverage and spatial granularity of the seven primary and derived data streams. Soil properties (SoilGrids) are collected as a single point-in-time snapshot rather than a time series; the domestic market series (grainunion.kz) covers 12 weeks at the time of writing and is shown not to scale, with its actual short duration noted explicitly.

*[Insert `figure1_coverage.png` here]*

### 3.1 National production statistics (FAOSTAT)

National-level crop area, production, and producer prices for wheat, barley, maize, sunflower seed, and rapeseed (1992–2024) were retrieved from FAOSTAT bulk data. During validation (Section 5), an incorrect country code was identified and corrected (Table 3).

### 3.2 Global commodity prices (World Bank Pink Sheet)

Monthly and annually averaged USD/tonne prices for ten agricultural commodities and inputs (wheat HRW/SRW, barley, maize, rapeseed/sunflower/soybean/palm oil, DAP and urea fertilizer) were retrieved for 1990–2025. As of data collection (September 2026), no 2026 monthly observations were yet published by the source; this lag is propagated explicitly into the derived price-spread file (Section 3.6).

### 3.3 Climate reanalysis (ERA5-Land)

Monthly climate variables (2 m air temperature, precipitation, potential evaporation, soil water content at two depths, surface solar radiation) were retrieved for a bounding box covering the grain belt (55°N–49°N, 60°E–78°E) for 1991–2025, and aggregated to growing-season (April–September) annual means. During validation, a unit-conversion issue affecting three cumulative variables was identified and corrected (Table 3).

### 3.4 Soil properties (ISRIC SoilGrids v2.0)

Eight soil properties (pH, organic carbon, bulk density, clay/sand/silt content, cation exchange capacity, nitrogen) were retrieved at four depth intervals from 20 grid points spanning the grain belt via the SoilGrids REST API, then averaged to a single representative value per property (0–5 cm layer, mean across grid points). A unit-conversion issue and an intermittent API-retry gap were identified and corrected (Table 3).

### 3.5 Regional and district-level production statistics (stat.gov.kz)

The Bureau of National Statistics of Kazakhstan does not provide a public REST API for crop production; each region publishes historical time-series ("Dynamic Tables") as downloadable spreadsheets. These were retrieved and parsed directly for three target regions: Akmola, Kostanay, and North Kazakhstan. Reporting granularity differs structurally by region: Kostanay and North Kazakhstan publish separate files per crop (wheat, barley, maize, sunflower) with district breakdowns; Akmola publishes at the level of crop groups ("grains and legumes", "oilseeds"), but group files were found to contain embedded sub-rows for wheat and sunflower with their own district breakdown, which were extracted and merged with the single-crop series from the other two regions. Barley and maize for Akmola remain available only at the group level, a genuine source limitation rather than a parsing gap. Reported units (hectares vs. thousand hectares; tonnes vs. centners) differ between region-level files and are resolved dynamically from in-file labels rather than assumed constant. A separate district-level file (57 districts) is maintained independently of the merged analysis table (Section 4).

### 3.6 Domestic and export market prices (Grain Union of Kazakhstan)

Weekly domestic (EXW-elevator, KZT) and export (multiple Incoterms, USD) prices for wheat, barley, and flax seed were extracted from structured weekly market bulletins published by the Grain Union of Kazakhstan (grainunion.kz) since 25 May 2026 — the earliest date at which this structured bulletin format is available in the source's archive (verified by manual review of the full news archive back to 2019). The collection script is designed for recurring execution (e.g., weekly via a scheduled task) and appends new bulletins incrementally; at the time of writing, 12 weekly bulletins (231 price records) had been collected. A derived file (script 09) computes the weekly spread between export and domestic prices, and between domestic and the World Bank global benchmark, explicitly flagging the staleness (in months) of the global benchmark due to its publication lag.

### 3.7 Cross-source validation

An independent validation script (07) compares the sum of regional production (script 05) against the corresponding national total (FAOSTAT, script 01) for each crop and year, and a second validation routine compares district-level sums against the corresponding regional total within script 05. Results are reported in Section 5.

---

## Data Records

The dataset is organized as a set of CSV files in the `output/` directory of the repository, deposited on Zenodo (DOI: 10.5281/zenodo.22748048) and mirrored on GitHub (https://github.com/NecronTrooper/kazakhstan-agri-recommender-data).

**Primary analysis table.** `master_dataset.csv` (382 rows × 44 columns) is the merged, analysis-ready table produced by script 06, combining scripts 01–05. Row granularity is (region, crop, year); coverage is three regions × up to six crops/crop groups × up to 36 years (1990–2025). A complete column dictionary, including units, missingness percentages, and the documented reason for each missingness pattern, is provided as Supplementary File S1. Three feature groups (world commodity prices, climate variables, soil properties) are reported at coarser granularity than the row (national/grain-belt-wide, or year-only) and are replicated across all regions/crops for convenience; this is documented explicitly to prevent misinterpretation of these features as region-varying signals (Supplementary File S1, Section "Important notes before use").

**Intermediate and derived files.** Ten additional files (raw per-source extracts, the district-level breakdown, the cross-validation report, domestic price and spread series, and one clearly labeled illustrative file) are described in full in Supplementary File S2, summarized in Table 2.

**Table 2.** Supplementary output files.

| File | Rows | Granularity | Role |
|---|---|---|---|
| `01_faostat.csv` | 466 | (crop, indicator, year) | Raw national statistics |
| `02_worldbank_prices.csv` / `_monthly.csv` | 36 / 432 | year / (year, month) | Raw global commodity prices |
| `03_era5_climate.csv` / `_monthly.csv` | 35 / 420 | year / (year, month) | Raw climate reanalysis |
| `04_soilgrids_long.csv` / `_wide.csv` | 640 / 80 | (point, depth, property) / (point, depth) | Raw soil properties |
| `05_kaz_stat.csv` | 382 | (region, crop, year) | Regional production (oblast level) |
| `05_kaz_stat_districts.csv` | 6,067 | (region, district, crop, year) | District-level production, 57 districts |
| `07_validation_report.csv` | 182 | (crop, year) | Regional-vs-national cross-validation detail |
| `08_grainunion_domestic_prices.csv` / `_fx_rates.csv` | 231 / 12 | (bulletin, crop/basis) / (bulletin) | Weekly domestic/export prices and FX rates |
| `09_price_spread.csv` | 12 | (bulletin week) | Domestic/export/world price spread |
| `10_district_price_snapshot.csv` | 177 | (district, crop) | **Illustrative only** — see Usage Notes |

---

## Technical Validation

Three data-quality issues were identified during compilation through automated cross-checks and corrected before finalizing the dataset (Table 3). In each case, the issue was caught by an automated consistency check flagging a physically implausible value, rather than by manual inspection, and confirmed against an independent, well-established reference fact before being classified as an error.

**Table 3.** Data-quality issues identified and corrected during compilation.

| Issue | Source script | Detection method | Correction |
|---|---|---|---|
| Incorrect FAOSTAT country code (63 = Estonia, not Kazakhstan; correct code is 108) | 01 | Regional-vs-national share exceeded 8,900% for some crop/year combinations, a physical impossibility | Corrected to code 108; added a runtime check that the returned country name contains "Kazakhstan" |
| ERA5-Land cumulative variables (precipitation, potential evaporation, solar radiation) reported as a mean daily rate rather than a monthly sum for the `monthly_averaged_reanalysis` product type | 03 | Growing-season precipitation totaled ~13 mm/year against a known regional norm of ~350–400 mm/year | Multiplied cumulative variables by the number of days in each month; verified against the documented 2021–2022 regional drought, which is now correctly reflected as a precipitation anomaly |
| SoilGrids unit-conversion factor not applied (API field name is `d_factor`, not `conversion_factor` as originally coded, so a default of 1 was silently used) | 04 | Clay + sand + silt summed to ~1,000 instead of ~100%; pH values of 65–80 instead of 6.5–8.0 | Corrected to read the `d_factor` field; all 20 grid points re-collected |

Two additional issues affecting the district-level file were identified and corrected during a later revision (a false-positive unit-scale-jump detector on small district series, and a double-counting of production totals caused by nested "of which: wheat" / "of which: sunflower seed" sub-rows within Akmola region's crop-group files) and are documented in the repository's change log together with the corresponding commit history.

**Cross-source validation (regional vs. national).** For each crop and year, the sum of regional production (script 05, three target regions) was compared against the corresponding FAOSTAT national total (script 01). No year exceeded a 100% regional share for any crop. Wheat — the dominant crop in all three target regions — showed a stable regional share of the national total with a median of 77% (range 57–88%, coefficient of variation 0.09), consistent with the well-established characterization of Akmola, Kostanay, and North Kazakhstan as Kazakhstan's "northern grain triangle." This share rose from approximately 51% (Kostanay and North Kazakhstan only) to 77% after the embedded Akmola wheat sub-series was extracted (Section 3.5), providing an independent, domain-knowledge-based confirmation of the extraction's correctness. Full per-crop, per-year results are provided in `07_validation_report.csv`.

**Figure 2.** Wheat and barley: combined share of national production (FAOSTAT) accounted for by the three target regions, 1992–2024. Both series remain below the 100% ceiling in every year, and wheat's share is stable around a 77% median, consistent with the established characterization of these three regions as Kazakhstan's principal wheat-producing area.

*[Insert `figure2_validation.png` here]*

**District-level validation.** For each (region, crop, year) group, the sum of district-level production was compared against the corresponding regional total reported in the same source. Of 375 groups checked, 371 (98.9%) matched exactly; the four discrepancies involve maize in Kostanay region, a minor crop with a small absolute production base where rounding at the tonne level produces a visible percentage discrepancy despite a negligible absolute one.

---

## Usage Notes

**Granularity mismatch in `master_dataset.csv`.** World commodity prices and climate variables vary only by year (identical across all three regions and all crops in a given year); soil properties are a single constant value for the entire dataset. Users should not interpret cross-regional differences in yield as being explained by these features in their current form; they function as inter-annual, not inter-regional, signals. A runtime assertion demonstrating this property is provided in Supplementary File S1.

**Short temporal coverage of domestic price data.** The domestic and export price series (scripts 08–09) cover 12 weekly bulletins from 25 May 2026 onward — less than one full seasonal cycle. These data are not intended to support standalone time-series forecasting (e.g., ARIMA, Prophet) at the time of this data descriptor's preparation; they are more appropriately used as a supplementary or calibrating feature alongside a model trained on the longer-running World Bank series. The collection script is designed for continued weekly execution, and the archive will grow over time.

**Figure 3.** Grade-3 wheat price spread across the 12 collected weekly bulletins (25 May – 6 September 2026): export price (DAP basis), domestic market price (EXW-elevator), and the World Bank global benchmark. The export–domestic spread narrows from late June through early August and widens again toward the end of the series as the new harvest reaches the domestic market — averaging +21% over the full period, but not constant week to week. The flat world-benchmark line reflects the World Bank series' publication lag (up to 8 months at the time of writing); the plotted value is the last available monthly figure (as-of), not a contemporaneous price, and the domestic-vs-world spread (−8.4% on average) should be read with this lag in mind.

*[Insert `figure3_price_spread.png` here]*

**Illustrative, non-methodological file.** `10_district_price_snapshot.csv` deliberately joins the most recent available district-level harvest year (2025) with the most recent available weekly price (September 2026) to demonstrate that a downstream recommendation module can technically consume both district-level yield and price data jointly. This file contains an intentional date mismatch and should not be used as a historical record or as a validated input to any yield or price model.

**Domestic price series has no regional axis.** Domestic and export prices in scripts 08–09 are published by the source as a single figure covering all three target regions jointly, not per region — this is a structural property of how the Grain Union of Kazakhstan's elevator prices are reported, not a gap in data collection. Users attempting to join district- or region-level production data with price data should do so on (year, crop) only, once both series share at least one full agricultural cycle of overlapping coverage (from the September 2026 harvest through the August 2027 marketing season); a region-level join key is not meaningful for this price series.

**Regional coverage gaps.** Rapeseed is not published at the regional level by any of the three target regions and is available only via national FAOSTAT figures. Barley and maize for Akmola region are available only as part of an aggregate crop group, not as individual crops, reflecting a genuine limitation of the source rather than the collection methodology.

**Licensing.** The compiled dataset (selection of sources, cleaning, merging, and derived features) is licensed under CC BY 4.0. Primary sources carry their own terms that remain in force independently of this compilation license. FAOSTAT data is licensed under CC BY 4.0 as of FAO's Open Data Licensing for Statistical Databases Policy 2025 (superseding an earlier, more restrictive 2020 policy; verified 14 September 2026), consistent with this dataset's overall license; re-dissemination should still carry FAO's own attribution line ("FAO. [year]. [dataset]. [access date]. [URL] Licence: CC-BY-4.0."). Other sources (Copernicus/ECMWF, ISRIC SoilGrids, the Bureau of National Statistics of Kazakhstan, and the Grain Union of Kazakhstan) carry their own attribution terms, summarized with source and verification date in the repository's `DATA_LICENSE.md`.

---

## Code Availability

All collection, merging, and validation scripts (Python 3.x) are openly available at:
https://github.com/NecronTrooper/kazakhstan-agri-recommender-data (MIT license for code).

## Data Availability

The dataset described in this paper is archived on Zenodo:
DOI: [10.5281/zenodo.22748048](https://doi.org/10.5281/zenodo.22748048)

---

## Author Contributions

Conceptualization, A.K. and N.K.; methodology, data curation, software, validation, and writing — original draft, A.K.; supervision and writing — review and editing, N.K. All authors have read and agreed to the published version of the manuscript.

## Funding

*[To be completed — state any funding source, or "This research received no external funding."]*

## Acknowledgements

This work was conducted as part of a master's dissertation research program at Astana IT University. The authors thank the School of Software Engineering for institutional support.

## Conflicts of Interest

The authors declare no conflict of interest.

---

## References

*(Data Descriptor references are typically limited to the primary data sources and closely related dataset papers; the reference list below is a starting point and should be finalized against the target journal's citation style.)*

1. FAO. FAOSTAT Statistical Database. Food and Agriculture Organization of the United Nations, Rome. Available online: https://www.fao.org/faostat (accessed on 14 September 2026).
2. World Bank. Commodity Markets ("Pink Sheet"). World Bank Group. Available online: https://www.worldbank.org/en/research/commodity-markets (accessed on 14 September 2026).
3. Muñoz Sabater, J. ERA5-Land Monthly Averaged Data from 1950 to Present. Copernicus Climate Change Service (C3S) Climate Data Store (CDS). https://doi.org/10.24381/cds.68d2bb30
4. Poggio, L.; de Sousa, L.M.; Batjes, N.H.; et al. SoilGrids 2.0: producing soil information for the globe with quantified spatial uncertainty. *SOIL* **2021**, *7*, 217–240.
5. Bureau of National Statistics, Agency for Strategic Planning and Reforms of the Republic of Kazakhstan. Agriculture, Forestry and Fisheries Statistics. Available online: https://stat.gov.kz (accessed on 14 September 2026).
6. Grain Union of Kazakhstan. Weekly Grain Market Price Review. Available online: https://grainunion.kz/ru/news/32 (accessed on 14 September 2026).
7. Kumarov, A.; Kashkimbayeva, N.; Kaibassova, D. Comparison of Machine Learning Models for Predicting Crop Yield and Market Prices. [Conference/venue, year — cross-reference to the companion empirical paper once accepted].

---

## Supplementary Files

- **S1.** Data dictionary for `master_dataset.csv` (44 columns, units, missingness).
- **S2.** Data dictionary for all remaining `output/` files (raw per-source extracts, district-level file, validation report, price/spread files).
- **S3.** `DATA_LICENSE.md` — full source-by-source licensing table.
