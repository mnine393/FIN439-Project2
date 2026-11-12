# AI use log

| Date | Tool | Task | What was produced | My check / Accept-Modify-Reject |
|---|---|---|---|---|
| 2026-11-10 | Codex + GPT-5.6-Terra | Initial FIN 439 Project 2 build | Investment management application, visible output, tests, and documentation | Pending my check |
| 2026-11-12 | Codex + GPT-5.6-Terra | CPI vintage dates, independent stress cases, and dollar amounts | Renamed the CPI module, added cached ALFRED release-date lookup, corrected stress measures, and added dollar displays | Pending my check |
| 2026-11-12 | Codex + GPT-5.6-Terra | Correct stress-cost test expectation | Calculated turnover and trading-cost expectations from the test cost row and 60/40 benchmark weights | Pending my check |
| 2026-11-12 | Codex + GPT-5.6-Terra | Correct stress-cost return expectation | Updated the expected return after cost to subtract the test-computed turnover times 10 basis points | Pending my check |
| 2026-11-12 | Codex + GPT-5.6-Terra | Endowment Command Center analytics engine | Added the longer offline return history, frontier, simulations, point-in-time backtest, tabs, documentation, and tests | Pending my check |
| 2026-11-12 | Claude (Opus 5.5) | Fix the Treasury bill download and fill the backtest inflation cache | FRED dropped requests sent with a browser-style User-Agent, so data.py now sends Python's default one; ran the project's own load_cpi_vintages one date at a time with retries to build data/cpi_vintages.csv | Pending my check |
| 2026-11-12 | Codex + GPT-5.6-Terra | Committee dashboard, display formatting, and fair backtest costs | Added the committee summary and editable recommendation fields, refreshed the dashboard design and visible output formatting, and charged trading costs after monthly weight drift for every strategy | Pending my check |
