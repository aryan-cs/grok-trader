import os
import sys
import json
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import user, system, tool_result

# Add pre-processing to path to allow import
sys.path.append(os.path.join(os.path.dirname(__file__), "pre-processing"))
from process_market import get_market_sentiment, get_market_sentiment_tool

load_dotenv()


async def research_market(
    websocket,
    market_title: str,
    market_rules: str,
    custom_instructions: str,
    yes_price: int,
    no_price: int,
):
    """Stream research results to WebSocket"""
    client = Client(api_key=os.getenv("XAI_API_KEY"))

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

You have access to a tool 'get_market_sentiment' that can fetch real-time social media and news sentiment about the market. 
USE THIS TOOL to get the latest information before making your decision.

Provide a detailed analysis covering:
1. Key factors that could influence the outcome
2. Current trends or relevant information (incorporate findings from the tool)
3. Risk assessment
4. Actual fair prices for YES and NO contracts based on the true odds of the market.
4. Your final recommendation (YES or NO or NOOP)

End your response with a clear recommendation: "RECOMMENDATION: YES" or "RECOMMENDATION: NO" or "RECOMMENDATION: NOOP"

Additionally, here are some custom user instructions to focus on:
```
{custom_instructions}
```
"""

    print(f"Starting research for: {market_title}")

    try:
        # Send initial thinking message
        await websocket.send_json(
            {
                "message_type": "research",
                "type": "thinking",
                "content": "Initializing research analysis...",
            }
        )

        # Initialize chat with tools
        chat = client.chat.create(
            model="grok-4-1-fast-non-reasoning",
            tools=[get_market_sentiment_tool],
            tool_choice="auto",
        )

        chat.append(
            system("You are a helpful assistant that analyzes prediction markets.")
        )
        chat.append(user(prompt))

        # Send thinking update
        await websocket.send_json(
            {
                "message_type": "research",
                "type": "thinking",
                "content": "Analyzing market conditions...",
            }
        )

        # First sample to see if it wants to call a tool
        response = chat.sample()

        # Handle tool calls
        if response.tool_calls:
            for tool_call in response.tool_calls:
                if tool_call.function.name == "get_market_sentiment":
                    args = json.loads(tool_call.function.arguments)
                    print(
                        f"Grok requested tool execution: get_market_sentiment({args})"
                    )

                    # Send thinking update
                    await websocket.send_json(
                        {
                            "message_type": "research",
                            "type": "thinking",
                            "content": f"Fetching market sentiment data...",
                        }
                    )

                    # Call the actual function
                    sentiment_data = get_market_sentiment(**args)

                    # Add result to chat
                    chat.append(
                        tool_result(
                            tool_call_id=tool_call.id,
                            content=json.dumps(sentiment_data),
                        )
                    )

            # Send thinking update
            await websocket.send_json(
                {
                    "message_type": "research",
                    "type": "thinking",
                    "content": "Processing sentiment data and generating report...",
                }
            )

            # Get final response after tool output
            response = chat.sample()

        report = response.content

        # Stream the report content
        await websocket.send_json(
            {"message_type": "research", "type": "report", "content": report}
        )

        # Extract recommendation from report
        recommendation = "NOOP"
        if "RECOMMENDATION: YES" in report.upper():
            recommendation = "YES"
        elif "RECOMMENDATION: NO" in report.upper():
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
        error_msg = str(e)
        print(f"❌ Research error: {error_msg}")
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
    client = Client(api_key=os.getenv("XAI_API_KEY"))

    try:
        # Send thinking message
        await websocket.send_json(
            {
                "message_type": "research_followup",
                "type": "thinking",
                "content": "Processing your follow-up question...",
            }
        )

        # Initialize chat
        chat = client.chat.create(
            model="grok-4-1-fast-non-reasoning",
            tools=[get_market_sentiment_tool],
            tool_choice="auto",
        )

        # Add system message
        chat.append(
            system(
                "You are a helpful assistant that analyzes prediction markets. "
                "You previously provided a research report. Now answer follow-up questions "
                "about that report, provide clarifications, or respond to challenges."
            )
        )

        # Build conversation context
        # Format: [{"role": "user|assistant", "content": "..."}]
        for msg in messages:
            if msg["role"] == "user":
                chat.append(user(msg["content"]))
            # Note: xai_sdk doesn't have a simple way to add assistant messages
            # The conversation context is maintained through the messages list

        # Get response
        response = chat.sample()

        # Handle tool calls if any
        if response.tool_calls:
            for tool_call in response.tool_calls:
                if tool_call.function.name == "get_market_sentiment":
                    args = json.loads(tool_call.function.arguments)
                    await websocket.send_json(
                        {
                            "message_type": "research_followup",
                            "type": "thinking",
                            "content": "Fetching additional market data...",
                        }
                    )
                    sentiment_data = get_market_sentiment(**args)
                    chat.append(
                        tool_result(
                            tool_call_id=tool_call.id, content=json.dumps(sentiment_data)
                        )
                    )

            response = chat.sample()

        # Stream the response
        await websocket.send_json(
            {
                "message_type": "research_followup",
                "type": "response",
                "content": response.content,
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
