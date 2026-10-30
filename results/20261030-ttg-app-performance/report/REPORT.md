# TTG application performance results

All 30 entries (one microbenchmark and 29 full applications) were measured under all four configurations at seed42. Each primary cell has at least three independent measured fresh-database trials after one excluded full-workflow warmup. The complete original app walkers and domain workflows retain their native correctness and restart oracles.

## Main observations

Legacy TTG lowered the median full-workflow protocol sum for LinkedList, while all 29 full applications had higher medians in this local workload. These are comparisons of observed medians with n=3, not statistical significance claims. Both dependency configurations issued exactly the same SQL dispatch counts as prefetch off in every app. The separately captured 60 dependency preflight cases considered zero plans despite actual checkpoint activity. No admission plan reached either model; these observations do not evaluate learned discrimination or probing. Their timing variation must not be presented as a dependency-prefetch benefit or an evaluation of trained model discrimination.

## What is measured

Primary DB protocol completion wall time runs from immediately before actual sendall of a prebuilt packet to ReadyForQuery Z. It includes PostgreSQL work, transport and driver decoding/progress. SQL construction, compiler/model CPU and parameter encoding are outside that interval. Driver-call wall time is separately retained and includes encoding. Summed DB intervals can overlap; interval union is separately reported. SQL dispatches, CommandComplete messages, protocol cycles and transaction/control commands are different measured counts. Foreground protocol time includes synchronous speculative resolution and is not pure blocked-thread wait.

Natural close ordering is preserved. A separate post-response control drains late workers and serializes evidence. Primary HTTP is labeled instrumented auxiliary data. Clean app HTTP is deferred because the frozen clean path does not honor the cold-provider reset; all clean HTTP cells remain absent. No fixed overhead subtraction is used.

## Workload results

Entries show median [Q1, Q3] summed protocol-completion milliseconds for the complete ordered workflow. Every cell has n=3 independent trials. Quartiles describe these three observations, not confidence intervals. Full ranges, standard deviations, interval unions, driver times and foreground/background counts are in CSV/JSON.

| Application | None | Original TTG | Dependency always | Dependency expected benefit |
|---|---:|---:|---:|---:|
| LinkedList | 93.03 [91.71, 93.51] | 80.01 [79.08, 80.28] | 122.93 [109.94, 123.55] | 98.01 [94.99, 100.37] |
| LittleX | 42.40 [41.65, 44.12] | 121.95 [114.29, 126.84] | 40.44 [39.67, 47.61] | 43.31 [42.79, 49.72] |
| Jacord | 119.16 [118.98, 119.50] | 129.36 [129.04, 129.82] | 119.88 [118.00, 126.20] | 117.35 [117.05, 118.47] |
| JDrive | 47.82 [47.32, 48.60] | 78.01 [76.94, 80.91] | 48.03 [47.81, 49.75] | 79.55 [64.27, 675.88] |
| IssueDesk | 142.43 [140.88, 146.30] | 301.22 [298.36, 302.47] | 144.61 [144.11, 147.52] | 140.29 [139.85, 142.29] |
| ApprovalDesk | 131.32 [131.31, 131.86] | 279.36 [273.68, 280.60] | 130.23 [128.59, 131.05] | 130.44 [129.09, 131.72] |
| StockRoom | 136.10 [134.09, 136.16] | 325.91 [324.38, 329.18] | 136.57 [135.41, 138.15] | 138.11 [135.91, 139.84] |
| ClinicQueue | 107.74 [107.17, 108.60] | 213.78 [208.03, 216.46] | 106.82 [104.42, 107.58] | 104.49 [103.59, 105.16] |
| CoursePath | 158.73 [156.65, 165.41] | 272.77 [272.73, 273.11] | 159.52 [158.17, 165.15] | 156.26 [154.23, 162.79] |
| LibraryLoans | 145.60 [142.78, 146.50] | 308.94 [308.18, 323.01] | 148.69 [146.75, 148.82] | 146.02 [143.46, 146.04] |
| EventSeats | 105.74 [105.18, 116.52] | 218.21 [217.84, 250.85] | 108.20 [104.81, 108.56] | 104.43 [104.33, 106.75] |
| HelpQueue | 161.24 [160.82, 171.87] | 327.05 [324.09, 332.38] | 159.93 [155.25, 160.04] | 157.39 [156.83, 158.46] |
| RecipePantry | 86.34 [83.69, 86.58] | 198.61 [197.46, 198.90] | 87.75 [84.06, 90.83] | 91.30 [84.28, 98.90] |
| TripBoard | 48.75 [48.67, 50.24] | 122.07 [121.80, 122.94] | 49.22 [47.76, 49.23] | 48.36 [47.56, 52.24] |
| DeliveryRoute | 99.44 [98.97, 102.96] | 229.54 [228.74, 234.14] | 109.48 [104.91, 110.10] | 106.45 [103.11, 107.29] |
| HiringPipeline | 192.38 [189.54, 193.43] | 387.24 [385.76, 389.04] | 180.15 [178.08, 180.19] | 185.77 [180.17, 185.86] |
| SalesPipeline | 64.50 [63.61, 64.66] | 153.47 [153.20, 156.55] | 65.10 [64.80, 65.61] | 64.93 [64.69, 64.94] |
| GrantReview | 78.25 [71.36, 78.50] | 167.98 [167.80, 170.25] | 68.67 [68.12, 68.89] | 77.09 [75.19, 78.66] |
| LabSamples | 77.89 [75.72, 78.24] | 191.11 [190.52, 191.28] | 75.11 [75.04, 75.88] | 79.02 [78.30, 79.39] |
| AssetCare | 61.67 [60.07, 62.11] | 162.25 [160.71, 162.34] | 61.67 [60.89, 62.92] | 62.04 [61.55, 62.93] |
| UtilityMeter | 62.38 [58.88, 63.04] | 131.34 [130.81, 134.31] | 59.42 [56.13, 63.41] | 63.94 [61.18, 69.05] |
| VolunteerShift | 76.11 [76.01, 76.86] | 159.16 [155.79, 165.55] | 76.27 [74.04, 76.35] | 75.58 [75.11, 76.42] |
| PollAssembly | 65.82 [64.66, 68.84] | 147.31 [145.47, 147.50] | 64.49 [63.34, 65.90] | 69.53 [66.67, 71.39] |
| BudgetLedger | 57.85 [54.65, 66.49] | 137.62 [135.83, 137.86] | 53.89 [52.57, 56.17] | 60.03 [56.16, 69.73] |
| BuildRelease | 92.77 [92.18, 93.13] | 201.46 [199.32, 203.96] | 91.65 [91.57, 91.74] | 93.31 [90.36, 93.91] |
| KnowledgeMap | 74.00 [72.89, 97.59] | 170.71 [168.96, 218.50] | 71.94 [70.83, 72.42] | 72.96 [70.88, 74.87] |
| ReturnCounter | 57.83 [57.50, 63.49] | 135.07 [134.60, 135.22] | 57.27 [56.68, 58.58] | 55.43 [54.73, 56.14] |
| GardenPlan | 67.18 [65.90, 68.95] | 154.78 [153.86, 155.69] | 63.33 [63.08, 66.03] | 63.19 [62.20, 66.40] |
| Tournament | 72.32 [70.19, 72.32] | 131.32 [130.46, 131.39] | 72.12 [71.23, 75.47] | 71.17 [69.86, 72.39] |
| IncidentRoom | 77.00 [71.78, 79.18] | 190.21 [188.95, 191.54] | 77.57 [73.55, 94.41] | 67.40 [66.02, 67.91] |

## First workflow request: cold model

Median [Q1, Q3] summed protocol milliseconds; n=3 independent trials.

