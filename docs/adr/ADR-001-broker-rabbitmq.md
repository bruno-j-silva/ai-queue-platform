# ADR-001 — RabbitMQ como broker de mensagens

- **Status:** Aceita
- **Data:** 2026-07-05

## Contexto
Precisamos de um broker durável para jobs de inferência longos (segundos a minutos), com priorização, redelivery em falha de worker, DLQ e roteamento por tipo de fila. Escala alvo: milhares de jobs/dia com headroom 10x.

## Decisão
Usar **RabbitMQ** com quorum queues, publisher confirms e manual ack, como broker do Celery.

## Alternativas consideradas
- **Redis (BullMQ/Celery-Redis):** simples, mas garantias de durabilidade mais fracas para jobs longos; sem DLX nativo rico.
- **Kafka:** excelente throughput, mas semântica de fila de trabalho (ack individual, retry seletivo, prioridade) é desajeitada; complexidade operacional desnecessária nesta escala.
- **PostgreSQL como fila:** viável na escala inicial, mas perderíamos roteamento, delayed retry e o ecossistema Celery/Rabbit.

## Consequências
- (+) Semântica de work queue madura, DLX/TTL nativos, management UI, integração de primeira classe com Celery.
- (−) Mais um componente stateful para operar; em K8s usaremos o RabbitMQ Cluster Operator.
- Prioridade NÃO usará `x-max-priority` nativo (ver ADR-002).
