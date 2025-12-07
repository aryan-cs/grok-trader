import tweepy
import os
from dotenv import load_dotenv

load_dotenv()

BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")

def main():
    if not BEARER_TOKEN:
        print("Error: X_BEARER_TOKEN not found in .env file")
        return

    client = tweepy.Client(bearer_token=BEARER_TOKEN)
    
    # 10 most recent tweets, excluding retweets
    query = "Python -is:retweet"
    response = client.search_recent_tweets(query=query, max_results=10)

    if response.data:
        for tweet in response.data:
            print(f"- {tweet.text}\n")
    else:
        print("No tweets found.")

if __name__ == "__main__":
    main()

