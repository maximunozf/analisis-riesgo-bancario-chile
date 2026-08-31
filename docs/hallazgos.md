# Hallazgos

**Análisis comparativo del riesgo crediticio: retail financiero vs. banca tradicional en Chile**
Datos públicos CMF · 41 meses (ene-2023 a may-2026) · 5 bancos

Todas las cifras de este documento salen de las consultas de [`sql/analisis_riesgo.sql`](../sql/analisis_riesgo.sql)
corridas sobre la base `riesgo_bancario_cmf`. El número entre paréntesis al final de
cada sección indica qué consulta la produce.

---

## Insight central

> **Los dos grupos se movieron en direcciones opuestas.** Entre enero de 2023 y mayo de
> 2026 la morosidad de la banca tradicional subió de 1,70% a 2,23% y su cobertura cayó de
> 1,34 a 1,09. En el mismo periodo el retail financiero bajó su morosidad de 4,87% a 4,24%
> manteniendo la cobertura estable en torno a 1,37.
>
> **La brecha entre ambos se cerró de un máximo de 3,5 puntos porcentuales (mar-2024) a
> 2,0 pp — pero no porque el retail se pareciera a la banca, sino porque la banca se acercó
> al retail.**

La correlación de las dos series mensuales de morosidad es **−0,19** en niveles y **+0,20**
en variaciones mes a mes: prácticamente no hay relación. No es un ciclo de crédito común
moviendo a los cinco bancos a la vez; son dos trayectorias distintas. *(consulta 10)*

---

## Cómo leer estos números (leer antes que los hallazgos)

1. **Son índices porcentuales, no montos.** No se suman segmentos ni bancos. Todo agregado
   de este documento es un promedio, nunca una suma.
2. **Los promedios por grupo son simples, no ponderados.** `AVG()` le da a Banco de Chile
   el mismo peso que a Banco Ripley. Cuando aquí se lee "la morosidad de la banca
   tradicional", debe entenderse "el promedio de las morosidades de sus tres miembros".
   Ponderar por tamaño de cartera exigiría saldos en pesos que estos dos reportes de la CMF
   no entregan.
3. **2026 son cinco meses (ene-may), no un año.** El promedio de un índice no se distorsiona
   por tener menos meses, pero tiene menos evidencia detrás.
4. **La cobertura es una razón aproximada.** Numerador y denominador vienen de reportes
   distintos con denominadores contables equivalentes pero no idénticos
   (ver `limitaciones.md`, sección 11).
5. **Cobertura bajo 1 no es incumplimiento normativo.** La CMF no exige provisiones ≥ mora
   90+. Las garantías reales reducen la provisión exigida, así que una cartera con mucha
   vivienda tiene cobertura estructuralmente baja sin estar sub-provisionada. La cobertura
   sirve para comparar **trayectorias**, no para dictaminar suficiencia.

---

## Hallazgo 1 — El deterioro está en la banca tradicional, no en el retail

Promedio anual del segmento `total_colocaciones`: *(consulta 2)*

| Grupo | Año | Morosidad 90+ | Índice provisiones | Cobertura |
|---|---|---|---|---|
| Banca tradicional | 2023 | 1,70% | 2,24% | **1,34** |
| Banca tradicional | 2024 | 2,14% | 2,29% | 1,12 |
| Banca tradicional | 2025 | 2,18% | 2,37% | 1,13 |
| Banca tradicional | 2026 | **2,23%** | 2,40% | **1,09** |
| Retail financiero | 2023 | 4,87% | 7,01% | **1,45** |
| Retail financiero | 2024 | 5,21% | 7,17% | 1,37 |
| Retail financiero | 2025 | 4,34% | 6,02% | 1,37 |
| Retail financiero | 2026 | **4,24%** | 5,97% | **1,37** |

La banca tradicional acumula **+0,53 pp de morosidad** en el periodo y pierde **0,26 puntos
de cobertura**. Sus provisiones subieron (2,24% → 2,40%), pero más lento que su mora: por
eso la cobertura cae aunque el numerador crezca.

