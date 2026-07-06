# 05 — Roadmap Incremental (TDD)

Cada milestone é um incremento **deployável e demonstrável**. A regra de ouro: o milestone só fecha quando todos os critérios de aceitação das specs associadas têm testes verdes e o Definition of Done está satisfeito.

## Definition of Done (todo milestone)
- Specs associadas com todos os ACs cobertos por testes que referenciam seus IDs.
- Cobertura ≥ 85% nos módulos tocados; lint (ruff) e type-check (mypy) limpos.
- `docker compose up` sobe o incremento funcionando; smoke test e2e verde no CI.
- Docs atualizadas (spec, ADR se houve decisão nova, changelog).

## Milestones

### M0 — Fundação (1 sprint)
Scaffold do monorepo (`api/`, `workers/`, `shared/`), Docker Compose (Postgres, RabbitMQ, MinIO, Redis), migrações (Alembic), CI (pytest + ruff + mypy), esqueleto de métricas.
**Demo:** `compose up` + healthchecks verdes + pipeline CI rodando.

### M1 — Submissão e ciclo de vida (SPEC-001)
`POST /v1/jobs` com validação, auth por API Key, outbox → RabbitMQ, `GET /v1/jobs/{id}`, máquina de estados + job_events.
**Demo:** submeter job, vê-lo `queued` no banco e na fila.

### M2 — Worker + backend Ollama, texto (SPEC-005 parcial)
Worker Celery consome, executa texto no `OllamaBackend` (FakeBackend nos testes), grava resultado, transiciona estados, timeout (RF-021), retry transiente (RF-022), acks_late para crash-recovery (RNF-006).
**Demo:** job de texto fim-a-fim com resultado consultável via GET.

### M3 — Entrega por webhook (SPEC-003)
Cadastro de endpoints, dispatcher com HMAC, retries com backoff, DLQ, redeliver via Admin API.
**Demo:** job termina → callback assinado recebido; derrubar o receptor → retries → DLQ → redeliver.

### M4 — Priorização por plano (SPEC-002)
Filas por prioridade, weighted fair scheduling, anti-starvation testado, snapshot de prioridade no submit.
**Demo:** carga mista free/enterprise → enterprise fura fila, free não morre de fome.

### M5 — Cancelamento (SPEC-004)
Cancel de queued (tombstone) e running (CancelToken + abort), semântica ≤ 10s, 409 em terminal.
**Demo:** cancelar job longo em execução e ver o worker pegar o próximo em segundos.

### M6 — Multimodal + vLLM (SPEC-005 completo, SPEC-006)
`POST /v1/artifacts` + presigned URLs, payloads com imagem/áudio/documento, `VLLMBackend`, validação de capabilities no submit, suíte de contrato de backends.
**Demo:** job de visão no vLLM e job de texto no Ollama, mesmo contrato.

### M7 — Observabilidade e hardening (SPEC-007)
Métricas Prometheus completas, dashboards Grafana (fila por prioridade, latências, webhooks, workers), alertas, logs estruturados correlacionados, idempotency-key (RF-006), TTL/expiração de resultados (RF-044/RNF-007).
**Demo:** dashboard mostrando carga real + alerta de DLQ disparando.

### M8 — Kubernetes (SPEC-008)
Helm chart, deployments com HPA (API) e node pools GPU (workers), operators de RabbitMQ/Postgres ou serviços gerenciados, segredos via secret manager, runbook de operação.
**Demo:** plataforma completa num cluster de staging.

## Pós-MVP (backlog)
Rate limiting e quotas por plano (RF-053/054) · fairness intra-prioridade por tenant · SSE/streaming · KEDA autoscaling por profundidade de fila · console web · roteamento para APIs externas.

## Dependências entre milestones
M0 → M1 → M2 → {M3, M4, M5 em paralelo} → M6 → M7 → M8.
