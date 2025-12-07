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


def produce_trading_decision(max_size, condition, yes_book, no_book, tweet_window):
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
        "You are an execution assistant trading binary prediction markets. "
        "Decide whether to BUY or SELL the YES or NO side using an IOC limit order, or HOLD. "
        "Use web_search and x_search tools if extra signal is needed. "
        "Constrain size to max_size and price to [0,1]. "
        "Return only the structured decision. "
        f"Market condition: {condition}"
    )
    chat.append(system(prompt))

    book_context = {
        "yes_book": _snapshot(yes_book),
        "no_book": _snapshot(no_book),
        "max_size": max_size,
    }
    tweets_context = _summarize_tweets(tweet_window)

    chat.append(
        user(
            json.dumps(
                {
                    "book_state": book_context,
                    "tweets": tweets_context,
                    "instruction": "Pick action buy/sell/hold and outcome yes/no; suggest an IOC price and size (<= max_size).",
                }
            )
        )
    )

    response, parsed = chat.parse(Decision)

    action = parsed.action.lower()
    outcome = parsed.outcome.lower()
    if action == "hold":
        return IOCDecision("hold", outcome, 0.0, 0.0, response)

    size = min(parsed.size, max_size)
    return IOCDecision(action, outcome, parsed.price, size, response)
