# 00 — Plano de Execução por Fases (MVP)

> Camada de execução do `ai-queue-platform`. Traduz o [roadmap](../05-roadmap.md) e as [specs](../specs/) em fases acionáveis com atividades, dependências e gates.
> Acompanhamento vivo: [`PROGRESS.md`](./PROGRESS.md) (dashboard) + [`checks/M0..M8`](./checks/) (rastreabilidade de ACs).

## Objetivo do MVP

Entregar uma plataforma de **inferência de IA assíncrona multi-tenant**: o tenant submete um job via API, recebe `job_id` imediatamente, a plataforma enfileira com priorização por plano, executa em workers com backends plugáveis (Ollama/vLLM) e entrega o resultado via webhook assinado com retry/DLQ. Escopo e não-objetivos em [`00-vision.md`](../00-vision.md).

### Métricas de sucesso (gate do MVP — de `00-vision.md`)
- 95% dos jobs premium iniciam processamento em < 30s sob carga nominal.
- ≥ 99% dos webhooks entregues em até 3 tentativas.
- Zero jobs perdidos (todo job termina em estado terminal — nunca desaparece).
- Throughput de milhares de jobs/dia com headroom de 10x.

## Disciplina de trabalho (toda fase)

Fluxo **spec-driven + TDD** (de [`README`](../../README.md) e [`06-testing-strategy.md`](../06-testing-strategy.md)):

1. **Spec primeiro** — ler a `SPEC-NNN` da fase; nenhum código sem AC aprovado.
2. **Red** — escrever os testes derivados de cada AC (nomes já definidos no "Plano de testes" da spec), todos falhando pelo motivo certo.
3. **Green** — implementar o mínimo para passar.
4. **Refactor** — melhorar o design mantendo a suíte verde.
5. **Rastreabilidade** — cada teste referencia o ID do AC (`# SPEC-NNN/AC-xx`); atualizar o check da fase (Red→Green).
6. **Gate DoD** — só fecha a fase com o Definition of Done satisfeito (abaixo).

### Definition of Done (todo milestone — de `05-roadmap.md`)
- [ ] Todos os ACs da(s) spec(s) cobertos por testes que referenciam seus IDs.
- [ ] Cobertura ≥ 85% nos módulos tocados; `ruff` e `mypy` limpos.
- [ ] `docker compose up` sobe o incremento funcionando; smoke test e2e verde no CI.
- [ ] Docs atualizadas (spec, ADR se houve decisão nova, changelog).

## Mapa de fases (roadmap → specs → ACs)

| Fase | Milestone | Spec(s) | ACs | Dependências | Check |
|---|---|---|---|---|---|
| **F0** | M0 — Fundação | infra (sem spec) | DoD de infra | — | [M0](./checks/M0.md) |
| **F1** | M1 — Submissão e ciclo de vida | [SPEC-001](../specs/SPEC-001-job-submission.md) | AC-01..08 + I1 | M0 | [M1](./checks/M1.md) |
| **F2** | M2 — Worker + Ollama (texto) | [SPEC-005](../specs/SPEC-005-inference-backends.md) (parcial) | AC-01..06 | M1 | [M2](./checks/M2.md) |
| **F3** | M3 — Webhook delivery | [SPEC-003](../specs/SPEC-003-webhook-delivery.md) | AC-01..08 | M2 | [M3](./checks/M3.md) |
| **F4** | M4 — Priorização por plano | [SPEC-002](../specs/SPEC-002-priority-scheduling.md) | AC-01..05 | M2 ∥ M3/M5 | [M4](./checks/M4.md) |
| **F5** | M5 — Cancelamento | [SPEC-004](../specs/SPEC-004-cancellation.md) | AC-01..06 + corrida | M2 ∥ M3/M4 | [M5](./checks/M5.md) |
| **F6** | M6 — Multimodal + vLLM | [SPEC-005](../specs/SPEC-005-inference-backends.md) + [SPEC-006](../specs/SPEC-006-multimodal-artifacts.md) | 005/AC-07 + 006/AC-01..07 | M3, M4, M5 | [M6](./checks/M6.md) |
| **F7** | M7 — Observabilidade + hardening | [SPEC-007](../specs/SPEC-007-observability.md) | AC-01..05 (+RF-006, RF-044) | M6 | [M7](./checks/M7.md) |
| **F8** | M8 — Kubernetes | [SPEC-008](../specs/SPEC-008-kubernetes-deploy.md) | AC-01..05 | M7 | [M8](./checks/M8.md) |

