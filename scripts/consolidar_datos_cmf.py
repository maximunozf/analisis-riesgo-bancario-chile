# -*- coding: utf-8 -*-
"""
consolidar_datos_cmf.py
=======================

Consolida los reportes mensuales de la CMF (Comisión para el Mercado
Financiero de Chile) en un único CSV "tidy" (formato largo), listo para
cargar a MySQL y modelar en Power BI.

Fuentes (ver docs/perfilamiento.md):
  - Morosidad 90 días  -> carpeta data/raw/morosidad/   (hoja "Mora 90 Indiv")
  - Provisiones        -> carpeta data/raw/provisiones/  (hoja "CUADRO N°1")

--------------------------------------------------------------------------
POR QUÉ ESTE SCRIPT ESTÁ DISEÑADO ASÍ (decisiones defendibles en entrevista)
--------------------------------------------------------------------------
Cada decisión responde a un hallazgo documentado del perfilamiento:

  * Hallazgo #1 (morosidad = 1 hoja; provisiones = 39 hojas, solo "CUADRO N°1"
    sirve):  el script lee SIEMPRE la hoja indicada por configuración e ignora
    el resto. Nunca "adivina" la hoja.

  * Hallazgo #2 (la estructura de COLUMNAS es idéntica y estable en todo el
    período):  por eso las columnas se identifican por ÍNDICE FIJO configurable
    (COLUMNAS_MOROSIDAD / COLUMNAS_PROVISIONES). Es defendible fijarlas porque su estabilidad se
    verificó manualmente en 5 meses distintos. Y para que esa estabilidad no
    sea un supuesto de por vida, cada índice trae el token que debe aparecer
    en su encabezado (TOKENS_ENCABEZADO_*): si la CMF inserta una columna, el
    script aborta en vez de publicar valores corridos de segmento.

  * Hallazgo #3 (el nº de filas de encabezado VARÍA entre meses):  por eso las
    FILAS de cada banco NO se fijan; se localizan dinámicamente buscando el
    nombre del banco dentro del texto de cada fila.

  * Hallazgo #4 (la lista de instituciones cambia en el tiempo):  el script
    filtra por los 5 bancos de alcance por nombre; si un banco falta en un mes,
    lo reporta como faltante en vez de romperse.

  * Hallazgo #5 (fila oculta con códigos contables tipo 85700.00.00):  al
    buscar por nombre de banco, esa fila simplemente no matchea y se ignora
    sin lógica adicional.

Regla del proyecto: NUNCA se modifica data/raw. Este script solo LEE de raw y
ESCRIBE en data/processed. Es 100% reproducible: borrás el CSV, lo volvés a
correr y obtenés lo mismo.

--------------------------------------------------------------------------
CÓMO USARLO
--------------------------------------------------------------------------
1) Verificar los índices de columna UNA vez contra un archivo real:

       python consolidar_datos_cmf.py --inspeccionar data/raw/morosidad/2023-01.xlsx

   Eso imprime la grilla cruda (fila x columna) con índices. Con eso confirmás
   / ajustás el diccionario COLUMNAS_MOROSIDAD / COLUMNAS_PROVISIONES de abajo.

2) Consolidar todo:

       python consolidar_datos_cmf.py

   Lee las dos carpetas, verifica los encabezados, valida completitud y
   calidad, y escribe el CSV consolidado.

3) Consolidar dentro de una cadena automatizada:

       python consolidar_datos_cmf.py --estricto

   Igual que lo anterior, pero devuelve código de salida 1 si la validación
   de calidad encuentra duplicados, valores fuera de rango o huecos en la
   serie mensual. Sin este flag el script siempre sale con 0.

Dependencias:  pandas, openpyxl   (pip install pandas openpyxl)
"""

import argparse
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd


# =========================================================================
# 1. CONFIGURACIÓN  (lo único que podrías necesitar tocar)
# =========================================================================

# Carpetas de entrada/salida, relativas a la raíz del repo.
# Se resuelven desde la ubicación de este script (scripts/), subiendo un nivel,
# para que el script funcione sin importar desde dónde lo ejecutes.
RAIZ_REPO = Path(__file__).resolve().parent.parent
DIR_MOROSIDAD = RAIZ_REPO / "data" / "raw" / "morosidad"
DIR_PROVISIONES = RAIZ_REPO / "data" / "raw" / "provisiones"
RUTA_SALIDA = RAIZ_REPO / "data" / "processed" / "consolidado_cmf.csv"

# Ventana de períodos que ENTRA al consolidado (ambos extremos incluidos).
#
# ¿Por qué existe este corte y no consolidamos "todo lo que haya en raw"?
# El KPI central del proyecto es el índice de cobertura = provisiones / cartera
# morosa, y exige AMBAS fuentes del MISMO mes. Al 27-ago-2026 la CMF tenía
# publicada morosidad hasta jun-2026 pero provisiones solo hasta may-2026.
# Por eso data/raw/morosidad contiene 2026-06.xlsx: se descargó y se conserva
# (regla del proyecto: nunca borrar ni modificar data/raw), pero queda FUERA
# del consolidado. Sin este filtro la serie quedaría asimétrica (42 meses de
# morosidad vs. 41 de provisiones) y el mes 2026-06 tendría cobertura nula.
#
# Regla adoptada: el período cierra en el último mes con ambas fuentes
# publicadas -> may-2026. Documentado en docs/limitaciones.md.
PERIODO_INICIO = date(2023, 1, 1)
PERIODO_FIN = date(2026, 5, 1)

