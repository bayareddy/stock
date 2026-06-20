from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from orb_backtester import ORBBacktester
from orb_order_manager_fyers import FyersORBOrderManager

FYERS_CLIENT_ID = "Z4O9BSFX7K-100"
access_token='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwieDowIiwieDoxIiwieDoyIl0sImF0X2hhc2giOiJnQUFBQUFCcU5qX2hhc25vclB3bDRBcUJCNWl6d3NTb0JjS3hVVVMySFdzNjNIeTFkeDZaUC1BSG83aEQtZ0RwaWZXbFBaSlQwSDg5VHpvRzZLTGptNjBWZ1kzbF9Mc1NJek9vUFFfOUhXT1d0eXVMMURSZllIWT0iLCJkaXNwbGF5X25hbWUiOiIiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiI2MDBiMGYzNTNjNmM5MzEyOGQ1NTAwMzdlYzg3MDU5Y2JlMzUyN2FkMTczYWZiMDkxNTJjMTY5ZCIsImlzRGRwaUVuYWJsZWQiOiJZIiwiaXNNdGZFbmFibGVkIjoiWSIsImZ5X2lkIjoiWFAxNDE4NCIsImFwcFR5cGUiOjEwMCwiZXhwIjoxNzgyMDAxODAwLCJpYXQiOjE3ODE5NDAxOTMsImlzcyI6ImFwaS5meWVycy5pbiIsIm5iZiI6MTc4MTk0MDE5Mywic3ViIjoiYWNjZXNzX3Rva2VuIn0.3YkcH7YFs65hR_JDcImCvO1GK8Xa_1g4PNgrRanGyuc'
    
def _to_yyyy_mm_dd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

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

def fetch_fyers_intraday_5min_temp(symbol: str, range_from: str, range_to: str, resolution: str = "5") -> pd.DataFrame:
    """Small wrapper around fyers history using existing token flow in fyers_util."""
    from fyers_util import fyersObj

    resp = fyersObj().history(
        {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": "1",
            "range_from": range_from,
            "range_to": range_to,
            "cont_flag": "1",
        }
    )

    if not isinstance(resp, dict) or resp.get("s") == "no_data":
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    if "candles" not in resp or not resp["candles"]:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    df = pd.DataFrame(resp["candles"], columns=cols)

    # timestamp is seconds epoch
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/kolkata")
    df["timestamp"] = df["timestamp"].dt.tz_localize(None)

    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    return df.reset_index(drop=True)


def _pick_latest_trade_signal(trades_df: pd.DataFrame) -> Optional[pd.Series]:
    if trades_df is None or trades_df.empty:
        return None

    # Latest executed trade
    return trades_df.sort_values("entry_time").iloc[-1]


def main(
    symbol: str = "NSE:SBIN-EQ",
    qty: int = 1,
    days_back: int = 1,
):
    # Fetch recent candles
    end_dt = datetime.utcnow() - timedelta(days=1)
    start_dt = end_dt - timedelta(days=days_back)
    print(f"Fetching candles for {symbol} from {start_dt} to {end_dt}")
    range_from = _to_yyyy_mm_dd(start_dt)
    range_to = _to_yyyy_mm_dd(end_dt)

    df = fetch_fyers_intraday_5min(symbol=symbol, range_from=range_from, range_to=range_to)
    print('df head: ',df.head())
    if df.empty:
        # Fyers can return no_data for some date ranges (weekends/holidays/market hours).
        # Retry with a smaller rolling window.
        for retry_days_back in [2, 1, 0]:
            start_dt_retry = end_dt - timedelta(days=retry_days_back)
            range_from_retry = _to_yyyy_mm_dd(start_dt_retry)
            range_to_retry = _to_yyyy_mm_dd(end_dt)
            print(f"Retrying candle fetch for {symbol}: {range_from_retry} -> {range_to_retry}")
            df = fetch_fyers_intraday_5min(
                symbol=symbol,
                range_from=range_from_retry,
                range_to=range_to_retry,
            )
            if not df.empty:
                break

    if df.empty:
        raise RuntimeError(f"No candle data returned for {symbol} using initial and retry windows")


    backtester = ORBBacktester(initial_capital=100000.0)
    trades_df, _equity = backtester.run(df)

    latest = _pick_latest_trade_signal(trades_df)
    print(f"Latest trade signal for {symbol}: {latest}")
    if latest is None:
        print("No trade signal found")
        return

    side = latest["side"]  # 'long'/'short'
    entry_price = float(latest["entry_price"])
    sl_price = float(latest["sl"])
    tp_price = float(latest["tp"])

    # Place orders
    om = FyersORBOrderManager()
    # pass only stock code to manager; it will format NSE:...-EQ
    stock_code = symbol.replace("NSE:", "").replace("-EQ", "")

    resp = om.place_entry_and_exits_separate(
        exchange_symbol=stock_code,
        qty=qty,
        side=side,
        entry_price=entry_price,
        sl_price=sl_price,
        tp_price=tp_price,
        skip_if_position_exists=True,
    )

    print("ORB live order management response:")
    print(resp)


if __name__ == "__main__":
    main()

