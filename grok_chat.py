import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = "grok-4-1-fast-non-reasoning"

XAI_API_KEY = os.getenv("XAI_API_KEY")

# Initialize xAI client (uses OpenAI SDK with custom base URL)
client = AsyncOpenAI(
    api_key=XAI_API_KEY,
    base_url="https://api.x.ai/v1",
)


async def stream_chat_response(messages: list[dict], websocket):
    """
    Stream chat responses from xAI API to the client via WebSocket.

    Args:
        messages: List of chat messages with 'role' and 'content'
        websocket: FastAPI WebSocket connection to stream responses to
    """
    if not XAI_API_KEY:
        await websocket.send_json(
            {"type": "error", "error": "XAI_API_KEY not configured"}
        )
        return

    try:
        # Create streaming chat completion
        stream = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            stream=True,
            temperature=0.7,
        )

        # Stream the response
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                content = delta.content

                if content:
                    # Send text delta to client
                    await websocket.send_json(
                        {"type": "chat_delta", "content": content}
                    )

        # Send completion signal
        await websocket.send_json({"type": "chat_complete"})

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Chat error: {error_msg}")
        await websocket.send_json({"type": "error", "error": f"Error: {error_msg}"})
