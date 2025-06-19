import asyncio
import json
import websockets
import threading
import time
import os
from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

app = Flask(__name__, static_folder='static')
socketio = SocketIO(app, cors_allowed_origins="*")

# Global dictionary for the latest data for each currency pair
latest_data = {}

# G10 Currency pairs to track
G10_PAIRS = [
    'EURUSD', 'USDJPY', 'GBPUSD', 'US30USD',
    'USDCAD', 'USDCHF', 'AUDUSD', 'OILUSD', 
    'EURCHF', 'EURJPY', 'UKOILUSD', 'UK100USD',
     "XAUUSD", 'BTCUSD', "EURNOK"
]

class TraderMadeStream:
    def __init__(self):
        self.api_key = None
        self.symbols = []
        self.websocket = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 3  # seconds
        self.running = False

    def set_ws_key(self, api_key):
        """Set the TraderMade WebSocket API key"""
        self.api_key = api_key
        print("API Key set successfully")

    def set_symbols(self, symbols_string):
        """Set the symbols to stream, as a comma-separated string"""
        self.symbols = [s.strip() for s in symbols_string.split(',')]
        print(f"Symbols set: {', '.join(self.symbols)}")

    async def connect_and_stream(self):
        """Connect to the TraderMade WebSocket and stream data"""
        if not self.api_key:
            raise ValueError("API Key not set. Use set_ws_key() first.")
        if not self.symbols:
            raise ValueError("No symbols set. Use set_symbols() first.")
        
        self.running = True
        while self.running:
            try:
                uri = f"wss://marketdata.tradermade.com/feedadv?api_key={self.api_key}"
                async with websockets.connect(uri) as websocket:
                    self.websocket = websocket
                    self.reconnect_attempts = 0
                    print("WebSocket connection established")
                    
                    # Subscribe to the specified symbols
                    subscribe_msg = {
                        "userKey": self.api_key,
                        "symbol": ",".join(self.symbols)
                    }
                    await websocket.send(json.dumps(subscribe_msg))
                    
                    # Process incoming messages
                    while self.running:
                        message = await websocket.recv()
                        # Skip if empty
                        if not message.strip():
                            continue
                        # Skip initial confirmation message "connected"
                        if message.strip().lower() == "connected":
                            print("Received initial connection confirmation, skipping message")
                            continue
                        
                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError as e:
                            print("Error decoding JSON message:", message, "-", e)
                            continue
                        
                        self.process_message(data)
            
            except websockets.exceptions.ConnectionClosed:
                print("WebSocket connection closed")
                await self.handle_reconnect()
            except Exception as e:
                print(f"WebSocket error: {e}")
                await self.handle_reconnect()

    async def handle_reconnect(self):
        """Handle reconnection logic"""
        if not self.running:
            return
        if self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            reconnect_time = self.reconnect_delay * self.reconnect_attempts
            print(f"Attempting to reconnect ({self.reconnect_attempts}/{self.max_reconnect_attempts}) in {reconnect_time} seconds...")
            await asyncio.sleep(reconnect_time)
        else:
            print("Max reconnect attempts reached. Please check your connection or API key.")
            self.running = False

    def process_message(self, data):
        """Process and store the incoming market data and emit it to clients"""
        if isinstance(data, dict) and 'symbol' in data:
            symbol = data['symbol']
            latest_data[symbol] = data
            print(data)
            socketio.emit('market_update', data)
            # if 'bid' in data and 'ask' in data:
            #     print(f"Received data for {symbol}: Bid: {data['bid']}, Ask: {data['ask']}")

    def disconnect(self):
        """Disconnect from the WebSocket"""
        self.running = False
        print("WebSocket connection manually closed")

    def start_streaming(self):
        """Start the streaming in a separate thread"""
        def run_streaming():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.connect_and_stream())
            
        thread = threading.Thread(target=run_streaming)
        thread.daemon = True
        thread.start()

# Create an instance of TraderMadeStream
tm_stream = TraderMadeStream()

@app.route('/')
def index():
    return render_template('index3.html')

# @app.route('/2')
# def index2():
#     return render_template('index2.html')

# @app.route('/3')
# def index3():
#     return render_template('index3.html')

# Route to serve static files if needed (optional)
@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

# Socket.IO events
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    tm_stream.start_streaming()
    if latest_data:
        socketio.emit('initial_data', latest_data)

@socketio.on('disconnect')
def handle_disconnect():
    tm_stream.disconnect()
    print('Client disconnected')

# Run the server
if __name__ == "__main__":
    # Get API key from .env
    API_KEY = os.getenv("TRADERMADE_API_KEY")
    if not API_KEY:
        print("Error: TRADERMADE_API_KEY is not set in the .env file")
        exit(1)
    
    # Configure the TraderMadeStream with the API key and symbols
    tm_stream.set_ws_key(API_KEY)
    tm_stream.set_symbols(','.join(G10_PAIRS))
    
    # Start streaming data in the background
    # tm_stream.start_streaming()
    
    # Start the Flask-SocketIO server on port 5000
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True, use_reloader=False)
