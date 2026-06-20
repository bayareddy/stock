# ORB Backtest Strategy (5-minute intraday)

This document describes the strategy implemented in `orb_backtester.py` and used by `orb_backtest_fyers.py`.

## 1) Universe / Data
- **Symbol**: any Fyers intraday 5-minute OHLCV feed (example: `NSE:SBIN-EQ`).
- **Timeframe**: 5-minute candles.
- **Input columns** (required): `timestamp`, `open`, `high`, `low`, `close`, `volume`.
- **Timestamp**: converted to pandas datetime and sorted; in `orb_backtest_fyers.py` timestamps are made **naive** before being passed to the backtester.

## 2) Strategy Parameters
From `ORBBacktester.__init__`:
- `opening_start`: **09:15**
- `opening_end`: **09:30** (inclusive)
- `entry_start`: **09:30**
- `entry_end`: **15:00**
- `squareoff_time`: **15:15**
- `rr_ratio`: **2.0**
- `initial_capital`: default **100.0** (used only for equity curve + metrics)

## 3) Core Indicator: Opening Range (OR)
For each trading day:
- Consider only candles in the **opening window**: **09:15 to 09:30 (inclusive)**.
- Compute:
  - **OR_High** = max(`high`) within opening window
  - **OR_Low** = min(`low`) within opening window
  - **OR_Midpoint** = (`OR_High` + `OR_Low`) / 2

These OR values are merged forward so later candles in the same day know the day’s OR_High / OR_Low / OR_Midpoint.

## 4) Entry Criteria
Entries are evaluated on each 5-minute candle from **09:30 to 15:00 (inclusive)**.

### 4.1 Long Entry (BUY)
A long position is opened when:
- `close > OR_High`

Additional constraints:
- At most **one long per day** (`used_long`)
- If a long is already active, no new long is opened

On entry:
- **entry_price** = `close` (current candle close)
- **sl** = `OR_Midpoint`
- **risk** = `entry_price - sl`
- **tp** = `entry_price + risk * rr_ratio`
  - with `rr_ratio=2.0`: TP distance = **2 * risk**

### 4.2 Short Entry (SELL)
A short position is opened when:
- `close < OR_Low`

Additional constraints:
- At most **one short per day** (`used_short`)
- If a short is already active, no new short is opened

On entry:
- **entry_price** = `close`
- **sl** = `OR_Midpoint`
- **risk** = `sl - entry_price`
- **tp** = `entry_price - risk * rr_ratio`

## 5) Exit Criteria
The simulator manages exits candle-by-candle for any active positions.

### 5.1 Intrabar SL/TP (conservative)
For each active position on each 5-minute candle:
- **Long**:
  - SL touched if `low <= sl`
  - TP touched if `high >= tp`
  - If **both** SL and TP are touched in the same candle: **assume SL hit first**.
  - Exit price: `sl` (if SL hit) or `tp` (if TP hit)

- **Short**:
  - SL touched if `high >= sl`
  - TP touched if `low <= tp`
  - If **both** SL and TP are touched in the same candle: **assume SL hit first**.
  - Exit price: `sl` (if SL hit) or `tp` (if TP hit)

### 5.2 Time-based Square-off (EOD in this strategy)
If a position is still active at the candle where:
- `minute == squareoff_m` (i.e., **15:15**)

Then:
- All active positions are closed at that candle’s **close** price (`result='eod'`).

## 6) Trade Handling / Limits
- **No compounding within the day**: equity is updated only on exits; entries are limited by the one-per-side logic.
- You can have **up to one long and one short per day** (because the code prevents multiple entries per side, but does not globally prevent both simultaneously).

## 7) Outputs
`ORBBacktester.run(df)` returns:
- `trades_df`: one row per executed trade.
  - Columns: `date, side, entry_time, exit_time, entry_price, exit_price, sl, tp, pnl, result`
  - `side`: `'long'` or `'short'`
  - `result`: `'tp'`, `'sl'`, or `'eod'`
- `equity_curve`: step-wise equity indexed by timestamps when exits occur.

`orb_backtest_fyers.py` prints trade details (BUY/SELL mapped from `side`) after the run.

## 8) Notes / Caveats
- Breakout conditions use **close price** (`close > OR_High` / `close < OR_Low`), not high/low.
- SL/TP triggering uses **conservative intrabar assumptions** (SL first when both are touched).
- If a day lacks candles in the opening window (09:15–09:30), the backtester will raise an error about missing OR levels.

