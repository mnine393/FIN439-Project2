# FIN 439 Project 2 visible output

## Material inputs
Decision date: 2026-09-30
Return file: data/monthly_returns.csv; funds: SGOV, IEF, USIG, VT
Estimates use all monthly returns.
Portfolio size: $100,000,000; quarterly payout: $750,000.
The 3% reserve rule equals four quarterly payouts divided by portfolio size.

## Consumer Price Index as known
Consumer Price Index year-over-year: 3.35%
Latest known month: 2026-08-01
First published: 2026-09-11
Saved file: data\cpi_asof_2026-09-30.csv

## Portfolios
### Equal weight
Weights: SGOV 25.00% ($25,000,000), IEF 25.00% ($25,000,000), USIG 25.00% ($25,000,000), VT 25.00% ($25,000,000)
Expected return: 4.47%
Volatility: 5.80%
### 60/40 benchmark
Weights: SGOV 0.00% ($0), IEF 40.00% ($40,000,000), USIG 0.00% ($0), VT 60.00% ($60,000,000)
Expected return: 7.02%
Volatility: 10.29%
### Constrained portfolio
Weights: SGOV 0.00% ($0), IEF 10.00% ($10,000,000), USIG 30.00% ($30,000,000), VT 60.00% ($60,000,000)
Expected return: 7.36%
Volatility: 11.23%

## Stress
| case | meets_objective | largest_weight_change | turnover | expected_return_after_cost | trading_cost_dollars |
| --- | --- | --- | --- | --- | --- |
| All monthly returns; SGOV return -1% | True | 0.00% | not applicable | 7.36% | not applicable |
| All monthly returns; SGOV return +1% | True | 0.00% | not applicable | 7.36% | not applicable |
| All monthly returns; IEF return -1% | True | 5.00% | not applicable | 7.37% | not applicable |
| All monthly returns; IEF return +1% | True | 30.00% | not applicable | 7.42% | not applicable |
| All monthly returns; USIG return -1% | False | not applicable | not applicable | not applicable | not applicable |
| All monthly returns; USIG return +1% | True | 5.00% | not applicable | 7.41% | not applicable |
| All monthly returns; VT return -1% | False | not applicable | not applicable | not applicable | not applicable |
| All monthly returns; VT return +1% | True | 20.00% | not applicable | 7.38% | not applicable |
| Last 60 monthly returns | True | 55.00% | not applicable | 7.40% | not applicable |
| Last 36 monthly returns | True | 60.00% | not applicable | 7.43% | not applicable |
| Transaction cost 0 basis points | True | 0.00% | 30.00% | 7.36% | $0 |
| Transaction cost 10 basis points | False | 0.00% | 30.00% | 7.33% | $30,000 |
| Transaction cost 25 basis points | False | 0.00% | 30.00% | 7.29% | $75,000 |
| Transaction cost 50 basis points | False | 0.00% | 30.00% | 7.21% | $150,000 |
| Reserve minimum 10% | True | 0.00% | not applicable | 7.36% | not applicable |
| Reserve minimum 20% | False | not applicable | not applicable | not applicable | not applicable |
| 60% cap off | True | 30.00% | not applicable | 7.38% | not applicable |

## Frontier summary
Mixes evaluated: 1,771
Mixes meeting every mandate rule: 2

## Monte Carlo table
| portfolio | probability objective | probability below $90m | median ending value | 5th percentile | 95th percentile |
| --- | --- | --- | --- | --- | --- |
| Equal weight | 9.67% | 26.22% | $110,895,947 | 83389438.99682342 | 145383703.34197578 |
| 60/40 benchmark | 44.27% | 37.26% | $131,334,489 | 79499392.17171003 | 211650406.8982477 |
| Constrained portfolio | 47.23% | 40.00% | $134,131,071 | 77020910.57408498 | 225045600.94269508 |

## Backtest table
| portfolio | annualized_return | volatility | worst_peak_to_trough_drop | ending_dollar_value | objective_not_reachable_months | average_turnover |
| --- | --- | --- | --- | --- | --- | --- |
| Constrained portfolio | 4.76% | 8.35% | -27.24% | $134,296,207 | 58 | 9.54% |
| Equal weight | 4.32% | 5.28% | -17.78% | $126,112,544 | 0 | 0.66% |
| 60/40 benchmark | 7.08% | 9.10% | -22.99% | $200,614,136 | 0 | 0.80% |
