
# Crawler Outputs Analysis Summary


## ALL RUNS ANALYSIS

| Run Name | Static | Headless | Total | Nothing | Invalid | Hanged | Total Proc | Base(s) | Head(s) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| crawler_output_top50K_new | 6,764 | 5,241 | 12,005 | 14,291 | 6,511 | 12,704 | 46,420 | 7.55 | 18.98 |


## STATIC VS HEADLESS DETECTION BREAKDOWN

| Run Name | Total Pixels | Static | Static % | Headless | Headless % |
| :--- | ---: | ---: | ---: | ---: | ---: |
| crawler_output_top50K_new | 12,005 | 6,764 | 56.3% | 5,241 | 43.7% |


### PIXEL TYPE BREAKDOWN - crawler_output_top50K_new

| Detection | State Type | Total Found | Valid Found | Valid % |
| :--- | :--- | ---: | ---: | ---: |
| Static | PIXEL_GTM | 4,867 | 4,861 | 99.88% |
| Static | PIXEL_CORE | 1,568 | 1,527 | 97.39% |
| Static | PIXEL_IN_OTHER_TP | 327 | 327 | 100.00% |
| Static | PIXEL_WORDPRESS | 2 | 2 | 100.00% |
| **Static Total** |  | **6,764** | **6,717** | **99.31%** |
| Headless | FBP | 2,508 | 2,508 | 100.00% |
| Headless | GTM | 2,465 | 2,456 | 99.63% |
| Headless | HTML | 122 | 122 | 100.00% |
| Headless | CAPI_OR_NETWORK | 110 | 105 | 95.45% |
| Headless | DEEP_EXTRACTION_SOURCE | 35 | 35 | 100.00% |
| Headless | DEEP_EXTRACTION_LOCALSTORAGE | 1 | 1 | 100.00% |
| **Headless Total** |  | **5,241** | **5,227** | **99.73%** |


## DETECTION RATES (% of total domains)

| Run Name | Pixels Found | Valid Pixels | Detection Rate |
| :--- | ---: | ---: | ---: |
| crawler_output_top50K_new | 12,005 | 11,944 | 25.7% |

