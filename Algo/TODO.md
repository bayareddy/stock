- [ ] Add production-ready ORB backtester script using pandas/numpy
- [x] Provide class-based modular implementation with metrics + matplotlib plot (`orb_backtester.py`)
- [ ] Wire ORB backtester to Fyers API (fetch 5-min candles) and run end-to-end (`orb_backtest_fyers.py`)
- [x] Created `orb_backtest_fyers.py` (Fyers fetch + end-to-end runner)
- [x] Implement Fyers order management for ORB strategy (entry LIMIT at candle close + separate SL-M and TP orders) (`orb_order_manager_fyers.py`, `orb_live_runner_fyers.py`)

