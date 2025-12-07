import os
import sys
import json
import re
import argparse
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import system, user

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

MODEL_NAME = "grok-4-1-fast-reasoning"

PROMPT_FILE = os.path.join(os.path.dirname(__file__), 'prompts', 'find_signal_accounts.txt')

def find_signal_accounts(market_question: str, verbose: bool = False):
    try:
        client = Client(api_key=os.getenv("XAI_API_KEY"))
    except Exception as e:
        print(f"Error initializing xAI Client: {e}")
        return []

    try:
        with open(PROMPT_FILE, 'r') as f:
            prompt_template = f.read()
        prompt = prompt_template.format(market_question=market_question)
    except Exception as e:
        print(f"Error loading prompt file: {e}")
        return []

    try:
        if verbose:
            print(f"Asking Grok to find signal accounts for: '{market_question}'...")
        
        chat = client.chat.create(model=MODEL_NAME)
        chat.append(system("You are an expert researcher with access to real-time information."))
        chat.append(user(prompt))
        
        response = chat.sample()
        content = response.content
        
        if verbose:
            print(f"Raw response from Grok:\n{content}\n")
        
        if "```" in content:
            match = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
            if match:
                content = match.group(1)
        
        data = json.loads(content.strip())
        return data.get("accounts", [])

    except Exception as e:
        print(f"Error finding accounts: {e}")
        return []

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find X accounts relevant to a prediction market.")
    parser.add_argument("market", nargs="?", help="The market question to research")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    if args.market:
        markets = [args.market]
    else:
        markets = [
            "Will Lando Norris win the Abu Dhabi Grand Prix?",
            "Who will be the #1 searched person on Google in 2025?"
        ]
    
    for market in markets:
        print(f"\n--- Researching: {market} ---")
        accounts = find_signal_accounts(market, verbose=args.verbose)
        if accounts:
            print(json.dumps(accounts, indent=2))
        else:
            print("No accounts found.")
