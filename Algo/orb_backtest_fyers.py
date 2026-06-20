"""End-to-end ORB backtest runner using Fyers intraday data.

- Reads access_token from your existing MySQL table (fyres_broker_details)
  and uses the existing Fyers client_id/secret details hardcoded in the repo.
- Fetches 5-minute candles via fyers.history()
- Converts returned candles into the df schema expected by ORBBacktester:
    ['timestamp','open','high','low','close','volume']

This script is intentionally modular and production-safe: it validates schema,
handles empty/no-data cases, and cleanly separates fetching from backtesting.

NOTE:
- Requires `fyers_apiv3`, `mysql-connector-python`, `pandas`, `numpy`, `matplotlib`.
- You must have a valid access_token stored in `fyres_broker_details`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

import mysql.connector
import pandas as pd

from orb_backtester import ORBBacktester


# Keep consistent with repo's existing hardcoded values
FYERS_CLIENT_ID = "Z4O9BSFX7K-100"
FYERS_SECRET_KEY = "4YW3EMFX5U"  # not used for history calls; kept for completeness
FYERS_REDIRECT_URI = "https://www.google.com/"

TABLE_NAME = "fyres_broker_details"


@dataclass(frozen=True)
class DBConfig:
    host: str = "193.203.184.80"
    user: str = "u679206380_trade"
    password: str = "Stockt@27"
    database: str = "u679206380_trade"


def _get_access_token(db: DBConfig, client_id: str) -> str:
    cnx = None
    cursor = None
    try:
        cnx = mysql.connector.connect(
            host=db.host,
            user=db.user,
            password=db.password,
            database=db.database,
        )
        cursor = cnx.cursor()
        cursor.execute(
            f"SELECT access_token FROM {TABLE_NAME} WHERE client_id=%s LIMIT 1",
            (client_id,),
        )
        row = cursor.fetchone()
        if not row or not row[0]:
            raise RuntimeError(
                f"No access_token found for client_id={client_id} in table `{TABLE_NAME}`"
            )
        return str(row[0]).strip()
    finally:
        if cursor is not None:
            cursor.close()
        if cnx is not None:
            cnx.close()


def _make_fyers(access_token: str):
    # Import locally so script can be imported without Fyers dependency.
    from fyers_apiv3 import fyersModel

    return fyersModel.FyersModel(
        client_id=FYERS_CLIENT_ID,
        is_async=False,
        token=access_token,
        log_path=".",
    )


def fetch_fyers_intraday_5min(
    symbol: str,
    range_from,
    range_to,
    tz: str = "Asia/kolkata",
) -> pd.DataFrame:
    """Fetch 5-min candles from Fyers history API.

    Args:
        symbol: e.g. "NSE:SBIN-EQ" or "NSE:RELIANCE-EQ"
        range_from           : unix timestamp (seconds)
        range_to: unix timestamp (seconds)
        tz: target timezone for timestamps.

    Returns:
        df with columns: timestamp, open, high, low, close, volume
    """

    #db = DBConfig()
    #access_token = _get_access_token(db, FYERS_CLIENT_ID)
    access_token='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwieDowIiwieDoxIiwieDoyIl0sImF0X2hhc2giOiJnQUFBQUFCcU5qX2hhc25vclB3bDRBcUJCNWl6d3NTb0JjS3hVVVMySFdzNjNIeTFkeDZaUC1BSG83aEQtZ0RwaWZXbFBaSlQwSDg5VHpvRzZLTGptNjBWZ1kzbF9Mc1NJek9vUFFfOUhXT1d0eXVMMURSZllIWT0iLCJkaXNwbGF5X25hbWUiOiIiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiI2MDBiMGYzNTNjNmM5MzEyOGQ1NTAwMzdlYzg3MDU5Y2JlMzUyN2FkMTczYWZiMDkxNTJjMTY5ZCIsImlzRGRwaUVuYWJsZWQiOiJZIiwiaXNNdGZFbmFibGVkIjoiWSIsImZ5X2lkIjoiWFAxNDE4NCIsImFwcFR5cGUiOjEwMCwiZXhwIjoxNzgyMDAxODAwLCJpYXQiOjE3ODE5NDAxOTMsImlzcyI6ImFwaS5meWVycy5pbiIsIm5iZiI6MTc4MTk0MDE5Mywic3ViIjoiYWNjZXNzX3Rva2VuIn0.3YkcH7YFs65hR_JDcImCvO1GK8Xa_1g4PNgrRanGyuc'
    #print(f"Using access token for client {FYERS_CLIENT_ID},access_token={access_token}")
    fyers = _make_fyers(access_token)
    #print(f"fyrers object created successfully: {fyers}")
    #print(f"Fetching 5-min candles for {symbol} from {range_from} to {range_to}...")
    resp = fyers.history(
        {
            "symbol": symbol,
            "resolution": "5",
            # Fyers expects YYYY-MM-DD for range_from/range_to when date_format="1"
            "date_format": "1",
            "range_from": range_from,
            "range_to": range_to,
            "cont_flag": "1",
        }
    )
    #print(f"Raw response from Fyers API: {resp}")
    

    if not isinstance(resp, dict) or resp.get("s") == "no_data":
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    if "candles" not in resp:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    candles = resp["candles"]
    if not candles:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    # Each candle is expected to be [date, open, high, low, close, volume]
    # according to Fyers docs and your repo's usage.
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    df = pd.DataFrame(candles, columns=cols)

    # timestamp is seconds epoch
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert(tz)
    # ORBacktester expects naive timestamps.
    df["timestamp"] = df["timestamp"].dt.tz_localize(None)

    # Ensure numeric
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    return df.reset_index(drop=True)


def _to_yyyy_mm_dd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _to_unix_seconds(dt: datetime) -> int:
    return int(dt.timestamp())


def main(
    symbol: str = "NSE:RPTECH-EQ",
    days_back: int = 0,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Run an end-to-end backtest for last N days."""
    print(f"Starting ORB backtest for symbol={symbol} for last {days_back} days...")
    # Build unix range
    #end_dt = datetime.utcnow()
    end_dt = datetime.utcnow()- pd.Timedelta(days=3)
    start_dt = end_dt - pd.Timedelta(days=days_back)
    print(f"Fetching data for {symbol} from {start_dt} to {end_dt}...")

    # When date_format="1", fyers expects YYYY-MM-DD strings.
    range_from = _to_yyyy_mm_dd(start_dt)
    range_to = _to_yyyy_mm_dd(end_dt)
    #print(f"range_from={range_from}, range_to={range_to}")

    df = fetch_fyers_intraday_5min(symbol=symbol, range_from=range_from, range_to=range_to)
    print(f"Fetched {len(df)} candles for {symbol} from Fyers API.")
    print(f"DataFrame head:\n{df.head()}")
    #print(f"DataFrame tail:\n{df.tail()}")
    if df.empty:
        raise RuntimeError(f"No intraday candles returned for symbol={symbol}")

    backtester = ORBBacktester(initial_capital=100000.0)
    trades_df, equity_curve = backtester.run(df)

    print("=== ORB Metrics ===")
    for k, v in backtester.metrics().items():
        print(f"{k}: {v}")

    # Print buy/sell stock price details
    if trades_df is not None and not trades_df.empty:
        print("\n=== Trade Price Details (BUY/SELL) ===")
        # Map backtester side -> BUY/SELL
        tmp = trades_df.copy()
        tmp["trade_type"] = tmp["side"].map(lambda s: "BUY" if s == "long" else "SELL")

        buys = tmp[tmp["trade_type"] == "BUY"]
        sells = tmp[tmp["trade_type"] == "SELL"]
        print(f"BUY trades: {len(buys)}")
        print(f"SELL trades: {len(sells)}")

        cols_to_print = [
            "entry_time",
            "exit_time",
            "trade_type",
            "entry_price",
            "exit_price",
            "sl",
            "tp",
            "pnl",
            "result",
        ]
        existing_cols = [c for c in cols_to_print if c in tmp.columns]
        print(tmp[existing_cols].to_string(index=False))
    else:
        print("\n=== Trade Price Details (BUY/SELL) ===")
        print("No trades executed.")

    # Plot
    backtester.plot_equity_curve()

    return df, trades_df



if __name__ == "__main__":
    main()

