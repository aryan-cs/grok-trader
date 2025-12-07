import time
import asyncio
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI

from polymarket.feed import OrderBook, PolymarketFeed
from autotrade_orm import AutoTrade

load_dotenv()

XAI_API_KEY = os.getenv("XAI_API_KEY")

# Initialize xAI client
client = AsyncOpenAI(
    api_key=XAI_API_KEY,
    base_url="https://api.x.ai/v1",
) if XAI_API_KEY else None


class Strategy:
    def on_order_book(self, market: str, order_book: OrderBook) -> None:
        raise NotImplementedError


class AutoTradeStrategy(Strategy):
    """
    Strategy that executes trades based on AutoTrade conditions and logs them.
    """
    def __init__(self, autotrade: AutoTrade):
        self.autotrade = autotrade
        self.last_evaluation_time = 0
        self.evaluation_interval = 10  # Evaluate every 10 seconds

    def on_order_book(self, market: str, order_book: OrderBook) -> None:
        """Called when order book updates are received"""
        current_time = time.time()

        # Rate limit evaluations
        if current_time - self.last_evaluation_time < self.evaluation_interval:
            return

        self.last_evaluation_time = current_time

        bids = order_book.best_bid()
        asks = order_book.best_ask()
        if not bids or not asks:
            return

        best_bid_price, best_bid_size = bids[0]
        best_ask_price, best_ask_size = asks[0]

        # Check if we should trade based on conditions
        # This would typically involve:
        # 1. Checking if condition is met (via LLM or other logic)
        # 2. Checking if price is within limit
        # 3. Executing trade and logging it

        # For now, simple example: trade if price is within limit
        if best_ask_price <= self.autotrade.limit and not self.autotrade.open_positions:
            # Buy signal
            self._execute_buy(best_ask_price)
        elif best_bid_price > 0 and self.autotrade.open_positions:
            # Sell signal (if we have holdings)
            self._execute_sell(best_bid_price)

    def _execute_buy(self, price: float):
        """Execute a buy trade and log it"""
        amount = self.autotrade.amount
        trade = self.autotrade.log_trade(action="buy", amount=amount)

        print(f"🟢 BUY executed: ${amount:.2f} at price {price:.4f}")
        print(f"   PnL: ${self.autotrade.pnl:.2f}")
        print(f"   Holdings Cost: ${self.autotrade.holdings_cost:.2f}")

        # Send WebSocket update if available
        if self.autotrade.websocket:
            asyncio.create_task(self.autotrade.websocket.send_json({
                "message_type": "autotrade",
                "type": "trade_executed",
                "autotrade_id": self.autotrade.id,
                "trade": {
                    "action": trade.action,
                    "amount": trade.amount,
                    "timestamp": trade.timestamp.isoformat(),
                },
                "pnl": self.autotrade.pnl,
                "holdings_cost": self.autotrade.holdings_cost
            }))

    def _execute_sell(self, price: float):
        """Execute a sell trade and log it"""
        if not self.autotrade.open_positions:
            return

        # Sell amount equal to our holdings cost
        amount = self.autotrade.holdings_cost * (price / self.autotrade.limit)  # Adjust for price difference
        trade = self.autotrade.log_trade(action="sell", amount=amount)

        print(f"🔴 SELL executed: ${amount:.2f} at price {price:.4f}")
        print(f"   PnL: ${self.autotrade.pnl:.2f}")
        print(f"   Holdings Cost: ${self.autotrade.holdings_cost:.2f}")

        # Send WebSocket update if available
        if self.autotrade.websocket:
            asyncio.create_task(self.autotrade.websocket.send_json({
                "message_type": "autotrade",
                "type": "trade_executed",
                "autotrade_id": self.autotrade.id,
                "trade": {
                    "action": trade.action,
                    "amount": trade.amount,
                    "timestamp": trade.timestamp.isoformat(),
                },
                "pnl": self.autotrade.pnl,
                "holdings_cost": self.autotrade.holdings_cost
            }))


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


def start_autotrader(autotrade: AutoTrade) -> PolymarketFeed:
    """
    Start monitoring and trading for the given AutoTrade.

    Args:
        autotrade: AutoTrade object with market, condition, amount, limit, and websocket

    Returns:
        PolymarketFeed instance that's running in background
    """
    try:
        strategy = AutoTradeStrategy(autotrade)
        feed = PolymarketFeed(verbose=True, strategy=strategy)

        event_slug = autotrade.event_slug
        market_slug = autotrade.market_slug

        print(f"🚀 Attempting to start AutoTrader")
        print(f"   Event: {event_slug}")
        print(f"   Market: {market_slug}")
        print(f"   Condition: {autotrade.condition}")
        print(f"   Amount: ${autotrade.amount}")
        print(f"   Limit: {autotrade.limit}")

        # Subscribe to event first, then market
        feed.subscribe_event(event_slug)
        feed.subscribe_market(market_slug, event_slug=event_slug)

        feed.start_in_background()
        print(f"✅ AutoTrader successfully started")

        return feed

    except Exception as e:
        print(f"❌ Error in start_autotrader: {e}")
        import traceback
        traceback.print_exc()
        raise


def run_demo() -> None:
    """Demo function using PrintTopOfBookStrategy"""
    strategy = PrintTopOfBookStrategy(spread_alert=0.02)
    feed = PolymarketFeed(verbose=False, strategy=strategy)
    feed.subscribe_event("will-israel-strike-gaza-on-379")
    feed.start_in_background()

    while True:
        time.sleep(5)


if __name__ == "__main__":
    run_demo()
