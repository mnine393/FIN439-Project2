AI use: built with OpenAI Codex (GPT-5.6-Terra) for the code and Claude for planning and checking; the analysis and the decision are mine.

Education, not investment advice.

# FIN 439 Project 2

This application is an Endowment Command Center for a $100 million foundation. It keeps monthly returns locally after the first download, uses Consumer Price Index information that was known at each decision date, checks the mandate, and makes no claim to provide investment advice.

The tabs show the mandate verdicts, the inflation signal, the three portfolios, stress results, the efficient frontier, seven-year “Will the money last?” simulations, and the expanding-window “Would it have worked?” backtest. The market-return source is Yahoo Finance adjusted close data for SGOV, IEF, USIG, and VT, with the three-month Treasury bill rate from the Federal Reserve Bank of St. Louis as the pre-SGOV cash proxy. The inflation source is ALFRED Consumer Price Index vintages. See `docs/data-card-prices.md` and `docs/data-card.md` for limits and links.

## Dashboard tabs

- Committee summary: committee-ready metrics, evidence, stop-condition status, and undecided recommendation fields.
- Mandate: the investment rules and their current pass or fail results.
- Signal: Consumer Price Index information available on the decision date and data-source notes.
- Portfolios: weights, return and risk estimates, and mandate results for each portfolio.
- Stress: independent adverse cases and the stop-rule result.
- Frontier: every tested long-only mix by expected return and risk.
- Will the money last?: seven-year simulated portfolio values and objective probabilities.
- Would it have worked?: expanding-window historical performance after payouts and trading costs.

## Setup

`python -m pip install -r requirements.txt`

Run the application:

`python -m streamlit run app.py`

Write reviewer-visible output:

`python run_analysis.py`

Run tests:

`python -m pytest -q`
