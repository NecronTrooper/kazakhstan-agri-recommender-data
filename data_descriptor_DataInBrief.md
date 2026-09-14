*NOTE FOR AUTHORS — before submission: verify this structure and section order against the current "Guide for Authors" at https://www.sciencedirect.com/journal/data-in-brief/publish/guide-for-authors, since this draft was assembled from the journal's well-documented Specifications Table format and general house style rather than a directly fetched copy of the live guide (both direct fetch attempts returned HTTP 403). The content itself is complete and accurate to the underlying dataset; only formatting details (exact table field labels, current word/reference limits) should be spot-checked.*

---

# A Multi-Source Dataset Integrating Crop Production, Climate, Soil, and Market Prices for Northern Kazakhstan's Grain Belt (1990–2025)

**Authors:** Akezhan Kumarov ᵃ\*, Nurzhamal Kashkimbayeva ᵃ

ᵃ School of Software Engineering, Astana IT University, Astana, Kazakhstan

\* Corresponding author. E-mail: 255662@astanait.edu.kz

**ORCID:** Akezhan Kumarov — 0009-0006-5674-2929; Nurzhamal Kashkimbayeva — 0000-0002-6070-876X

---

## Abstract

Data-driven decision support for grain producers requires integrating production, climate, soil, and market data, typically scattered across incompatible national and international sources. This article describes a compiled, cross-validated dataset for Kazakhstan's northern grain belt (Akmola, Kostanay, and North Kazakhstan regions), combining regional crop production statistics (1990–2025) from the national statistics agency with FAOSTAT, ERA5-Land climate reanalysis, ISRIC SoilGrids soil properties, World Bank commodity prices, and weekly domestic market bulletins collected since May 2026. The dataset comprises a merged analysis-ready table (382 rows × 44 columns) and ten intermediate and derived files, including a district-level breakdown (57 districts, 6,067 rows) and an independent cross-validation of regional against national totals. Three data-quality issues found during compilation — an incorrect country code, an unapplied unit-conversion factor, and an unconverted cumulative climate variable — are documented and corrected. All collection scripts, validation routines, and licensing terms are openly available.

---

## Specifications Table

| Subject | Agricultural and Biological Sciences — Agronomy and Crop Science |
|---|---|
| Specific subject area | Integrated crop production, climate, soil, and market-price data for regional agricultural decision support in Kazakhstan's northern grain belt |
| Type of data | Tables (CSV); one merged analysis-ready table and ten raw/intermediate/derived tables |
| Data collection | Data were assembled by automated Python scripts (one per source), each retrieving data via a public bulk-download interface, REST API, or structured web page, between May and September 2026. Source-reported units of measurement were resolved dynamically from in-file labels rather than assumed constant; three cross-source and cross-check consistency validations (an incorrect area code, an unapplied unit factor, and an unconverted cumulative climate variable) were applied before finalizing the dataset, and two further checks (a regional-vs-national production cross-validation and a district-vs-regional sum cross-validation) were run as an independent quality gate. Full detail is given in the "Experimental Design, Materials and Methods" section. |
| Data source location | Institution: Astana IT University, Astana, Kazakhstan. Region of data collection: Akmola, Kostanay, and North Kazakhstan regions (oblasts) of the Republic of Kazakhstan, approx. 55°N–49°N, 60°E–78°E. Source repositories: FAOSTAT (Rome, Italy); World Bank (Washington, DC, USA); Copernicus Climate Data Store (EU); ISRIC SoilGrids (Wageningen, Netherlands); Bureau of National Statistics of the Republic of Kazakhstan (Astana, Kazakhstan); Grain Union of Kazakhstan (Astana, Kazakhstan). |
| Data accessibility | Repository name: Zenodo. Data identification number: DOI 10.5281/zenodo.22748048. Direct URL to data: https://doi.org/10.5281/zenodo.22748048. Mirror (code + data, version-controlled): https://github.com/NecronTrooper/kazakhstan-agri-recommender-data |
| Related research article | Not applicable — no companion primary-research article has been published at the time of this data descriptor's submission. |

---

## Value of the Data

