import os
import sys
import json
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Add pre-processing to path to allow import
sys.path.append(os.path.join(os.path.dirname(__file__), "pre-processing"))
from process_market import get_market_sentiment, get_market_sentiment_tool

# Add grokipedia to path
sys.path.append(os.path.join(os.path.dirname(__file__), "datafeed", "grokipedia"))
from grokipedia import fetch_grokipedia_article, get_grokipedia_article_tool

load_dotenv()

MODEL_NAME = "grok-4-1-fast-non-reasoning"
XAI_API_KEY = os.getenv("XAI_API_KEY")

# Initialize xAI client (uses OpenAI SDK with custom base URL)
client = AsyncOpenAI(
    api_key=XAI_API_KEY,
    base_url="https://api.x.ai/v1",
)


async def research_market(
    websocket,
    market_title: str,
    market_rules: str,
    custom_instructions: str,
    yes_price: int,
    no_price: int,
):
    """Stream research results to WebSocket"""
    prompt = f"""You are an expert at analyzing prediction markets.

You will analyze the following market and provide a recommendation for the user to make a trade.

Market Title: {market_title}

Market Rules: {market_rules}

The current prices of the market are:
Yes Price: {yes_price}
No Price: {no_price}

The prices are in cents * 10. E.g. if YES is priced at 531, then the YES price is 53.1 cents.

Prediction Market General rules:
- The market may resolve to YES or NO.
- Once resolved, winning contracts resolve to 100 cents. E.g. 53.1 cents -> 100 cents.
- the NOOP recommendation means that the market is not clear OR the market is perfectly priced and the user should not trade.
- You should should only recommend a contract purchase if it is underpriced and buying will result in positive expected value.
- Expected value is calculated as (probability of winning * payout) - cost of the contract. Basically if the probablity of the contract is greater than the implied probability of the market, then it is underpriced.

I will provide you with real-time social media and news sentiment data about this market. Use this information to inform your analysis.

Provide a detailed analysis covering:
1. Key factors that could influence the outcome
2. Current trends or relevant information (incorporate the sentiment data provided)
3. Risk assessment
4. Actual fair prices for YES and NO contracts based on the true odds of the market.
5. Your final recommendation (YES or NO or NOOP)

End your response with a clear recommendation: "RECOMMENDATION: YES" or "RECOMMENDATION: NO" or "RECOMMENDATION: NOOP"

Additionally, here are some custom user instructions to focus on:
```
{custom_instructions}
```
"""

    print(f"Starting research for: {market_title}")

    if not XAI_API_KEY:
        await websocket.send_json(
            {
                "message_type": "research",
                "type": "error",
                "error": "XAI_API_KEY not configured",
            }
        )
        return

    try:
        # Send initial thinking message
        await websocket.send_json(
            {
                "message_type": "research",
                "type": "thinking",
                "content": "Gathering market sentiment data...",
            }
        )

        # Fetch market sentiment data upfront
        sentiment_data = get_market_sentiment(market_title)
        sentiment_text = json.dumps(sentiment_data, indent=2)

        # Update prompt to include sentiment data
        prompt_with_data = f"""{prompt}

---

Here is the current market sentiment data I gathered for you:

```json
{sentiment_text}
```

Use this data in your analysis."""

        # Send thinking message
        await websocket.send_json(
            {
                "message_type": "research",
                "type": "thinking",
                "content": "Analyzing market data and trends...",
            }
        )

        # Create streaming chat completion
        stream = await client.chat.completions.create(
            model="grok-2-1212",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that analyzes prediction markets.",
                },
                {"role": "user", "content": prompt_with_data},
            ],
            stream=True,
            temperature=0.7,
        )

        # Stream the response
        full_response = ""
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                content = delta.content

                if content:
                    full_response += content
                    # Send text delta to client
                    await websocket.send_json(
                        {"message_type": "research", "type": "delta", "content": content}
                    )

        # Extract recommendation from report
        recommendation = "NOOP"
        if "RECOMMENDATION: YES" in full_response.upper():
            recommendation = "YES"
        elif "RECOMMENDATION: NO" in full_response.upper():
            recommendation = "NO"

        # Send completion with recommendation
        await websocket.send_json(
            {
                "message_type": "research",
                "type": "complete",
                "recommendation": recommendation,
            }
        )

        print(f"✅ Research complete: {recommendation}")

    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback_str = traceback.format_exc()
        print(f"❌ Research error: {error_msg}")
        print(f"Traceback:\n{traceback_str}")
        await websocket.send_json(
            {
                "message_type": "research",
                "type": "error",
                "error": f"Error: {error_msg}",
            }
        )


async def research_followup(websocket, messages: list[dict]):
    """
    Handle follow-up questions about research reports.
    Streams responses via WebSocket.

    Args:
        websocket: FastAPI WebSocket connection
        messages: Conversation history including original report and follow-up questions
    """
    try:
        # Send thinking message
        await websocket.send_json(
            {
                "message_type": "research_followup",
                "type": "thinking",
                "content": "Processing your follow-up question...",
            }
        )

        # Build conversation with system message + history
        conversation = [
            {
                "role": "system",
                "content": "You are a helpful assistant that analyzes prediction markets. "
                "You previously provided a research report. Now answer follow-up questions "
                "about that report, provide clarifications, or respond to challenges."
            }
        ] + messages

        # Create streaming chat completion
        stream = await client.chat.completions.create(
            model="grok-2-1212",
            messages=conversation,
            stream=True,
            temperature=0.7,
        )

        # Stream the response
        full_response = ""
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                content = delta.content

                if content:
                    full_response += content
                    # Send text delta to client
                    await websocket.send_json(
                        {
                            "message_type": "research_followup",
                            "type": "delta",
                            "content": content
                        }
                    )

        # Send completion
        await websocket.send_json(
            {"message_type": "research_followup", "type": "complete"}
        )

        print(f"✅ Follow-up response complete")

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Follow-up error: {error_msg}")
        await websocket.send_json(
            {
                "message_type": "research_followup",
                "type": "error",
                "error": f"Error: {error_msg}",
            }
        )


if __name__ == "__main__":
    title = "Who will Trump nominate as Fed Chair?"
    rules = "If Kevin Hassett is the first person formally nominated by the President to Fed Chair before Jan 20, 2029, then the market resolves to Yes. Outcome verified from Library of Congress."
    yes_price = 531
    no_price = 469

    result = research_market(title, rules, yes_price, no_price)

    print("\n--- FINAL REPORT ---\n")
    print(result["report"])
    print(f"\nFINAL RECOMMENDATION: {result['recommendation']}")
