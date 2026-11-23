**AI use:** OpenAI Codex (GPT-5.6-Terra) built the analysis engine; Claude built the website and helped plan and check; the analysis and the decision are mine.

**Education, not investment advice.**

# Validation and AI use

Contents: 1. Sources and as-of boundary · 2. Tests · 3. Results · 4. Limitations · 5. AI use · 6. Locked Changed-Input Record

## 1. Sources and as-of boundary

| Data | Source | Coverage | As-of rule |
|---|---|---|---|
| Fund total returns (IEF, USIG, VT, SGOV) | Yahoo Finance monthly adjusted close | July 2008 to September 2026, 219 months | Saved in `data/monthly_returns.csv` (downloaded 2026-11-12) |
| Cash proxy before SGOV existed | FRED, 3-month Treasury bill rate (TB3MS) | July 2008 to June 2020, 144 months | Monthly return = rate / 12 |
| Inflation | ALFRED, Consumer Price Index (CPIAUCSL) vintages | One vintage per decision date | The value as first published on or before the decision date; never today's revised figure |

- **Decision date:** September 30, 2026. Inflation as known: **3.35%** (August 2026, first published September 11, 2026,
  confirmed from ALFRED vintages). Return objective: 3.35% + 4% = **7.35%**.
- **Backtest boundary:** each month-end from June 2011 uses only returns up to that month-end and the Consumer Price Index
  vintage of that date (`data/cpi_vintages.csv`, 183 decision dates).
- Data cards: `docs/data-card.md` (inflation) and `docs/data-card-prices.md` (fund returns).

## 2. Tests

`python -m pytest -q` runs 86 tests; **all 86 pass** (2026-11-23). No test calls an AI service.

| What is tested | How |
|---|---|
| Known answers | The Lab 15 Meridian answer (0/20/25/55, 6.51%, 9.44%) and the Lab 16 as-of table (AAA +1.98%, BBB -1.02%, CCC +0.91%) |
| Regression pins | Every hand-checked foundation number: weights, returns, volatilities, the 2 of 1,771 frontier count, simulation and backtest results |
| No look-ahead | Change every return after a month-end to a wild value; the portfolio chosen at that month-end must not change (institution and personal backtests) |
| Independent check | Personal mode was recomputed in a separate script written from the raw data only; required real return 4.52%, mix 0/15/15/70, chance of the goal 40.54%: all match |
| Mandate verdicts | Equal weight and 60/40 get the right pass or fail per rule; reserve and drop limits bind when they should |
| Stress and stop rule | Each case changes one input; the stop condition triggers on the right cases |
| Committee | Votes follow the checks; the number checker flags an invented "40.0%" and accepts printed numbers |
| Website | Every page loads its scripts and data; the default plan request returns the pinned 40.54% |
| Improved forecast | 12-month blocks stay consecutive; the forecast mean matches the blended assumption; yields dated after the forecast date are never used; a table without dates is refused |
| Accuracy test | Each past forecast uses only returns and yields up to its own date; changing a later return leaves it unchanged |
| Portfolio analyzer | Every section is returned for funds, stocks and mixes with short histories; risk shares add to 100%; crisis replays label estimated holdings |
| Ask Compass | A fake AI client proves the tools run the real engine, invented numbers are flagged, and the free built-in mode answers what-ifs with checked numbers |

## 3. Results (institution mode, decision date September 30, 2026)

| Portfolio | Mix (SGOV/IEF/USIG/VT) | Expected return | Mandate verdict |
|---|---|---|---|
| Equal weight | 25/25/25/25 | 4.47% | Fails: return below the 7.35% objective |
| 60/40 benchmark | 0/40/0/60 | 7.02% | Fails: return below the 7.35% objective |
| Constrained portfolio (the optimizer) | 0/10/30/60 | 7.36% | Passes every rule |

- **Frontier:** only 2 of 1,771 long-only mixes meet every rule.
- **Will the money last** (10,000 paths, seven years, $750,000 paid each quarter): the optimizer has a 47.23% chance of
  meeting the objective and a 40.00% chance of dipping below $90 million (60/40: 44.27% and 37.26%).
- **Would it have worked** (point-in-time, July 2011 to September 2026): $100 million became $134.3 million under the
  optimizer, against $200.6 million for the 60/40 benchmark; worst drop -27.24% against -22.99%; the objective was out of
  reach in 58 of 183 months.
- **Stress run:** the stop condition is **triggered**. Eight single changes move a weight by more than 20 points or leave no
  mix: VT one point lower and USIG one point lower leave no mix; the last 60 or 36 months move weights by 55 and 60
  points; a 10 basis point trading cost already drops the optimizer below the objective.
