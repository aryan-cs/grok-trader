import os
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import json
import asyncio
from grok_chat import stream_chat_response
from market_to_results import analyze_market as research_market
from grok_research import research_followup
from polymarket.asset_id import fetch_event_market_slugs
sys.path.append(os.path.join(os.path.dirname(__file__), "pre-processing"))
from process_market import get_market_sentiment

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "running", "service": "Grok Trader API"}


websocket_connections: dict[str, WebSocket] = {}


class ChatRequest(BaseModel):
    client_id: str
    messages: list[dict]
    event_slug: str | None = None


class ResearchRequest(BaseModel):
    client_id: str
    market_title: str
    custom_notes: str = ""


class ResearchFollowupRequest(BaseModel):
    client_id: str
    messages: list[dict]


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Handle chat message POST requests and stream responses via WebSocket"""
    client_id = request.client_id

    if client_id not in websocket_connections:
        return {"error": "WebSocket not connected. Please establish WebSocket connection first."}

    websocket = websocket_connections[client_id]

    print(f"💬 Chat request from {client_id}: {len(request.messages)} messages")

    await stream_chat_response(request.messages, websocket)

    return {"status": "streaming"}


@app.post("/research")
async def research_endpoint(request: ResearchRequest):
    """Handle market research requests and stream responses via WebSocket"""
    client_id = request.client_id

    if client_id not in websocket_connections:
        return {"error": "WebSocket not connected. Please establish WebSocket connection first."}

    websocket = websocket_connections[client_id]

    print(f"🔬 Research request from {client_id}: {request.market_title}")

    await research_market(
        websocket=websocket,
        market_title=request.market_title,
        custom_instructions=request.custom_notes
    )

    return {"status": "streaming"}


@app.post("/research/followup")
async def research_followup_endpoint(request: ResearchFollowupRequest):
    """Handle research follow-up questions and stream responses via WebSocket"""
    client_id = request.client_id

    if client_id not in websocket_connections:
        return {"error": "WebSocket not connected. Please establish WebSocket connection first."}

    websocket = websocket_connections[client_id]

    print(f"💬 Research follow-up from {client_id}: {len(request.messages)} messages")

    await research_followup(websocket, request.messages)

    return {"status": "streaming"}


@app.get("/market-slugs")
async def get_market_slugs(event_slug: str = Query(..., description="The event slug to fetch market slugs for")):
    """Get all market slugs for a given event slug"""
    try:
        print(f"📊 Fetching market slugs for event: {event_slug}")
        slugs = fetch_event_market_slugs(event_slug)

        return {
            "status": "success",
            "event_slug": event_slug,
            "market_slugs": slugs
        }
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error fetching market slugs: {error_msg}")
        return {
            "status": "error",
            "error": error_msg
        }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handle WebSocket connections"""
    await websocket.accept()
    client_host = websocket.client.host if websocket.client else "unknown"
    client_port = websocket.client.port if websocket.client else "unknown"
    print(f"✓ Client connected from {client_host}:{client_port}")

    client_id = None

    try:
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)

                if message.get('type') == 'register':
                    client_id = message.get('client_id')
                    if client_id:
                        websocket_connections[client_id] = websocket
                        print(f"📝 Registered client: {client_id}")
                        await websocket.send_json({
                            'type': 'registered',
                            'client_id': client_id
                        })

                elif message.get('event_slug'):
                    event_slug = message.get('event_slug')
                    print(f"📍 Received event slug: {event_slug}")

                    response = {
                        'status': 'success',
                        'message': f'Processing event: {event_slug}'
                    }
                    await websocket.send_json(response)

                elif message.get('type') == 'research_request':
                    market_title = message.get('market_title')
                    custom_notes = message.get('custom_notes', '')
                    print(f"🔬 Research request via WS: {market_title}")
                    
                    asyncio.create_task(research_market(
                        websocket=websocket,
                        market_title=market_title,
                        custom_instructions=custom_notes
                    ))

                elif message.get('type') == 'feed_request':
                    market_title = message.get('market_title')
                    print(f"🧠 Feed sentiment request via WS: {market_title}")

                    async def send_feed():
                        try:
                            items = get_market_sentiment(market=market_title, verbose=True)
                            print(f"📨 Feed items ready ({len(items)} items) for market: {market_title}")
                            await websocket.send_json({
                                "message_type": "feed",
                                "type": "sentiment_items",
                                "items": items,
                            })
                        except Exception as e:
                            err_msg = str(e)
                            print(f"❌ Feed request error: {err_msg}")
                            await websocket.send_json({
                                "message_type": "feed",
                                "type": "error",
                                "error": err_msg,
                            })

                    asyncio.create_task(send_feed())

                else:
                    print(f"❓ Received unknown message: {data}")

            except json.JSONDecodeError:
                print(f"Invalid JSON received: {data}")
                error_response = {
                    'type': 'error',
                    'message': 'Invalid JSON format'
                }
                await websocket.send_json(error_response)

    except WebSocketDisconnect:
        print(f"✗ Client disconnected from {client_host}:{client_port}")
        if client_id and client_id in websocket_connections:
            del websocket_connections[client_id]
            print(f"🗑️ Removed client: {client_id}")


if __name__ == "__main__":
    print("Starting FastAPI WebSocket server on ws://localhost:8765/ws")
    uvicorn.run(app, host="localhost", port=8765)
