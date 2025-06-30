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

# Track connected clients for logging purposes
connected_clients = 0
client_lock = threading.Lock()

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
        self.max_reconnect_attempts = 10  # Increased for persistent connection
        self.reconnect_delay = 5  # seconds
        self.running = False
        self.stream_thread = None
        self.connection_established = False

    def set_ws_key(self, api_key):
        """Set the TraderMade WebSocket API key"""
        self.api_key = api_key
        print("API Key set successfully")

    def set_symbols(self, symbols_string):
        """Set the symbols to stream, as a comma-separated string"""
        self.symbols = [s.strip() for s in symbols_string.split(',')]
        print(f"Symbols set: {', '.join(self.symbols)}")

    async def connect_and_stream(self):
        """Connect to the TraderMade WebSocket and stream data persistently"""
        if not self.api_key:
            raise ValueError("API Key not set. Use set_ws_key() first.")
        if not self.symbols:
            raise ValueError("No symbols set. Use set_symbols() first.")
        
        while self.running:
            try:
                uri = f"wss://marketdata.tradermade.com/feedadv?api_key={self.api_key}"
                print(f"Attempting to connect to WebSocket...")
                
                async with websockets.connect(
                    uri,
                    ping_interval=20,  # Send ping every 20 seconds
                    ping_timeout=10,   # Wait 10 seconds for pong
                    close_timeout=10   # Wait 10 seconds when closing
                ) as websocket:
                    self.websocket = websocket
                    self.reconnect_attempts = 0
                    self.connection_established = True
                    print("✅ WebSocket connection established and persistent")
                    
                    # Subscribe to the specified symbols
                    subscribe_msg = {
                        "userKey": self.api_key,
                        "symbol": ",".join(self.symbols)
                    }
                    await websocket.send(json.dumps(subscribe_msg))
                    print(f"📡 Subscribed to symbols: {', '.join(self.symbols)}")
                    
                    # Process incoming messages continuously
                    while self.running:
                        try:
                            message = await websocket.recv()
                            
                            # Skip if empty
                            if not message.strip():
                                continue
                                
                            # Skip initial confirmation message "connected"
                            if message.strip().lower() == "connected":
                                print("📋 Received connection confirmation")
                                continue
                            
                            try:
                                data = json.loads(message)
                                self.process_message(data)
                            except json.JSONDecodeError as e:
                                print(f"⚠️ JSON decode error: {message[:100]}... - {e}")
                                continue
                                
                        except websockets.exceptions.ConnectionClosed:
                            print("🔌 WebSocket connection closed by server")
                            self.connection_established = False
                            break
                        except asyncio.TimeoutError:
                            print("⏰ WebSocket timeout, attempting to reconnect...")
                            self.connection_established = False
                            break
                        except Exception as e:
                            print(f"❌ Error receiving message: {e}")
                            continue
            
            except websockets.exceptions.ConnectionClosed as e:
                print(f"🔌 WebSocket connection closed: {e.code} - {e.reason}")
                self.connection_established = False
                if self.running:
                    await self.handle_reconnect()
            except websockets.exceptions.InvalidStatusCode as e:
                print(f"❌ Invalid status code: {e.status_code}")
                self.connection_established = False
                if self.running:
                    await self.handle_reconnect()
            except Exception as e:
                print(f"❌ Unexpected connection error: {e}")
                self.connection_established = False
                if self.running:
                    await self.handle_reconnect()

        print("🛑 WebSocket streaming stopped")

    async def handle_reconnect(self):
        """Handle reconnection logic with exponential backoff"""
        if not self.running:
            return
            
        if self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            # Exponential backoff: 5, 10, 20, 40, 60, 60, 60... (max 60 seconds)
            reconnect_time = min(self.reconnect_delay * (2 ** (self.reconnect_attempts - 1)), 60)
            print(f"🔄 Reconnect attempt {self.reconnect_attempts}/{self.max_reconnect_attempts} in {reconnect_time} seconds...")
            await asyncio.sleep(reconnect_time)
        else:
            print("❌ Max reconnect attempts reached. Continuing to retry every 60 seconds...")
            # Don't stop trying, just use longer delays
            await asyncio.sleep(60)
            self.reconnect_attempts = self.max_reconnect_attempts - 1  # Reset to keep trying

    def process_message(self, data):
        """Process and store the incoming market data and emit it to clients"""
        if isinstance(data, dict) and 'symbol' in data:
            symbol = data['symbol']
            latest_data[symbol] = data
            
            # Add timestamp for debugging
            data['server_timestamp'] = int(time.time() * 1000)
            
            print(f"📊 {symbol}: {data.get('bid', 'N/A')}/{data.get('ask', 'N/A')}")
            
            # Always emit to connected clients (SocketIO handles if no clients)
            socketio.emit('market_update', data)

    def start_streaming(self):
        """Start the persistent streaming in a separate thread"""
        if self.running and self.stream_thread and self.stream_thread.is_alive():
            print("📡 WebSocket stream already running")
            return
        
        def run_streaming():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.connect_and_stream())
            except Exception as e:
                print(f"❌ Streaming thread error: {e}")
            finally:
                loop.close()

        self.running = True    
        self.stream_thread = threading.Thread(target=run_streaming, name="WebSocketStream")
        self.stream_thread.daemon = True
        self.stream_thread.start()
        print("🚀 Started persistent WebSocket streaming thread")

    def stop_streaming(self):
        """Stop the streaming"""
        print("🛑 Stopping WebSocket stream...")
        self.running = False
        self.connection_established = False
        
        # The connection will close naturally when the async loop detects running=False
        if self.stream_thread and self.stream_thread.is_alive():
            print("⏳ Waiting for stream thread to finish...")
            # Give it a moment to close gracefully
            time.sleep(2)

    def is_connected(self):
        """Check if WebSocket is connected"""
        return self.connection_established and self.running

