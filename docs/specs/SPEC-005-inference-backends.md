# SPEC-005 — Execução e backends plugáveis (Ollama/vLLM)

- **Status:** Aprovada
- **Milestone:** M2 (Ollama/texto) + M6 (vLLM)
- **Requisitos:** RF-020..023, RNF-006
- **ADRs:** ADR-003, ADR-005

## História
Como operador, quero executar jobs em Ollama ou vLLM através de uma interface única, para escolher o engine por modelo sem alterar o core.

## Critérios de aceitação
| ID | Critério |
|---|---|
| AC-01 | O worker deve resolver o backend pelo catálogo (`model_id → backend`) e executar via Protocol `InferenceBackend`, sem `if backend == "ollama"` fora do registry. |
| AC-02 | QUANDO a inferência excede `timeout_seconds`, o worker deve abortar, marcar `failed` com `error.code=timeout` e liberar o slot. |
| AC-03 | SE ocorrer erro transiente (conexão, 503, OOM sinalizado como retryable), ENTÃO reexecutar com backoff (1s, 4s, 16s) até 3 tentativas antes de `failed`. |
| AC-04 | SE ocorrer erro permanente (modelo inexistente no backend, payload rejeitado), ENTÃO `failed` imediato sem retry. |
| AC-05 | Todo job concluído deve registrar `usage` (tokens in/out, duration_ms, backend, attempt). |
| AC-06 | SE o worker morrer durante a execução, ENTÃO a mensagem deve ser reentregue e o job reprocessado do zero (acks_late), sem duplicar efeitos (job ainda `running` volta a `running` com attempt+1). |
| AC-07 | Toda implementação de backend deve passar a suíte de contrato (gera texto, respeita max_tokens, aborta ≤ 2s, reporta usage, health fiel). |

## Design notes
- `OllamaBackend`: `/api/chat` com stream para permitir checagem do CancelToken por chunk.
- `VLLMBackend`: endpoint OpenAI-compatible `/v1/chat/completions` com stream.
- Classificador de erros por backend: mapeia respostas para `retryable: bool`.

## Plano de testes
| AC | Nível | Teste |
|---|---|---|
| AC-01 | unit | test_spec005_ac01_registry_resolves_backend |
| AC-02 | unit | test_spec005_ac02_timeout_aborts_and_fails (Clock + FakeBackend lento) |
| AC-03/04 | unit | test_spec005_ac03_transient_retries / ac04_permanent_no_retry |
| AC-05 | int | test_spec005_ac05_usage_recorded |
| AC-06 | int | test_spec005_ac06_worker_crash_redelivery |
| AC-07 | contract | suíte parametrizada contract/backends (Fake sempre; live noturno) |
