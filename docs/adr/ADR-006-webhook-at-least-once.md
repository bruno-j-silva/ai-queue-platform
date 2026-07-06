# ADR-006 — Webhooks at-least-once com HMAC e outbox

- **Status:** Aceita
- **Data:** 2026-07-05

## Contexto
RF-040..044: entrega confiável do resultado, com segurança verificável pelo tenant.

## Decisão
- **Outbox transacional:** a transição de estado terminal e a criação do registro `webhook_deliveries` ocorrem na mesma transação; um relay publica na fila `webhooks.delivery`. Elimina a janela "estado mudou mas webhook nunca foi enfileirado".
- **At-least-once:** retries com backoff exponencial + jitter (1m, 5m, 30m, 2h, 12h). Payload inclui `delivery_id` e `attempt` para dedupe no cliente.
- **Assinatura:** header `X-Signature: sha256=HMAC(secret, timestamp + "." + body)` + `X-Timestamp` (janela anti-replay de 5 min). Segredo por endpoint, rotacionável.
- **DLQ:** após esgotar tentativas, entrega vai para `webhooks.dlq`; operador pode reprocessar via Admin API.

## Alternativas consideradas
- Exactly-once: impossível de garantir fim-a-fim sobre HTTP; dedupe no cliente é o padrão da indústria (Stripe, GitHub).

## Consequências
- (+) Zero perda entre estado e notificação; segurança verificável.
- (−) Cliente precisa implementar dedupe idempotente — documentado no guia de integração (04-api-spec).
