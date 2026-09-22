"""Print synthetic demo inputs/results only. Credentials are never printed."""
import argparse
import os
import uuid

import httpx
from dotenv import load_dotenv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--chat", action="store_true")
    args = parser.parse_args()
    load_dotenv(args.env_file)
    key = os.environ["DEMO_API_KEY"]
    text = "Клиент: Иванов Иван Иванович; Email: demo@example.org; PIN: 1234; карта: 4111 1111 1111 1111"
    with httpx.Client(base_url=args.url, headers={"Authorization": "Bearer " + key}, timeout=40) as client:
        identifier = uuid.uuid4().hex
        first = client.post("/process", json={"payload": text, "payload_id": identifier})
        first.raise_for_status()
        masked = first.json()["result"]
        second = client.post("/process", json={"payload": masked, "payload_id": identifier})
        second.raise_for_status()
        assert second.json()["result"] == text
        print("SYNTHETIC INPUT:", text)
        print("MASK:", masked)
        print("EXACT ROUNDTRIP: PASS")
        if args.chat:
            reply = client.post("/v1/chat", json={"request_id": uuid.uuid4().hex, "message": text})
            reply.raise_for_status()
            print("LLM ANSWER:", reply.json()["answer"])
        metrics = client.get("/metrics")
        metrics.raise_for_status()
        print("METRICS: available")


if __name__ == "__main__":
    main()

