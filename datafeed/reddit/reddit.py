import requests
import os
import csv
import re
import time
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box

root_dir = Path(__file__).resolve().parents[2]
load_dotenv(root_dir / '.env')

REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "python:grok-trader:v1.0 (by /u/yourusername)")
USE_TEST_DATA = False
CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reddit_data.csv")

console = Console()

class User:
    def __init__(self, username):
        self.username = username

class Post:
    def __init__(self, id, title, text, created_utc, metrics, subreddit, author, url):
        self.id = id
        self.title = title
        self.text = text
        self.created_utc = created_utc
        self.metrics = metrics
        self.subreddit = subreddit
        self.author = author
        self.url = url

def save_to_csv(post, user):
    file_exists = os.path.isfile(CSV_FILE)
    
    # Check for duplicates
    if file_exists:
        try:
            with open(CSV_FILE, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row.get("post_id") == str(post.id):
                        return
        except Exception:
            pass
    
    with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        
        if not file_exists:
            writer.writerow([
                "post_id", "created_utc", "author", "subreddit", "title", 
                "text", "score", "comments", "upvote_ratio", "url"
            ])
            
        metrics = post.metrics or {}
        
        writer.writerow([
            post.id,
            post.created_utc,
            user.username if user else "Unknown",
            post.subreddit,
            post.title.replace('\n', ' '),
            post.text.replace('\n', ' ')[:500],
            metrics.get('score', 0),
            metrics.get('num_comments', 0),
            metrics.get('upvote_ratio', 0),
            post.url
        ])

def display_post(post, user):
    
    if user:
        author_text = Text()
        author_text.append(f"u/{user.username}", style=f"bold cyan link=https://reddit.com/user/{user.username}")
        author_text.append(f" in r/{post.subreddit}", style="bold white")
    else:
        author_text = Text(f"Unknown User in r/{post.subreddit}", style="bold red")

    post_content = Text()
    post_content.append(f"{post.title}\n\n", style="bold yellow")
    
    display_text = post.text[:300] + "..." if len(post.text) > 300 else post.text
    post_content.append(display_text, style="white")

    metrics = post.metrics or {}
    
    if isinstance(post.created_utc, (int, float)):
        dt = datetime.fromtimestamp(post.created_utc)
        date_str = dt.strftime('%I:%M:%S %p %m/%d/%Y').lower()
    elif isinstance(post.created_utc, str):
         date_str = post.created_utc
    else:
        date_str = "Unknown Date"

    metrics_line = (
        f"⬆️  {metrics.get('score', 0)}  "
        f"💬  {metrics.get('num_comments', 0)}  "
        f"📈  {int(metrics.get('upvote_ratio', 0) * 100)}%  "
        f"📅  {date_str}"
    )

    content = Group(
        author_text,
        Text(" "),
        post_content,
        Text(" "),
        Text(metrics_line, style="dim"),
        Text(post.url, style=f"blue underline link={post.url}")
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

    console.print(f"[bold yellow]Loading posts from {CSV_FILE}...[/bold yellow]\n")
    
    with open(CSV_FILE, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        count = 0
        for row in reader:
            user = User(username=row.get("author", "Unknown"))
            
            metrics = {
                "score": int(row.get("score", 0)),
                "num_comments": int(row.get("comments", 0)),
                "upvote_ratio": float(row.get("upvote_ratio", 0))
            }
            
            post = Post(
                id=row.get("post_id"),
                title=row.get("title"),
                text=row.get("text"),
                created_utc=row.get("created_utc"),
                metrics=metrics,
                subreddit=row.get("subreddit"),
                author=row.get("author"),
                url=row.get("url")
            )
            
            display_post(post, user)
            count += 1
            
        console.print(f"\n[bold green]Displayed {count} posts from CSV.[/bold green]")

def build_query(keywords=None, logic="AND", site_filter=None):
    """Constructs a search query for Reddit."""
    if not keywords:
        return ""
        
    if logic.upper() == "OR":
        query = " OR ".join(keywords)
    else:
        query = " AND ".join(keywords)
        
    if site_filter:
        query += f" site:{site_filter}"
        
    return query

def fetch_posts(keywords=None, 
                subreddits=None, 
                logic="AND", 
                limit=10, 
                time_filter="all",
                sort="relevance"):
    """
    Fetches posts from Reddit based on criteria using public JSON endpoints.
    
    Args:
        keywords (list): List of keywords to search for.
        subreddits (list): List of subreddits to search in (e.g. ["python", "learnprogramming"]). 
                           If None, searches all.
        logic (str): "AND" or "OR" for combining keywords.
        limit (int): Number of posts to return.
        time_filter (str): "all", "day", "hour", "month", "week", "year".
        sort (str): "relevance", "hot", "top", "new", "comments".
    """
    
    headers = {'User-Agent': REDDIT_USER_AGENT}
    
    try:
        query = build_query(keywords, logic)
        console.print(f"[bold yellow]Searching Reddit for:[/bold yellow] '{query}' in {subreddits if subreddits else 'all'}...\n")

        if subreddits:
            sub_string = "+".join(subreddits)
            base_url = f"https://www.reddit.com/r/{sub_string}"
        else:
            base_url = "https://www.reddit.com/r/all"

        params = {'limit': limit}
        
        if query:
            url = f"{base_url}/search.json"
            params['q'] = query
            params['sort'] = sort
            params['t'] = time_filter
            params['restrict_sr'] = 1 if subreddits else 0
        else:
            url = f"{base_url}/{sort}.json"
            params['t'] = time_filter

        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            console.print(f"[bold red]Error {response.status_code}:[/bold red] {response.text}")
            return

        data = response.json()
        posts_data = data.get('data', {}).get('children', [])

        fetched_posts = []
        count = 0
        for item in posts_data:
            submission = item['data']
            
            user = User(username=submission.get('author', 'deleted'))
            
            metrics = {
                "score": submission.get('score', 0),
                "num_comments": submission.get('num_comments', 0),
                "upvote_ratio": submission.get('upvote_ratio', 0.0)
            }
            
            post = Post(
                id=submission.get('id'),
                title=submission.get('title'),
                text=submission.get('selftext', ''),
                created_utc=submission.get('created_utc'),
                metrics=metrics,
                subreddit=submission.get('subreddit'),
                author=user.username,
                url=f"https://reddit.com{submission.get('permalink')}"
            )
            
            display_post(post, user)
            save_to_csv(post, user)
            
            fetched_posts.append({
                "post_id": post.id,
                "created_utc": post.created_utc,
                "author": post.author,
                "subreddit": post.subreddit,
                "title": post.title,
                "text": post.text,
                "score": metrics['score'],
                "comments": metrics['num_comments'],
                "upvote_ratio": metrics['upvote_ratio'],
                "url": post.url
            })
            
            count += 1
            
        if count > 0:
            console.print(f"\n[bold green]Success![/bold green] Saved {count} posts to {CSV_FILE}")
        else:
            console.print("[bold red]No posts found matching criteria.[/bold red]")
            
        return fetched_posts

    except Exception as e:
        console.print(f"[bold red]An error occurred:[/bold red] {e}")
        return []
        console.print(f"[bold red]An error occurred:[/bold red] {e}")

def load_posts(keywords=None, 
                       subreddits=None, 
                       authors=None,
                       start_time=None, 
                       end_time=None, 
                       logic="AND", 
                       min_score=0, 
                       min_comments=0):

    if not os.path.exists(CSV_FILE):
        console.print(f"[bold red]Error:[/bold red] {CSV_FILE} not found.")
        return []

    results = []
    
    start_ts = None
    end_ts = None
    
    if start_time:
        try:
            dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            start_ts = dt.timestamp()
        except ValueError:
            pass
            
    if end_time:
        try:
            dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            end_ts = dt.timestamp()
        except ValueError:
            pass

    with open(CSV_FILE, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            if subreddits:
                if row.get("subreddit", "").lower() not in [s.lower() for s in subreddits]:
                    continue

            if authors:
                if row.get("author", "").lower() not in [a.lower() for a in authors]:
                    continue

            try:
                score = int(row.get("score", 0))
                comments = int(row.get("comments", 0))
            except ValueError:
                score = 0
                comments = 0
                
            if score < min_score or comments < min_comments:
                continue

            created_utc_str = row.get("created_utc")
            if (start_ts or end_ts) and created_utc_str:
                try:
                    post_ts = float(created_utc_str)
                    
                    if start_ts and post_ts < start_ts:
                        continue
                    if end_ts and post_ts > end_ts:
                        continue
                except ValueError:
                    continue

            if keywords:
                title = row.get("title", "").lower()
                text = row.get("text", "").lower()
                content = title + " " + text
                
                keyword_matches = [k.lower() in content for k in keywords]
                
                if logic.upper() == "AND":
                    if not all(keyword_matches):
                        continue
                else:
                    if not any(keyword_matches):
                        continue

            results.append(row)
            
    return results

def main():
    
    """  
    Args:
        keywords (list): List of keywords to search for.
        subreddits (list): List of subreddits to search in (e.g. ["python", "learnprogramming"]). 
                           If None, searches all.
        logic (str): "AND" or "OR" for combining keywords.
        limit (int): Number of posts to return.
        time_filter (str): "all", "day", "hour", "month", "week", "year".
        sort (str): "relevance", "hot", "top", "new", "comments".
    """
    
    
    fetch_posts(
        keywords=["Python", "AI"],
        subreddits=["technology", "programming"],
        logic="OR",
        limit=5,
        sort="top",
        time_filter="month"
    )
    
    fetch_posts(
        subreddits=["wallstreetbets"],
        limit=5,
        sort="hot"
    )

if __name__ == "__main__":
    main()
