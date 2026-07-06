# 02 — Arquitetura

## Visão de contexto (C4 nível 1)

```
[Cliente do Tenant] --HTTPS--> [AI Queue Platform] --webhook HTTPS--> [Endpoint do Tenant]
                                      |
                              [GPUs / Ollama / vLLM]
```

## Componentes (C4 nível 2)

```
                    ┌────────────────────────────────────────────────┐
                    │                 AI Queue Platform              │
                    │                                                │
 Tenant ──HTTPS──▶  │  ┌──────────┐   publish   ┌──────────────┐    │
                    │  │ API      │ ───────────▶ │  RabbitMQ    │    │
                    │  │ (FastAPI)│              │  (quorum)    │    │
                    │  └────┬─────┘              └──────┬───────┘    │
                    │       │ write                     │ consume    │
                    │  ┌────▼─────┐              ┌──────▼───────┐    │
                    │  │PostgreSQL│◀── status ── │ Inference    │    │
                    │  │          │              │ Workers      │──┐ │
                    │  └────┬─────┘              │ (Celery)     │  │ │
                    │       │                    └──────┬───────┘  │ │
                    │  ┌────▼─────┐   consume    ┌──────▼───────┐  │ │
                    │  │ MinIO    │              │ Webhook      │  │ │
                    │  │(artifacts│              │ Dispatcher   │──┼─┼──▶ Tenant endpoint
                    │  │/results) │              │ (Celery)     │  │ │
                    │  └──────────┘              └──────────────┘  │ │
                    │                                              │ │
                    │  Prometheus ◀── /metrics ── todos ───────────┘ │
                    └────────────────────────────────────────────────┘
                                                       │
                                          ┌────────────▼────────────┐
                                          │ Inference Backends      │
                                          │  - OllamaBackend (HTTP) │
                                          │  - VLLMBackend (OpenAI- │
                                          │    compatible HTTP)     │
                                          └─────────────────────────┘
```

### 1. API Service (FastAPI)
- Autenticação por API Key (hash lookup + cache), validação de payload (Pydantic), criação do job em Postgres + publish no RabbitMQ (padrão **transactional outbox** para não perder jobs entre DB e broker).
- Endpoints de status, listagem, cancelamento, upload de artifacts (presigned URL do MinIO), gestão de webhooks.
- Admin API (operador): tenants, planos, catálogo de modelos, reprocesso de DLQ.

### 2. RabbitMQ — topologia de filas
- **Uma fila por classe de prioridade por pool de capacidade**: ex. `inference.gpu-a.p10`, `inference.gpu-a.p5`, `inference.gpu-a.p1`.
- Workers consomem com **pesos** (weighted fair scheduling) para garantir anti-starvation (RF-011) — ver ADR-002.
- Quorum queues + publisher confirms + manual ack. `x-delivery-limit` + DLX para jobs venenosos.
- Fila dedicada `webhooks.delivery` + `webhooks.dlq`.

### 3. Inference Workers (Celery)
- Prefetch=1 (jobs longos), ack tardio (`acks_late=True`) para redelivery em crash (RNF-006).
- Resolve o backend via `InferenceBackend` (Strategy): `generate(job) -> Result`, `abort(job_id)`, `health()`.
- Baixa artifacts do MinIO, monta o prompt multimodal no formato do backend, aplica timeout (RF-021), checa flag de cancelamento cooperativamente (Redis/Postgres advisory — ver ADR-005).
- Ao terminar: grava resultado (MinIO se grande, Postgres se pequeno), transiciona estado, enfileira entrega de webhook.

### 4. Webhook Dispatcher (Celery)
- Consome `webhooks.delivery`, assina payload com HMAC-SHA256 (segredo por endpoint), POST com timeout de 10s.
- Retry com backoff exponencial + jitter via reenfileiramento com delay (delayed exchange ou TTL+DLX). Esgotadas as tentativas → `webhooks.dlq` + alerta.

### 5. PostgreSQL
- Fonte da verdade de tenants, planos, jobs, eventos, entregas. Ver `03-data-model.md`.

### 6. MinIO
- Buckets por tenant-prefix para artifacts de entrada e resultados grandes; presigned URLs; criptografia em repouso (RNF-005); lifecycle rules para TTL (RNF-007).

## Fluxo principal (submissão → entrega)

1. `POST /v1/jobs` → valida → grava `jobs` + `outbox` na mesma transação → 202 com `job_id`.
2. Relay do outbox publica na fila de prioridade correta.
3. Worker consome, transiciona `queued→running`, executa no backend com timeout e checagem de cancelamento.
4. Resultado persistido; transição para estado terminal; evento de webhook enfileirado.
5. Dispatcher entrega o webhook assinado; retries se necessário; DLQ se esgotar.
6. Tenant pode consultar `GET /v1/jobs/{id}` a qualquer momento (TTL 7 dias).

## Fluxo de cancelamento

- `DELETE /v1/jobs/{id}`:
  - `queued`: marca `cancel_requested`; worker descarta ao consumir (tombstone check) → `cancelled`.
  - `running`: seta flag de cancelamento; worker checa a cada iteração/chunk e chama `backend.abort()` → `cancelled` em ≤ 10s.
  - terminal: `409`.

## Decisões registradas (ADRs)

| ADR | Decisão |
|---|---|
| ADR-001 | RabbitMQ como broker (vs Redis/Kafka) |
| ADR-002 | Priorização por filas separadas + consumo ponderado (vs priority queues nativas) |
| ADR-003 | Interface `InferenceBackend` plugável (Strategy + registry) |
| ADR-004 | Artifacts multimodais em MinIO com presigned URLs |
| ADR-005 | Cancelamento cooperativo com flag centralizada |
| ADR-006 | Webhook at-least-once com HMAC + outbox transacional |

## Evolução Compose → Kubernetes

- **Dev/teste:** Docker Compose com todos os serviços + Ollama CPU para testes funcionais.
- **Produção:** Helm chart; API como Deployment + HPA; workers como Deployments por pool de GPU (nodeSelector/taints para nós GPU); RabbitMQ e Postgres via operators; KEDA para autoscaling de workers por profundidade de fila (pós-MVP).
