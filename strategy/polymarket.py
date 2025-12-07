import json
import threading
import time
from typing import Callable

from websocket import WebSocketApp

from polymarket.asset_id import fetch_event_market_clobs


WSS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class Book:
    def __init__(
        self, asset_id: str, market: str | None = None, side: str | None = None
    ):
        self.asset_id = asset_id
        self.market = market
        self.side = side
        self.bids: list[tuple[float, float]] = []
        self.asks: list[tuple[float, float]] = []
        self.timestamp: str | None = None
        self.hash: str | None = None

    def update_from_message(self, msg: dict) -> None:
        self.market = msg.get("market", self.market)
        self.timestamp = msg.get("timestamp") or self.timestamp
        self.hash = msg.get("hash") or self.hash

        raw_bids = msg.get("bids") or msg.get("buys") or []
        raw_asks = msg.get("asks") or msg.get("sells") or []

        def _parse(levels):
            parsed: list[tuple[float, float]] = []
            for level in levels:
                try:
                    price = float(level.get("price", 0) or 0)
                except Exception:
                    price = 0.0
                try:
                    size = float(level.get("size", 0) or 0)
                except Exception:
                    size = 0.0
                parsed.append((price, size))
            return parsed

        bids = _parse(raw_bids)
        asks = _parse(raw_asks)

        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        self.bids = bids
        self.asks = asks

    def best_bid(self, n: int = 1) -> list[tuple[float, float]]:
        if n <= 0:
            return []
        return self.bids[:n]

    def best_ask(self, n: int = 1) -> list[tuple[float, float]]:
        if n <= 0:
            return []
        return self.asks[:n]

    def __repr__(self) -> str:
        return (
            f"Book(asset_id={self.asset_id}, market={self.market}, side={self.side}, "
            f"bids={self.bids}, asks={self.asks}, ts={self.timestamp}, hash={self.hash})"
        )


class Polymarket:
    def __init__(
        self,
        event_slug: str,
        strategy: Callable[[Book | None, Book | None], None],
        market_slug: str | None = None,
        url: str = WSS_URL,
    ):
        self.event_slug = event_slug
        self.market_slug = market_slug
        self.strategy = strategy
        self.url = url

        self.asset_ids: list[str] = []
        self.token_lookup: dict[str, tuple[str, str]] = {}
        self.books: dict[str, Book] = {}
        self.market_books: dict[str, dict[str, Book]] = {}

        self._ws: WebSocketApp | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

        self._prepare_subscription()
        self._start_socket()

    def _prepare_subscription(self) -> None:
        mapping = fetch_event_market_clobs(self.event_slug)
        if not mapping:
            raise ValueError(f"No markets found for event '{self.event_slug}'")

        if self.market_slug:
            if self.market_slug not in mapping:
                raise ValueError(
                    f"Market slug '{self.market_slug}' not found in event '{self.event_slug}'"
                )
            selected = {self.market_slug: mapping[self.market_slug]}
        else:
            selected = mapping  # subscribe to all markets under the event

        for slug, sides in selected.items():
            market_entry = self.market_books.setdefault(slug, {})
            for side, token in sides.items():
                self.token_lookup[token] = (slug, side)
                self.asset_ids.append(token)
                market_entry.setdefault(side)

    def _start_socket(self) -> None:
        if not self.asset_ids:
            raise ValueError("No asset ids to subscribe to")

        self._ws = WebSocketApp(
            self.url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

        thread = threading.Thread(target=self._ws.run_forever, daemon=True)
        self._thread = thread
        thread.start()

    def _on_open(self, ws) -> None:
        subscribe_msg = {"type": "market", "assets_ids": self.asset_ids}
        ws.send(json.dumps(subscribe_msg))

        ping_thread = threading.Thread(target=self._ping, args=(ws,), daemon=True)
        ping_thread.start()

    def _ping(self, ws) -> None:
        while True:
            try:
                ws.send("PING")
            except Exception:
                break
            time.sleep(10)

    def _on_message(self, ws, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    self._handle_book(item)
        elif isinstance(data, dict):
            self._handle_book(data)

    def _handle_book(self, msg: dict) -> None:
        if msg.get("event_type") != "book":
            return

        asset_id = msg.get("asset_id")
        if not asset_id:
            return

        with self._lock:
            book = self.books.get(asset_id)
            if not book:
                slug, side = self.token_lookup.get(asset_id, (self.market_slug, ""))
                book = Book(asset_id=asset_id, market=slug, side=side)
                self.books[asset_id] = book
                self.market_books.setdefault(slug, {})[side] = book

            book.update_from_message(msg)

            slug, side = self.token_lookup.get(asset_id, (book.market, book.side))
            market_entry = self.market_books.setdefault(slug, {})
            market_entry[side] = book
            yes_book = market_entry.get("yes")
            no_book = market_entry.get("no")

        try:
            if hasattr(self.strategy, "on_new_book"):
                self.strategy.on_new_book(yes_book, no_book)
            else:
                self.strategy(yes_book, no_book)
        except Exception:
            # Strategy exceptions shouldn't kill the feed
            return

    def _on_error(self, ws, error) -> None:
        print("Polymarket websocket error:", error)

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        print("Polymarket websocket closed:", close_status_code, close_msg)

    def close(self) -> None:
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
