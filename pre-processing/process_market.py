import os
import sys
import json
import re
import argparse
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import tool, user, system

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'post-processing')))

from datafeed.x.x import load_tweets, fetch_tweets
from datafeed.reddit.reddit import load_posts, fetch_posts
from datafeed.reuters.reuters import load_articles, fetch_articles
from process_data import normalize_data, analyze_text

load_dotenv()

try:
    client = Client(api_key=os.getenv("XAI_API_KEY"))
except Exception as e:
    print(f"Error initializing xAI Client: {e}")
    client = None

def generate_search_terms(market: str, client):
    """
    Generates search keywords and subreddits based on the market question using Grok.
    """
    try:
        prompt = f"""
        Given the prediction market question: "{market}", provide a JSON object with:
        1. "keywords": A list of 3-5 specific search keywords (strings).
        2. "subreddits": A list of 2-3 relevant subreddits (strings, without 'r/').
        
        Example output:
        {{
            "keywords": ["Lando Norris", "McLaren", "F1 Driver Championship"],
            "subreddits": ["formula1", "grandprix"]
        }}
        """
        
        chat = client.chat.create(model="grok-4-1-fast-non-reasoning")
        chat.append(system("You are a helpful research assistant."))
        chat.append(user(prompt))
        
        response = chat.sample()
        content = response.content
        
        if "```" in content:
            match = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
            if match:
                content = match.group(1)
                
        return json.loads(content.strip())
    except Exception as e:
        print(f"Error generating search terms: {e}")
        return {"keywords": [], "subreddits": []}

def get_market_sentiment(market: str, contracts: list = None, start_date: str = None, end_date: str = None, limit: int = 20, verbose: bool = False):
    """
    Fetches and analyzes social media and news data for a specific market.
    
    Args:
        market (str): The market question or topic (e.g., "Will Lando Norris win?").
        contracts (list, optional): List of contract names to filter for.
        start_date (str, optional): ISO 8601 start date for data fetch.
        end_date (str, optional): ISO 8601 end date for data fetch.
        limit (int, optional): Max number of items to fetch per source. Default 20.
        verbose (bool, optional): Whether to print progress updates.
        
    Returns:
        list: A list of relevant, analyzed items with sentiment and reasoning.
    """
    if verbose:
        print(f"Fetching data for market: {market}")
        if start_date:
            print(f"Start Date: {start_date}")
        if end_date:
            print(f"End Date: {end_date}")
        
    tweets = []
    posts = []
    articles = []

    if client:
        if verbose:
            print("Generating search terms with Grok...")
        search_config = generate_search_terms(market, client)
        keywords = search_config.get("keywords", [])
        subreddits = search_config.get("subreddits", [])
        
        if verbose:
            print(f"Keywords: {keywords}")
            print(f"Subreddits: {subreddits}")
            
        if keywords:
            if verbose:
                print("Fetching fresh Tweets...")
            try:
                fetched = fetch_tweets(keywords=keywords, start_time=start_date, end_time=end_date, max_results=limit)
                if fetched:
                    tweets = fetched
            except Exception as e:
                print(f"Error fetching tweets: {e}")

            if verbose:
                print("Fetching fresh Reddit posts...")
            try:
                fetched = fetch_posts(keywords=keywords, subreddits=subreddits, limit=limit)
                if fetched:
                    posts = fetched
            except Exception as e:
                print(f"Error fetching reddit posts: {e}")

            if verbose:
                print("Fetching fresh Reuters articles...")
            try:
                fetched = fetch_articles(keywords=keywords, limit=limit)
                if fetched:
                    articles = fetched
            except Exception as e:
                print(f"Error fetching articles: {e}")
    else:
        print("Warning: xAI Client not initialized, skipping fresh data fetch.")
    
    if verbose:
        print(f"Loaded {len(tweets)} tweets, {len(posts)} posts, {len(articles)} articles")
    
    items = normalize_data(tweets, posts, articles)
    
    if verbose:
        print(f"Normalized {len(items)} items. Starting analysis...")
    
    relevant_items = []
    
    for i, item in enumerate(items):

        if not item['text'].strip():
            continue
            
        if verbose:
            print(f"[{i+1}/{len(items)}] Analyzing item from {item['source']}...")

        analysis = analyze_text(item['text'], item['source'], market=market)
        
        if analysis.get('is_useful'):
            if verbose:
                print(f"  -> Useful! Sentiment: {analysis.get('sentiment')}")
            relevant_items.append({
                "source": item['source'],
                "content": item['text'],
                "sentiment": analysis.get('sentiment'),
                "reasoning": analysis.get('reason')
            })
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
                "description": "The market question or topic (e.g., 'Will Lando Norris win?')."
            },
            "contracts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of contract names to filter for."
            },
            "start_date": {
                "type": "string",
                "description": "ISO 8601 start date for data fetch (e.g., '2023-12-01T00:00:00Z')."
            },
            "end_date": {
                "type": "string",
                "description": "ISO 8601 end date for data fetch."
            },
            "limit": {
                "type": "integer",
                "description": "Max number of items to fetch per source. Default 20."
            }
        },
        "required": ["market"]
    }
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch and analyze market sentiment.")
    parser.add_argument("market", nargs="?", default="Will AI take over the world?", help="The market question to analyze")
    parser.add_argument("--start-date", help="ISO 8601 start date")
    parser.add_argument("--end-date", help="ISO 8601 end date")
    parser.add_argument("--limit", type=int, default=20, help="Max items per source")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    res = get_market_sentiment(args.market, start_date=args.start_date, end_date=args.end_date, limit=args.limit, verbose=args.verbose)
    print(json.dumps(res, indent=2))
