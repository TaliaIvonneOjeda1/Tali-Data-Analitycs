# TaliAnalytics

Agente analítico que responde preguntas de negocio en lenguaje natural, mantiene conversación con contexto y genera **informes ejecutivos en PDF** — con traza de cada cifra (medida, filtros, SQL o cuenta).

Datos de demo: base comercial ficticia **Almacenes del Sur** (DuckDB, solo lectura).

## Qué incluye

- Preguntas puntuales, comparativas, rankings y diagnósticos
- Chat con herencia de período / filtros / medida
- Informes PDF con KPIs, gráfico y anexo de consultas
- API + UI web para uso de producto

## Stack

| Capa | Tecnología |
|------|------------|
| Modelo | Anthropic Claude (`claude-haiku-5-5`) |
| Backend | Python · FastAPI · agent loop + multiagente |
| Datos | DuckDB (MCP / tools) · capa semántica YAML |
| Front | React · Vite · TypeScript |
| Informes | ReportLab · Matplotlib |
| Guardrails | Hooks (SQL readonly, traza, budgets) |

Diagrama de arquitectura: [`.archify/.../taligent-arquitectura.html`](.archify/architecture-taligent-analista-20261117-203940/taligent-arquitectura.html)

## Cómo levantarlo

```bash
# 1. Dependencias
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 2. Secretos (nunca subir .env)
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux
# Completar ANTHROPIC_API_KEY

# 3. API (terminal 1)
python scripts/serve_api.py     # http://127.0.0.1:8000

# 4. UI (terminal 2)
cd web
npm install
copy .env.example .env          # token de demo alineado con la API
npm run dev                     # http://127.0.0.1:5173
```

Tests sin gastar tokens: `pytest tests -q`

## Estructura

```text
src/           # API, agente, tools/MCP, semántica, reporting, seguridad
web/           # Frontend React
data/          # DuckDB + medidas + glosario + preguntas demo
scripts/       # serve_api, ask, chat, informe, diagnostico
tests/         # Tests automatizados
.agents/       # Skill de informes BI
.archify/      # Diagrama de arquitectura (HTML)
```

## Seguridad (breve)

- `.env` está ignorado; la key de Anthropic **no** viaja al browser
- El front usa `ANALISTA_API_TOKEN` / `VITE_ANALISTA_API_TOKEN` (cambiar en producción)
- DuckDB solo lectura · rate limit y budgets en API · respuestas filtradas para el cliente

## Licencia / origen de datos

Datos sintéticos de campamento de en inteligencia artificial de mano de Taligent. Uso demostrativo.
