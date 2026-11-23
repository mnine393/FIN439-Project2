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
| case | group | meets_objective | largest_weight_change | turnover | expected_return_after_cost | trading_cost_dollars |
| --- | --- | --- | --- | --- | --- | --- |
| SGOV expected return one point lower | Estimates | True | 0.00% | not applicable | 7.36% | not applicable |
| SGOV expected return one point higher | Estimates | True | 0.00% | not applicable | 7.36% | not applicable |
| IEF expected return one point lower | Estimates | True | 5.00% | not applicable | 7.37% | not applicable |
| IEF expected return one point higher | Estimates | True | 30.00% | not applicable | 7.42% | not applicable |
| USIG expected return one point lower | Estimates | False | not applicable | not applicable | not applicable | not applicable |
| USIG expected return one point higher | Estimates | True | 5.00% | not applicable | 7.41% | not applicable |
| VT expected return one point lower | Estimates | False | not applicable | not applicable | not applicable | not applicable |
| VT expected return one point higher | Estimates | True | 20.00% | not applicable | 7.38% | not applicable |
| Estimate window: last 60 months | Data window | True | 55.00% | not applicable | 7.40% | not applicable |
| Estimate window: last 36 months | Data window | True | 60.00% | not applicable | 7.43% | not applicable |
| Trading cost 0 basis points | Costs | True | 0.00% | 30.00% | 7.36% | $0 |
| Trading cost 10 basis points | Costs | False | 0.00% | 30.00% | 7.33% | $30,000 |
| Trading cost 25 basis points | Costs | False | 0.00% | 30.00% | 7.29% | $75,000 |
| Trading cost 50 basis points | Costs | False | 0.00% | 30.00% | 7.21% | $150,000 |
| Reserve minimum 10% | Rules | True | 0.00% | not applicable | 7.36% | not applicable |
| Reserve minimum 20% | Rules | False | not applicable | not applicable | not applicable | not applicable |
| 60% fund cap removed | Rules | True | 30.00% | not applicable | 7.38% | not applicable |

## Frontier summary
Mixes evaluated: 1,771
Mixes meeting every mandate rule: 2

## Monte Carlo table
| portfolio | probability objective | probability below $90m | median ending value | 5th percentile | 95th percentile |
| --- | --- | --- | --- | --- | --- |
| Equal weight | 9.67% | 26.22% | $110,895,947 | $83,389,439 | $145,383,703 |
| 60/40 benchmark | 44.27% | 37.26% | $131,334,489 | $79,499,392 | $211,650,407 |
| Constrained portfolio | 47.23% | 40.00% | $134,131,071 | $77,020,911 | $225,045,601 |

## Backtest table
| portfolio | annualized_return | volatility | worst_peak_to_trough_drop | ending_dollar_value | objective_not_reachable_months | average_turnover |
| --- | --- | --- | --- | --- | --- | --- |
| Constrained portfolio | 4.76% | 8.35% | -27.24% | $134,296,207 | 58 | 9.54% |
| Equal weight | 4.32% | 5.28% | -17.78% | $126,112,544 | 0 | 0.66% |
| 60/40 benchmark | 7.08% | 9.10% | -22.99% | $200,614,136 | 0 | 0.80% |

## Personal mode example
Example: $40,000 savings, $1,200 monthly contribution, $1,000,000 goal, 30 years, 40% tolerated drop, $3,000 monthly expenses, and six reserve months.
Suggested portfolio: Your plan; expected return 7.90%; volatility 12.26%.
Chance of reaching the goal: 40.54%.
Mix: SGOV 0.00% ($0), IEF 15.00% ($3,300), USIG 15.00% ($3,300), VT 70.00% ($15,400).
Monthly contribution for an 80% chance: $2,025.

## Mandate verdicts
| portfolio | rule | verdict |
| --- | --- | --- |
| Equal weight | Long-only | Pass |
| Equal weight | Weights sum to 100% | Pass |
| Equal weight | At least 3% in SGOV + IEF | Pass |
| Equal weight | No fund above 60% | Pass |
| Equal weight | Return at least inflation plus required return | Fail |
| 60/40 benchmark | Long-only | Pass |
| 60/40 benchmark | Weights sum to 100% | Pass |
| 60/40 benchmark | At least 3% in SGOV + IEF | Pass |
| 60/40 benchmark | No fund above 60% | Pass |
| 60/40 benchmark | Return at least inflation plus required return | Fail |
| Constrained portfolio | Long-only | Pass |
| Constrained portfolio | Weights sum to 100% | Pass |
| Constrained portfolio | At least 3% in SGOV + IEF | Pass |
| Constrained portfolio | No fund above 60% | Pass |
| Constrained portfolio | Return at least inflation plus required return | Pass |

## Stop condition
Triggered: Yes.
Threshold: 20.00% change in any weight.
Stress cases that triggered it: IEF expected return one point higher; USIG expected return one point lower; VT expected return one point lower; VT expected return one point higher; Estimate window: last 60 months; Estimate window: last 36 months; Reserve minimum 20%; 60% fund cap removed

## Committee review
| member | vote | memo source |
| --- | --- | --- |
| Endowment Builder | Approve with conditions | rule-based |
| Indexer | Oppose | rule-based |
| Risk Skeptic | Oppose | rule-based |
Outcome: Oppose.

## Improved forecast (Build G)
Seven-year forecast using a $750,000 quarterly payout (modeled as a $250,000 monthly outflow).
| portfolio | method | expected return | 10th percentile ending value | 50th percentile ending value | 90th percentile ending value | yield dates | chance of ending at or above $100 million |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Constrained portfolio | Contiguous 12-month historical blocks with forward assumptions | 7.28% | $81,187,520 | $134,391,700 | $205,004,616 | TB3MS: 2026-09-30, GS10: 2026-09-30, BAA: 2026-09-30 | 78.30% |
| 60/40 benchmark | Contiguous 12-month historical blocks with forward assumptions | 7.04% | $83,735,681 | $132,335,747 | $195,889,727 | TB3MS: 2026-09-30, GS10: 2026-09-30, BAA: 2026-09-30 | 79.15% |

## Forecast calibration
60/40 benchmark (VT 60%, IEF 40%).
| method | horizon (months) | number of forecasts | share inside the 10th-90th range | below | above | pinball loss |
| --- | --- | --- | --- | --- | --- | --- |
| simple | 12 | 148 | 87.16% | 8.11% | 4.73% | 0.0230 |
| simple | 36 | 124 | 95.97% | 0.00% | 4.03% | 0.0382 |
| improved | 12 | 148 | 83.78% | 7.43% | 8.78% | 0.0223 |
| improved | 36 | 124 | 98.39% | 0.00% | 1.61% | 0.0367 |

## Recommendation
Action: Reject the optimizer; hold the 60/40 benchmark
Allocation range: VT 60% (55% to 65%), IEF 37% (32% to 42%), SGOV at least 3%, USIG 0%
Conditions: Adopt Compass as the committee's quarterly testing and monitoring tool; re-run it every quarter with the newest data
Triggers:
- Rebalance when VT leaves 55% to 65% or SGOV falls below 3%
- Committee review if inflation as known moves the objective by more than 1 point
- Committee review if the portfolio falls below $90 million
- Reconsider the optimizer only if it beats the 60/40 benchmark in the backtest and the stop condition clears
Committee ask: Approve the 60/40 within these ranges, adopt Compass for monitoring, and decide whether to accept the 60/40's expected shortfall of about 0.3 points against the 7.35% objective or revisit the target or the payout
