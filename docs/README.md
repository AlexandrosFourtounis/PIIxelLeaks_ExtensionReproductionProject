# PIIxel Leaks

Meta Pixel crawling and analysis workspace for the replication and extension study.

## Repository Structure

- `Analysis_Top10K`: original Top 10K analysis data, cleanup scripts, and derived outputs.
- `Analysis_Tranco1M`: larger Tranco analysis, parameter studies, and unified dataset scripts.
- `CrawlerOutputs`: saved crawler runs from previous experiments.
- `PIILeakage`: combined result folders for old, new, scam, and malicious datasets.
- `crawler_output`: default output folder for the current crawler run.
- `plots`: generated figures.
- `scripts`: crawler and analysis scripts.
- `suspicious&scam`: scam and suspicious domain lists.
- `tranco`: Tranco lists, batch files, and batching helpers.

## How To Run

Run commands from the repository root unless a script says otherwise. The crawler scripts accept either a single domain or a text file with one domain per line.

### 1. `PII_Hybrid_Crawler.py`

Sequential crawler for one domain or one file of domains.

Use `-d` for a single domain and `-f` for a file:

```bash
python scripts/PII_Hybrid_Crawler.py -d example.com
python scripts/PII_Hybrid_Crawler.py -f tranco/test_domains.txt
```

What it does:

- Fetches each domain.
- Tries static HTML extraction first.
- Falls back to headless rendering when needed.
- Writes crawler output files such as `pixels_found.json`, `state_fbq.json`, timing files, and error logs into the default crawler output folder.

### 2. `PII_Hybrid_Crawler_Parallel.py`

Parallel version of the crawler for a domain list.

```bash
python scripts/PII_Hybrid_Crawler_Parallel.py -f tranco/test_domains.txt
```

What it does:

- Uses the same detection logic as the sequential crawler.
- Runs the work in parallel to speed up large crawls.
- Writes the same family of output files as the sequential version.

Use this when you want throughput rather than a one-off single-domain check.

### 3. `get_PII_from_configs.py`

Validates config IDs found by the crawler and extracts PII parameter information from the Meta config endpoint.

There are two modes:

Compare two crawler folders:

```bash
python scripts/get_PII_from_configs.py --compare --old-dir CrawlerOutputs/crawler_output_10K_old --new-dir CrawlerOutputs/crawler_output_10K_new --results-root PIILeakage/temp_results
```

Single-folder mode:

```bash
python scripts/get_PII_from_configs.py --crawler-dir CrawlerOutputs/crawler_output_10K_old --results-dir PIILeakage/temp_results_single
```

What it does:

- Reads `pixels_found.json`, `state_fbq.json`, or `state_fbw.json` from the crawler output folders.
- Validates each numeric config ID against Meta.
- In compare mode, writes `results_old/` and `results_new/` under the results root.
- In single-folder mode, writes the same result files into the chosen results directory.
- Produces `valid_config_ids_all.json`, `per_domain_all_params_all.json`, and `per_domain_total_params_all.json`.

### 4. `analyze_pixel_usage.py`

Summarizes pixel reuse and parameter usage inside one results folder.

Default input folder:

```bash
python scripts/analyze_pixel_usage.py
```

Custom results folder:

```bash
python scripts/analyze_pixel_usage.py PIILeakage/malicious_results
```

What it does:

- Counts how many domains were processed.
- Counts unique pixel IDs and reused pixel IDs.
- Prints the top reused IDs and their parameters.
- Writes `pixel_usage_summary.json` into the same results directory.

### 4b. `clustering.py`

Enriches clustered domains with WHOIS and hosting information.

```bash
python scripts/clustering.py --summary CrawlerOutputs/crawler_output_scam_fqdns_1k/validation/pixel_usage_summary.json
```

What it does:

- Reads a `pixel_usage_summary.json` file and keeps only multi-domain clusters.
- Queries RDAP for registrar, nameservers, creation date, expiry date, and status.
- Resolves domain IPs and looks up ASN / network holder information.
- Writes `cluster_infra_report.json` and `cluster_infra_report.csv` in `<summary-folder>/cluster_infra` by default, or in the directory you pass with `--output-dir`.

### 4c. `enrich_domain_infra.py`

Enriches a plain domain list with WHOIS and ASN information, without any pixel clustering.

```bash
python scripts/enrich_domain_infra.py --domains suspicious&scam/scam_no_pixels.txt
```

What it does:

