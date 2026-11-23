"""Editable committee recommendation fields (Miles's decision, also in docs/decision-memo.md)."""

ACTION = "Reject the optimizer; hold the 60/40 benchmark"
ALLOCATION_RANGE = "VT 60% (55% to 65%), IEF 37% (32% to 42%), SGOV at least 3%, USIG 0%"
CONDITIONS = ("Adopt Compass as the committee's quarterly testing and monitoring tool; re-run it every quarter "
              "with the newest data")
TRIGGERS = [
    "Rebalance when VT leaves 55% to 65% or SGOV falls below 3%",
    "Committee review if inflation as known moves the objective by more than 1 point",
    "Committee review if the portfolio falls below $90 million",
    "Reconsider the optimizer only if it beats the 60/40 benchmark in the backtest and the stop condition clears",
]
COMMITTEE_ASK = ("Approve the 60/40 within these ranges, adopt Compass for monitoring, and decide whether to accept "
                 "the 60/40's expected shortfall of about 0.3 points against the 7.35% objective or revisit the "
                 "target or the payout")
