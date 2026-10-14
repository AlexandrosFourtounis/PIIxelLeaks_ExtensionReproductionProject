
# Crawler Outputs Analysis Summary


## ALL RUNS ANALYSIS

| Run Name | Static | Headless | Total | Nothing | Invalid | Hanged | Total Proc | Base(s) | Head(s) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| crawler_output_batch_01_0_9999 | 1,207 | 1,137 | 2,344 | 1,968 | 1,253 | 2,323 | 8,038 | 4.85 | 14.87 |


## STATIC VS HEADLESS DETECTION BREAKDOWN

| Run Name | Total Pixels | Static | Static % | Headless | Headless % |
| :--- | ---: | ---: | ---: | ---: | ---: |
| crawler_output_batch_01_0_9999 | 2,344 | 1,207 | 51.5% | 1,137 | 48.5% |


### PIXEL TYPE BREAKDOWN - crawler_output_batch_01_0_9999

| Detection | State Type | Total Found | Valid Found | Valid % |
| :--- | :--- | ---: | ---: | ---: |
| Static | PIXEL_GTM | 893 | 891 | 99.78% |
| Static | PIXEL_CORE | 240 | 235 | 97.92% |
| Static | PIXEL_IN_OTHER_TP | 74 | 74 | 100.00% |
| **Static Total** |  | **1,207** | **1,200** | **99.42%** |
| Headless | GTM | 580 | 579 | 99.83% |
| Headless | FBP | 499 | 499 | 100.00% |
| Headless | CAPI_OR_NETWORK | 31 | 26 | 83.87% |
| Headless | HTML | 21 | 21 | 100.00% |
| Headless | DEEP_EXTRACTION_SOURCE | 6 | 6 | 100.00% |
| **Headless Total** |  | **1,137** | **1,131** | **99.47%** |


## DETECTION RATES (% of total domains)

| Run Name | Pixels Found | Valid Pixels | Detection Rate |
| :--- | ---: | ---: | ---: |
| crawler_output_batch_01_0_9999 | 2,344 | 2,331 | 23.3% |

