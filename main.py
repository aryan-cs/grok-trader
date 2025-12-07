from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import json
from grok_chat import stream_chat_response
from grok_research import research_market, research_followup
from polymarket.asset_id import fetch_event_market_slugs

app = FastAPI()

# Enable CORS for the extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Store active WebSocket connections by client ID
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
    messages: list[dict]  # Full conversation history


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Handle chat message POST requests and stream responses via WebSocket"""
    client_id = request.client_id

    # Check if WebSocket connection exists
    if client_id not in websocket_connections:
        return {"error": "WebSocket not connected. Please establish WebSocket connection first."}

    websocket = websocket_connections[client_id]

    print(f"💬 Chat request from {client_id}: {len(request.messages)} messages")

    # Stream the response via WebSocket
    await stream_chat_response(request.messages, websocket)

    return {"status": "streaming"}


@app.post("/research")
async def research_endpoint(request: ResearchRequest):
    """Handle market research requests and stream responses via WebSocket"""
    client_id = request.client_id

    # Check if WebSocket connection exists
    if client_id not in websocket_connections:
        return {"error": "WebSocket not connected. Please establish WebSocket connection first."}

    websocket = websocket_connections[client_id]

    print(f"🔬 Research request from {client_id}: {request.market_title}")

    # Stream the research via WebSocket
    await research_market(
        websocket=websocket,
        market_title=request.market_title,
        market_rules="",
        custom_instructions=request.custom_notes,
        yes_price=500,
        no_price=500
    )

    return {"status": "streaming"}


@app.post("/research/followup")
async def research_followup_endpoint(request: ResearchFollowupRequest):
    """Handle research follow-up questions and stream responses via WebSocket"""
    client_id = request.client_id

    # Check if WebSocket connection exists
    if client_id not in websocket_connections:
        return {"error": "WebSocket not connected. Please establish WebSocket connection first."}

    websocket = websocket_connections[client_id]

    print(f"💬 Research follow-up from {client_id}: {len(request.messages)} messages")

    # Stream the follow-up response via WebSocket
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
            # Receive message from client
            data = await websocket.receive_text()

            try:
                message = json.loads(data)

                # Handle client registration
                if message.get('type') == 'register':
                    client_id = message.get('client_id')
                    if client_id:
                        websocket_connections[client_id] = websocket
                        print(f"📝 Registered client: {client_id}")
                        await websocket.send_json({
                            'type': 'registered',
                            'client_id': client_id
                        })

                # Handle event slug
                elif message.get('event_slug'):
                    event_slug = message.get('event_slug')
                    print(f"📍 Received event slug: {event_slug}")

                    # Send acknowledgment back to client
                    response = {
                        'status': 'success',
                        'message': f'Processing event: {event_slug}'
                    }
                    await websocket.send_json(response)
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
        # Remove from connections
        if client_id and client_id in websocket_connections:
            del websocket_connections[client_id]
            print(f"🗑️ Removed client: {client_id}")


if __name__ == "__main__":
    print("Starting FastAPI WebSocket server on ws://localhost:8765/ws")
    uvicorn.run(app, host="localhost", port=8765)
