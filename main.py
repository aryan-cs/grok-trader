from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json

app = FastAPI()

# Enable CORS for the extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handle WebSocket connections"""
    await websocket.accept()
    client_host = websocket.client.host if websocket.client else "unknown"
    client_port = websocket.client.port if websocket.client else "unknown"
    print(f"✓ Client connected from {client_host}:{client_port}")

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                event_slug = message.get('event_slug')

                if event_slug:
                    print(f"Received event slug: {event_slug}")

                    # Send acknowledgment back to client
                    response = {
                        'status': 'success',
                        'message': f'Processing event: {event_slug}'
                    }
                    await websocket.send_json(response)
                else:
                    print(f"Received message without event_slug: {data}")

            except json.JSONDecodeError:
                print(f"Invalid JSON received: {data}")
                error_response = {
                    'status': 'error',
                    'message': 'Invalid JSON format'
                }
                await websocket.send_json(error_response)

    except WebSocketDisconnect:
        print(f"✗ Client disconnected from {client_host}:{client_port}")


if __name__ == "__main__":
    print("Starting FastAPI WebSocket server on ws://localhost:8765/ws")
    uvicorn.run(app, host="localhost", port=8765)
