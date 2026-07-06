# 03 — Modelo de Dados (PostgreSQL)

## Diagrama lógico

```
tenants ─1:N─ api_keys
tenants ─N:1─ plans
tenants ─1:N─ jobs ─1:N─ job_events
tenants ─1:N─ webhook_endpoints ─1:N─ webhook_deliveries ─N:1─ jobs
jobs ─N:M─ artifacts (job_artifacts)
plans ─N:M─ models (plan_models)
models ─N:1─ backends (lógico, via campo)
outbox (relay para RabbitMQ)
```

## Tabelas

### tenants
| Coluna | Tipo | Notas |
|---|---|---|
| id | uuid PK | |
| name | text | |
| plan_id | uuid FK plans | |
| status | enum(active, suspended) | |
| created_at / updated_at | timestamptz | |

### plans
| Coluna | Tipo | Notas |
|---|---|---|
| id | uuid PK | |
| name | text | free / pro / enterprise |
| priority_weight | int | RB-01: 1 / 5 / 10 |
| max_timeout_seconds | int | RB-02 |
| result_ttl_days | int | default 7 |
| max_payload_mb | int | RB-03 |

### api_keys
| Coluna | Tipo | Notas |
|---|---|---|
| id | uuid PK | |
| tenant_id | uuid FK | |
| key_hash | text | SHA-256; nunca plaintext (RF-050) |
| prefix | text | 8 chars visíveis p/ identificação |
| status | enum(active, revoked) | rotação = criar nova + revogar antiga |
| last_used_at | timestamptz | |

### models (catálogo)
| Coluna | Tipo | Notas |
|---|---|---|
| id | text PK | ex.: `llama3.1-70b` (nome público) |
| backend | enum(ollama, vllm) | ADR-003 |
| backend_model_name | text | nome interno no backend |
| capabilities | jsonb | ["text","vision","audio","json_mode"] |
| pool | text | classe de capacidade → define fila (ex.: gpu-a) |
| status | enum(active, disabled) | |

### plan_models
`(plan_id, model_id)` — modelos permitidos por plano (RF-052).

### jobs
| Coluna | Tipo | Notas |
|---|---|---|
| id | uuid PK | |
| tenant_id | uuid FK | index composto (tenant_id, created_at) |
| model_id | text FK models | |
| status | enum(queued, running, succeeded, failed, cancelled, expired) | RF-002 |
| priority_weight | int | snapshot do plano no submit |
| payload | jsonb | mensagens/params; mídias por artifact_id |
| result_inline | jsonb null | resultados ≤ 256 KB |
| result_artifact_id | uuid null | resultados grandes (ADR-004) |
| error | jsonb null | {code, message, retryable} |
| timeout_seconds | int | ≤ teto do plano (RF-021) |
| idempotency_key | text null | unique (tenant_id, idempotency_key) (RF-006) |
| cancel_requested | bool default false | ADR-005 |
| attempt | int default 0 | RF-022 |
| usage | jsonb null | tokens in/out, duration_ms, backend (RF-023) |
| queued_at / started_at / finished_at | timestamptz | |
| expires_at | timestamptz | TTL do resultado (RF-044) |

### job_events (auditoria da máquina de estados)
| Coluna | Tipo |
|---|---|
| id | bigserial PK |
| job_id | uuid FK |
| from_status / to_status | enum |
| detail | jsonb |
| created_at | timestamptz |

### artifacts
| Coluna | Tipo | Notas |
|---|---|---|
| id | uuid PK | |
| tenant_id | uuid FK | isolamento (RF-051) |
| kind | enum(input, output) | |
| media_type | text | image/png, audio/wav... |
| storage_key | text | caminho no MinIO |
| size_bytes | bigint | |
| expires_at | timestamptz | lifecycle |

### webhook_endpoints
| Coluna | Tipo | Notas |
|---|---|---|
| id | uuid PK | |
| tenant_id | uuid FK | |
| url | text | HTTPS obrigatório |
| secret_hash | text | segredo HMAC (mostrado uma vez) |
| status | enum(active, disabled) | |

### webhook_deliveries
| Coluna | Tipo | Notas |
|---|---|---|
| id | uuid PK | delivery_id no payload (RF-043) |
| job_id | uuid FK | |
| endpoint_id | uuid FK | |
| status | enum(pending, delivering, delivered, dead) | |
| attempt | int | |
| next_attempt_at | timestamptz | schedule de retry |
| last_response_code | int null | |
| created_at / delivered_at | timestamptz | |

### outbox
| Coluna | Tipo | Notas |
|---|---|---|
| id | bigserial PK | |
| topic | text | inference.dispatch / webhook.delivery |
| payload | jsonb | |
| published_at | timestamptz null | null = pendente |

## Invariantes (verificados por testes)

- I1. Transições de `jobs.status` só pelas arestas válidas da máquina de estados; toda transição gera `job_events`.
- I2. `(tenant_id, idempotency_key)` único quando não nulo.
- I3. Job em estado terminal é imutável (exceto expiração de resultado).
- I4. Toda linha de `jobs` criada tem linha correspondente em `outbox` na mesma transação.
- I5. Nenhuma query de leitura de jobs/artifacts sem filtro por `tenant_id` (enforced por repositório + testes de isolamento).
