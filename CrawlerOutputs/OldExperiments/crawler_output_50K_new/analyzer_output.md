
# Crawler Outputs Analysis Summary


## ALL RUNS ANALYSIS

| Run Name | Static | Headless | Total | Nothing | Invalid | Hanged | Total Proc | Base(s) | Head(s) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| crawler_output_50K_new | 6,645 | 4,444 | 11,089 | 11,626 | 7,155 | 11,894 | 42,605 | 8.25 | 21.37 |


## STATIC VS HEADLESS DETECTION BREAKDOWN

| Run Name | Total Pixels | Static | Static % | Headless | Headless % |
| :--- | ---: | ---: | ---: | ---: | ---: |
| crawler_output_50K_new | 11,089 | 6,645 | 59.9% | 4,444 | 40.1% |


### PIXEL TYPE BREAKDOWN - crawler_output_50K_new

| Detection | State Type | Total Found | Valid Found | Valid % |
| :--- | :--- | ---: | ---: | ---: |
| Static | PIXEL_GTM | 4,794 | 4,788 | 99.87% |
| Static | PIXEL_CORE | 1,530 | 1,494 | 97.65% |
| Static | PIXEL_IN_OTHER_TP | 321 | 321 | 100.00% |
| **Static Total** |  | **6,645** | **6,603** | **99.37%** |
| Headless | GTM | 2,369 | 2,360 | 99.62% |
| Headless | FBP | 1,963 | 1,963 | 100.00% |
| Headless | HTML | 112 | 112 | 100.00% |
| **Headless Total** |  | **4,444** | **4,435** | **99.80%** |


## DETECTION RATES (% of total domains)

| Run Name | Pixels Found | Valid Pixels | Detection Rate |
| :--- | ---: | ---: | ---: |
| crawler_output_50K_new | 11,089 | 11,038 | 25.9% |

