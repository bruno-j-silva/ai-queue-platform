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
        response = await client.post(
            "/v1/jobs",
            headers=headers,
            json={
                "model": model_id,
                "input": {"messages": [{"role": "user", "content": "smoke"}]},
                "timeout_seconds": 30,
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
    await engine.dispose()