# Create an instance of TraderMadeStream
tm_stream = TraderMadeStream()

@app.route('/')
def index():
    return render_template('index3.html')

@app.route('/status')
def status():
    """Health check endpoint"""
    return {
        'websocket_connected': tm_stream.is_connected(),
        'connected_clients': connected_clients,
        'latest_data_count': len(latest_data),
        'symbols': tm_stream.symbols
    }

# Route to serve static files if needed (optional)
@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

# Socket.IO events
@socketio.on('connect')
def handle_connect():
    global connected_clients
    with client_lock:
        connected_clients += 1
        print(f'👤 Client connected. Total clients: {connected_clients}')
    
    # Send latest data to the newly connected client
    if latest_data:
        print(f"📤 Sending {len(latest_data)} cached market data points to new client")
        socketio.emit('initial_data', latest_data)
    
    # Send connection status
    socketio.emit('connection_status', {
        'websocket_connected': tm_stream.is_connected(),
        'message': 'Connected to market data feed' if tm_stream.is_connected() else 'Connecting to market data feed...'
    })

@socketio.on('disconnect')
def handle_disconnect():
    global connected_clients
    with client_lock:
        connected_clients = max(0, connected_clients - 1)
        print(f'👤 Client disconnected. Total clients: {connected_clients}')
        # Note: We do NOT stop the WebSocket stream - it stays persistent

@socketio.on('request_status')
def handle_status_request():
    """Handle client requests for connection status"""
    socketio.emit('connection_status', {
        'websocket_connected': tm_stream.is_connected(),
        'connected_clients': connected_clients,
        'latest_data_count': len(latest_data)
    })

# Graceful shutdown
import signal
import sys

def signal_handler(sig, frame):
    print('\n🛑 Gracefully shutting down...')
    tm_stream.stop_streaming()
    time.sleep(1)  # Give it a moment to clean up
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Run the server
if __name__ == "__main__":
    # Get API key from .env
    API_KEY = os.getenv("TRADERMADE_API_KEY")
    if not API_KEY:
        print("❌ Error: TRADERMADE_API_KEY is not set in the .env file")
        exit(1)
    
    # Configure the TraderMadeStream with the API key and symbols
    tm_stream.set_ws_key(API_KEY)
    tm_stream.set_symbols(','.join(G10_PAIRS))
    
    # Start the persistent WebSocket stream immediately
    print("🚀 Starting persistent WebSocket connection...")
    tm_stream.start_streaming()
    
    # Give the WebSocket a moment to establish connection
    time.sleep(2)
    
    # Start the Flask-SocketIO server on port 5000
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Starting Flask server on port {port}")
    socketio.run(app, host='0.0.0.0', port=port, debug=True, use_reloader=False)