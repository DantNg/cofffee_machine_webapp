import time
import socketio

received = 0

sio = socketio.Client()

@sio.event
def connect():
    print("[CLIENT] Connected to server")

@sio.event
def disconnect():
    print("[CLIENT] Disconnected from server")

@sio.on('message')
def on_message(msg):
    global received
    if isinstance(msg, dict) and msg.get('type') == 'data_update':
        payload = msg.get('payload', {})
        print(f"[DATA] pressure={payload.get('pressure')} grams={payload.get('grams')} ts={payload.get('ts')}")
        received += 1
        if received >= 10:
            print("[CLIENT] Received 10 updates, disconnecting...")
            sio.disconnect()

if __name__ == '__main__':
    sio.connect('http://127.0.0.1:5000')
    while sio.connected:
        time.sleep(0.1)