- These data are useful because they resolve, in one cross-validated table, a fragmentation problem that otherwise forces every researcher working on Kazakhstan's grain belt to separately source, clean, and reconcile national production statistics, climate reanalysis, soil properties, and market prices — each with its own units, granularity, and update cadence.
- These data can be used by agricultural economists and agronomists to study yield-climate-price relationships in a major Central Asian grain-exporting region; by machine-learning researchers to train and benchmark crop-yield and price-forecasting models at regional or district granularity; and by policymakers to assess the representativeness of national aggregate statistics against the "northern grain triangle" that produces the bulk of the country's wheat.
- These data are linked to ongoing dissertation research on a crop-and-market recommendation system for farmers in Kazakhstan's grain belt; no companion empirical results paper has yet been published, so the dataset is presented as a standalone, reusable resource in its own right.
- Related datasets exist at each individual source (FAOSTAT, World Bank Pink Sheet, ERA5-Land, SoilGrids, stat.gov.kz, grainunion.kz) but only at national, global, or raw-bulletin granularity; none of them offers the region/district-level, cross-validated, analysis-ready integration provided here. Two other groups of researchers working on similar problems in the same region could adopt this dataset directly, or extend the same collection pipeline (openly available, see Data Availability) to other regions or crops.
- Further use of the data is enabled by the fully documented and reproducible collection pipeline (ten Python scripts, one per source or derived step), so the dataset can be regenerated, extended to additional years, or adapted to additional regions without needing to reverse-engineer the original collection logic.

---

## Data Description

