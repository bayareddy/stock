from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Tuple

from fyers_util import (
    fyersObj,
    getLastTradedPrice,
    getNetPostions,
    placeOrderwith_symbol,
)


@dataclass(frozen=True)
class ORBOrderPlan:
    symbol: str  # like "NSE:SBIN-EQ"
    qty: int
    side: str  # "long" | "short"
    entry_price: float
    sl_price: float
    tp_price: float


class FyersORBOrderManager:
    """Places ORB entry + two exit orders (SL + TP) as separate intraday orders.

    - Entry is placed as LIMIT at strategy entry_price (requested behavior).
    - For exits we use:
        * SL as Stop Order (SL-M) => type=3
        * TP as LIMIT Order (type=1)

    Note: Fyers order semantics differ slightly by order type.
    This manager aims to be idempotent using positions snapshot.
    """

    def __init__(self, poll_interval_sec: float = 1.0, poll_timeout_sec: float = 20.0):
        self.poll_interval_sec = poll_interval_sec
        self.poll_timeout_sec = poll_timeout_sec

    @staticmethod
    def _to_fyers_symbol(exchange_symbol: str) -> str:
        # Accepts either "SBIN" or already "NSE:SBIN-EQ".
        if exchange_symbol.startswith("NSE:") and exchange_symbol.endswith("-EQ"):
            return exchange_symbol
        return f"NSE:{exchange_symbol}-EQ"

    @staticmethod
    def _side_to_fyers(side: str) -> int:
        if side == "long":
            return 1
        if side == "short":
            return -1
        raise ValueError("side must be 'long' or 'short'")

    def _position_open_for_symbol(self, exchange_symbol: str) -> Tuple[int, int]:
        # Returns (buy_qty, sell_qty) from existing util
        # For intraday, this indicates open net positions (if any)
        # fyers_util.getNetPostions() is a thin wrapper and may throw if the broker response
        # format differs (e.g., missing 'overall'). Treat any failure as "no open position"
        # so we don't crash the strategy.
        try:
            buy_qty, sell_qty = getNetPostions(
                exchange_symbol.replace("NSE:", "").replace("-EQ", "")
            )
            return int(buy_qty), int(sell_qty)
        except Exception:
            return 0, 0


    def _has_live_position(self, symbol: str, side: str) -> bool:
        buy_qty, sell_qty = self._position_open_for_symbol(symbol)
        if side == "long":
            return buy_qty > 0
        return sell_qty > 0

    def place_entry_limit(self, exchange_symbol: str, qty: int, side: str, entry_price: float) -> dict:
        fy_symbol = self._to_fyers_symbol(exchange_symbol)
        fyers_side = self._side_to_fyers(side)

        # type=1 => Limit
        # Use productType=INTRADAY per util defaults
        return placeOrderwith_symbol(
            symbol=fy_symbol,
            quantity=qty,
            side=fyers_side,
            order_type=1,
            limitPrice=float(entry_price),
            stopPrice=0,
        )

    def _place_sl_stop_m(self, exchange_symbol: str, qty: int, side: str, sl_price: float) -> dict:
        fy_symbol = self._to_fyers_symbol(exchange_symbol)
        fyers_side = self._side_to_fyers(side)

        # For SL (SL-M), type=3 in fyers util comment.
        # stopPrice is used; limitPrice ignored/should be 0.
        return placeOrderwith_symbol(
            symbol=fy_symbol,
            quantity=qty,
            side=fyers_side,
            order_type=3,
            limitPrice=0,
            stopPrice=float(sl_price),
        )

    def _place_tp_limit(self, exchange_symbol: str, qty: int, side: str, tp_price: float) -> dict:
        fy_symbol = self._to_fyers_symbol(exchange_symbol)
        fyers_side = self._side_to_fyers(side)

        # TP as LIMIT order
        return placeOrderwith_symbol(
            symbol=fy_symbol,
            quantity=qty,
            side=fyers_side,
            order_type=1,
            limitPrice=float(tp_price),
            stopPrice=0,
        )

    def place_entry_and_exits_separate(
        self,
        exchange_symbol: str,
        qty: int,
        side: str,
        entry_price: float,
        sl_price: float,
        tp_price: float,
        skip_if_position_exists: bool = True,
    ) -> dict:
        """Idempotent orchestration:
        - If position already exists for the side, do nothing.
        - Else place entry (limit at entry_price), then place SL/TP orders.

        Returns a dict with raw responses.
        """
        print(f"Placing entry and exits for {exchange_symbol}: side={side}, entry={entry_price}, sl={sl_price}, tp={tp_price}")
        if skip_if_position_exists and self._has_live_position(self._to_fyers_symbol(exchange_symbol), side):
            return {"skipped": True, "reason": "position already open"}

        entry_resp = self.place_entry_limit(exchange_symbol, qty, side, entry_price)

        # Wait briefly for fill/position to open to reduce chance of orphan exits.
        filled = False
        t0 = time.time()
        while time.time() - t0 < self.poll_timeout_sec:
            if self._has_live_position(self._to_fyers_symbol(exchange_symbol), side):
                filled = True
                break
            time.sleep(self.poll_interval_sec)

        sl_resp = self._place_sl_stop_m(exchange_symbol, qty, side, sl_price)
        tp_resp = self._place_tp_limit(exchange_symbol, qty, side, tp_price)

        return {
            "skipped": False,
            "filled": filled,
            "entry": entry_resp,
            "sl": sl_resp,
            "tp": tp_resp,
        }