| Application | None | Original TTG | Dependency always | Dependency expected benefit |
|---|---:|---:|---:|---:|
| LinkedList | 21.23 [20.74, 21.28] | 16.12 [15.32, 17.25] | 50.77 [36.28, 51.54] | 22.68 [21.77, 26.85] |
| LittleX | 5.19 [5.18, 5.34] | 22.92 [21.83, 23.05] | 5.13 [4.99, 5.24] | 5.18 [5.11, 5.33] |
| Jacord | 47.45 [47.13, 47.92] | 48.12 [47.82, 48.44] | 48.28 [47.73, 52.08] | 47.30 [46.99, 47.40] |
| JDrive | 3.86 [3.74, 3.88] | 3.91 [3.77, 4.00] | 3.53 [3.47, 3.59] | 3.77 [3.61, 3.84] |
| IssueDesk | 6.78 [6.77, 6.81] | 16.83 [16.64, 17.02] | 7.02 [6.95, 7.06] | 6.97 [6.71, 7.03] |
| ApprovalDesk | 4.13 [4.00, 4.17] | 10.33 [10.18, 10.48] | 4.07 [3.89, 4.20] | 4.11 [3.81, 4.18] |
| StockRoom | 6.04 [6.01, 6.35] | 24.02 [23.91, 26.72] | 6.19 [6.10, 6.20] | 5.93 [5.92, 6.07] |
| ClinicQueue | 9.58 [9.40, 9.65] | 21.30 [21.26, 21.78] | 9.49 [9.02, 11.08] | 9.32 [9.23, 9.37] |
| CoursePath | 7.10 [6.82, 7.14] | 17.71 [17.43, 17.88] | 7.46 [7.14, 7.48] | 6.85 [6.81, 7.04] |
| LibraryLoans | 7.37 [7.26, 7.40] | 25.32 [25.32, 25.38] | 7.22 [7.18, 7.30] | 6.79 [6.68, 6.83] |
| EventSeats | 6.83 [6.75, 6.86] | 17.95 [17.70, 17.96] | 6.56 [6.55, 6.76] | 7.01 [6.90, 7.15] |
| HelpQueue | 6.68 [6.40, 6.79] | 17.55 [17.46, 17.67] | 6.47 [6.39, 6.49] | 6.52 [6.48, 6.62] |
| RecipePantry | 6.75 [6.43, 6.82] | 20.50 [20.22, 20.54] | 6.20 [6.14, 6.52] | 6.62 [6.34, 6.68] |
| TripBoard | 3.83 [3.79, 3.92] | 12.63 [12.63, 12.75] | 3.68 [3.67, 3.87] | 3.68 [3.66, 3.86] |
| DeliveryRoute | 5.27 [5.22, 5.44] | 19.04 [18.83, 19.20] | 5.35 [5.20, 5.49] | 5.48 [5.26, 5.49] |
| HiringPipeline | 3.75 [3.75, 3.94] | 14.23 [14.19, 14.43] | 3.54 [3.52, 3.67] | 3.87 [3.84, 3.99] |
| SalesPipeline | 5.95 [5.68, 5.99] | 15.07 [14.84, 15.10] | 5.83 [5.77, 5.84] | 5.71 [5.64, 5.79] |
| GrantReview | 5.06 [4.96, 5.19] | 18.03 [17.55, 18.06] | 4.99 [4.96, 5.25] | 5.41 [5.30, 5.58] |
| LabSamples | 4.76 [4.73, 4.79] | 17.57 [17.42, 17.63] | 4.43 [4.39, 4.45] | 4.48 [4.41, 4.51] |
| AssetCare | 5.72 [5.44, 5.80] | 18.49 [18.45, 19.05] | 5.58 [5.51, 5.60] | 5.79 [5.73, 5.81] |
| UtilityMeter | 4.30 [4.09, 4.32] | 15.75 [15.64, 15.90] | 3.87 [3.85, 3.97] | 4.06 [4.00, 4.22] |
| VolunteerShift | 7.27 [7.26, 7.56] | 19.36 [19.34, 19.52] | 7.59 [7.28, 7.87] | 7.41 [7.37, 7.49] |
| PollAssembly | 6.75 [6.19, 6.89] | 18.58 [18.38, 18.62] | 6.06 [5.91, 6.11] | 6.72 [6.21, 6.79] |
| BudgetLedger | 5.30 [5.01, 5.39] | 18.63 [18.47, 18.69] | 5.29 [5.20, 5.30] | 5.26 [5.25, 5.34] |
| BuildRelease | 2.45 [2.39, 2.46] | 10.59 [10.53, 10.67] | 2.36 [2.31, 2.39] | 2.43 [2.40, 2.44] |
| KnowledgeMap | 9.20 [8.87, 9.33] | 21.55 [21.20, 21.62] | 9.22 [9.04, 9.36] | 9.16 [8.84, 9.32] |
| ReturnCounter | 3.77 [3.64, 3.87] | 12.52 [12.44, 12.59] | 3.73 [3.68, 3.79] | 3.67 [3.58, 3.69] |
| GardenPlan | 3.84 [3.77, 3.89] | 14.18 [14.14, 14.23] | 3.68 [3.62, 3.90] | 3.86 [3.62, 3.97] |
| Tournament | 9.97 [9.69, 9.97] | 19.29 [18.96, 19.35] | 9.99 [9.94, 10.09] | 9.96 [9.86, 10.27] |
| IncidentRoom | 3.96 [3.90, 3.99] | 18.70 [18.69, 18.77] | 4.20 [4.06, 4.21] | 3.91 [3.83, 3.97] |

## Final-state warmed read-only phase

Median [Q1, Q3] summed protocol milliseconds; n=3 independent trials.

| Application | None | Original TTG | Dependency always | Dependency expected benefit |
|---|---:|---:|---:|---:|
| LinkedList | 57.56 [57.09, 58.83] | 31.52 [30.26, 32.09] | 62.02 [60.98, 62.57] | 60.80 [60.67, 61.60] |
| LittleX | 15.47 [15.17, 16.16] | 52.77 [46.77, 52.92] | 15.09 [14.95, 15.39] | 14.41 [13.97, 14.68] |
| Jacord | 147.20 [146.56, 147.88] | 133.19 [132.24, 133.28] | 147.10 [144.51, 147.76] | 147.46 [143.76, 148.43] |
| JDrive | 29.61 [28.48, 29.71] | 53.66 [49.76, 54.60] | 30.31 [29.84, 30.67] | 30.72 [29.55, 42.86] |
| IssueDesk | 25.17 [24.73, 25.74] | 44.68 [44.41, 44.97] | 25.56 [24.99, 26.40] | 25.03 [24.81, 26.25] |
| ApprovalDesk | 33.46 [33.06, 33.72] | 50.33 [50.30, 50.65] | 33.46 [32.22, 33.71] | 33.20 [32.56, 33.28] |
| StockRoom | 38.93 [37.47, 38.96] | 73.22 [72.75, 73.37] | 38.97 [37.84, 39.09] | 38.68 [37.53, 39.10] |
| ClinicQueue | 34.01 [33.53, 34.11] | 50.56 [50.09, 50.58] | 33.43 [33.11, 33.79] | 33.09 [33.02, 33.13] |
| CoursePath | 41.79 [40.63, 41.81] | 59.25 [59.19, 60.38] | 40.94 [40.49, 42.52] | 38.21 [38.20, 39.55] |
| LibraryLoans | 39.38 [39.09, 39.69] | 76.21 [75.99, 80.76] | 40.06 [40.00, 40.22] | 39.56 [39.22, 39.86] |
| EventSeats | 33.87 [33.63, 36.60] | 50.62 [49.94, 50.71] | 34.27 [32.97, 35.61] | 33.66 [33.56, 33.84] |
| HelpQueue | 35.53 [34.97, 35.56] | 57.08 [56.88, 57.55] | 34.42 [34.17, 35.18] | 35.61 [34.46, 35.74] |
| RecipePantry | 24.20 [23.42, 25.00] | 41.16 [40.66, 41.42] | 26.81 [26.30, 26.87] | 26.07 [24.28, 26.47] |
| TripBoard | 13.59 [12.91, 13.93] | 30.26 [29.81, 30.62] | 12.21 [11.97, 12.62] | 12.38 [12.18, 12.67] |
| DeliveryRoute | 24.43 [22.88, 25.02] | 46.19 [46.00, 46.25] | 24.06 [23.71, 24.93] | 23.24 [22.56, 23.91] |
| HiringPipeline | 36.99 [36.93, 38.92] | 57.04 [56.93, 57.49] | 38.20 [38.12, 39.59] | 40.97 [39.51, 41.51] |
| SalesPipeline | 17.79 [17.64, 18.13] | 34.78 [34.48, 35.28] | 18.32 [18.32, 18.41] | 17.93 [17.57, 18.01] |
| GrantReview | 23.06 [22.72, 23.53] | 48.36 [48.29, 48.52] | 26.14 [24.10, 29.24] | 25.14 [24.59, 25.80] |
| LabSamples | 21.31 [20.87, 21.52] | 46.65 [46.09, 46.70] | 21.17 [20.70, 21.31] | 21.04 [21.01, 21.57] |
| AssetCare | 22.77 [21.81, 22.89] | 43.13 [43.06, 43.58] | 21.02 [20.79, 22.30] | 20.91 [20.85, 21.40] |
| UtilityMeter | 11.99 [11.99, 12.08] | 32.32 [32.25, 32.72] | 11.77 [11.61, 11.87] | 12.27 [11.74, 12.73] |
| VolunteerShift | 26.80 [26.52, 27.14] | 49.22 [48.31, 49.45] | 25.83 [25.79, 26.71] | 26.62 [26.61, 26.72] |
| PollAssembly | 21.00 [20.98, 22.55] | 43.00 [42.85, 43.40] | 23.16 [22.39, 23.80] | 23.36 [22.48, 23.88] |
| BudgetLedger | 16.97 [16.82, 17.97] | 38.39 [38.02, 38.74] | 17.11 [17.01, 17.13] | 19.42 [17.70, 19.70] |
| BuildRelease | 19.45 [19.41, 19.74] | 37.35 [36.81, 37.43] | 19.09 [19.08, 19.14] | 19.31 [18.56, 19.42] |
| KnowledgeMap | 27.29 [26.73, 27.48] | 49.36 [49.21, 49.87] | 26.26 [26.14, 26.34] | 26.93 [26.29, 26.95] |
| ReturnCounter | 16.03 [15.74, 16.53] | 32.87 [32.65, 33.11] | 15.26 [14.74, 15.37] | 16.02 [15.53, 16.73] |
| GardenPlan | 23.67 [23.33, 24.98] | 41.59 [41.57, 41.78] | 24.28 [23.12, 24.39] | 21.54 [21.27, 23.25] |
| Tournament | 31.78 [31.09, 32.05] | 50.66 [49.70, 51.12] | 31.67 [31.18, 31.87] | 33.01 [32.73, 33.02] |
| IncidentRoom | 23.10 [21.62, 23.28] | 47.60 [47.15, 47.91] | 24.23 [23.32, 24.46] | 23.04 [22.16, 23.05] |

