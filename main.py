from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import json
import asyncio
from grok_chat import stream_chat_response
from grok_research import research_market, research_followup
from polymarket.asset_id import fetch_event_market_slugs
from polymarket.feed import PolymarketFeed
from autotrade_orm import AutoTrade
from autotrader import start_autotrader

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

# Store active auto trades by market slug (one per market)
active_autotrades: dict[str, AutoTrade] = {}  # market_slug -> AutoTrade object

# Store running autotrader feeds by market slug
active_feeds: dict[str, PolymarketFeed] = {}  # market_slug -> PolymarketFeed


class ChatRequest(BaseModel):
    client_id: str
    messages: list[dict]
    event_slug: str | None = None
    market_slug: str | None = None


class ResearchRequest(BaseModel):
    client_id: str
    market_title: str
    event_slug: str = ""
    custom_notes: str = ""


class ResearchFollowupRequest(BaseModel):
    client_id: str
    messages: list[dict]  # Full conversation history


class AutoTradeRequest(BaseModel):
    client_id: str
    event_slug: str
    market_slug: str
    condition: str  # Natural language condition - model will determine buy/sell
    amount: float  # dollar amount
    limit: float  # limit price


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Handle chat message POST requests and stream responses via WebSocket"""
    client_id = request.client_id

    # Check if WebSocket connection exists
    if client_id not in websocket_connections:
        return {
            "error": "WebSocket not connected. Please establish WebSocket connection first."
        }

    websocket = websocket_connections[client_id]

    market_context = f" (market: {request.market_slug})" if request.market_slug else ""
    print(
        f"💬 Chat request from {client_id}: {len(request.messages)} messages{market_context}"
    )

    # Stream the response via WebSocket
    await stream_chat_response(request.messages, websocket, request.market_slug)

    return {"status": "streaming"}


@app.post("/research")
async def research_endpoint(request: ResearchRequest):
    """Handle market research requests and stream responses via WebSocket"""
    client_id = request.client_id

    # Check if WebSocket connection exists
    if client_id not in websocket_connections:
        return {
            "error": "WebSocket not connected. Please establish WebSocket connection first."
        }

    websocket = websocket_connections[client_id]

    print(f"🔬 Research request from {client_id}: {request.market_title}")

    # Fetch live market prices using PolymarketFeed
    yes_price = 500  # Default fallback
    no_price = 500  # Default fallback

    await websocket.send_json(
        {
            "message_type": "research",
            "type": "thinking",
            "content": "Fetching live market prices...",
        }
    )
    await asyncio.sleep(0)  # Yield to event loop to flush WebSocket

    try:
        # Create feed and subscribe to market
        feed = PolymarketFeed(verbose=False)
        feed.subscribe_market(
            market_slug=request.market_title,
            event_slug=request.event_slug if request.event_slug else None,
        )

        # Start feed in background
        feed.start_in_background()

        # Wait for orderbooks to be populated (max 5 seconds)
        max_wait = 10
        waited = 0
        while waited < max_wait:
            await asyncio.sleep(0.5)
            waited += 0.5

            # Check if we have orderbooks for this market
            if request.market_title in feed.market_tokens:
                tokens = feed.market_tokens[request.market_title]
                yes_token_id = tokens.get("yes")

                if yes_token_id and yes_token_id in feed.orderbooks:
                    yes_ob = feed.orderbooks[yes_token_id]

                    # Get best bid and best ask
                    best_ask_list = yes_ob.best_ask(1)
                    best_bid_list = yes_ob.best_bid(1)

                    if best_ask_list and best_bid_list:
                        best_ask = best_ask_list[0][0]  # (price, size) tuple
                        best_bid = best_bid_list[0][0]

                        # Calculate prices as specified
                        yes_price = int(
                            100 * best_ask * 10
                        )  # *10 because prices are in cents*10
                        no_price = int(100 * (1 - best_bid) * 10)

                        print(
                            f"✓ Got live prices: YES={yes_price/10:.1f}¢ NO={no_price/10:.1f}¢"
                        )
                        break

        # Stop the feed
        if feed.ws:
            feed.ws.close()

    except Exception as e:
        print(f"⚠️  Error fetching live prices: {e}")
        print(f"   Using default prices: YES=50¢ NO=50¢")

    print(f"💰 Yes price: {yes_price}, No price: {no_price}")
    # Stream the research via WebSocket
    await research_market(
        websocket=websocket,
        market_title=request.market_title,
        market_rules="",
        custom_instructions=request.custom_notes,
        yes_price=yes_price,
        no_price=no_price,
    )

    return {"status": "streaming"}


@app.post("/research/followup")
async def research_followup_endpoint(request: ResearchFollowupRequest):
    """Handle research follow-up questions and stream responses via WebSocket"""
    client_id = request.client_id

    # Check if WebSocket connection exists
    if client_id not in websocket_connections:
        return {
            "error": "WebSocket not connected. Please establish WebSocket connection first."
        }

    websocket = websocket_connections[client_id]

    print(f"💬 Research follow-up from {client_id}: {len(request.messages)} messages")

    # Stream the follow-up response via WebSocket
    await research_followup(websocket, request.messages)

    return {"status": "streaming"}


@app.post("/autotrade/start")
async def start_autotrade(request: AutoTradeRequest, background_tasks: BackgroundTasks):
    """Start an auto trade that monitors for specified conditions"""
    client_id = request.client_id

    print(f"🤖 Auto trade request from {client_id}:")
    print(f"   Event: {request.event_slug}")
    print(f"   Market: {request.market_slug}")
    print(f"   Condition: {request.condition}")
    print(f"   Amount: ${request.amount}")
    print(f"   Limit: {request.limit}")

    # Check if there's already an auto trade for this market
    if request.market_slug in active_autotrades:
        existing_trade = active_autotrades[request.market_slug]
        return {
            "status": "error",
            "message": f"Auto trade already active for this market: {existing_trade.id}",
            "existing_auto_trade_id": existing_trade.id,
        }

    # Generate a unique auto trade ID
    import time

    auto_trade_id = f"auto_{int(time.time())}_{client_id[:8]}"

    # Get websocket connection for this client
    websocket = websocket_connections.get(client_id)

    # Create AutoTrade object
    auto_trade = AutoTrade(
        id=auto_trade_id,
        event_slug=request.event_slug,
        market_slug=request.market_slug,
        condition=request.condition,
        amount=request.amount,
        limit=request.limit,
        websocket=websocket,
    )

    # Store in active auto trades
    active_autotrades[request.market_slug] = auto_trade

    # Start the autotrader in background
    try:
        feed = start_autotrader(auto_trade)
        active_feeds[request.market_slug] = feed
        print(f"✓ Started autotrader for {request.market_slug}")
    except Exception as e:
        print(f"❌ Failed to start autotrader: {e}")
        # Clean up on failure
        del active_autotrades[request.market_slug]
        return {
            "status": "error",
            "message": f"Failed to start autotrader: {str(e)}"
        }

    print(f"✓ Stored auto trade {auto_trade_id} for market {request.market_slug}")

    return {
        "status": "success",
        "auto_trade_id": auto_trade_id,
        "message": f"Auto trade started. Monitoring for specified condition.",
        "condition": request.condition,
        "amount": request.amount,
        "limit": request.limit,
    }


@app.get("/autotrade/status/{auto_trade_id}")
async def get_autotrade_status(auto_trade_id: str):
    """Get the status of an active auto trade"""
    print(f"📊 Status request for auto trade: {auto_trade_id}")

    # Check if this auto trade exists
    found_trade = None
    for market_slug, trade in active_autotrades.items():
        if trade.id == auto_trade_id:
            found_trade = trade
            break

    if not found_trade:
        return {
            "status": "not_found",
            "auto_trade_id": auto_trade_id,
            "message": "Auto trade not found or already stopped",
        }

    # TODO: Implement detailed status lookup
    return {
        "status": "active",
        "auto_trade_id": auto_trade_id,
        "auto_trade": found_trade.to_dict(),
        "condition_met": False,
        "trades_executed": 0,
        "message": "Monitoring conditions...",
    }


@app.get("/autotrade/list")
async def list_autotrades():
    """List all active auto trades"""
    print(f"📋 Listing {len(active_autotrades)} active auto trades")

    return {
        "status": "success",
        "count": len(active_autotrades),
        "active_trades": [
            {"market_slug": market, "auto_trade": trade.to_dict()}
            for market, trade in active_autotrades.items()
        ],
    }


@app.get("/autotrade/market/{market_slug}")
async def get_autotrade_by_market(market_slug: str):
    """Get the auto trade for a specific market"""
    print(f"🔍 Looking up auto trade for market: {market_slug}")

    auto_trade = active_autotrades.get(market_slug)

    if auto_trade is None:
        return {"auto_trade": None}

    return {"auto_trade": auto_trade.to_dict()}


@app.post("/autotrade/stop/{auto_trade_id}")
async def stop_autotrade(auto_trade_id: str):
    """Stop an active auto trade"""
    print(f"🛑 Stop request for auto trade: {auto_trade_id}")

    # Find and remove the auto trade
    market_to_remove = None
    for market_slug, trade in active_autotrades.items():
        if trade.id == auto_trade_id:
            market_to_remove = market_slug
            break

    if not market_to_remove:
        return {
            "status": "error",
            "auto_trade_id": auto_trade_id,
            "message": "Auto trade not found",
        }

    # Stop the autotrader feed if running
    if market_to_remove in active_feeds:
        try:
            feed = active_feeds[market_to_remove]
            # Close the websocket connection
            if feed.ws:
                feed.ws.close()
                print(f"✓ Closed websocket for {market_to_remove}")
            del active_feeds[market_to_remove]
            print(f"✓ Stopped autotrader feed for {market_to_remove}")
        except Exception as e:
            print(f"⚠️ Error stopping feed: {e}")

    # Remove from active trades
    del active_autotrades[market_to_remove]
    print(f"✓ Removed auto trade {auto_trade_id} from market {market_to_remove}")

    return {
        "status": "stopped",
        "auto_trade_id": auto_trade_id,
        "message": "Auto trade stopped successfully",
    }


@app.get("/market-slugs")
async def get_market_slugs(
    event_slug: str = Query(..., description="The event slug to fetch market slugs for")
):
    """Get all market slugs for a given event slug"""
    try:
        print(f"📊 Fetching market slugs for event: {event_slug}")
        slugs = fetch_event_market_slugs(event_slug)

        return {"status": "success", "event_slug": event_slug, "market_slugs": slugs}
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error fetching market slugs: {error_msg}")
        return {"status": "error", "error": error_msg}


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
                if message.get("type") == "register":
                    client_id = message.get("client_id")
                    if client_id:
                        websocket_connections[client_id] = websocket
                        print(f"📝 Registered client: {client_id}")
                        await websocket.send_json(
                            {"type": "registered", "client_id": client_id}
                        )

                # Handle event slug
                elif message.get("event_slug"):
                    event_slug = message.get("event_slug")
                    print(f"📍 Received event slug: {event_slug}")

                    # Send acknowledgment back to client
                    response = {
                        "status": "success",
                        "message": f"Processing event: {event_slug}",
                    }
                    await websocket.send_json(response)
                else:
                    print(f"❓ Received unknown message: {data}")

            except json.JSONDecodeError:
                print(f"Invalid JSON received: {data}")
                error_response = {"type": "error", "message": "Invalid JSON format"}
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