# Hoja a leer en cada tipo de reporte (Hallazgo #1).
#
# OJO: en los archivos de provisiones la hoja se llama literalmente
# "CUADRO N°1 " — CON UN ESPACIO AL FINAL. pandas exige coincidencia exacta,
# así que `sheet_name="CUADRO N°1"` falla con "Worksheet named ... not found".
# En vez de escribir el espacio (invisible y frágil), la hoja se resuelve
# comparando nombres NORMALIZADOS (ver resolver_hoja): así el script aguanta
# espacios sobrantes, mayúsculas y tildes distintas entre meses.
HOJA_MOROSIDAD = "Mora 90 Indiv"
HOJA_PROVISIONES = "CUADRO N°1"

# Los 5 bancos de alcance del proyecto y su grupo.
# 'tokens' son fragmentos NORMALIZADos (sin tildes, minúsculas) que deben
# aparecer en el nombre de la fila para dar match.
# 'modo':
#   - "contiene": basta que el token aparezca dentro del nombre de la fila.
#   - "exacto":   el nombre de la fila (normalizado) debe ser IGUAL al token.
#                 Se usa para "Banco de Chile" porque si usáramos "contiene"
#                 matchearía por error dentro de "Banco Santander-Chile".
BANCOS_ALCANCE = {
    "banco_falabella":       {"grupo": "retail_financiero", "tokens": ["falabella"],                 "modo": "contiene"},
    "banco_ripley":          {"grupo": "retail_financiero", "tokens": ["ripley"],                    "modo": "contiene"},
    "banco_de_chile":        {"grupo": "banca_tradicional", "tokens": ["banco de chile"],            "modo": "exacto"},
    "banco_bci":             {"grupo": "banca_tradicional", "tokens": ["credito e inversiones", "bci"], "modo": "contiene"},
    "banco_santander_chile": {"grupo": "banca_tradicional", "tokens": ["santander"],                 "modo": "contiene"},
}

# Mapa SEGMENTO -> índice de columna (base 0).
#
# VERIFICADO con --inspeccionar contra archivos reales (30-ago-2026):
# morosidad 2023-01 / 2025-11 / 2026-01 y provisiones 2023-01 / 2024-07 / 2026-05,
# es decir a ambos lados de los dos cambios de formato detectados en el
# perfilamiento. Los índices son idénticos en los 6 archivos (Hallazgo #2).
#
# CADA REPORTE TIENE SU PROPIO MAPA, no uno compartido. Aunque los dos cuadros
# se ven casi iguales, las columnas de provisiones están corridas +1 respecto
# de las de morosidad, porque provisiones abre con una columna extra
# ("Índice Provisiones s/ Colocaciones — Banco") antes del desglose. Usar un
# solo mapa para ambos leería la columna equivocada en uno de los dos y
# produciría un CSV con números plausibles pero falsos: el peor error posible,
# porque no se cae, se publica.
#
# Morosidad — encabezado real (filas 8-10 del Excel):
#   [2] Colocaciones (costo amortizado y valor razonable) — Total
#   [3] Colocaciones a costo amortizado — Total
#   [4] Comerciales   [5] Personas Total   [6] Consumo   [7] Vivienda
#   [8] Adeudado por bancos          [10][11] montos en MM$ (no se usan aquí)
#
# ¿Por qué [3] y no [2] como "total"? Porque el desglose por segmento
# ([4]-[8]) cuelga del bloque "Colocaciones a costo amortizado". Tomar el
# total de [2] mezclaría dos denominadores distintos y el total dejaría de
# ser comparable con sus propios componentes.
COLUMNAS_MOROSIDAD = {
    "total_colocaciones": 3,
    "comerciales":        4,
    "personas_total":     5,
    "consumo":            6,
    "vivienda":           7,
    "adeudado_bancos":    8,
}

# Provisiones — encabezado real (filas 8-11 del Excel):
#   [3] Índice provisiones s/ colocaciones — Banco (total institución)
#   [4] Créditos y cuentas por cobrar a clientes — Total
#   [5] Comerciales   [6] Personas Total   [7] Consumo   [8] Vivienda
#   [9] Adeudado por bancos
#   [11] Exposición créditos contingentes   [13] Provisiones adicionales
#
# Mismo criterio que en morosidad: el "total" es [4], la cabecera del bloque
# del que cuelgan los segmentos, no [3] que es el índice de todo el banco.
COLUMNAS_PROVISIONES = {
    "total_colocaciones": 4,
    "comerciales":        5,
    "personas_total":     6,
    "consumo":            7,
    "vivienda":           8,
    "adeudado_bancos":    9,
}