## Actual SQL dispatch counts

Each entry is total / non-control data / control dispatches for the full workflow. These counts are identical across all three trials in each cell. Non-control means the measured control classifier is false, including data reads/writes and other non-control SQL. Protocol cycles and CommandComplete counts remain separate measured quantities.

| Application | None | Original TTG | Dependency always | Dependency expected benefit |
|---|---:|---:|---:|---:|
| LinkedList | 355 / 313 / 42 | 105 / 51 / 54 | 355 / 313 / 42 | 355 / 313 / 42 |
| LittleX | 153 / 90 / 63 | 154 / 79 / 75 | 153 / 90 / 63 | 153 / 90 / 63 |
| Jacord | 293 / 265 / 28 | 231 / 196 / 35 | 293 / 265 / 28 | 293 / 265 / 28 |
| JDrive | 156 / 107 / 49 | 135 / 80 / 55 | 156 / 107 / 49 | 156 / 107 / 49 |
| IssueDesk | 555 / 366 / 189 | 577 / 358 / 219 | 555 / 366 / 189 | 555 / 366 / 189 |
| ApprovalDesk | 539 / 343 / 196 | 577 / 341 / 236 | 539 / 343 / 196 | 539 / 343 / 196 |
| StockRoom | 497 / 343 / 154 | 493 / 312 / 181 | 497 / 343 / 154 | 497 / 343 / 154 |
| ClinicQueue | 408 / 275 / 133 | 403 / 250 / 153 | 408 / 275 / 133 | 408 / 275 / 133 |
| CoursePath | 521 / 381 / 140 | 544 / 376 / 168 | 521 / 381 / 140 | 521 / 381 / 140 |
| LibraryLoans | 531 / 370 / 161 | 522 / 336 / 186 | 531 / 370 / 161 | 531 / 370 / 161 |
| EventSeats | 434 / 294 / 140 | 436 / 274 / 162 | 434 / 294 / 140 | 434 / 294 / 140 |
| HelpQueue | 605 / 409 / 196 | 607 / 377 / 230 | 605 / 409 / 196 | 605 / 409 / 196 |
| RecipePantry | 327 / 208 / 119 | 335 / 186 / 149 | 327 / 208 / 119 | 327 / 208 / 119 |
| TripBoard | 232 / 134 / 98 | 246 / 133 / 113 | 232 / 134 / 98 | 232 / 134 / 98 |
| DeliveryRoute | 415 / 268 / 147 | 416 / 246 / 170 | 415 / 268 / 147 | 415 / 268 / 147 |
| HiringPipeline | 753 / 494 / 259 | 806 / 477 / 329 | 753 / 494 / 259 | 753 / 494 / 259 |
| SalesPipeline | 292 / 180 / 112 | 307 / 167 / 140 | 292 / 180 / 112 | 292 / 180 / 112 |
| GrantReview | 300 / 188 / 112 | 310 / 170 / 140 | 300 / 188 / 112 | 300 / 188 / 112 |
| LabSamples | 338 / 212 / 126 | 357 / 199 / 158 | 338 / 212 / 126 | 338 / 212 / 126 |
| AssetCare | 273 / 168 / 105 | 276 / 145 / 131 | 273 / 168 / 105 | 273 / 168 / 105 |
| UtilityMeter | 244 / 153 / 91 | 249 / 144 / 105 | 244 / 153 / 91 | 244 / 153 / 91 |
| VolunteerShift | 286 / 195 / 91 | 279 / 174 / 105 | 286 / 195 / 91 | 286 / 195 / 91 |
| PollAssembly | 270 / 179 / 91 | 263 / 158 / 105 | 270 / 179 / 91 | 270 / 179 / 91 |
| BudgetLedger | 234 / 143 / 91 | 235 / 130 / 105 | 234 / 143 / 91 | 234 / 143 / 91 |
| BuildRelease | 390 / 243 / 147 | 411 / 242 / 169 | 390 / 243 / 147 | 390 / 243 / 147 |
| KnowledgeMap | 298 / 186 / 112 | 304 / 164 / 140 | 298 / 186 / 112 | 298 / 186 / 112 |
| ReturnCounter | 259 / 154 / 105 | 274 / 153 / 121 | 259 / 154 / 105 | 259 / 154 / 105 |
| GardenPlan | 286 / 181 / 105 | 294 / 163 / 131 | 286 / 181 / 105 | 286 / 181 / 105 |
| Tournament | 265 / 188 / 77 | 276 / 187 / 89 | 265 / 188 / 77 | 265 / 188 / 77 |
| IncidentRoom | 293 / 174 / 119 | 305 / 166 / 139 | 293 / 174 / 119 | 293 / 174 / 119 |

## Fixed seed and initial graph sizes

Seed42 and smoke/domain fixtures are used throughout. Counts below retain the actual persisted anchor-kind encodings, independently validated on a dedicated native fixture. They count the domain-related census, not every auth/system anchor. Full fixture hashes and ordered action lists are in workload-inventory.json and sealed case evidence.

