# ADR-004 — Artifacts multimodais em object storage (MinIO)

- **Status:** Aceita
- **Data:** 2026-07-05

## Contexto
RF-005 exige payloads multimodais. Mídias (imagens, áudio, documentos) não devem trafegar pelo broker nem inchar o Postgres (RB-03).

## Decisão
- Upload prévio via `POST /v1/artifacts` → presigned URL do MinIO; o job referencia `artifact_id`s.
- Resultados grandes (> 256 KB) também vão para MinIO; o webhook e o `GET /jobs/{id}` retornam URL presigned de leitura.
- Prefixo por tenant + criptografia SSE + lifecycle rules por TTL do plano.

## Consequências
- (+) Broker e DB permanecem leves; download é feito só pelo worker que executa.
- (+) TTL/limpeza delegados ao lifecycle do storage (RNF-007).
- (−) Mais um serviço no Compose/K8s; em produção pode ser trocado por S3 real (interface idêntica).