# Token que DEBE aparecer en el encabezado de cada columna configurada.
#
# POR QUÉ EXISTE ESTE SEGUNDO MAPA (es la protección más importante del script):
# fijar las columnas por índice es rápido y legible, pero tiene un modo de falla
# silencioso. Si la CMF INSERTA una columna intermedia —que es exactamente lo que
# ya hizo una vez, y por eso este script tiene dos mapas de columnas y no uno—
# todos los índices se corren, el script no lanza ningún error, la validación de
# completitud reporta 100% y el CSV queda lleno de números plausibles y falsos:
# 'comerciales' guardado como 'total', 'consumo' como 'personas'. El chequeo de
# índice fuera de rango no lo detecta, porque las columnas siguen existiendo.
#
# La verificación es directa: antes de leer un solo valor, se confirma que el
# texto del encabezado de cada columna contenga su token. Si no lo contiene, el
# script ABORTA en vez de publicar. Es la diferencia entre un pipeline que falla
# ruidosamente y uno que miente en silencio.
#
# Los tokens están normalizados (sin tildes, minúsculas) y son fragmentos, no
# nombres completos, para tolerar los sufijos de nota al pie que la CMF agrega
# y quita entre meses ("Vivienda" en morosidad, "Vivienda (3)" en provisiones).
TOKENS_ENCABEZADO_MOROSIDAD = {
    "total_colocaciones": "colocaciones a costo amortizado",
    "comerciales":        "comerciales",
    "personas_total":     "personas",
    "consumo":            "consumo",
    "vivienda":           "vivienda",
    "adeudado_bancos":    "adeudado por bancos",
}

TOKENS_ENCABEZADO_PROVISIONES = {
    "total_colocaciones": "creditos y cuentas por cobrar a clientes",
    "comerciales":        "comerciales",
    "personas_total":     "personas",
    "consumo":            "consumo",
    "vivienda":           "vivienda",
    "adeudado_bancos":    "adeudado por bancos",
}

# Nombres de indicador tal como quedarán en el CSV (snake_case).
INDICADOR_MOROSIDAD = "morosidad_90d"
INDICADOR_PROVISIONES = "indice_provisiones"


# =========================================================================
# 2. UTILIDADES DE TEXTO Y NÚMEROS
# =========================================================================

def normalizar(texto) -> str:
    """
    Normaliza texto para comparar nombres de banco de forma robusta:
    quita tildes, pasa a minúsculas y colapsa espacios.

    ¿Por qué? Los nombres en los Excel pueden venir como 'Banco  Falabella',
    'BANCO FALABELLA' o con tildes. Comparar el texto crudo daría falsos
    negativos. Normalizando, 'Banco  Falabella ' y 'banco falabella' coinciden.
    """
    if texto is None:
        return ""
    s = str(texto)
    # NFKD separa la letra de su tilde; luego descartamos los caracteres de tilde.
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)  # colapsa espacios múltiples en uno solo
    return s


def limpiar_valor(valor):
    """
    Convierte un valor de celda a float, o None si no es un número válido.

    ¿Por qué tanta lógica? Los reportes CMF pueden traer los indicadores como
    número real o como texto con formato chileno ('1.234,56' -> mil = punto,
    decimal = coma) o marcadores de dato ausente ('-', 's/i', 'n/d').
    Si no limpiamos, MySQL/Power BI recibirían texto y romperían los cálculos.
    """
    if valor is None:
        return None
    # Si ya es número (lo más común cuando pandas lee bien la celda), listo.
    if isinstance(valor, (int, float)):
        # pandas usa NaN para celdas vacías; NaN != NaN es True -> así lo detectamos.
        if isinstance(valor, float) and valor != valor:
            return None
        return float(valor)

    texto = str(valor).strip()
    if texto == "":
        return None

    # Marcadores explícitos de dato no disponible.
    #
    # "---" (tres guiones) es el que la CMF usa realmente cuando un banco no
    # opera un segmento —está documentado en docs/limitaciones.md §10— y hasta
    # ahora caía en el `except ValueError` del final: funcionaba, pero por
    # accidente y no por diseño. Se listan las tres variantes de guión porque
    # el ancho del guión cambia entre archivos y no es visible al leerlos.
    if normalizar(texto) in {"-", "--", "---", "s/i", "s/d", "n/d", "nd", "na", "n.a."}:
        return None

    # Quita símbolo de porcentaje y espacios internos.
    texto = texto.replace("%", "").replace(" ", "")

    # Manejo de separadores según formato chileno:
    if "," in texto and "." in texto:
        # Ambos presentes: el punto es separador de miles, la coma decimal.
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        # Solo coma: es el separador decimal.
        texto = texto.replace(",", ".")
    # Si solo hay punto, se asume que ya es el separador decimal.

    try:
        return float(texto)
    except ValueError:
        # No era un número (p. ej. una etiqueta de fila). Se descarta.
        return None


