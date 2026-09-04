# Limitaciones conocidas

Este documento registra lo que este análisis **no** puede afirmar, y las decisiones que
recortaron deliberadamente su alcance. Está escrito para que quien lea los resultados
sepa dónde están los bordes.

## 1. La muestra no es el sistema bancario chileno

El análisis cubre **5 bancos**, no el sistema completo. Fueron elegidos para contrastar
dos modelos de negocio —retail financiero contra banca tradicional— y no constituyen una
muestra estadísticamente representativa del sistema. Cualquier conclusión aplica a estas
cinco instituciones, no a "la banca chilena".

Consecuencia práctica: los promedios por grupo (2 bancos contra 3) son sensibles al
comportamiento de cualquiera de sus integrantes. Un movimiento fuerte de un solo banco
mueve el promedio de su grupo.

## 2. El período se recorta por el calendario de publicación de la CMF

La CMF publica los dos reportes con desfase: al momento de la descarga, morosidad llegaba
a **junio 2026** y provisiones a **mayo 2026**.

Como el índice de cobertura (provisiones / cartera morosa) exige ambas fuentes del mismo
mes, la serie cierra en **mayo 2026 (41 meses)**. El archivo
`data/raw/morosidad/2026-06.xlsx` se conserva —la regla del proyecto es nunca borrar ni
modificar `data/raw`— pero queda **fuera del consolidado** mediante un filtro explícito
`periodo <= 2026-05`.

Se prefirió una serie más corta y simétrica antes que una serie más larga con un mes
final donde el KPI central no existe.

## 3. Datos declarados, no auditados

Las cifras son las que cada banco reporta a la CMF bajo el Compendio de Normas Contables.
Este análisis no las audita ni las reconstruye desde estados financieros. Diferencias en
políticas internas de provisionamiento entre instituciones son parte de lo que el análisis
observa, no un sesgo que corrija.

## 4. Análisis descriptivo, no causal ni predictivo

Se describe **qué** pasó con la morosidad, las provisiones y la cobertura, y **cómo** se
diferencian los dos grupos. No se modelan las causas (tasas, desempleo, inflación,
cambios regulatorios) ni se proyectan valores futuros. Una correlación observada entre
grupos no implica que el modelo de negocio la cause.

## 5. Cambios de estructura en las fuentes

Detectados en el perfilamiento (ver [`perfilamiento.md`](perfilamiento.md)) y verificados
al descargar la serie completa:

- **Provisiones cambia de formato en enero 2024**: los archivos de 2023 pesan ~478 KB y
  desde `2024-01` bajan a ~330 KB.
- **Morosidad presenta tres escalones de tamaño**: ~40 KB (ene-feb 2023), ~51 KB
  (mar 2023 – dic 2025), ~42 KB (desde ene 2026).
- **La lista de instituciones no es estática**: Banco Security desaparece en noviembre
  2025 (fusión con Banco Bice); Tanner Banco Digital aparece ese mismo mes; Itaú Corpbanca
  cambia de razón social entre 2023 y 2024.

Ninguno de estos cambios afecta a los 5 bancos de alcance, y el script los ubica por
nombre y nunca por número de fila. Aun así quedan registrados: si en algún momento el
consolidado arroja valores inesperados, estos son los primeros puntos a revisar.

## 6. Los datos crudos no se versionan

`data/raw/` está en `.gitignore`. Son ~30 MB de Excel que cualquiera puede regenerar con
`scripts/descargar_cmf.py`. La contrapartida honesta es que **el repositorio depende de
que el portal de la CMF siga en línea y mantenga su estructura**. Si la CMF reorganiza sus
URLs, el script de descarga necesitará ajustes; el análisis ya realizado no se pierde,
pero la reproducción desde cero sí se vería afectada.

## 7. Resultado de la validación de completitud (Día 4)

El consolidado se validó contra la matriz esperada antes de darlo por bueno. **Esta tabla no
está escrita a mano: es la salida de `validar_completitud()` y `validar_calidad()` dentro de
`scripts/consolidar_datos_cmf.py`**, y se reproduce corriendo el script.

| Chequeo | Resultado | Quién lo produce |
|---|---|---|
| Filas | **2.460** = 5 bancos × 41 meses × 6 segmentos × 2 indicadores | `validar_completitud()` |
| Duplicados de clave (`periodo`+`banco`+`indicador`+`segmento`) | 0 | `validar_calidad()` |
| Meses continuos entre ene-2023 y may-2026 | sí, sin huecos (41 meses) | `validar_calidad()` |
| Valores negativos o superiores a 100% | 0 | `validar_calidad()` |
| Nulos | 164, **todos estructurales** (ver sección 8) | `validar_completitud()` |
| Cobertura de meses entre ambos indicadores | idéntica | `validar_completitud()` |

