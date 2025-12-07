import json
import threading
import time
from typing import Protocol

from websocket import WebSocketApp
from polymarket.asset_id import fetch_event_market_clobs


WSS_BASE_URL = "wss://ws-subscriptions-clob.polymarket.com"
MARKET_CHANNEL = "market"


class OrderBook:
    def __init__(self, asset_id: str, market: str | None = None):
        self.asset_id = asset_id
        self.market = market
        self.bids: list[tuple[float, float]] = []
        self.asks: list[tuple[float, float]] = []
        self.timestamp: str | None = None
        self.hash: str | None = None

    def update_from_book_message(self, msg: dict) -> None:
        self.market = msg.get("market")
        self.timestamp = msg.get("timestamp")
        self.hash = msg.get("hash")

        raw_bids = msg.get("bids") or msg.get("buys") or []
        raw_asks = msg.get("asks") or msg.get("sells") or []

        def _parse_side(levels):
            parsed: list[tuple[float, float]] = []
            for level in levels:
                price_str = level.get("price", "0")
                size_str = level.get("size", "0")
                try:
                    price = float(price_str)
                except ValueError:
                    price = 0.0
                try:
                    size = float(size_str)
                except ValueError:
                    size = 0.0
                parsed.append((price, size))
            return parsed

        bids = _parse_side(raw_bids)
        asks = _parse_side(raw_asks)

        # Maintain sorted invariant:
        # - bids: highest price first
        # - asks: lowest price first
        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        self.bids = bids
        self.asks = asks

    def _upsert_bid(self, price: float, size: float) -> None:
        if size <= 0:
            self.bids = [(p, s) for (p, s) in self.bids if p != price]
            return

        for i, (p, _) in enumerate(self.bids):
            if p == price:
                # Update in place
                self.bids[i] = (price, size)
                return
            if p < price:
                # Insert before the first lower price
                self.bids.insert(i, (price, size))
                return

        # If we didn't insert yet, append at the end (lowest price)
        self.bids.append((price, size))

    def _upsert_ask(self, price: float, size: float) -> None:
        if size <= 0:
            self.asks = [(p, s) for (p, s) in self.asks if p != price]
            return

        for i, (p, _) in enumerate(self.asks):
            if p == price:
                # Update in place
                self.asks[i] = (price, size)
                return
            if p > price:
                # Insert before the first higher price
                self.asks.insert(i, (price, size))
                return

        # If we didn't insert yet, append at the end (highest price)
        self.asks.append((price, size))

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
            f"OrderBook(asset_id={self.asset_id}, market={self.market}, "
            f"bids={self.bids}, asks={self.asks}, "
            f"timestamp={self.timestamp}, hash={self.hash})"
        )


class OrderBookStrategy(Protocol):
    def on_order_book(self, market: str, order_book: OrderBook) -> None: ...


class NoOpStrategy:
    def on_order_book(self, market: str, order_book: OrderBook) -> None:  # noqa: D401
        """
        Default strategy that leaves feed behaviour unchanged.
        """
        return


