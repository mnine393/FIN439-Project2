# FIN 439 Project 2 visible output

## Material inputs
Decision date: 2026-09-30
Return file: data/monthly_returns.csv; funds: SGOV, IEF, USIG, VT
Estimates use all monthly returns.
Portfolio size: $100,000,000; quarterly payout: $750,000.
The 3% reserve rule equals four quarterly payouts divided by portfolio size.

## CPI as known
CPI year-over-year: 3.35%
Latest known month: 2026-08-01
First published: 2026-09-11
Saved file: data\cpi_asof_2026-09-30.csv

## Portfolios
### Equal weight
Weights: SGOV 25% ($25,000,000), IEF 25% ($25,000,000), USIG 25% ($25,000,000), VT 25% ($25,000,000)
Expected return: 4.47%
Volatility: 5.80%
### 60/40 benchmark
Weights: SGOV 0% ($0), IEF 40% ($40,000,000), USIG 0% ($0), VT 60% ($60,000,000)
Expected return: 7.02%
Volatility: 10.29%
### Constrained portfolio
Weights: SGOV 0% ($0), IEF 10% ($10,000,000), USIG 30% ($30,000,000), VT 60% ($60,000,000)
Expected return: 7.36%
Volatility: 11.23%

## Stress
| case | meets_objective | largest_weight_change | turnover | expected_return_after_cost | trading_cost_dollars |
| --- | --- | --- | --- | --- | --- |
| All monthly returns; SGOV return -1% | True | 0.0 | nan | 0.07360556348435607 | nan |
| All monthly returns; SGOV return +1% | True | 0.0 | nan | 0.07360556348435607 | nan |
| All monthly returns; IEF return -1% | True | 0.05 | nan | 0.0736752036815392 | nan |
| All monthly returns; IEF return +1% | True | 0.30000000000000004 | nan | 0.07418772230125734 | nan |
| All monthly returns; USIG return -1% | False | nan | nan | nan | nan |
| All monthly returns; USIG return +1% | True | 0.050000000000000044 | nan | 0.07410383637122661 | nan |
| All monthly returns; VT return -1% | False | nan | nan | nan | nan |
| All monthly returns; VT return +1% | True | 0.20000000000000004 | nan | 0.07382527558249413 | nan |
| Last 60 monthly returns | True | 0.55 | nan | 0.07396138872871132 | nan |
| Last 36 monthly returns | True | 0.6000000000000001 | nan | 0.07434301215321136 | nan |
| Transaction cost 0 basis points | True | 0.0 | 0.3000000000000001 | 0.07360556348435607 | 0.0 |
| Transaction cost 10 basis points | False | 0.0 | 0.3000000000000001 | 0.07330556348435607 | 30000.000000000007 |
| Transaction cost 25 basis points | False | 0.0 | 0.3000000000000001 | 0.07285556348435607 | 75000.00000000003 |
| Transaction cost 50 basis points | False | 0.0 | 0.3000000000000001 | 0.07210556348435607 | 150000.00000000006 |
| Reserve minimum 10% | True | 0.0 | nan | 0.07360556348435607 | nan |
| Reserve minimum 20% | False | nan | nan | nan | nan |
| 60% cap off | True | 0.30000000000000004 | nan | 0.0737590896115699 | nan |

## Frontier summary
Mixes evaluated: 1,771
Mixes meeting every mandate rule: 2

## Monte Carlo table
| portfolio | probability objective | probability below $90m | median ending value | 5th percentile | 95th percentile |
| --- | --- | --- | --- | --- | --- |
| Equal weight | 0.0967 | 0.2622 | 110895946.68144073 | 83389438.99682342 | 145383703.34197578 |
| 60/40 benchmark | 0.4427 | 0.3726 | 131334488.78257094 | 79499392.17171003 | 211650406.8982477 |
| Constrained portfolio | 0.4723 | 0.4 | 134131070.94258648 | 77020910.57408498 | 225045600.94269508 |

## Backtest table
| portfolio | annualized_return | volatility | worst_peak_to_trough_drop | ending_dollar_value | objective_not_reachable_months | average_turnover |
| --- | --- | --- | --- | --- | --- | --- |
| Constrained portfolio | 0.04760837146090369 | 0.08345905567623137 | -0.2723186705779479 | 134378304.01221773 | 58 | 0.09262295081967215 |
| Equal weight | 0.04329428369589938 | 0.05277414507833145 | -0.1777037098511688 | 126299668.20000568 | 0 | 0.0 |
| 60/40 benchmark | 0.07088288217601368 | 0.09095545159950233 | -0.22977514604908256 | 200960802.84915456 | 0 | 0.0 |
