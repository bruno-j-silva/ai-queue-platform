# SPEC-001 — Submissão e ciclo de vida de jobs

- **Status:** Aprovada
- **Milestone:** M1
- **Requisitos:** RF-001..006, RF-050, RF-051, RNF-001
- **ADRs:** ADR-001, ADR-006 (outbox)

## História
Como desenvolvedor integrador, quero submeter um job de IA e receber um `job_id` imediatamente, para processar de forma assíncrona sem manter conexão aberta.

## Escopo
Entra: POST /v1/jobs, GET /v1/jobs/{id}, GET /v1/jobs, auth por API Key, máquina de estados + job_events, outbox→RabbitMQ, idempotency-key. Não entra: execução (SPEC-005), webhook (SPEC-003), prioridade real (SPEC-002 — aqui grava-se apenas o snapshot do peso).

## Critérios de aceitação
| ID | Critério |
|---|---|
| AC-01 | QUANDO um tenant autenticado envia payload válido, o sistema deve responder 202 com `job_id` e persistir o job em `queued` com evento em `job_events`, em < 500ms p95. |
| AC-02 | QUANDO o job é persistido, uma linha de `outbox` deve existir na MESMA transação; o relay deve publicá-la na fila correta em ≤ 2s. |
| AC-03 | SE o modelo não existir, não estiver no plano do tenant, ou o payload violar o schema, ENTÃO responder 422 com problem+json sem persistir job. |
| AC-04 | SE a API Key for inválida/revogada, ENTÃO responder 401 sem vazar se o tenant existe. |
| AC-05 | QUANDO `Idempotency-Key` repetida chega do mesmo tenant, retornar o job original (200) sem duplicar. |
| AC-06 | QUANDO tenant A consulta job do tenant B, responder 404. |
| AC-07 | QUANDO `timeout_seconds` excede o teto do plano, responder 422 indicando o teto. |
| AC-08 | GET /v1/jobs/{id} de job `queued` deve incluir `queue_position` estimada. |

## Design notes
- Máquina de estados como módulo puro (`transition(job, event) -> job | error`) — 100% unit-testável.
- Outbox relay: processo/task que faz poll `WHERE published_at IS NULL` com `FOR UPDATE SKIP LOCKED`.
- API Key: lookup por hash com cache Redis de 60s.

## Plano de testes
| AC | Nível | Teste |
|---|---|---|
| AC-01 | int | test_spec001_ac01_valid_submit_returns_202_and_persists |
| AC-02 | int | test_spec001_ac02_outbox_same_tx_and_relay_publishes |
| AC-03 | unit+int | test_spec001_ac03_invalid_model_422 / schema_422 |
| AC-04 | int | test_spec001_ac04_invalid_key_401 |
| AC-05 | int | test_spec001_ac05_idempotency_returns_original |
| AC-06 | int | test_spec001_ac06_cross_tenant_404 |
| AC-07 | unit | test_spec001_ac07_timeout_above_plan_cap_422 |
| AC-08 | int | test_spec001_ac08_queue_position_estimate |
| I1 | unit (hypothesis) | test_state_machine_rejects_invalid_transitions |