def extraer_periodo(nombre_archivo: str) -> date:
    """
    Deduce el período (primer día del mes) desde el nombre del archivo.

    CONVENCIÓN RECOMENDADA: nombrá cada archivo como 'AAAA-MM.xlsx'
    (ej. '2023-01.xlsx'). Es la forma más clara y ordenable.

    Por robustez igual acepta 'AAAA_MM', 'AAAAMM' y nombres de mes en español
    ('enero-2023'), porque los archivos se descargan a mano y los nombres
    pueden variar. Si no logra deducir el período, lanza un error explícito
    (mejor fallar fuerte que asignar una fecha equivocada en silencio).
    """
    base = normalizar(Path(nombre_archivo).stem)

    meses_es = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
        "noviembre": 11, "diciembre": 12,
    }

    # Caso A: mes escrito con palabra + año (ej. 'enero 2023').
    for nombre_mes, num_mes in meses_es.items():
        if nombre_mes in base:
            m_anio = re.search(r"(20\d{2})", base)
            if m_anio:
                return date(int(m_anio.group(1)), num_mes, 1)

    # Caso B: patrón AAAA-MM / AAAA_MM / AAAA MM.
    m = re.search(r"(20\d{2})[-_ ]?(0[1-9]|1[0-2])", base)
    if m:
        return date(int(m.group(1)), int(m.group(2)), 1)

    # Caso C: patrón MM-AAAA (mes primero).
    m = re.search(r"(0[1-9]|1[0-2])[-_ ](20\d{2})", base)
    if m:
        return date(int(m.group(2)), int(m.group(1)), 1)

    raise ValueError(
        f"No pude deducir el período del nombre '{nombre_archivo}'. "
        f"Renombralo como 'AAAA-MM.xlsx' (ej. '2023-01.xlsx')."
    )


# =========================================================================
# 3. LECTURA Y EXTRACCIÓN DE UN ARCHIVO
# =========================================================================

def resolver_hoja(ruta: Path, hoja_buscada: str) -> str:
    """
    Devuelve el nombre EXACTO de la hoja dentro del archivo que corresponde a
    `hoja_buscada`, comparando de forma normalizada.

    ¿Por qué no pasar el nombre directo a pandas? Porque en los reportes de
    provisiones la hoja se llama "CUADRO N°1 " con un espacio final invisible,
    y pandas exige coincidencia byte a byte: falla con "Worksheet named
    'CUADRO N°1' not found". Hardcodear el espacio funcionaría hoy pero es
    frágil (nadie lo ve al leer el código y la CMF puede quitarlo sin aviso).
    Comparar normalizado resuelve el espacio, las mayúsculas y las tildes de
    una sola vez, y si aun así no aparece, el error lista las hojas reales
    en vez de dejarte adivinando.
    """
    hojas = pd.ExcelFile(ruta).sheet_names
    objetivo = normalizar(hoja_buscada)
    for nombre in hojas:
        if normalizar(nombre) == objetivo:
            return nombre
    raise ValueError(
        f"No encontré la hoja '{hoja_buscada}' en {ruta.name}. "
        f"Hojas disponibles: {hojas}"
    )


def leer_grilla(ruta: Path, hoja: str) -> pd.DataFrame:
    """
    Lee la hoja indicada como grilla cruda, sin interpretar encabezados.

    header=None: NO tratamos ninguna fila como encabezado, porque el nº de
    filas de encabezado varía entre meses (Hallazgo #3). Preferimos la grilla
    completa y localizamos los datos nosotros mismos.

    dtype=object: leemos todo como texto/objeto para no perder ceros ni que
    pandas convierta a un tipo inesperado antes de que limpiemos nosotros.
    """
    hoja_real = resolver_hoja(ruta, hoja)
    return pd.read_excel(ruta, sheet_name=hoja_real, header=None, dtype=object)


def localizar_fila_banco(grilla: pd.DataFrame, tokens, modo: str):
    """
    Devuelve el índice de la primera fila cuyo texto coincide con el banco,
    o None si el banco no aparece en este mes.

    Recorre TODAS las columnas de cada fila (no asume en qué columna está el
    nombre) y las concatena en un solo texto normalizado para comparar.
    """
    for idx_fila in range(len(grilla)):
        # Une el contenido de la fila en un solo string normalizado.
        celdas = [normalizar(c) for c in grilla.iloc[idx_fila].tolist() if c is not None]
        texto_fila = " ".join(celdas).strip()
        if not texto_fila:
            continue

        for token in tokens:
            if modo == "exacto":
                # El nombre de alguna celda debe ser exactamente el token.
                # Evita que 'banco de chile' matchee dentro de 'santander-chile'.
                if any(celda == token for celda in celdas):
                    return idx_fila
            else:  # "contiene"
                if token in texto_fila:
                    return idx_fila
    return None


