# SPEC-003 — Entrega de resultados via webhook

- **Status:** Aprovada
- **Milestone:** M3
- **Requisitos:** RF-040..044, RB-04
- **ADRs:** ADR-006

## História
Como desenvolvedor integrador, quero receber um callback assinado quando meu job terminar, para reagir sem polling e com garantia de autenticidade.

## Escopo
Entra: CRUD de webhook endpoints, dispatcher, HMAC, retries+DLQ, redeliver admin, endpoint de teste. Não entra: mTLS, transformação de payload custom.

## Critérios de aceitação
| ID | Critério |
|---|---|
| AC-01 | QUANDO um job atinge estado terminal, um `webhook_delivery` deve ser criado na mesma transação da transição e publicado pelo relay. |
| AC-02 | A entrega deve conter headers X-Delivery-Id, X-Timestamp, X-Attempt e X-Signature válida (HMAC-SHA256 de `timestamp + "." + body`). |
| AC-03 | QUANDO o endpoint responde 2xx em ≤ 10s, a delivery vira `delivered`. |
| AC-04 | SE responder ≠2xx, exceder 10s ou falhar rede, ENTÃO reagendar com backoff 1m,5m,30m,2h,12h (jitter ±20%). |
| AC-05 | SE a 5ª tentativa falhar, ENTÃO status `dead`, mensagem na `webhooks.dlq`, métrica `webhook_dead_total` incrementada. |
| AC-06 | QUANDO o operador aciona redeliver na DLQ, uma nova tentativa deve ocorrer preservando `delivery_id`. |
| AC-07 | Reentregas devem manter o mesmo `delivery_id` com `attempt` incrementado (dedupe no cliente). |
| AC-08 | GET /v1/jobs/{id} deve continuar servindo o resultado mesmo com webhook em falha (independência). |

## Design notes
- Backoff calculado com Clock injetável; agenda via `next_attempt_at` + poller (evita depender de delayed-exchange plugin no MVP).
- Segredo por endpoint: gerado no create, exibido uma vez, armazenado hasheado + cifrado para uso do signer (KMS/secret manager em prod).

## Plano de testes
| AC | Nível | Teste |
|---|---|---|
| AC-01 | int | test_spec003_ac01_terminal_state_creates_delivery_same_tx |
| AC-02 | unit | test_spec003_ac02_hmac_signature_valid_and_tamper_detected |
| AC-03/04 | int | test_spec003_ac03_2xx_marks_delivered / ac04_retry_backoff_schedule |
| AC-05 | int | test_spec003_ac05_exhausted_goes_to_dlq_with_metric |
| AC-06 | int | test_spec003_ac06_admin_redeliver_from_dlq |
| AC-07 | unit | test_spec003_ac07_delivery_id_stable_attempt_increments |
| AC-08 | e2e | test_spec003_ac08_get_job_independent_of_webhook_failure |
