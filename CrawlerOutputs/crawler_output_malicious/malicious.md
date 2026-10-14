
# Crawler Outputs Analysis Summary


## ALL RUNS ANALYSIS

| Run Name | Static | Headless | Total | Nothing | Invalid | Hanged | Total Proc | Base(s) | Head(s) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| crawler_output_active_domains | 57 | 40 | 97 | 7,128 | 1,545 | 2,251 | 11,489 | 2.35 | 22.06 |


## STATIC VS HEADLESS DETECTION BREAKDOWN

| Run Name | Total Pixels | Static | Static % | Headless | Headless % |
| :--- | ---: | ---: | ---: | ---: | ---: |
| crawler_output_active_domains | 97 | 57 | 58.8% | 40 | 41.2% |


### PIXEL TYPE BREAKDOWN - crawler_output_active_domains

| Detection | State Type | Total Found | Valid Found | Valid % |
| :--- | :--- | ---: | ---: | ---: |
| Static | PIXEL_CORE | 54 | 21 | 38.89% |
| Static | PIXEL_IN_OTHER_TP | 2 | 2 | 100.00% |
| Static | PIXEL_GTM | 1 | 1 | 100.00% |
| **Static Total** |  | **57** | **24** | **42.11%** |
| Headless | FBP | 30 | 30 | 100.00% |
| Headless | GTM | 9 | 9 | 100.00% |
| Headless | CAPI_OR_NETWORK | 1 | 1 | 100.00% |
| **Headless Total** |  | **40** | **40** | **100.00%** |


## DETECTION RATES (% of total domains)

| Run Name | Pixels Found | Valid Pixels | Detection Rate |
| :--- | ---: | ---: | ---: |
| crawler_output_active_domains | 97 | 64 | 0.6% |