La distinción importa: una tabla de calidad escrita a mano en un documento afirma; una que
sale del script se puede volver a correr y contradecir. Con `--estricto` los tres chequeos de
calidad devuelven código de salida 1 si fallan, de modo que el CSV no puede avanzar hacia
MySQL ni al dashboard con un duplicado o un hueco adentro.

Dos errores encontrados y corregidos en esta etapa, ambos silenciosos:

- **Los índices de columna estaban corridos en los dos reportes.** Provisiones abre con
  una columna extra (`Índice Provisiones s/ Colocaciones — Banco`) antes del desglose, de
  modo que sus segmentos van corridos +1 respecto de morosidad. Usar un único mapa para
  ambos reportes habría producido un CSV que **no falla, se publica**: `comerciales`
  guardado como `total`, `consumo` como `personas`. Ahora hay un mapa por reporte,
  verificado contra 6 archivos reales repartidos a ambos lados de los dos cambios de
  formato conocidos.
- **La hoja de provisiones se llama `"CUADRO N°1 "`, con un espacio final.** El script ya
  no exige coincidencia exacta: resuelve el nombre de hoja comparando en forma
  normalizada, lo que además lo hace tolerante a mayúsculas y tildes.

El primero de esos dos errores dejó una lección que ya no depende de que alguien la recuerde:
**si la CMF vuelve a insertar una columna, el script se detiene solo.** Cada índice de
columna declara ahora el token que debe aparecer en su encabezado
(`TOKENS_ENCABEZADO_MOROSIDAD` / `TOKENS_ENCABEZADO_PROVISIONES`), y antes de leer un solo
valor se confirma que la columna sea la que dice ser. Si no lo es, el proceso aborta con
código de salida 1 y nombra la columna que se corrió, en vez de escribir un CSV de números
plausibles y falsos. El bloque de encabezado se delimita solo —es todo lo que está por
encima de la primera fila de banco—, así que el control no reintroduce la dependencia de un
número fijo de filas que el Hallazgo #3 había eliminado.

Queda una advertencia honesta sobre el alcance de estos controles: verifican que el CSV sea
internamente consistente y que las columnas sean las que dicen ser, no que cada valor sea el
que la CMF publicó. Ese segundo tramo lo cubre `scripts/verificar_muestra.py`, que reabre los
Excel originales y compara celdas elegidas al azar contra el CSV —los nulos incluidos—, pero
lo hace **sobre una muestra**, no sobre las 2.460 celdas. Detecta lo que importa (un mapa de
columnas corrido o un archivo asignado al mes equivocado afectan filas enteras) y no puede
descartar un error aislado en una celda que la muestra no tocó.

## 8. El segmento "adeudado por bancos" no es analizable

- En **morosidad** vale exactamente `0,00` en los 41 meses para los tres bancos
  tradicionales, y viene como `---` (dato ausente) en Falabella y Ripley, que no operan
  ese segmento. De ahí salen los 164 nulos: 2 bancos × 41 meses × 2 indicadores.
- En **provisiones** se mueve en un rango de 0,04% a 0,24%, órdenes de magnitud por debajo
  del resto.

Decisión: el segmento **se conserva en el CSV** (el consolidado refleja la fuente tal como
es), pero **se excluye del análisis y del dashboard**. Un indicador constante en cero no
distingue nada entre bancos y solo agregaría ruido visual.

## 9. La cartera de vivienda de Banco Ripley distorsiona cualquier promedio simple

La morosidad de vivienda de Ripley sube de ~13% (2023) a ~27% (2026), mientras su índice
de provisiones de vivienda se mantiene entre 0,4% y 0,5%. La cobertura implícita de ese
segmento queda cerca de 0,02 — un valor que sería alarmante si se leyera como el resto.

La explicación más plausible es que se trata de una cartera residual, muy pequeña y con
garantía hipotecaria detrás: la garantía reduce la pérdida esperada y por lo tanto la
provisión exigida, aunque la mora sea alta. **Este análisis no puede confirmarlo con los
datos de la CMF**, porque los reportes usados entregan índices porcentuales y no los saldos
que permitirían medir el peso de esa cartera.

Consecuencia — dónde entra vivienda y dónde no:

- **No entra en el KPI central.** El índice de cobertura que la portada y el comparativo
  entre bancos muestran se calcula sobre `total_colocaciones`, y la lectura por segmento del
  hallazgo principal se apoya en `consumo`. Vivienda nunca forma parte de esas cifras.
- **Sí entra en la lectura por segmento, y nunca sin la advertencia al lado.** El dashboard
  publica la brecha de *morosidad* de vivienda entre grupos —de 7,2 pp (2023) a 13,8 pp
  (2026)— y `hallazgos.md` reporta además su cobertura por grupo (0,31 la banca tradicional,
  0,06 el retail) dentro de la tabla por segmento. Son movimientos reales de la serie y
  omitirlos sería esconder justo el segmento que más se abrió. La nota al pie de la página de
  Segmentación lo declara en el mismo visual: los promedios entre bancos son simples y no
  ponderados, y la vivienda de Ripley —mora de 13% a 27% con provisiones de 0,4-0,5%— es
  cartera residual con garantía real.
