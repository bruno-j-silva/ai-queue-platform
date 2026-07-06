# SPEC-007 — Observabilidade e operação

- **Status:** Aprovada
- **Milestone:** M7
- **Requisitos:** RNF-002, RF-042 (alerta DLQ), RF-044
- **ADRs:** —

## História
Como operador, quero métricas, dashboards e logs correlacionados, para diagnosticar gargalos e falhas antes que virem incidente.

## Critérios de aceitação
| ID | Critério |
|---|---|
| AC-01 | API e workers devem expor /metrics Prometheus com: `jobs_submitted_total{tenant,model}`, `queue_depth{pool,priority}`, `job_wait_seconds` e `job_exec_seconds` (histogramas), `job_failed_total{code}`, `webhook_delivery_total{status}`, `webhook_dead_total`, `worker_busy{pool}`. |
| AC-02 | Dashboards Grafana provisionados como código (JSON no repo): visão de filas, latências p50/95/99, webhooks, workers/GPU. |
| AC-03 | Alertas mínimos: `webhook_dead_total` crescente, `queue_depth p1` acima de limiar por > 15 min, taxa de `job_failed` > 5%. |
| AC-04 | Logs estruturados JSON com `job_id`, `tenant_id`, `delivery_id` propagados API→broker→worker→dispatcher (correlação fim-a-fim de 1 job com uma única query). |
| AC-05 | Job de limpeza deve expirar resultados/artifacts vencidos (status `expired` quando aplicável) com log auditável de quantos itens removeu. |

## Plano de testes
| AC | Nível | Teste |
|---|---|---|
| AC-01 | int | test_spec007_ac01_metrics_exposed_and_incremented |
| AC-02/03 | e2e smoke | provisionamento sobe sem erro; alert rules válidas (promtool) |
| AC-04 | int | test_spec007_ac04_correlation_ids_propagated |
| AC-05 | int | test_spec007_ac05_ttl_cleanup_job |
