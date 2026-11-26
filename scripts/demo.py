"""Real API + Temporal demo. Requires running API and worker, no model credentials."""

import json
import time
import uuid
from pathlib import Path

import httpx
from agentgenome.config import Settings


def main() -> None:
    settings = Settings()
    if settings.profile != "dev" or not settings.dev_auth:
        raise RuntimeError("This demo requires explicit development identity")
    with httpx.Client(
        base_url="http://127.0.0.1:8080/api/v1",
        timeout=10,
        headers={"Authorization": "Bearer " + settings.dev_token.get_secret_value()},
    ) as client:

        def post(path, body=None, **kwargs):
            result = client.post(path, json=body, **kwargs)
            result.raise_for_status()
            return result.json()

        manifest = json.loads(Path("examples/genomes/procurement.json").read_text())
        agent = post("/agents", {"name": "Demo " + uuid.uuid4().hex[:8]})
        genome = post(f"/agents/{agent['id']}/genomes", manifest)
        post(f"/genomes/{genome['id']}/publish")
        run = post(
            "/runs",
            {"genome_id": genome["id"], "task": "Submit approved simulated order"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        deadline = time.monotonic() + 90
        approved = False
        while time.monotonic() < deadline:
            result = client.get(f"/runs/{run['id']}")
            result.raise_for_status()
            current = result.json()
            if current["state"] == "WAITING_APPROVAL" and not approved:
                pending = client.get("/approvals")
                pending.raise_for_status()
                approval = next(a for a in pending.json()["items"] if a["run_id"] == run["id"])
                post(f"/approvals/{approval['id']}/approve")
                approved = True
            if current["state"] == "SUCCEEDED":
                assert approved and current["result"]["simulated"]
                events = client.get(f"/runs/{run['id']}/events")
                events.raise_for_status()
                assert "run.succeeded" in events.text
                print(
                    json.dumps(
                        {
                            "run_id": run["id"],
                            "state": current["state"],
                            "result": current["result"],
                        }
                    )
                )
                return
            if current["state"] in {"FAILED", "CANCELLED", "TIMED_OUT", "BUDGET_EXHAUSTED"}:
                raise RuntimeError(str(current))
            time.sleep(0.5)
        raise TimeoutError("Real worker did not complete the run before demo deadline")


if __name__ == "__main__":
    main()
