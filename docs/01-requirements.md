# 01 — Requisitos (formato EARS)

Sintaxe EARS (Easy Approach to Requirements Syntax):
- **Ubíquo:** "O sistema deve..."
- **Event-driven:** "QUANDO <evento>, o sistema deve..."
- **State-driven:** "ENQUANTO <estado>, o sistema deve..."
- **Unwanted behavior:** "SE <condição indesejada>, ENTÃO o sistema deve..."
- **Opcional:** "ONDE <feature habilitada>, o sistema deve..."

Prioridade MoSCoW: **M**ust / **S**hould / **C**ould / **W**on't (MVP).

## Requisitos Funcionais

### Submissão e ciclo de vida de jobs

| ID | Requisito | Prio |
|---|---|---|
| RF-001 | QUANDO um tenant autenticado submete um job válido, o sistema deve persistir o job, enfileirá-lo e retornar `202 Accepted` com `job_id` em < 500ms (p95). | M |
| RF-002 | O sistema deve manter o ciclo de vida do job na máquina de estados: `queued → running → succeeded \| failed \| cancelled \| expired`, registrando cada transição com timestamp em `job_events`. | M |
| RF-003 | QUANDO um tenant consulta `GET /v1/jobs/{id}`, o sistema deve retornar status, posição estimada na fila (se `queued`), resultado (se `succeeded`) e erro estruturado (se `failed`). | M |
| RF-004 | SE o payload do job for inválido (schema, modelo inexistente, mídia não suportada), ENTÃO o sistema deve rejeitar com `422` e erro estruturado, sem enfileirar. | M |
| RF-005 | O sistema deve aceitar payloads multimodais: texto, imagens, áudio e documentos, com mídias enviadas por upload prévio (artifact) ou URL. | M |
| RF-006 | QUANDO um job é submetido com header `Idempotency-Key` repetido pelo mesmo tenant, o sistema deve retornar o job original sem criar duplicata. | S |

### Priorização e agendamento

| ID | Requisito | Prio |
|---|---|---|
| RF-010 | O sistema deve despachar jobs respeitando a prioridade do plano do tenant (ex.: enterprise > pro > free). | M |
| RF-011 | ENQUANTO houver jobs de prioridades diferentes na fila, o sistema deve garantir anti-starvation: jobs de baixa prioridade devem iniciar em no máximo T_starvation (configurável, default 15 min) sob carga nominal. | M |
| RF-012 | O sistema deve rotear jobs para a fila do modelo/backend adequado (uma fila lógica por classe de capacidade). | M |

### Execução e backends

| ID | Requisito | Prio |
|---|---|---|
| RF-020 | O sistema deve executar inferência através de uma interface `InferenceBackend` plugável, com implementações para Ollama e vLLM. | M |
| RF-021 | QUANDO um job atinge seu timeout (definido pelo tenant no submit, limitado pelo teto do plano), o sistema deve abortar a inferência, marcar `failed` com `error.code=timeout` e liberar o worker. | M |
| RF-022 | SE a inferência falhar por erro transiente (backend indisponível, OOM recuperável), ENTÃO o sistema deve reexecutar com backoff exponencial até N tentativas (default 3) antes de marcar `failed`. | M |
| RF-023 | O sistema deve registrar métricas de uso por job: tokens de entrada/saída, duração, modelo, backend. | M |

### Cancelamento

| ID | Requisito | Prio |
|---|---|---|
| RF-030 | QUANDO um tenant cancela um job `queued`, o sistema deve removê-lo do despacho e marcá-lo `cancelled` imediatamente. | M |
| RF-031 | QUANDO um tenant cancela um job `running`, o sistema deve sinalizar o worker, que deve abortar a inferência cooperativamente em até 10s e marcar `cancelled`. | M |
| RF-032 | SE o cancelamento chegar após o job terminar, ENTÃO o sistema deve retornar `409 Conflict` com o estado final. | M |

### Entrega de resultados (webhooks)

