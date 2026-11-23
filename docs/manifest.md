**AI use:** OpenAI Codex (GPT-5.6-Terra) built the analysis engine; Claude built the website and helped plan and check; the analysis and the decision are mine.

**Education, not investment advice.**

# Project 2 submission manifest: Compass (Miles Nine)

**Decision:** reject the optimizer; hold the 60/40 benchmark within ranges (VT 55% to 65%, IEF 32% to 42%, SGOV at least
3%); adopt Compass as the committee's quarterly testing and monitoring tool. Data as of September 30, 2026.

| # | Item | Location | Notes |
|---|---|---|---|
| 1 | GitHub repository | https://github.com/mnine393/FIN439-Project2 | Public: no access request needed. Start with `python run.py` (see README). |
| 2 | Research evolution (Editions A and B) | Not required | Project 2 has no editions (course ruling 2026-10-14). |
| 3 | Decision memo | https://github.com/mnine393/FIN439-Project2/blob/main/docs/decision-memo.md | Also attached in Brightspace |
| 4 | Validation and AI use, with the Locked Changed-Input Record | https://github.com/mnine393/FIN439-Project2/blob/main/docs/validation-and-ai-use.md | Also attached in Brightspace. Prediction commit `c0e9dda` (2026-11-12), before the run |
| 5 | Visible executed output | https://github.com/mnine393/FIN439-Project2/blob/main/output/visible_output.md | Material inputs, as-of date, results and the decision, without running code. Locked run: `output/locked_run_output.txt` |
| 6 | Video 1: How my thinking changed | https://youtu.be/gk8MM6TMAbg | YouTube, Unlisted · 2:50 |
| 7 | Video 1 transcript | https://github.com/mnine393/FIN439-Project2/blob/main/docs/transcript-video-1.txt | Corrected |
| 8 | Video 2: Code walkthrough | https://youtu.be/rx07mjb-1vc | YouTube, Unlisted · 4:41 |
| 9 | Video 2 transcript | https://github.com/mnine393/FIN439-Project2/blob/main/docs/transcript-video-2.txt | Corrected |
| 10 | Video 3: Committee presentation | https://youtu.be/mapiTfLlAOY | YouTube, Unlisted · 4:38 |
| 11 | Video 3 transcript | https://github.com/mnine393/FIN439-Project2/blob/main/docs/transcript-video-3.txt | Corrected |
| 12 | Deployed output (optional) | None | Runs locally with `python run.py`; no deployment |

**Access confirmation:** the repository is public, and all three videos are Unlisted and play while logged out (checked
2026-11-23).

## Timestamp evidence index

### Video 1: How my thinking changed (2:50)
| Time | Required element |
|---|---|
| 0:00 | Two statements: which AI was used and for what, the analysis and decision are mine; education, not investment advice |
| 0:19 | Where the system and my thinking started: the mandate and the optimizer |
| 0:49 | What changed and what drove it: my own testing, not the AI (2 of 1,771 mixes; $134 million against $201 million) |
| 1:23 | Locked prediction result: no mix worked |
| 1:38 | Why the evidence was enough: three different tests agreed; the change from building an optimizer to building a tool that tests one |
| 1:55 | AI output checked: the improved forecast used 1970 interest rates. Disposition: corrected (code refuses undated data and prints the dates used) |
| 2:36 | Resulting decision |

### Video 2: Code walkthrough (4:41)
| Time | Required element |
|---|---|
| 0:00 | Two statements |
| 0:19 | Architecture and data flow |
| 0:41 | How to reproduce the output (`python run_analysis.py`, `python run.py`) |
| 0:58 | Mandate rules in code (`mandate.py`) |
| 1:28 | Point-in-time inflation signal (`cpi_signal.py`, ALFRED) |
| 1:57 | Optimizer grid and point-in-time backtest, with the no-look-ahead test (`portfolio.py`, `backtest.py`) |
| 2:42 | Stress run and stop condition (`stress.py`) |
| 3:02 | Changed-input test of the highest-risk claim, run live (`python locked_run.py`) |
| 3:53 | Improved forecast and the 1970-date fix (`forecast.py`) |
| 4:15 | Limitations: three-year forecast ranges too wide; 18 years of data |
| 4:24 | Validation summary: 86 tests; every number from code |

### Video 3: Committee presentation (4:38)
| Time | Required element |
|---|---|
| 0:00 | Opens with the app running live; two statements |
| 0:19 | Decision first |
| 0:34 | Mandate and objective |
| 1:02 | Evidence: frontier, backtest, stop condition, locked prediction, committee vote |
| 2:00 | Material assumptions and sensitivity |
| 2:13 | Risks of the recommended 60/40 |
| 2:40 | Allocation range |
| 2:58 | Rebalance, review and reversal triggers |
| 3:18 | Why adopt the app (live Analyze demonstration) |
| 3:59 | Committee ask |

## Frozen files
`docs/decision-memo.md`, `docs/validation-and-ai-use.md`, `docs/transcript-video-1.txt`, `docs/transcript-video-2.txt`,
`docs/transcript-video-3.txt` (attached in Brightspace; identical to the repository copies at submission).
