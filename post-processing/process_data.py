import os
import sys
import json
import re
import csv
from datetime import datetime
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import user, system
from rich.console import Console
from rich.table import Table
from rich.progress import track

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datafeed.x.x import load_tweets
from datafeed.reddit.reddit import load_posts
from datafeed.reuters.reuters import load_articles

MODEL_NAME = "grok-4-1-fast-non-reasoning"

load_dotenv()

console = Console()

try:
    client = Client(api_key=os.getenv("XAI_API_KEY"))
except Exception as e:
    console.print(f"[bold red]Error initializing xAI Client:[/bold red] {e}")
    console.print("[yellow]Make sure 'xai-sdk' is installed: pip install xai-sdk[/yellow]")
    client = None

def load_prompt(filename):
    try:
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", filename)
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        console.print(f"[red]Error loading prompt {filename}: {e}[/red]")
        return ""

def analyze_text(text, source, market=None):
    if not client:
        return {"is_useful": False, "reason": "Client not initialized", "sentiment": "neutral"}

    try:
        chat = client.chat.create(model=MODEL_NAME)
        
        if market:
            prompt_template = load_prompt("market_filter_prompt.txt")
            sys_prompt = prompt_template.format(market=market)
        else:
            sys_prompt = load_prompt("financial_filter_prompt.txt")
        
        chat.append(system(sys_prompt))
        chat.append(user(f"Source: {source}\nText: {text}"))
        
        response = chat.sample()
        content = response.content
        
        if "```" in content:
            match = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
            if match:
                content = match.group(1)
        
        return json.loads(content.strip())
    except Exception as e:
        return {"is_useful": False, "reason": f"Error: {str(e)}", "sentiment": "neutral"}

def normalize_data(tweets, posts, articles):

    all_items = []
    
    for t in tweets:
        all_items.append({
            "source": "X",
            "text": t.get('text', ''),
            "meta": f"@{t.get('username')}",
            "original": t
        })
        
    for p in posts:
        all_items.append({
            "source": "Reddit",
            "text": f"{p.get('title')} - {p.get('text')[:200]}",
            "meta": f"r/{p.get('subreddit')}",
            "original": p
        })
        
    for a in articles:
        all_items.append({
            "source": "Reuters",
            "text": f"{a.get('title')} - {a.get('summary')}",
            "meta": "Reuters",
            "original": a
        })
        
    return all_items

def run_analysis(items, market_question):

    results = []
    console.print(f"\n[yellow]Analyzing with Grok {MODEL_NAME} for market: '{market_question}'...[/yellow]")
    
    for item in track(items, description="Processing..."):
        if not item['text'].strip():
            continue
            
        analysis = analyze_text(item['text'], item['source'], market=market_question)
        
        results.append({
            **item,
            **analysis
        })
        
    return results

def save_results_to_csv(results, filename="analysis_results.csv"):

    if not results:
        console.print("[yellow]No results to save.[/yellow]")
        return

    file_exists = os.path.isfile(filename)
    
    try:
        with open(filename, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            
            if not file_exists:
                writer.writerow(["timestamp", "source", "meta", "text", "sentiment", "is_useful", "reason"])
            
            timestamp = datetime.now().isoformat()
            
            for res in results:
                writer.writerow([
                    timestamp,
                    res.get('source', ''),
                    res.get('meta', ''),
                    res.get('text', '').replace('\n', ' '),
                    res.get('sentiment', ''),
                    res.get('is_useful', False),
                    res.get('reason', '')
                ])
                
        console.print(f"[bold green]Saved results to {filename}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Error saving to CSV:[/bold red] {e}")

def display_analysis(results):
    console.print(f"\n[bold blue]Analysis Complete. Processed {len(results)} items:[/bold blue]\n")
    
    table = Table(show_header=True, header_style="bold magenta", show_lines=True)
    table.add_column("Source", style="cyan", width=10)
    table.add_column("Content", style="white")
    table.add_column("Sentiment", width=10)
    table.add_column("Useful?", width=8)
    table.add_column("Reason", style="dim")

    for res in results:
        sentiment_color = "green" if res['sentiment'] == 'positive' else "red" if res['sentiment'] == 'negative' else "yellow"
        useful_str = "[bold green]YES[/bold green]" if res.get('is_useful') else "[dim red]NO[/dim red]"
        
        table.add_row(
            f"{res['source']}\n{res['meta']}",
            res['text'][:100] + "...",
            f"[{sentiment_color}]{res['sentiment']}[/{sentiment_color}]",
            useful_str,
            res['reason']
        )

    console.print(table)

def main():
    console.print("[bold blue]Starting Data Processing Pipeline (xAI SDK)...[/bold blue]")

    console.print("\n[yellow]Fetching data from local CSVs...[/yellow]")
    
    tweets = load_tweets()[-10:] 
    posts = load_posts()[-10:] 
    articles = load_articles()[-10:]
    
    all_items = normalize_data(tweets, posts, articles)

    console.print(f"Loaded {len(all_items)} items for processing.")

    test_market = "Will AI take over the world?"
    results = run_analysis(all_items, test_market)

    display_analysis(results)
    save_results_to_csv(results)

if __name__ == "__main__":
    main()