| Application | NodeAnchor | EdgeAnchor | Fixture SHA256 prefix |
|---|---:|---:|---|
| LinkedList | 32 | 32 | a8147ae49097f9bd |
| LittleX | 30 | 44 | 326a6aa5f413db2c |
| Jacord | 43 | 82 | fe04fd042699242d |
| JDrive | 54 | 54 | 1048aa77dd2ab1b2 |
| IssueDesk | 6 | 8 | 1306cf8448d204ca |
| ApprovalDesk | 5 | 5 | e5cce4a67860ce32 |
| StockRoom | 6 | 9 | 65328a0998515225 |
| ClinicQueue | 8 | 8 | 50e2f90e8a982af2 |
| CoursePath | 7 | 10 | 54949a5d31c64a7e |
| LibraryLoans | 10 | 10 | e3d81788a93b4961 |
| EventSeats | 9 | 9 | a4f29bb5cb0909b8 |
| HelpQueue | 8 | 10 | a2162345865ccf09 |
| RecipePantry | 9 | 13 | 1a6b020f7ca795aa |
| TripBoard | 3 | 3 | 7d246e2957f66fb6 |
| DeliveryRoute | 5 | 5 | a9736dcd94342668 |
| HiringPipeline | 4 | 4 | 34f55db09073b063 |
| SalesPipeline | 5 | 5 | 8a1c0ce94dc8e41e |
| GrantReview | 5 | 6 | 19dcb20c23c5618a |
| LabSamples | 3 | 3 | 09b90151a5dcec8d |
| AssetCare | 4 | 4 | b8e729ae9a840779 |
| UtilityMeter | 5 | 5 | eaa388d9ae4999d7 |
| VolunteerShift | 9 | 13 | 81ce2a9899fef7a8 |
| PollAssembly | 10 | 10 | 7e8c4bc6d4962e48 |
| BudgetLedger | 5 | 5 | 8e87d1105a96cebd |
| BuildRelease | 1 | 1 | 3f36ee3e652e83e4 |
| KnowledgeMap | 7 | 9 | a2e41292b4f292af |
| ReturnCounter | 3 | 3 | b3978c34773f0c55 |
| GardenPlan | 4 | 4 | b8f0a75a945dc9c8 |
| Tournament | 10 | 16 | c87e39bf9c32d590 |
| IncidentRoom | 3 | 6 | 855c7d7cb0604693 |

## Cache, model and mutation interpretation

Fresh equivalent DB each trial, seeded/verified pages warm; fresh session per request; compiler/OS warm. Module SQL-template caches not forcibly reset beyond process lifecycle; setup may warm them.

Cold provider reset on first workflow request; adaptive within workflow. Three warmup final-state reads then three steady reads. Profiles discarded with process; no held-out training.

Workflow results include accepted and rejected mutations, permission checks and reads. Seed/provision/authentication setup is excluded. Per-request authentication/root resolution and transaction completion naturally belong to each actual walker request. Final-state read-only results have three defined warmup reads and three measured reads within each independent trial; their dataset and warmed profile differ from the initial workflow. These phases are not pooled.

Original-app logical outputs, ordering/authorship and full graph topology are checked. Raw wall-clock mutation timestamps are retained; only documented source-oracle exemptions are normalized with validity and created-before-updated checks. Domain-app identities use a persistent bijection preserving references, ordering, amounts, status, URLs and embedded IDs.

## Calibration and independent checks

The main agent accepted the disclosed direct-boundary overlay after independent PG CSV validation and rotated SQL-only controls. The same effective overlay is used for all four primary configurations. The following are observed calibration deltas, not exact causal overhead estimates; raw reference dispersion is retained.

| Synthetic SQL control | Outer-call median delta (us) | Protocol/reference median delta (us) |
|---|---:|---:|
| scalar | 2.240 | -1.489 |
| text16k | 2.022 | 2.050 |
| json16k | 2.305 | -3.043 |
| multirow128 | 9.872 | -3.717 |

Independent app diagnostics checked 20 representative app/policy cases against PostgreSQL CSV execute/error records. Primary/clean timing has statement logging off. Detailed bytes/model/profile runs use separate diagnostics with statement logging on; their elapsed times never replace primary samples. CPU capture was unsuccessful: main found impossible negative self/cumulative entries in 167 of 1432 profiles. All CPU leaders and comparisons are excluded, including apparently nonnegative subsets, pending controlled timer/thread validation. Raw profiles and historical CPU-derived explanation fields remain preserved as unaccepted data. Newly captured diagnostics and earlier preflight mechanism evidence remain distinct datasets.

## Dependency-prefetch mechanism coverage

The following support observations come from separately labeled correctness-preflight diagnostics, not formal timing samples. Zero opportunities are retained and do not count as successful prefetch. Actual considered plans, feature snapshots where present, decision reasons, sample/probe state, submitted/promoted/unused IDs, outcomes and source locations remain in raw events. Static compiler barriers are potential limitations; they are not labeled dynamically reached without corresponding visit/checkpoint evidence.

| Application | Always considered plans | Expected-benefit considered plans |
|---|---:|---:|
| LinkedList | 0 | 0 |
| LittleX | 0 | 0 |
| Jacord | 0 | 0 |
| JDrive | 0 | 0 |
| IssueDesk | 0 | 0 |
| ApprovalDesk | 0 | 0 |
| StockRoom | 0 | 0 |
| ClinicQueue | 0 | 0 |
| CoursePath | 0 | 0 |
| LibraryLoans | 0 | 0 |
| EventSeats | 0 | 0 |
| HelpQueue | 0 | 0 |
| RecipePantry | 0 | 0 |
| TripBoard | 0 | 0 |
| DeliveryRoute | 0 | 0 |
| HiringPipeline | 0 | 0 |
| SalesPipeline | 0 | 0 |
| GrantReview | 0 | 0 |
| LabSamples | 0 | 0 |
| AssetCare | 0 | 0 |
| UtilityMeter | 0 | 0 |
| VolunteerShift | 0 | 0 |
| PollAssembly | 0 | 0 |
| BudgetLedger | 0 | 0 |
| BuildRelease | 0 | 0 |
| KnowledgeMap | 0 | 0 |
| ReturnCounter | 0 | 0 |
| GardenPlan | 0 | 0 |
| Tournament | 0 | 0 |
| IncidentRoom | 0 | 0 |

## Profiles and limits

Validated per-fingerprint primary SQL times/counts and separate detailed query traces explain observed SQL contributions. CPU profiles were captured but failed validity review, so no CPU leaders/comparisons or CPU causes of DB latency are asserted. Consumed prefetch bytes and pure foreground blocked wait are unknown unless separately measured. A demanded visit is not evidence that its payload was promoted.

Accepted per-app SQL observations and static/dynamic mechanism evidence are in `accepted-db-observations.json`. The frozen historical `explanations.json` also contains CPU-derived fields; those fields are unaccepted and excluded from the report.

## Newly captured diagnostic query-count validation

The following are separate post-primary diagnostics with detailed wrappers, foreground-thread CPU profiling and PG CSV logging enabled. Their timings are not primary samples. Server execute/error counts are independently reconciled by SQL fingerprint and owned database; a parse error may lack an execute log, while an execution error can overlap one.

| Application | Policy | Driver dispatches | PG execute records | PG error records |
|---|---|---:|---:|---:|
| ApprovalDesk | Dependency: always | 929 | 927 | 2 |
| ApprovalDesk | Dependency: expected benefit | 929 | 927 | 2 |
| ApprovalDesk | None | 929 | 927 | 2 |
| ApprovalDesk | Original TTG | 990 | 988 | 2 |
| AssetCare | Dependency: always | 593 | 591 | 2 |
| AssetCare | Dependency: expected benefit | 593 | 591 | 2 |
| AssetCare | None | 593 | 591 | 2 |
| AssetCare | Original TTG | 565 | 563 | 2 |
| HiringPipeline | Dependency: always | 1171 | 1169 | 2 |
| HiringPipeline | Dependency: expected benefit | 1171 | 1169 | 2 |
| HiringPipeline | None | 1171 | 1169 | 2 |
| HiringPipeline | Original TTG | 1207 | 1205 | 2 |
| LittleX | Dependency: always | 634 | 632 | 2 |
| LittleX | Dependency: expected benefit | 634 | 632 | 2 |
| LittleX | None | 634 | 632 | 2 |
| LittleX | Original TTG | 635 | 633 | 2 |
| TripBoard | Dependency: always | 503 | 501 | 2 |
| TripBoard | Dependency: expected benefit | 503 | 501 | 2 |
| TripBoard | None | 503 | 501 | 2 |
| TripBoard | Original TTG | 526 | 524 | 2 |

