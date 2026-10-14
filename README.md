# PIIxel Leaks: Replication & Extension Study

> **Note:** This work was carried out as a collaborative graduate course project by **Anna Makridou** and **Alexandros Fourtounis**.

This repository contains the codebase, datasets, and analysis scripts for the replication and extension of the following study:

> Paschalis Bekos, Panagiotis Papadopoulos, Nicolas Kourtellis, and Michalis Polychronakis.  
> **[PIIxel Leaks: Passive Identification of Personally Identifiable Information Leakage through Meta Pixel](https://doi.org/10.1145/3719027.3765113)**.  
> *Proceedings of the 2025 ACM SIGSAC Conference on Computer and Communications Security (CCS ’25)*, 2025, pp. 4229–4243.

The primary objective of this project is to evaluate the longitudinal stability of Meta Pixel tracking (comparing 2024 vs 2026 data), assess the tracking behavior of adversarial (malicious and scam) domains, and extend the original detection methodology to discover hidden, obfuscated tracking (such as server-side Conversions API and deep extraction).

## Project Structure

```
├── CrawlerOutputs/           # Contains raw outputs, logs, and aggregated JSONs from all crawler runs
│   ├── crawler_output_top50K_old/      # Crawled baseline (2024 Tranco top 50K)
│   ├── crawler_output_top50K_new/      # Crawled baseline (2026 Tranco top 50K)
│   ├── crawler_output_malicious/       # Crawled results for malicious domains
│   └── crawler_output_scam/            # Crawled results for scam domains
├── plots/                    # Generated plots (.pdf) used in the report and presentation
├── scripts/                  # Core Python scripts (Crawlers, Extractors, Analyzers, Plotters)
├── tranco/                   # Tranco lists used for baseline analysis
├── report.tex                # The main ACM-formatted project report (LaTeX)
└── presentation.tex          # The Beamer-formatted slide deck (LaTeX)
```

## Scripts (`scripts/`)

The `scripts/` directory houses the complete data pipeline, consisting of the crawlers, data extractors, analytical scripts, and plot generators.

### 1. Crawlers
- **`PII_Hybrid_Crawler.py`**: The original hybrid crawler logic replicating the baseline measurement study. Combines static source-code analysis with headless browser interactions.
- **`PII_Hybrid_Crawler_Parallel.py`**: A parallelized enhancement of the original crawler, significantly reducing execution time by running domains in threaded batches.
- **`PII_Hybrid_Crawler_Extension.py`**: Our extended crawler that introduces advanced capabilities:
  - **CAPI/Network Interception**: Catches server-side tracking via the Conversions API.
  - **Deep Extraction**: Parses `localStorage` and complex inline scripts to find obfuscated Meta Pixel setups.

### 2. Data Processing & Analyzers
- **`analyzer.py`**: General purpose analysis script that aggregates raw crawler outputs and calculates high-level validation statistics across runs.
- **`get_PII_from_configs.py`**: Interrogates the validated pixel IDs to extract the underlying configuration and determine precisely which Advanced Matching PII parameters are being collected.
- **`analyze_pixel_usage.py`**: Used heavily for adversarial domains. It groups identified Pixel IDs, resolves the ASNs and geographic locations of tracking infrastructures, and highlights clustering behaviors among scam and malicious networks.
- **`find_extra_domains.py`**: A utility script used to identify exactly which domains were recovered uniquely by our extended detection methodologies (CAPI & Deep Extraction) that were completely missed by the baseline.
- **`top_PII_parameters.py`**: Computes macro-level tracking summaries across entire datasets.

### 3. Plot Generators
All plotting scripts are designed to process the flattened `CrawlerOutputs` directories by dynamically mapping domains to their corresponding rank in the Tranco lists, ensuring perfectly bucketed distributions (e.g., `0-10K`, `10K-20K`, etc.).

- **`per_rank_adoption.py`**: Generates `facebook_pixel_adoption_by_rank_*.pdf`, mapping Meta Pixel deployment rates across different website popularity brackets.
- **`per_rank_parameters.py`**: Generates `parameter_adoption_per_rank_*.pdf`, showing absolute counts of individual tracked PII parameters across rank buckets.
- **`param_combination.py`**: Generates `parameter_combo_distribution_*.pdf`, visualizing the most common tracking matrix combinations (e.g., the 11-parameter matrix vs. partial setups) across ranking brackets.

## Workflow Execution
To run the plot generation for the Top 50K datasets (assuming the Tranco CSVs and CrawlerOutputs are present):

```bash
# Generate the parameter combination plots
python scripts/param_combination.py

# Generate parameter adoption by rank plots
python scripts/per_rank_parameters.py

# Generate overall Meta Pixel adoption by rank plots
python scripts/per_rank_adoption.py
```
*(Note: These updated scripts read the `CrawlerOutputs/crawler_output_top50K_new` and `_old` directories automatically and bin them based on the `tranco/top-1m.csv` and `top-1m-new.csv` lists).*
