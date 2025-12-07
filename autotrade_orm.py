class AutoTrade:
    def __init__(
        self,
        id: int,
        market_slug: str,
        x_handles: list[str],
        condition: str,
        amount: float,
        limit: float,
    ):
        self.id = id
        self.market_slug = market_slug
        self.x_handles = x_handles
        self.condition = condition
        self.amount = amount
        self.limit = limit

    def to_dict(self):
        return {
            "id": self.id,
            "market_slug": self.market_slug,
            "x_handles": self.x_handles,
            "condition": self.condition,
            "amount": self.amount,
            "limit": self.limit,
        }

    def from_dict(self, data: dict):
        self.id = data.get("id")
        self.market_slug = data.get("market_slug")
        self.x_handles = data.get("x_handles")
        self.condition = data.get("condition")
        self.amount = data.get("amount")
        self.limit = data.get("limit")
