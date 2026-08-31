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

## Estado del proyecto

**En construcción.** Avance real al 29 de agosto de 2026:

- [x] Definición de alcance y pregunta de negocio
- [x] Perfilamiento de las fuentes (5 meses de muestra, cambios de formato documentados)
- [x] Descarga automatizada de la serie completa — 82 archivos Excel, 41 meses × 2 reportes
- [ ] Consolidación y validación de completitud
- [ ] Modelo relacional en MySQL + diagrama ER
- [ ] Análisis SQL y hallazgos
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

Los Excel crudos de la CMF **no se versionan** (`data/raw/` está en `.gitignore`): son
~30 MB que cualquiera puede regenerar. `scripts/descargar_cmf.py` es la pieza que hace
este repositorio reproducible de punta a punta.

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

`descargar_cmf.py` es **idempotente**: solo baja lo que falta, escribe a un archivo
temporal y lo renombra recién al terminar, de modo que una corrida interrumpida no deja
archivos parciales dados por buenos.

## Estructura

```
├── data/raw/morosidad/      Excel originales CMF (no versionados, nunca se modifican)
├── data/raw/provisiones/    Excel originales CMF (no versionados, nunca se modifican)
├── data/processed/          CSV consolidado y limpio
├── scripts/                 descarga, verificación de inventario y consolidación
├── sql/                     CREATE TABLE y consultas de análisis
├── dashboard/               archivo .pbix
└── docs/                    alcance, perfilamiento, limitaciones, hallazgos, diagrama ER
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

## Fuentes

- [Indicador de morosidad de 90 días o más — CMF](https://www.cmfchile.cl/portal/estadisticas/617/w3-propertyvalue-28914.html)
- [Indicadores de Provisiones por Riesgo de Crédito de Bancos — CMF](https://www.cmfchile.cl/portal/estadisticas/617/w3-propertyvalue-29554.html)

## Licencia

MIT — ver [`LICENSE`](LICENSE). Los datos son de dominio público y pertenecen a la CMF.