**Grafo de dependências:** `M0 → M1 → M2 → {M3, M4, M5 em paralelo} → M6 → M7 → M8`

```
M0 ─▶ M1 ─▶ M2 ─┬─▶ M3 ─┐
                ├─▶ M4 ─┼─▶ M6 ─▶ M7 ─▶ M8
                └─▶ M5 ─┘
```

**MVP = M0–M7.** M8 (Kubernetes) é produção; SPEC-008 ainda em *Draft* (refinar em M7).

---

## Detalhamento das atividades por fase

Cada fase abaixo lista as atividades de implementação em ordem TDD. O rastreio granular (Red/Green por AC, DoD, demo) vive no arquivo de check correspondente.

### F0 — M0 — Fundação
*Objetivo:* base reproduzível para todas as fases seguintes. Sem spec; guiado por RNF-003/004 e arquitetura.
- Scaffold do monorepo: `api/` (FastAPI), `workers/` (Celery), `shared/` (domínio, modelos, tipos), `tests/` (`unit/`, `integration/`, `e2e/`, `contract/backends/`, `conftest.py`).
- `docker-compose.yml`: Postgres 16, RabbitMQ (quorum), MinIO, Redis, (Ollama CPU para testes funcionais).
- Migrações **Alembic** com o esqueleto do [modelo de dados](../03-data-model.md) (tabelas base; detalhamento por fase).
- CI (GitHub Actions): `pytest` + `ruff` + `mypy`, alvo < 10 min; job de e2e no merge; slot para contrato noturno.
- Skeleton de observabilidade: endpoint `/metrics` (Prometheus) vazio em API e worker; logging JSON estruturado base.
- Protocolos/portas de domínio: `Clock` injetável, `InferenceBackend` (Protocol), `FakeBackend` inicial.
- *Demo:* `compose up` + healthchecks verdes + pipeline CI rodando.

### F1 — M1 — Submissão e ciclo de vida — [SPEC-001](../specs/SPEC-001-job-submission.md)
*Cobre:* RF-001..006, RF-050/051, RNF-001. *ADRs:* ADR-001, ADR-006 (outbox).
- **Máquina de estados pura** `transition(job, event) -> job | error` (100% unit; invariante **I1**).
- Auth por API Key: lookup por hash + cache Redis 60s (RF-050); isolamento por tenant (RF-051, invariante **I5**).
- `POST /v1/jobs`: validação Pydantic, catálogo/plano (modelo permitido), teto de timeout do plano; persistência `jobs` + `outbox` na **mesma transação** (invariante **I4**, ADR-006).
- **Outbox relay**: poll `WHERE published_at IS NULL` com `FOR UPDATE SKIP LOCKED` → publish RabbitMQ.
- `GET /v1/jobs/{id}` (com `queue_position` estimada) e `GET /v1/jobs` (filtros/cursor).
- Idempotency-Key (RF-006): unique `(tenant_id, idempotency_key)`, retorno do job original.
- Erros problem+json (RFC 9457): 401/422/413 conforme contrato.
- *Demo:* submeter job → vê-lo `queued` no banco e na fila.

### F2 — M2 — Worker + backend Ollama (texto) — [SPEC-005](../specs/SPEC-005-inference-backends.md) (parcial)
*Cobre:* RF-020..023, RNF-006. *ADRs:* ADR-003, ADR-005.
- Worker Celery: prefetch=1, `acks_late=True` (crash-recovery, RNF-006 / AC-06).
- Registry de backend por catálogo (`model_id → backend`) via Protocol — **sem** `if backend == ...` fora do registry (AC-01).
- `OllamaBackend` (`/api/chat`, stream para checagem de cancelamento por chunk); `FakeBackend` no core dos testes.
- Timeout com `Clock` injetável → abort + `failed(code=timeout)` + libera slot (RF-021 / AC-02).
- Classificador de erros: retry transiente com backoff 1s/4s/16s até 3 (RF-022 / AC-03); erro permanente → `failed` imediato (AC-04).
- Registro de `usage` (tokens in/out, duration_ms, backend, attempt) (RF-023 / AC-05).
- Transições `queued→running→succeeded|failed` com `job_events`.
- *Demo:* job de texto fim-a-fim, resultado consultável via GET.

