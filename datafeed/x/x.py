import tweepy
import os
import csv
import re
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box

# Load .env from project root
root_dir = Path(__file__).resolve().parents[2]
load_dotenv(root_dir / '.env')

BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
USE_TEST_DATA = False
CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tweets_data.csv")
MIN_TWEETS = 10; """ THIS IS AN API LIMITATION NOT DESIGN CHOICE """

console = Console()

class User:
    def __init__(self, username, name):
        self.username = username
        self.name = name

class Tweet:
    def __init__(self, id, text, created_at, metrics, lang, author_id):
        self.id = id
        self.text = text
        self.created_at = created_at
        self.public_metrics = metrics
        self.lang = lang
        self.author_id = author_id

def save_to_csv(tweet, user):
    try:
        file_exists = os.path.isfile(CSV_FILE)
        
        # Check for duplicates
        if file_exists:
            try:
                with open(CSV_FILE, mode='r', encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                    for row in reader:
                        if row.get("tweet_id") == str(tweet.id):
                            # console.print(f"[dim]Skipping duplicate tweet {tweet.id}[/dim]")
                            return
            except Exception as e:
                console.print(f"[red]Error reading CSV for duplicates: {e}[/red]")
        
        with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            
            if not file_exists:
                writer.writerow([
                    "tweet_id", "created_at", "author_id", "username", "name", 
                    "text", "likes", "retweets", "replies", "quotes", "impressions", "lang", "url"
                ])
                
            metrics = tweet.public_metrics or {}
            url = f"https://x.com/{user.username}/status/{tweet.id}" if user else ""
            
            # Ensure created_at is a string
            created_at_str = tweet.created_at.isoformat() if hasattr(tweet.created_at, 'isoformat') else str(tweet.created_at)

            writer.writerow([
                tweet.id,
                created_at_str,
                tweet.author_id,
                user.username if user else "Unknown",
                user.name if user else "Unknown",
                tweet.text.replace('\n', ' '),
                metrics.get('like_count', 0),
                metrics.get('retweet_count', 0),
                metrics.get('reply_count', 0),
                metrics.get('quote_count', 0),
                metrics.get('impression_count', 0),
                tweet.lang,
                url
            ])
            # console.print(f"[dim]Saved tweet {tweet.id} to CSV[/dim]")
            
    except Exception as e:
        console.print(f"[bold red]Error saving to CSV:[/bold red] {e}")

def display_tweet(tweet, user):
    
    if user:
        author_text = Text()
        author_text.append(f"@{user.username}", style=f"bold cyan link=https://x.com/{user.username}")
        author_text.append(f" ({user.name})", style="bold white")
        url = f"https://x.com/{user.username}/status/{tweet.id}"
    else:
        author_text = Text("Unknown User", style="bold red")
        url = "N/A"

    tweet_text_content = Text()
    parts = re.split(r'(@\w+)', tweet.text)
    for part in parts:
        if part.startswith('@') and len(part) > 1:
            handle = part[1:]
            tweet_text_content.append(part, style=f"bold cyan link=https://x.com/{handle}")
        else:
            tweet_text_content.append(part, style="white")

    metrics = tweet.public_metrics or {}
    
    if isinstance(tweet.created_at, str):
        try:
            dt = datetime.fromisoformat(tweet.created_at.replace('Z', '+00:00'))
            date_str = dt.strftime('%I:%M:%S %p %m/%d/%Y').lower()
        except ValueError:
            date_str = tweet.created_at
    else:
        date_str = tweet.created_at.strftime('%I:%M:%S %p %m/%d/%Y').lower()

    metrics_line = (
        f"❤️  {metrics.get('like_count', 0)}  "
        f"🔁  {metrics.get('retweet_count', 0)}  "
        f"💬  {metrics.get('reply_count', 0)}  "
        f"👁️  {metrics.get('impression_count', 0)} "
        f"📅  {date_str}"
    )

    content = Group(
        author_text,
        Text(" "),
        tweet_text_content,
        Text(" "),
        Text(metrics_line, style="dim"),
        Text(url, style=f"blue underline link={url}")
    )

    panel = Panel(
        content,
        border_style="white",
        box=box.HORIZONTALS,
        expand=True,
        padding=(0, 0)
    )
    console.print(panel)

def load_from_csv():
    if not os.path.exists(CSV_FILE):
        console.print(f"[bold red]Error:[/bold red] {CSV_FILE} not found.")
        return

    console.print(f"[bold yellow]Loading tweets from {CSV_FILE}...[/bold yellow]\n")
    
    with open(CSV_FILE, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        count = 0
        for row in reader:
            user = User(
                username=row.get("username", "Unknown"),
                name=row.get("name", "Unknown")
            )
            
            metrics = {
                "like_count": int(row.get("likes", 0)),
                "retweet_count": int(row.get("retweets", 0)),
                "reply_count": int(row.get("replies", 0)),
                "quote_count": int(row.get("quotes", 0)),
                "impression_count": int(row.get("impressions", 0))
            }
            
            tweet = Tweet(
                id=row.get("tweet_id"),
                text=row.get("text"),
                created_at=row.get("created_at"),
                metrics=metrics,
                lang=row.get("lang"),
                author_id=row.get("author_id")
            )
            
            display_tweet(tweet, user)
            count += 1
            
        console.print(f"\n[bold green]Displayed {count} tweets from CSV.[/bold green]")

def build_query(keywords=None, usernames=None, logic="AND", min_likes=0, min_retweets=0, entities=None, lang="en"):
    parts = []
    
    if keywords:
        join_op = " OR " if logic.upper() == "OR" else " "
        parts.append(f"({' '.join(keywords)})" if logic.upper() == "AND" else f"({' OR '.join(keywords)})")
            
    if usernames:
        user_queries = [f"from:{u}" for u in usernames]
        parts.append(f"({' OR '.join(user_queries)})")
        
    if entities:
        entity_queries = [f'entity:"{e}"' for e in entities]
        parts.append(f"({' OR '.join(entity_queries)})")
        
    # Note: min_faves and min_retweets are not supported in standard v2 recent search query
    # We will filter these client-side instead.
        
    parts.append(f"lang:{lang}")
    parts.append("-is:retweet")
    
    return " ".join(parts)

def fetch_tweets(keywords=None, 
                 usernames=None, 
                 start_time=None, 
                 end_time=None, 
                 logic="OR", 
                 min_likes=0, 
                 min_retweets=0, 
                 entities=None, 
                 max_results=10,
                 full_archive=False):
    """
    Fetches tweets based on advanced criteria.
    
    Args:
        keywords (list): List of keywords to search for.
        usernames (list): List of usernames to search from.
        start_time (str): ISO 8601 start time (e.g., "2023-12-01T00:00:00Z").
        end_time (str): ISO 8601 end time.
        logic (str): "AND" or "OR" for combining keywords.
        min_likes (int): Minimum number of likes.
        min_retweets (int): Minimum number of retweets.
        entities (list): List of entities to search for.
        max_results (int): Number of tweets to return (10-100).
        full_archive (bool): Whether to search the full archive (required for tweets older than 7 days).
    """
    if not BEARER_TOKEN:
        console.print("[bold red]Error:[/bold red] X_BEARER_TOKEN not found in .env file")
        return

    client = tweepy.Client(bearer_token=BEARER_TOKEN)
    
    query = build_query(keywords, usernames, logic, min_likes, min_retweets, entities)
    console.print(f"[bold yellow]Generated Query:[/bold yellow] {query}\n")

    try:
        # Select the appropriate endpoint
        search_function = client.search_all_tweets if full_archive else client.search_recent_tweets
        endpoint_name = "Full Archive Search" if full_archive else "Recent Search"
        console.print(f"[dim]Using endpoint: {endpoint_name}[/dim]")

        response = search_function(
            query=query, 
            start_time=start_time,
            end_time=end_time,
            max_results=max_results,
            tweet_fields=['created_at', 'public_metrics', 'lang', 'author_id'],
            expansions=['author_id'],
            user_fields=['username', 'name', 'public_metrics']
        )

        # Auto-Retry Logic: If no results and logic is AND, try OR
        if not response.data and logic.upper() == "AND" and keywords and len(keywords) > 1:
            console.print("[bold yellow]No results with AND logic. Retrying with OR logic...[/bold yellow]")
            query = build_query(keywords, usernames, "OR", min_likes, min_retweets, entities)
            response = search_function(
                query=query, 
                start_time=start_time,
                end_time=end_time,
                max_results=max_results,
                tweet_fields=['created_at', 'public_metrics', 'lang', 'author_id'],
                expansions=['author_id'],
                user_fields=['username', 'name', 'public_metrics']
            )

        # Auto-Retry Logic: If still no results and we have many keywords, try simplified query (first 3 keywords)
        if not response.data and keywords and len(keywords) > 3:
            console.print("[bold yellow]No results. Retrying with simplified keywords (first 3)...[/bold yellow]")
            simple_keywords = keywords[:3]
            query = build_query(simple_keywords, usernames, "OR", min_likes, min_retweets, entities)
            response = search_function(
                query=query, 
                start_time=start_time,
                end_time=end_time,
                max_results=max_results,
                tweet_fields=['created_at', 'public_metrics', 'lang', 'author_id'],
                expansions=['author_id'],
                user_fields=['username', 'name', 'public_metrics']
            )

        fetched_tweets = []
        if response.data:
            users = {u.id: u for u in response.includes['users']} if response.includes else {}

            for tweet in response.data:
                # Client-side filtering for metrics (since API doesn't support it in query)
                likes = tweet.public_metrics.get('like_count', 0)
                retweets = tweet.public_metrics.get('retweet_count', 0)
                
                if likes < min_likes or retweets < min_retweets:
                    continue

                user = users.get(tweet.author_id)
                
                display_tweet(tweet, user)
                
                save_to_csv(tweet, user)
                
                # Prepare dict for return
                fetched_tweets.append({
                    "tweet_id": tweet.id,
                    "created_at": tweet.created_at.isoformat() if tweet.created_at else "",
                    "author_id": tweet.author_id,
                    "username": user.username if user else "unknown",
                    "name": user.name if user else "unknown",
                    "text": tweet.text,
                    "likes": tweet.public_metrics.get('like_count', 0),
                    "retweets": tweet.public_metrics.get('retweet_count', 0),
                    "replies": tweet.public_metrics.get('reply_count', 0),
                    "quotes": tweet.public_metrics.get('quote_count', 0),
                    "impressions": tweet.public_metrics.get('impression_count', 0),
                    "lang": tweet.lang,
                    "url": f"https://twitter.com/{user.username}/status/{tweet.id}" if user else ""
                })
            
            console.print(f"\n[bold green]Success![/bold green] Processed {len(fetched_tweets)} tweets (filtered from {len(response.data)} raw) to {CSV_FILE}")
        else:
            console.print("[bold red]No tweets found matching criteria.[/bold red]")
            
        return fetched_tweets

    except Exception as e:
        console.print(f"[bold red]An error occurred:[/bold red] {e}")
        return []

def load_tweets(keywords=None, 
                        usernames=None, 
                        start_time=None, 
                        end_time=None, 
                        logic="OR", 
                        min_likes=0, 
                        min_retweets=0, 
                        lang=None):
    
    if not os.path.exists(CSV_FILE):
        console.print(f"[bold red]Error:[/bold red] {CSV_FILE} not found.")
        return []

    results = []
    
    # Parse date strings to datetime objects for comparison
    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00')) if start_time else None
    end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00')) if end_time else None

    with open(CSV_FILE, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            # Filter by Language
            if lang and row.get("lang") != lang:
                continue

            # Filter by Usernames
            if usernames:
                if row.get("username", "").lower() not in [u.lower() for u in usernames]:
                    continue

            # Filter by Metrics
            try:
                likes = int(row.get("likes", 0))
                retweets = int(row.get("retweets", 0))
            except ValueError:
                likes = 0
                retweets = 0
                
            if likes < min_likes or retweets < min_retweets:
                continue

            # Filter by Date
            created_at_str = row.get("created_at")
            if (start_dt or end_dt) and created_at_str:
                try:
                    # Handle potential Z suffix or other formats if necessary
                    tweet_dt = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    
                    if start_dt and tweet_dt < start_dt:
                        continue
                    if end_dt and tweet_dt > end_dt:
                        continue
                except ValueError:
                    continue

            # Filter by Keywords
            if keywords:
                text = row.get("text", "").lower()
                keyword_matches = [k.lower() in text for k in keywords]
                
                if logic.upper() == "OR":
                    if not all(keyword_matches):
                        continue
                else: # OR
                    if not any(keyword_matches):
                        continue

            # If we passed all filters, add to results
            results.append(row)
            
    return results

def main():
    
    """
    Args:
        keywords (list): List of keywords to search for.
        usernames (list): List of usernames to search from.
        start_time (str): ISO 8601 start time (e.g., "2023-12-01T00:00:00Z").
        end_time (str): ISO 8601 end time.
        logic (str): "AND" or "OR" for combining keywords.
        min_likes (int): Minimum number of likes.
        min_retweets (int): Minimum number of retweets.
        entities (list): List of entities to search for.
        max_results (int): Number of tweets to return (10-100).
        full_archive (bool): Whether to search the full archive (required for tweets older than 7 days).
    """
    
    fetch_tweets(
        # usernames=["elonmusk"],
        # start_time="2025-03-03T00:00:00Z",
        # end_time="2025-04-25T00:00:00Z",
        max_results=MIN_TWEETS,
        full_archive=False
    )
    
    fetch_tweets(
        # keywords=["cut", "decision", "fed", "rates"],  # or usernames=[...]
        keywords = ['Fed', 'interest', 'rates', 'FOMC', 'December', '2025', '50', 'bps', 'cut', 'Federal', 'Reserve', 'meeting'],
        # start_time="2025-06-07T00:00:00Z",
        # end_time="2025-11-30T11:57:00Z",
        max_results=MIN_TWEETS,
        full_archive=False  # required for dates older than ~7 days
    )
    
    # fetch_tweets(
    #     # usernames=["elonmusk"],
    #     keywords=["dildo", "wnba", "court"],
    #     start_time="2025-05-03T00:00:00Z",
    #     end_time="2025-09-25T00:00:00Z",
    #     max_results=MIN_TWEETS,
    #     full_archive=True
    # )
    
    # fetch_tweets(
    #     usernames=["F1",  "Drivers", "Champion"],
    #     # start_time="2025-03-03T00:00:00Z",
    #     # end_time="2025-04-25T00:00:00Z",
    #     max_results=MIN_TWEETS,
    #     full_archive=True
    # )

if __name__ == "__main__":
    main()

