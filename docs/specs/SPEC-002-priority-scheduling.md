# SPEC-002 — Priorização por plano com anti-starvation

- **Status:** Aprovada
- **Milestone:** M4
- **Requisitos:** RF-010, RF-011, RF-012, RB-01
- **ADRs:** ADR-002

## História
Como operador, quero que jobs de planos superiores tenham precedência sem matar de fome os planos inferiores, para cumprir SLAs diferenciados de forma justa.

## Escopo
Entra: filas por prioridade por pool, weighted fair scheduling nos workers, roteamento no publish, métricas de profundidade por prioridade. Não entra: fairness intra-prioridade por tenant (pós-MVP), quotas.

## Critérios de aceitação
| ID | Critério |
|---|---|
| AC-01 | QUANDO um job é publicado, deve ir para a fila `inference.<pool>.p<peso>` correspondente ao pool do modelo e ao peso do plano (snapshot). |
| AC-02 | ENQUANTO houver jobs em múltiplas prioridades, a seleção de fila do worker deve seguir os pesos 10/5/1 (tolerância ±10% em janelas de 100 slots). |
| AC-03 | SE só houver jobs de uma prioridade, o worker deve consumi-la a 100% (work-conserving, sem slots ociosos). |
| AC-04 | Sob carga contínua de p10, um job p1 deve iniciar em ≤ T_starvation (default 15 min; nos testes, T reduzido com clock injetável). |
| AC-05 | QUANDO o plano do tenant muda, jobs já enfileirados mantêm o peso do submit; novos jobs usam o novo peso. |

## Design notes
- Scheduler como função pura `pick_queue(depths, weights, history) -> queue` — testável por propriedade.
- Consumo: worker faz `basic_get` ponderado ou mantém consumers com prefetch=1 e gate local ponderado.

## Plano de testes
| AC | Nível | Teste |
|---|---|---|
| AC-01 | int | test_spec002_ac01_routing_by_pool_and_weight |
| AC-02 | unit (hypothesis) | test_spec002_ac02_weighted_fairness_within_tolerance |
| AC-03 | unit | test_spec002_ac03_work_conserving |
| AC-04 | unit+int | test_spec002_ac04_no_starvation_under_p10_flood |
| AC-05 | int | test_spec002_ac05_weight_snapshot_on_submit |
