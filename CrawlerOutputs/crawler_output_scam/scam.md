
# Crawler Outputs Analysis Summary


## ALL RUNS ANALYSIS

| Run Name | Static | Headless | Total | Nothing | Invalid | Hanged | Total Proc | Base(s) | Head(s) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| crawler_output_scam_active | 139 | 395 | 534 | 0 | 115 | 450 | 1,129 | 21.51 | 10.00 |


## STATIC VS HEADLESS DETECTION BREAKDOWN

| Run Name | Total Pixels | Static | Static % | Headless | Headless % |
| :--- | ---: | ---: | ---: | ---: | ---: |
| crawler_output_scam_active | 534 | 139 | 26.0% | 395 | 74.0% |


### PIXEL TYPE BREAKDOWN - crawler_output_scam_active

| Detection | State Type | Total Found | Valid Found | Valid % |
| :--- | :--- | ---: | ---: | ---: |
| Static | PIXEL_CORE | 136 | 131 | 96.32% |
| Static | PIXEL_IN_OTHER_TP | 2 | 2 | 100.00% |
| Static | PIXEL_GTM | 1 | 1 | 100.00% |
| **Static Total** |  | **139** | **134** | **96.40%** |
| Headless | FBP | 379 | 379 | 100.00% |
| Headless | DEEP_EXTRACTION_LOCALSTORAGE | 9 | 9 | 100.00% |
| Headless | GTM | 5 | 5 | 100.00% |
| Headless | DEEP_EXTRACTION_SOURCE | 2 | 2 | 100.00% |
| **Headless Total** |  | **395** | **395** | **100.00%** |


## DETECTION RATES (% of total domains)

| Run Name | Pixels Found | Valid Pixels | Detection Rate |
| :--- | ---: | ---: | ---: |
| crawler_output_scam_active | 534 | 475 | 42.1% |

