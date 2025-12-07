import json
import os
from typing import Any

from pydantic import BaseModel, Field, field_validator
from xai_sdk import Client
from xai_sdk.chat import system, user
from xai_sdk.tools import web_search, x_search


class IOCDecision:
    # represents an IOC order on a binary contract (buy/sell yes/no)
    def __init__(
        self, action: str, outcome: str, price: float, size: float, response=None
    ):
        self.action = action
        self.outcome = outcome
        self.price = price
        self.size = size

        # raw xAI response for interpretability (tool calls, citations, usage)
        self.response = response

    def __repr__(self) -> str:
        return (
            f"IOCDecision(action={self.action}, outcome={self.outcome}, "
            f"price={self.price}, size={self.size})"
        )


def produce_trading_decision(
    max_size, max_position, condition, yes_book, no_book, positions, tweet_window
):
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("XAI_API_KEY not set")

    def _snapshot(book) -> dict[str, Any] | None:
        if not book:
            return None
        return {
            "side": book.side,
            "market": book.market,
            "timestamp": book.timestamp,
            "best_bid": book.best_bid(3),
            "best_ask": book.best_ask(3),
        }

    def _summarize_tweets(tweets):
        summary = []
        for tw in tweets or []:
            summary.append(
                {
                    "id": tw.get("tweet_id"),
                    "created_at": tw.get("created_at"),
                    "username": tw.get("username") or tw.get("name"),
                    "likes": tw.get("likes"),
                    "text": tw.get("text"),
                    "url": tw.get("url"),
                }
            )
        return summary

    def _summarize_positions(pos):
        if not pos:
            return {"summary": "flat", "positions": []}
        if isinstance(pos, dict):
            return pos
        total_yes = 0.0
        total_no = 0.0
        cleaned = []
        for p in pos:
            outcome = (p.get("outcome") or p.get("side") or "").lower()
            size = float(p.get("size", 0) or 0)
            action = (p.get("action") or p.get("side") or "").lower()
            if outcome == "yes":
                total_yes += size if action == "buy" else -size
            elif outcome == "no":
                total_no += size if action == "buy" else -size
            cleaned.append(
                {
                    "outcome": outcome,
                    "action": action,
                    "size": size,
                    "avg_price": p.get("avg_price"),
                }
            )
        return {
            "summary": {"net_yes": total_yes, "net_no": total_no},
            "positions": cleaned,
        }

    class Decision(BaseModel):
        action: str = Field(description="buy, sell, or hold")
        outcome: str = Field(description="yes or no side when trading")
        price: float = Field(description="limit price between 0 and 1 inclusive")
        size: float = Field(
            description="IOC size in contracts, must not exceed max_size"
        )

        @field_validator("action")
        @classmethod
        def _action_ok(cls, v):
            v = v.lower()
            if v not in {"buy", "sell", "hold"}:
                raise ValueError("action must be buy, sell, or hold")
            return v

        @field_validator("outcome")
        @classmethod
        def _outcome_ok(cls, v):
            v = v.lower()
            if v not in {"yes", "no"}:
                raise ValueError("outcome must be yes or no")
            return v

        @field_validator("price")
        @classmethod
        def _price_ok(cls, v):
            if v < 0 or v > 1:
                raise ValueError("price must be within [0,1]")
            return v

        @field_validator("size")
        @classmethod
        def _size_ok(cls, v):
            if v < 0:
                raise ValueError("size must be non-negative")
            return v

    client = Client(api_key=api_key)
    chat = client.chat.create(
        model="grok-4-1-fast",
        tools=[web_search(), x_search()],
    )

    prompt = (
        "You are an elite quantitative trader with 15+ years of experience specializing in binary prediction markets and derivatives trading. "
        "Your expertise spans macroeconomic analysis, sentiment analysis, orderbook dynamics, and risk management. "
        f"You are analyzing the market: {condition}\n\n"
        "TRADING MANDATE:\n"
        "- Execute IOC (Immediate-or-Cancel) limit orders only: BUY or SELL on YES/NO sides, or HOLD\n"
        "- Price constraints: [0.0, 1.0] representing probability (0% to 100%)\n"
        "- Size constraints: Must not exceed max_size AND absolutely must not exceed max_position\n"
        "- CRITICAL: Position limits are HARD LIMITS - exceeding max_position will result in trade rejection\n"
        "- Risk management: Consider position sizing relative to edge, volatility, and existing exposure\n\n"
        "DECISION FRAMEWORK:\n"
        "1. MARKET MICROSTRUCTURE: Analyze bid-ask spreads, depth, and liquidity patterns\n"
        "2. SENTIMENT SIGNALS: Extract alpha from social media, news flow, and market positioning\n"
        "3. FUNDAMENTAL CATALYSTS: Assess event probability using base rates and new information\n"
        "4. TECHNICAL FACTORS: Evaluate momentum, mean reversion signals, and volume patterns\n"
        "5. RISK-REWARD: Calculate expected value and Kelly-optimal sizing\n\n"
        "RESEARCH PROTOCOL:\n"
        "- Use web_search for breaking news, official announcements, and fundamental data\n"
        "- Use x_search for real-time sentiment, insider insights, and crowd positioning\n"
        "- Cross-reference multiple sources to avoid false signals\n"
        "- Weight recent information higher but consider base rate neglect\n\n"
        "EXECUTION GUIDELINES:\n"
        "- BUY YES: When probability > current ask price with sufficient edge\n"
        "- SELL YES: When probability < current bid price with sufficient edge\n"
        "- BUY NO: Equivalent to selling YES (when probability < (1 - ask_price))\n"
        "- SELL NO: Equivalent to buying YES (when probability > (1 - bid_price))\n"
        "- HOLD: When edge is insufficient, liquidity is poor, or uncertainty is too high\n\n"
        "POSITION MANAGEMENT:\n"
        "- ALWAYS check existing positions before sizing new trades\n"
        "- Calculate net exposure: sum of all open positions on this market\n"
        "- New trade size = min(max_size, max_position - abs(current_net_position))\n"
        "- If current position + new trade would exceed max_position: REDUCE SIZE or HOLD\n"
        "- Consider position concentration risk across correlated markets\n\n"
        "POSITION SIZING:\n"
        "- High confidence (>80%): Use 60-80% of available capacity\n"
        "- Medium confidence (60-80%): Use 30-50% of available capacity\n"
        "- Low confidence (55-60%): Use 10-20% of available capacity\n"
        "- Marginal edge (<55%): HOLD or micro-size (<10%)\n"
        "- Available capacity = min(max_size, max_position - abs(current_position))\n\n"
        "OUTPUT REQUIREMENTS:\n"
        "Return ONLY the structured decision with your reasoning embedded in the probability assessment. "
        "Be decisive but prudent. Time is money in these markets."
    )
    chat.append(system(prompt))

    book_context = {
        "yes_book": _snapshot(yes_book),
        "no_book": _snapshot(no_book),
        "max_size": max_size,
        "max_position": max_position,
        "current_positions": _summarize_positions(positions),
    }
    tweets_context = _summarize_tweets(tweet_window)

    chat.append(
        user(
            json.dumps(
                {
                    "book_state": book_context,
                    "tweets": tweets_context,
                    "instruction": "Analyze current positions and pick action buy/sell/hold and outcome yes/no. Size must respect BOTH max_size AND max_position limits. Factor in existing exposure before sizing.",
                }
            )
        )
    )

    response, parsed = chat.parse(Decision)

    action = parsed.action.lower()
    outcome = parsed.outcome.lower()
    if action == "hold":
        return IOCDecision("hold", outcome, 0.0, 0.0, response)

    size = min(parsed.size, max_size, max_position)
    return IOCDecision(action, outcome, parsed.price, size, response)