### F3 — M3 — Entrega por webhook — [SPEC-003](../specs/SPEC-003-webhook-delivery.md)
*Cobre:* RF-040..044, RB-04. *ADRs:* ADR-006.
- CRUD `webhook_endpoints`; segredo gerado no create, exibido uma vez, hasheado/cifrado.
- Criação de `webhook_delivery` na **mesma transação** da transição terminal + publish pelo relay (AC-01).
- Dispatcher Celery: assinatura HMAC-SHA256 (`timestamp + "." + body`), headers `X-Delivery-Id/Timestamp/Attempt/Signature` (AC-02); POST timeout 10s → `delivered` em 2xx (AC-03).
- Retry com backoff 1m/5m/30m/2h/12h + jitter ±20% via `next_attempt_at` + poller (Clock injetável) (AC-04).
- Esgotamento → `dead` + `webhooks.dlq` + métrica `webhook_dead_total` (AC-05).
- Redeliver admin preservando `delivery_id`, `attempt` incrementado (AC-06/07).
- Independência: `GET /v1/jobs/{id}` serve resultado mesmo com webhook falho (AC-08).
- *Demo:* job termina → callback assinado; derrubar receptor → retries → DLQ → redeliver.

### F4 — M4 — Priorização por plano — [SPEC-002](../specs/SPEC-002-priority-scheduling.md)
*Cobre:* RF-010..012, RB-01. *ADRs:* ADR-002. *(paralelo a M3/M5)*
- Roteamento no publish: `inference.<pool>.p<peso>` por pool do modelo + peso do plano (snapshot) (AC-01/05).
- **Scheduler puro** `pick_queue(depths, weights, history) -> queue` — testável por propriedade (hypothesis).
- Weighted fair scheduling nos workers: pesos 10/5/1, tolerância ±10% em janelas de 100 slots (AC-02).
- Work-conserving: prioridade única → consumo a 100% sem slots ociosos (AC-03).
- Anti-starvation: p1 inicia em ≤ T_starvation (default 15 min; testes com clock reduzido) (RF-011 / AC-04).
- Métricas de profundidade por prioridade (`queue_depth{pool,priority}`).
- *Demo:* carga mista free/enterprise → enterprise fura fila, free não morre de fome.

### F5 — M5 — Cancelamento — [SPEC-004](../specs/SPEC-004-cancellation.md)
*Cobre:* RF-030..032. *ADRs:* ADR-005. *(paralelo a M3/M4)*
- `DELETE /v1/jobs/{id}`: `queued` → tombstone, worker descarta → `cancelled` (AC-01); `running` → CancelToken + `backend.abort()` ≤ 10s (AC-02).
- Flag em Postgres + cache Redis TTL curto; worker checa a cada chunk / ≤ 2s.
- Corrida cancel × término: compare-and-swap no status, primeiro que grava vence; DELETE tardio → 409 (AC-03 + teste de corrida).
- Sem webhook `succeeded/failed` em job cancelado — só `job.cancelled` (AC-04).
- `job_events` com origem `api_cancel`; worker liberado imediatamente (AC-05); cross-tenant → 404 (AC-06).
- *Demo:* cancelar job longo em execução e ver o worker pegar o próximo em segundos.

### F6 — M6 — Multimodal + vLLM — [SPEC-005](../specs/SPEC-005-inference-backends.md) (completo) + [SPEC-006](../specs/SPEC-006-multimodal-artifacts.md)
*Cobre:* RF-004/005, RB-03, RNF-005/007. *ADRs:* ADR-004.
- `POST /v1/artifacts` → presigned URL (15 min), restrita a media_type/size (AC-01); cliente faz `PUT` direto no MinIO.
- Validação no submit: existência, posse pelo tenant, compatibilidade com `capabilities` do modelo → 422 / `capability_not_supported` (AC-02/03).
- Worker baixa artifacts e monta request por backend (base64 no Ollama, image_url no vLLM) (AC-04).
- Resultados > 256 KB → artifact `output` no MinIO com URL presigned (AC-05).
- Expiração por TTL do plano → 410 após vencer (AC-06); inline base64 > 1 MB → 413 (AC-07).
- `VLLMBackend` (OpenAI-compatible `/v1/chat/completions`, stream) + **suíte de contrato** parametrizada (SPEC-005/AC-07): Fake sempre no CI, live noturno.
- *Demo:* job de visão no vLLM e job de texto no Ollama, mesmo contrato.

