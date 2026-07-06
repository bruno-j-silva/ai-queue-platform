# ADR-005 — Cancelamento cooperativo com flag centralizada

- **Status:** Aceita
- **Data:** 2026-07-05

## Contexto
RF-030/031: cancelar jobs na fila e em execução (≤ 10s). Matar processos de worker (SIGKILL) desperdiça o worker inteiro e corrompe estado do Celery; Celery `revoke(terminate=True)` é destrutivo e não aborta a chamada HTTP ao backend.

## Decisão
- Flag `cancel_requested` no registro do job (Postgres) + cache Redis para leitura barata.
- **Queued:** tombstone check — o worker verifica a flag ao consumir e descarta (ack) sem executar.
- **Running:** o worker passa um `CancelToken` ao backend; o loop de inferência checa o token a cada chunk/intervalo (≤ 2s) e chama `backend.abort()` (Ollama: fechar conexão de stream; vLLM: `POST /abort` / cancelar request).
- Transição final `cancelled` é feita pelo próprio worker, garantindo consistência da máquina de estados.

## Consequências
- (+) Sem processos zumbis; worker liberado imediatamente para o próximo job.
- (+) Semântica testável: "cancel efetivo em ≤ 10s" vira critério de aceitação mensurável.
- (−) Backends precisam suportar aborto ou, no pior caso, o token só interrompe entre etapas.
