# Análisis comparativo de riesgo crediticio: retail financiero vs. banca tradicional en Chile

Análisis de la evolución del riesgo de crédito de cinco bancos chilenos entre enero 2023
y mayo 2026, construido sobre **datos públicos reales de la Comisión para el Mercado
Financiero (CMF)**, no sintéticos.

## Pregunta que responde

> ¿El riesgo crediticio del retail financiero se comporta distinto al de la banca
> tradicional, y esa diferencia se sostiene en el tiempo?

Se mide con tres indicadores mensuales por banco y por segmento de cartera:

| Indicador | Qué muestra |
|---|---|
| Morosidad 90+ días | Cuánta cartera ya se deterioró |
| Provisiones por riesgo de crédito | Cuánto anticipa el banco que va a perder |
| **Índice de cobertura** (provisiones / cartera morosa) | Cuán preparado está frente a lo que ya se deterioró |

El índice de cobertura es el KPI central: dos bancos con la misma morosidad pueden tener
posturas de riesgo completamente distintas según cuánto provisionen.

## Resultado principal

> **Los dos grupos se movieron en direcciones opuestas.** Entre enero de 2023 y mayo de
> 2026 la morosidad de la banca tradicional subió de 1,70% a 2,23% y su cobertura cayó de
> 1,34 a 1,09. En el mismo período el retail financiero **bajó** su morosidad de 4,87% a
> 4,24% manteniendo la cobertura estable en torno a 1,37.
>
> La brecha entre ambos se cerró de 3,5 a 2,0 puntos porcentuales, pero no porque el retail
> se pareciera a la banca: porque la banca se acercó al retail.

| | Banca tradicional | Retail financiero |
|---|---|---|
| Morosidad 90+ · 2023 → 2026 | 1,70% → **2,23%** | 4,87% → **4,24%** |
| Cobertura · 2023 → 2026 | 1,34 → **1,09** | 1,45 → **1,37** |

La correlación entre las dos series mensuales de morosidad es **−0,19**: no es un ciclo de
crédito común empujando a los cinco bancos, son dos trayectorias distintas.

El desarrollo completo —seis hallazgos, con lo que los datos **no** permiten afirmar— está
en [`docs/hallazgos.md`](docs/hallazgos.md).

## Estado del proyecto

**En construcción.** Avance real al 31 de agosto de 2026:

- [x] Definición de alcance y pregunta de negocio
- [x] Perfilamiento de las fuentes (5 meses de muestra, cambios de formato documentados)
- [x] Descarga automatizada de la serie completa — 82 archivos Excel, 41 meses × 2 reportes
- [x] Consolidación y validación de completitud — 2.460 filas, 0 duplicados, 41 meses continuos
- [x] Modelo relacional en MySQL + diagrama ER
- [x] Análisis SQL y hallazgos
- [ ] Dashboard Power BI (3 páginas, medidas DAX)

## Alcance

**5 bancos**, elegidos para contrastar dos modelos de negocio:

| Banco | Grupo |
|---|---|
| Banco Falabella | Retail financiero |
| Banco Ripley | Retail financiero |
| Banco de Chile | Banca tradicional |
| Banco de Crédito e Inversiones (BCI) | Banca tradicional |
| Banco Santander-Chile | Banca tradicional |

**Período:** enero 2023 – mayo 2026 (41 meses, frecuencia mensual).

El detalle está en [`docs/alcance.md`](docs/alcance.md). Lo que este análisis **no**
puede afirmar está en [`docs/limitaciones.md`](docs/limitaciones.md).

## Reproducibilidad

Los Excel crudos de la CMF **no se versionan**: son ~30 MB que cualquiera puede regenerar.
El `.gitignore` excluye los `.xlsx`, no las carpetas —los `.gitkeep` sí se versionan— para
que al clonar exista la estructura que `scripts/descargar_cmf.py` necesita. Ese script es
la pieza que hace este repositorio reproducible de punta a punta.

```bash
git clone https://github.com/maximunozf/analisis-riesgo-bancario-chile
cd analisis-riesgo-bancario-chile

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scripts/descargar_cmf.py --dry-run   # muestra qué bajaría, sin descargar
python scripts/descargar_cmf.py             # descarga la serie completa (~10 min)
python scripts/verificar_inventario.py      # confirma que no hay meses faltantes
python scripts/consolidar_datos_cmf.py      # genera el CSV consolidado
```

