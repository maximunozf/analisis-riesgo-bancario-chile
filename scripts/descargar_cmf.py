"""
descargar_cmf.py — Descarga automatizada de los reportes mensuales de la CMF.

Reemplaza la descarga manual mes a mes de los dos reportes del proyecto:
  - Indicador de morosidad de 90 dias o mas (individual)
  - Indicadores de Provisiones por Riesgo de Credito

Por que un scraper y no una lista fija de URLs:
la CMF publica cada mes como un "articulo" con un ID propio e impredecible
(w4-article-112234.html). No existe un patron de URL que se pueda construir a
partir de la fecha, asi que la unica forma reproducible de obtener los enlaces
es leer la pagina indice de cada reporte, que lista todos los meses publicados
en una sola vista.

Reglas del proyecto que respeta este script:
  - Nunca modifica ni sobrescribe archivos ya presentes en data/raw.
  - Es idempotente: se puede correr las veces que sea necesario; solo baja lo
    que falta. Si una corrida se interrumpe, la siguiente retoma donde quedo.
  - Guarda con la convencion de nombre del proyecto: AAAA-MM.xlsx

Uso:
    python scripts/descargar_cmf.py --dry-run   # solo muestra que bajaria
    python scripts/descargar_cmf.py             # descarga de verdad

Dependencias: requests, beautifulsoup4 (ver requirements.txt)
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------------

# Paginas indice de cada reporte. Cada una lista TODOS los meses publicados
# (desde 2017-2018 hasta el mes mas reciente) en una sola pagina sin paginacion.
INDICES = {
    "morosidad": "https://www.cmfchile.cl/portal/estadisticas/617/w3-propertyvalue-28914.html",
    "provisiones": "https://www.cmfchile.cl/portal/estadisticas/617/w3-propertyvalue-29554.html",
}

# Rango del alcance del proyecto.
# Por que termina en 2026-05 y no en 2026-06: provisiones se publica con un mes
# de rezago respecto de morosidad, y el indicador de cobertura
# (provisiones / cartera morosa) exige ambas fuentes del MISMO mes. El periodo
# cierra en el ultimo mes con las dos fuentes publicadas.
PERIODO_INICIO = "2023-01"
PERIODO_FIN = "2026-05"

# La CMF es un servicio publico con infraestructura modesta: un delay entre
# descargas evita gatillar rate-limiting y es la practica correcta al automatizar
# contra un portal publico.
DELAY_ENTRE_DESCARGAS = 1.5  # segundos
TIMEOUT = 60  # segundos por request
REINTENTOS = 3
ESPERA_REINTENTO = [3, 8, 20]  # backoff creciente, en segundos

# Identificarse es cortesia basica al scrapear y evita bloqueos por user-agent vacio.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; portafolio-datos/1.0; "
        "proyecto academico de analisis de riesgo crediticio)"
    )
}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Raiz del repo calculada desde la ubicacion del script (scripts/ -> raiz).
# Por que: permite ejecutarlo desde cualquier directorio sin romper las rutas.
RAIZ = Path(__file__).resolve().parents[1]
DATA_RAW = RAIZ / "data" / "raw"


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def sin_acentos(texto: str) -> str:
    """Normaliza para que 'Marzo' y 'marzo' matcheen igual que 'Setiembre'."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def periodos_esperados(inicio: str, fin: str) -> list[str]:
    """Genera ['2023-01', '2023-02', ..., '2026-05'] sin depender de pandas."""
    a_i, m_i = (int(x) for x in inicio.split("-"))
    a_f, m_f = (int(x) for x in fin.split("-"))
    out = []
    a, m = a_i, m_i
    while (a, m) <= (a_f, m_f):
        out.append(f"{a:04d}-{m:02d}")
        m += 1
        if m == 13:
            a, m = a + 1, 1
    return out


def extraer_periodo(texto: str) -> str | None:
    """
    Obtiene 'AAAA-MM' desde el texto del enlace.

    Se soportan dos formatos porque la CMF no es consistente entre reportes ni
    entre epocas: algunos titulos dicen 'Mayo 2026' y otros '2026-05'.
    Devuelve None si el enlace no corresponde a una publicacion mensual.
    """
    t = sin_acentos(texto)

    # Formato numerico: "... - 2026-05"
    m = re.search(r"\b(20\d{2})[-/](0[1-9]|1[0-2])\b", t)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    # Formato en palabras: "... Mayo 2026" o "... mayo de 2026"
    nombres = "|".join(MESES)
    m = re.search(rf"\b({nombres})\s+(?:de\s+)?(20\d{{2}})\b", t)
    if m:
        return f"{int(m.group(2)):04d}-{MESES[m.group(1)]:02d}"

    return None


def get_con_reintentos(session: requests.Session, url: str) -> requests.Response:
    """
    GET con reintentos y backoff.

    Por que: el portal de la CMF se cae o se satura con cierta frecuencia. Un
    fallo puntual no debe abortar una corrida de 75 descargas.
    """
    ultimo_error = None
    for intento in range(REINTENTOS):
        try:
            r = session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            ultimo_error = e
            if intento < REINTENTOS - 1:
                espera = ESPERA_REINTENTO[intento]
                print(f"      reintento {intento + 1}/{REINTENTOS - 1} en {espera}s ({e.__class__.__name__})")
                time.sleep(espera)
    raise RuntimeError(f"no se pudo obtener {url}: {ultimo_error}")


# --------------------------------------------------------------------------
# Scraping
# --------------------------------------------------------------------------

