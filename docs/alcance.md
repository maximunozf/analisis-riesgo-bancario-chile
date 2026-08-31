# Alcance del proyecto: análisis comparativo de riesgo crediticio (2023-2026)

## 1. Pregunta de negocio

¿Existe una diferencia significativa en la evolución y velocidad de deterioro del riesgo
crediticio entre el retail financiero y la banca tradicional en Chile? Y, en particular,
¿difieren en cuánto se cubren frente a la cartera que ya se deterioró?

**Indicador central:** el índice de cobertura (provisiones / cartera morosa). Dos bancos
con la misma morosidad pueden tener posturas de riesgo opuestas según cuánto provisionen,
y es esa brecha —no la morosidad por sí sola— la que distingue los dos modelos de negocio.

## 2. Entidades analizadas

El análisis se restringe a **5 instituciones**, elegidas para contrastar ambos modelos:

| Banco | Grupo |
|---|---|
| Banco Falabella | Retail financiero |
| Banco Ripley | Retail financiero |
| Banco de Chile | Banca tradicional |
| Banco de Crédito e Inversiones (BCI) | Banca tradicional |
| Banco Santander-Chile | Banca tradicional |

**Tenpo quedó fuera del alcance.** Estaba en la definición original, pero no está regulado
como banco ante la CMF (opera como emisor de tarjeta de prepago) y por lo tanto no aparece
en ninguno de los dos reportes fuente. Incluirlo habría sido imposible, no una decisión de
diseño.

## 3. Horizonte temporal

- **Rango:** enero 2023 – mayo 2026. **41 meses.**
- **Frecuencia:** mensual.

**Regla de cierre del período:** la serie termina en el último mes en que *ambos* reportes
están publicados. La CMF publica provisiones aproximadamente un mes después que morosidad;
al momento de la descarga, morosidad llegaba a junio 2026 y provisiones a mayo 2026. Como
el índice de cobertura exige las dos fuentes del mismo mes, un mes con una sola fuente no
produce el indicador, y una serie que termine en distinto mes según la métrica rompe la
comparabilidad del dashboard. Por eso el corte es mayo 2026.

*Justificación del rango:* el período captura el ciclo post-pandemia, la estabilización de
tasas y el comportamiento de pago del consumidor frente a las presiones inflacionarias
recientes.

## 4. Fuentes de datos

Datos de acceso público de la Comisión para el Mercado Financiero (CMF) de Chile:

1. **Indicador de morosidad de 90 días o más** (individual), desagregado por banco y
   segmento de cartera.
2. **Indicadores de Provisiones por Riesgo de Crédito**, con el mismo nivel de
   granularidad.

Ambos se obtienen con `scripts/descargar_cmf.py`, que scrapea la página índice de cada
reporte y descarga los Excel mensuales. **La descarga es reproducible, no manual:** los
archivos crudos no se versionan en el repositorio, así que el script es lo que permite a
cualquiera reconstruir el dataset completo desde cero.

## 5. Segmentos de cartera

Ambos reportes comparten la misma estructura de columnas, lo que permite compararlos
directamente: Total, Colocaciones comerciales, Colocaciones a personas (Total, Consumo,
Vivienda) y Adeudado por bancos.

## 6. Alcance del entregable

- Análisis **descriptivo e histórico**. Queda explícitamente fuera de esta iteración el
  modelamiento predictivo.
- Entregables: CSV consolidado, modelo relacional en MySQL, consultas SQL de análisis y un
  dashboard de Power BI de 3 páginas.

Las limitaciones de interpretación —qué no se puede concluir a partir de este análisis—
están en [`limitaciones.md`](limitaciones.md).
