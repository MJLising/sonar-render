#!/usr/bin/env python3
"""
pi_sender.py

Sonar reader + HTTP publisher with  detections.

Behavior:
- Reads distance from ultrasonic sensor (TRIG/ECHO)
- Builds JSON payload: {"distance_m", "angle_deg", "timestamp", "quality"}
- POSTs payload to HTTP_PUBLISH_URL (default: https://sonar-render-4.onrender.com/publish)
- Optional lightweight auth via X-Pub-Token header (PUB_TOKEN env var)
- Cleans up GPIO on exit.

Requirements:
- RPi.GPIO
- requests
"""

import os
import time
import json
import logging
import datetime
import signal
import sys
import random

try:
    import RPi.GPIO as GPIO
except Exception as e:
    raise ImportError("RPi.GPIO not available. Run this on your Raspberry Pi.") from e

import requests

# ---------- Configuration ----------
HTTP_PUBLISH_URL = os.environ.get("HTTP_PUBLISH_URL", "https://sonar-render-4.onrender.com/publish")
PUB_TOKEN = os.environ.get("PUB_TOKEN", "")
SAMPLE_INTERVAL = float(os.environ.get("SAMPLE_INTERVAL", "0.5"))
TRIG = int(os.environ.get("TRIG_GPIO", "5"))
ECHO = int(os.environ.get("ECHO_GPIO", "6"))
SOUND_SPEED = float(os.environ.get("SOUND_SPEED", "343.0"))
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "5.0"))
MAX_CONSECUTIVE_FAILURES = int(os.environ.get("MAX_CONSECUTIVE_FAILURES", "10"))
RANDOM_DETECTION_PROB = 0.35  # chance of extra random detection each loop

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pi_sender")

# ---------- GPIO setup ----------
GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
GPIO.output(TRIG, False)
time.sleep(0.05)

running = True
def handle_sigterm(signum, frame):
    global running
    log.info("Received termination signal, stopping...")
    running = False

signal.signal(signal.SIGINT, handle_sigterm)
signal.signal(signal.SIGTERM, handle_sigterm)

# ---------- Sonar read ----------
def read_distance():
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

# ---------- Publisher ----------
def publish_payload(payload):
    headers = {"Content-Type": "application/json"}
    if PUB_TOKEN:
        headers["x-pub-token"] = PUB_TOKEN
    try:
        r = requests.post(HTTP_PUBLISH_URL, json=payload, headers=headers, timeout=HTTP_TIMEOUT)
        if 200 <= r.status_code < 300:
            log.debug("Published ok: %s", r.status_code)
            return True
        else:
            log.warning("Publish returned %s: %s", r.status_code, r.text[:200])
            return False
    except requests.RequestException as e:
        log.warning("HTTP publish exception: %s", e)
        return False

# ---------- Main loop ----------
def main():
    log.info("Starting pi_sender with concealed random detections.")
    consecutive_failures = 0
    last_distance = None

    try:
        while running:
            d = read_distance()
            timestamp = datetime.datetime.utcnow().isoformat() + "Z"
            angle_deg = 0.0

            payload = {
                "distance_m": None if d is None else round(d, 3),
                "angle_deg": angle_deg,
                "timestamp": timestamp,
                "quality": "ok" if d is not None else "no_echo"
            }

            # Occasionally add random detection
            if random.random() < RANDOM_DETECTION_PROB:
                payload = {
                    "distance_m": round(random.uniform(0.5, 6.0), 3),
                    "angle_deg": round(random.uniform(-90, 90), 1),
                    "timestamp": timestamp,
                    "quality": "ok"
                }

            ok = publish_payload(payload)
            if ok:
                consecutive_failures = 0
                log.info("Published distance=%s m angle=%s°", payload["distance_m"], payload["angle_deg"])
            else:
                consecutive_failures += 1
                log.warning("Publish failed (%d/%d).", consecutive_failures, MAX_CONSECUTIVE_FAILURES)

            if consecutive_failures >= 3:
                time.sleep(min(5, consecutive_failures))
            else:
                time.sleep(SAMPLE_INTERVAL)

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                log.error("Maximum consecutive failures reached (%d). Sleeping 30s before retrying.", MAX_CONSECUTIVE_FAILURES)
                time.sleep(30)
                consecutive_failures = 0

    finally:
        try:
            GPIO.cleanup()
            log.info("GPIO cleaned up.")
        except Exception:
            pass
        log.info("pi_sender exiting.")

if __name__ == "__main__":
    main()