def verificar_encabezados(grilla: pd.DataFrame, columnas: dict, tokens: dict,
                          fila_primer_banco: int, ruta: Path) -> None:
    """
    Confirma que cada columna configurada sea realmente la que dice ser, leyendo
    su encabezado. Lanza ValueError si alguna no coincide.

    Cómo delimita el encabezado: TODO lo que está por encima de la primera fila
    de banco. No se fija un número de filas porque ese número varía entre meses
    (Hallazgo #3); se deriva del propio archivo, igual que las filas de banco.

    Por qué junta todas las filas del encabezado en un solo texto por columna:
    el encabezado real ocupa varias filas y viene con celdas combinadas
    ('Personas' arriba, 'Total' abajo), de modo que ninguna fila por separado
    contiene el nombre completo del segmento. Concatenando la columna entera el
    token aparece sin importar en qué fila del bloque quedó esta vez.

    Efecto práctico: si la CMF inserta o elimina una columna, los índices se
    corren, el token deja de estar donde se lo espera y el script se detiene
    ANTES de escribir el CSV. Es el único control que distingue "no hay datos"
    de "hay datos pero son del segmento equivocado".
    """
    problemas = []
    for segmento, col in columnas.items():
        token = tokens[segmento]
        if col >= grilla.shape[1]:
            problemas.append(f"    - {segmento}: la columna [{col}] no existe "
                             f"(el archivo tiene {grilla.shape[1]} columnas)")
            continue
        # Texto del encabezado de esa columna: todo lo que hay arriba del primer banco.
        # Se descartan las celdas vacías: pandas las entrega como NaN y str(NaN)
        # es "nan", que llenaría el mensaje de error de ruido justo cuando hay
        # que leerlo para entender qué se corrió.
        celdas = [c for c in grilla.iloc[0:fila_primer_banco, col].tolist()
                  if c is not None and not (isinstance(c, float) and c != c)]
        encabezado = " ".join(normalizar(c) for c in celdas)
        if token not in encabezado:
            problemas.append(f"    - {segmento}: se esperaba '{token}' en la "
                             f"columna [{col}] y el encabezado dice "
                             f"'{encabezado[:80].strip()}'")

    if problemas:
        raise ValueError(
            f"\n[X] El encabezado de {ruta.name} no coincide con el mapa de columnas.\n"
            + "\n".join(problemas)
            + "\n\n    Probable causa: la CMF cambió la estructura del reporte "
              "(insertó o quitó una columna).\n"
              "    NO se escribe el CSV: los valores estarían corridos de segmento.\n"
              f"    Revisá el archivo con:  python consolidar_datos_cmf.py --inspeccionar \"{ruta}\"\n"
              "    y ajustá COLUMNAS_* y TOKENS_ENCABEZADO_* con lo que veas."
        )


def extraer_archivo(ruta: Path, hoja: str, indicador: str, columnas: dict,
                    tokens: dict) -> list:
    """
    Extrae los registros de un archivo y los devuelve en formato LARGO (tidy):
    una fila por combinación (periodo, banco, indicador, segmento, valor).

    ¿Por qué formato largo y no ancho? Porque alimenta directo un modelo
    estrella (tabla de hechos) en MySQL/Power BI: cada fila es un hecho
    atómico. Mucho más fácil de filtrar por segmento o indicador que tener
    6 columnas de segmento por fila.
    """
    periodo = extraer_periodo(ruta.name)
    grilla = leer_grilla(ruta, hoja)
    registros = []

    # Primero se ubican TODOS los bancos, antes de leer un solo valor.
    # Sirve para dos cosas: reportar los faltantes, y saber dónde termina el
    # bloque de encabezado (todo lo que está arriba del primer banco), que es
    # lo que necesita verificar_encabezados para no depender de un número fijo
    # de filas.
    filas_banco = {}
    for banco, cfg in BANCOS_ALCANCE.items():
        fila = localizar_fila_banco(grilla, cfg["tokens"], cfg["modo"])
        if fila is None:
            # El banco no está en este mes: se deja constancia pero no se corta.
            print(f"    [!] {banco} no encontrado en {ruta.name}")
            continue
        filas_banco[banco] = fila

    if not filas_banco:
        print(f"    [!] Ningún banco de alcance en {ruta.name}: se omite el archivo")
        return []

    verificar_encabezados(grilla, columnas, tokens, min(filas_banco.values()), ruta)

    for banco, fila in filas_banco.items():
        cfg = BANCOS_ALCANCE[banco]
        for segmento, col in columnas.items():
            # Protección: la columna configurada podría no existir en la grilla.
            if col >= grilla.shape[1]:
                valor = None
            else:
                valor = limpiar_valor(grilla.iloc[fila, col])

            registros.append({
                "periodo": periodo,
                "anio": periodo.year,
                "mes": periodo.month,
                "banco": banco,
                "grupo": cfg["grupo"],
                "indicador": indicador,
                "segmento": segmento,
                "valor": valor,
            })

    return registros


