import os
import json
import re
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import user, system
from rich.console import Console
from rich.table import Table
from rich.progress import track

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

def analyze_text(text, source, market=None):
    if not client:
        return {"is_useful": False, "reason": "Client not initialized", "sentiment": "neutral"}

    try:
        chat = client.chat.create(model=MODEL_NAME)
        
        if market:
            sys_prompt = (
                f"You are a prediction market analyst. The market question is: '{market}'. "
                "Analyze the input text. Determine if it provides insight into the outcome of this market. "
                "Return ONLY a JSON object with keys: "
                "'is_useful' (boolean), "
                "'reason' (short string explaining relevance to the market question), "
                "'sentiment' (string: 'positive' if it supports YES, 'negative' if it supports NO, 'neutral' if irrelevant)."
            )
        else:
            sys_prompt = "You are a financial data filter. Analyze the input text. Determine if it contains useful signal for market analysis or trading. Return ONLY a JSON object with keys: 'is_useful' (boolean), 'reason' (short string), 'sentiment' (string: positive/negative/neutral)."
        
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
    """
    Normalizes data from different sources into a common format.
    """
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
    """
    Runs the analysis on the normalized items.
    """
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
    posts = []
    articles = []
    
    all_items = normalize_data(tweets, posts, articles)

    console.print(f"Loaded {len(all_items)} items for processing.")

    test_market = "Will AI take over the world?"
    results = run_analysis(all_items, test_market)

    display_analysis(results)

if __name__ == "__main__":
    main()