- **AI committee:** Endowment Builder approve with conditions; Indexer oppose; Risk Skeptic oppose. Outcome: **Oppose**.
- **Improved forecast** (12-month blocks of history, September 2026 yields, uncertain averages; seven years with
  payouts): 60/40 benchmark 10th percentile $83.7 million, median $132.3 million; optimizer $81.2 million and
  $134.4 million. Chance of ending at or above $100 million: 79.15% against 78.30%.
- **Forecast accuracy** (60/40, 148 one-year forecasts made with only the data known at the time): the improved
  method's 80% range caught 83.78% of real outcomes (the simple method: 87.16%), with a lower error score (0.0223
  against 0.0230). At three years both ranges are too wide (98.39% and 95.97% caught).
- Full detail: `output/visible_output.md`.

## 4. Limitations

- **Short and unusual history.** 18 years includes 2008, near-zero rates until 2022 and the 2022 bond crash. Expected
  returns estimated from it are noisy; the stress run shows the answer is sensitive to them.
- **Cash proxy.** Before mid-2020, SGOV is replaced by the Treasury bill rate, which ignores small fund costs.
- **Adjusted prices are not strictly point-in-time.** Yahoo recalculates adjusted prices after later dividends; the
  effect on monthly total returns is small but not zero.
- **Mean-variance with 5-point steps.** Volatility is the risk measure, and the grid cannot pick weights between steps.
- **Simulation assumes the future resembles past months.** The original bootstrap draws real historical months
  independently. The improved forecast draws 12-month stretches and starts from today's yields, but it still cannot
  produce a regime longer than history shows, such as a decade of high inflation.
- **Forward-looking assumptions are simple.** Stocks are assumed to earn the bill yield plus beta times a 4.5% equity
  risk premium, a common long-run assumption, not a measured fact. The three-year forecast ranges are too wide.
- **Four funds only.** No real estate, commodities or inflation-protected bonds; a next version would add an
  inflation-protected bond fund, since the objective is tied to inflation.
- **Taxes are ignored,** and trading costs are a flat basis-point charge.
- **Personal mode is an illustration** for one example person; it is not advice for anyone.

## 5. AI use

| Tool and version | Dates | What it did | My check |
|---|---|---|---|
| OpenAI Codex CLI 0.167.0, model GPT-5.6-Terra | 2026-11-10 to 2026-11-17 | Wrote the analysis engine: mandate, inflation signal, data, search, frontier, simulation, backtest, stress run, personal mode, committee checks and votes, the JSON service, and the tests | Every result rerun on my machine; tests run (Codex could not run Python here); personal mode checked against an independent calculation; several bugs found and sent back (see the log) |
| OpenAI Codex CLI 0.167.0, model GPT-5.6-Terra | 2026-11-18 to 2026-11-23 | Builds F to L: any-ticker plans, the improved forecast, the accuracy test, crisis replays, the portfolio analyzer, the risk quiz, and the decision in the visible output | Every build's tests run by me and Claude; four builds came back with bugs (below) and were sent back |
| OpenAI Codex CLI 0.167.0, model GPT-5.6-Terra | 2026-11-17 | Wrote the six saved committee memos from the code-generated fact sheets | The number checker found no invented numbers; one sentence that compared the return with the 4% spread instead of the 7.35% objective was corrected |
| Claude (Anthropic, Claude Code desktop app; Claude Opus 5.5 and Claude Fable 5.2) | 2026-11-10 to 2026-11-23 | Planned the project, wrote the build instructions for Codex, checked every number, fixed small bugs it found, built the website under `web/` and the Ask Compass assistant (`assistant.py`, `assistant_offline.py`), and drafted this record, the README and the memo layout | I reviewed the site and these documents; the decision and the locked prediction are mine |

Material errors the AI made and how they were caught:

1. Codex named a file `signal.py`, which hid Python's own `signal` module and crashed the app; found by running it.
2. Codex invented the inflation publication date (month end plus 14 days); replaced with the real ALFRED date
   (September 11, not September 14).
3. The transaction-cost stress measured turnover against the portfolio itself, so costs never mattered; fixed to
   measure from the 60/40 benchmark, which revealed that a 10 basis point cost breaks the objective.
4. The first backtest charged costs only to the optimizer; fixed so every strategy pays for its rebalancing.
5. Personal mode first forced 72% of the portfolio into cash forever and took 104 seconds; redesigned so the emergency
   reserve is set aside first, and sped up to about 2 seconds.