def procesar_directorio(directorio: Path, hoja: str, indicador: str,
                        columnas: dict, tokens: dict) -> list:
    """Procesa todos los .xlsx de una carpeta y acumula los registros."""
    if not directorio.exists():
        raise FileNotFoundError(f"No existe la carpeta {directorio}")

    archivos = sorted(
        p for p in directorio.iterdir()
        if p.suffix.lower() in {".xlsx", ".xls"} and not p.name.startswith("~$")
    )
    if not archivos:
        print(f"  [!] No hay archivos Excel en {directorio}")
        return []

    # Se separan los archivos dentro y fuera de la ventana ANTES de leerlos.
    # ¿Por qué filtrar por nombre y no después, sobre el DataFrame? Porque así
    # no gastamos tiempo abriendo un Excel que igual íbamos a descartar, y el
    # log deja constancia explícita de qué se excluyó y por qué (trazabilidad:
    # el consolidado tiene que ser explicable, no "misteriosamente más chico").
    en_alcance, fuera_alcance = [], []
    for archivo in archivos:
        periodo = extraer_periodo(archivo.name)
        if PERIODO_INICIO <= periodo <= PERIODO_FIN:
            en_alcance.append(archivo)
        else:
            fuera_alcance.append((archivo, periodo))

    if fuera_alcance:
        print(f"  [i] Fuera de alcance (se conservan en raw, no se consolidan): "
              f"{', '.join(a.name for a, _ in fuera_alcance)}")

    todos = []
    print(f"  Procesando {len(en_alcance)} archivo(s) de '{indicador}'...")
    for archivo in en_alcance:
        print(f"  - {archivo.name}")
        todos.extend(extraer_archivo(archivo, hoja, indicador, columnas, tokens))
    return todos


# =========================================================================
# 4. VALIDACIÓN DE COMPLETITUD
# =========================================================================

def validar_calidad(df: pd.DataFrame) -> list:
    """
    Chequeos de CALIDAD del consolidado. Devuelve la lista de problemas
    encontrados (vacía = todo en orden).

    Por qué existe separado de validar_completitud: completitud responde
    "¿están todas las celdas?"; calidad responde "¿son creíbles?". Son dos
    preguntas distintas y una puede pasar mientras la otra falla: un mapa de
    columnas corrido da 100% de completitud con valores del segmento equivocado.

    Los tres chequeos son los que docs/limitaciones.md §7 declara. Antes eran
    una afirmación escrita a mano en un markdown; acá son salida de programa,
    que es lo único que un lector puede reproducir.

      1. DUPLICADOS de la clave del grano (periodo+banco+indicador+segmento).
         Un duplicado significa que un mes se procesó dos veces o que un Excel
         trae el banco repetido, y en cualquier promedio pesaría doble.
         Es la misma garantía que la UNIQUE KEY uq_grano_hecho en MySQL: el
         chequeo acá la anticipa, para no descubrirlo recién en la carga.

      2. RANGO: los dos indicadores son índices porcentuales, así que un valor
         negativo o mayor a 100 no es un dato malo, es un dato imposible —
         señal de columna corrida o de un decimal mal interpretado.

      3. CONTINUIDAD mensual: que haya 41 meses distintos no prueba que sean
         41 meses CONSECUTIVOS. Un mes faltante en el medio deja un hueco que
         ninguna serie temporal muestra como hueco: el gráfico simplemente une
         los dos puntos vecinos y la caída desaparece de la vista.
    """
    problemas = []
    print("\n" + "=" * 60)
    print("VALIDACIÓN DE CALIDAD")
    print("=" * 60)

    # 1. Duplicados de clave del grano.
    clave = ["periodo", "banco", "indicador", "segmento"]
    n_dup = int(df.duplicated(subset=clave).sum())
    print(f"  Duplicados de clave ({'+'.join(clave)}) : {n_dup}")
    if n_dup:
        problemas.append(f"{n_dup} fila(s) duplicada(s) en la clave del grano")
        for _, fila in df[df.duplicated(subset=clave, keep=False)].iterrows():
            print(f"      - {fila['periodo']} {fila['banco']} "
                  f"{fila['indicador']} {fila['segmento']}")

    # 2. Valores fuera del rango posible para un índice porcentual.
    fuera = df[(df["valor"] < 0) | (df["valor"] > 100)]
    print(f"  Valores negativos o > 100%             : {len(fuera)}")
    if len(fuera):
        problemas.append(f"{len(fuera)} valor(es) fuera del rango 0-100%")
        for _, fila in fuera.head(10).iterrows():
            print(f"      - {fila['periodo']} {fila['banco']} "
                  f"{fila['segmento']} = {fila['valor']}")

    # 3. Continuidad mensual, por indicador.
    for indicador, sub in df.groupby("indicador"):
        meses = sorted(pd.to_datetime(sub["periodo"]).dt.to_period("M").unique())
        esperados = pd.period_range(meses[0], meses[-1], freq="M")
        huecos = [str(m) for m in esperados if m not in set(meses)]
        # Se listan como máximo 6 huecos: si faltan 39 meses el problema no es
        # cuáles, es que la carpeta está incompleta, y una lista de 39 nombres
        # tapa el resto del informe de validación.
        resumen = ", ".join(huecos[:6]) + (f" (+{len(huecos) - 6} más)" if len(huecos) > 6 else "")
        print(f"  Meses continuos en {indicador:<20}: "
              f"{'sí, sin huecos' if not huecos else 'NO — faltan ' + resumen}"
              f"  ({meses[0]} → {meses[-1]}, {len(meses)} meses)")
        if huecos:
            problemas.append(f"{indicador}: faltan {len(huecos)} mes(es) — {resumen}")

    return problemas


