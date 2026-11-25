---
name: informe-bi
description: >-
  Produce and review professional BI executive PDFs for TaliAnalytics with logo,
  narrative structure, KPIs with context, visualization rules, and SQL traceability.
  Use when improving or regenerating informes, editing pdf_report/charts/Redactor
  prompts, reviewing PDF quality, or aligning output to BI consulting practices.
---

# Informe BI (TaliAnalytics)

Guía para informes PDF del producto. El runtime (`src/reporting/pdf_report.py`) debe cumplir esta estructura; esta skill alinea prompts, QA y cambios de código.

## Cuándo aplicar

- Mejorar, regenerar o revisar un informe PDF.
- Cambiar Redactor, `pdf_report.py`, `charts.py` o naming de archivos.
- Calibrar storytelling / visualización con material de BI.

## Nombres de archivo

| Origen | Archivo |
|--------|---------|
| Consulta libre / sesión | `InformeYYYYMMDD-Consultas.pdf` |
| Predefinidos I1–I3 | `InformeYYYYMMDD-ejecutivo.pdf` |

Helper: `src/reporting/names.py`.

## Estructura obligatoria del PDF

1. Portada: logo TaliAnalytics, título, período, fecha, pedido.
2. Pregunta y contexto (audiencia + decisión esperada).
3. Resumen ejecutivo (síntesis breve).
4. KPIs con contexto (período / comparación / nota; no métricas sueltas).
5. Evidencia visual (1 gráfico útil; título-hallazgo).
6. Hallazgos e interpretación (dato ≠ interpretación).
7. Conclusiones y próximos pasos.
8. Limitaciones y supuestos.
9. Glosario de términos.
10. Anexo — consultas SQL y cuentas.

Lenguaje: español claro; siglas con significado entre paréntesis o en el glosario.

Detalle: [references/estructura-informe.md](references/estructura-informe.md).

## Reglas de oro (clases BI 1–16)

1. Primero la pregunta de negocio; el gráfico sirve a esa pregunta.
2. Informe **explicativo** (hallazgo guiado), no dashboard exploratorio.
3. Narrativa: contexto → pregunta → hallazgo → evidencia → interpretación → recomendación.
4. Jerarquía: KPIs → gráficos → detalle/anexo.
5. Simplicidad: sin 3D, sombras ni decoración.
6. Títulos específicos (qué + período); preferible título-hallazgo.
7. Barras con eje desde 0; orden mayor→menor si es categórico.
8. Tipo correcto: **líneas si hay cambio en el tiempo**; barras solo para categorías en un mismo corte.
9. Color con significado y consistente (paleta TaliAnalytics).
10. KPI ≠ métrica: objetivo, período, comparable, accionable.
11. Consistencia de nombres, monedas y fechas en todo el PDF.
12. Menos es más: cada gráfico una función.
13. Conclusiones con evidencia; no inventar cifras.
14. Adaptar profundidad a la audiencia sin alterar datos.
15. Calidad de datos antes de visualizar; declarar limitaciones.
16. Minimización PII: agregados, no listar clientes individuales.

Visualización: [references/visualizacion.md](references/visualizacion.md).

## Branding

- Logo: `src/reporting/assets/taligent-logo.png`
- Colores UI: navy `#101a2f`, accent `#2457d6`, meta `#475569`
- Footer: “TaliAnalytics · Confidencial — uso interno” + nº de página

## Anti-patrones

- Volcar todas las métricas sin pregunta.
- Títulos genéricos (“Ventas”, “Gráfico 1”).
- Ocultar limitaciones o LFL incompleto.
- Inventar nulos / sustituir indicadores faltantes.
- PDF sin logo / sin próximos pasos cuando el Analista los aportó.
- Tortas para series temporales; ejes de barras que no parten de 0.

## Flujo de trabajo del agente

1. Leer [estructura-informe.md](references/estructura-informe.md) y el contrato JSON del Redactor.
2. Si tocás código: alinear `SYSTEM_REDACTOR`, `build_pdf` y charts a esa plantilla.
3. Antes de dar por cerrado: [checklist-qa.md](references/checklist-qa.md).
4. Verificar nombre `InformeYYYYMMDD-Consultas|ejecutivo.pdf`.
