# Validación cruzada del dashboard

> **Objetivo:** probar que cada cifra visible en `dashboard/Proyecto CMF.pbix` sale de los mismos
> datos y da el mismo número que la fuente. Si un visual y su consulta discrepan, o la medida DAX
> está mal escrita, o el visual arrastra un filtro que no debería tener.

Esto no es prolijidad. Una medida DAX mal escrita **no da ningún mensaje de error**: devuelve un
número plausible y silenciosamente falso. Los tres primeros defectos de la sección 5 son
exactamente eso — los tres se veían bien en pantalla. El cuarto es del control mismo.

---

## 1. Decisión de método: validación selectiva, no fuerza bruta

El plan original de este día era exportar a CSV los 9 visuales del informe y los 6 resultados de
`sql/analisis_riesgo.sql`, y comparar los 15 archivos con un script. **Se descartó.**

La razón: el costo de una validación no es igual en todos los visuales, y el riesgo tampoco.

| Tipo de visual | Cuántos valores muestra | Cómo se valida |
|---|---|---|
| Tarjeta KPI | 1–2 | Lectura directa contra la consulta. El ojo no se equivoca con dos números. |
| Ranking de barras | 5 | Lectura directa, uno a uno. |
| Serie de 41 meses × 5 bancos | 205 | Export + comparación por script. Acá el ojo sí se equivoca. |

Exportar 15 CSV para comparar 2 valores es ceremonia, no control. La regla que se aplicó:
**se compara a mano lo que el ojo puede sostener y por script lo que no.** Los extremos de las
series largas (primer mes, último mes, mínimo) se validan a mano; el resto de la serie, por script.

> **Respuesta de entrevista.** *"Validé el dashboard contra la fuente eligiendo el método por
> visual: lo que muestra 2 o 5 valores lo comparé directo contra el SQL, y lo que muestra 200 lo
> comparé con un script. Validar 200 números a ojo y validar 2 con un pipeline son las dos formas
> de que la validación no sirva."*

**Regla de tolerancia.** Las medidas DAX están formateadas a 2 decimales y el SQL redondea a 3.
Una fila cuadra si `round(fuente, 2) == pantalla`. Cualquier diferencia mayor a 0,01 es un defecto
real: se explica, no se redondea.

---

## 2. Qué se validó, página por página

### Portada

| Cifra en pantalla | Valor | Fuente | Resultado |
|---|---|---|---|
| KPI cobertura retail · 2026 | 1,37 | `AVG(cobertura)` retail, `total_colocaciones`, 2026 (10 filas, sin nulos) | ✅ |
| KPI cobertura banca tradicional · 2026 | 1,09 | ídem banca (15 filas) | ✅ |
| Líneas de cobertura por grupo | 41 meses × 2 series | consulta 3 | ✅ por script |

### Comparativo — los 15 valores, uno a uno

Los tres gráficos de barras muestran 5 bancos × 3 medidas. Se cruzaron **los 15** contra
`data/processed/consolidado_cmf.csv` con `scripts/validar_dashboard.py`:

| Banco | Mora 90+ may-2026 | Cobertura may-2026 | Δ cobertura ene-2023 → may-2026 |
|---|---|---|---|
| Banco Ripley | 4,91 % ✅ | 1,60 ✅ | +0,13 ✅ |
| Banco Falabella | 3,33 % ✅ | 1,18 ✅ | −0,48 ✅ |
| Banco Santander-Chile | 2,95 % ✅ | 1,07 ✅ | −0,25 ✅ |
| BCI | 1,90 % ✅ | 0,90 ✅ | −0,32 ✅ |
| Banco de Chile | 1,63 % ✅ | 1,29 ✅ | −0,53 ✅ |

**15 de 15 cuadran.** Las dos cifras del cuadro de hallazgo de esa página también se verificaron
contra los datos, porque están escritas a mano en un cuadro de texto y ningún control automático
las cubre:

- *"BCI: 25 de 41 meses bajo 1"* → 25 ✅ (Santander-Chile, 9 ✅; el resto, ninguno)
- *"Ripley es el único que reforzó su cobertura desde 2023"* → único Δ positivo de los cinco ✅
- *"Ripley lidera la cobertura desde may-2025"* → 13 meses consecutivos como máximo de los cinco ✅

### Segmentación

Esta página convive con **dos bases de cálculo** y hay que decir cuál es cuál: el gráfico de
brechas termina en el **último mes publicado**, y el cuadro de texto cita **promedios anuales**.
La brecha de consumo es 0,36 pp en may-2026 y 0,32 pp en promedio 2026: las dos ciertas. Comparar
una contra la otra hace ver un defecto donde solo hay dos preguntas distintas.

| Cifra en pantalla | Base | Valor | Resultado |
|---|---|---|---|
| Mora consumo retail · 2023 → 2026 (cuadro de texto) | promedio anual | 4,04 % → 2,54 % | ✅ |
| Mora consumo banca · 2023 → 2026 (cuadro de texto) | promedio anual | 2,16 % → 2,22 % | ✅ |
| Brecha comerciales · último punto del gráfico | may-2026 | 11,62 pp | ✅ |
| Brecha consumo · último punto del gráfico | may-2026 | 0,36 pp | ✅ |
| Brecha vivienda · último punto del gráfico | may-2026 | 13,68 pp | ✅ |
| Series de brecha y de morosidad por cartera | 41 meses | 3 carteras × 2 grupos | ✅ por script |

