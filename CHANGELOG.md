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
- **M3 — Webhook delivery:** CRUD de endpoints com segredo gerado/hasheado/cifrado; assinatura HMAC-SHA256; criação de delivery na mesma transição terminal; dispatcher Celery com backoff 1m/5m/30m/2h; esgotamento → dead + DLQ + métrica; redeliver admin preservando delivery_id; endpoint de teste; poller de retry com Clock injetável; SSRF protection; E2E com DLQ + redeliver.