| ID | Requisito | Prio |
|---|---|---|
| RF-040 | QUANDO um job atinge estado terminal, o sistema deve entregar um webhook POST na URL registrada pelo tenant, assinado com HMAC-SHA256. | M |
| RF-041 | SE a entrega do webhook falhar (timeout, 5xx, erro de rede), ENTÃO o sistema deve retentar com backoff exponencial + jitter (ex.: 1m, 5m, 30m, 2h, 12h) até N tentativas. | M |
| RF-042 | SE todas as tentativas falharem, ENTÃO o sistema deve mover a entrega para a DLQ de webhooks, expor no endpoint de status e emitir métrica/alerta. | M |
| RF-043 | O sistema deve garantir semântica at-least-once na entrega; o payload deve conter `delivery_id` e `attempt` para deduplicação pelo cliente. | M |
| RF-044 | O resultado deve permanecer disponível via `GET /v1/jobs/{id}` por um TTL configurável (default 7 dias), independente do webhook. | M |

### Multi-tenancy e autenticação

| ID | Requisito | Prio |
|---|---|---|
| RF-050 | O sistema deve autenticar toda requisição via API Key por tenant (`Authorization: Bearer`), com hash armazenado (nunca plaintext) e suporte a rotação (múltiplas chaves ativas). | M |
| RF-051 | O sistema deve isolar dados por tenant: nenhum tenant pode ler, cancelar ou listar jobs de outro. | M |
| RF-052 | O sistema deve permitir ao operador CRUD de tenants, planos e associação de modelos permitidos por plano. | M |
| RF-053 | ONDE rate limiting estiver habilitado (pós-MVP), o sistema deve limitar req/s por tenant conforme o plano. | C |
| RF-054 | ONDE quotas estiverem habilitadas (pós-MVP), o sistema deve bloquear submissão ao exceder tokens/jobs do período. | C |

## Requisitos Não-Funcionais

| ID | Requisito | Prio |
|---|---|---|
| RNF-001 | **Durabilidade:** nenhum job aceito (202) pode ser perdido; filas duráveis (quorum queues), acks manuais, outbox para eventos críticos. | M |
| RNF-002 | **Observabilidade:** métricas Prometheus (profundidade de fila por prioridade, latência de espera/execução p50/p95/p99, taxa de erro, entregas de webhook, utilização de workers) e dashboards Grafana; logs estruturados JSON com `job_id`/`tenant_id` correlacionados. | M |
| RNF-003 | **Escalabilidade horizontal:** API e workers stateless; adicionar workers não requer mudança de configuração central. | M |
| RNF-004 | **Deploy:** ambiente completo reproduzível via Docker Compose; manifests/Helm para Kubernetes em produção. | M |
| RNF-005 | **Segurança:** TLS externo; segredos fora do código; payloads e resultados de tenants cifrados em repouso no object storage. | M |
| RNF-006 | **Recuperação:** SE um worker morrer no meio de um job, ENTÃO o job deve retornar à fila (redelivery) e ser reprocessado respeitando idempotência. | M |
| RNF-007 | **Retenção:** artefatos e resultados expiram conforme TTL do plano; limpeza automática auditável. | S |
| RNF-008 | **Compatibilidade:** API versionada (`/v1`); mudanças breaking exigem nova versão. | M |

## Regras de negócio

- RB-01. Prioridades de plano no MVP: `enterprise=10`, `pro=5`, `free=1` (pesos do scheduler).
- RB-02. Teto de timeout por plano: free 120s, pro 600s, enterprise 1800s.
- RB-03. Tamanho máximo de payload por job: 50 MB (mídias via artifact/URL, nunca inline em base64 acima de 1 MB).
- RB-04. Webhook: resposta 2xx em até 10s conta como entregue; qualquer outra coisa é falha.

## Questões em aberto

| ID | Questão | Dono | Status |
|---|---|---|---|
| Q-01 | Nome definitivo do produto | Bruno | Aberta |
| Q-02 | Modelos iniciais do catálogo (quais LLMs em Ollama/vLLM?) | Bruno | Aberta |
| Q-03 | Áudio: transcrição (Whisper) entra como backend próprio ou modelo multimodal? | Bruno | Aberta |
| Q-04 | Política de retenção de mídia de entrada (LGPD/PII de clientes finais) | Bruno | Aberta |