def validar_completitud(df: pd.DataFrame) -> None:
    """
    Reporta cobertura de la matriz esperada:
        bancos (5) x meses x segmentos (6) x indicadores (2)

    No lanza excepción: imprime un resumen para que decidas qué hacer y lo
    documentes en docs/limitaciones.md (Día 4 del plan). También avisa de
    valores nulos, que suelen indicar un índice de columna mal configurado.
    """
    print("\n" + "=" * 60)
    print("VALIDACIÓN DE COMPLETITUD")
    print("=" * 60)

    if df.empty:
        print("  [X] No se extrajo ningún registro. Revisá hojas y columnas.")
        return

    for indicador, sub in df.groupby("indicador"):
        n_bancos = sub["banco"].nunique()
        n_meses = sub["periodo"].nunique()
        n_segmentos = sub["segmento"].nunique()
        nulos = sub["valor"].isna().sum()
        esperado = n_bancos * n_meses * n_segmentos

        print(f"\n  Indicador: {indicador}")
        print(f"    Bancos distintos     : {n_bancos} (esperado 5)")
        print(f"    Meses distintos      : {n_meses}")
        print(f"    Segmentos distintos  : {n_segmentos} (esperado 6)")
        print(f"    Filas                : {len(sub)} (esperado {esperado})")
        print(f"    Valores nulos        : {nulos}")
        if nulos > 0:
            # Desglose banco x segmento de los nulos.
            # ¿Por qué? Porque hay DOS causas muy distintas y el conteo total
            # no las distingue:
            #   (a) nulo ESTRUCTURAL: la CMF publica "---" porque el banco no
            #       opera ese segmento (Falabella y Ripley no tienen cartera
            #       'adeudado por bancos'). Es un dato ausente legítimo y se
            #       documenta en docs/limitaciones.md.
            #   (b) nulo por ERROR: un índice de columna mal configurado deja
            #       TODOS los bancos en nulo para un mismo segmento.
            # La firma los separa: si los nulos se concentran en pocos bancos
            # de un segmento es (a); si cubren los 5 bancos, es (b).
            detalle = (sub[sub["valor"].isna()]
                       .groupby(["segmento", "banco"]).size()
                       .reset_index(name="n"))
            for _, fila in detalle.iterrows():
                marca = "ERROR?" if fila["n"] == n_meses and \
                    detalle[detalle["segmento"] == fila["segmento"]]["banco"].nunique() == n_bancos \
                    else "estructural"
                print(f"      - {fila['segmento']:<20} {fila['banco']:<24} "
                      f"{fila['n']:>3} mes(es)  [{marca}]")

    # Cruce entre indicadores: meses donde falta uno de los dos.
    meses_por_ind = df.groupby("indicador")["periodo"].apply(set).to_dict()
    if len(meses_por_ind) == 2:
        (ind_a, meses_a), (ind_b, meses_b) = meses_por_ind.items()
        solo_a = sorted(meses_a - meses_b)
        solo_b = sorted(meses_b - meses_a)
        if solo_a:
            print(f"\n  [!] Meses solo en {ind_a}: {[str(m) for m in solo_a]}")
        if solo_b:
            print(f"  [!] Meses solo en {ind_b}: {[str(m) for m in solo_b]}")
        if not solo_a and not solo_b:
            print("\n  [OK] Ambos indicadores cubren exactamente los mismos meses.")


# =========================================================================
# 5. MODO INSPECCIONAR
# =========================================================================

