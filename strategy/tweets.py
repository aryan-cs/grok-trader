class TweetFeed:
    def __init__(self, market_slug, min_likes, strategy):
        # This should subscribe to tweets that have min_likes and have keywords related to market_slug
        # Every time a new tweet comes through, this should call strategy.on_new_post(tweet)
        pass
