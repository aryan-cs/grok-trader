import requests
import os
import csv
import re
import xml.etree.ElementTree as ET
from datetime import datetime
import email.utils
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich import box
import urllib.parse

CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reuters_data.csv")
console = Console()

class Article:
    def __init__(self, title, link, published, summary=""):
        self.title = title
        self.link = link
        self.published = published
        self.summary = summary

def save_to_csv(article):
    file_exists = os.path.isfile(CSV_FILE)
    
    with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        
        if not file_exists:
            writer.writerow(["title", "link", "published", "summary"])
            
        writer.writerow([
            article.title,
            article.link,
            article.published,
            article.summary
        ])

def display_article(article):
    
    title_text = Text(article.title, style="bold yellow")
    
    meta_text = Text()
    meta_text.append(f"📅 {article.published}", style="dim")
    
    link_text = Text(article.link, style=f"blue underline link={article.link}")

    content = Group(
        title_text,
        Text(" "),
        meta_text,
        Text(" "),
        link_text
    )

    panel = Panel(
        content,
        border_style="white",
        box=box.HORIZONTALS,
        expand=True,
        padding=(0, 0),
        title="Reuters (via Google News)",
        title_align="right"
    )
    console.print(panel)

def load_from_csv():
    if not os.path.exists(CSV_FILE):
        console.print(f"[bold red]Error:[/bold red] {CSV_FILE} not found.")
        return

    console.print(f"[bold yellow]Loading articles from {CSV_FILE}...[/bold yellow]\n")
    
    with open(CSV_FILE, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        count = 0
        for row in reader:
            article = Article(
                title=row.get("title"),
                link=row.get("link"),
                published=row.get("published"),
                summary=row.get("summary")
            )
            display_article(article)
            count += 1
            
        console.print(f"\n[bold green]Displayed {count} articles from CSV.[/bold green]")

def fetch_articles(keywords=None, limit=10):
    if not keywords:
        console.print("[bold red]Error:[/bold red] Keywords are required for search.")
        return

    query_str = " ".join(keywords)
    full_query = f"site:reuters.com {query_str}"
    encoded_query = urllib.parse.quote(full_query)
    
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    
    console.print(f"[bold yellow]Searching Reuters for:[/bold yellow] '{query_str}'...\n")
    
    try:
        response = requests.get(url)
        if response.status_code != 200:
            console.print(f"[bold red]Error {response.status_code}:[/bold red] Failed to fetch RSS feed.")
            return

        root = ET.fromstring(response.content)
        channel = root.find("channel")
        items = channel.findall("item")
        
        fetched_articles = []
        count = 0
        for item in items[:limit]:
            title = item.find("title").text if item.find("title") is not None else "No Title"
            link = item.find("link").text if item.find("link") is not None else ""
            pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
            description = item.find("description").text if item.find("description") is not None else ""
            
            if description:
                description = re.sub(r'<[^>]+>', '', description)
                description = description.replace('&nbsp;', ' ')
                description = description.replace('Reuters', '').strip()

            if " - Reuters" in title:
                title = title.replace(" - Reuters", "")
            
            article = Article(
                title=title,
                link=link,
                published=pub_date,
                summary=description
            )
            
            display_article(article)
            save_to_csv(article)
            
            fetched_articles.append({
                "title": article.title,
                "link": article.link,
                "published": article.published,
                "summary": article.summary
            })
            
            count += 1
            
        if count > 0:
            console.print(f"\n[bold green]Success![/bold green] Saved {count} articles to {CSV_FILE}")
        else:
            console.print("[bold red]No articles found matching criteria.[/bold red]")
            
        return fetched_articles
    except Exception as e:
        console.print(f"[bold red]An error occurred:[/bold red] {e}")
        return []

    except Exception as e:
        console.print(f"[bold red]An error occurred:[/bold red] {e}")

def load_articles(keywords=None, start_time=None, end_time=None, logic="AND"):
    """
    Retrieves articles from the CSV file based on filtering criteria.
    Returns a list of dictionaries.
    """
    if not os.path.exists(CSV_FILE):
        console.print(f"[bold red]Error:[/bold red] {CSV_FILE} not found.")
        return []

    results = []
    
    
    start_dt = None
    end_dt = None
    
    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        except ValueError:
            pass
            
    if end_time:
        try:
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        except ValueError:
            pass

    with open(CSV_FILE, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            if keywords:
                title = row.get("title", "").lower()
                summary = row.get("summary", "").lower()
                content = title + " " + summary
                
                keyword_matches = [k.lower() in content for k in keywords]
                
                if logic.upper() == "AND":
                    if not all(keyword_matches):
                        continue
                else:
                    if not any(keyword_matches):
                        continue
            
            published_str = row.get("published")
            if (start_dt or end_dt) and published_str:
                try:
                    article_dt = email.utils.parsedate_to_datetime(published_str)
                    
                    if start_dt and article_dt < start_dt:
                        continue
                    if end_dt and article_dt > end_dt:
                        continue
                except Exception:
                    pass
            
            results.append(row)
            
    return results

def main():
    fetch_articles(keywords=["Elon Musk", "Tesla"], limit=5)
    fetch_articles(keywords=["Oil", "OPEC"], limit=5)

if __name__ == "__main__":
    main()
