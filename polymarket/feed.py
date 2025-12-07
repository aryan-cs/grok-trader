import json
import threading
import time

from websocket import WebSocketApp
from asset_id import fetch_event


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

        # Some older docs mention buys/sells in the text, but the example response
        # (and current docs) use 'bids' and 'asks'. We support both just in case.
        raw_bids = msg.get("bids") or msg.get("buys") or []
        raw_asks = msg.get("asks") or msg.get("sells") or []

        def _parse_side(levels):
            parsed = []
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

        self.bids = _parse_side(raw_bids)
        self.asks = _parse_side(raw_asks)

    def __repr__(self) -> str:
        return (
            f"OrderBook(asset_id={self.asset_id}, market={self.market}, "
            f"bids={self.bids}, asks={self.asks}, "
            f"timestamp={self.timestamp}, hash={self.hash})"
        )


class PolymarketFeed:
    def __init__(self, url: str = WSS_BASE_URL, verbose: bool = False):
        self.url = url
        self.verbose = verbose
        self.asset_ids: list[str] = []
        self.ws: WebSocketApp | None = None

        # asset_id -> OrderBook
        self.orderbooks: dict[str, OrderBook] = {}

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

    def _on_open(self, ws) -> None:
        if self.verbose:
            print("WebSocket opened, sending subscription...")

        subscribe_msg = {
            "assets_ids": self.asset_ids,
            "type": MARKET_CHANNEL,  # "market"
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
        # TODO(ayushgun) - fix this to store states

        print(f"\nOrder book update for asset_id={market} (market={order_book.market})")
        print(f"timestamp={order_book.timestamp}, hash={order_book.hash}")

        def _fmt_levels(levels):
            return ", ".join(f"{size}@{price}" for price, size in levels)

        print("Bids:", _fmt_levels(order_book.bids))
        print("Asks:", _fmt_levels(order_book.asks))


if __name__ == "__main__":
    market_ids = fetch_event("elc-cha-por-2025-12-06")
    yes_asset_ids = [m["yes"] for m in market_ids.values()]
    feed = PolymarketFeed(verbose=True)
    feed.subscribe(yes_asset_ids)
    feed.connect()