def leer_indice(session: requests.Session, url_indice: str) -> dict[str, str]:
    """
    Devuelve {'2026-05': 'https://.../w4-article-112237.html', ...}

    Se queda con la PRIMERA aparicion de cada periodo porque la pagina lista de
    mas reciente a mas antiguo y esa primera entrada es la publicacion vigente.
    """
    resp = get_con_reintentos(session, url_indice)
    soup = BeautifulSoup(resp.text, "html.parser")

    # Por que resp.url y no url_indice: el portal redirige la seccion /617/ hacia
    # /626/. Los href del indice son RELATIVOS, asi que resolverlos contra la URL
    # solicitada arma rutas /617/w4-article-*.html que responden 404. La base
    # correcta es siempre la URL final despues de los redirects.
    base = resp.url

    encontrados: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Solo interesan los enlaces a articulos de publicacion mensual.
        if "article" not in href:
            continue
        periodo = extraer_periodo(a.get_text(" ", strip=True))
        if periodo and periodo not in encontrados:
            encontrados[periodo] = requests.compat.urljoin(base, href)

    return encontrados


def url_del_xlsx(session: requests.Session, url_articulo: str) -> str:
    """
    Obtiene el enlace real al .xlsx desde la pagina del articulo.

    Por que no construir la URL directamente: el patron observado hoy es
    'articles-<ID>_recurso_1.xlsx', pero es un detalle interno del CMS y puede
    cambiar. Leer el href publicado es lo unico estable. Igual se deja el patron
    como fallback para no fallar si la pagina cambia de maquetacion.
    """
    resp = get_con_reintentos(session, url_articulo)
    soup = BeautifulSoup(resp.text, "html.parser")

    # Misma razon que en leer_indice: la base para resolver href relativos es la
    # URL final tras redirects, no la solicitada.
    base = resp.url

    for a in soup.find_all("a", href=True):
        if a["href"].lower().split("?")[0].endswith(".xlsx"):
            return requests.compat.urljoin(base, a["href"])

    # Fallback: reconstruir desde el ID del articulo.
    m = re.search(r"w[34]-article-(\d+)\.html", base)
    if m:
        return requests.compat.urljoin(base, f"articles-{m.group(1)}_recurso_1.xlsx")

    raise RuntimeError(f"no se encontro el .xlsx en {url_articulo}")


def descargar(session: requests.Session, url_xlsx: str, destino: Path) -> None:
    """
    Descarga a un archivo temporal y recien despues lo renombra al nombre final.

    Por que: si la conexion se corta a la mitad, un archivo parcial con el nombre
    definitivo haria que la proxima corrida lo diera por descargado y el hueco
    quedaria invisible hasta la consolidacion.
    """
    resp = get_con_reintentos(session, url_xlsx)

    # Un .xlsx es un ZIP: siempre empieza con la firma 'PK'. Si el portal devuelve
    # una pagina de error con HTTP 200 (le pasa), esto lo detecta al instante.
    if resp.content[:2] != b"PK":
        raise RuntimeError(
            f"la respuesta no es un .xlsx valido ({len(resp.content)} bytes). "
            "Probablemente el portal devolvio una pagina de error."
        )

    tmp = destino.with_suffix(".xlsx.tmp")
    tmp.write_bytes(resp.content)
    tmp.replace(destino)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga los reportes mensuales de la CMF.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Lee los indices y reporta que bajaria, sin descargar nada.",
    )
    args = parser.parse_args()

    esperados = periodos_esperados(PERIODO_INICIO, PERIODO_FIN)
    print(f"Alcance: {PERIODO_INICIO} a {PERIODO_FIN} ({len(esperados)} meses por reporte)")

    session = requests.Session()
    session.headers.update(HEADERS)

    total_ok = 0
    total_error = 0

    for reporte, url_indice in INDICES.items():
        carpeta = DATA_RAW / reporte
        carpeta.mkdir(parents=True, exist_ok=True)

        presentes = {f.stem for f in carpeta.glob("*.xlsx")}
        faltantes = [p for p in esperados if p not in presentes]

        print(f"\n=== {reporte} ===")
        print(f"  ya presentes en alcance: {len(presentes & set(esperados))}/{len(esperados)}")
        print(f"  por descargar: {len(faltantes)}")
        if not faltantes:
            continue

        print(f"  leyendo indice...")
        catalogo = leer_indice(session, url_indice)
        print(f"  el indice publica {len(catalogo)} meses en total")

        no_publicados = [p for p in faltantes if p not in catalogo]
        if no_publicados:
            print(f"  AVISO: {len(no_publicados)} mes(es) del alcance no estan en el indice: {no_publicados}")

        for periodo in faltantes:
            if periodo not in catalogo:
                continue
            destino = carpeta / f"{periodo}.xlsx"
            if args.dry_run:
                print(f"  [dry-run] {periodo} -> {catalogo[periodo]}")
                total_ok += 1
                continue
            try:
                enlace = url_del_xlsx(session, catalogo[periodo])
                descargar(session, enlace, destino)
                print(f"  OK  {periodo}.xlsx")
                total_ok += 1
            except Exception as e:
                print(f"  FALLA {periodo}: {e}")
                total_error += 1
            time.sleep(DELAY_ENTRE_DESCARGAS)

    print(f"\nResumen: {total_ok} ok, {total_error} con error.")
    if total_error:
        print("Volver a correr el script: reintenta solo los que fallaron.")
    return 1 if total_error else 0


if __name__ == "__main__":
    sys.exit(main())
