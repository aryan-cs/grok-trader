import os
import sys
import time
from collections import deque
import threading

if __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from strategy.polymarket import Polymarket
from strategy.tweets import TweetFeed
from strategy.brain import produce_trading_decision
from strategy.account import create_client_from_env, place_order, get_orders


class Strategy:
    def __init__(
        self, market_slug, condition, max_size, max_position=None, positions=None
    ):
        self.market_slug = market_slug
        self.condition = condition
        self.max_size = max_size
        self.max_position = max_position if max_position is not None else max_size
        self.positions = positions or []

        self.yes_book = None
        self.no_book = None
        self.tweets = deque(maxlen=10)
        self.tweet_ids: set[int] = set()
        self._last_decision_ts = 0.0
        self.client = None
        self.funder = os.environ.get("POLY_FUNDER_ADDRESS")
        self.signature_type = (
            int(os.environ["POLY_SIGNATURE_TYPE"])
            if os.environ.get("POLY_SIGNATURE_TYPE") is not None
            else None
        )
        try:
            self.client = create_client_from_env(
                funder_override=self.funder, signature_type=self.signature_type
            )
        except Exception as e:
            print(f"[account][error] {e}")

    def on_new_post(self, tweet):
        tweet_id = tweet.get("tweet_id")
        if tweet_id in self.tweet_ids:
            return

        # maintain sliding window of last 10 unique tweets
        self.tweet_ids.add(tweet_id)
        self.tweets.append(tweet)
        while len(self.tweet_ids) > 10 or len(self.tweets) > 10:
            oldest = self.tweets.popleft()
            self.tweet_ids.discard(oldest.get("tweet_id"))

    def on_new_book(self, yes_book, no_book):
        def fmt(book):
            if not book:
                return "—"
            bid = book.best_bid(1)
            ask = book.best_ask(1)
            bid_s = f"{bid[0][0]:.4f}@{bid[0][1]:.0f}" if bid else "—"
            ask_s = f"{ask[0][0]:.4f}@{ask[0][1]:.0f}" if ask else "—"
            return f"{book.side}:{bid_s}/{ask_s}"

        print(f"[{self.market_slug}] {fmt(yes_book)} || {fmt(no_book)}")

        self.yes_book = yes_book
        self.no_book = no_book

        if not self.yes_book or not self.no_book:
            return

        # simple throttle to avoid hammering the model
        now = time.time()
        if now - self._last_decision_ts < 30:
            return
        self._last_decision_ts = now

        # produce trading decision
        try:
            # refresh positions via open orders snapshot
            if self.client:
                try:
                    yes_pos = get_orders(self.client, asset_id=yes_book.asset_id) or []
                    no_pos = get_orders(self.client, asset_id=no_book.asset_id) or []
                    self.positions = yes_pos + no_pos
                except Exception as e:
                    print(f"[positions][error] {e}")

            decision = produce_trading_decision(
                self.max_size,
                self.max_position,
                self.condition,
                self.yes_book,
                self.no_book,
                self.positions,
                list(self.tweets),
            )
            print(f"[decision][{self.market_slug}] {decision}")
            if decision.response:
                print(f"[grok_response] {decision.response}")

            if self.client and decision.action != "hold" and decision.size > 0:
                token_id = (
                    self.yes_book.asset_id
                    if decision.outcome == "yes"
                    else self.no_book.asset_id
                )

                # don't allow selling flat
                if decision.action == "sell" and not self.positions:
                    print(
                        "[order][skip] No inventory tracked; skipping sell while flat."
                    )
                    return

                try:
                    order_resp = place_order(
                        client=self.client,
                        token_id=token_id,
                        side=decision.action,
                        price=decision.price,
                        size=decision.size,
                    )
                    print(f"[order][placed] {order_resp}")
                except Exception as e:
                    print(f"[order][error] {e}")

            if self.client:
                try:
                    yes_open = get_orders(self.client, asset_id=yes_book.asset_id) or []
                    no_open = get_orders(self.client, asset_id=no_book.asset_id) or []
                    print(f"[open_orders] yes={len(yes_open)} no={len(no_open)}")
                    if yes_open:
                        print(f"  yes_open: {yes_open}")
                    if no_open:
                        print(f"  no_open: {no_open}")
                except Exception as e:
                    print(f"[open_orders][error] {e}")
        except Exception as e:
            print(f"[decision][error] {e}")


if __name__ == "__main__":
    event_slug = "spacex-ipo-closing-market-cap"
    market_slug = "will-spacex-not-ipo-by-december-31-2027"
    condition = "Comfort trading the SpaceX IPO market; focus on asymmetric buy/sell setups around IPO timing."

    my_strategy = Strategy(market_slug, condition, max_size=5, max_position=5)
    feed = Polymarket(event_slug, strategy=my_strategy, market_slug=market_slug)
    tweet_feed = TweetFeed(
        market_slug=market_slug,
        min_likes=5,
        strategy=my_strategy,
        poll_interval=30,
        max_results=20,
    )

    def poll_tweets():
        while True:
            try:
                tweet_feed.run_once()
            except Exception as e:
                print(f"[tweets] error: {e}")
            time.sleep(tweet_feed.poll_interval)

    try:
        threading.Thread(target=poll_tweets, daemon=True).start()
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        feed.close()
