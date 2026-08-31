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

## 7. Aprendizaje de proceso: un dry-run que no ejerce la ruta real no valida nada

El script de descarga tenía un modo `--dry-run` que reportó "75 ok" mientras la corrida
real fallaba en los 75 archivos. La causa: los índices de la CMF redirigen `/617/` hacia
`/626/` mediante una cadena `302 → 301`, y los enlaces del índice son relativos. Al
resolverlos contra la URL solicitada en vez de la URL final (`resp.url`), el script armaba
rutas que respondían 404.

El `--dry-run` no lo detectó porque solo imprime las URLs que construye — nunca las visita.
Quedó como criterio para el resto del proyecto: **un modo de prueba que no ejerce la ruta
real solo valida la etapa que sí ejecuta.**
