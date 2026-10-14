
# Crawler Outputs Analysis Summary


## ALL RUNS ANALYSIS

| Run Name | Static | Headless | Total | Nothing | Invalid | Hanged | Total Proc | Base(s) | Head(s) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| crawler_output_batch_02_10000_19999 | 1,358 | 1,104 | 2,462 | 1,791 | 1,247 | 2,638 | 8,319 | 7.24 | 17.67 |


## STATIC VS HEADLESS DETECTION BREAKDOWN

| Run Name | Total Pixels | Static | Static % | Headless | Headless % |
| :--- | ---: | ---: | ---: | ---: | ---: |
| crawler_output_batch_02_10000_19999 | 2,462 | 1,358 | 55.2% | 1,104 | 44.8% |


### PIXEL TYPE BREAKDOWN - crawler_output_batch_02_10000_19999

| Detection | State Type | Total Found | Valid Found | Valid % |
| :--- | :--- | ---: | ---: | ---: |
| Static | PIXEL_GTM | 999 | 998 | 99.90% |
| Static | PIXEL_CORE | 288 | 280 | 97.22% |
| Static | PIXEL_IN_OTHER_TP | 71 | 71 | 100.00% |
| **Static Total** |  | **1,358** | **1,349** | **99.34%** |
| Headless | FBP | 530 | 434 | 81.89% |
| Headless | GTM | 517 | 506 | 97.87% |
| Headless | HTML | 30 | 30 | 100.00% |
| Headless | CAPI_OR_NETWORK | 22 | 0 | 0.00% |
| Headless | DEEP_EXTRACTION_SOURCE | 5 | 0 | 0.00% |
| **Headless Total** |  | **1,104** | **970** | **87.86%** |


## DETECTION RATES (% of total domains)

| Run Name | Pixels Found | Valid Pixels | Detection Rate |
| :--- | ---: | ---: | ---: |
| crawler_output_batch_02_10000_19999 | 2,462 | 2,319 | 23.2% |

