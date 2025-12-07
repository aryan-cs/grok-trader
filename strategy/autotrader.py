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
        print(
            f"[{self.market_slug}] {yes_book.best_bid(1)}@{yes_book.best_ask(1)} || {no_book.best_bid(1)}@{no_book.best_ask(1)}"
        )

        self.yes_book = yes_book
        self.no_book = no_book

        if not self.yes_book or not self.no_book:
            return

        # simple throttle to avoid hammering the model
        now = time.time()
        if now - self._last_decision_ts < 30:
            return
        self._last_decision_ts = now

        # produce tradng decision
        try:
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
