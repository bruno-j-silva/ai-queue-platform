# AI Queue Platform (nome provisório: "Enfila")

Plataforma multi-tenant de inferência de IA assíncrona: recebe requisições via API, enfileira com priorização por plano, processa em workers com backends plugáveis (Ollama/vLLM) e entrega o resultado via webhook.

## Stack decidida

| Camada | Tecnologia |
|---|---|
| API | Python 3.12 + FastAPI |
| Fila/Broker | RabbitMQ (quorum queues) |
| Workers | Celery |
| Persistência | PostgreSQL 16 |
| Artefatos multimodais | MinIO (S3-compatible) |
| Inferência | Ollama e vLLM (backends plugáveis) |
| Observabilidade | Prometheus + Grafana |
| Deploy | Docker Compose (dev/teste) → Kubernetes (produção) |

## Mapa da documentação

| Documento | Conteúdo |
|---|---|
| `docs/00-vision.md` | Problema, objetivos, não-objetivos, personas |
| `docs/01-requirements.md` | Requisitos funcionais e não-funcionais (formato EARS) |
| `docs/02-architecture.md` | Componentes, fluxos, diagramas |
| `docs/adr/` | Architecture Decision Records |
| `docs/03-data-model.md` | Modelo de dados (PostgreSQL) |
| `docs/04-api-spec.md` | Contrato da API REST e do webhook |
| `docs/05-roadmap.md` | Incrementos M0→M8 com definição de pronto |
| `docs/06-testing-strategy.md` | Estratégia de testes e disciplina TDD |
| `docs/specs/` | Specs por feature (fonte da verdade para implementação) |

## Desenvolvimento local

### Pré-requisitos
- Python 3.12+
- Docker e Docker Compose

### Setup

```bash
# Instalar dependências reproduzíveis
uv sync --frozen

# Copiar variáveis de ambiente
cp .env.example .env
# Editar .env com suas configurações

# Subir API, worker, relay, migrações e infraestrutura
docker compose up -d --build --wait

# Rodar testes e gates locais
uv run pytest --cov
uv run ruff check .
uv run mypy api workers shared
```

A API fica em `http://localhost:8000`, métricas do worker em
`http://localhost:9100` e o painel RabbitMQ em `http://localhost:15672`.
Use `API_PORT=18000 docker compose up -d` se a porta 8000 estiver ocupada.

## Workflow de desenvolvimento (spec-driven + TDD)

1. **Spec primeiro.** Nenhuma feature entra em código sem uma `SPEC-NNN` aprovada em `docs/specs/`, com critérios de aceitação no formato EARS e plano de testes.
2. **Red.** Escreva os testes derivados dos critérios de aceitação da spec. Todos devem falhar.
3. **Green.** Implemente o mínimo para os testes passarem.
4. **Refactor.** Melhore o design mantendo os testes verdes.
5. **Rastreabilidade.** Cada teste referencia o ID do critério (ex.: `# SPEC-001/AC-03`). Cada PR referencia a spec.
6. **Spec desatualizada = bug.** Se a implementação divergir da spec, atualiza-se a spec ou a implementação — nunca se convive com a divergência.

## Ordem de leitura para novos membros

`00-vision` → `01-requirements` → `02-architecture` → `04-api-spec` → spec da feature em que vai trabalhar.