Frozen run_diagnostics.py exited 1 after all20 workflows and PG shutdown: application_name == jac selected zero actual jac:<PID>:run CSV rows; query mismatch at line77. No diagnostic rerun or bound source edit.
Supplemental strict backend-label reconciliation preserves the failed original checker and binds CSV, case seals, profiles and adapter source hashes.

## Preflight versus newly captured mechanism activity

The same checkpoint-hit/considered-plan counts were observed in these separate captures. These rows are not pooled with timing trials.

| Application | Policy | Preflight hits / plans | New diagnostic hits / plans |
|---|---|---:|---:|
| ApprovalDesk | Dependency: always | 15 / 0 | 15 / 0 |
| ApprovalDesk | Dependency: expected benefit | 15 / 0 | 15 / 0 |
| AssetCare | Dependency: always | 33 / 0 | 33 / 0 |
| AssetCare | Dependency: expected benefit | 33 / 0 | 33 / 0 |
| HiringPipeline | Dependency: always | 22 / 0 | 22 / 0 |
| HiringPipeline | Dependency: expected benefit | 22 / 0 | 22 / 0 |
| LittleX | Dependency: always | 22 / 0 | 22 / 0 |
| LittleX | Dependency: expected benefit | 22 / 0 | 22 / 0 |
| TripBoard | Dependency: always | 11 / 0 | 11 / 0 |
| TripBoard | Dependency: expected benefit | 11 / 0 | 11 / 0 |

## Concrete primary trace evidence: LittleX

The four largest recursive fingerprint contributors below are absent with prefetch off. Their mean protocol-sum differences come from all three primary trials. The total workload medians are 42.405 ms (none) and 121.952 ms (legacy TTG); a mean fingerprint delta is not a decomposition of a median difference.

| Recursive fingerprint SHA256 prefix | Mean dispatches none → TTG | Mean protocol difference (ms) |
|---|---:|---:|
| d36899011a19 | 0 → 4 | +57.048 |
| ebc1e8b69ff7 | 0 → 1 | +11.431 |
| 5c85d1cc2354 | 0 → 1 | +6.215 |
| 5644fab3cc55 | 0 → 1 | +4.873 |

### LinkedList — Original TTG

Measured protocol-sum median ratio policy/none: 0.8601.
Observed median SQL dispatch change: -250; control dispatch change: +12.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +6.000 | +52.630 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -140.000 | -49.952 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | -128.000 | -19.093 |

Static compiler examples (potential support/barriers only): Traverse: 0 supported typed visits, 3 barriers; Sum: 0 supported typed visits, 3 barriers.

### LinkedList — Dependency: always

Measured protocol-sum median ratio policy/none: 1.3215.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +12.975 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +8.757 |
| `COMMIT` | +0.000 | +0.160 |

Static compiler examples (potential support/barriers only): Traverse: 0 supported typed visits, 3 barriers; Sum: 0 supported typed visits, 3 barriers.

### LinkedList — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.0536.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +2.622 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +2.412 |
| `DISCARD ALL` | +0.000 | -0.051 |

Static compiler examples (potential support/barriers only): Traverse: 0 supported typed visits, 3 barriers; Sum: 0 supported typed visits, 3 barriers.

### LittleX — Original TTG

Measured protocol-sum median ratio policy/none: 2.8759.
Observed median SQL dispatch change: +1; control dispatch change: +12.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +57.048 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +1.000 | +11.431 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +1.000 | +6.215 |

Static compiler examples (potential support/barriers only): setup_profile: 0 supported typed visits, 8 barriers; get_profile: 1 supported typed visits, 1 barriers.

### LittleX — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9538.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.590 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.437 |
| `SELECT n2.id, e2.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.376 |

Preflight checkpoint example: ability run, line 265, column 9; status blocked; reasons: Unknown effect or cancellation at 273.

Static compiler examples (potential support/barriers only): setup_profile: 0 supported typed visits, 8 barriers; get_profile: 1 supported typed visits, 1 barriers.

### LittleX — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.0213.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +1.550 |
| `SELECT n2.id, e2.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.859 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.660 |

Preflight checkpoint example: ability run, line 265, column 9; status blocked; reasons: Unknown effect or cancellation at 273.

Static compiler examples (potential support/barriers only): setup_profile: 0 supported typed visits, 8 barriers; get_profile: 1 supported typed visits, 1 barriers.

### Jacord — Original TTG

Measured protocol-sum median ratio policy/none: 1.0856.
Observed median SQL dispatch change: -62; control dispatch change: +7.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +3.000 | +28.017 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -39.000 | -22.298 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +1.000 | +4.952 |

Static compiler examples (potential support/barriers only): EnsureUser: 0 supported typed visits, 7 barriers; CreateWorkspace: 0 supported typed visits, 7 barriers.

### Jacord — Dependency: always

Measured protocol-sum median ratio policy/none: 1.0060.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.974 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.967 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.958 |

Preflight checkpoint example: ability gather_messages, line 242, column 5; status blocked; reasons: Unknown effect or cancellation at 246.

Static compiler examples (potential support/barriers only): EnsureUser: 0 supported typed visits, 7 barriers; CreateWorkspace: 0 supported typed visits, 7 barriers.

### Jacord — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9847.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.525 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.447 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.216 |

Preflight checkpoint example: ability gather_messages, line 242, column 5; status blocked; reasons: Unknown effect or cancellation at 246.

Static compiler examples (potential support/barriers only): EnsureUser: 0 supported typed visits, 7 barriers; CreateWorkspace: 0 supported typed visits, 7 barriers.

### JDrive — Original TTG

Measured protocol-sum median ratio policy/none: 1.6314.
Observed median SQL dispatch change: -21; control dispatch change: +6.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +3.000 | +36.551 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -18.000 | -10.947 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | -12.000 | +2.885 |

Static compiler examples (potential support/barriers only): GetRoot: 0 supported typed visits, 9 barriers; ListFolder: 0 supported typed visits, 1 barriers.

### JDrive — Dependency: always

Measured protocol-sum median ratio policy/none: 1.0045.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.783 |
| `COMMIT` | +0.000 | +0.429 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.173 |

Static compiler examples (potential support/barriers only): GetRoot: 0 supported typed visits, 9 barriers; ListFolder: 0 supported typed visits, 1 barriers.

### JDrive — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.6637.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `COMMIT` | +0.000 | +406.762 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +8.092 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +3.082 |

Static compiler examples (potential support/barriers only): GetRoot: 0 supported typed visits, 9 barriers; ListFolder: 0 supported typed visits, 1 barriers.

### IssueDesk — Original TTG

Measured protocol-sum median ratio policy/none: 2.1148.
Observed median SQL dispatch change: +22; control dispatch change: +30.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +26.000 | +117.461 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +5.000 | +37.443 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -25.000 | -11.783 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 12 barriers; ProjectBoard: 3 supported typed visits, 4 barriers.

### IssueDesk — Dependency: always

Measured protocol-sum median ratio policy/none: 1.0153.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.846 |
| `SET LOCAL lock_timeout = ?` | +0.000 | +0.362 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.320 |

Preflight checkpoint example: ability start, line 95, column 9; status blocked; reasons: Unknown effect or cancellation at 98.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 12 barriers; ProjectBoard: 3 supported typed visits, 4 barriers.

### IssueDesk — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9849.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `COMMIT` | +0.000 | -0.767 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.647 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -0.527 |

Preflight checkpoint example: ability start, line 95, column 9; status blocked; reasons: Unknown effect or cancellation at 98.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 12 barriers; ProjectBoard: 3 supported typed visits, 4 barriers.

### ApprovalDesk — Original TTG

Measured protocol-sum median ratio policy/none: 2.1274.
Observed median SQL dispatch change: +38; control dispatch change: +40.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +20.000 | +95.184 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +5.000 | +35.610 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | -1.000 | +13.229 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 9 barriers; ExpenseBoard: 1 supported typed visits, 2 barriers.

### ApprovalDesk — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9917.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `COMMIT` | +0.000 | -1.140 |
| `SELECT doc FROM identity_users WHERE user_id = :u` | +0.000 | -0.388 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.182 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 9 barriers; ExpenseBoard: 1 supported typed visits, 2 barriers.

