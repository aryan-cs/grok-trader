"""
Backtester for Polymarket data.

Two modes:
1) Book replay: load recorded book messages (json/jsonl) and feed to Strategy.on_new_book.
2) Trade fetch: pull historical trades from the public Polymarket data API for a market
    (by conditionId) and persist them for later analysis/replay.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, Iterable, List, Optional, Tuple

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from strategy.polymarket import Book
from strategy.autotrader import Strategy


@dataclass
class TradeLogEntry:
    side: str
    action: str
    size: float
    price: float
    notional: float
    timestamp: Optional[int] = None


@dataclass
class Simulator:
    cash: float = 0.0
    pos_yes: float = 0.0
    pos_no: float = 0.0
    last_price_yes: Optional[float] = None
    last_price_no: Optional[float] = None
    trades: List[TradeLogEntry] = field(default_factory=list)

    def mark(self) -> float:
        mtm_yes = (self.last_price_yes or 0.0) * self.pos_yes
        mtm_no = (self.last_price_no or 0.0) * self.pos_no
        return self.cash + mtm_yes + mtm_no

    def apply_actions(
        self,
        actions: List[dict],
        yes_book: Optional[Book],
        no_book: Optional[Book],
    ) -> None:
        price_yes = self._top_price(yes_book)
        price_no = self._top_price(no_book)
        timestamp = self._top_ts(yes_book, no_book)

        for action in actions:
            side = (action.get("side") or "").lower()
            direction = (action.get("action") or action.get("direction") or "").lower()
            size = float(action.get("size") or 0)
            if side not in {"yes", "no"} or direction not in {"buy", "sell"} or size <= 0:
                continue
            px = price_yes if side == "yes" else price_no
            if px is None:
                continue

            notional = px * size
            if direction == "buy":
                if side == "yes":
                    self.pos_yes += size
                else:
                    self.pos_no += size
                self.cash -= notional
            else:
                if side == "yes":
                    self.pos_yes -= size
                else:
                    self.pos_no -= size
                self.cash += notional

            self.trades.append(
                TradeLogEntry(
                    side=side,
                    action=direction,
                    size=size,
                    price=px,
                    notional=notional,
                    timestamp=timestamp,
                )
            )

        if price_yes is not None:
            self.last_price_yes = price_yes
        if price_no is not None:
            self.last_price_no = price_no

    def report(self) -> None:
        realized = self.cash
        unrealized = (self.last_price_yes or 0.0) * self.pos_yes + (self.last_price_no or 0.0) * self.pos_no
        total = realized + unrealized
        max_dd = self._max_drawdown()
        print(f"\n=== Backtest Report ===")
        print(f"Trades: {len(self.trades)}")
        print(f"Position YES: {self.pos_yes:.4f}, NO: {self.pos_no:.4f}")
        print(f"Cash (realized PnL): {realized:.4f}")
        print(f"Unrealized PnL: {unrealized:.4f}")
        print(f"Total PnL: {total:.4f}")
        print(f"Max Drawdown (equity): {max_dd:.4f}")

    def _top_price(self, book: Optional[Book]) -> Optional[float]:
        if not book:
            return None
        if book.bids:
            return book.bids[0][0]
        if book.asks:
            return book.asks[0][0]
        return None

    def _top_ts(self, yes_book: Optional[Book], no_book: Optional[Book]) -> Optional[int]:
        ts = None
        if yes_book and yes_book.timestamp:
            try:
                ts = int(yes_book.timestamp)
            except Exception:
                ts = None
        if no_book and no_book.timestamp:
            try:
                ts = int(no_book.timestamp)
            except Exception:
                pass
        return ts

    def _max_drawdown(self) -> float:
        equity_curve = []
        last_yes = self.last_price_yes
        last_no = self.last_price_no
        cash = 0.0
        pos_yes = 0.0
        pos_no = 0.0
        peak = 0.0
        max_dd = 0.0
        for tr in self.trades:
            px = tr.price
            if tr.side == "yes":
                if tr.action == "buy":
                    pos_yes += tr.size
                    cash -= tr.notional
                else:
                    pos_yes -= tr.size
                    cash += tr.notional
                last_yes = px
            else:
                if tr.action == "buy":
                    pos_no += tr.size
                    cash -= tr.notional
                else:
                    pos_no -= tr.size
                    cash += tr.notional
                last_no = px
            equity = cash + (last_yes or 0.0) * pos_yes + (last_no or 0.0) * pos_no
            peak = max(peak, equity)
            dd = peak - equity
            max_dd = max(max_dd, dd)
            equity_curve.append(equity)
        return max_dd


def load_historical_data(path: str) -> Generator[dict, None, None]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Historical data file not found: {path}")

    if p.suffix.lower() == ".jsonl":
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    elif p.suffix.lower() == ".json":
        with p.open("r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item
        elif isinstance(data, dict):
            yield data
    else:
        raise ValueError("Unsupported file format; use .jsonl or .json")


def replay_history(messages: Iterable[dict], strategy: Strategy) -> None:
    books: dict[str, Book] = {}
    market_books: dict[str, dict[str, Book]] = {}

    simulator = Simulator()

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("event_type") != "book":
            continue

        asset_id = msg.get("asset_id")
        if not asset_id:
            continue

        market_slug = msg.get("market") or ""
        side = msg.get("side") or ""

        book = books.get(asset_id)
        if not book:
            book = Book(asset_id=asset_id, market=market_slug, side=side)
            books[asset_id] = book
        book.update_from_message(msg)

        market_entry = market_books.setdefault(market_slug, {})
        if side:
            market_entry[side] = book

        yes_book = market_entry.get("yes")
        no_book = market_entry.get("no")

        actions = []
        try:
            if hasattr(strategy, "on_new_book"):
                res = strategy.on_new_book(yes_book, no_book)
            else:
                res = strategy(yes_book, no_book)
            if res:
                # allow a single dict or list of dicts
                if isinstance(res, dict):
                    actions = [res]
                elif isinstance(res, list):
                    actions = res
        except Exception:
            continue

        simulator.apply_actions(actions, yes_book, no_book)

    simulator.report()


def trades_to_book_messages(trades: list[dict]) -> list[dict]:
    trades_sorted = sorted(
        trades,
        key=lambda t: t.get("timestamp", 0)
    )
    messages: list[dict] = []
    for t in trades_sorted:
        asset_id = t.get("asset") or t.get("token")
        market_slug = t.get("slug") or t.get("market") or ""
        side_label = t.get("outcome") or ("yes" if t.get("outcomeIndex") == 0 else "no")
        price = float(t.get("price", 0) or 0)
        size = float(t.get("size", 0) or 0)
        if not asset_id or price <= 0 or size <= 0:
            continue
        msg = {
            "event_type": "book",
            "asset_id": str(asset_id),
            "market": market_slug,
            "side": side_label.lower() if isinstance(side_label, str) else "",
            "timestamp": t.get("timestamp"),
            "bids": [{"price": price, "size": size}]
            ,
            "asks": [{"price": price, "size": size}],
        }
        messages.append(msg)
    return messages


def run_backtest(
    history_path: str,
    market_slug: str,
    condition: str = "",
    max_size: float = 0.0,
) -> None:
    """Entry point for backtesting a single market from historical book data."""
    messages = load_historical_data(history_path)
    strategy = Strategy(market_slug=market_slug, condition=condition, max_size=max_size)
    replay_history(messages, strategy)


# ----------------------
# Trade fetch utilities
# ----------------------


def fetch_market_ids(event_slug: str, market_slug: str) -> dict:
    """Resolve conditionId and yes/no token ids for a market via Gamma API."""
    url = f"https://gamma-api.polymarket.com/events?slug={event_slug}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    events = resp.json()
    if not events:
        raise ValueError(f"Event slug not found: {event_slug}")
    event = events[0]
    for market in event.get("markets", []):
        if market.get("slug") == market_slug:
            clob_ids = market.get("clobTokenIds")
            try:
                token_ids = json.loads(clob_ids) if isinstance(clob_ids, str) else clob_ids
            except Exception:
                token_ids = []
            condition_id = market.get("conditionId") or market.get("condition_id")
            return {
                "condition_id": condition_id,
                "yes_token": token_ids[0] if token_ids and len(token_ids) > 0 else None,
                "no_token": token_ids[1] if token_ids and len(token_ids) > 1 else None,
            }
    raise ValueError(f"Market slug '{market_slug}' not found in event '{event_slug}'")


def fetch_trades(
    condition_id: str,
    limit: int = 10000,
    max_pages: int = 1,
    taker_only: bool = True,
    side: str | None = None,
) -> list[dict]:
    """Pull historical trades for a conditionId from data-api.polymarket.com."""
    trades: list[dict] = []
    base_url = "https://data-api.polymarket.com/trades"
    for page in range(max_pages):
        offset = page * limit
        params = {
            "market": condition_id,
            "limit": limit,
            "offset": offset,
            "takerOnly": str(taker_only).lower(),
        }
        if side:
            params["side"] = side
        resp = requests.get(base_url, params=params, timeout=15)
        resp.raise_for_status()
        batch = resp.json() or []
        if not batch:
            break
        trades.extend(batch)
        if len(batch) < limit:
            break
    return trades


def save_trades_jsonl(trades: list[dict], out_path: str) -> None:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for t in trades:
            f.write(json.dumps(t))
            f.write("\n")


def fetch_and_save_trades(event_slug: str, market_slug: str, out_path: str) -> None:
    """Resolve ids, fetch trades, and persist to jsonl for later replay/analysis."""
    ids = fetch_market_ids(event_slug, market_slug)
    condition_id = ids.get("condition_id")
    if not condition_id:
        raise ValueError("condition_id not found for market")
    trades = fetch_trades(condition_id=condition_id, limit=10000, max_pages=10)
    save_trades_jsonl(trades, out_path)
    print(f"Saved {len(trades)} trades to {out_path}")


if __name__ == "__main__":
    # Example: download trades for a market
    # fetch_and_save_trades(
    #     event_slug="spacex-ipo-closing-market-cap",
    #     market_slug="will-spacex-not-ipo-by-december-31-2027",
    #     out_path="data/polymarket_trades.jsonl",
    # )

    # Example: replay recorded book messages
    # run_backtest(
    #     history_path="data/polymarket_history.jsonl",
    #     market_slug="will-space-x-ipo-this-year",
    #     condition="",
    #     max_size=0.0,
    # )
    
    
    fetch_and_save_trades(
        event_slug="spacex-ipo-closing-market-cap",
        market_slug="will-spacex-not-ipo-by-december-31-2027",
        out_path="data/polymarket_trades.jsonl",
    )

    history_path = Path("data/polymarket_history.jsonl")
    trades_path = Path("data/polymarket_trades.jsonl")

    if history_path.exists():
        run_backtest(
            history_path=str(history_path),
            market_slug="will-space-x-ipo-this-year",
            condition="",
            max_size=0.0,
        )
    elif trades_path.exists():
        # Use trades to synthesize book messages and replay
        trades = list(load_historical_data(str(trades_path)))
        synthetic_msgs = trades_to_book_messages(trades)
        strategy = Strategy(
            market_slug="will-space-x-ipo-this-year",
            condition="",
            max_size=0.0,
        )
        replay_history(synthetic_msgs, strategy)
        print(f"Replayed {len(synthetic_msgs)} synthetic book messages from trades")
    else:
        print(f"History file not found, and no trades file found at {trades_path}")