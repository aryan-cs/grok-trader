import tweepy
import os
import csv
import re
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box

load_dotenv()

BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
USE_TEST_DATA = False
CSV_FILE = "tweets_data.csv"
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
    file_exists = os.path.isfile(CSV_FILE)
    
    with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        
        if not file_exists:
            writer.writerow([
                "tweet_id", "created_at", "author_id", "username", "name", 
                "text", "likes", "retweets", "replies", "quotes", "impressions", "lang", "url"
            ])
            
        metrics = tweet.public_metrics or {}
        url = f"https://x.com/{user.username}/status/{tweet.id}" if user else ""
        
        writer.writerow([
            tweet.id,
            tweet.created_at,
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
        
    if min_likes > 0:
        parts.append(f"min_faves:{min_likes}")
    if min_retweets > 0:
        parts.append(f"min_retweets:{min_retweets}")
        
    parts.append(f"lang:{lang}")
    parts.append("-is:retweet")
    
    return " ".join(parts)

def fetch_tweets(keywords=None, 
                 usernames=None, 
                 start_time=None, 
                 end_time=None, 
                 logic="AND", 
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

        if response.data:
            users = {u.id: u for u in response.includes['users']} if response.includes else {}

            for tweet in response.data:
                user = users.get(tweet.author_id)
                
                display_tweet(tweet, user)
                
                save_to_csv(tweet, user)
            
            console.print(f"\n[bold green]Success![/bold green] Saved {len(response.data)} tweets to {CSV_FILE}")
        else:
            console.print("[bold red]No tweets found matching criteria.[/bold red]")

    except Exception as e:
        console.print(f"[bold red]An error occurred:[/bold red] {e}")

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
        usernames=["elonmusk"],
        start_time="2025-03-03T00:00:00Z",
        end_time="2025-04-25T00:00:00Z",
        max_results=MIN_TWEETS,
        full_archive=True
    )
    
    fetch_tweets(
        # usernames=["elonmusk"],
        keywords=["dildo", "wnba", "court"],
        start_time="2025-05-03T00:00:00Z",
        end_time="2025-09-25T00:00:00Z",
        max_results=MIN_TWEETS,
        full_archive=True
    )
    
    fetch_tweets(
        usernames=["F1",  "Drivers", "Champion"],
        # start_time="2025-03-03T00:00:00Z",
        # end_time="2025-04-25T00:00:00Z",
        max_results=MIN_TWEETS,
        full_archive=True
    )

if __name__ == "__main__":
    main()

