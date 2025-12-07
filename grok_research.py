import os
import sys
import json
from dotenv import load_dotenv
from xai_sdk import Client
from xai_sdk.chat import user, system, tool_result

# Add pre-processing to path to allow import
sys.path.append(os.path.join(os.path.dirname(__file__), 'pre-processing'))
from process_market import get_market_sentiment, get_market_sentiment_tool

load_dotenv()

MODEL_NAME = "grok-4-1-fast-non-reasoning"

def research_market(
    market_title: str, market_rules: str, yes_price: int, no_price: int
) -> dict:
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
- Expected value is calculated as (probability of winning * payout) - cost of the contract.

You have access to a tool 'get_market_sentiment' that can fetch real-time social media and news sentiment about the market. 
USE THIS TOOL to get the latest information before making your decision.

Provide a detailed analysis covering:
1. Key factors that could influence the outcome
2. Current trends or relevant information (incorporate findings from the tool)
3. Risk assessment
4. Actual fair prices for YES and NO contracts based on the true odds of the market.
4. Your final recommendation (YES or NO or NOOP)

End your response with a clear recommendation: "RECOMMENDATION: YES" or "RECOMMENDATION: NO" or "RECOMMENDATION: NOOP"
"""

    print(f"Starting research for: {market_title}")

    # Initialize chat with tools
    chat = client.chat.create(
        model=MODEL_NAME,
        tools=[get_market_sentiment_tool],
        tool_choice="auto"
    )

    chat.append(system("You are a helpful assistant that analyzes prediction markets."))
    chat.append(user(prompt))

    # First sample to see if it wants to call a tool
    response = chat.sample()

    # Handle tool calls
    if response.tool_calls:
        for tool_call in response.tool_calls:
            if tool_call.function.name == "get_market_sentiment":
                args = json.loads(tool_call.function.arguments)
                print(f"Grok requested tool execution: get_market_sentiment({args})")
                
                # Call the actual function
                sentiment_data = get_market_sentiment(**args)
                
                # Add result to chat
                chat.append(tool_result(
                    tool_call_id=tool_call.id,
                    content=json.dumps(sentiment_data)
                ))
        
        # Get final response after tool output
        response = chat.sample()

    report = response.content

    # Extract recommendation from report
    recommendation = "NOOP"
    if "RECOMMENDATION: YES" in report.upper():
        recommendation = "YES"
    elif "RECOMMENDATION: NO" in report.upper():
        recommendation = "NO"

    return {"recommendation": recommendation, "report": report}


if __name__ == "__main__":
    title = "Who will Trump nominate as Fed Chair?"
    rules = "If Kevin Hassett is the first person formally nominated by the President to Fed Chair before Jan 20, 2029, then the market resolves to Yes. Outcome verified from Library of Congress."
    yes_price = 531
    no_price = 469
    
    result = research_market(title, rules, yes_price, no_price)
    
    print("\n--- FINAL REPORT ---\n")
    print(result['report'])
    print(f"\nFINAL RECOMMENDATION: {result['recommendation']}")
