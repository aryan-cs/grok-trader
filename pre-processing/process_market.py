import os
import sys
import json
import re
import argparse
import asyncio
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import tool, user, system

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "post-processing"))
)

from datafeed.x.x import load_tweets, fetch_tweets
from datafeed.reddit.reddit import load_posts, fetch_posts
from datafeed.reuters.reuters import load_articles, fetch_articles
from process_data import normalize_data, analyze_text

load_dotenv()

MODEL_NAME = "grok-4-1-fast-non-reasoning"

try:
    client = Client(api_key=os.getenv("XAI_API_KEY"))
except Exception as e:
    print(f"Error initializing xAI Client: {e}")
    client = None

PROMPT_FILE = os.path.join(
    os.path.dirname(__file__), "prompts", "generate_search_terms.txt"
)


def _send_thinking_message(websocket, message: str, loop):
    """Helper to send thinking message from sync context via event loop"""
    if websocket and loop:
        asyncio.run_coroutine_threadsafe(
            websocket.send_json(
                {
                    "message_type": "research",
                    "type": "thinking",
                    "content": message,
                }
            ),
            loop,
        )


def generate_search_terms(market: str, client):
    try:
        with open(PROMPT_FILE, "r") as f:
            prompt_template = f.read()
        prompt = prompt_template.format(market=market)

        chat = client.chat.create(model=MODEL_NAME)
        chat.append(system("You are a helpful research assistant."))
        chat.append(user(prompt))

        response = chat.sample()
        content = response.content

        if "```" in content:
            match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
            if match:
                content = match.group(1)

        return json.loads(content.strip())
    except Exception as e:
        print(f"Error generating search terms: {e}")
        return {"keywords": [], "subreddits": []}


