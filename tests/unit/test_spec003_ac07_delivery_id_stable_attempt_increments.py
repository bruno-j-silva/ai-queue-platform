"""SPEC-003/AC-07: delivery identity is stable across attempts."""

from shared.webhooks.delivery import build_webhook_payload


def test_spec003_ac07_delivery_id_stable_attempt_increments() -> None:
    job = {"job_id": "job-1", "status": "succeeded"}

    first = build_webhook_payload("delivery-1", "job.succeeded", 1, job)
    second = build_webhook_payload("delivery-1", "job.succeeded", 2, job)

    assert first["delivery_id"] == second["delivery_id"] == "delivery-1"
    assert first["attempt"] == 1
    assert second["attempt"] == 2
    assert first["job"] == second["job"] == job