- **Lo que no se hace es leer esos promedios como riesgo comparable.** Son promedios simples
  de dos bancos contra tres, dominados por la cartera residual de Ripley, y una cobertura de
  0,06 puesta al lado de una de 1,3 se lee como alarma cuando en realidad refleja una
  garantía hipotecaria. Ninguna de esas cifras se presenta sin la advertencia inmediatamente
  a su lado, ni se usa para concluir nada sobre "el riesgo hipotecario del retail financiero".

Regla operativa, para no dejarla a interpretación: **vivienda se publica, nunca se concluye.**

## 10. Quiebre en las provisiones comerciales de Banco Ripley

El índice de provisiones comerciales de Ripley cae de ~11,9% (promedio 2023) a ~1,5%
(2026), mientras su morosidad comercial se mantiene alta, entre 16% y 21%. Es el
movimiento más brusco de toda la serie.

Un cambio de esa magnitud, con la mora sin mejorar en paralelo, apunta más a un evento
contable —venta o castigo de cartera, reclasificación de segmento— que a una mejora real
del riesgo. **Con estos datos no se puede determinar cuál de las dos cosas es.** Se
reporta como observación, nunca como "Ripley mejoró su riesgo comercial".

## 11. El índice de cobertura compara dos porcentajes con denominadores distintos

El KPI central se calcula como `índice de provisiones / índice de morosidad`. Eso equivale
al cociente de montos (provisiones / cartera morosa) **solo si ambos porcentajes usan el
mismo denominador**.

En la fuente los denominadores se llaman distinto: morosidad usa *"Colocaciones a costo
amortizado"* y provisiones usa *"Créditos y cuentas por cobrar a clientes"*. Son conceptos
equivalentes en el marco contable de la CMF, y por eso se consideran comparables, pero
**esta equivalencia no fue verificada contra los saldos**. El indicador debe leerse como
una razón de cobertura aproximada y comparable entre bancos, no como un cociente contable
exacto.

## 12. Aprendizaje de proceso: un dry-run que no ejerce la ruta real no valida nada

El script de descarga tenía un modo `--dry-run` que reportó "75 ok" mientras la corrida
real fallaba en los 75 archivos. La causa: los índices de la CMF redirigen `/617/` hacia
`/626/` mediante una cadena `302 → 301`, y los enlaces del índice son relativos. Al
resolverlos contra la URL solicitada en vez de la URL final (`resp.url`), el script armaba
rutas que respondían 404.

El `--dry-run` no lo detectó porque solo imprime las URLs que construye — nunca las visita.
Quedó como criterio para el resto del proyecto: **un modo de prueba que no ejerce la ruta
real solo valida la etapa que sí ejecuta.**

## 13. Una cobertura bajo 1 no es un incumplimiento normativo

El índice de cobertura de este proyecto mide provisiones contra cartera con mora de 90 días
o más. **La CMF no exige que esa razón sea mayor a 1.** Las provisiones se determinan por
pérdida esperada según los modelos de cada banco, y las garantías reales —hipotecarias
sobre todo— reducen la provisión exigida sobre una misma cartera morosa. Una cartera con
alta proporción de vivienda tiene cobertura estructuralmente baja sin estar
sub-provisionada.

Consecuencia para la lectura de los resultados: cuando `hallazgos.md` reporta que BCI lleva
25 de 41 meses bajo 1, eso describe **una trayectoria**, no un dictamen de suficiencia. El
indicador sirve para comparar a un banco consigo mismo en el tiempo y para contrastar
tendencias entre instituciones. No sirve para afirmar que un banco está mal provisionado, y
en ningún gráfico de este proyecto se presenta el valor 1 como un umbral regulatorio.

## 14. Los promedios entre bancos son simples, no ponderados

Todos los agregados por grupo de este proyecto se calculan con `AVG()` sobre los bancos que
lo componen. Eso le da a Banco de Chile el mismo peso que a Banco Ripley, pese a que sus
carteras difieren en órdenes de magnitud.

Lo correcto sería ponderar por saldo de colocaciones, y **no es posible con estas dos
fuentes**: ambas publican índices porcentuales, ninguna publica el monto de la cartera.
Obtenerlo exigiría incorporar un tercer reporte de la CMF (estados financieros), lo que
queda fuera del alcance declarado.

Por lo tanto, en todo este proyecto **"la morosidad de la banca tradicional" significa "el
promedio de las morosidades de sus tres miembros"**, no la morosidad agregada del grupo. La
distinción está impresa en la portada del dashboard, no escondida en un tooltip.
