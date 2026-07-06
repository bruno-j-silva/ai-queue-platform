# ADR-002 — Priorização via filas separadas com consumo ponderado

- **Status:** Aceita
- **Data:** 2026-07-05

## Contexto
RF-010/RF-011 exigem priorização por plano com anti-starvation. RabbitMQ oferece priority queues nativas (`x-max-priority`), mas elas causam starvation total de mensagens de baixa prioridade sob carga e têm custo de performance.

## Decisão
Criar **uma fila por nível de prioridade por pool de capacidade** (ex.: `inference.gpu-a.p10/p5/p1`). Workers implementam **weighted fair scheduling**: a cada slot livre, escolhem a fila proporcionalmente aos pesos do plano (10/5/1), garantindo que p1 sempre receba uma fração mínima da capacidade.

## Alternativas consideradas
- **Priority queue nativa:** starvation de free sob carga contínua de enterprise; viola RF-011.
- **Fila única FIFO + reordenação em memória:** perde durabilidade da ordenação e complica redelivery.

## Consequências
- (+) Anti-starvation determinístico e testável; métricas de profundidade por prioridade triviais.
- (+) Fácil evoluir para fairness intra-prioridade por tenant (round-robin de sub-filas) pós-MVP.
- (−) Mais filas para declarar/gerenciar → mitigado com declaração idempotente por código (infra-as-code).
