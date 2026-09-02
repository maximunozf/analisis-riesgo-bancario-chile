"""
cargar_mysql.py — carga data/processed/consolidado_cmf.csv al modelo relacional.

Uso:
    python -u scripts/cargar_mysql.py --recrear    # ejecuta el DDL y carga todo
    python -u scripts/cargar_mysql.py              # solo carga (la base ya existe)
    python -u scripts/cargar_mysql.py --validar    # no carga, solo revisa lo cargado

POR QUE UN SCRIPT Y NO EL ASISTENTE DE IMPORTACION DE WORKBENCH:
un import manual funciona una vez y no deja rastro. Aca la base es un artefacto
reproducible: cualquiera clona el repo, corre descargar_cmf.py, consolidar_datos_cmf.py
y este script, y llega exactamente a la misma base. Si manana la CMF publica junio de
2026, se vuelve a correr y no hay que recordar que se hizo a mano la vez anterior.

POR QUE LOS CATALOGOS ESTAN ESCRITOS ACA Y NO SE DEDUCEN DEL CSV:
el nombre para mostrar de cada banco, su tipo_institucion y la jerarquia de segmentos
son reglas de negocio que YO defini, no datos que la CMF publique. Derivarlas del CSV
las volveria invisibles. Escritas aca son revisables en el code review y fallan ruidosamente
si el CSV trae un banco o segmento que no esta declarado.
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import mysql.connector
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Rutas: siempre relativas a la raiz del repo, nunca al directorio desde donde
# se invoca el script. Asi `python scripts/cargar_mysql.py` y
# `cd scripts && python cargar_mysql.py` se comportan igual.
# ---------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parents[1]
RUTA_CSV = RAIZ / "data" / "processed" / "consolidado_cmf.csv"
RUTA_DDL = RAIZ / "sql" / "create_tables.sql"

# El nombre de la base es una constante y no una variable de .env a proposito:
# create_tables.sql tambien lo declara, y si vivieran en dos lugares distintos
# terminarian desincronizados. El .env guarda solo credenciales.
BASE_DATOS = "riesgo_bancario_cmf"

# Filas esperadas: 5 bancos x 41 meses x 6 segmentos x 2 indicadores.
FILAS_ESPERADAS = 2460

# Nulos estructurales esperados: Falabella y Ripley no operan adeudado_bancos,
# la CMF publica "---". 2 bancos x 41 meses x 2 indicadores.
NULOS_ESPERADOS = 164

# Valores que trae .env.example. Si alguno sigue en pie al conectar, es que el
# .env se copio de la plantilla y no se edito.
VALORES_DE_EJEMPLO = {"tu_password_aqui", "tu_usuario_aqui"}

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

# codigo_banco (como viene en el CSV) -> (nombre para mostrar, tipo_institucion)
CATALOGO_BANCOS = {
    "banco_falabella":       ("Banco Falabella",                        "retail_financiero"),
    "banco_ripley":          ("Banco Ripley",                           "retail_financiero"),
    "banco_de_chile":        ("Banco de Chile",                         "banca_tradicional"),
    # "Banco BCI" y no el nombre legal completo: el nombre largo se truncaba en los
    # rankings del dashboard ("Banco de Credito e Inversion...") y BCI es como lo
    # nombra el mercado. El nombre para mostrar se decide aqui, no en Power Query,
    # para que el modelo siga siendo la unica fuente de los rotulos.
    "banco_bci":             ("Banco BCI",                              "banca_tradicional"),
    "banco_santander_chile": ("Banco Santander-Chile",                  "banca_tradicional"),
}

# (codigo, nombre, nivel, codigo_padre, incluido_en_analisis)
# El orden importa: los padres se insertan antes que los hijos porque
# id_segmento_padre es una FK a esta misma tabla.
CATALOGO_SEGMENTOS = [
    ("total_colocaciones", "Total colocaciones",       1, None,                 True),
    ("adeudado_bancos",    "Adeudado por bancos",      1, None,                 False),
    ("comerciales",        "Comerciales",              2, "total_colocaciones", True),
    ("personas_total",     "Personas (total)",         2, "total_colocaciones", True),
    ("consumo",            "Consumo",                  3, "personas_total",     True),
    ("vivienda",           "Vivienda",                 3, "personas_total",     True),
]


def conectar(con_base=True):
    """Abre la conexion a MySQL leyendo credenciales desde .env.

    con_base=False se usa para correr el DDL, porque en ese momento la base
    todavia no existe (el script empieza con DROP DATABASE IF EXISTS).
    """
    ruta_env = RAIZ / ".env"
    if not ruta_env.exists():
        sys.exit(
            "ERROR: no existe el archivo .env en la raiz del repo.\n"
            "  Windows:  copy .env.example .env\n"
            "  Linux:    cp .env.example .env\n"
            "Despues editalo con tus credenciales reales."
        )
    load_dotenv(ruta_env)

    # El error mas probable la primera vez que alguien clona el repo no es una
    # variable ausente, sino una copiada de la plantilla y nunca editada. Sin
    # este chequeo, MySQL contesta "Access denied for user", que apunta al
    # servidor y manda a depurar el lugar equivocado: el archivo que hay que
    # arreglar es .env, no la instalacion de MySQL.
    problemas = []
    for variable in ("MYSQL_USER", "MYSQL_PASSWORD"):
        valor = os.getenv(variable)
        if not valor:
            problemas.append(f"{variable} esta vacia")
        elif valor in VALORES_DE_EJEMPLO:
            problemas.append(f"{variable} todavia tiene el valor de ejemplo ('{valor}')")
    if problemas:
        sys.exit(
            "ERROR en el archivo .env:\n  - "
            + "\n  - ".join(problemas)
            + "\nEditalo con tus credenciales reales de MySQL y volve a correr el script."
        )

    parametros = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        # autocommit apagado: la carga completa es una sola transaccion. Si algo
        # falla a mitad de camino, la base queda como estaba y no a medio poblar.
        "autocommit": False,
    }
    if con_base:
        parametros["database"] = BASE_DATOS

    return mysql.connector.connect(**parametros)


def separar_sentencias(texto_sql):
    """Parte un script SQL en sentencias ejecutables.

    Las lineas de comentario se descartan ANTES de partir por el punto y coma,
    y ese orden no es cosmetico: el DDL esta comentado en prosa y esa prosa
    contiene puntos y coma. Partiendo primero, una sentencia quedaba cortada a
    la mitad y MySQL recibia media frase en castellano como si fuera SQL.
    Detectado corriendo la carga de punta a punta, no leyendo el codigo.
    """
    lineas = [l for l in texto_sql.splitlines() if not l.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lineas).split(";") if s.strip()]


def ejecutar_ddl():
    """Corre sql/create_tables.sql sentencia por sentencia.

    El conector no ejecuta multiples sentencias en un solo execute() de forma
    portable entre versiones, de ahi que el archivo se parta antes de enviarlo.
    """
    if not RUTA_DDL.exists():
        sys.exit(f"ERROR: no encuentro {RUTA_DDL}")

    sentencias = separar_sentencias(RUTA_DDL.read_text(encoding="utf-8"))

    cnx = conectar(con_base=False)
    cur = cnx.cursor()
    for sentencia in sentencias:
        cur.execute(sentencia)
    cnx.commit()
    cur.close()
    cnx.close()
    print(f"DDL ejecutado: {len(sentencias)} sentencias. Base '{BASE_DATOS}' creada.")


def leer_csv():
    """Lee el consolidado y valida que no traiga sorpresas.

    encoding='utf-8-sig' y no 'utf-8': el CSV trae BOM (lo escribe pandas en
    Windows). Con 'utf-8' la primera columna se llamaria '\\ufeffperiodo' y el
    acceso df['periodo'] fallaria con KeyError.
    """
    df = pd.read_csv(RUTA_CSV, encoding="utf-8-sig", parse_dates=["periodo"])

    # Fallar temprano y ruidosamente si el CSV trae una categoria no declarada
    # en los catalogos: es mejor que insertarla con una FK inventada.
    bancos_csv = set(df["banco"].unique())
    if not bancos_csv <= set(CATALOGO_BANCOS):
        sys.exit(f"ERROR: bancos en el CSV sin declarar: {bancos_csv - set(CATALOGO_BANCOS)}")

    codigos_segmento = {s[0] for s in CATALOGO_SEGMENTOS}
    segmentos_csv = set(df["segmento"].unique())
    if not segmentos_csv <= codigos_segmento:
        sys.exit(f"ERROR: segmentos en el CSV sin declarar: {segmentos_csv - codigos_segmento}")

    print(f"CSV leido: {len(df):,} filas, {df['periodo'].min():%Y-%m} a {df['periodo'].max():%Y-%m}")
    return df


def poblar_dimensiones(cur, df):
    """Inserta las tres dimensiones y devuelve los mapas codigo -> id.

    Los mapas se arman en memoria y no con un SELECT por fila: 2.460 lookups
    contra la base para resolver FKs seria lento sin ninguna ganancia.
    """
    # --- dim_banco ---
    cur.executemany(
        "INSERT INTO dim_banco (codigo_banco, nombre_banco, tipo_institucion) VALUES (%s, %s, %s)",
        [(codigo, nombre, tipo) for codigo, (nombre, tipo) in CATALOGO_BANCOS.items()],
    )
    cur.execute("SELECT codigo_banco, id_banco FROM dim_banco")
    mapa_bancos = dict(cur.fetchall())

    # --- dim_segmento ---
    # Se insertan de a un nivel porque los hijos necesitan el id del padre,
    # que solo existe despues de insertarlo.
    mapa_segmentos = {}
    for nivel in (1, 2, 3):
        del_nivel = [s for s in CATALOGO_SEGMENTOS if s[2] == nivel]
        cur.executemany(
            "INSERT INTO dim_segmento "
            "(codigo_segmento, nombre_segmento, nivel_agregacion, id_segmento_padre, incluido_en_analisis) "
            "VALUES (%s, %s, %s, %s, %s)",
            [
                (codigo, nombre, niv, mapa_segmentos.get(padre), incluido)
                for codigo, nombre, niv, padre, incluido in del_nivel
            ],
        )
        cur.execute("SELECT codigo_segmento, id_segmento FROM dim_segmento")
        mapa_segmentos = dict(cur.fetchall())

    # --- dim_tiempo ---
    # Se genera un rango CONTINUO entre el primer y el ultimo mes del CSV, no
    # los meses distintos que aparecen en el. Si a la serie le faltara un mes,
    # el calendario igual lo tendria y ese hueco se veria como un corte en el
    # grafico en vez de disimularse uniendo los dos meses vecinos.
    meses = pd.date_range(df["periodo"].min(), df["periodo"].max(), freq="MS")
    cur.executemany(
        "INSERT INTO dim_tiempo (id_tiempo, fecha, anio, mes, trimestre, nombre_mes, anio_mes) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        [
            (
                f.year * 100 + f.month,       # id_tiempo = AAAAMM
                f.date(),
                f.year,
                f.month,
                (f.month - 1) // 3 + 1,
                MESES_ES[f.month - 1],
                f"{f.year}-{f.month:02d}",
            )
            for f in meses
        ],
    )

    print(
        f"Dimensiones pobladas: {len(mapa_bancos)} bancos, "
        f"{len(mapa_segmentos)} segmentos, {len(meses)} meses."
    )
    return mapa_bancos, mapa_segmentos


def poblar_hechos(cur, df, mapa_bancos, mapa_segmentos):
    """Inserta la tabla de hechos resolviendo las FKs con los mapas en memoria."""
    filas = [
        (
            fila.periodo.year * 100 + fila.periodo.month,
            mapa_bancos[fila.banco],
            mapa_segmentos[fila.segmento],
            fila.indicador,
            # None y no NaN: mysql-connector traduce None a NULL, pero NaN lo
            # insertaria como el literal 'nan' o fallaria segun la version.
            None if pd.isna(fila.valor) else round(float(fila.valor), 6),
        )
        for fila in df.itertuples(index=False)
    ]

    cur.executemany(
        "INSERT INTO fact_riesgo_crediticio "
        "(id_tiempo, id_banco, id_segmento, indicador, valor) VALUES (%s, %s, %s, %s, %s)",
        filas,
    )
    print(f"Hechos insertados: {cur.rowcount:,} filas.")


def validar(cur, df=None):
    """Compara lo cargado contra lo esperado. Devuelve True si todo cuadra.

    No alcanza con que el INSERT no reviente: hay que probar que lo que quedo
    en la base es lo mismo que habia en el CSV. Este bloque es lo que se muestra
    en una entrevista cuando preguntan como se valida una carga.
    """
    chequeos = []

    cur.execute("SELECT COUNT(*) FROM fact_riesgo_crediticio")
    filas = cur.fetchone()[0]
    chequeos.append(("Filas en la tabla de hechos", filas, FILAS_ESPERADAS, filas == FILAS_ESPERADAS))

    cur.execute("SELECT COUNT(*) FROM fact_riesgo_crediticio WHERE valor IS NULL")
    nulos = cur.fetchone()[0]
    chequeos.append(("Nulos estructurales", nulos, NULOS_ESPERADOS, nulos == NULOS_ESPERADOS))

    # Que los nulos sean SOLO adeudado_bancos de los dos bancos de retail.
    # Un nulo en otro lado seria un bug de la consolidacion, no un dato ausente.
    cur.execute(
        "SELECT COUNT(*) FROM fact_riesgo_crediticio f "
        "JOIN dim_segmento s ON s.id_segmento = f.id_segmento "
        "WHERE f.valor IS NULL AND s.codigo_segmento <> 'adeudado_bancos'"
    )
    nulos_raros = cur.fetchone()[0]
    chequeos.append(("Nulos fuera de adeudado_bancos", nulos_raros, 0, nulos_raros == 0))

    cur.execute("SELECT COUNT(*) FROM dim_tiempo")
    meses = cur.fetchone()[0]
    chequeos.append(("Meses en el calendario", meses, 41, meses == 41))

    # Cobertura pareja: cada indicador debe tener exactamente la mitad de las filas.
    cur.execute("SELECT indicador, COUNT(*) FROM fact_riesgo_crediticio GROUP BY indicador")
    por_indicador = dict(cur.fetchall())
    parejo = len(por_indicador) == 2 and len(set(por_indicador.values())) == 1
    chequeos.append(("Filas por indicador", str(por_indicador), "iguales entre si", parejo))

    cur.execute("SELECT MIN(valor), MAX(valor) FROM fact_riesgo_crediticio")
    minimo, maximo = cur.fetchone()
    rango_ok = minimo is not None and minimo >= 0 and maximo <= 100
    chequeos.append(("Rango de valores", f"{minimo} a {maximo}", "entre 0 y 100", rango_ok))

    # El chequeo mas fuerte: la suma total en la base contra la suma en el CSV.
    # Detecta filas perdidas, duplicadas o truncadas por el DECIMAL(9,6).
    if df is not None:
        cur.execute("SELECT SUM(valor) FROM fact_riesgo_crediticio")
        suma_db = float(cur.fetchone()[0])
        suma_csv = float(df["valor"].sum())
        # Tolerancia de 0,01: el CSV tiene precision float y la base redondea a
        # 6 decimales. Una diferencia mayor a eso no es redondeo, es un dato perdido.
        coincide = abs(suma_db - suma_csv) < 0.01
        chequeos.append(
            ("Suma de valores DB vs CSV", f"{suma_db:.4f}", f"{suma_csv:.4f}", coincide)
        )

    print("\n" + "=" * 78)
    print(f"{'CHEQUEO':<34} {'OBTENIDO':<22} {'ESPERADO':<16} {'':<4}")
    print("=" * 78)
    for nombre, obtenido, esperado, ok in chequeos:
        print(f"{nombre:<34} {str(obtenido):<22} {str(esperado):<16} {'OK' if ok else 'FALLA'}")
    print("=" * 78)

    todo_ok = all(c[3] for c in chequeos)
    print("\nVALIDACION COMPLETA: todo cuadra." if todo_ok
          else "\nVALIDACION CON FALLAS: revisar las lineas marcadas FALLA.")
    return todo_ok


def main():
    parser = argparse.ArgumentParser(description="Carga el consolidado CMF a MySQL.")
    parser.add_argument("--recrear", action="store_true",
                        help="Ejecuta sql/create_tables.sql antes de cargar (BORRA la base).")
    parser.add_argument("--validar", action="store_true",
                        help="Solo valida lo ya cargado, sin insertar nada.")
    args = parser.parse_args()

    if args.validar:
        cnx = conectar()
        cur = cnx.cursor()
        ok = validar(cur, leer_csv())
        cur.close()
        cnx.close()
        sys.exit(0 if ok else 1)

    if args.recrear:
        ejecutar_ddl()

    df = leer_csv()
    cnx = conectar()
    cur = cnx.cursor()
    try:
        mapa_bancos, mapa_segmentos = poblar_dimensiones(cur, df)
        poblar_hechos(cur, df, mapa_bancos, mapa_segmentos)
        ok = validar(cur, df)
        if ok:
            cnx.commit()
            print("\nCommit aplicado.")
        else:
            # Rollback si la validacion falla: es preferible una base vacia a una
            # base a medio cargar que despues alguien consulta creyendo que esta bien.
            cnx.rollback()
            print("\nROLLBACK aplicado: la base quedo sin cambios.")
            sys.exit(1)
    except mysql.connector.Error as e:
        cnx.rollback()
        sys.exit(f"\nERROR de MySQL, rollback aplicado: {e}")
    finally:
        cur.close()
        cnx.close()


if __name__ == "__main__":
    main()
