# 06 — Estratégia de Testes (TDD)

## Pirâmide

| Nível | Escopo | Ferramentas | Velocidade |
|---|---|---|---|
| **Unit** (~70%) | Máquina de estados, scheduler ponderado, validação, assinatura HMAC, cálculo de backoff | pytest + FakeBackend/fakes in-memory | ms |
| **Integração** (~25%) | Repositórios Postgres, publish/consume RabbitMQ, presigned MinIO, outbox relay | pytest + **testcontainers** (Postgres, RabbitMQ, MinIO reais) | s |
| **E2E** (~5%) | Fluxos completos via Docker Compose: submit→process→webhook; cancel; retry→DLQ | pytest + httpx + receptor de webhook fake | min |

## Disciplina TDD por feature

1. Ler a `SPEC-NNN` e transformar cada AC em um teste nomeado com o ID:
   ```python
   def test_spec001_ac03_invalid_model_returns_422(): ...
   ```
2. Rodar → **red** (todos falham pelo motivo certo).
3. Implementar o mínimo → **green**.
4. **Refactor** com a suíte verde.
5. PR só é mergeável com: todos os ACs da spec cobertos (checklist na PR), cobertura ≥ 85% nos módulos tocados, mypy/ruff limpos.

## Padrões de teste críticos deste domínio

### FakeBackend (determinístico, sem GPU)
Implementa `InferenceBackend` com comportamento programável por teste: latência simulada, falha transiente na tentativa N, respeito ao CancelToken, resposta multimodal fake. **Todo teste do core usa FakeBackend**; Ollama/vLLM reais só aparecem nos testes de contrato.

### Testes de contrato de backends (ADR-003)
Suíte única parametrizada que roda contra `FakeBackend` (sempre no CI) e contra Ollama/vLLM reais (job noturno/manual, marcados `@pytest.mark.live_backend`):
- gera texto e respeita `max_tokens`
- aborta em ≤ 2s após CancelToken
- reporta usage (tokens/duração)
- health() reflete indisponibilidade

### Propriedades e invariantes (hypothesis)
- Máquina de estados nunca aceita transição inválida (I1).
- Scheduler ponderado: para qualquer sequência de chegada, fração de slots de p1 ≥ mínimo garantido (RF-011).
- Assinatura HMAC: verify(sign(x)) == True; alterar 1 byte quebra.

### Testes de resiliência (integração)
- Matar worker no meio do job → redelivery e reprocesso (RNF-006).
- RabbitMQ indisponível no submit → outbox segura o evento; relay publica ao voltar (I4).
- Receptor de webhook retorna 500 5x → delivery em DLQ com `attempt=5` (RF-041/042).

### Testes de isolamento multi-tenant (RF-051)
Fixture com 2 tenants; toda rota de leitura/cancelamento é exercitada cross-tenant e deve retornar 404 (nunca 403, para não vazar existência).

### Testes de tempo
Nada de `sleep` real em unit: relógio injetável (`Clock` protocol) e avanço manual para backoff, TTL e anti-starvation.

## Estrutura de diretórios
```
tests/
  unit/
  integration/        # testcontainers
  e2e/                # compose
  contract/backends/  # suíte parametrizada
  conftest.py         # fakes, fixtures, clock
```

## CI (GitHub Actions ou equivalente)
- PR: unit + integração (testcontainers) + lint + type-check. Alvo < 10 min.
- Merge em main: + e2e via Compose.
- Noturno: contrato contra backends reais (runner com GPU/Ollama CPU).