Para levantar la base y correr el análisis:

```bash
cp .env.example .env                        # y editar con las credenciales de MySQL
mysql -u root -p < sql/create_tables.sql    # crea el esquema y la vista
python -u scripts/cargar_mysql.py           # carga las 2.460 filas
python -u scripts/cargar_mysql.py --validar # 7 chequeos de integridad

mysql -u root -p -t riesgo_bancario_cmf < sql/analisis_riesgo.sql
```

El script de carga es transaccional y la tabla de hechos tiene una restricción `UNIQUE`
sobre el grano completo: una segunda corrida falla en vez de duplicar en silencio. Para
recrear la base desde cero, `--recrear`.

`descargar_cmf.py` es **idempotente**: solo baja lo que falta, escribe a un archivo
temporal y lo renombra recién al terminar, de modo que una corrida interrumpida no deja
archivos parciales dados por buenos.

## Estructura

```
├── data/raw/morosidad/      Excel originales CMF (no versionados, nunca se modifican)
├── data/raw/provisiones/    Excel originales CMF (no versionados, nunca se modifican)
├── data/processed/          CSV consolidado y limpio
├── scripts/                 descarga, verificación, consolidación y carga a MySQL
├── sql/                     create_tables.sql (esquema + vista) y analisis_riesgo.sql
├── dashboard/               archivo .pbix
└── docs/                    alcance, perfilamiento, limitaciones, modelo de datos, hallazgos
```

## Stack

Python (`pandas`, `requests`, `beautifulsoup4`, `openpyxl`) → MySQL → Power BI.

## Decisiones técnicas

**La descarga scrapea el índice en vez de construir URLs.** Cada mes se publica como un
artículo con ID impredecible (`w4-article-112237.html`), sin patrón derivable de la fecha.
Leer la página índice es la única forma reproducible de obtener los enlaces.

**Los índices de la CMF redirigen `/617/` → `/626/` (cadena 302 → 301) y sus enlaces son
relativos.** Resolverlos contra la URL solicitada en vez de la URL final produce rutas que
responden 404. La base del `urljoin` tiene que ser `resp.url`.

**El script ubica cada banco buscando su nombre, nunca por número de fila.** La cantidad de
filas de encabezado varía entre meses y la lista de instituciones no es estática (Banco
Security desaparece en noviembre 2025 por su fusión con Bice; Tanner Banco Digital aparece
ese mismo mes). Ver [`docs/perfilamiento.md`](docs/perfilamiento.md).

**El período cierra en el último mes con ambas fuentes publicadas.** Provisiones se publica
un mes después que morosidad, y el índice de cobertura exige las dos del mismo mes.

**Validación de integridad en la descarga.** Un `.xlsx` es un ZIP y siempre empieza con la
firma `PK`. El portal a veces devuelve páginas de error con HTTP 200; verificar los dos
primeros bytes las detecta antes de que contaminen el consolidado.

**La tabla de hechos está en formato largo, no una columna por indicador.** Agregar un
tercer indicador de la CMF es insertar filas, no alterar la tabla y reescribir la carga. El
costo —que la cobertura exige un self-join— se paga una sola vez en la vista
`vw_riesgo_ancho`. El razonamiento completo del modelo, con el diagrama ER, está en
[`docs/modelo_datos.md`](docs/modelo_datos.md).

**Los valores son índices porcentuales, no montos.** Los segmentos no se suman
(`comerciales + personas ≠ total`) y los promedios entre bancos son simples, no ponderados
por tamaño de cartera: ninguna de las dos fuentes publica saldos en pesos. Esta restricción
condiciona cómo se lee todo el análisis y está declarada en el dashboard, no solo en los
documentos.

## Fuentes

- [Indicador de morosidad de 90 días o más — CMF](https://www.cmfchile.cl/portal/estadisticas/617/w3-propertyvalue-28914.html)
- [Indicadores de Provisiones por Riesgo de Crédito de Bancos — CMF](https://www.cmfchile.cl/portal/estadisticas/617/w3-propertyvalue-29554.html)

## Licencia

MIT — ver [`LICENSE`](LICENSE). Los datos son de dominio público y pertenecen a la CMF.