El retail financiero hace lo contrario: **−0,63 pp de morosidad** y cobertura plana. Su
índice de provisiones baja de 7,01% a 5,97%, pero acompañando una cartera que efectivamente
se deterioró menos.

**Lectura:** el ciclo golpeó a quien venía de una base baja. El retail ya operaba con
morosidad estructuralmente alta y con provisiones dimensionadas para eso.

---

## Hallazgo 2 — La brecha se cierra por el lado equivocado

Distancia entre grupos en morosidad: *(consulta 3)*

| Mes | Banca trad. | Retail | Brecha (pp) | Ratio |
|---|---|---|---|---|
| 2023-01 | 1,56% | 4,23% | 2,67 | 2,71× |
| 2024-03 | 1,98% | 5,44% | **3,46** (máx.) | 2,75× |
| 2025-07 | 2,16% | 4,09% | 1,93 (mín.) | 1,89× |
| 2026-05 | 2,16% | 4,12% | 1,96 | **1,91×** |

El ratio pasa de 2,71× a 1,91×. Convergencia real, pero de las dos que existen —que el de
abajo suba o que el de arriba baje— aquí ocurrieron **ambas a la vez**, con el grueso del
movimiento del lado de la banca tradicional en 2024.

Un dashboard que muestre solo "la brecha se redujo" cuenta una buena noticia falsa. Por eso
la portada del dashboard lleva las dos series, no la resta.

---

## Hallazgo 3 — Dos de los tres bancos tradicionales provisionan bajo su propia mora

Cobertura promedio anual por banco: *(consultas 6 y 7)*

| Banco | Grupo | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| BCI | Banca tradicional | 1,19 | **0,93** | **0,94** | **0,92** |
| Santander-Chile | Banca tradicional | 1,27 | **1,01** | 1,04 | 1,06 |
| Banco de Chile | Banca tradicional | 1,58 | 1,40 | 1,39 | 1,29 |
| Falabella | Retail financiero | 1,48 | 1,35 | 1,27 | 1,20 |
| Ripley | Retail financiero | 1,42 | 1,39 | 1,47 | **1,54** |

- **BCI** lleva **25 de 41 meses** con cobertura bajo 1 (desde may-2024, mínimo 0,823).
- **Santander-Chile**, 9 meses bajo 1, todos entre may-2024 y ene-2026 (mínimo 0,905).
- **Ripley es el único banco de los cinco cuya cobertura sube** en el periodo.

Con la advertencia 5 en mano: esto no dice que BCI esté sub-provisionado —dice que la
distancia entre su stock de provisiones y su cartera morosa se dio vuelta a mediados de
2024 y no volvió. Es la pregunta que este análisis deja planteada, no una conclusión sobre
suficiencia.

---

## Hallazgo 4 — En consumo, el retail casi alcanzó a la banca

El segmento más comparable entre los dos modelos de negocio: *(consulta 5)*

| Año | Mora consumo — banca trad. | Mora consumo — retail | Brecha |
|---|---|---|---|
| 2023 | 2,16% | 4,04% | 1,88 pp |
| 2024 | 2,28% | 3,68% | 1,40 pp |
| 2025 | 2,14% | 2,47% | 0,33 pp |
| 2026 | 2,22% | **2,54%** | **0,32 pp** |

La morosidad de consumo del retail cayó **1,51 pp** mientras la de la banca se mantuvo
plana. Su cobertura de consumo subió de 2,44 a 3,07, acercándose a la de la banca (3,27).

Este es el hallazgo que más contradice la intuición de partida: **en su propio negocio
—el crédito de consumo— el retail financiero cerró casi por completo la distancia.** La
brecha del total que se ve en el Hallazgo 2 ya no viene de consumo.

---

## Hallazgo 5 — De dónde viene entonces cada brecha

Descomponiendo por segmento (promedio 2026): *(consulta 5)*

