import os
import tweepy
from dotenv import load_dotenv
from pathlib import Path
from xai_sdk import Client

verbose = False

def generate_query(source, slug):
    """
    Generate a query for the given source using Grok (XAI API).
    - For 'x': returns a string query with AND/OR and keywords.
    - For 'reddit': returns a JSON object with 'subreddits' (list) and 'keywords' (list) for Reddit API.
    - For 'reuters': returns a string query for Google News RSS.
    """
    xai_api_key = os.getenv("XAI_API_KEY")
    if not xai_api_key:
        raise RuntimeError("XAI_API_KEY not found in environment")
    client = Client(api_key=xai_api_key)
    from xai_sdk.chat import user, system

    # Compose system and user messages for Grok
    if source == 'x':
        system_msg = system("You are an expert at writing boolean queries for the X (Twitter) API. Given a market slug, generate a boolean query string using AND/OR and relevant keywords, hashtags, and cashtags. Return only the query string. Here is an example: '(Lando Norris OR #LandoNorris OR #LN4) (win OR winner OR victory OR champion OR #F1Winner) (race OR Grand Prix OR #Formula1 OR #F1)'")
        user_msg = user(f"Market slug: {slug}")
        chat = client.chat.create(model="grok-4-1-fast-reasoning", messages=[system_msg])
        chat.append(user_msg)
        resp = chat.sample()
        return getattr(resp, 'content', None)
    elif source == 'reddit':
        system_msg = system("You are an expert at writing Reddit search queries. Given a market slug, return a JSON object with two fields: 'subreddits' (list of relevant subreddits) and 'keywords' (list of relevant keywords). Return only the JSON object.")
        user_msg = user(f"Market slug: {slug}")
        chat = client.chat.create(model="grok-4-1-fast-reasoning", messages=[system_msg])
        chat.append(user_msg)
        resp = chat.sample()
        import json
        try:
            return json.loads(getattr(resp, 'content', '{}'))
        except Exception:
            return {}
    elif source == 'reuters':
        system_msg = system("You are an expert at writing Google News queries for Reuters. Given a market slug, generate a query string suitable for Google News RSS search, using relevant keywords. Return only the query string.")
        user_msg = user(f"Market slug: {slug}")
        chat = client.chat.create(model="grok-4-1-fast-reasoning", messages=[system_msg])
        chat.append(user_msg)
        resp = chat.sample()
        return getattr(resp, 'content', None)
    return None
    

class TweetFeed:
    def __init__(self, market_slug, min_likes, strategy, poll_interval=60, max_results=10):
        """
        market_slug: str - Used as keywords for tweet search
        min_likes: int - Minimum likes for tweets
        strategy: object - Must have on_new_post(tweet) method
        poll_interval: int - How often to poll for new tweets (seconds)
        max_results: int - Max tweets per poll
        """
        self.market_slug = market_slug
        self.min_likes = min_likes
        self.strategy = strategy
        self.poll_interval = poll_interval
        self.max_results = max_results
        self.last_seen_ids = set()

        project_root = Path(__file__).resolve().parent.parent
        load_dotenv(project_root / '.env')
        self.bearer_token = os.getenv("X_BEARER_TOKEN")
        if not self.bearer_token:
            raise RuntimeError("X_BEARER_TOKEN not found in .env file")
        self.client = tweepy.Client(bearer_token=self.bearer_token)

    def build_query(self):
        # keywords = self.market_slug.split('-') if self.market_slug else []
        # query = f"({' OR '.join(keywords)}) lang:en -is:retweet"
        # return query
        return generate_query('x', self.market_slug) + "-is:retweet lang:en"

    def fetch_and_process(self):
        query = self.build_query()
        # print(query)
        response = self.client.search_recent_tweets(
            query=query,
            max_results=self.max_results,
            tweet_fields=['created_at', 'public_metrics', 'lang', 'author_id'],
            expansions=['author_id'],
            user_fields=['username', 'name']
        )
        users = {u.id: u for u in response.includes['users']} if response.includes and 'users' in response.includes else {}
        new_tweets = []
        if response.data:
            # print(f"Fetched {len(response.data)} tweets for query: {query}")
            for tweet in response.data:
                if tweet.id in self.last_seen_ids:
                    continue
                metrics = tweet.public_metrics or {}
                if metrics.get('like_count', 0) < self.min_likes:
                    # print(f"Skipping tweet {tweet.id} with {metrics.get('like_count', 0)} likes (min required: {self.min_likes})")
                    continue
                user = users.get(tweet.author_id)
                tweet_obj = {
                    "tweet_id": tweet.id,
                    "created_at": tweet.created_at.isoformat() if tweet.created_at else "",
                    "author_id": tweet.author_id,
                    "username": user.username if user else "unknown",
                    "name": user.name if user else "unknown",
                    "text": tweet.text,
                    "likes": metrics.get('like_count', 0),
                    "retweets": metrics.get('retweet_count', 0),
                    "replies": metrics.get('reply_count', 0),
                    "quotes": metrics.get('quote_count', 0),
                    "impressions": metrics.get('impression_count', 0),
                    "lang": tweet.lang,
                    "url": f"https://x.com/{user.username}/status/{tweet.id}" if user else ""
                }
                self.strategy.on_new_post(tweet_obj)
                new_tweets.append(tweet_obj)
                self.last_seen_ids.add(tweet.id)
        return new_tweets

    def run_once(self):
        return self.fetch_and_process()


def __main__():
    class PrintStrategy:
        def on_new_post(self, tweet):
            print(f"{tweet['url']} - Likes: {tweet['likes']}")

    feed = TweetFeed(
        market_slug="will-space-x-ipo-this-year",
        min_likes=0,
        strategy=PrintStrategy(),
        poll_interval=60,
        max_results=10
    )

    new_tweets = feed.run_once()
    # print(f"Fetched {len(new_tweets)} new tweets")

if __name__ == "__main__":
    __main__()