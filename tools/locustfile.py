"""Interactive closed-loop alternative. Use load.py for arrival-rate evidence."""
import os
import uuid

from locust import HttpUser, constant, task


class PairUser(HttpUser):
    wait_time = constant(0)

    def on_start(self):
        self.client.headers.update({"Authorization": "Bearer " + os.environ["DEMO_API_KEY"]})

    @task
    def pair(self):
        identifier = uuid.uuid4().hex
        text = "Email: synthetic@example.org; PIN: 1234"
        response = self.client.post("/process", json={"payload": text, "payload_id": identifier}, name="mask")
        if response.status_code == 200:
            with self.client.post("/process", json={"payload": response.json()["result"], "payload_id": identifier},
                                  name="restore", catch_response=True) as restored:
                if restored.status_code == 200 and restored.json().get("result") != text:
                    restored.failure("Restoration mismatch")

