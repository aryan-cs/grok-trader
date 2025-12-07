from datetime import datetime


class TradeInstance:
    def __init__(
        self,
        action: str,  # "buy" or "sell"
        amount: float,
        timestamp: datetime = None,
    ):
        self.action = action
        self.amount = amount
        self.timestamp = timestamp or datetime.now()

    def to_dict(self):
        return {
            "action": self.action,
            "amount": self.amount,
            "timestamp": self.timestamp.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict):
        return TradeInstance(
            action=data.get("action"),
            amount=data.get("amount"),
            timestamp=datetime.fromisoformat(data.get("timestamp")) if data.get("timestamp") else None,
        )


class AutoTrade:
    def __init__(
        self,
        id: int,
        event_slug: str,
        market_slug: str,
        condition: str,
        amount: float,
        limit: float,
        websocket=None,
    ):
        self.id = id
        self.event_slug = event_slug
        self.market_slug = market_slug
        self.condition = condition
        self.amount = amount
        self.limit = limit
        self.websocket = websocket
        self.trades = []
        self.open_positions = []  # Track cost basis of holdings (FIFO)
        self.realized_pnl = 0.0  # Profit from closed positions

    @property
    def pnl(self):
        """Total realized PnL (profit from sells minus buy costs)"""
        return self.realized_pnl

    @property
    def holdings_cost(self):
        """Total cost basis of current holdings"""
        return sum(self.open_positions)

    def log_trade(self, action: str, amount: float, timestamp: datetime = None):
        """
        Create a trade instance and update PnL.

        Args:
            action: "buy" or "sell"
            amount: Trade amount in dollars
            timestamp: Optional timestamp (defaults to current time)
        """
        # Create trade instance
        trade = TradeInstance(action=action, amount=amount, timestamp=timestamp)
        self.trades.append(trade)

        # Update PnL and holdings
        if action.lower() == "buy":
            # Add to open positions (we hold an asset worth `amount`)
            # PnL doesn't change because we still have the value
            self.open_positions.append(amount)
        elif action.lower() == "sell":
            # Close a position (FIFO - First In First Out)
            if self.open_positions:
                cost_basis = self.open_positions.pop(0)
                profit = amount - cost_basis
                self.realized_pnl += profit
            else:
                # Selling without a buy (shouldn't happen, but handle it)
                self.realized_pnl += amount

        return trade

    def to_dict(self):
        return {
            "id": self.id,
            "event_slug": self.event_slug,
            "market_slug": self.market_slug,
            "condition": self.condition,
            "amount": self.amount,
            "limit": self.limit,
            "pnl": self.pnl,  # Computed property (realized PnL)
            "realized_pnl": self.realized_pnl,
            "holdings_cost": self.holdings_cost,  # Computed property
            "open_positions": self.open_positions,
            "trades": [trade.to_dict() for trade in self.trades],
        }

    def from_dict(self, data: dict):
        self.id = data.get("id")
        self.event_slug = data.get("event_slug")
        self.market_slug = data.get("market_slug")
        self.condition = data.get("condition")
        self.amount = data.get("amount")
        self.limit = data.get("limit")
        self.realized_pnl = data.get("realized_pnl", 0.0)
        self.open_positions = data.get("open_positions", [])
        self.trades = [TradeInstance.from_dict(t) for t in data.get("trades", [])]
