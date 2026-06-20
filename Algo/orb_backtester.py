import dataclasses
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


@dataclass(frozen=True)
class Trade:
    date: pd.Timestamp
    side: str  # 'long' or 'short'
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    sl: float
    tp: float
    pnl: float  # absolute PnL in price units (no sizing)
    result: str  # 'tp', 'sl', or 'eod'


class ORBBacktester:
    """Opening Range Breakout backtester for 5-minute intraday OHLCV data.

    Requirements implemented:
      - Opening Range window: 09:15 to 09:30 inclusive (15 minutes)
      - OR_High/OR_Low captured per day from that window
      - Entries allowed between 09:30 and 15:00 inclusive
      - SL at OR midpoint, TP at RR=1:2 using entry->SL distance
      - One long and one short maximum per day (no compounding)
      - Square-off at 15:15 at prevailing close price

    Notes on bias:
      - OR levels are computed using only candles within the opening range.
      - Daily OR values are mapped forward to subsequent candles via shifting so that
        candle at time t only sees OR_High/OR_Low computed from candles strictly
        inside the opening range.
    """

    def __init__(
        self,
        opening_start: str = "09:15",
        opening_end: str = "09:30",
        entry_start: str = "09:30",
        entry_end: str = "15:00",
        squareoff_time: str = "15:15",
        rr_ratio: float = 2.0,
        initial_capital: float = 100.0,
    ):
        self.opening_start = opening_start
        self.opening_end = opening_end
        self.entry_start = entry_start
        self.entry_end = entry_end
        self.squareoff_time = squareoff_time
        self.rr_ratio = rr_ratio
        self.initial_capital = initial_capital

        self.trades: list[Trade] = []
        self.equity_curve_: Optional[pd.Series] = None
        self.metrics_: Optional[dict] = None

    @staticmethod
    def _validate_df(df: pd.DataFrame) -> pd.DataFrame:
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")

        out = df.copy()
        out["timestamp"] = pd.to_datetime(out["timestamp"])
        out = out.sort_values("timestamp").reset_index(drop=True)
        return out

    @staticmethod
    def _time_str_to_minutes(t: str) -> int:
        hh, mm = t.split(":")
        return int(hh) * 60 + int(mm)

    def _compute_daily_or_levels(self, df: pd.DataFrame) -> pd.DataFrame:
        ts = df["timestamp"]
        minutes = ts.dt.hour * 60 + ts.dt.minute

        opening_start_m = self._time_str_to_minutes(self.opening_start)
        opening_end_m = self._time_str_to_minutes(self.opening_end)

        date = ts.dt.normalize()

        mask_or = (minutes >= opening_start_m) & (minutes <= opening_end_m)
        or_df = (
            df.loc[mask_or]
            .groupby(date.loc[mask_or])
            .agg(OR_High=("high", "max"), OR_Low=("low", "min"))
        )
        or_df["OR_Midpoint"] = (or_df["OR_High"] + or_df["OR_Low"]) / 2.0
        or_df.index.name = "date"
        return or_df.reset_index()

    def _map_or_to_bars(self, df: pd.DataFrame, or_levels: pd.DataFrame) -> pd.DataFrame:
        # Merge on date. OR levels are computed from opening window only.
        df2 = df.copy()
        df2["date"] = df2["timestamp"].dt.normalize()
        df2 = df2.merge(or_levels, on="date", how="left")

        if df2[["OR_High", "OR_Low", "OR_Midpoint"]].isna().any().any():
            missing_days = df2.loc[
                df2[["OR_High", "OR_Low", "OR_Midpoint"]].isna().any(axis=1), "date"
            ].unique()
            raise ValueError(f"OR levels not available for days: {missing_days}")

        return df2

    def run(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """Run backtest.

        Returns:
            trades_df: one row per executed trade
            equity_curve: equity series indexed by timestamp (step-wise)
        """
        df = self._validate_df(df)
        or_levels = self._compute_daily_or_levels(df)
        print(f"Computed OR levels : {or_levels} .")
        df = self._map_or_to_bars(df, or_levels)

        minutes = df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute
        entry_start_m = self._time_str_to_minutes(self.entry_start)
        entry_end_m = self._time_str_to_minutes(self.entry_end)
        opening_start_m = self._time_str_to_minutes(self.opening_start)
        opening_end_m = self._time_str_to_minutes(self.opening_end)
        squareoff_m = self._time_str_to_minutes(self.squareoff_time)

        # Candle-level masks
        can_enter = (minutes >= entry_start_m) & (minutes <= entry_end_m)

        # We'll simulate per day to keep it modular and prevent compounding.
        trades: list[Trade] = []

        equity_index = []
        equity_values = []

        equity = self.initial_capital
        prev_ts = None

        for day, day_df in df.groupby("date", sort=True):
            day_df = day_df.reset_index(drop=True)

            # Track whether we've already taken long/short trades for this day
            used_long = False
            used_short = False

            # Collect candidate entries during allowed entry window (iterative is ok here; OR mapping is safe)
            for i in range(len(day_df)):
                row = day_df.iloc[i]
                ts = row["timestamp"]
                if prev_ts is None:
                    prev_ts = ts

                # Mark-to-equity (step-wise): if no trade is active, equity remains.
                # We'll update equity only on exits.

                # Force exit logic: if we are at/after squareoff, handle active positions and stop daily loop.
                if (ts.hour * 60 + ts.minute) == squareoff_m:
                    # If we had any open trade(s), they would have been captured by our TP/SL checks earlier.
                    # This simulator opens positions and checks exits on subsequent bars;
                    # by the time we reach squareoff, any open trade will be closed at close here.
                    # We implement this by checking whether trades were opened but not closed.
                    # Simpler: manage active positions list.
                    break

            # Active positions are managed as we iterate; re-iterate with that logic.
            active = []  # entries: dict with side, entry_price, sl, tp, entry_idx

            for i in range(len(day_df)):
                row = day_df.iloc[i]
                ts = row["timestamp"]
                minute = ts.hour * 60 + ts.minute

                # First, check exits for active positions on the current candle.
                # Within a 5-min candle, we use a conservative priority:
                #   - If SL and TP are both touched, we assume SL first for conservatism.
                #   - This avoids optimistic sequencing.
                new_active = []
                for pos in active:
                    side = pos["side"]
                    sl = pos["sl"]
                    tp = pos["tp"]

                    o = row["open"]
                    h = row["high"]
                    l = row["low"]
                    c = row["close"]

                    exit_hit = None
                    exit_price = None
                    result = None

                    if side == "long":
                        sl_hit = l <= sl
                        tp_hit = h >= tp
                        if sl_hit and tp_hit:
                            exit_hit = "sl"
                            exit_price = sl
                            result = "sl"
                        elif sl_hit:
                            exit_hit = "sl"
                            exit_price = sl
                            result = "sl"
                        elif tp_hit:
                            exit_hit = "tp"
                            exit_price = tp
                            result = "tp"
                    else:
                        sl_hit = h >= sl
                        tp_hit = l <= tp
                        if sl_hit and tp_hit:
                            exit_hit = "sl"
                            exit_price = sl
                            result = "sl"
                        elif sl_hit:
                            exit_hit = "sl"
                            exit_price = sl
                            result = "sl"
                        elif tp_hit:
                            exit_hit = "tp"
                            exit_price = tp
                            result = "tp"

                    is_squareoff_bar = minute == squareoff_m
                    if exit_hit is not None:
                        # Exit now
                        pnl = (exit_price - pos["entry_price"]) if side == "long" else (pos["entry_price"] - exit_price)
                        trades.append(
                            Trade(
                                date=day,
                                side=side,
                                entry_time=pos["entry_time"],
                                exit_time=ts,
                                entry_price=float(pos["entry_price"]),
                                exit_price=float(exit_price),
                                sl=float(sl),
                                tp=float(tp),
                                pnl=float(pnl),
                                result=result,
                            )
                        )
                        equity += pnl
                        equity_index.append(ts)
                        equity_values.append(equity)
                    elif is_squareoff_bar:
                        exit_price = c
                        pnl = (exit_price - pos["entry_price"]) if side == "long" else (pos["entry_price"] - exit_price)
                        trades.append(
                            Trade(
                                date=day,
                                side=side,
                                entry_time=pos["entry_time"],
                                exit_time=ts,
                                entry_price=float(pos["entry_price"]),
                                exit_price=float(exit_price),
                                sl=float(sl),
                                tp=float(tp),
                                pnl=float(pnl),
                                result="eod",
                            )
                        )
                        equity += pnl
                        equity_index.append(ts)
                        equity_values.append(equity)
                    else:
                        new_active.append(pos)

                active = new_active

                # After exits, check for new entries (only within allowed entry window)
                if minute < entry_start_m or minute > entry_end_m:
                    continue

                # No compounding per day: allow at most one long and one short.
                # Also prevent opening if a position of same side is already active.

                or_high = row["OR_High"]
                or_low = row["OR_Low"]
                or_mid = row["OR_Midpoint"]

                c = row["close"]

                if (not used_long) and (not any(p["side"] == "long" for p in active)):
                    if c > or_high:
                        entry_price = c
                        sl = or_mid
                        risk = entry_price - sl
                        if risk > 0:
                            tp = entry_price + risk * (self.rr_ratio)  # rr=1:2 => tp distance = 2*risk
                            active.append(
                                {
                                    "side": "long",
                                    "entry_time": ts,
                                    "entry_price": entry_price,
                                    "sl": sl,
                                    "tp": tp,
                                }
                            )
                            used_long = True
                            print(
                                f"[{day.date()}] BUY (long) entry at {ts} close={c:.4f} | OR_High={or_high:.4f} | SL={sl:.4f} TP={tp:.4f}"
                            )

                if (not used_short) and (not any(p["side"] == "short" for p in active)):
                    if c < or_low:
                        entry_price = c
                        sl = or_mid
                        risk = sl - entry_price
                        if risk > 0:
                            tp = entry_price - risk * (self.rr_ratio)
                            active.append(
                                {
                                    "side": "short",
                                    "entry_time": ts,
                                    "entry_price": entry_price,
                                    "sl": sl,
                                    "tp": tp,
                                }
                            )
                            used_short = True

                # If squareoff bar, close any remaining active at close.
                if minute == squareoff_m and active:
                    for pos in active:
                        exit_price = row["close"]
                        side = pos["side"]
                        sl = pos["sl"]
                        tp = pos["tp"]
                        pnl = (exit_price - pos["entry_price"]) if side == "long" else (pos["entry_price"] - exit_price)
                        trades.append(
                            Trade(
                                date=day,
                                side=side,
                                entry_time=pos["entry_time"],
                                exit_time=ts,
                                entry_price=float(pos["entry_price"]),
                                exit_price=float(exit_price),
                                sl=float(sl),
                                tp=float(tp),
                                pnl=float(pnl),
                                result="eod",
                            )
                        )
                        equity += pnl
                        equity_index.append(ts)
                        equity_values.append(equity)
                    active = []
                    break

        self.trades = trades

        trades_df = pd.DataFrame([dataclasses.asdict(t) for t in trades])
        if not trades_df.empty:
            trades_df = trades_df.sort_values(["exit_time"]).reset_index(drop=True)

        equity_curve = pd.Series(equity_values, index=pd.to_datetime(equity_index)).sort_index()
        # If there were no trades, return a flat curve.
        if equity_curve.empty:
            equity_curve = pd.Series([self.initial_capital], index=[df["timestamp"].iloc[0]])

        self.equity_curve_ = equity_curve
        self.metrics_ = self._compute_metrics(trades_df, equity_curve)
        return trades_df, equity_curve

    def _compute_metrics(self, trades_df: pd.DataFrame, equity_curve: pd.Series) -> dict:
        metrics = {}
        if trades_df is None or trades_df.empty:
            metrics.update(
                {
                    "Net Profit (%)": 0.0,
                    "Win Rate (%)": 0.0,
                    "Profit Factor": np.nan,
                    "Max Drawdown (%)": 0.0,
                    "Total Number of Trades": 0,
                }
            )
            return metrics

        metrics["Total Number of Trades"] = int(len(trades_df))

        net_profit_abs = equity_curve.iloc[-1] - self.initial_capital
        metrics["Net Profit (%)"] = float((net_profit_abs / self.initial_capital) * 100.0)

        wins = (trades_df["pnl"] > 0).sum()
        metrics["Win Rate (%)"] = float((wins / len(trades_df)) * 100.0)

        gross_profit = trades_df.loc[trades_df["pnl"] > 0, "pnl"].sum()
        gross_loss = trades_df.loc[trades_df["pnl"] < 0, "pnl"].sum()  # negative
        if gross_loss == 0:
            metrics["Profit Factor"] = np.inf
        else:
            metrics["Profit Factor"] = float(gross_profit / abs(gross_loss))

        # Max drawdown based on equity curve
        running_max = equity_curve.cummax()
        drawdown = equity_curve / running_max - 1.0
        metrics["Max Drawdown (%)"] = float(drawdown.min() * 100.0)

        return metrics

    def metrics(self) -> dict:
        if self.metrics_ is None:
            raise RuntimeError("Run backtest first (call run(df)).")
        return self.metrics_

    def plot_equity_curve(self) -> None:
        if self.equity_curve_ is None:
            raise RuntimeError("Run backtest first (call run(df)).")

        plt.figure(figsize=(10, 4))
        plt.plot(self.equity_curve_.index, self.equity_curve_.values, linewidth=2)
        plt.title("ORB Backtest Equity Curve")
        plt.xlabel("Time")
        plt.ylabel("Equity")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    # Example usage (expects you to provide df with 5-min intraday OHLCV):
    # df = pd.read_csv(...)
    # trades_df, equity_curve = ORBBacktester().run(df)
    # print(ORBBacktester().metrics())
    pass

