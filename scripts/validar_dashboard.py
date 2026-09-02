"""
Validación cruzada del dashboard Power BI contra el CSV consolidado.

Por qué existe este script y no una revisión a ojo:
una medida DAX mal escrita no produce ningún error — devuelve un número plausible.
Los tres defectos documentados en docs/validacion.md (sección 5) se veían bien en pantalla.
La única forma de detectarlos es recalcular la cifra desde el dato y comparar.

Por qué valida contra el CSV y no contra MySQL:
el .pbix se alimenta del mismo CSV consolidado. Cruzar el dashboard contra su propia fuente
prueba que la capa DAX no deformó el dato, que es exactamente lo que este control busca.
Que el CSV coincida con los Excel de la CMF lo prueban consolidar_datos_cmf.py y
verificar_inventario.py, no este script.

Tolerancia: las medidas DAX están formateadas a 2 decimales. Una cifra cuadra si
round(valor_recalculado, 2) == valor_en_pantalla. Una diferencia mayor es un defecto real.

Uso:
    python scripts/validar_dashboard.py
Devuelve código de salida 1 si alguna cifra no cuadra, para poder encadenarlo antes de publicar.
"""

from pathlib import Path
import sys

import pandas as pd

CSV = Path(__file__).resolve().parents[1] / "data" / "processed" / "consolidado_cmf.csv"

# Lo que el informe muestra HOY, transcrito a mano desde el .pbix.
# Es la mitad del contrato: si alguien edita un visual y no actualiza esto, el script falla.
PANTALLA_COMPARATIVO = {
    # banco                  : (mora may-2026, cobertura may-2026, Δ cobertura desde ene-2023)
    "banco_ripley":           (4.91, 1.60,  0.13),
    "banco_falabella":        (3.33, 1.18, -0.48),
    "banco_santander_chile":  (2.95, 1.07, -0.25),
    "banco_bci":              (1.90, 0.90, -0.32),
    "banco_de_chile":         (1.63, 1.29, -0.53),
}
PANTALLA_PORTADA = {"retail_financiero": 1.37, "banca_tradicional": 1.09}
PANTALLA_BRECHAS_MAY_2026 = {"comerciales": 11.62, "consumo": 0.36, "vivienda": 13.68}
PANTALLA_CONSUMO = {  # (2023, 2026)
    "retail_financiero": (4.04, 2.54),
    "banca_tradicional": (2.16, 2.22),
}
PANTALLA_MESES_BAJO_1 = {"banco_bci": 25, "banco_santander_chile": 9}

fallos = []


def comparar(etiqueta, calculado, pantalla):
    """Compara con la misma tolerancia que declara docs/validacion.md."""
    ok = round(float(calculado), 2) == round(float(pantalla), 2)
    print(f"  {'OK ' if ok else 'MAL'}  {etiqueta:<52} pantalla={pantalla:>7}  dato={round(float(calculado), 2):>7}")
    if not ok:
        fallos.append(etiqueta)


def main():
    d = pd.read_csv(CSV)

    # El grano es largo (una fila por indicador); la cobertura exige las dos medidas en la
    # misma fila, así que se pivotea. Es el equivalente de la vista vw_riesgo_ancho en SQL.
    p = (
        d.pivot_table(
            index=["periodo", "banco", "grupo", "segmento"],
            columns="indicador",
            values="valor",
        )
        .reset_index()
    )
    p["cobertura"] = p["indice_provisiones"] / p["morosidad_90d"]
    p["anio"] = p["periodo"].str[:4]

    total = p[p.segmento == "total_colocaciones"]
    # El último y el primer mes se derivan del dato, nunca se escriben a mano:
    # es la misma regla que MAX(id_tiempo) en SQL y el MAXX sobre meses con dato en DAX.
    mes_fin, mes_ini = total.periodo.max(), total.periodo.min()

    print(f"\nSerie: {mes_ini} → {mes_fin}  ({total.periodo.nunique()} meses, {len(d)} filas)\n")

    print("Comparativo — 15 valores (5 bancos × mora, cobertura, variación)")
    fin = total[total.periodo == mes_fin].set_index("banco")
    ini = total[total.periodo == mes_ini].set_index("banco")
    for banco, (mora, cob, var) in PANTALLA_COMPARATIVO.items():
        comparar(f"{banco} · mora {mes_fin[:7]}", fin.loc[banco, "morosidad_90d"], mora)
        comparar(f"{banco} · cobertura {mes_fin[:7]}", fin.loc[banco, "cobertura"], cob)
        comparar(f"{banco} · Δ cobertura", fin.loc[banco, "cobertura"] - ini.loc[banco, "cobertura"], var)

    print("\nPortada — KPI de cobertura 2026 por grupo")
    kpi = total[total.anio == "2026"].groupby("grupo")["cobertura"].mean()
    for grupo, valor in PANTALLA_PORTADA.items():
        comparar(f"{grupo} · cobertura 2026", kpi[grupo], valor)

    print("\nSegmentación — brechas de morosidad en el último mes")
    u = p[p.periodo == mes_fin].pivot_table(index="segmento", columns="grupo", values="morosidad_90d")
    for seg, valor in PANTALLA_BRECHAS_MAY_2026.items():
        comparar(f"brecha {seg}", u.loc[seg, "retail_financiero"] - u.loc[seg, "banca_tradicional"], valor)

    print("\nSegmentación — morosidad en consumo, punta a punta")
    consumo = p[p.segmento == "consumo"].groupby(["grupo", "anio"])["morosidad_90d"].mean()
    for grupo, (v2023, v2026) in PANTALLA_CONSUMO.items():
        comparar(f"consumo {grupo} 2023", consumo[(grupo, "2023")], v2023)
        comparar(f"consumo {grupo} 2026", consumo[(grupo, "2026")], v2026)

    print("\nCuadro de hallazgo — cifras escritas a mano en el informe")
    bajo_1 = total[total.cobertura < 1].groupby("banco").size()
    for banco, meses in PANTALLA_MESES_BAJO_1.items():
        comparar(f"{banco} · meses con cobertura < 1", bajo_1.get(banco, 0), meses)
    otros = set(bajo_1.index) - set(PANTALLA_MESES_BAJO_1)
    comparar("ningún otro banco baja de 1", len(otros), 0)

    # "Ripley es el único que reforzó su cobertura desde 2023": debe haber exactamente un Δ > 0.
    suben = sum(1 for b in PANTALLA_COMPARATIVO if fin.loc[b, "cobertura"] > ini.loc[b, "cobertura"])
    comparar("bancos que suben cobertura (el informe dice 1)", suben, 1)

    print()
    if fallos:
        print(f"{len(fallos)} cifra(s) NO cuadran: {', '.join(fallos)}")
        return 1
    print("Todas las cifras del informe cuadran contra el CSV consolidado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
