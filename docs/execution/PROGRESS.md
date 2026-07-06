# PROGRESS — Dashboard de Execução

> Painel consolidado de evolução do MVP. Fonte das atividades: [`00-plano-execucao.md`](./00-plano-execucao.md). Detalhe por fase: [`checks/`](./checks/).
> **Atualize este arquivo ao fechar cada AC e ao mover o status de um milestone.**

## Legenda de status
- ⬜ **Não iniciado** — nenhuma atividade começada.
- 🟡 **Em progresso** — pelo menos um AC em Red/Green, DoD ainda não satisfeito.
- ✅ **Concluído** — todos os ACs verdes + Definition of Done satisfeito.

## Rollup por milestone

| Fase | Milestone | Status | ACs verdes | Cobertura | DoD | Check |
|---|---|:--:|:--:|:--:|:--:|---|
| F0 | M0 — Fundação | ⬜ | — (infra) | — | ⬜ | [M0](./checks/M0.md) |
| F1 | M1 — Submissão e ciclo de vida | ⬜ | 0/8 (+I1) | — | ⬜ | [M1](./checks/M1.md) |
| F2 | M2 — Worker + Ollama (texto) | ⬜ | 0/6 | — | ⬜ | [M2](./checks/M2.md) |
| F3 | M3 — Webhook delivery | ⬜ | 0/8 | — | ⬜ | [M3](./checks/M3.md) |
| F4 | M4 — Priorização por plano | ⬜ | 0/5 | — | ⬜ | [M4](./checks/M4.md) |
| F5 | M5 — Cancelamento | ⬜ | 0/6 (+corrida) | — | ⬜ | [M5](./checks/M5.md) |
| F6 | M6 — Multimodal + vLLM | ⬜ | 0/8 | — | ⬜ | [M6](./checks/M6.md) |
| F7 | M7 — Observabilidade + hardening | ⬜ | 0/5 | — | ⬜ | [M7](./checks/M7.md) |
| F8 | M8 — Kubernetes | ⬜ | 0/5 | — | ⬜ | [M8](./checks/M8.md) |

> Contagem de ACs: M1=8, M2=6, M3=8, M4=5, M5=6, M6=8 (SPEC-006 AC-01..07 + SPEC-005 AC-07), M7=5, M8=5. **Total de ACs de spec = 43** (+ invariante I1 em M1 e teste de corrida em M5). M0 é medido por DoD de infra.

## Progresso do MVP (M0–M7)

```
M0 [                    ] 0%
M1 [                    ] 0%
M2 [                    ] 0%
M3 [                    ] 0%
M4 [                    ] 0%
M5 [                    ] 0%
M6 [                    ] 0%
M7 [                    ] 0%
```
**MVP: 0/8 milestones concluídos.**

## Progresso do projeto completo (M0–M8)
**0/9 milestones concluídos.**

## Grafo de dependências
```
M0 ─▶ M1 ─▶ M2 ─┬─▶ M3 ─┐
                ├─▶ M4 ─┼─▶ M6 ─▶ M7 ─▶ M8
                └─▶ M5 ─┘
```
M3/M4/M5 podem ser executados em paralelo após M2.

## Métricas de sucesso do MVP (gate final — verificar em M7)
- [ ] 95% dos jobs premium iniciam em < 30s sob carga nominal.
- [ ] ≥ 99% dos webhooks entregues em até 3 tentativas.
- [ ] Zero jobs perdidos (todo job atinge estado terminal).
- [ ] Throughput de milhares de jobs/dia com headroom de 10x.

## Como atualizar
1. Ao passar um AC para verde, marque `Green [x]` no check do milestone.
2. Recalcule "ACs verdes" e a barra de progresso do milestone aqui.
3. Ao satisfazer o Definition of Done, mude o status para ✅ e a cobertura final.
4. Registre a data de fechamento no cabeçalho do check do milestone.
