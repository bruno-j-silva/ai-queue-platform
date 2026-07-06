# ADR-003 — Interface InferenceBackend plugável

- **Status:** Aceita
- **Data:** 2026-07-05

## Contexto
RF-020 exige suportar Ollama e vLLM hoje, com portas abertas para outros backends (ex.: APIs externas) sem tocar o core.

## Decisão
Definir uma interface (Protocol) `InferenceBackend`:

```python
class InferenceBackend(Protocol):
    name: str
    async def generate(self, request: InferenceRequest, cancel: CancelToken) -> InferenceResult: ...
    async def abort(self, backend_job_ref: str) -> None: ...
    async def health(self) -> BackendHealth: ...
    def supports(self, capability: Capability) -> bool: ...  # ex.: VISION, AUDIO, JSON_MODE
```

Implementações: `OllamaBackend` (API HTTP nativa) e `VLLMBackend` (endpoint OpenAI-compatible). Um **registry** mapeia `model_id → (backend, backend_model_name, capabilities)` a partir do catálogo em Postgres. O core (worker, scheduler, API) depende apenas do Protocol — nunca de um backend concreto.

## Padrões aplicados
Strategy + Registry + Adapter. Testes de contrato compartilhados garantem que toda implementação honra a mesma semântica (ver 06-testing-strategy).

## Consequências
- (+) Adicionar um backend = nova classe + entrada no catálogo + passar na suíte de contrato.
- (+) Testes do core usam `FakeBackend` determinístico, sem GPU.
- (−) Capacidades divergentes (ex.: vLLM sem áudio nativo) exigem validação de capability no submit (RF-004).
