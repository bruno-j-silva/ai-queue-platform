"""Smoke test for the real API -> outbox -> RabbitMQ -> Celery pipeline."""

import asyncio
import hashlib
import os
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.models.api_key import ApiKey, ApiKeyStatus
from shared.models.model_catalog import ModelBackend, ModelCatalog, ModelStatus
from shared.models.plan import Plan
from shared.models.plan_model import PlanModel
from shared.models.tenant import Tenant, TenantStatus

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_E2E") != "1",
    reason="set RUN_E2E=1 after starting the full Compose stack",
)


@pytest.mark.asyncio
async def test_submit_is_processed_and_result_is_retrievable() -> None:
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://enfila:enfila@localhost:5432/enfila",
    )
    api_url = os.environ.get("API_URL", "http://localhost:8000")
    raw_key = f"e2e-{uuid.uuid4()}"
    tenant_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    model_id = f"e2e-model-{uuid.uuid4()}"
    now = datetime.now(UTC)

    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        session.add_all(
            [
                Plan(
                    id=plan_id,
                    name=f"e2e-{plan_id}",
                    priority_weight=10,
                    max_timeout_seconds=60,
                    result_ttl_days=1,
                    max_payload_mb=1,
                ),
                ModelCatalog(
                    id=model_id,
                    backend=ModelBackend.ollama,
                    backend_model_name="fake-e2e",
                    status=ModelStatus.active,
                ),
            ]
        )
        await session.flush()
        session.add(
            Tenant(
                id=tenant_id,
                name="E2E Tenant",
                plan_id=plan_id,
                status=TenantStatus.active,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(PlanModel(plan_id=plan_id, model_id=model_id))
        session.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
                prefix=raw_key[:8],
                status=ApiKeyStatus.active,
            )
        )

    headers = {"Authorization": f"Bearer {raw_key}", "Idempotency-Key": str(uuid.uuid4())}
    async with httpx.AsyncClient(base_url=api_url, timeout=10) as client:
        endpoint_response = await client.post(
            "/v1/webhook-endpoints",
            headers=headers,
            json={"url": "https://host.docker.internal:1/callback"},
        )
        assert endpoint_response.status_code == 201, endpoint_response.text
        endpoint_id = endpoint_response.json()["id"]

        response = await client.post(
            "/v1/jobs",
            headers=headers,
            json={
                "model": model_id,
                "input": {"messages": [{"role": "user", "content": "smoke"}]},
                "timeout_seconds": 30,
                "webhook_endpoint_id": endpoint_id,
            },
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]

        for _ in range(40):
            result = await client.get(f"/v1/jobs/{job_id}", headers=headers)
            assert result.status_code == 200, result.text
            if result.json()["status"] == "succeeded":
                break
            await asyncio.sleep(0.25)
        else:
            pytest.fail(f"job did not succeed: {result.text}")

    body = result.json()
    assert body["result"]["output"][0]["text"] == "fake response"
    assert body["usage"]["backend"] == "fake"

    admin_headers = {"X-Admin-Token": os.environ.get("ADMIN_API_TOKEN", "test-admin-token")}
    async with httpx.AsyncClient(base_url=api_url, timeout=10) as client:
        for _ in range(80):
            dead_response = await client.get(
                "/admin/v1/dlq/webhooks",
                headers=admin_headers,
            )
            assert dead_response.status_code == 200, dead_response.text
            dead = dead_response.json()
            if dead:
                break
            await asyncio.sleep(0.25)
        else:
            pytest.fail("webhook delivery did not reach DLQ")

        delivery_id = dead[0]["delivery_id"]
        assert dead[0]["attempt"] == 5

        still_available = await client.get(f"/v1/jobs/{job_id}", headers=headers)
        assert still_available.status_code == 200
        assert still_available.json()["status"] == "succeeded"
        assert still_available.json()["result"] == body["result"]

        redelivered = await client.post(
            f"/admin/v1/dlq/webhooks/{delivery_id}/redeliver",
            headers=admin_headers,
        )
        assert redelivered.status_code == 202, redelivered.text
        assert redelivered.json() == {
            "delivery_id": delivery_id,
            "expected_attempt": 6,
        }

        for _ in range(40):
            retried = await client.get("/admin/v1/dlq/webhooks", headers=admin_headers)
            matching = [item for item in retried.json() if item["delivery_id"] == delivery_id]
            if matching and matching[0]["attempt"] == 6:
                break
            await asyncio.sleep(0.25)
        else:
            pytest.fail("admin redelivery did not execute attempt 6")
    await engine.dispose()
