# 00 — Visão e Escopo

## Problema

Times e clientes precisam executar tarefas de IA (texto, visão, áudio) sobre LLMs auto-hospedados, mas inferência é lenta, cara em GPU e sujeita a picos. Chamadas síncronas causam timeouts, desperdiçam capacidade e não permitem controlar consumo por cliente.

## Solução

Uma plataforma de **inferência assíncrona multi-tenant**: o cliente submete um job via API e recebe imediatamente um `job_id`; a plataforma enfileira, prioriza conforme o plano do tenant, executa em workers com GPU e entrega o resultado via **webhook** assinado, com retry e dead-letter.

## Objetivos (Goals)

- G1. Absorver picos de demanda sem degradar clientes de planos superiores.
- G2. Suportar múltiplos backends de inferência (Ollama, vLLM) atrás de uma interface única.
- G3. Suportar payloads multimodais (texto, imagem, áudio, documentos).
- G4. Garantir entrega do resultado ao cliente (at-least-once, com DLQ para falhas persistentes).
- G5. Dar visibilidade operacional completa (métricas por tenant, fila, worker, modelo).
- G6. Permitir cancelamento de jobs na fila e em execução.

## Não-objetivos (Non-Goals) — MVP

- NG1. Streaming de tokens em tempo real (o modelo é assíncrono; SSE fica para versão futura).
- NG2. Fine-tuning ou gestão de treinamento de modelos.
- NG3. Billing/cobrança automatizada (apenas contabilização de uso; quotas e rate limiting entram pós-MVP).
- NG4. Console web self-service para tenants (interação via API no MVP).
- NG5. Roteamento para APIs externas (Claude/OpenAI) — arquitetura deve permitir, mas não implementa.

## Personas

| Persona | Necessidade |
|---|---|
| **Desenvolvedor integrador (tenant)** | Submeter jobs, acompanhar status, receber webhook confiável, cancelar jobs |
| **Operador da plataforma** | Ver saúde das filas, GPU, latências; gerenciar tenants, planos e modelos; reprocessar DLQ |
| **Gestor do tenant** | Entender consumo e SLA do seu plano |

## Métricas de sucesso do MVP

- 95% dos jobs de plano premium iniciam processamento em < 30s sob carga nominal.
- ≥ 99% dos webhooks entregues com sucesso em até 3 tentativas.
- Zero jobs perdidos (todo job termina em `succeeded`, `failed`, `cancelled` ou `expired` — nunca desaparece).
- Throughput sustentado de milhares de jobs/dia com headroom para 10x.
