# SPEC-008 — Deploy Kubernetes

- **Status:** Draft (detalhar em M7)
- **Milestone:** M8
- **Requisitos:** RNF-003, RNF-004, RNF-005

## História
Como operador, quero implantar a plataforma em Kubernetes com escala e segredos gerenciados, para operar em produção com confiabilidade.

## Critérios de aceitação (alto nível — refinar)
| ID | Critério |
|---|---|
| AC-01 | Helm chart único instala API, workers (por pool), dispatcher, relay do outbox; RabbitMQ/Postgres via operator ou serviço gerenciado configurável por values. |
| AC-02 | API com HPA por CPU/RPS; workers com nodeSelector/tolerations para nós GPU. |
| AC-03 | Segredos (API keys admin, HMAC, credenciais) via Secret externo (ESO/Vault), nunca em values. |
| AC-04 | Rolling update de workers não perde jobs: preStop drena (para de consumir, termina job atual dentro do grace period configurável ≥ timeout máx do pool). |
| AC-05 | Smoke test e2e roda contra o cluster de staging no pipeline de release. |

## Questões em aberto
- Autoscaling por profundidade de fila (KEDA) entra aqui ou pós-MVP? (proposta: pós-MVP)
- Cluster alvo: on-prem Callink ou cloud? Define storage class e GPU node pools.
