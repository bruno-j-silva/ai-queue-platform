# 04 — Contrato da API (v1)

Base: `https://api.<dominio>/v1` · Auth: `Authorization: Bearer <api_key>` · Erros: RFC 9457 (problem+json).

## Endpoints do tenant

### POST /v1/jobs — submeter job (RF-001)
```json
{
  "model": "llama3.1-70b",
  "input": {
    "messages": [
      {"role": "user", "content": [
        {"type": "text", "text": "Descreva esta imagem"},
        {"type": "artifact", "artifact_id": "a1b2..."}
      ]}
    ],
    "params": {"temperature": 0.2, "max_tokens": 1024, "json_mode": false}
  },
  "timeout_seconds": 300,
  "webhook_endpoint_id": "we_123",
  "metadata": {"correlation_id": "livre-para-o-tenant"}
}
```
Headers opcionais: `Idempotency-Key` (RF-006).

**202 Accepted**
```json
{"job_id": "j_9f2...", "status": "queued", "created_at": "...", "links": {"self": "/v1/jobs/j_9f2..."}}
```
Erros: `401` chave inválida · `422` payload/modelo/capability inválidos (RF-004) · `413` payload acima do limite do plano.

### GET /v1/jobs/{id} — status/resultado (RF-003)
```json
{
  "job_id": "j_9f2...",
  "status": "succeeded",
  "queue_position": null,
  "result": {"output": [{"type": "text", "text": "..."}], "artifact_urls": []},
  "usage": {"input_tokens": 812, "output_tokens": 240, "duration_ms": 5410},
  "error": null,
  "timestamps": {"queued_at": "...", "started_at": "...", "finished_at": "..."},
  "expires_at": "..."
}
```

### GET /v1/jobs — listar (filtros: `status`, `created_after`, `cursor`)

### DELETE /v1/jobs/{id} — cancelar (RF-030/031/032)
- `202` cancelamento aceito (queued ou running)
- `409` job já em estado terminal — body traz o estado final

### POST /v1/artifacts — upload multimodal (ADR-004)
```json
{"media_type": "image/png", "size_bytes": 482113}
```
**201** → `{"artifact_id": "...", "upload_url": "https://minio/...presigned...", "expires_in": 900}`
Cliente faz `PUT` direto na `upload_url`.

### Webhook endpoints
- `POST /v1/webhook-endpoints` `{"url": "https://cliente/callback"}` → retorna `secret` (exibido uma única vez)
- `GET /v1/webhook-endpoints` · `DELETE /v1/webhook-endpoints/{id}`
- `POST /v1/webhook-endpoints/{id}/test` — dispara evento de teste

## Payload do webhook (RF-040..043)

`POST <url do tenant>` com headers:
```
X-Delivery-Id: d_77ab...
X-Timestamp: 1720180800
X-Signature: sha256=hex(HMAC_SHA256(secret, timestamp + "." + raw_body))
X-Attempt: 2
```
Body:
```json
{
  "event": "job.succeeded",            // job.succeeded | job.failed | job.cancelled | job.expired
  "delivery_id": "d_77ab...",
  "attempt": 2,
  "job": { ...mesmo shape do GET /v1/jobs/{id}... }
}
```
Regras para o cliente: responder `2xx` em ≤ 10s (RB-04); deduplicar por `delivery_id`; validar assinatura e janela de timestamp de 5 min.

## Admin API (operador) — prefixo /admin/v1, auth separada
- CRUD `tenants`, `plans`, `models`, `plan-models` (RF-052)
- `GET /admin/v1/dlq/webhooks` + `POST /admin/v1/dlq/webhooks/{id}/redeliver` (RF-042)
- `GET /admin/v1/queues` — profundidade por fila/prioridade

## Versionamento
Breaking changes ⇒ `/v2` (RNF-008). Campos novos são sempre aditivos e opcionais em v1.
