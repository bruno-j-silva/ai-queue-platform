# SPEC-004 — Cancelamento de jobs

- **Status:** Aprovada
- **Milestone:** M5
- **Requisitos:** RF-030, RF-031, RF-032
- **ADRs:** ADR-005

## História
Como desenvolvedor integrador, quero cancelar jobs desnecessários (na fila ou executando), para não desperdiçar tempo de GPU nem esperar resultados obsoletos.

## Critérios de aceitação
| ID | Critério |
|---|---|
| AC-01 | QUANDO DELETE chega para job `queued`, responder 202; o worker que consumir a mensagem deve descartá-la (tombstone) e o job vira `cancelled` sem executar inferência. |
| AC-02 | QUANDO DELETE chega para job `running`, responder 202; o worker deve detectar o CancelToken e abortar o backend, com transição para `cancelled` em ≤ 10s (medido do DELETE ao evento). |
| AC-03 | SE o job já está em estado terminal, ENTÃO responder 409 com o estado final no body. |
| AC-04 | QUANDO um job é cancelado, NENHUM webhook `job.succeeded/failed` deve ser emitido — apenas `job.cancelled`. |
| AC-05 | Job cancelado deve registrar `job_events` com origem (`api_cancel`) e liberar o worker imediatamente para o próximo job. |
| AC-06 | Cancelamento cross-tenant deve responder 404 (isolamento). |

## Design notes
- Flag em Postgres + cache Redis com TTL curto; worker checa a cada chunk do stream ou a cada ≤ 2s.
- Corrida cancel × término: transição terminal usa compare-and-swap no status; primeiro que gravar vence; DELETE tardio recebe 409.

## Plano de testes
| AC | Nível | Teste |
|---|---|---|
| AC-01 | int | test_spec004_ac01_cancel_queued_tombstone |
| AC-02 | int | test_spec004_ac02_cancel_running_within_10s (FakeBackend com CancelToken) |
| AC-03 | unit | test_spec004_ac03_terminal_conflict_409 |
| AC-04 | int | test_spec004_ac04_only_cancelled_webhook |
| AC-05 | int | test_spec004_ac05_worker_freed_immediately |
| AC-06 | int | test_spec004_ac06_cross_tenant_404 |
| corrida | unit (hypothesis) | test_spec004_race_cancel_vs_completion_single_winner |
