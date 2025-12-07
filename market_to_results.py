import os
import sys
import json
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI

sys.path.append(os.path.join(os.path.dirname(__file__), "pre-processing"))
sys.path.append(os.path.join(os.path.dirname(__file__), "datafeed", "grokipedia"))

from process_market import get_market_sentiment
from grokipedia import fetch_grokipedia_article

load_dotenv()

MODEL_NAME = "grok-4-1-fast-non-reasoning"
XAI_API_KEY = os.getenv("XAI_API_KEY")

client = AsyncOpenAI(
    api_key=XAI_API_KEY,
    base_url="https://api.x.ai/v1",
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_market_sentiment",
            "description": "Fetch real-time social media (X, Reddit) and news (Reuters) sentiment for a given market.",
            "parameters": {
                "type": "object",
                "properties": {
                    "market": {
                        "type": "string",
                        "description": "The market question or topic (e.g., 'Will Lando Norris win?')."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of items to fetch per source. Default 20."
                    }
                },
                "required": ["market"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_grokipedia_article",
            "description": "Retrieves a comprehensive encyclopedia-style article on a given topic from Grokipedia.com or Wikipedia.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The topic or keywords to look up."
                    }
                },
                "required": ["topic"]
            }
        }
    }
]

async def analyze_market(websocket, market_title: str, custom_instructions: str = ""):
    """
    Analyzes a market using Grok and streams results to a WebSocket.
    """
    print(f"🚀 Starting analysis for: {market_title}")
    
    if not XAI_API_KEY:
        print("❌ XAI_API_KEY missing")
        await websocket.send_json({
            "message_type": "research",
            "type": "error",
            "error": "XAI_API_KEY not configured"
        })
        return

    print("📡 Sending initial thinking message...")
    await websocket.send_json({
        "message_type": "research",
        "type": "thinking",
        "content": "Initializing market analysis..."
    })
    print("✅ Initial thinking message sent.")

    messages = [
        {
            "role": "system",
            "content": "You are an expert prediction market analyst. Your goal is to provide a comprehensive analysis and a trading recommendation (YES, NO, or NOOP)."
        },
        {
            "role": "user",
            "content": f"""Market: "{market_title}"
            
            Steps:
            1. Use `get_market_sentiment` to get social media and news sentiment.
            2. Use `fetch_grokipedia_article` if you need background context.
            3. Analyze the data.
            4. Provide a final report with:
               - Key Factors
               - Sentiment Analysis
               - Risk Assessment
               - Fair Price Estimation
               - Final Recommendation (YES/NO/NOOP)
            
            Custom Instructions:
            {custom_instructions}
            """
        }
    ]

    try:
        while True:
            print("🤖 Calling Grok model...")
            response = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto"
            )
            print("✅ Grok response received.")
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            if tool_calls:
                print(f"🛠️ Tool calls requested: {len(tool_calls)}")
                messages.append(response_message)

                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    print(f"🛠️ Executing tool: {function_name} with args: {function_args}")
                    
                    await websocket.send_json({
                        "message_type": "research",
                        "type": "thinking",
                        "content": f"Using tool: {function_name}..."
                    })

                    function_response = ""
                    
                    if function_name == "get_market_sentiment":
                        # Define callback to stream items
                        loop = asyncio.get_running_loop()
                        def on_item(item):
                            asyncio.run_coroutine_threadsafe(
                                websocket.send_json({
                                    "message_type": "feed",
                                    "type": "sentiment_item",
                                    "item": item,
                                }),
                                loop
                            )

                        # Run in executor to avoid blocking and enable streaming
                        sentiment_data = await loop.run_in_executor(
                            None,
                            lambda: get_market_sentiment(**function_args, on_item=on_item)
                        )
                        function_response = json.dumps(sentiment_data)

                        # Also push the full list at the end to ensure consistency
                        try:
                            await websocket.send_json({
                                "message_type": "feed",
                                "type": "sentiment_items",
                                "items": sentiment_data,
                            })
                        except Exception as send_err:
                            print(f"⚠️ Failed to send sentiment items to feed: {send_err}")
                        
                    elif function_name == "fetch_grokipedia_article":
                        article_data = fetch_grokipedia_article(**function_args)
                        function_response = json.dumps(article_data)
                    
                    else:
                        function_response = "Error: Tool not found"

                    print(f"✅ Tool execution complete. Response length: {len(function_response)}")

                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                    })
            else:
                print("🏁 No more tools. Generating final report...")
                break

        await websocket.send_json({
            "message_type": "research",
            "type": "thinking",
            "content": "Generating final report..."
        })

        print("🌊 Streaming final response...")
        stream = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            stream=True
        )

        full_content = ""
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content += content
                
                await websocket.send_json({
                    "message_type": "research",
                    "type": "delta",
                    "content": content
                })
        print("✅ Stream complete.")

        recommendation = "NOOP"
        if "RECOMMENDATION: YES" in full_content.upper():
            recommendation = "YES"
        elif "RECOMMENDATION: NO" in full_content.upper():
            recommendation = "NO"

        await websocket.send_json({
            "message_type": "research",
            "type": "complete",
            "recommendation": recommendation
        })
        
        print("✅ Analysis complete.")

    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        await websocket.send_json({
            "message_type": "research",
            "type": "error",
            "error": str(e)
        })