6. The first website parsed "$1.0 million" as $1 and reported a 100% chance of reaching the goal; caught on screen.
7. The optimizer for 9 to 15 holdings took two minutes and wrongly said no mix existed; a separate check showed a
   10.6% return was possible. It was rewritten to take about 6 seconds and find the mix.
8. The first improved-forecast build crashed on every custom portfolio (a date conversion error) and would have
   downloaded interest rates hundreds of times per accuracy test; caught by running the tests, sent back.
9. Crisis replays crashed for any stocks that did not exist in 2008; fixed to estimate them from the market and label
   them as estimated.
10. A later fix broke the analyzer for every portfolio holding VT or IEF. I saw it in the app ("things in the analyze
    tab don't work") while it was also being traced in testing; the cause was data stored where pandas compares it.
11. **The improved forecast silently used interest rates from January 1970.** A return table reached the forecast without
    its dates, and the code treated it as starting in 1970, so bond forecasts were about 7.8% instead of about 5% on the
    Institution page and in the visible output. It did not crash; it gave wrong numbers. It was caught because the
    yield dates printed as 1970. The code now refuses undated data, and the output prints the yield dates used.
12. Two numbers in the visible output were off: the personal example printed dollars on a $100 million base, and two
    columns printed raw unformatted numbers. Both fixed.

The full task-by-task record is `docs/ai-use-log.md`.

## 6. Locked Changed-Input Record

### Before the run (AI-off prediction, locked)

- **Locked:** 2026-11-12 15:48 (Eastern), committed to GitHub before any run with the changed input.
- **Changed input:** VT (global stocks) expected annual return.
- **Old value:** 9.88% a year (all-history estimate from monthly returns, July 2008 to September 2026).
- **New value:** 7.88% a year (2 percentage points lower). Every other input unchanged: decision date 2026-09-30, CPI as known 3.35%, objective 7.35%, all mandate limits.
- **My prediction, written by me without AI, exactly as written:**

> If VT's expected return drops 2 points, I predict the portfolio mix will go down %. The chance of hitting the goal will go down by about 8%. And my recommendation will change because VT is the biggest percentage of my portfolio.

- **Expected direction:** VT's weight down; the chance of hitting the goal down by about 8 percentage points; the recommendation changes.

### After the run

Run with `python locked_run.py` after the prediction was committed (commit `c0e9dda`, 2026-11-12 15:48); output saved in
`output/locked_run_output.txt` and reproduced exactly on 2026-11-17.

| | Before (VT 9.88%) | After (VT 7.88%) | Predicted |
|---|---|---|---|
| Optimizer's mix | SGOV 0 / IEF 10 / USIG 30 / VT 60 | **No mix meets the mandate** | VT weight goes down |
| Chance of meeting the objective (the original mix held) | 47.2% | 36.3% (**-10.9 points**) | Down about 8 points |
| Chance of dipping below $90 million (same mix) | 40.0% | 46.9% | Not predicted |
| Median value after seven years (same mix) | $134.1 million | $122.4 million | Not predicted |
| 60/40 benchmark, chance of meeting the objective | 44.3% | 32.5% | Not predicted |

- **Direction:** as expected, everything got worse, and the chance of meeting the objective fell by about as much as
  predicted (10.9 points against about 8).
- **Where the prediction was wrong:** I expected the mix to shift away from VT. Instead the optimizer found no mix at all.

**Effect on my decision (my words):** It made me more sure about rejecting. I had guessed the chance of hitting the
target would drop and that money would move out of VT, but it did more than that: it couldn't even find a mix that
followed the rules and hit 7.35%, and the chance dropped by just under 11 points (47.2% to 36.3%). If stocks do just a
little worse than expected, it completely breaks the optimizer, and a process with that little room for error isn't
something a foundation should rely on. So it didn't change my mind; it confirmed it.

**Why my prediction was off (my words):** The problem was that no fund can be more than 60% of the portfolio. The best
mix I could build was about 60% VT with the rest spread across the other funds, which got to roughly 7.4%, just above
the 7.35% target. That's why only 2 of the mixes worked. After the test dropped VT's expected return, the best we
could get was about 6.3%, way short of 7.35%. So the optimizer couldn't just shift the mix: to make up for VT earning
less it would need more VT, but VT is capped at 60%, and the other 40% has to go to funds that earn way less, so they
can't make up the gap. Even the best possible mix falls short. My guess was off because I thought it would just lower
the chance, but instead it made the optimizer stop working, because no mix works.