### ApprovalDesk — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9933.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `COMMIT` | +0.000 | -0.976 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -0.191 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.168 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 9 barriers; ExpenseBoard: 1 supported typed visits, 2 barriers.

### StockRoom — Original TTG

Measured protocol-sum median ratio policy/none: 2.3945.
Observed median SQL dispatch change: -4; control dispatch change: +27.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +8.000 | +111.306 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +7.000 | +31.658 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +27.230 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 11 barriers; Inventory: 5 supported typed visits, 8 barriers.

### StockRoom — Dependency: always

Measured protocol-sum median ratio policy/none: 1.0034.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +1.370 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.744 |
| `COMMIT` | +0.000 | -0.647 |

Preflight checkpoint example: ability start, line 113, column 9; status blocked; reasons: Unknown effect or cancellation at 116.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 11 barriers; Inventory: 5 supported typed visits, 8 barriers.

### StockRoom — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.0147.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +1.861 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +1.055 |
| `COMMIT` | +0.000 | -0.692 |

Preflight checkpoint example: ability start, line 113, column 9; status blocked; reasons: Unknown effect or cancellation at 116.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 11 barriers; Inventory: 5 supported typed visits, 8 barriers.

### ClinicQueue — Original TTG

Measured protocol-sum median ratio policy/none: 1.9841.
Observed median SQL dispatch change: -5; control dispatch change: +20.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +15.000 | +67.144 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +44.186 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -17.000 | -8.209 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; ClinicSchedule: 3 supported typed visits, 5 barriers.

### ClinicQueue — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9914.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -0.885 |
| `COMMIT` | +0.000 | -0.855 |
| `SELECT doc FROM identity_users WHERE user_id = :u` | +0.000 | +0.157 |

Preflight checkpoint example: ability start, line 73, column 9; status blocked; reasons: Unknown effect or cancellation at 76.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; ClinicSchedule: 3 supported typed visits, 5 barriers.

### ClinicQueue — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9698.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -1.223 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.710 |
| `COMMIT` | +0.000 | -0.621 |

Preflight checkpoint example: ability start, line 73, column 9; status blocked; reasons: Unknown effect or cancellation at 76.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; ClinicSchedule: 3 supported typed visits, 5 barriers.

### CoursePath — Original TTG

Measured protocol-sum median ratio policy/none: 1.7185.
Observed median SQL dispatch change: +23; control dispatch change: +28.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +12.000 | +54.688 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +30.133 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +23.010 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 12 barriers; LearningDashboard: 2 supported typed visits, 5 barriers.

### CoursePath — Dependency: always

Measured protocol-sum median ratio policy/none: 1.0050.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.345 |
| `SELECT doc FROM identity_users WHERE user_id = :u` | +0.000 | +0.134 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.092 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 12 barriers; LearningDashboard: 2 supported typed visits, 5 barriers.

### CoursePath — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9844.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -1.449 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -1.216 |
| `COMMIT` | +0.000 | +0.310 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 12 barriers; LearningDashboard: 2 supported typed visits, 5 barriers.

### LibraryLoans — Original TTG

Measured protocol-sum median ratio policy/none: 2.1218.
Observed median SQL dispatch change: -9; control dispatch change: +25.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +5.000 | +88.611 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +18.000 | +84.340 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -21.000 | -9.788 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 9 barriers; LibraryCatalog: 4 supported typed visits, 10 barriers.

### LibraryLoans — Dependency: always

Measured protocol-sum median ratio policy/none: 1.0212.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +1.413 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.597 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.339 |

Preflight checkpoint example: ability start, line 106, column 9; status blocked; reasons: Unknown effect or cancellation at 109.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 9 barriers; LibraryCatalog: 4 supported typed visits, 10 barriers.

### LibraryLoans — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.0029.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `COMMIT` | +0.000 | -0.913 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.354 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.142 |

Preflight checkpoint example: ability start, line 106, column 9; status blocked; reasons: Unknown effect or cancellation at 109.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 9 barriers; LibraryCatalog: 4 supported typed visits, 10 barriers.

### EventSeats — Original TTG

Measured protocol-sum median ratio policy/none: 2.0637.
Observed median SQL dispatch change: +2; control dispatch change: +22.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +15.000 | +67.217 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +5.000 | +44.399 |
| `COMMIT` | +0.000 | +22.640 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 9 barriers; EventCatalog: 2 supported typed visits, 5 barriers.

### EventSeats — Dependency: always

Measured protocol-sum median ratio policy/none: 1.0233.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -2.826 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -1.629 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.639 |

Preflight checkpoint example: ability start, line 99, column 9; status blocked; reasons: Unknown effect or cancellation at 102.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 9 barriers; EventCatalog: 2 supported typed visits, 5 barriers.

### EventSeats — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9877.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -2.623 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -1.314 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.674 |

Preflight checkpoint example: ability start, line 99, column 9; status blocked; reasons: Unknown effect or cancellation at 102.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 9 barriers; EventCatalog: 2 supported typed visits, 5 barriers.

### HelpQueue — Original TTG

Measured protocol-sum median ratio policy/none: 2.0284.
Observed median SQL dispatch change: +2; control dispatch change: +34.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +19.000 | +87.045 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +6.000 | +53.065 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +3.000 | +29.576 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 12 barriers; DeskBoard: 4 supported typed visits, 5 barriers.

### HelpQueue — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9919.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -4.215 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -3.592 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -1.202 |

Preflight checkpoint example: ability start, line 119, column 9; status blocked; reasons: Unknown effect or cancellation at 122.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 12 barriers; DeskBoard: 4 supported typed visits, 5 barriers.

### HelpQueue — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9761.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -3.166 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -2.868 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.905 |

Preflight checkpoint example: ability start, line 119, column 9; status blocked; reasons: Unknown effect or cancellation at 122.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 12 barriers; DeskBoard: 4 supported typed visits, 5 barriers.

### RecipePantry — Original TTG

Measured protocol-sum median ratio policy/none: 2.3004.
Observed median SQL dispatch change: +8; control dispatch change: +30.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +6.000 | +62.619 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +10.000 | +46.656 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -14.000 | -6.811 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 8 barriers; PantryBoard: 3 supported typed visits, 4 barriers.

### RecipePantry — Dependency: always

Measured protocol-sum median ratio policy/none: 1.0164.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.913 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.581 |
| `SELECT doc FROM identity_users WHERE user_id = :u` | +0.000 | +0.302 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 8 barriers; PantryBoard: 3 supported typed visits, 4 barriers.

### RecipePantry — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.0574.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +2.503 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +2.205 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.403 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 8 barriers; PantryBoard: 3 supported typed visits, 4 barriers.

### TripBoard — Original TTG

Measured protocol-sum median ratio policy/none: 2.5041.
Observed median SQL dispatch change: +14; control dispatch change: +15.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +10.000 | +45.406 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +24.634 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -12.000 | -5.645 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 5 barriers; Itinerary: 1 supported typed visits, 4 barriers.

### TripBoard — Dependency: always

Measured protocol-sum median ratio policy/none: 1.0097.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -0.578 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.231 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.205 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 5 barriers; Itinerary: 1 supported typed visits, 4 barriers.

### TripBoard — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9921.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `COMMIT` | +0.000 | +0.626 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.070 |
| `INSERT INTO anchors (id, kind, arch_type, arch_module, fingerprint, root_id, src, dst, undirected, props, format_version, version, updated_at) VALUES ` | +0.000 | +0.062 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 5 barriers; Itinerary: 1 supported typed visits, 4 barriers.

### DeliveryRoute — Original TTG

Measured protocol-sum median ratio policy/none: 2.3083.
Observed median SQL dispatch change: +1; control dispatch change: +23.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +16.000 | +74.499 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +5.000 | +54.922 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -19.000 | -8.646 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; RouteBoard: 3 supported typed visits, 7 barriers.

### DeliveryRoute — Dependency: always

Measured protocol-sum median ratio policy/none: 1.1010.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +1.972 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +1.598 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.473 |