def get_market_sentiment(
    market: str = None,
    contracts: list = None,
    start_date: str = None,
    end_date: str = None,
    limit: int = 20,
    verbose: bool = False,
    accounts: list = None,
    on_item=None,
    websocket=None,
    loop=None,
):
    """
    Fetches and analyzes social media and news data for a specific market.

    Args:
        market (str, optional): The market question or topic. If None, assumes general feed.
        contracts (list, optional): List of contract names to filter for.
        start_date (str, optional): ISO 8601 start date for data fetch.
        end_date (str, optional): ISO 8601 end date for data fetch.
        limit (int, optional): Max number of items to fetch per source. Default 20.
        verbose (bool, optional): Whether to print progress updates.
        accounts (list, optional): List of X accounts to prioritize/filter by.
        on_item (callable, optional): Callback function to be called with each analyzed item.
        websocket (optional): WebSocket connection to send progress updates.
        loop (optional): Event loop for sending async messages from thread.

    Returns:
        list: A list of relevant, analyzed items with sentiment and reasoning.
    """
    if verbose:
        print(f"Fetching data for market: {market if market else 'General Feed'}")
        if start_date:
            print(f"Start Date: {start_date}")
        if end_date:
            print(f"End Date: {end_date}")
        if accounts:
            print(f"Target Accounts: {accounts}")

    tweets = []
    posts = []
    articles = []

    if client:
        keywords = []
        subreddits = []

        if market:
            print(f"Generating search terms with Grok for: {market}")
            search_config = generate_search_terms(market, client)
            keywords = search_config.get("keywords", [])
            subreddits = search_config.get("subreddits", [])

            # Ensure we have keywords
            if not keywords:
                print("⚠️ No keywords generated, using market title words.")
                keywords = [w for w in market.split() if len(w) > 3]

            print(f"Keywords (Phrases): {keywords}")
            print(f"Subreddits: {subreddits}")

        if keywords or accounts:
            _send_thinking_message(websocket, "Fetching tweets from X...", loop)
            print("Fetching fresh Tweets...")
            # We request up to 100 tweets to ensure we find enough that meet the min_likes criteria
            fetch_limit = 100
            try:
                if accounts:
                    fetched = fetch_tweets(
                        keywords=keywords,
                        usernames=accounts,
                        start_time=start_date,
                        end_time=end_date,
                        max_results=fetch_limit,
                        logic="OR",
                        min_likes=5,
                    )
                    if fetched:
                        tweets.extend(fetched)

                if keywords:
                    if accounts:
                        print("Fetching general Tweets (crowd sentiment)...")

                    # Try with phrases first (High Relevance)
                    fetched_general = fetch_tweets(
                        keywords=keywords,
                        start_time=start_date,
                        end_time=end_date,
                        max_results=fetch_limit,
                        logic="OR",
                        min_likes=30,
                    )
                    if fetched_general:
                        existing_ids = {t["url"] for t in tweets}
                        for t in fetched_general:
                            if t["url"] not in existing_ids:
                                tweets.append(t)
            except Exception as e:
                print(f"Error fetching tweets: {e}")

        if verbose:
            print(
                f"Fetched counts — tweets: {len(tweets)}, reddit: {len(posts)}, articles: {len(articles)}"
            )
            if (keywords or accounts) and len(tweets) == 0:
                print(
                    "⚠️ No tweets fetched. Check X_BEARER_TOKEN, query recency (recent search ~7 days), or consider full_archive access."
                )

        if keywords:
            _send_thinking_message(websocket, "Fetching posts from Reddit...", loop)
            print("Fetching fresh Reddit posts...")
            try:
                fetched = fetch_posts(
                    keywords=keywords, subreddits=subreddits, limit=limit, logic="OR"
                )
                if fetched:
                    posts = fetched
            except Exception as e:
                print(f"Error fetching reddit posts: {e}")

            _send_thinking_message(websocket, "Fetching articles from Reuters...", loop)
            print("Fetching fresh Reuters articles...")
            try:
                fetched = fetch_articles(
                    keywords=keywords,
                    limit=limit,
                    start_time=start_date,
                    end_time=end_date,
                    logic="OR",
                )
                if fetched:
                    articles = fetched
            except Exception as e:
                print(f"Error fetching articles: {e}")
    else:
        print("Warning: xAI Client not initialized, skipping fresh data fetch.")

    if verbose:
        print(
            f"Loaded {len(tweets)} tweets, {len(posts)} posts, {len(articles)} articles"
        )

    # Send summary of what was fetched
    summary = f"Found {len(tweets)} tweets, {len(posts)} Reddit posts, {len(articles)} Reuters articles"
    _send_thinking_message(websocket, summary, loop)

    _send_thinking_message(websocket, "Analyzing sentiment...", loop)
    items = normalize_data(tweets, posts, articles)

    if verbose:
        print(f"Normalized {len(items)} items. Starting analysis...")

    relevant_items = []

    for i, item in enumerate(items):

        if not item["text"].strip():
            continue

        if verbose:
            print(f"[{i+1}/{len(items)}] Analyzing item from {item['source']}...")

        analysis = analyze_text(item["text"], item["source"], market=market)

        # Only include useful items
        is_useful = analysis.get("is_useful")

        if is_useful:
            if verbose:
                print(f"  -> Useful! Sentiment: {analysis.get('sentiment')}")

            result_item = {
                "source": item["source"],
                "content": item["text"],
                "sentiment": analysis.get("sentiment"),
                "reasoning": analysis.get("reason"),
                "meta": item.get("meta"),
                "link": (
                    item.get("original", {}).get("url")
                    if isinstance(item.get("original"), dict)
                    else None
                ),
            }
            relevant_items.append(result_item)
            if on_item:
                on_item(result_item)
        elif verbose:
            print(f"  -> Not useful. Reason: {analysis.get('reason')}")

    return relevant_items


get_market_sentiment_tool = tool(
    name="get_market_sentiment",
    description="Fetches and analyzes social media and news data for a specific market to provide sentiment and reasoning.",
    parameters={
        "type": "object",
        "properties": {
            "market": {
                "type": "string",
                "description": "The market question or topic (e.g., 'Will Lando Norris win?').",
            },
            "contracts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of contract names to filter for.",
            },
            "start_date": {
                "type": "string",
                "description": "ISO 8601 start date for data fetch (e.g., '2023-12-01T00:00:00Z').",
            },
            "end_date": {
                "type": "string",
                "description": "ISO 8601 end date for data fetch.",
            },
            "limit": {
                "type": "integer",
                "description": "Max number of items to fetch per source. Default 20.",
            },
        },
        "required": ["market"],
    },
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch and analyze market sentiment.")
    parser.add_argument(
        "market",
        nargs="?",
        default="Will AI take over the world?",
        help="The market question to analyze",
    )
    parser.add_argument("--start-date", help="ISO 8601 start date")
    parser.add_argument("--end-date", help="ISO 8601 end date")
    parser.add_argument("--limit", type=int, default=20, help="Max items per source")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    res = get_market_sentiment(
        args.market,
        start_date=args.start_date,
        end_date=args.end_date,
        limit=args.limit,
        verbose=args.verbose,
    )
    print(json.dumps(res, indent=2))