The dataset is organized as a set of CSV files, deposited on Zenodo (DOI: 10.5281/zenodo.22748048) and mirrored on GitHub (https://github.com/NecronTrooper/kazakhstan-agri-recommender-data).

**Primary analysis table.** `master_dataset.csv` (382 rows × 44 columns) is the merged, analysis-ready table, combining production statistics, climate, soil, and price sources. Row granularity is (region, crop, year); coverage is three regions × up to six crops/crop groups × up to 36 years (1990–2025). A complete column dictionary, including units, missingness percentages, and the documented reason for each missingness pattern, is provided as Supplementary File S1. Three feature groups — world commodity prices, climate variables, and soil properties — are reported at coarser granularity than the row (national/grain-belt-wide, or year-only) and are replicated across all regions/crops for convenience; this is documented explicitly to prevent misinterpretation of these features as region-varying signals (Supplementary File S1).

**Intermediate and derived files.** Table 1 summarizes the ten additional files: raw per-source extracts, a district-level breakdown, a cross-source validation report, domestic price and spread series, and one file explicitly labeled as illustrative rather than methodological. Full column-level detail is given in Supplementary File S2.

**Table 1.** Supplementary output files.

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
| `10_district_price_snapshot.csv` | 177 | (district, crop) | **Illustrative only** — see Limitations |

**Figure 1.** Temporal coverage and spatial granularity of the seven primary and derived data streams. Soil properties (SoilGrids) are collected as a single point-in-time snapshot rather than a time series; the domestic market series (grainunion.kz) covers 12 weeks at the time of writing and is shown not to scale, with its actual short duration noted explicitly.

*[Insert `figure1_coverage.png` here]*

**Figure 2.** Wheat and barley: combined share of national production (FAOSTAT) accounted for by the three target regions, 1992–2024. Both series remain below the 100% ceiling in every year, and wheat's share is stable around a 77% median, consistent with the established characterization of these three regions as Kazakhstan's principal wheat-producing area.

*[Insert `figure2_validation.png` here]*

**Figure 3.** Grade-3 wheat price spread across the 12 collected weekly bulletins (25 May – 6 September 2026): export price (DAP basis), domestic market price (EXW-elevator), and the World Bank global benchmark. The export–domestic spread narrows from late June through early August and widens again toward the end of the series as the new harvest reaches the domestic market — averaging +21% over the full period, but not constant week to week. The flat world-benchmark line reflects the World Bank series' publication lag (up to 8 months at the time of writing); the plotted value is the last available monthly figure (as-of), not a contemporaneous price.

*[Insert `figure3_price_spread.png` here]*

---

## Experimental Design, Materials and Methods

Data were collected between May and September 2026 using automated Python scripts, each corresponding to one source. The pipeline (scripts `01`–`10`) is openly available in the accompanying code repository (see Data Availability). All scripts write outputs to a common `output/` directory and log data-quality checks to the console.

**National production statistics (FAOSTAT).** National-level crop area, production, and producer prices for wheat, barley, maize, sunflower seed, and rapeseed (1992–2024) were retrieved from FAOSTAT bulk data. During validation, an incorrect country code was identified and corrected (Table 2).

**Global commodity prices (World Bank Pink Sheet).** Monthly and annually averaged USD/tonne prices for ten agricultural commodities and inputs (wheat HRW/SRW, barley, maize, rapeseed/sunflower/soybean/palm oil, DAP and urea fertilizer) were retrieved for 1990–2025. As of data collection (September 2026), no 2026 monthly observations were yet published by the source; this lag is propagated explicitly into the derived price-spread file.

**Climate reanalysis (ERA5-Land).** Monthly climate variables (2 m air temperature, precipitation, potential evaporation, soil water content at two depths, surface solar radiation) were retrieved for a bounding box covering the grain belt (55°N–49°N, 60°E–78°E) for 1991–2025, and aggregated to growing-season (April–September) annual means. During validation, a unit-conversion issue affecting three cumulative variables was identified and corrected (Table 2).

**Soil properties (ISRIC SoilGrids v2.0).** Eight soil properties (pH, organic carbon, bulk density, clay/sand/silt content, cation exchange capacity, nitrogen) were retrieved at four depth intervals from 20 grid points spanning the grain belt via the SoilGrids REST API, then averaged to a single representative value per property (0–5 cm layer, mean across grid points). A unit-conversion issue and an intermittent API-retry gap were identified and corrected (Table 2).

**Regional and district-level production statistics (stat.gov.kz).** The Bureau of National Statistics of Kazakhstan does not provide a public REST API for crop production; each region publishes historical time-series ("Dynamic Tables") as downloadable spreadsheets. These were retrieved and parsed directly for three target regions: Akmola, Kostanay, and North Kazakhstan. Reporting granularity differs structurally by region: Kostanay and North Kazakhstan publish separate files per crop (wheat, barley, maize, sunflower) with district breakdowns; Akmola publishes at the level of crop groups ("grains and legumes", "oilseeds"), but group files were found to contain embedded sub-rows for wheat and sunflower with their own district breakdown, which were extracted and merged with the single-crop series from the other two regions. Barley and maize for Akmola remain available only at the group level, a genuine source limitation rather than a parsing gap. Reported units (hectares vs. thousand hectares; tonnes vs. centners) differ between region-level files and are resolved dynamically from in-file labels rather than assumed constant.

**Domestic and export market prices (Grain Union of Kazakhstan).** Weekly domestic (EXW-elevator, KZT) and export (multiple Incoterms, USD) prices for wheat, barley, and flax seed were extracted from structured weekly market bulletins published since 25 May 2026 — the earliest date at which this structured bulletin format is available in the source's archive (verified by manual review of the full news archive back to 2019). The collection script is designed for recurring execution (e.g., weekly via a scheduled task) and appends new bulletins incrementally; at the time of writing, 12 weekly bulletins (231 price records) had been collected. A derived file (script 09) computes the weekly spread between export and domestic prices, and between domestic and the World Bank global benchmark, explicitly flagging the staleness (in months) of the global benchmark due to its publication lag.

**Cross-source validation.** An independent validation script (07) compares the sum of regional production (script 05) against the corresponding national total (FAOSTAT, script 01) for each crop and year, and a second validation routine compares district-level sums against the corresponding regional total within script 05.

Three data-quality issues were identified during compilation through automated cross-checks and corrected before finalizing the dataset (Table 2). In each case, the issue was caught by an automated consistency check flagging a physically implausible value, rather than by manual inspection, and confirmed against an independent, well-established reference fact before being classified as an error.

**Table 2.** Data-quality issues identified and corrected during compilation.

| Issue | Source script | Detection method | Correction |
|---|---|---|---|
| Incorrect FAOSTAT country code (63 = Estonia, not Kazakhstan; correct code is 108) | 01 | Regional-vs-national share exceeded 8,900% for some crop/year combinations, a physical impossibility | Corrected to code 108; added a runtime check that the returned country name contains "Kazakhstan" |
| ERA5-Land cumulative variables (precipitation, potential evaporation, solar radiation) reported as a mean daily rate rather than a monthly sum for the `monthly_averaged_reanalysis` product type | 03 | Growing-season precipitation totaled ~13 mm/year against a known regional norm of ~350–400 mm/year | Multiplied cumulative variables by the number of days in each month; verified against the documented 2021–2022 regional drought, which is now correctly reflected as a precipitation anomaly |
| SoilGrids unit-conversion factor not applied (API field name is `d_factor`, not `conversion_factor` as originally coded, so a default of 1 was silently used) | 04 | Clay + sand + silt summed to ~1,000 instead of ~100%; pH values of 65–80 instead of 6.5–8.0 | Corrected to read the `d_factor` field; all 20 grid points re-collected |

Two additional issues affecting the district-level file were identified and corrected during a later revision (a false-positive unit-scale-jump detector on small district series, and a double-counting of production totals caused by nested "of which: wheat" / "of which: sunflower seed" sub-rows within Akmola region's crop-group files) and are documented in the repository's change log together with the corresponding commit history.

**Cross-source validation results (regional vs. national).** For each crop and year, the sum of regional production (three target regions) was compared against the corresponding FAOSTAT national total. No year exceeded a 100% regional share for any crop. Wheat — the dominant crop in all three target regions — showed a stable regional share of the national total with a median of 77% (range 57–88%, coefficient of variation 0.09), consistent with the well-established characterization of Akmola, Kostanay, and North Kazakhstan as Kazakhstan's "northern grain triangle." This share rose from approximately 51% (Kostanay and North Kazakhstan only) to 77% after the embedded Akmola wheat sub-series was extracted, providing an independent, domain-knowledge-based confirmation of the extraction's correctness. Full per-crop, per-year results are provided in `07_validation_report.csv`.

**District-level validation results.** For each (region, crop, year) group, the sum of district-level production was compared against the corresponding regional total reported in the same source. Of 375 groups checked, 371 (98.9%) matched exactly; the four discrepancies involve maize in Kostanay region, a minor crop with a small absolute production base where rounding at the tonne level produces a visible percentage discrepancy despite a negligible absolute one.

---

## Limitations

- World commodity prices and climate variables in `master_dataset.csv` vary only by year (identical across all three regions and all crops in a given year); soil properties are a single constant value for the entire dataset. These features should be read as inter-annual, not inter-regional, signals.
- The domestic and export price series (scripts 08–09) cover only 12 weekly bulletins from 25 May 2026 onward — less than one full seasonal cycle — and are not intended to support standalone time-series forecasting at the time of this article's preparation.
- `10_district_price_snapshot.csv` deliberately joins the most recent available district-level harvest year (2025) with the most recent available weekly price (September 2026) to demonstrate joint consumption of district-level yield and price data by a downstream application. This file contains an intentional date mismatch and must not be used as a historical record or as a validated input to any yield or price model.
- Domestic and export prices (scripts 08–09) are published by the source as a single figure covering all three target regions jointly, not per region; this is a structural property of the source, not a collection gap. A region-level join key is not meaningful for this price series.
- Rapeseed is not published at the regional level by any of the three target regions and is available only via national FAOSTAT figures. Barley and maize for Akmola region are available only as part of an aggregate crop group, not as individual crops.

---

## Ethics Statement

This work did not involve human subjects, human data, or animal experimentation. All data were compiled from publicly available government, intergovernmental, and industry-association sources; no primary data collection involving people was undertaken.

---

## CRediT Authorship Contribution Statement

**Akezhan Kumarov:** Conceptualization, Methodology, Software, Data curation, Validation, Writing – original draft. **Nurzhamal Kashkimbayeva:** Conceptualization, Supervision, Writing – review & editing.

---

## Declaration of Competing Interest

The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.

---

## Data Availability

The dataset described in this article is openly available:
- Kumarov, A.; Kashkimbayeva, N. Kazakhstan Agri Recommender — Data Collection Pipeline. Zenodo. https://doi.org/10.5281/zenodo.22748048 (2026).
- Mirror (code + data, version-controlled): https://github.com/NecronTrooper/kazakhstan-agri-recommender-data (MIT license for code; CC BY 4.0 for the compiled dataset).

---

## Acknowledgments

This work was conducted as part of a master's dissertation research program at Astana IT University. The authors thank the School of Software Engineering for institutional support.

## Funding

This research received no external funding.

---

## References

1. FAO. FAOSTAT Statistical Database. Food and Agriculture Organization of the United Nations, Rome, Italy. https://www.fao.org/faostat (accessed 14 September 2026).
2. World Bank. Commodity Markets ("Pink Sheet"). World Bank Group, Washington, DC, USA. https://www.worldbank.org/en/research/commodity-markets (accessed 14 September 2026).
3. J. Muñoz Sabater, ERA5-Land Monthly Averaged Data from 1950 to Present, Copernicus Climate Change Service (C3S) Climate Data Store (CDS), 2021. https://doi.org/10.24381/cds.68d2bb30 (accessed 14 September 2026).
4. L. Poggio, L.M. de Sousa, N.H. Batjes, G.B.M. Heuvelink, B. Kempen, E. Ribeiro, D. Rossiter, SoilGrids 2.0: producing soil information for the globe with quantified spatial uncertainty, SOIL 7 (2021) 217–240.
5. Bureau of National Statistics, Agency for Strategic Planning and Reforms of the Republic of Kazakhstan. Agriculture, Forestry and Fisheries Statistics. https://stat.gov.kz (accessed 14 September 2026).
6. Grain Union of Kazakhstan. Weekly Grain Market Price Review. https://grainunion.kz/ru/news/32 (accessed 14 September 2026).

---

## Supplementary Materials

- **S1.** Data dictionary for `master_dataset.csv` (44 columns, units, missingness).
- **S2.** Data dictionary for all remaining `output/` files (raw per-source extracts, district-level file, validation report, price/spread files).
- **S3.** `DATA_LICENSE.md` — full source-by-source licensing table.