Preflight checkpoint example: ability start, line 62, column 9; status blocked; reasons: Unknown effect or cancellation at 65.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; RouteBoard: 3 supported typed visits, 7 barriers.

### DeliveryRoute — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.0705.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +1.494 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +1.074 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.277 |

Preflight checkpoint example: ability start, line 62, column 9; status blocked; reasons: Unknown effect or cancellation at 65.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; RouteBoard: 3 supported typed visits, 7 barriers.

### HiringPipeline — Original TTG

Measured protocol-sum median ratio policy/none: 2.0129.
Observed median SQL dispatch change: +53; control dispatch change: +70.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +29.000 | +132.938 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +30.132 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +23.537 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 6 barriers; HiringBoard: 2 supported typed visits, 5 barriers.

### HiringPipeline — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9364.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -4.645 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -1.634 |
| `COMMIT` | +0.000 | -1.394 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 6 barriers; HiringBoard: 2 supported typed visits, 5 barriers.

### HiringPipeline — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9656.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -3.639 |
| `COMMIT` | +0.000 | -1.335 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -1.025 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 6 barriers; HiringBoard: 2 supported typed visits, 5 barriers.

### SalesPipeline — Original TTG

Measured protocol-sum median ratio policy/none: 2.3793.
Observed median SQL dispatch change: +15; control dispatch change: +28.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +12.000 | +55.195 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +29.915 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | -6.000 | +9.248 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; SalesBoard: 1 supported typed visits, 4 barriers.

### SalesPipeline — Dependency: always

Measured protocol-sum median ratio policy/none: 1.0092.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.645 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.291 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.207 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; SalesBoard: 1 supported typed visits, 4 barriers.

### SalesPipeline — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.0066.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.304 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.243 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.107 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; SalesBoard: 1 supported typed visits, 4 barriers.

### GrantReview — Original TTG

Measured protocol-sum median ratio policy/none: 2.1468.
Observed median SQL dispatch change: +10; control dispatch change: +28.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +35.917 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +7.000 | +31.908 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +5.000 | +28.974 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 8 barriers; ReviewBoard: 2 supported typed visits, 5 barriers.

### GrantReview — Dependency: always

Measured protocol-sum median ratio policy/none: 0.8776.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -1.993 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -1.082 |
| `COMMIT` | +0.000 | -0.756 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 8 barriers; ReviewBoard: 2 supported typed visits, 5 barriers.

### GrantReview — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9852.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +1.306 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.385 |
| `SET LOCAL lock_timeout = ?` | +0.000 | +0.384 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 8 barriers; ReviewBoard: 2 supported typed visits, 5 barriers.

### LabSamples — Original TTG

Measured protocol-sum median ratio policy/none: 2.4535.
Observed median SQL dispatch change: +19; control dispatch change: +32.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +14.000 | +63.262 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +42.058 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | -8.000 | +8.238 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 5 barriers; LabBoard: 3 supported typed visits, 4 barriers.

### LabSamples — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9642.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `COMMIT` | +0.000 | -0.528 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -0.321 |
| `SET LOCAL lock_timeout = ?` | +0.000 | -0.124 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 5 barriers; LabBoard: 3 supported typed visits, 4 barriers.

### LabSamples — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.0145.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.629 |
| `COMMIT` | +0.000 | +0.598 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.250 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 5 barriers; LabBoard: 3 supported typed visits, 4 barriers.

### AssetCare — Original TTG

Measured protocol-sum median ratio policy/none: 2.6308.
Observed median SQL dispatch change: +3; control dispatch change: +26.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +42.599 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +6.000 | +35.638 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +5.000 | +22.648 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 6 barriers; AssetBoard: 3 supported typed visits, 4 barriers.

### AssetCare — Dependency: always

Measured protocol-sum median ratio policy/none: 1.0000.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `COMMIT` | +0.000 | +0.367 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.276 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.188 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 6 barriers; AssetBoard: 3 supported typed visits, 4 barriers.

### AssetCare — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.0059.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.745 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.606 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.517 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 6 barriers; AssetBoard: 3 supported typed visits, 4 barriers.

### UtilityMeter — Original TTG

Measured protocol-sum median ratio policy/none: 2.1056.
Observed median SQL dispatch change: +5; control dispatch change: +14.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +9.000 | +40.022 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +36.424 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -11.000 | -5.284 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; MeterBoard: 2 supported typed visits, 3 barriers.

### UtilityMeter — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9526.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `COMMIT` | +0.000 | -0.191 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.117 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.115 |

Preflight checkpoint example: ability start, line 56, column 9; status blocked; reasons: Unknown effect or cancellation at 59.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; MeterBoard: 2 supported typed visits, 3 barriers.

### UtilityMeter — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.0250.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +1.929 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +1.097 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.557 |

Preflight checkpoint example: ability start, line 56, column 9; status blocked; reasons: Unknown effect or cancellation at 59.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; MeterBoard: 2 supported typed visits, 3 barriers.

### VolunteerShift — Original TTG

Measured protocol-sum median ratio policy/none: 2.0913.
Observed median SQL dispatch change: -7; control dispatch change: +14.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +43.322 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +9.000 | +42.418 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -13.000 | -5.880 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 12 barriers; VolunteerBoard: 3 supported typed visits, 4 barriers.

### VolunteerShift — Dependency: always

Measured protocol-sum median ratio policy/none: 1.0022.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -0.532 |
| `COMMIT` | +0.000 | -0.471 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.414 |

Preflight checkpoint example: ability start, line 64, column 9; status blocked; reasons: Unknown effect or cancellation at 67.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 12 barriers; VolunteerBoard: 3 supported typed visits, 4 barriers.

### VolunteerShift — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9931.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.220 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -0.187 |
| `COMMIT` | +0.000 | -0.167 |

Preflight checkpoint example: ability start, line 64, column 9; status blocked; reasons: Unknown effect or cancellation at 67.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 12 barriers; VolunteerBoard: 3 supported typed visits, 4 barriers.

### PollAssembly — Original TTG

Measured protocol-sum median ratio policy/none: 2.2380.
Observed median SQL dispatch change: -7; control dispatch change: +14.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +42.878 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +9.000 | +41.037 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -13.000 | -6.148 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; AssemblyBoard: 3 supported typed visits, 5 barriers.

### PollAssembly — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9797.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -1.166 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.253 |
| `COMMIT` | +0.000 | -0.213 |

Preflight checkpoint example: ability start, line 60, column 9; status blocked; reasons: Unknown effect or cancellation at 63.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; AssemblyBoard: 3 supported typed visits, 5 barriers.

### PollAssembly — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.0563.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.586 |
| `COMMIT` | +0.000 | +0.505 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.234 |

Preflight checkpoint example: ability start, line 60, column 9; status blocked; reasons: Unknown effect or cancellation at 63.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; AssemblyBoard: 3 supported typed visits, 5 barriers.

### BudgetLedger — Original TTG

Measured protocol-sum median ratio policy/none: 2.3788.
Observed median SQL dispatch change: +1; control dispatch change: +14.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +42.762 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +9.000 | +41.039 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -11.000 | -6.017 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; BudgetBoard: 4 supported typed visits, 5 barriers.

### BudgetLedger — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9315.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -3.226 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -1.484 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.845 |

Preflight checkpoint example: ability start, line 65, column 9; status blocked; reasons: Unknown effect or cancellation at 68.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; BudgetBoard: 4 supported typed visits, 5 barriers.

### BudgetLedger — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.0377.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.980 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.726 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.256 |

Preflight checkpoint example: ability start, line 65, column 9; status blocked; reasons: Unknown effect or cancellation at 68.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 7 barriers; BudgetBoard: 4 supported typed visits, 5 barriers.

### BuildRelease — Original TTG

Measured protocol-sum median ratio policy/none: 2.1716.
Observed median SQL dispatch change: +21; control dispatch change: +22.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +15.000 | +68.315 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +6.000 | +36.212 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -19.000 | -9.029 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 3 barriers; ReleaseBoard: 1 supported typed visits, 2 barriers.

### BuildRelease — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9879.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `COMMIT` | +0.000 | -0.508 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.300 |
| `DISCARD ALL` | +0.000 | +0.082 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 3 barriers; ReleaseBoard: 1 supported typed visits, 2 barriers.