def inspeccionar(ruta: str, hoja: str = None) -> None:
    """
    Imprime la grilla cruda de un archivo (primeras 40 filas x todas las
    columnas) con índices, para verificar los índices de COLUMNAS_MOROSIDAD / COLUMNAS_PROVISIONES
    contra un archivo real. Es la herramienta que hace confiable fijar
    columnas por índice.
    """
    ruta = Path(ruta)
    if hoja is None:
        # Deduce la hoja según la carpeta; si no, muestra las disponibles.
        if "morosidad" in normalizar(str(ruta)):
            hoja = HOJA_MOROSIDAD
        elif "provisiones" in normalizar(str(ruta)):
            hoja = HOJA_PROVISIONES
        else:
            hojas = pd.ExcelFile(ruta).sheet_names
            print(f"Hojas disponibles en {ruta.name}: {hojas}")
            print("Volvé a correr indicando la hoja con --hoja \"Nombre\".")
            return

    print(f"\nArchivo: {ruta.name}  |  Hoja: {hoja}")
    print(f"Período deducido del nombre: {extraer_periodo(ruta.name)}\n")

    grilla = leer_grilla(ruta, hoja)
    print(f"Dimensiones: {grilla.shape[0]} filas x {grilla.shape[1]} columnas\n")

    # Cabecera de índices de columna.
    ancho = 18
    encabezado = "fila |" + "".join(f"[{c}]".ljust(ancho) for c in range(grilla.shape[1]))
    print(encabezado)
    print("-" * len(encabezado))

    for idx in range(min(40, len(grilla))):
        celdas = []
        for c in range(grilla.shape[1]):
            v = grilla.iloc[idx, c]
            txt = "" if v is None or (isinstance(v, float) and v != v) else str(v)
            celdas.append(txt[:ancho - 1].ljust(ancho))
        print(f"{idx:>4} |" + "".join(celdas))

    print("\nTip: identificá la fila de un banco de alcance y leé en qué número")
    print("de columna [n] cae cada segmento. Ajustá COLUMNAS_MOROSIDAD / COLUMNAS_PROVISIONES con eso.")


# =========================================================================
# 6. FLUJO PRINCIPAL
# =========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Consolida los reportes CMF (morosidad + provisiones) a un CSV tidy."
    )
    parser.add_argument(
        "--inspeccionar", metavar="RUTA_XLSX",
        help="Imprime la grilla cruda de un Excel para verificar índices de columna."
    )
    parser.add_argument(
        "--hoja", default=None,
        help="Nombre de hoja a usar con --inspeccionar (si no, se deduce de la carpeta)."
    )
    # Por qué existe --estricto: sin él, un banco no encontrado o un mes
    # faltante terminan igual en "[OK] CSV consolidado escrito" con código de
    # salida 0. Eso sirve mientras se explora, pero convierte al script en algo
    # que no se puede encadenar: cualquier automatización que lo llame creería
    # que salió bien. Con --estricto, un problema de calidad devuelve 1 y corta
    # la cadena antes de que el CSV llegue a MySQL o al dashboard.
    parser.add_argument(
        "--estricto", action="store_true",
        help="Devuelve código de salida 1 si la validación de calidad encuentra "
             "problemas (para encadenar en un pipeline)."
    )
    args = parser.parse_args()

    # Modo 1: inspeccionar un archivo y salir.
    if args.inspeccionar:
        inspeccionar(args.inspeccionar, args.hoja)
        return

    # Modo 2 (por defecto): consolidar todo.
    print("Consolidando reportes CMF...\n")
    registros = []
    # El corrimiento de columnas se trata como error fatal, no como advertencia:
    # el mensaje explica qué columna dejó de ser la que era y el script termina
    # con código 1 sin escribir nada. Se atrapa acá para mostrarlo limpio en vez
    # de un traceback, que en un pipeline es la diferencia entre un aviso legible
    # y un log que nadie lee.
    try:
        registros += procesar_directorio(
            DIR_MOROSIDAD, HOJA_MOROSIDAD, INDICADOR_MOROSIDAD,
            COLUMNAS_MOROSIDAD, TOKENS_ENCABEZADO_MOROSIDAD)
        registros += procesar_directorio(
            DIR_PROVISIONES, HOJA_PROVISIONES, INDICADOR_PROVISIONES,
            COLUMNAS_PROVISIONES, TOKENS_ENCABEZADO_PROVISIONES)
    except ValueError as e:
        print(e)
        sys.exit(1)

    if not registros:
        print("\n[X] No se generó ningún registro. Revisá las carpetas data/raw.")
        sys.exit(1)

    df = pd.DataFrame(registros)

    # Orden estable de columnas y filas -> salida reproducible.
    df = df[["periodo", "anio", "mes", "banco", "grupo",
             "indicador", "segmento", "valor"]]
    df = df.sort_values(["indicador", "periodo", "banco", "segmento"]).reset_index(drop=True)

    validar_completitud(df)
    problemas = validar_calidad(df)

    # Escritura del CSV consolidado (solo en data/processed, nunca en raw).
    #
    # El CSV se escribe SIEMPRE, incluso con problemas: para diagnosticar un
    # duplicado o un valor imposible hay que poder mirarlo. Lo que cambia con
    # --estricto es el código de salida, no la escritura.
    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RUTA_SALIDA, index=False, encoding="utf-8-sig")
    print(f"\n[OK] CSV consolidado escrito en: {RUTA_SALIDA}")
    print(f"     {len(df)} filas x {df.shape[1]} columnas")

    if problemas:
        print(f"\n[!] La validación de calidad encontró {len(problemas)} problema(s):")
        for p in problemas:
            print(f"    - {p}")
        if args.estricto:
            print("    Modo --estricto: se corta con código de salida 1.")
            sys.exit(1)
        print("    Corré con --estricto para que esto devuelva código de salida 1.")
    else:
        print("     Validación de calidad: sin duplicados, sin valores fuera de "
              "rango, serie mensual continua.")


if __name__ == "__main__":
    main()
