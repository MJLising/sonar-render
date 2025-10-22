# pi_sender.py
import asyncio
import json
import time
import RPi.GPIO as GPIO
import websockets
import datetime
import os

TRIG = 5
ECHO = 6

GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
SOUND_SPEED = 343.0  # air; change to 1482 if underwater

# set this after deploy: wss://<yourservice>.onrender.com/ws/publisher
WS_SERVER = os.environ.get("WS_SERVER", "wss://sonar-render-4.onrender.com/ws/publisher")


def read_distance():
    GPIO.output(TRIG, False)
    time.sleep(0.05)
    GPIO.output(TRIG, True)
    time.sleep(0.00002)
    GPIO.output(TRIG, False)

    start = time.perf_counter()
    timeout = start + 0.05
    while GPIO.input(ECHO) == 0 and time.perf_counter() < timeout:
        start = time.perf_counter()
    if time.perf_counter() >= timeout:
        return None

    end = time.perf_counter()
    timeout = end + 0.05
    while GPIO.input(ECHO) == 1 and time.perf_counter() < timeout:
        end = time.perf_counter()
    if time.perf_counter() >= timeout:
        return None

    pulse = end - start
    distance_m = (pulse * SOUND_SPEED) / 2.0
    return distance_m

async def send_loop():
    async with websockets.connect(WS_SERVER, open_timeout=20, ping_interval=20) as ws:
        print("Connected to server")
        try:
            while True:
                d = read_distance()
                timestamp = datetime.datetime.utcnow().isoformat() + "Z"
                angle_deg = 0.0
                payload = {
                    "distance_m": None if d is None else round(d, 3),
                    "angle_deg": angle_deg,
                    "timestamp": timestamp,
                    "quality": "ok" if d is not None else "no_echo"
                }
                await ws.send(json.dumps(payload))
                await asyncio.sleep(0.2)
        finally:
            GPIO.cleanup()

if __name__ == "__main__":
    asyncio.run(send_loop())
