"""
verificar_inventario.py — Chequeo de completitud de data/raw antes de consolidar.

Por que existe este script:
detectar un mes faltante ANTES de consolidar es mucho mas barato que descubrir
una serie interrumpida ya cargada en MySQL o graficada en Power BI. Un hueco de
un mes en una serie mensual no se nota a simple vista en un grafico, pero rompe
cualquier calculo de variacion mes a mes.

Uso:
    python scripts/verificar_inventario.py

Codigo de salida: 0 si no falta nada, 1 si hay huecos (util para encadenarlo
antes de la consolidacion sin correrla con datos incompletos).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Mismo alcance que descargar_cmf.py y consolidar_datos_cmf.py.
# Por que cierra en 2026-05: provisiones se publica con un mes de rezago frente a
# morosidad, y el indicador de cobertura (provisiones / cartera morosa) exige
# ambas fuentes del MISMO mes. El periodo cierra en el ultimo mes con las dos.
PERIODO_INICIO = "2023-01"
PERIODO_FIN = "2026-05"

CARPETAS = ("morosidad", "provisiones")

# Raiz calculada desde la ubicacion del script (scripts/ -> raiz), para poder
# ejecutarlo desde cualquier directorio sin romper las rutas.
RAIZ = Path(__file__).resolve().parents[1]
DATA_RAW = RAIZ / "data" / "raw"


def periodos_esperados(inicio: str, fin: str) -> list[str]:
    """Genera ['2023-01', ..., '2026-05'] sin depender de pandas."""
    a_i, m_i = (int(x) for x in inicio.split("-"))
    a_f, m_f = (int(x) for x in fin.split("-"))
    out: list[str] = []
    a, m = a_i, m_i
    while (a, m) <= (a_f, m_f):
        out.append(f"{a:04d}-{m:02d}")
        m += 1
        if m == 13:
            a, m = a + 1, 1
    return out


def main() -> int:
    esperados = periodos_esperados(PERIODO_INICIO, PERIODO_FIN)
    print(f"Alcance: {PERIODO_INICIO} a {PERIODO_FIN} ({len(esperados)} meses por reporte)")

    hay_huecos = False

    for carpeta in CARPETAS:
        ruta = DATA_RAW / carpeta
        presentes = {f.stem for f in ruta.glob("*.xlsx")}

        faltantes = [p for p in esperados if p not in presentes]
        # "extras" no es un error: morosidad/2026-06 se conserva por la regla de
        # nunca borrar data/raw, pero queda fuera del consolidado.
        extras = sorted(presentes - set(esperados))
        # Un .tmp sobreviviente delata una descarga cortada a la mitad.
        parciales = sorted(f.name for f in ruta.glob("*.tmp"))

        print(f"\n[{carpeta}] {len(esperados) - len(faltantes)}/{len(esperados)} en alcance")
        print(f"  faltantes: {faltantes or 'ninguno'}")
        print(f"  fuera de alcance (se conservan, no se consolidan): {extras or 'ninguno'}")
        if parciales:
            print(f"  ATENCION descargas incompletas (.tmp): {parciales}")
            hay_huecos = True
        if faltantes:
            hay_huecos = True

    if hay_huecos:
        print("\nInventario INCOMPLETO. Volver a correr: python scripts/descargar_cmf.py")
        return 1

    print("\nInventario COMPLETO. Listo para consolidar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
