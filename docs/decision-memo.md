**AI use:** OpenAI Codex (GPT-5.6-Terra) built the analysis engine; Claude built the website and helped plan and check; the analysis and the decision are mine.

**Education, not investment advice.**

# Decision memo: Meridian Foundation

**To:** Meridian Foundation investment committee · **From:** Miles Nine · **Decision date:** September 30, 2026 (data as known on that date)

## Recommendation

**Reject the optimizer. Adopt the Compass app as the committee's testing and monitoring tool, keep it simple, and hold
the 60/40 benchmark within set ranges.**

The optimizer only works on 2 of 1,771 possible mixes. Historically it would have turned $100 million into only
$134 million, while the simple 60/40 split turned it into $201 million. So it makes sense to reject the optimizer.

## The mandate

$100 million, paying $750,000 every quarter, held in four funds: SGOV (Treasury bills), IEF (government bonds),
USIG (corporate bonds) and VT (global stocks). The objective is a return of at least inflation as known plus 4%:
3.35% (the August 2026 Consumer Price Index, first published September 11, 2026) + 4% = **7.35% a year**. The rules
are long-only, no fund above 60%, and at least 3% in SGOV and IEF (one year of payouts). The benchmark is 60% VT and
40% IEF.

## Evidence

| | Equal weight | 60/40 benchmark | Optimizer (constrained) |
|---|---|---|---|
| Mix (SGOV / IEF / USIG / VT) | 25 / 25 / 25 / 25 | 0 / 40 / 0 / 60 | 0 / 10 / 30 / 60 |
| Expected return / volatility | 4.47% / 5.80% | 7.02% / 10.29% | 7.36% / 11.23% |
| Mandate verdict | Fails: return below 7.35% | Fails: return below 7.35% | Passes every rule |
| Chance of averaging 7.35% over 7 years (10,000 simulations) | 9.67% | 44.27% | 47.23% |
| Backtest, July 2011 to September 2026: $100 million became | $126.1 million | **$200.6 million** | $134.3 million |
| Worst drop in the backtest | -17.78% | -22.99% | -27.24% |

What the app found:

1. **The target is barely reachable.** Only 2 of 1,771 mixes meet every rule and the objective.
2. **The optimizer lost in real time.** In a point-in-time backtest that used only data known at each month, the
   optimizer ended $66 million behind the 60/40 benchmark. It also had the deepest drop, and for 58 months no mix
   could meet the objective at all.
3. **It is not stable.** The stop condition triggered. Using a shorter data window moves its mix by 55 to 60
   points, and any trading cost of 10 basis points or more pushes it below the objective.
4. **It breaks under a realistic surprise.** In my Locked Changed-Input Record, lowering VT's expected return by
   2 points left no mix that meets the rules, and the chance of reaching the objective fell from 47.2% to 36.3%.
5. **A stricter forecast points the same way.** The improved forecast draws whole 12-month stretches of history and
   starts from September 2026 yields. With it, the 60/40 has the better poor case after 7 years of payouts ($83.7
   million against $81.2 million at the 10th percentile) and about the same chance of staying above $100 million
   (79.15% against 78.30%).
6. **The committee review agrees.** The Indexer and the Risk Skeptic vote Oppose and the Endowment Builder votes
   Approve with conditions. The outcome is Oppose. The votes come from checks computed by code.

**Honest limit:** the 60/40 benchmark is also expected to fall short of the objective (7.02% against 7.35%). No
simple, stable mix reliably reaches 7.35% with these funds and rules. The optimizer only "passes" on paper, by a
hundredth of a point.

## Material assumptions and sensitivities

- **Expected returns are all-history averages** of monthly returns, July 2008 to September 2026: VT 9.88%, USIG 3.87%,
  IEF 2.73%, SGOV 1.38% a year. Volatility is the risk measure.
- **The objective depends on inflation as known** (3.35%). A higher inflation print raises the 7.35% target one for one.
- **Sensitivities from the stress run:** lowering VT or USIG by 1 point leaves no mix that meets the mandate; using
  only the last 60 or 36 months moves the optimizer's mix by 55 to 60 points; a 10 basis point trading cost pushes it
  below the objective. Lowering VT by 2 points cuts the 60/40's chance of meeting the objective from 44.3% to 32.5%.

## Principal risks and failure conditions (for the 60/40)

- **Return shortfall:** expected 7.02% against the 7.35% objective; a 37.26% chance of dipping below $90 million
  within seven years (10,000 simulations).
- **Market drops:** replaying real crises on this mix gives -26.1% in the 2008 financial crisis, -10.3% in the 2020
  COVID crash and -19.0% in the 2022 rate shock, when stocks and bonds fell together.
- **Inflation:** a high-inflation year hurts both VT and IEF and raises the objective at the same time.
- **Failure condition:** the plan needs a committee review if the portfolio falls below $90 million or if inflation
  moves the objective by more than 1 point (see the triggers below).

## Allocation range

| Fund | Target | Range |
|---|---|---|
| VT (global stocks) | 60% | 55% to 65% |
| IEF (government bonds) | 37% | 32% to 42% |
| SGOV (Treasury bills, payout reserve) | 3% | at least 3% |
| USIG (corporate bonds) | 0% | 0% |

The 3% in SGOV holds one year of payouts in cash, so a payout never forces a sale in a downturn.

## Conditions and triggers

- **Rebalance trigger:** rebalance back to target when VT leaves 55% to 65%, or when SGOV falls below 3%.
- **Monitoring:** re-run Compass every quarter with the newest data, and record the chance of meeting the objective.
- **Review trigger:** call a committee review if inflation as known moves the objective by more than 1 point, or if
  the portfolio falls below $90 million.
- **Reversal trigger:** I would reconsider the optimizer only if it beats the 60/40 benchmark in the backtest *and*
  stops changing its mix so much when the data changes (the stop condition clears).

## Committee ask

1. Approve holding the 60/40 benchmark within the ranges above, and reject the optimizer.
2. Adopt Compass as the quarterly testing and monitoring tool.
3. Decide on the gap. The 60/40 is expected to earn about 0.3 points less than the 7.35% objective. Either accept
   that shortfall, or revisit the 4% real return target or the payout.

*Sources: Yahoo Finance monthly adjusted prices; FRED (Treasury bill rates); ALFRED (Consumer Price Index as known on
each date). Full numbers: `output/visible_output.md` and the app. Validation and AI use:
`docs/validation-and-ai-use.md`.*
