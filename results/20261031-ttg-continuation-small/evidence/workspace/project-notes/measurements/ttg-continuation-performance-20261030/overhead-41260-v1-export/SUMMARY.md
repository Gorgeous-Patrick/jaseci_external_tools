# Synthetic observer calibration

Nine balanced rotated blocks per mode;200 measured calls/block,20 excluded warmup calls. Values are medians of block medians; brackets show their min/max. No application samples or fixed overhead subtraction.

|Control|Reference protocol us|Direct protocol us|Observed protocol delta us|Delta %|Clean outer us|Direct outer us|
|---|---:|---:|---:|---:|---:|---:|
|scalar|40.480 [38.964,42.258]|40.440 [39.658,41.681]|-0.041|-0.10|43.672 [42.545,45.596]|45.157 [44.333,46.568]|
|text16KiB|68.739 [67.969,70.962]|69.463 [68.445,75.189]|+0.725|+1.05|77.924 [77.499,100.427]|83.891 [82.406,87.442]|
|json16KiB|108.037 [89.724,113.179]|107.662 [93.918,113.340]|-0.376|-0.35|152.272 [130.583,197.783]|152.064 [137.526,161.719]|
|multirow128|390.358 [385.711,392.449]|390.053 [385.180,396.029]|-0.304|-0.08|398.327 [395.955,406.358]|403.586 [398.375,409.010]|

Outer call includes observer work after its protocol/end clocks. Negative observed differences are variation, not an inferred speedup from instrumentation. Raw per-call samples and paired block differences are retained in the sealed inputs/JSON.
