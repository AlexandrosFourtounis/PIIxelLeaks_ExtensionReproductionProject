
# Crawler Outputs Analysis Summary


## ALL RUNS ANALYSIS

| Run Name | Static | Headless | Total | Nothing | Invalid | Hanged | Total Proc | Base(s) | Head(s) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| crawler_output_top50K_old | 6,997 | 5,299 | 12,296 | 13,454 | 6,137 | 12,972 | 46,053 | 6.51 | 18.01 |


## STATIC VS HEADLESS DETECTION BREAKDOWN

| Run Name | Total Pixels | Static | Static % | Headless | Headless % |
| :--- | ---: | ---: | ---: | ---: | ---: |
| crawler_output_top50K_old | 12,296 | 6,997 | 56.9% | 5,299 | 43.1% |


### PIXEL TYPE BREAKDOWN - crawler_output_top50K_old

| Detection | State Type | Total Found | Valid Found | Valid % |
| :--- | :--- | ---: | ---: | ---: |
| Static | PIXEL_GTM | 5,119 | 5,112 | 99.86% |
| Static | PIXEL_CORE | 1,537 | 1,508 | 98.11% |
| Static | PIXEL_IN_OTHER_TP | 337 | 337 | 100.00% |
| Static | PIXEL_WORDPRESS | 2 | 2 | 100.00% |
| Static | PIXEL_OBFUSCATED | 2 | 2 | 100.00% |
| **Static Total** |  | **6,997** | **6,961** | **99.49%** |
| Headless | FBP | 2,522 | 2,522 | 100.00% |
| Headless | GTM | 2,519 | 2,508 | 99.56% |
| Headless | CAPI_OR_NETWORK | 112 | 106 | 94.64% |
| Headless | HTML | 110 | 110 | 100.00% |
| Headless | DEEP_EXTRACTION_SOURCE | 36 | 36 | 100.00% |
| **Headless Total** |  | **5,299** | **5,282** | **99.68%** |


## DETECTION RATES (% of total domains)

| Run Name | Pixels Found | Valid Pixels | Detection Rate |
| :--- | ---: | ---: | ---: |
| crawler_output_top50K_old | 12,296 | 12,243 | 26.6% |

