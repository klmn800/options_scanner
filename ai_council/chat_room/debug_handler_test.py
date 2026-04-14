"""
Flask-SocketIO Handler Debug Test
================================

Minimal test to isolate the send_message handler registration issue.
"""

from flask import Flask
from flask_socketio import SocketIO, emit
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'debug-test-key'
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

# Global test counter
message_count = 0

@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Handler Debug Test</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    </head>
    <body>
        <h1>Handler Debug Test</h1>
        <div id="log"></div>
        <input id="messageInput" placeholder="Type message">
        <button onclick="sendMessage()">Send</button>
        
        <script>
            const socket = io();
            const log = document.getElementById('log');
            
            function addLog(msg) {
                const div = document.createElement('div');
                div.textContent = new Date().toLocaleTimeString() + ': ' + msg;
                log.appendChild(div);
            }
            
            socket.on('connect', function() {
                addLog('Connected to server');
            });
            
            socket.on('test_response', function(data) {
                addLog('Received test_response: ' + JSON.stringify(data));
            });
            
            function sendMessage() {
                const input = document.getElementById('messageInput');
                const message = input.value.trim();
                if (message) {
                    addLog('Sending message: ' + message);
                    socket.emit('send_message', {message: message});
                    input.value = '';
                }
            }
            
            // Send message on Enter
            document.getElementById('messageInput').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    sendMessage();
                }
            });
        </script>
    </body>
    </html>
    '''

@socketio.on('connect')
def on_connect():
    print("DEBUG_TEST: Client connected")
    logger.info("DEBUG_TEST: Client connected")

@socketio.on('disconnect')
def on_disconnect():
    print("DEBUG_TEST: Client disconnected")
    logger.info("DEBUG_TEST: Client disconnected")

@socketio.on('send_message')
def handle_send_message(data):
    """MINIMAL TEST HANDLER for send_message"""
    global message_count
    message_count += 1
    
    print(f"DEBUG_TEST: HANDLER EXECUTED! Count: {message_count}")
    print(f"DEBUG_TEST: Received data: {data}")
    logger.info(f"DEBUG_TEST: HANDLER EXECUTED! Count: {message_count}")
    logger.info(f"DEBUG_TEST: Received data: {data}")
    
    # Send a simple response
    response_data = {
        'status': 'SUCCESS',
        'message_count': message_count,
        'received_message': data.get('message', 'NO MESSAGE'),
        'timestamp': str(__import__('datetime').datetime.now())
    }
    
    emit('test_response', response_data)
    print(f"DEBUG_TEST: Emitted test_response: {response_data}")

if __name__ == '__main__':
    print("Starting Flask-SocketIO Handler Debug Test")
    print("Visit http://localhost:5001 to test")
    socketio.run(app, host='0.0.0.0', port=5001, debug=True)