- Reads a newline-delimited domain list.
- Queries RDAP for registrar, nameservers, creation date, expiry date, and status.
- Resolves domain IPs and looks up ASN / network holder information.
- Writes `domain_infra_report.json` and `domain_infra_report.csv` in `<domain-list-folder>/domain_infra` by default, or in the directory you pass with `--output-dir`.

### 5. `analyzer.py`

Scans crawler output folders and prints a summary table of detection counts and timing metrics.

```bash
python scripts/analyzer.py
```

To limit the analysis to specific folders under `CrawlerOutputs`, pass `--only` with one or more folder names:

```bash
python scripts/analyzer.py --only crawler_output_10K_old crawler_output_10K_new
```

What it does:

- Walks the `CrawlerOutputs` tree.
- Summarizes static pixels, headless pixels, found-nothing cases, invalid HTML, hanged runs, and total processed domains.
- Saves the printed report to `CrawlerOutputs/analyzer_output.txt`.

### 6. `compare_pixels.py`

Compares two crawler runs and writes JSON and CSV reports for identical, changed, removed, and added pixel detections.

Default comparison:

```bash
python scripts/compare_pixels.py
```

You can point it at other runs if needed:

```bash
python scripts/compare_pixels.py --authors-pixels CrawlerOutputs/authors_output_10K_old/pixels_found.json --our-pixels CrawlerOutputs/crawler_output_10K_old/pixels_found.json
```

What it does:

- Compares the `authors` run against the `our` run.
- Uses both `pixels_found.json` and `state_fbq.json`.
- Writes results under `CrawlerOutputs/Pixels_Comparison/` by default.

### 7. `find_extra_domains.py`

Finds domains that appear in one crawler run but not the other and prepares a rerun list.

```bash
python scripts/find_extra_domains.py
```

What it does:

- Compares the old serial, old parallel, new serial, and new parallel runs.
- Writes `tranco/rerun_extra_domains.txt`.
- Writes `tranco/rerun_extra_domains_details.json` with per-run details for those domains.

### 8. `param_combination.py`

Plots parameter-combination distributions by rank batch.

```bash
python scripts/param_combination.py
```

To use different result folders:

```bash
python scripts/param_combination.py --results-dir PIILeakage/results_crawler_output_batch_01_0_9999 PIILeakage/results_crawler_output_batch_02_10000_19999
```

What it does:

- Reads `per_domain_total_params_all.json` from each batch folder.
- Groups domains by parameter combinations.
- Saves `parameter_combo_distribution.pdf`.

### 9. `per_rank_adoption.py`

Plots parameter adoption across rank buckets.

```bash
python scripts/per_rank_adoption.py
```

You can pass one or more result folders:

```bash
python scripts/per_rank_adoption.py --results-dir PIILeakage/results_crawler_output_batch_01_0_9999 PIILeakage/results_crawler_output_batch_02_10000_19999
```

What it does:

- Reads `per_domain_total_params_all.json` from each batch.
- Counts how often each parameter appears in each rank range.
- Saves `parameter_adoption_per_rank.pdf`.

### 10. `per_rank_parameters.py`

Prints per-rank parameter prevalence tables and summarizes how many domains with pixels also leak PII.

```bash
python scripts/per_rank_parameters.py
```

You can pass multiple result folders if needed:

```bash
python scripts/per_rank_parameters.py --results-dir PIILeakage/temp_results PIILeakage/malicious_results
```

What it does:

- Merges `per_domain_total_params_all.json` files.
- Counts parameter prevalence by domain.
- Prints a PII-leak summary per results folder.

### 11. `top_PII_parameters.py`

Another parameter-counting helper focused on PII prevalence across result folders.

```bash
python scripts/top_PII_parameters.py
```

You can provide multiple result folders:

```bash
python scripts/top_PII_parameters.py --results-dir PIILeakage/temp_results PIILeakage/malicious_results
```

What it does:

- Counts how often each parameter appears across domains.
- Prints how many pixel domains also leak PII in each result folder.

## Batch Runner

Use the Tranco batch runner to split a large list into 10K-sized chunks and run the parallel crawler on each chunk.

```bash
chmod +x tranco/run_batches.sh
./tranco/run_batches.sh tranco/top100K.txt
```

You can override the batch size temporarily:

```bash
BATCH_SIZE=10000 ./tranco/run_batches.sh tranco/top100K.txt
```

```bash
python3 scripts/clustering.py --summary CrawlerOutputs/crawler_output_scam_fqdns_1k/validation/pixel_usage_summary.json
```

## Output Folders

Most generated data lives in `CrawlerOutputs/` and `PIILeakage/`. The crawler scripts write JSON, timing, and status files into per-run folders, while the analysis scripts write summaries and PDF figures next to the results they read.
