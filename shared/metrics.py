"""
Métricas Prometheus da plataforma.
Os incrementos acontecem nas fases M1–M7; aqui apenas a definição.
"""
from prometheus_client import Counter, Gauge, Histogram

# -- Contadores --
jobs_submitted_total = Counter(
    "jobs_submitted_total",
    "Total de jobs submetidos",
    ["tenant", "model"],
)

job_failed_total = Counter(
    "job_failed_total",
    "Total de jobs com falha por código de erro",
    ["code"],
)

webhook_delivery_total = Counter(
    "webhook_delivery_total",
    "Total de tentativas de entrega de webhook",
    ["status"],
)

webhook_dead_total = Counter(
    "webhook_dead_total",
    "Total de webhooks que foram para a DLQ",
)

# -- Histogramas --
job_wait_seconds = Histogram(
    "job_wait_seconds",
    "Tempo de espera do job na fila (segundos)",
    buckets=[1, 5, 15, 30, 60, 120, 300, 600, 1800],
)

job_exec_seconds = Histogram(
    "job_exec_seconds",
    "Tempo de execução do job (segundos)",
    buckets=[1, 5, 15, 30, 60, 120, 300, 600, 1800],
)

# -- Gauges --
queue_depth = Gauge(
    "queue_depth",
    "Profundidade da fila por pool e prioridade",
    ["pool", "priority"],
)

worker_busy = Gauge(
    "worker_busy",
    "Workers ocupados por pool",
    ["pool"],
)
