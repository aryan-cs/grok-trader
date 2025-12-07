import time

from polymarket.feed import OrderBook, PolymarketFeed


class Strategy:
    def on_order_book(self, market: str, order_book: OrderBook) -> None:
        raise NotImplementedError


class PrintTopOfBookStrategy(Strategy):
    def __init__(self, spread_alert: float = 0.05):
        self.spread_alert = spread_alert

    def on_order_book(self, market: str, order_book: OrderBook) -> None:
        bids = order_book.best_bid()
        asks = order_book.best_ask()
        if not bids or not asks:
            return

        best_bid_price, best_bid_size = bids[0]
        best_ask_price, best_ask_size = asks[0]
        spread = best_ask_price - best_bid_price

        print(
            f"{market}: "
            f"bid {best_bid_price:.4f} ({best_bid_size}) | "
            f"ask {best_ask_price:.4f} ({best_ask_size}) | "
            f"spread {spread:.4f}"
        )

        if spread <= self.spread_alert:
            print("  -> Spread small enough to consider taking liquidity.")


def run_demo() -> None:
    strategy = PrintTopOfBookStrategy(spread_alert=0.02)
    feed = PolymarketFeed(verbose=False, strategy=strategy)
    feed.subscribe_event("will-israel-strike-gaza-on-379")
    feed.start_in_background()

    while True:
        time.sleep(5)


if __name__ == "__main__":
    run_demo()