### BuildRelease — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 1.0058.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `COMMIT` | +0.000 | -0.582 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -0.112 |
| `SELECT doc FROM identity_users WHERE user_id = :u` | +0.000 | -0.067 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 3 barriers; ReleaseBoard: 1 supported typed visits, 2 barriers.

### KnowledgeMap — Original TTG

Measured protocol-sum median ratio policy/none: 2.3070.
Observed median SQL dispatch change: +6; control dispatch change: +28.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +11.000 | +51.944 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +42.698 |
| `COMMIT` | +0.000 | +29.878 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 4 barriers; KnowledgeBoard: 1 supported typed visits, 2 barriers.

### KnowledgeMap — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9721.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -7.960 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -2.553 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -2.462 |

Preflight checkpoint example: ability article, line 176, column 9; status blocked; reasons: Unknown effect or cancellation at 171.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 4 barriers; KnowledgeBoard: 1 supported typed visits, 2 barriers.

### KnowledgeMap — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9859.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -7.438 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -2.343 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -2.016 |

Preflight checkpoint example: ability article, line 176, column 9; status blocked; reasons: Unknown effect or cancellation at 171.

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 4 barriers; KnowledgeBoard: 1 supported typed visits, 2 barriers.

### ReturnCounter — Original TTG

Measured protocol-sum median ratio policy/none: 2.3355.
Observed median SQL dispatch change: +15; control dispatch change: +16.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +11.000 | +49.449 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +24.763 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | -13.000 | -6.417 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 5 barriers; ReturnBoard: 1 supported typed visits, 2 barriers.

### ReturnCounter — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9903.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -1.391 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.649 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.416 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 5 barriers; ReturnBoard: 1 supported typed visits, 2 barriers.

### ReturnCounter — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9584.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -2.219 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.971 |
| `COMMIT` | +0.000 | -0.513 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 5 barriers; ReturnBoard: 1 supported typed visits, 2 barriers.

### GardenPlan — Original TTG

Measured protocol-sum median ratio policy/none: 2.3039.
Observed median SQL dispatch change: +8; control dispatch change: +26.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +5.000 | +37.088 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +6.000 | +27.041 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +23.390 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 6 barriers; GardenBoard: 2 supported typed visits, 3 barriers.

### GardenPlan — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9426.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -1.118 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.473 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.214 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 6 barriers; GardenBoard: 2 supported typed visits, 3 barriers.

### GardenPlan — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9406.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -1.150 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.604 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.393 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 6 barriers; GardenBoard: 2 supported typed visits, 3 barriers.

### Tournament — Original TTG

Measured protocol-sum median ratio policy/none: 1.8158.
Observed median SQL dispatch change: +11; control dispatch change: +12.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +7.000 | +32.218 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +4.000 | +25.004 |
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +5.367 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 4 barriers; BracketBoard: 1 supported typed visits, 4 barriers.

### Tournament — Dependency: always

Measured protocol-sum median ratio policy/none: 0.9973.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +1.064 |
| `COMMIT` | +0.000 | +0.460 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +0.337 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 4 barriers; BracketBoard: 1 supported typed visits, 4 barriers.

### Tournament — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.9841.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +0.340 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.338 |
| `SELECT doc FROM identity_users WHERE user_id = :u` | +0.000 | +0.187 |

Static compiler examples (potential support/barriers only): Seed: 0 supported typed visits, 4 barriers; BracketBoard: 1 supported typed visits, 4 barriers.

### IncidentRoom — Original TTG

Measured protocol-sum median ratio policy/none: 2.4704.
Observed median SQL dispatch change: +12; control dispatch change: +20.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +12.000 | +54.563 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +5.000 | +52.309 |
| `WITH RECURSIVE "_cte0" ("depth", "bfs_ord", "node_id", "arch_type", "parent_depth", "parent_bfs_ord", "parent_node_id", "step_nodes", "step_edges", "i` | +1.000 | +13.226 |

Static compiler examples (potential support/barriers only): ImpactTrace: 1 supported typed visits, 3 barriers; Seed: 0 supported typed visits, 8 barriers.

### IncidentRoom — Dependency: always

Measured protocol-sum median ratio policy/none: 1.0075.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | +4.244 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +2.126 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | +1.924 |

Preflight checkpoint example: ability service, line 39, column 9; status blocked; reasons: Unknown effect or cancellation at 34.

Static compiler examples (potential support/barriers only): ImpactTrace: 1 supported typed visits, 3 barriers; Seed: 0 supported typed visits, 8 barriers.

### IncidentRoom — Dependency: expected benefit

Measured protocol-sum median ratio policy/none: 0.8754.
Observed median SQL dispatch change: +0; control dispatch change: +0.
Fingerprint deltas are observed contributors, not an exact causal partition; timing/reference variability remains.
No dependency plans were considered in recorded correctness diagnostics. This is zero observed mechanism coverage, not successful prefetch.

Largest observed mean per-trial fingerprint deltas from the three primary SQL traces (not a causal decomposition):

| SQL fingerprint excerpt | Dispatch change | Protocol sum change (ms) |
|---|---:|---:|
| `SELECT a.id, a.kind, a.arch_type, a.arch_module, a.fingerprint, a.root_id, a.src, a.dst, a.undirected, a.props, a.version, CASE WHEN a.kind = ? THEN (` | +0.000 | -2.845 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.842 |
| `SELECT n1.id, e1.id FROM unnest(CAST(:origin AS uuid[])) WITH ORDINALITY AS f0(id, ord) LEFT JOIN anchors s1 ON s1.id = f0.id JOIN anchors e1 ON e1.ki` | +0.000 | -0.763 |

Preflight checkpoint example: ability service, line 39, column 9; status blocked; reasons: Unknown effect or cancellation at 34.

Static compiler examples (potential support/barriers only): ImpactTrace: 1 supported typed visits, 3 barriers; Seed: 0 supported typed visits, 8 barriers.

This is a local fixed-seed smoke/domain workload study. No held-out43/44 or injected-latency result is implied. OS/disk caches were not flushed. Small microsecond differences within calibration/reference variation are not established speedups. Per-cell n, quartiles/range, raw trials, dataset/source hashes and exact action lists accompany the results.

## Reproducibility artifacts

- Raw experiment: `project-notes/measurements/ttg-app-performance-20261030/formal-v1`
- Full per-app CSV: `project-notes/measurements/ttg-app-performance-20261030/formal-v1/per-app-results.csv`
- Raw samples and aggregate JSON: `project-notes/measurements/ttg-app-performance-20261030/formal-v1/results.json`
- Main-reviewed plan/instrument manifests: `project-notes/measurements/ttg-app-performance-20261030/review-ready-v2`
- Independent diagnostic counts/profiles: `project-notes/measurements/ttg-app-performance-20261030/diagnostics-v2`

- Main export audit: `project-notes/measurements/ttg-app-main-review-20261030/formal-export-audit.json`
- Main supplemental-diagnostic audit: `project-notes/measurements/ttg-app-main-review-20261030/diagnostic-reconciliation-audit.json`

| Bound input | SHA256 |
|---|---|
| runtime_manifest | 9ddb41dfe9be8b362f6bec204aa66afd4d2ac6d08dee7bc9b14bd94463570d87 |
| overlay_manifest | 779e16e92ab729cb1cca801c2e116f9f88eef1987284bec8adf43e9e7905b332 |
| suite_manifest | ef180e4e3548780779ca6e894a9a3c564d81dbace299ede6c25710ae6456aea7 |
| acceptance_manifest | dda575e11bb69320eda6910ac4970f1fdacf6e00cabc89657c2a4c1de7a235c7 |
| preflight_manifest | 3508fa1da151452a9374b6d0821133b381f3eff9c95d690a63d7d9c45fbb3456 |
| instrument_manifest | 2084f3ba7d8e6f37f01e75af8663f0b4e44643109ecf36c202b798dc24d2e096 |
| experiment_plan | 44c9efc2c4d7843609b93161d27ea8ea664e642a6d2ef79fcee9cc755ddd445d |