class PolymarketFeed:
    def __init__(
        self,
        url: str = WSS_BASE_URL,
        verbose: bool = False,
        strategy: OrderBookStrategy | None = None,
    ):
        self.url = url
        self.verbose = verbose
        self.asset_ids: list[str] = []
        self.ws: WebSocketApp | None = None
        self._lock = threading.Lock()
        self.strategy: OrderBookStrategy = strategy or NoOpStrategy()

        # asset_id -> OrderBook
        self.orderbooks: dict[str, OrderBook] = {}

        # slug -> {"yes": token_id, "no": token_id}
        self.market_tokens: dict[str, dict[str, str]] = {}
        # token_id -> (slug, side)
        self.token_lookup: dict[str, tuple[str, str]] = {}

    def connect(self) -> None:
        if not self.asset_ids:
            raise ValueError("No asset_ids set. Call `subscribe()` before `connect()`.")

        full_url = self.url + "/ws/" + MARKET_CHANNEL

        self.ws = WebSocketApp(
            full_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
        )

        self.ws.run_forever()

    def subscribe(self, markets: list[str]) -> None:
        self.asset_ids = list(markets)

    def subscribe_event(self, event_slug: str) -> None:
        self.market_tokens = fetch_event_market_clobs(event_slug)
        token_ids: list[str] = []
        self.token_lookup = {}
        for slug, sides in self.market_tokens.items():
            for side, token in sides.items():
                token_ids.append(token)
                self.token_lookup[token] = (slug, side)
        self.subscribe(token_ids)

    def subscribe_market(self, market_slug: str, event_slug: str | None = None) -> None:
        """
        Subscribe only to one market within an event.
        If no event data is loaded yet, pass event_slug to fetch it first.
        """
        if not self.market_tokens:
            if not event_slug:
                raise ValueError(
                    "No event data loaded. Call subscribe_event first or provide event_slug."
                )
            self.subscribe_event(event_slug)

        if market_slug not in self.market_tokens:
            if event_slug:
                self.subscribe_event(event_slug)
            if market_slug not in self.market_tokens:
                raise KeyError(
                    f"Market slug '{market_slug}' not found in current event."
                )

        market_tokens = self.market_tokens[market_slug]
        # Limit scope to just this market for downstream reporting
        self.market_tokens = {market_slug: market_tokens}
        token_ids: list[str] = []
        self.token_lookup = {}
        for side, token in market_tokens.items():
            token_ids.append(token)
            self.token_lookup[token] = (market_slug, side)

        self.subscribe(token_ids)

    def _on_open(self, ws) -> None:
        if self.verbose:
            print("WebSocket opened, sending subscription...")

        subscribe_msg = {
            "assets_ids": self.asset_ids,
            "type": MARKET_CHANNEL,
        }
        ws.send(json.dumps(subscribe_msg))

        # Start ping thread (as in the sample implementation).
        ping_thread = threading.Thread(target=self._ping, args=(ws,))
        ping_thread.daemon = True
        ping_thread.start()

    def _ping(self, ws) -> None:
        while True:
            try:
                ws.send("PING")
            except Exception as e:
                if self.verbose:
                    print(f"Ping failed: {e}")
                break
            time.sleep(10)

    def _on_message(self, ws, message: str) -> None:
        if self.verbose:
            print("Raw message:", message)

        try:
            data = json.loads(message)
        except json.JSONDecodeError:  # usually a pong
            return

        # If it's a list, handle each item; if it's a dict, handle it directly
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    self._handle_book_message(item)
        elif isinstance(data, dict):
            self._handle_book_message(data)
        else:
            # Unexpected type, ignore
            return

    def _handle_book_message(self, msg: dict) -> None:
        event_type = msg.get("event_type")
        if event_type != "book":
            # Ignore other event types: price_change, tick_size_change, last_trade_price, etc.
            return

        asset_id = msg.get("asset_id")
        if not asset_id:
            return

        with self._lock:
            # Get or create OrderBook instance for this asset_id
            orderbook = self.orderbooks.get(asset_id)
            if orderbook is None:
                orderbook = OrderBook(asset_id=asset_id, market=msg.get("market"))
                self.orderbooks[asset_id] = orderbook

            # Update snapshot from the message
            orderbook.update_from_book_message(msg)

        # Callback for the updated order book snapshot
        self.on_order_book(asset_id, orderbook)

    def _on_error(self, ws, error) -> None:
        print("WebSocket error:", error)

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        print("WebSocket closed:", close_status_code, close_msg)

    def on_order_book(self, market, order_book: OrderBook) -> None:
        """
        Delegate order book updates to the configured strategy.
        """
        self.strategy.on_order_book(market, order_book)

    def start_in_background(self) -> threading.Thread:
        """
        Run the websocket client on a daemon thread so snapshots keep updating
        while the rest of the app (e.g. REST API) remains responsive.
        """
        t = threading.Thread(target=self.connect, daemon=True)
        t.start()
        return t

    def get_report(self) -> str:
        def _fmt(levels: list[tuple[float, float]]):
            if not levels:
                return "—"
            price, size = levels[0]
            return f"{price:.4f} @ {size}"

        lines: list[str] = [
            f"markets={len(self.market_tokens)}",
            f"assets={len(self.orderbooks)}",
        ]

        with self._lock:
            for slug, sides in self.market_tokens.items():
                yes_id = sides.get("yes")
                no_id = sides.get("no")
                yes_ob = self.orderbooks.get(yes_id)
                no_ob = self.orderbooks.get(no_id)

                lines.append(f"\nmarket={slug}")
                if yes_ob:
                    lines.append(
                        f" yes asset={yes_id} ts={yes_ob.timestamp} hash={yes_ob.hash} "
                        f"best_bid={_fmt(yes_ob.bids)} best_ask={_fmt(yes_ob.asks)}"
                    )
                else:
                    lines.append(f" yes asset={yes_id} (no data yet)")

                if no_ob:
                    lines.append(
                        f" no  asset={no_id} ts={no_ob.timestamp} hash={no_ob.hash} "
                        f"best_bid={_fmt(no_ob.bids)} best_ask={_fmt(no_ob.asks)}"
                    )
                else:
                    lines.append(f" no  asset={no_id} (no data yet)")

        return "\n".join(lines)
