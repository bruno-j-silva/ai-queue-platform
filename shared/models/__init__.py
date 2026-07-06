# Import all models to ensure they are registered in Base.metadata for Alembic autogenerate.
from shared.models.plan import Plan  # noqa: F401
from shared.models.tenant import Tenant  # noqa: F401
from shared.models.api_key import ApiKey  # noqa: F401
from shared.models.model_catalog import ModelCatalog  # noqa: F401
from shared.models.plan_model import PlanModel  # noqa: F401
from shared.models.artifact import Artifact  # noqa: F401
from shared.models.job import Job  # noqa: F401
from shared.models.job_event import JobEvent  # noqa: F401
from shared.models.webhook_endpoint import WebhookEndpoint  # noqa: F401
from shared.models.webhook_delivery import WebhookDelivery  # noqa: F401
from shared.models.outbox import Outbox  # noqa: F401

__all__ = [
    "Plan",
    "Tenant",
    "ApiKey",
    "ModelCatalog",
    "PlanModel",
    "Artifact",
    "Job",
    "JobEvent",
    "WebhookEndpoint",
    "WebhookDelivery",
    "Outbox",
]
