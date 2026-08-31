# Perfilamiento de los datos fuente (CMF)

**Por qué existe este documento:** antes de escribir el script de limpieza,
revisé manualmente 5 meses de cada reporte (enero 2023, julio 2024, octubre
2025, noviembre 2025 y el mes más reciente disponible al momento del
perfilamiento) para detectar cambios de formato en el tiempo. Documentar esto
ahora evita errores silenciosos en la consolidación de los **41 meses** del
proyecto (enero 2023 – mayo 2026), y deja registro del criterio usado para
quien revise este repositorio.

Los meses de muestra no se eligieron al azar: cubren los dos extremos de la
serie y los puntos donde se sabía que hubo cambios en el sistema bancario.

## Fuentes

- **Morosidad:** [Indicador de morosidad de 90 días o más — CMF](https://www.cmfchile.cl/portal/estadisticas/617/w3-propertyvalue-28914.html)
- **Provisiones:** [Indicadores de Provisiones por Riesgo de Crédito de Bancos — CMF](https://www.cmfchile.cl/portal/estadisticas/617/w3-propertyvalue-29554.html)

## Hallazgos

| # | Hallazgo | Impacto en el script |
|---|----------|----------------------|
| 1 | El archivo de morosidad viene en una sola hoja (`Mora 90 Indiv`). El de provisiones viene en un libro de **39 hojas**; solo `CUADRO N°1` tiene la estructura equivalente (índice de provisiones por tipo de colocación). | El script debe leer explícitamente esa hoja en provisiones e ignorar las 38 restantes. |
| 2 | La estructura de columnas (Total, Comerciales, Personas→Total/Consumo/Vivienda, Adeudado por bancos) es **idéntica** en ambos reportes y estable en todo el período 2023-2026. | Permite usar la misma lógica de extracción para ambos indicadores. |
| 3 | El número de filas de encabezado antes de los datos **varía levemente entre meses** (confirmado comparando enero 2023 contra meses posteriores). | El script nunca debe asumir un número de fila fijo — debe ubicar cada banco buscando su nombre en el texto. |
| 4 | La cantidad de instituciones reportadas **cambia en el tiempo**: Banco Security desaparece en noviembre 2025 (fusión con Banco Bice, Resolución CMF N° 10940); Tanner Banco Digital aparece por primera vez ese mismo mes. Itaú Corpbanca cambia de razón social a Banco Itaú Chile entre 2023 y 2024. | Ninguno de estos cambios afecta a los 5 bancos de alcance del proyecto (ver más abajo), pero confirma que la lista de instituciones no es estática — el script filtra por nombre, no por posición ni por cantidad total de filas. |
| 5 | Existe una fila oculta con códigos contables (ej. `85700.00.00`) sobre el encabezado visible, colapsada bajo "Presione [+] para ver códigos de cuentas". | El script busca los datos recorriendo todas las filas por contenido, no por un rango fijo, así que esta fila no genera error — simplemente no matchea ningún nombre de banco y se ignora. |

## Bancos de alcance del proyecto

Confirmado que estos 5 aparecen con el **mismo nombre exacto en los 5 meses
revisados**, sin cambios de razón social ni fusiones:

| Banco | Grupo |
|-------|-------|
| Banco Falabella | Retail financiero |
| Banco Ripley | Retail financiero |
| Banco de Chile | Banca tradicional |
| Banco de Crédito e Inversiones (BCI) | Banca tradicional |
| Banco Santander-Chile | Banca tradicional |

*Nota: Tenpo fue excluido del alcance original porque no está regulado como
banco ante la CMF (opera como emisor de tarjeta prepago/fintech) y por lo
tanto no aparece en ninguno de los dos reportes fuente.*

## Limitación conocida del período

Los reportes de morosidad y provisiones no se publican el mismo día del mes,
por lo que la serie de provisiones queda sistemáticamente **un mes detrás**
de la de morosidad. El análisis se acota a los meses donde ambos indicadores
están disponibles: la serie cierra en **mayo 2026**, y `morosidad/2026-06.xlsx`
se conserva en `data/raw` pero queda fuera del consolidado.

## Verificación posterior a la descarga completa

El perfilamiento se hizo sobre 5 meses de muestra. Al descargar los 41 meses
aparecieron dos escalones de formato que la muestra no dejaba ver con claridad
y que conviene tener presentes si la consolidación arroja algo raro:

- **Provisiones cambia de formato en enero 2024:** los archivos de 2023 pesan
  ~478 KB y desde `2024-01` bajan a ~330 KB. La muestra cruzaba ese corte
  (2023-01 y 2024-07), así que la lógica de extracción ya estaba validada a
  ambos lados.
- **Morosidad tiene tres escalones de tamaño:** ~40 KB (ene-feb 2023), ~51 KB
  (mar 2023 – dic 2025) y ~42 KB (desde ene 2026).

Ambos quedan registrados en [`limitaciones.md`](limitaciones.md).
