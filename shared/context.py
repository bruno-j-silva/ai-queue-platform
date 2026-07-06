from contextvars import ContextVar

job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)
tenant_id_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)
delivery_id_var: ContextVar[str | None] = ContextVar("delivery_id", default=None)


def set_correlation_ids(
    job_id: str | None = None,
    tenant_id: str | None = None,
    delivery_id: str | None = None,
) -> None:
    if job_id is not None:
        job_id_var.set(job_id)
    if tenant_id is not None:
        tenant_id_var.set(tenant_id)
    if delivery_id is not None:
        delivery_id_var.set(delivery_id)


def get_correlation_ids() -> dict[str, str | None]:
    return {
        "job_id": job_id_var.get(),
        "tenant_id": tenant_id_var.get(),
        "delivery_id": delivery_id_var.get(),
    }
