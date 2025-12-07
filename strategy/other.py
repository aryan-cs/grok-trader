from dotenv import load_dotenv
load_dotenv()

import requests
import xml.etree.ElementTree as ET
import urllib.parse
import os
from xai_sdk import Client

def get_reddit_data(slug, max_results=10):
    query = generate_query('reddit', slug)
    if not query or not isinstance(query, dict):
        return []
    subreddits = query.get('subreddits', ['all'])
    keywords = query.get('keywords', slug.split('-'))
    headers = {'User-Agent': os.getenv('REDDIT_USER_AGENT', 'python:grok-trader:v1.0 (by /u/yourusername)')}
    sub_string = '+'.join(subreddits)
    base_url = f"https://www.reddit.com/r/{sub_string}" if subreddits else "https://www.reddit.com/r/all"
    params = {'limit': max_results}
    if keywords:
        search_query = ' '.join(keywords)
        url = f"{base_url}/search.json"
        params['q'] = search_query
        params['sort'] = 'relevance'
        params['t'] = 'all'
        params['restrict_sr'] = 1 if subreddits else 0
    else:
        url = f"{base_url}/relevance.json"
        params['t'] = 'all'
    try:
        resp = requests.get(url, headers=headers, params=params)
        data = resp.json()
        posts_data = data.get('data', {}).get('children', [])
        links = [f"https://reddit.com{item['data'].get('permalink')}" for item in posts_data if 'data' in item and 'permalink' in item['data']]
        return links
    except Exception:
        return []

def get_reuter_data(slug, max_results=10):
    keywords = slug.split('-')
    query_str = ' '.join(keywords)
    full_query = f"site:reuters.com {query_str}"
    encoded_query = urllib.parse.quote(full_query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    try:
        resp = requests.get(url)
        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else []
        links = [item.find("link").text for item in items[:max_results] if item.find("link") is not None]
        return links
    except Exception:
        return []


def get_x_data(slug, max_results=10, verbose=False):
    """
    Fetch recent tweets for a slug using Grok-generated query.
    Returns a list of tweet URLs using the X API directly (no tweepy).
    """
    import requests
    query = generate_query('x', slug)
    if not query or not isinstance(query, str):
        if verbose:
            print("DEBUG: generate_query returned no valid query")
        return []

    bearer = os.getenv('X_BEARER_TOKEN')
    if not bearer:
        if verbose:
            print("DEBUG: X_BEARER_TOKEN not set")
        return []

    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {bearer}"}
    params = {
        "query": query,
        "max_results": min(max(10, max_results), 100),
        "tweet.fields": "created_at,public_metrics,lang,author_id",
        "expansions": "author_id",
        "user.fields": "username,name"
    }
    try:
        if verbose:
            print(f"DEBUG: X API query={query!r}, max_results={params['max_results']}")
        resp = requests.get(url, headers=headers, params=params)
        if verbose:
            print(f"DEBUG: X API status={resp.status_code}")
        if resp.status_code != 200:
            if verbose:
                print(f"DEBUG: X API error: {resp.text}")
            return []
        data = resp.json()
        tweets = data.get('data', [])
        users = {u['id']: u for u in data.get('includes', {}).get('users', [])}
        links = []
        for tweet in tweets:
            user = users.get(tweet.get('author_id'))
            if user and 'username' in user:
                links.append(f"https://x.com/{user['username']}/status/{tweet['id']}")
            else:
                links.append(f"https://x.com/i/web/status/{tweet['id']}")
        return links
    except Exception as e:
        if verbose:
            import traceback
            traceback.print_exc()
        return []
    
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

if __name__ == "__main__":
    
    test_slug = "fed-decision-in-january"
    
    x_query = generate_query('x', test_slug)
    print(f"\nX Query: {x_query}")
    
    reddit_query = generate_query('reddit', test_slug)
    print(f"\nReddit Query: {reddit_query}")
    
    reuters_query = generate_query('reuters', test_slug)
    print(f"\nReuters Query: {reuters_query}")
    
    x_links = get_x_data("fed-decision-in-january", max_results=5)
    print("X Links:")
    for links in x_links:
        print(links)
    
    reddit_links = get_reddit_data("fed-decision-in-january", max_results=5)
    print("Reddit Links:")
    for link in reddit_links:
        print(link)
    
    reuter_links = get_reuter_data("fed-decision-in-january", max_results=5)
    print("\nReuters Links:")
    for link in reuter_links:
        print(link)
