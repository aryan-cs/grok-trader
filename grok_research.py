import httpx
import asyncio
from dotenv import load_dotenv
import os

load_dotenv()

XAI_API_KEY = os.getenv("XAI_API_KEY")


async def research_market(
    market_title: str, market_rules: str, yes_price: int, no_price: int
) -> dict:
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


Provide a detailed analysis covering:
1. Key factors that could influence the outcome
2. Current trends or relevant information
3. Risk assessment
4. Actual fair prices for YES and NO contracts based on the true odds of the market.
4. Your final recommendation (YES or NO or NOOP)

End your response with a clear recommendation: "RECOMMENDATION: YES" or "RECOMMENDATION: NO"
"""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {XAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "grok-4-1-fast-non-reasoning",
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30.0,
        )
        response.raise_for_status()

        data = response.json()
        report = data["choices"][0]["message"]["content"]

        # Extract recommendation from report
        recommendation = "YES" if "RECOMMENDATION: YES" in report.upper() else "NO"

        return {"recommendation": recommendation, "report": report}


if __name__ == "__main__":
    title = "Who will Trump nominate as Fed Chair?"
    rules = "If Kevin Hassett is the first person formally nominated by the President to Fed Chair before Jan 20, 2029, then the market resolves to Yes. Outcome verified from Library of Congress."
    yes_price = 531
    no_price = 469
    result = asyncio.run(research_market(title, rules, yes_price, no_price))
    print(result)
