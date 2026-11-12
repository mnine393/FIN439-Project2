# Data card: monthly fund total returns

- Sources: [Yahoo Finance](https://finance.yahoo.com/) monthly adjusted close prices for [SGOV](https://finance.yahoo.com/quote/SGOV), [IEF](https://finance.yahoo.com/quote/IEF), [USIG](https://finance.yahoo.com/quote/USIG), and [VT](https://finance.yahoo.com/quote/VT); and the Federal Reserve Bank of St. Louis [three-month Treasury bill rate](https://fred.stlouisfed.org/graph/fredgraph.csv?id=TB3MS).
- Funds: SGOV is a short United States Treasury bill fund; IEF holds intermediate United States Treasury bonds; USIG holds investment-grade United States corporate bonds; VT holds global stocks.
- Method: adjusted close changes are monthly total returns, including reinvested dividends. The saved file covers July 2008 through September 2026. Download date: 2026-11-12 when created or refreshed by this project.
- SGOV proxy: SGOV began in 2020. Before its first full month, cash return is that month’s annual three-month Treasury bill rate divided by 12 and by 100. The file labels every month as either `SGOV actual` or `Treasury bill proxy`.
- Why the proxy is used: it supplies a reasonable cash-like return for the earlier history instead of pretending SGOV existed then.
- Known limits: Yahoo adjusted prices can be recalculated after later dividend events, so they are not strictly point-in-time. The Treasury bill proxy ignores small differences between the quoted rate and SGOV’s realized return.
