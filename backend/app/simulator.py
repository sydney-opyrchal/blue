"""
Simulated edge gateway publishing telemetry for the New Glenn factory floor.

This represents what an OPC UA -> MQTT bridge would do at the cell level:
read tags from PLCs, package them, and publish to the broker.

Run:  python -m app.simulator
"""
import json
import math
import os
import random
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List

import paho.mqtt.client as mqtt

from app.assets import ASSETS

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
PUBLISH_HZ = 2  # 2 messages per metric per second

# --- Anomaly injection ---------------------------------------------------------
# Periodically drift one asset out of nominal to demonstrate alarm logic.
ANOMALY_CHANCE_PER_TICK = 0.0008   # ~one anomaly every few minutes per asset
ANOMALY_DURATION_SEC = (15, 45)


@dataclass
class AnomalyState:
    metric: str = ""
    direction: int = 0          # +1 high, -1 low
    magnitude: float = 0.0      # multiplier above redline
    ends_at: float = 0.0


class AssetSim:
    def __init__(self, asset: dict):
        self.asset = asset
        self.t0 = time.time()
        self.anomaly = AnomalyState()

    def step(self) -> Dict[str, float]:
        now = time.time()
        elapsed = now - self.t0
        readings = {}

        # Should we start a new anomaly?
        if not self.anomaly.metric and random.random() < ANOMALY_CHANCE_PER_TICK:
            metric = random.choice(list(self.asset["metrics"].keys()))
            self.anomaly = AnomalyState(
                metric=metric,
                direction=random.choice([-1, 1]),
                magnitude=random.uniform(1.05, 1.25),
                ends_at=now + random.uniform(*ANOMALY_DURATION_SEC),
            )

        if self.anomaly.metric and now > self.anomaly.ends_at:
            self.anomaly = AnomalyState()

        for metric, cfg in self.asset["metrics"].items():
            # Slow sinusoid for realism + gaussian noise
            base = cfg["nominal"]
            slow = math.sin(elapsed / 30 + hash(metric) % 7) * cfg["noise"] * 0.3
            noise = random.gauss(0, cfg["noise"])
            value = base + slow + noise

            # Apply anomaly
            if self.anomaly.metric == metric:
                if self.anomaly.direction > 0:
                    target = cfg["redline_high"] * self.anomaly.magnitude
                else:
                    target = cfg["redline_low"] * (2 - self.anomaly.magnitude)
                # Smooth transition into anomaly value
                value = value * 0.3 + target * 0.7

            readings[metric] = round(value, 3)

        return readings


def topic_for(asset: dict, metric: str) -> str:
    return f"factory/{asset['area']}/{asset['cell']}/{asset['id']}/{metric}"


def status_topic(asset: dict) -> str:
    return f"factory/{asset['area']}/{asset['cell']}/{asset['id']}/status"


def main():
    client = mqtt.Client(client_id="edge-gateway-01", protocol=mqtt.MQTTv5)
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()

    sims = [AssetSim(a) for a in ASSETS]
    print(f"[simulator] publishing {len(sims)} assets at {PUBLISH_HZ} Hz")

    # Birth certificates: announce each asset with metadata
    for sim in sims:
        a = sim.asset
        client.publish(
            status_topic(a),
            json.dumps({
                "event": "online",
                "asset_id": a["id"],
                "name": a["name"],
                "type": a["type"],
                "area": a["area"],
                "cell": a["cell"],
                "x": a["x"], "y": a["y"],
                "metrics": list(a["metrics"].keys()),
            }),
            retain=True,
        )

    period = 1.0 / PUBLISH_HZ
    try:
        while True:
            tick = time.time()
            for sim in sims:
                readings = sim.step()
                for metric, value in readings.items():
                    payload = json.dumps({
                        "ts": int(tick * 1000),
                        "asset_id": sim.asset["id"],
                        "metric": metric,
                        "value": value,
                    })
                    client.publish(topic_for(sim.asset, metric), payload)
            sleep_for = max(0, period - (time.time() - tick))
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        print("\n[simulator] shutting down")
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
