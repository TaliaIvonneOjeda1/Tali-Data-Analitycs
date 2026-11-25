# Estructura del informe BI

## Secciones (orden fijo)

| # | Sección | Contenido |
|---|---------|-----------|
| 0 | Portada | Logo, título, período, fecha, tipo (Consultas/ejecutivo), pedido |
| 1 | Pregunta y contexto | `pregunta_negocio`, `audiencia`, decisión esperada |
| 2 | Resumen ejecutivo | 1–3 párrafos; hechos medidos, no marketing |
| 3 | KPIs | Hasta 8–12; cada uno con valor, unidad, contexto/comparación, nota |
| 4 | Evidencia visual | 0–2 gráficos; título-hallazgo; leyenda/unidades claras |
| 5 | Hallazgos | Lista corta: qué se encontró y por qué importa |
| 6 | Conclusiones y próximos pasos | Separar conclusión vs acción sugerida |
| 7 | Limitaciones y supuestos | Solo materiales (máx. ~5); sin duplicar |
| 8 | Glosario | Términos usados (AF, T2, pp, interanual, comparables…) |
| 9 | Anexo | SQL/trazas y cuentas de código |

## Contrato JSON del Redactor

```json
{
  "pedido": "...",
  "titulo": "...",
  "periodo": "T2 AF2026 | AF2025 | …",
  "audiencia": "dirección | operaciones | …",
  "pregunta_negocio": "...",
  "resumen_ejecutivo": "...",
  "indicadores": [
    {
      "nombre": "...",
      "valor": 0,
      "unidad": "ARS|%|pp|unidades",
      "contexto": "vs período anterior / meta",
      "nota": "filtro o definición breve"
    }
  ],
  "grafico": {
    "tipo": "lineas|barras",
    "etiquetas": ["..."],
    "valores": [0],
    "titulo": "Hallazgo con período",
    "ylabel": "...",
    "nombre_archivo": "InformeYYYYMMDD-….png"
  },
  "hallazgos": ["..."],
  "conclusiones": ["..."],
  "proximos_pasos": ["..."],
  "supuestos": ["..."],
  "limitaciones": ["..."],
  "consultas": [{"medida": "...", "filtros": {}, "sql": "..."}],
  "cuentas": ["..."]
}
```

Si no hay gráfico útil: `"grafico": null`.
`proximos_pasos` debe propagarse desde el Analista si el Redactor no los redefine.
`limitaciones` puede fusionarse con `supuestos` en el PDF si una lista viene vacía.

## Lenguaje y gráficos

- Preferir español claro; siglas con significado entre paréntesis o en el glosario.
- Evitar YoY/LFL en el PDF: usar «variación interanual» y «comparables (mismas sucursales)».
- Evolución en el tiempo → `tipo: "lineas"`. Barras solo para categorías en un mismo corte.

## Separación narrativa

- **Dato:** cifra trazable a consulta/cuenta.
- **Interpretación:** qué significa en el negocio (sin inventar causas no evidentes).
- **Recomendación:** próximo paso accionable o verificación pendiente.
