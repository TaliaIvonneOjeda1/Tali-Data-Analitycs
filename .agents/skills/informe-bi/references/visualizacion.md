# Visualización para informes TaliAnalytics

## Principios

- Informe **explicativo**: un mensaje por gráfico.
- Reducir carga cognitiva: título claro, orden, poco color decorativo.
- Jerarquía: KPIs arriba → evidencia → detalle en anexo.
- Paleta: positivo/categoría `#2457d6`, negativo `#b91c1c`, eje/texto `#101a2f` / `#475569`.

## Tipo de gráfico

| Pregunta | Tipo |
|----------|------|
| Comparar categorías (regiones, productos) en un mismo corte | Barras |
| Evolución en el tiempo (meses, trimestres, años) | **Líneas** (orden cronológico). No usar barras: se ven homogéneas y ocultan la tendencia |
| Composición de un total (pocas partes) | Circular solo si aplica; preferir barras |
| Valores exactos / varias métricas | Tabla breve en hallazgos o anexo |

Hoy el runtime soporta **barras** y **líneas** vía `charts.py`.

## Barras

- Eje de valor desde **0** (salvo desvíos con negativos: entonces línea en 0 y barras horizontales).
- Ordenar categorías de mayor a menor cuando no hay orden natural.
- Nombres largos → barras horizontales.
- Título con período y unidad implícita o en ylabel.

## Líneas

- Obligatorio para series temporales ordenadas (evolución / cambio en el tiempo).
- No usar para categorías nominales (ahí van barras).
- Preferir líneas también cuando hay 2–3 períodos a comparar (ej. T2 AF2025 vs T2 AF2026 + contexto): si el eje es tiempo, líneas.

## Títulos

- Mal: “Ventas”, “Gráfico 1”.
- Bien: “Ventas netas por región — AF2025 (ARS)”.
- Mejor: título-hallazgo si el dato lo sostiene (“La región Sur lidera el AF2025”).

## Qué evitar

- 3D, sombras, fondos recargados, demasiados colores.
- Escalas engañosas.
- Más de 2 gráficos por informe salvo pedido compuesto justificado.
- Depender solo del color (siempre etiqueta o valor).