### F7 — M7 — Observabilidade e hardening — [SPEC-007](../specs/SPEC-007-observability.md)
*Cobre:* RNF-002, RF-042 (alerta DLQ), RF-044, RF-006, RNF-007.
- Métricas Prometheus completas em API/workers (AC-01): `jobs_submitted_total`, `queue_depth`, `job_wait_seconds`, `job_exec_seconds`, `job_failed_total`, `webhook_delivery_total`, `webhook_dead_total`, `worker_busy`.
- Dashboards Grafana como código (JSON no repo): filas, latências p50/95/99, webhooks, workers/GPU (AC-02).
- Alertas: DLQ crescente, `queue_depth p1` > limiar por >15 min, `job_failed` > 5% (AC-03) — validar com `promtool`.
- Logs JSON correlacionados `job_id`/`tenant_id`/`delivery_id` API→broker→worker→dispatcher (AC-04).
- Job de limpeza de TTL: expira resultados/artifacts, status `expired`, log auditável (RF-044/RNF-007 / AC-05).
- Fecho de MVP: revisar métricas de sucesso do `00-vision.md`.
- *Demo:* dashboard com carga real + alerta de DLQ disparando.

### F8 — M8 — Kubernetes — [SPEC-008](../specs/SPEC-008-kubernetes-deploy.md) *(Draft — refinar em M7)*
*Cobre:* RNF-003/004/005.
- Helm chart único: API, workers (por pool), dispatcher, relay do outbox; RabbitMQ/Postgres via operator ou serviço gerenciado (AC-01).
- API com HPA (CPU/RPS); workers com nodeSelector/tolerations para nós GPU (AC-02).
- Segredos via Secret externo (ESO/Vault), nunca em values (AC-03).
- Rolling update sem perda: preStop drena consumo, termina job atual dentro do grace period ≥ timeout máx do pool (AC-04).
- Smoke e2e contra cluster de staging no pipeline de release (AC-05); runbook de operação.
- *Demo:* plataforma completa num cluster de staging.

---

## Riscos e questões em aberto

| ID | Questão | Dono | Fase de resolução |
|---|---|---|---|
| Q-01 | Nome definitivo do produto | Bruno | Qualquer (não bloqueia código) |
| Q-02 | Modelos iniciais do catálogo (LLMs em Ollama/vLLM) | Bruno | Até M2 (catálogo mínimo) / M6 (multimodal) |
| Q-03 | Áudio: Whisper como backend próprio ou modelo multimodal? | Bruno | Até M6 |
| Q-04 | Retenção de mídia de entrada (LGPD/PII) | Bruno | Até M6/M7 (TTL/limpeza) |
| Q-K1 | KEDA (autoscaling por fila) em M8 ou pós-MVP? | Operação | M8 (proposta: pós-MVP) |
| Q-K2 | Cluster alvo (on-prem Callink ou cloud): storage class + GPU pools | Operação | M8 |

## Pós-MVP (backlog — de `05-roadmap.md`)
Rate limiting e quotas por plano (RF-053/054) · fairness intra-prioridade por tenant · SSE/streaming · KEDA autoscaling · console web self-service · roteamento para APIs externas (Claude/OpenAI).

## Referências
- Visão/escopo: [`00-vision.md`](../00-vision.md) · Requisitos: [`01-requirements.md`](../01-requirements.md)
- Arquitetura: [`02-architecture.md`](../02-architecture.md) · Dados: [`03-data-model.md`](../03-data-model.md) · API: [`04-api-spec.md`](../04-api-spec.md)
- Roadmap: [`05-roadmap.md`](../05-roadmap.md) · Testes: [`06-testing-strategy.md`](../06-testing-strategy.md)
- ADRs: [`adr/`](../adr/) · Specs: [`specs/`](../specs/)
