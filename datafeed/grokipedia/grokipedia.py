import os
import csv
import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import system, user, tool
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

load_dotenv()

CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grokipedia_data.csv")
console = Console()

MODEL_NAME = "grok-4-1-fast-non-reasoning" 

def save_to_csv(topic, content, timestamp):
    file_exists = os.path.isfile(CSV_FILE)
    
    if file_exists:
        try:
            with open(CSV_FILE, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row.get("topic") == topic:
                        pass
        except Exception:
            pass

    with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        
        if not file_exists:
            writer.writerow(["timestamp", "topic", "content"])
            
        writer.writerow([timestamp, topic, content])

def fetch_grokipedia_article(topic: str, verbose: bool = False):
    """
    Fetches a Grokipedia article on the given topic from grokipedia.com.
    Falls back to Grok generation if the article is not found.
    """
    if verbose:
        console.print(f"[bold yellow]Consulting Grokipedia for:[/bold yellow] '{topic}'...")

    url = f"https://grokipedia.com/page/{topic.replace(' ', '_')}"
    scraped_content = None
    
    try:
        if verbose:
            console.print(f"Fetching from {url}...")
        
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            content_div = soup.find('article') or \
                          soup.find('div', {'id': 'content'}) or \
                          soup.find('div', {'class': 'mw-parser-output'}) or \
                          soup.body
            
            if content_div:
                for element in content_div(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                    element.decompose()

                text = content_div.get_text(separator='\n', strip=True)
                
                text = re.sub(r'\[\d+\]', '', text)
                
                text = re.sub(r'\n{3,}', '\n\n', text)
                
                scraped_content = text.strip()
    except Exception as e:
        if verbose:
            console.print(f"[red]Error scraping Grokipedia:[/red] {e}")

    if scraped_content:
        timestamp = datetime.now().isoformat()
        save_to_csv(topic, scraped_content, timestamp)
        
        if verbose:
            panel = Panel(
                Markdown(scraped_content),
                title=f"Grokipedia (Web): {topic}",
                border_style="green"
            )
            console.print(panel)
            
        return {
            "topic": topic,
            "content": scraped_content,
            "timestamp": timestamp,
            "source": "Grokipedia.com"
        }

    if verbose:
        console.print("[yellow]Article not found on Web. Generating with Grok...[/yellow]")

    try:
        client = Client(api_key=os.getenv("XAI_API_KEY"))
    except Exception as e:
        console.print(f"[bold red]Error initializing xAI Client:[/bold red] {e}")
        return None

    prompt = f"""
    Write a concise but comprehensive encyclopedia-style article about: "{topic}".
    
    Include:
    1. Definition/Overview
    2. Key Facts/Figures
    3. Recent Developments (if applicable)
    4. Relevance to financial/prediction markets (if applicable)
    
    Keep it factual and objective.
    """

    try:
        chat = client.chat.create(model=MODEL_NAME)
        chat.append(system("You are Grokipedia, a real-time encyclopedia with access to the latest information."))
        chat.append(user(prompt))
        
        response = chat.sample()
        content = response.content
        
        timestamp = datetime.now().isoformat()
        save_to_csv(topic, content, timestamp)
        
        if verbose:
            panel = Panel(
                Markdown(content),
                title=f"Grokipedia (Generated): {topic}",
                border_style="blue"
            )
            console.print(panel)
            
        return {
            "topic": topic,
            "content": content,
            "timestamp": timestamp,
            "source": "Grok (Generated)"
        }

    except Exception as e:
        console.print(f"[bold red]Error fetching Grokipedia article:[/bold red] {e}")
        return None

get_grokipedia_article_tool = tool(
    name="fetch_grokipedia_article",
    description="Retrieves a comprehensive encyclopedia-style article on a given topic from Grokipedia.com (or generates one if not found).",
    parameters={
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The topic or keywords to look up (e.g., 'Polymarket', 'US Election 2024')."
            }
        },
        "required": ["topic"]
    }
)

if __name__ == "__main__":
    fetch_grokipedia_article("Prediction market", verbose=True)