### Los cuadros de texto de Portada y Segmentación

Un cuadro de texto envejece igual que una medida: se escribe a mano, se edita a mano y ningún
control de Power BI lo recalcula. En la página `Comparativo` esas cifras ya se verificaban una a
una; en las otras dos no, y son 16.

| Cuadro de texto | Base | Cifras | Resultado |
|---|---|---|---|
| Portada · mora y cobertura por grupo, 2023 → 2026 | promedio anual | 8 | ✅ |
| Segmentación · brechas de consumo, vivienda y del total | promedio anual | 6 | ✅ |
| Segmentación · brecha de comerciales, citada como rango "~9-11" | promedio anual | 2 | ✅ 9,42 – 11,06 |

La de comerciales se valida distinto porque el informe no cita un valor sino un rango: lo que se
comprueba es que los dos extremos de la serie anual sigan cayendo dentro de él. Y las cifras que el
informe escribe con un decimal (7,2 · 13,8) se comparan con un decimal: exigirle dos a un número
redondeado a uno marcaría un defecto inexistente.

---

## 3. Control de grano previo

Antes de comparar una sola cifra se corre la **consulta 0** sobre la base. Debe devolver:

```
2460 filas · 41 meses · 5 bancos · 6 segmentos · 2 indicadores · 164 nulos · suma 8465,7966
```

Si no da eso, la base cambió desde la última carga y el resto de la validación sobra: se para y
se recarga. Validar contra una base distinta a la que alimentó el `.pbix` da falsos positivos.

---

## 4. Cómo reproducir esta validación

```bash
python scripts/validar_dashboard.py
```

El script recalcula desde `data/processed/consolidado_cmf.csv` las **44 cifras** del informe —15
del ranking de `Comparativo`, 2 KPI y 8 del cuadro de texto de la portada, 7 de segmentación, 8 de
su cuadro de texto y 4 del cuadro de hallazgo— y las compara contra los valores escritos en
pantalla, cada una contra su propia base. Devuelve código de salida distinto de 0 si alguna no
cuadra, así que sirve como chequeo antes de publicar una versión nueva del informe.

Deliberadamente **no** lee MySQL: valida contra el CSV consolidado, que es el archivo del que
también se alimenta el `.pbix`. Cruzar el dashboard contra la misma base que lo alimenta prueba
que la capa DAX no deformó el dato — que es lo que este control busca.

---

## 5. Defectos que esta validación encontró (y que en pantalla no se veían)

**1 · La medida de variación devolvía el valor inicial con signo negativo.**
`Variación de cobertura desde el inicio` derivaba el último mes con `MAX(dim_calendario[fecha])`.
El calendario DAX se extiende más allá de la última publicación de la CMF, así que ahí la
cobertura es `BLANK` y la resta quedaba `0 − cobertura_inicial`. En pantalla salían valores de
−1,23 a −1,82: cinco barras plausibles, todas mal. Corregido derivando el primer y último mes
**de los meses con dato**, no del rango del calendario — espejo del `MAX(id_tiempo)` del SQL.

> *La tabla calendario es más larga que la serie publicada; el último mes hay que derivarlo del
> dato, no del calendario.*

**2 · El promedio de cobertura se calculaba como razón de promedios.**
`DIVIDE(SUM(provisiones), SUM(morosidad))` en vez de `AVERAGE(indice_cobertura)`. Promedio de
razones ≠ razón de promedios: para la banca tradicional en 2023 la primera forma da 1,31 y la
correcta 1,34. La diferencia es chica y por eso es peligrosa — pasa por error de redondeo.

**3 · Las medidas sin filtro de segmento mezclaban el total con sus propias partes.**
La vista trae los seis niveles de cartera; un `AVERAGE` sin `CALCULATE(..., codigo_segmento =
"total_colocaciones")` promediaba el total junto a comerciales, consumo y vivienda. El retail daba
6,86 % de morosidad en vez de 4,87 % porque la vivienda residual de Ripley arrastraba el promedio.

**4 · El propio control tenía un punto ciego: los cuadros de texto.** La primera versión validaba
28 cifras y ninguna era de los cuadros de texto de Portada y Segmentación, que citan promedios
anuales. Peor: la tabla de esta sección rotulaba "cifra en pantalla" a las brechas del último mes,
que **no** son las que están escritas en la página. Cualquiera que comparara este documento con la
captura veía 0,36 donde la página dice 0,32 y concluía que la validación fallaba. No había error de
cálculo —las dos cifras son correctas— sino un rótulo que ocultaba que eran dos bases distintas.
Corregido declarando la base de cada cifra y sumando las 16 de los cuadros de texto al script.

> *Un número correcto con la base mal rotulada es indistinguible de un número mal calculado, para
> quien lo lee desde afuera.*

---

## 6. Lo que esta validación **no** cubre

- **No valida la fuente.** Prueba que el dashboard dice lo mismo que el CSV consolidado; que el
  CSV diga lo mismo que los Excel de la CMF lo prueban los controles de
  `scripts/consolidar_datos_cmf.py` y `scripts/verificar_inventario.py`, no este documento.
- **No valida el diseño.** Que un número sea correcto no significa que el visual lo comunique
  bien. Las decisiones de diseño están en el README.
- **No valida los textos interpretativos.** Los cuadros de texto llevan lectura del analista, no
  cifras derivadas; lo único verificable de ellos son los números que citan, y esos están en la
  sección 2.
