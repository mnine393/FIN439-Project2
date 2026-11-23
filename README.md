**AI use:** OpenAI Codex (GPT-5.6-Terra) built the analysis engine; Claude built the website and helped plan and check; the analysis and the decision are mine.

**Education, not investment advice.**

# Compass

**An investment committee in your pocket.** Compass is a point-in-time portfolio engine with a website. It tells an
investment committee how to allocate, how likely the money is to last, and whether the process would actually have
worked in real time.

It has two modes on one engine:

- **Institution mode (the graded mandate):** the $100 million Meridian Foundation reserve, which pays out $750,000
  every quarter and must earn inflation plus 4% a year.
- **Personal mode:** any person's savings plan. Enter savings, a monthly contribution, a goal and the largest one-year
  drop you could live with; Compass writes your rules, picks the lowest-risk mix that can reach the goal, and shows
  your odds.

The universe is four low-cost funds: **SGOV** (Treasury bills, the cash reserve), **IEF** (7-10 year Treasury bonds),
**USIG** (investment-grade corporate bonds) and **VT** (global stocks).

## Legend portfolios

The legend endpoints read public Form 13F filings for Warren Buffett and Michael Burry. A filing reports a manager's
quarter-end holdings but can arrive up to 45 days later, so Compass always uses only the filing that was public on the
requested decision date. The listed weights are disclosures, not current holdings; any screen or analysis uses that
same point-in-time date and does not test today's disclosed weights on earlier years.

## Choose your own funds

The application programming interface also accepts a universe of two to eight Yahoo Finance tickers.  Compass saves
monthly adjusted closes in `data/prices/` so later runs work offline, assigns familiar tickers a fund role, and uses a
five percentage point grid for up to five funds or a ten percentage point grid for six to eight funds.  The original
four-fund universe remains the default and continues to use its historical Treasury bill proxy.

## Run it (one command)

You need Python 3.11 or newer. From this folder:

```bash
python -m pip install -r requirements.txt
python run.py
```

`python run.py` starts Compass and opens **http://127.0.0.1:8000** in your browser. The first institution page takes
about ten seconds while it runs 10,000 simulations and an 18-year backtest; after that it is instant.

Everything needed is saved in `data/`, so it runs **without internet access**. Nothing needs a key or an account.

## Forecast and portfolio analysis application programming interface

The additive endpoints are `POST /api/analyze`, `POST /api/compare`, `POST /api/calibration`, `GET /api/risk-profile/questions`, and `POST /api/risk-profile`. The analyze endpoint accepts holding dollars and optional role names; it returns history, risk contributions, fees, two forecasts, crisis replays, and flags. See `docs/data-card-forecast.md` for sources and limitations.

If `python` is not found on Windows, try `py` instead of `python`. If port 8000 is busy, close the other program or
run `python -m uvicorn server:app --port 8001` and open http://127.0.0.1:8001.

## See the result without running anything

`output/visible_output.md` holds the material inputs, the decision date, the inflation figure as known, the three
portfolios with their mandate verdicts, the stress run, the simulation and the backtest. To regenerate it:

```bash
python run_analysis.py
```

## Check it

```bash
python -m pytest -q
```

The tests pin the hand-checked Meridian results, check that the backtest never uses future data (the look-ahead test),
and cover personal mode, the stress run, the committee votes and the number checker. All tests pass.

## What each page shows

**Personal mode**

| Page | What it shows |
|---|---|
| Home | The plan form |
| Summary | Chance of reaching the goal, the return the plan needs, the monthly contribution for an 80% chance |
| Safety net | The emergency reserve, set aside in cash before anything is invested |
| Allocation | The plan's mix next to two baselines (equal weight and 60/40), each with pass or fail on your rules |
| Will I make it? | 10,000 simulated futures in today's dollars, as a fan chart |
| If you had started | A point-in-time backtest of the plan and both baselines |
| How fragile is this? | The stress run and the stop condition |
| What to do today | Exact buys and sells from what you hold now |
| Policy statement | Your rules, written as an investment policy statement |
| Committee review | Three AI committee members review the plan |

**Institution mode (Meridian Foundation)**

| Page | What it shows |
|---|---|
| Committee summary | The objective, the stop condition, the evidence and the recommendation |
| Mandate and compliance | The rules, and the three portfolios checked against each rule |
| Inflation signal | The Consumer Price Index as known on the decision date, with its data card |
| Efficient frontier | All 1,771 mixes by risk and return; the few that meet every rule |
| Will the money last? | 10,000 seven-year paths with the quarterly payouts; the chance of dipping below $90 million |
| Would it have worked? | The point-in-time backtest, 2011 to 2026 |
| Stress lab | Change the cap, reserve, objective, data window or stop threshold and rerun |
| Locked prediction | The prediction written before the run, beside the result |
| Committee review | Three AI committee members review the optimizer |

## How it works

## Diversify beyond four funds

Custom universes can include from two to fifteen Yahoo Finance tickers, including individual stocks. Compass keeps the
five-percentage-point grid through five holdings and the ten-percentage-point grid through eight; larger universes use
a constrained optimizer, then displays whole-percentage weights. Optional diversification limits cap an individual
stock, all individual stocks together, and require a minimum count of holdings at or above two percent. The default
four-fund universe and its documented results remain unchanged.

1. **Mandate first.** `mandate.py` holds every rule as an editable constant: the objective, the benchmark (60% VT,
   40% IEF), the risk measure, long-only, fully invested, at least 3% in SGOV and IEF (four quarterly payouts), and
   no fund above 60%.
2. **Point-in-time signal.** `cpi_signal.py` reads the Consumer Price Index as it was published on each decision date
   (ALFRED vintages), never today's revised numbers. Inflation as known plus 4% is the return objective.
3. **Estimates.** `data.py` builds monthly total returns from July 2008 to September 2026. Before SGOV existed (mid-2020)
   the 3-month Treasury bill rate stands in for it. See `docs/data-card-prices.md`.
4. **The search.** `mixes.py` and `portfolio.py` evaluate every long-only mix in 5-point steps and pick the
   lowest-volatility mix that meets every rule.
5. **Testing the process.** `simulation.py` (10,000 paths of real historical months), `backtest.py` (each month uses only
   data known that day), and `stress.py` (one change at a time, with a stop condition set before looking at results).
6. **Personal mode.** `personal.py` reuses the same engine with a personal mandate.
7. **The AI committee.** `committee.py` computes every number and every vote in code. The memos are written by
   artificial intelligence from those numbers only, and the app highlights any number in a memo that the code did not
   compute.
8. **The website.** `server.py` serves the results as JSON under `/api`; `web/` is the website.

## Optional: live committee review

The saved committee memos work without any setup. To have Claude write new memos live, install the optional
`anthropic` package (already in `requirements.txt`) and set `ANTHROPIC_API_KEY` in your own environment before starting
Compass. `.env.example` is only a reminder; **never commit a real key**.

## Project documents

- `docs/decision-memo.md`: the recommendation
- `docs/validation-and-ai-use.md`: sources, tests, results, limitations, AI use and the Locked Changed-Input Record
- `docs/data-card.md` and `docs/data-card-prices.md`: the data cards
- `docs/ai-use-log.md`: every AI task, with my check
- `locked_run.py` and `output/locked_run_output.txt`: the locked changed-input run

The earlier Streamlit version of the app (kept to show how the project changed) runs with
`python -m streamlit run legacy/streamlit_app.py`.
