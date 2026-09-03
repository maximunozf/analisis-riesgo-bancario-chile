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

# Los cuadros de texto del informe son cifras escritas a mano: ningún control de Power BI
# las recalcula, y están en PROMEDIO ANUAL, no en el último mes. Son otra base de cálculo
# que la de los rankings, y confundirlas es lo que hace ver un defecto donde no lo hay
# (la brecha de consumo es 0,36 pp en may-2026 y 0,32 pp en promedio 2026: las dos ciertas).
PANTALLA_PORTADA_TEXTO = {  # (grupo, medida): (promedio 2023, promedio 2026)
    ("banca_tradicional", "morosidad_90d"): (1.70, 2.23),
    ("retail_financiero", "morosidad_90d"): (4.87, 4.24),
    ("banca_tradicional", "cobertura"):     (1.34, 1.09),
    ("retail_financiero", "cobertura"):     (1.45, 1.37),
}
PANTALLA_SEGMENTACION_TEXTO = {  # segmento: (brecha 2023, brecha 2026, decimales en pantalla)
    "consumo":            (1.88,  0.32, 2),
    "vivienda":           (7.2,  13.8,  1),
    "total_colocaciones": (3.17,  2.01, 2),
}

fallos = []


def comparar(etiqueta, calculado, pantalla, decimales=2):
    """Compara con la misma tolerancia que declara docs/validacion.md.

    `decimales` existe porque el informe no escribe todas sus cifras con la misma precisión:
    las medidas DAX salen formateadas a 2 decimales, pero los cuadros de texto citan algunas
    con 1 (7,2 · 13,8). Comparar 7,18 contra 7,2 exigiendo dos decimales marcaría un defecto
    donde solo hay una cifra redondeada a como está escrita.
    """
    ok = round(float(calculado), decimales) == round(float(pantalla), decimales)
    print(f"  {'OK ' if ok else 'MAL'}  {etiqueta:<52} pantalla={pantalla:>7}  dato={round(float(calculado), decimales):>7}")
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

    print("\nPortada — cuadro de texto (promedios anuales, no último mes)")
    anual = total.groupby(["grupo", "anio"])[["morosidad_90d", "cobertura"]].mean()
    for (grupo, medida), (v2023, v2026) in PANTALLA_PORTADA_TEXTO.items():
        comparar(f"{grupo} · {medida} 2023", anual.loc[(grupo, "2023"), medida], v2023)
        comparar(f"{grupo} · {medida} 2026", anual.loc[(grupo, "2026"), medida], v2026)

    print("\nSegmentación — cuadro de texto (brechas en promedio anual)")
    ba = p.pivot_table(index=["anio", "segmento"], columns="grupo", values="morosidad_90d")
    ba["brecha"] = ba["retail_financiero"] - ba["banca_tradicional"]
    for seg, (v2023, v2026, dec) in PANTALLA_SEGMENTACION_TEXTO.items():
        comparar(f"brecha {seg} 2023", ba.loc[("2023", seg), "brecha"], v2023, dec)
        comparar(f"brecha {seg} 2026", ba.loc[("2026", seg), "brecha"], v2026, dec)

    # El informe no cita un valor puntual para comerciales sino un rango ("~9-11 puntos"):
    # lo que se valida es que los dos extremos de la serie anual sigan cayendo dentro de él.
    com = ba.xs("comerciales", level="segmento")["brecha"]
    comparar("brecha comerciales · mínimo anual (pantalla ~9-11)", com.min(), 9.42)
    comparar("brecha comerciales · máximo anual (pantalla ~9-11)", com.max(), 11.06)

    print()
    if fallos:
        print(f"{len(fallos)} cifra(s) NO cuadran: {', '.join(fallos)}")
        return 1
    print("Todas las cifras del informe cuadran contra el CSV consolidado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
