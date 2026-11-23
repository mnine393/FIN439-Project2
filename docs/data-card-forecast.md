# Forecast data card

## Sources and dates

The forecast engine requests monthly FRED series TB3MS (three-month Treasury bill), GS10 (ten-year Treasury), and BAA (Moody's Baa corporate bond yield). Successful downloads are saved under `data/fred/`. Saved total-return history comes from `data/monthly_returns.csv` and saved Yahoo price files. The caller's `as_of` date limits both returns and yields: a forecast at month-end uses only values dated on or before that month-end.

## Assumptions

Cash uses the latest TB3MS yield. Government, broad, and inflation-protected bonds use GS10. Corporate bonds use BAA less 1.0 percentage point for expected defaults. Stock-like assets use TB3MS plus beta times a 4.5% equity risk premium. Beta is estimated through the as-of date and shrunk with the Blume adjustment: 0.67 times estimated beta plus 0.33. Historical arithmetic return and the building-block estimate are blended equally by default.

The process caches each FRED series in memory. It uses a saved file that is less than one day old, requests a download only for missing or stale files with a ten-second timeout, then falls back to the saved file and finally to the documented offline fallbacks. If FRED is unavailable, TB3MS is reconstructed from the saved Treasury-bill proxy in the monthly-return file. Missing GS10 or BAA use a documented 4% fallback, which is labelled in the assumption dates.

## Limitations

Yield is an imperfect predictor, beta is unstable, and all forward estimates are uncertain. The improved simulation preserves 12-month historical runs but cannot create unseen crises. Its covariance estimate uses a simplified Ledoit-Wolf constant-correlation shrinkage target; the full rho term is intentionally omitted, so the reported shrinkage intensity is an approximation. Calibration is reported so forecast coverage can be judged from historical walk-forward outcomes; it is evidence about the method, not a guarantee of future accuracy. Expense ratios are a small saved table of sponsor-published figures and should be checked before trading.
