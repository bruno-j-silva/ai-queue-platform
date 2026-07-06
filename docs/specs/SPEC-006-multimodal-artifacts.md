# SPEC-006 — Payloads multimodais e artifacts

- **Status:** Aprovada
- **Milestone:** M6
- **Requisitos:** RF-004, RF-005, RB-03, RNF-005, RNF-007
- **ADRs:** ADR-004

## História
Como desenvolvedor integrador, quero enviar imagens, áudio e documentos junto do prompt, para executar tarefas multimodais nos modelos que as suportam.

## Critérios de aceitação
| ID | Critério |
|---|---|
| AC-01 | QUANDO o tenant cria um artifact, deve receber presigned URL de upload válida por 15 min, restrita ao media_type/size declarados. |
| AC-02 | QUANDO um job referencia artifact_ids, o submit deve validar existência, posse pelo tenant e compatibilidade com as capabilities do modelo; caso contrário 422. |
| AC-03 | SE o modelo não suporta a modalidade (ex.: áudio em modelo text-only), ENTÃO 422 com `error.code=capability_not_supported`. |
| AC-04 | O worker deve baixar artifacts do MinIO e montar o request no formato do backend (ex.: imagens base64 no Ollama, image_url no vLLM). |
| AC-05 | Resultados > 256 KB devem ir para MinIO como artifact `output` com URL presigned no GET/webhook. |
| AC-06 | Artifacts devem expirar conforme TTL do plano; acesso após expiração retorna 410. |
| AC-07 | Payload inline em base64 acima de 1 MB deve ser rejeitado com 413 orientando uso de artifacts. |

## Plano de testes
| AC | Nível | Teste |
|---|---|---|
| AC-01 | int | test_spec006_ac01_presigned_upload_constraints |
| AC-02/03 | unit+int | test_spec006_ac02_ownership_and_capability_validation |
| AC-04 | contract | test_spec006_ac04_backend_specific_media_encoding |
| AC-05 | int | test_spec006_ac05_large_result_to_object_storage |
| AC-06 | int | test_spec006_ac06_expired_artifact_410 |
| AC-07 | unit | test_spec006_ac07_inline_base64_limit_413 |
