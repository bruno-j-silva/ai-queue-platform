# Changelog

## 2026-08-19

- Conectada a submissão de jobs ao Celery por transactional outbox e RabbitMQ quorum.
- Implementadas dependências assíncronas reais para PostgreSQL e Redis.
- Alinhado o contrato de `POST /v1/jobs` e `GET /v1/jobs/{id}` à API v1.
- Adicionadas validações de tenant, modelo, payload, timeout e idempotência por header.
- Centralizadas as transições do worker com registro de `job_events`.
- Adicionados Dockerfile não-root, serviços Compose da aplicação e smoke E2E completo.
- Adicionados contratos do FakeBackend e OllamaBackend; cobertura mínima elevada para 85%.
- Removido `.env` do versionamento.
