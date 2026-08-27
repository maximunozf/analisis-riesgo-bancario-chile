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
    (COLUMNAS_SEGMENTO). Es defendible fijarlas porque su estabilidad se
    verificó manualmente en 5 meses distintos.

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
   / ajustás el diccionario COLUMNAS_SEGMENTO de abajo.

2) Consolidar todo:

       python consolidar_datos_cmf.py

   Lee las dos carpetas, valida completitud y escribe el CSV consolidado.

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

# Hoja a leer en cada tipo de reporte (Hallazgo #1).
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
# --- VERIFICAR CON --inspeccionar ANTES DE CONFIAR EN ESTOS NÚMEROS ---
# Son estables en todo el período (Hallazgo #2), pero como el perfilamiento no
# registró el índice numérico exacto de cada columna, corré primero el modo
# inspeccionar y ajustá estos valores a lo que veas en el archivo real.
#
# Estructura documentada de columnas:
#   Total | Comerciales | Personas(Total | Consumo | Vivienda) | Adeudado bancos
COLUMNAS_SEGMENTO = {
    "total_colocaciones": 2,   # Cartera total
    "comerciales":        3,   # Colocaciones comerciales
    "personas_total":     4,   # Personas (total)
    "consumo":            5,   # Personas - consumo
    "vivienda":           6,   # Personas - vivienda
    "adeudado_bancos":    7,   # Adeudado por bancos
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
    if normalizar(texto) in {"-", "s/i", "n/d", "nd", "na", "n.a."}:
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

def leer_grilla(ruta: Path, hoja: str) -> pd.DataFrame:
    """
    Lee la hoja indicada como grilla cruda, sin interpretar encabezados.

    header=None: NO tratamos ninguna fila como encabezado, porque el nº de
    filas de encabezado varía entre meses (Hallazgo #3). Preferimos la grilla
    completa y localizamos los datos nosotros mismos.

    dtype=object: leemos todo como texto/objeto para no perder ceros ni que
    pandas convierta a un tipo inesperado antes de que limpiemos nosotros.
    """
    try:
        return pd.read_excel(ruta, sheet_name=hoja, header=None, dtype=object)
    except ValueError as e:
        # Típicamente: la hoja no existe con ese nombre.
        raise ValueError(
            f"No pude leer la hoja '{hoja}' en {ruta.name}. "
            f"Verificá el nombre exacto de la hoja. Detalle: {e}"
        )


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


def extraer_archivo(ruta: Path, hoja: str, indicador: str) -> list:
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

    for banco, cfg in BANCOS_ALCANCE.items():
        fila = localizar_fila_banco(grilla, cfg["tokens"], cfg["modo"])
        if fila is None:
            # El banco no está en este mes: se deja constancia pero no se corta.
            print(f"    [!] {banco} no encontrado en {ruta.name}")
            continue

        for segmento, col in COLUMNAS_SEGMENTO.items():
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


def procesar_directorio(directorio: Path, hoja: str, indicador: str) -> list:
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

    todos = []
    print(f"  Procesando {len(archivos)} archivo(s) de '{indicador}'...")
    for archivo in archivos:
        print(f"  - {archivo.name}")
        todos.extend(extraer_archivo(archivo, hoja, indicador))
    return todos


# =========================================================================
# 4. VALIDACIÓN DE COMPLETITUD
# =========================================================================

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
            print("      -> Nulos altos suelen indicar un índice de COLUMNAS_SEGMENTO")
            print("         mal configurado. Verificá con --inspeccionar.")

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
    columnas) con índices, para verificar los índices de COLUMNAS_SEGMENTO
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
    print("de columna [n] cae cada segmento. Ajustá COLUMNAS_SEGMENTO con eso.")


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
    args = parser.parse_args()

    # Modo 1: inspeccionar un archivo y salir.
    if args.inspeccionar:
        inspeccionar(args.inspeccionar, args.hoja)
        return

    # Modo 2 (por defecto): consolidar todo.
    print("Consolidando reportes CMF...\n")
    registros = []
    registros += procesar_directorio(DIR_MOROSIDAD, HOJA_MOROSIDAD, INDICADOR_MOROSIDAD)
    registros += procesar_directorio(DIR_PROVISIONES, HOJA_PROVISIONES, INDICADOR_PROVISIONES)

    if not registros:
        print("\n[X] No se generó ningún registro. Revisá las carpetas data/raw.")
        sys.exit(1)

    df = pd.DataFrame(registros)

    # Orden estable de columnas y filas -> salida reproducible.
    df = df[["periodo", "anio", "mes", "banco", "grupo",
             "indicador", "segmento", "valor"]]
    df = df.sort_values(["indicador", "periodo", "banco", "segmento"]).reset_index(drop=True)

    validar_completitud(df)

    # Escritura del CSV consolidado (solo en data/processed, nunca en raw).
    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RUTA_SALIDA, index=False, encoding="utf-8-sig")
    print(f"\n[OK] CSV consolidado escrito en: {RUTA_SALIDA}")
    print(f"     {len(df)} filas x {df.shape[1]} columnas")


if __name__ == "__main__":
    main()
