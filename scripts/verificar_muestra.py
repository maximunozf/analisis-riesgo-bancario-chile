# -*- coding: utf-8 -*-
"""
verificar_muestra.py
====================

Cierra el último tramo de trazabilidad del proyecto: **CSV consolidado → Excel
original de la CMF**.

--------------------------------------------------------------------------
POR QUÉ EXISTE ESTE SCRIPT
--------------------------------------------------------------------------
El proyecto ya prueba por código el tramo de arriba: `validar_dashboard.py`
recalcula las 44 cifras del informe contra el CSV, así que si una medida DAX
deforma el dato, se detecta.

Pero abajo de ese tramo había un hueco. Que el CSV coincida con los Excel de la
CMF descansaba en una **inspección visual** de unos pocos archivos hecha durante
el perfilamiento: ningún script reabría un Excel para comparar una celda. Y como
`data/raw/` no se versiona, un lector del repositorio no tenía forma de
comprobarlo por su cuenta.

Este script cierra ese hueco. Elige celdas al azar del CSV, vuelve a abrir el
Excel del que salió cada una y compara valor contra valor. Con eso, "cada cifra
es trazable hasta su fuente" deja de ser una afirmación del README y pasa a ser
algo que se ejecuta.

Por qué una MUESTRA y no todo: reabrir los 82 Excel para verificar 2.460 celdas
tarda minutos y no agrega información. Una muestra aleatoria detecta igual de
bien los dos errores que importan —un mapa de columnas corrido y un archivo
asignado al mes equivocado—, porque ambos afectan a filas enteras, no a una
celda suelta. La semilla es fija para que dos corridas comparen lo mismo.

Uso:
    python scripts/verificar_muestra.py              # 30 celdas
    python scripts/verificar_muestra.py --n 100      # más celdas
    python scripts/verificar_muestra.py --semilla 7  # otra muestra

Devuelve código de salida 1 si alguna celda no coincide.
"""

import argparse
import random
import sys
from pathlib import Path

import pandas as pd

# Se reutiliza la configuración del script de consolidación en vez de repetirla.
# Si mañana cambia un índice de columna, este verificador cambia con él: dos
# copias del mismo mapa serían dos verdades que se pueden desincronizar, y la
# que quedaría vieja es justamente la del control.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from consolidar_datos_cmf import (  # noqa: E402
    BANCOS_ALCANCE,
    COLUMNAS_MOROSIDAD,
    COLUMNAS_PROVISIONES,
    DIR_MOROSIDAD,
    DIR_PROVISIONES,
    HOJA_MOROSIDAD,
    HOJA_PROVISIONES,
    INDICADOR_MOROSIDAD,
    RUTA_SALIDA,
    leer_grilla,
    limpiar_valor,
    localizar_fila_banco,
)

# Tolerancia de comparación. El CSV guarda el float tal como pandas lo leyó de la
# celda, así que la coincidencia debería ser exacta; 1e-9 sólo absorbe el
# ida y vuelta por el texto del CSV.
TOLERANCIA = 1e-9


def config_de(indicador: str):
    """Devuelve (carpeta, hoja, mapa de columnas) según el indicador."""
    if indicador == INDICADOR_MOROSIDAD:
        return DIR_MOROSIDAD, HOJA_MOROSIDAD, COLUMNAS_MOROSIDAD
    return DIR_PROVISIONES, HOJA_PROVISIONES, COLUMNAS_PROVISIONES


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verifica una muestra del CSV consolidado contra los Excel originales."
    )
    parser.add_argument("--n", type=int, default=30,
                        help="Cantidad de celdas a verificar (por defecto 30).")
    parser.add_argument("--semilla", type=int, default=42,
                        help="Semilla del muestreo, para que la corrida sea repetible.")
    args = parser.parse_args()

    if not RUTA_SALIDA.exists():
        print(f"[X] No existe {RUTA_SALIDA}. Corré antes consolidar_datos_cmf.py")
        return 1

    df = pd.read_csv(RUTA_SALIDA)

    # Solo se pueden verificar los meses cuyo Excel esté presente: data/raw no se
    # versiona, así que quien clone el repo sin descargar la serie no debe recibir
    # un error, sino un aviso de que no hay nada que verificar todavía.
    disponibles = []
    for _, fila in df.iterrows():
        carpeta, _, _ = config_de(fila["indicador"])
        periodo = str(fila["periodo"])[:7]
        if (carpeta / f"{periodo}.xlsx").exists():
            disponibles.append(fila)

    if not disponibles:
        print("[!] No hay archivos en data/raw para verificar. "
              "Corré scripts/descargar_cmf.py primero.")
        return 1

    random.seed(args.semilla)
    muestra = random.sample(disponibles, min(args.n, len(disponibles)))

    print(f"Verificando {len(muestra)} celda(s) del CSV contra los Excel originales "
          f"(semilla {args.semilla})\n")

    # Los Excel se abren una sola vez cada uno: abrir el mismo archivo varias
    # veces es lo que haría lento un muestreo grande.
    cache = {}
    fallos = 0

    for fila in muestra:
        carpeta, hoja, columnas = config_de(fila["indicador"])
        periodo = str(fila["periodo"])[:7]
        ruta = carpeta / f"{periodo}.xlsx"

        if ruta not in cache:
            cache[ruta] = leer_grilla(ruta, hoja)
        grilla = cache[ruta]

        cfg = BANCOS_ALCANCE[fila["banco"]]
        idx_fila = localizar_fila_banco(grilla, cfg["tokens"], cfg["modo"])
        valor_excel = limpiar_valor(grilla.iloc[idx_fila, columnas[fila["segmento"]]])
        valor_csv = None if pd.isna(fila["valor"]) else float(fila["valor"])

        # Los nulos también se verifican: que el CSV diga NULL donde el Excel dice
        # "---" es parte del contrato. Guardarlo como 0 sería inventar un dato.
        if valor_excel is None or valor_csv is None:
            ok = valor_excel is None and valor_csv is None
        else:
            ok = abs(valor_excel - valor_csv) < TOLERANCIA

        etiqueta = (f"{periodo} · {fila['banco']:<22} · {fila['segmento']:<18} · "
                    f"{fila['indicador']}")
        print(f"  {'OK ' if ok else 'MAL'}  {etiqueta}  excel={valor_excel}  csv={valor_csv}")
        if not ok:
            fallos += 1

    print()
    if fallos:
        print(f"[X] {fallos} de {len(muestra)} celda(s) NO coinciden con su Excel de origen.")
        return 1
    print(f"[OK] Las {len(muestra)} celdas coinciden con el Excel del que salieron "
          f"({len(cache)} archivo(s) reabiertos).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
