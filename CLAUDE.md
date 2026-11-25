# CLAUDE.md

Contexto para quien trabaja este repo. Setup y comandos de producto están en el README. Acá van invariantes que no se adivinan leyendo un archivo suelto.

## Cómo correr

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
$env:PYTHONIOENCODING='utf-8'
pip install -r requirements.txt
```

- Producto: `python scripts\serve_api.py` + `cd web && npm run dev` → http://127.0.0.1:5173 (API en :8000).
- Tests sin API: `pytest tests -q`.
- Una pregunta: `python scripts\ask.py --id P01`. Un informe: `python scripts\informe.py --id I1`.

La key va en `.env` (`ANTHROPIC_API_KEY`). Si falta, `src.config` también mira el `.env` del directorio padre. No commitear `.env`. La key de Anthropic no viaja al browser: el front habla con la API y la API valida `ANALISTA_API_TOKEN`.

## Convenciones en el código

- Modelo por defecto: `claude-haiku-5-5`.
- Toda tool vive en `src/tools/registry.py`. `src/mcp_server` solo la envuelve. El loop y los evals llaman las mismas funciones in-process.
- Medidas por `consultar_medida` y `data/capa_semantica/medidas.yaml`. `ejecutar_sql_readonly` es para huecos, no para rearmar ventas o margen.
- Variaciones, desvíos, participaciones y gráficos se calculan en código (`src/semantic/accounting.py`, `src/reporting/`). El modelo no resta ni divide.
- Puntual, comparativa y ranking: un agente. Diagnóstico e informe: investigador → analista → redactor. El analista no tiene tools.
- Lo que «tiene que pasar siempre» está en `src/agent/hooks.py` (solo SELECT, traza, número no trazado no sale).
- Registro de respuesta o informe: validar con Pydantic antes de guardar.
- Prefijo de prompt cache: system y glosario estables (sin fecha, UUID ni turno del usuario).
- Informes PDF: skill `.agents/skills/informe-bi/` alinea estructura, visualización y QA.
- Si DBeaver tiene abierta la base, DuckDB no comparte el archivo: `db.connect()` cae a `almacenes_del_sur.ro.duckdb`.

## Decisiones que no hay que revertir

Los datos no se vuelcan al prompt: la base entra por tools. Un número sin traza no es una respuesta. Ante ambigüedad se declara el supuesto o se pide aclaración. Si el dato no existe, se dice que no existe.