| Segmento | Mora banca trad. | Mora retail | Cobertura banca trad. | Cobertura retail |
|---|---|---|---|---|
| Comerciales | 2,34% | **11,76%** | 1,09 | **0,34** |
| Consumo | 2,22% | 2,54% | 3,27 | 3,07 |
| Vivienda | 2,19% | **15,97%** | 0,31 | **0,06** |
| Personas (total) | 2,20% | 4,15% | 1,07 | 1,41 |

Dos advertencias que hacen que estas dos filas extremas **no** deban leerse como riesgo
comparable (ambas documentadas en `limitaciones.md`, secciones 7-8):

- **Vivienda del retail** es cartera residual: Ripley dejó de originar hipotecarios y lo que
  queda es la cola morosa de una cartera que ya no se renueva, con garantía real detrás.
  Morosidad de 16% con provisiones de 0,45% es exactamente lo que se ve cuando el
  denominador se achica y la garantía cubre. **No promediar vivienda entre grupos.**
- **Comerciales del retail**: la mora se mantiene sobre 11% mientras las provisiones caen de
  8,0% a 2,9% en tres años. Una caída de provisiones sin caída de mora apunta a un evento
  contable (venta o castigo de cartera), no a una mejora de riesgo.

El deterioro de la banca tradicional, en cambio, es parejo y está en **personas**: mora de
1,40% a 2,20% y cobertura de 1,53 a 1,07, con vivienda subiendo de 1,16% a 2,19%. Ahí está
el movimiento real del periodo.

---

## Hallazgo 6 — Quién se movió más

Rango entre el peor y el mejor mes de cada banco: *(consultas 4 y 8)*

| Banco | Mora mín. | Mora máx. | Rango | Δ punta a punta |
|---|---|---|---|---|
| Ripley | 4,84% (2025-07) | 7,06% (2024-05) | **2,22 pp** | −0,04 pp |
| Santander-Chile | 1,82% (2023-03) | 3,28% (2026-01) | 1,46 pp | **+1,01 pp** |
| Falabella | 3,18% (2025-09) | 4,16% (2023-06) | 0,98 pp | −0,18 pp |
| BCI | 1,55% (2023-03) | 2,38% (2024-09) | 0,83 pp | +0,29 pp |
| Banco de Chile | 1,13% (2023-01) | 1,66% (2025-12) | 0,54 pp | +0,50 pp |

Ripley es el más volátil pero termina donde empezó: su pico de may-2024 se revirtió por
completo. Santander-Chile es el caso opuesto —menos volátil, pero su máximo es el mes más
reciente de la serie—: no es ruido, es tendencia.

Falabella merece un matiz que el titular esconde: **bajó la mora y aun así perdió cobertura**
(1,48 → 1,20), porque redujo provisiones más rápido de lo que mejoró la cartera.

---

## Lo que estos datos no permiten afirmar

- **No es "el sistema bancario chileno".** Son 5 bancos de ~17 instituciones. Las
  conclusiones valen para estas cinco entidades.
- **No hay causalidad.** Los datos muestran trayectorias divergentes; no dicen si se deben a
  política de originación, a composición de cartera, a castigos o al ciclo macro.
- **No hay ponderación por tamaño.** Un promedio simple entre Banco de Chile y BCI no es la
  morosidad de la banca tradicional chilena.
- **No hay saldos en pesos.** Todo el análisis está en índices; ningún resultado puede
  expresarse en monto de cartera morosa.
- **La cobertura no mide suficiencia de provisiones.** Ver advertencia 5.

---

## Qué pasa al dashboard (Días 9-11)

| Página | Contenido | Fuente |
|---|---|---|
| **Portada — el insight** | Las dos series de morosidad en un solo gráfico + tarjetas de cobertura por grupo. El texto del hallazgo, visible. | consultas 2 y 3 |
| **Evolución y bancos** | Serie mensual por banco, variación mes a mes, pico/piso, meses bajo cobertura 1. | consultas 1, 7, 8, 9 |
| **Segmentos** | Mora y cobertura por segmento con `nivel_agregacion` como filtro, más las dos advertencias de datos en la propia página. | consulta 5 |

Regla para el dashboard: **la nota sobre promedios simples y sobre índices-no-montos va
impresa en la portada**, no escondida en un tooltip.
