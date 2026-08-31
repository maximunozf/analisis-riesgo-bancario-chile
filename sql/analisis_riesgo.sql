-- ===========================================================================
-- analisis-riesgo-bancario-chile — analisis SQL (Dias 6-8)
-- Base: riesgo_bancario_cmf · Motor: MySQL 8.0+
--
-- Pregunta que responde este archivo:
--   ¿El riesgo crediticio del retail financiero se mueve distinto al de la
--   banca tradicional? Medido en morosidad 90+, indice de provisiones y
--   cobertura (provisiones / morosidad).
--
-- TRES ADVERTENCIAS QUE APLICAN A TODO ESTE ARCHIVO:
--
-- 1. Los valores son INDICES PORCENTUALES, no montos. No se suman segmentos
--    ni bancos. Todo agregado aca es AVG(), nunca SUM().
-- 2. Los promedios por grupo son SIMPLES, no ponderados por tamaño de cartera:
--    AVG() le da a Banco de Chile el mismo peso que a Ripley. No es "la
--    morosidad del grupo", es "el promedio de las morosidades de sus miembros".
--    Ponderar exigiria saldos en pesos que estos dos reportes CMF no entregan.
-- 3. Salvo que se diga lo contrario, se analiza el segmento total_colocaciones
--    y se excluye adeudado_bancos (incluido_en_analisis = FALSE).
-- ===========================================================================

USE riesgo_bancario_cmf;


-- ---------------------------------------------------------------------------
-- 0. CONTROL DE GRANO — correr esto primero, siempre.
--
-- Por que: si este bloque no da 2460 / 41 / 5 / 6 / 2, cualquier numero de las
-- consultas siguientes es basura y no hay que interpretarlo.
-- ---------------------------------------------------------------------------
SELECT
    COUNT(*)                        AS filas,
    COUNT(DISTINCT id_tiempo)       AS meses,
    COUNT(DISTINCT id_banco)        AS bancos,
    COUNT(DISTINCT id_segmento)     AS segmentos,
    COUNT(DISTINCT indicador)       AS indicadores,
    SUM(valor IS NULL)              AS nulos_estructurales,
    ROUND(SUM(valor), 4)            AS suma_de_control
FROM fact_riesgo_crediticio;
-- Esperado: 2460 · 41 · 5 · 6 · 2 · 164 nulos · suma 8465.7966


-- ---------------------------------------------------------------------------
-- 1. EVOLUCION DEL SISTEMA (los 5 bancos juntos), mes a mes.
--
-- Por que empezar aca: antes de comparar los grupos hay que saber si el ciclo
-- de credito completo se movio. Si todo sube junto, la comparacion entre
-- grupos habla del ciclo; si no, habla de los modelos de negocio.
-- ---------------------------------------------------------------------------
SELECT
    anio_mes,
    ROUND(AVG(morosidad_90d),      3) AS mora_prom,
    ROUND(AVG(indice_provisiones), 3) AS provisiones_prom,
    ROUND(AVG(indice_cobertura),   3) AS cobertura_prom
FROM vw_riesgo_ancho
WHERE codigo_segmento = 'total_colocaciones'
GROUP BY anio_mes
ORDER BY anio_mes;


-- ---------------------------------------------------------------------------
-- 2. COMPARATIVO ENTRE GRUPOS — promedio anual.
--
-- Esta es la tabla que sostiene el insight central. Se lee por columna:
-- que le paso a la mora y que le paso a la cobertura en cada grupo.
--
-- 2026 son 5 meses (ene-may), no un año completo. Se deja igual porque el
-- promedio es de indices, no un acumulado: no se distorsiona por tener menos
-- meses, solo tiene menos evidencia detras. Declarado en hallazgos.md.
-- ---------------------------------------------------------------------------
SELECT
    tipo_institucion,
    anio,
    COUNT(DISTINCT anio_mes)          AS meses_observados,
    ROUND(AVG(morosidad_90d),      3) AS mora_prom,
    ROUND(AVG(indice_provisiones), 3) AS provisiones_prom,
    ROUND(AVG(indice_cobertura),   3) AS cobertura_prom
FROM vw_riesgo_ancho
WHERE codigo_segmento = 'total_colocaciones'
GROUP BY tipo_institucion, anio
ORDER BY tipo_institucion, anio;


-- ---------------------------------------------------------------------------
-- 3. LA BRECHA ENTRE GRUPOS, mes a mes.
--
-- Por que en pivote y no en filas: la pregunta del proyecto no es "cuanta mora
-- tiene cada grupo" sino "cuanto se separan y si esa distancia cambia". Eso
-- exige los dos grupos en la misma fila para restarlos.
--
-- brecha_pp = puntos porcentuales de diferencia (retail - tradicional).
-- ratio     = cuantas veces la mora del retail contiene a la de la banca.
--             El ratio importa porque una brecha de 2 pp sobre una base de 1%
--             y sobre una base de 4% no significan lo mismo.
-- ---------------------------------------------------------------------------
SELECT
    anio_mes,
    ROUND(AVG(CASE WHEN tipo_institucion = 'banca_tradicional' THEN morosidad_90d END), 3) AS mora_tradicional,
    ROUND(AVG(CASE WHEN tipo_institucion = 'retail_financiero' THEN morosidad_90d END), 3) AS mora_retail,
    ROUND(AVG(CASE WHEN tipo_institucion = 'retail_financiero' THEN morosidad_90d END)
        - AVG(CASE WHEN tipo_institucion = 'banca_tradicional' THEN morosidad_90d END), 3) AS brecha_pp,
    ROUND(AVG(CASE WHEN tipo_institucion = 'retail_financiero' THEN morosidad_90d END)
        / NULLIF(AVG(CASE WHEN tipo_institucion = 'banca_tradicional' THEN morosidad_90d END), 0), 2) AS ratio,
    ROUND(AVG(CASE WHEN tipo_institucion = 'banca_tradicional' THEN indice_cobertura END), 3) AS cobertura_tradicional,
    ROUND(AVG(CASE WHEN tipo_institucion = 'retail_financiero' THEN indice_cobertura END), 3) AS cobertura_retail
FROM vw_riesgo_ancho
WHERE codigo_segmento = 'total_colocaciones'
GROUP BY anio_mes
ORDER BY anio_mes;


-- ---------------------------------------------------------------------------
-- 4. PUNTA A PUNTA POR BANCO: primer mes vs ultimo mes.
--
-- Por que con CTE y no con fechas escritas a mano: si mañana se agregan los
-- meses de jun-2026 en adelante, la consulta sigue siendo correcta sin editarla.
-- Un literal '2026-05' seria una bomba de tiempo en un repo de portafolio.
-- ---------------------------------------------------------------------------
WITH bordes AS (
    SELECT MIN(id_tiempo) AS t_ini, MAX(id_tiempo) AS t_fin
    FROM vw_riesgo_ancho
    WHERE codigo_segmento = 'total_colocaciones'
),
puntas AS (
    SELECT
        v.nombre_banco,
        v.tipo_institucion,
        MAX(CASE WHEN v.id_tiempo = b.t_ini THEN v.morosidad_90d    END) AS mora_ini,
        MAX(CASE WHEN v.id_tiempo = b.t_fin THEN v.morosidad_90d    END) AS mora_fin,
        MAX(CASE WHEN v.id_tiempo = b.t_ini THEN v.indice_cobertura END) AS cob_ini,
        MAX(CASE WHEN v.id_tiempo = b.t_fin THEN v.indice_cobertura END) AS cob_fin
    FROM vw_riesgo_ancho v
    CROSS JOIN bordes b
    WHERE v.codigo_segmento = 'total_colocaciones'
      AND v.id_tiempo IN (b.t_ini, b.t_fin)
    GROUP BY v.nombre_banco, v.tipo_institucion
)
SELECT
    tipo_institucion,
    nombre_banco,
    ROUND(mora_ini, 3)            AS mora_ini,
    ROUND(mora_fin, 3)            AS mora_fin,
    ROUND(mora_fin - mora_ini, 3) AS delta_mora_pp,
    ROUND(cob_ini, 3)             AS cobertura_ini,
    ROUND(cob_fin, 3)             AS cobertura_fin,
    ROUND(cob_fin - cob_ini, 3)   AS delta_cobertura
FROM puntas
ORDER BY tipo_institucion, delta_mora_pp DESC;


-- ---------------------------------------------------------------------------
-- 5. SEGMENTACION POR CARTERA.
--
-- Por que importa: el total esconde de donde viene el movimiento. Dos bancos
-- con la misma mora total pueden tener carteras completamente distintas.
--
-- nivel_agregacion se usa para NO mezclar el total con sus partes en el mismo
-- grafico. Aca se piden solo los segmentos comparables entre los dos grupos.
-- ---------------------------------------------------------------------------
SELECT
    codigo_segmento,
    tipo_institucion,
    anio,
    ROUND(AVG(morosidad_90d),      3) AS mora_prom,
    ROUND(AVG(indice_provisiones), 3) AS provisiones_prom,
    ROUND(AVG(indice_cobertura),   3) AS cobertura_prom
FROM vw_riesgo_ancho
WHERE codigo_segmento IN ('comerciales', 'personas_total', 'consumo', 'vivienda')
GROUP BY codigo_segmento, tipo_institucion, anio
ORDER BY codigo_segmento, tipo_institucion, anio;


-- ---------------------------------------------------------------------------
-- 6. COBERTURA POR BANCO, promedio anual.
--
-- La cobertura es el KPI central del proyecto: cuantos pesos de provision hay
-- por cada peso de cartera morosa. Bajo 1 significa que el banco provisiona
-- menos de lo que tiene en mora de 90+ dias.
--
-- OJO al interpretarlo: la CMF NO exige cobertura > 1 sobre mora 90+. Las
-- garantias reales (hipotecarias sobre todo) reducen la provision exigida, asi
-- que un banco con mucha vivienda tiene cobertura estructuralmente baja sin
-- estar sub-provisionado. La cobertura sirve para comparar TRAYECTORIAS en el
-- tiempo, no para dictaminar suficiencia.
-- ---------------------------------------------------------------------------
SELECT
    nombre_banco,
    tipo_institucion,
    ROUND(AVG(CASE WHEN anio = 2023 THEN indice_cobertura END), 3) AS cob_2023,
    ROUND(AVG(CASE WHEN anio = 2024 THEN indice_cobertura END), 3) AS cob_2024,
    ROUND(AVG(CASE WHEN anio = 2025 THEN indice_cobertura END), 3) AS cob_2025,
    ROUND(AVG(CASE WHEN anio = 2026 THEN indice_cobertura END), 3) AS cob_2026
FROM vw_riesgo_ancho
WHERE codigo_segmento = 'total_colocaciones'
GROUP BY nombre_banco, tipo_institucion
ORDER BY tipo_institucion, cob_2026;


-- ---------------------------------------------------------------------------
-- 7. MESES CON COBERTURA BAJO 1, por banco.
--
-- Complementa la 6: un promedio anual de 0,95 puede ser un año entero apenas
-- bajo 1 o dos meses muy malos. Esta consulta distingue los dos casos.
-- ---------------------------------------------------------------------------
SELECT
    nombre_banco,
    COUNT(*)          AS meses_bajo_1,
    MIN(anio_mes)     AS primer_mes,
    MAX(anio_mes)     AS ultimo_mes,
    ROUND(MIN(indice_cobertura), 3) AS cobertura_minima
FROM vw_riesgo_ancho
WHERE codigo_segmento = 'total_colocaciones'
  AND indice_cobertura < 1
GROUP BY nombre_banco
ORDER BY meses_bajo_1 DESC;


-- ---------------------------------------------------------------------------
-- 8. PICO Y PISO DE MOROSIDAD POR BANCO, con el mes en que ocurrio.
--
-- Por que con window functions y no con dos subconsultas de MIN/MAX: un
-- MIN(morosidad) devuelve el valor pero pierde el mes. ROW_NUMBER() ordena la
-- serie de cada banco y se queda con la fila completa, mes incluido.
-- El rango (pico - piso) es una medida barata de volatilidad del riesgo.
-- ---------------------------------------------------------------------------
WITH ranked AS (
    SELECT
        nombre_banco,
        tipo_institucion,
        anio_mes,
        morosidad_90d,
        ROW_NUMBER() OVER (PARTITION BY nombre_banco ORDER BY morosidad_90d DESC) AS rn_max,
        ROW_NUMBER() OVER (PARTITION BY nombre_banco ORDER BY morosidad_90d ASC)  AS rn_min
    FROM vw_riesgo_ancho
    WHERE codigo_segmento = 'total_colocaciones'
)
SELECT
    tipo_institucion,
    nombre_banco,
    MAX(CASE WHEN rn_min = 1 THEN ROUND(morosidad_90d, 3) END) AS mora_minima,
    MAX(CASE WHEN rn_min = 1 THEN anio_mes END)                AS mes_minimo,
    MAX(CASE WHEN rn_max = 1 THEN ROUND(morosidad_90d, 3) END) AS mora_maxima,
    MAX(CASE WHEN rn_max = 1 THEN anio_mes END)                AS mes_maximo,
    ROUND(MAX(CASE WHEN rn_max = 1 THEN morosidad_90d END)
        - MAX(CASE WHEN rn_min = 1 THEN morosidad_90d END), 3) AS rango_pp
FROM ranked
WHERE rn_max = 1 OR rn_min = 1
GROUP BY tipo_institucion, nombre_banco
ORDER BY tipo_institucion, rango_pp DESC;


-- ---------------------------------------------------------------------------
-- 9. VARIACION MES A MES (para el grafico de tendencia del dashboard).
--
-- LAG() da el mes anterior dentro de la serie de cada banco. Es la base de la
-- medida DAX equivalente y sirve para detectar saltos bruscos que suelen ser
-- eventos contables, no deterioro real (ver limitaciones.md, comerciales de
-- Ripley).
-- ---------------------------------------------------------------------------
SELECT
    nombre_banco,
    anio_mes,
    ROUND(morosidad_90d, 3) AS mora,
    ROUND(morosidad_90d - LAG(morosidad_90d) OVER (PARTITION BY nombre_banco ORDER BY id_tiempo), 3) AS var_mes_pp
FROM vw_riesgo_ancho
WHERE codigo_segmento = 'total_colocaciones'
ORDER BY nombre_banco, anio_mes;


-- ---------------------------------------------------------------------------
-- 10. ¿SE MUEVEN JUNTOS? — correlacion de Pearson entre las dos series.
--
-- Es la prueba numerica de la pregunta del proyecto. MySQL no trae CORR(), asi
-- que se calcula con la formula directa sobre los 41 pares mensuales:
--     r = (n·Σxy − Σx·Σy) / sqrt( (n·Σx² − (Σx)²) · (n·Σy² − (Σy)²) )
--
-- Se calculan DOS correlaciones porque miden cosas distintas:
--   · niveles     — si las dos series suben y bajan juntas a lo largo del periodo.
--   · variaciones — si reaccionan igual mes a mes (esto captura el ciclo comun;
--                   los niveles pueden estar dominados por una tendencia).
-- ---------------------------------------------------------------------------
WITH mensual AS (
    SELECT
        id_tiempo,
        AVG(CASE WHEN tipo_institucion = 'banca_tradicional' THEN morosidad_90d END) AS x,
        AVG(CASE WHEN tipo_institucion = 'retail_financiero' THEN morosidad_90d END) AS y
    FROM vw_riesgo_ancho
    WHERE codigo_segmento = 'total_colocaciones'
    GROUP BY id_tiempo
),
con_variacion AS (
    SELECT
        x, y,
        x - LAG(x) OVER (ORDER BY id_tiempo) AS dx,
        y - LAG(y) OVER (ORDER BY id_tiempo) AS dy
    FROM mensual
)
SELECT
    'niveles' AS serie,
    COUNT(*)  AS n,
    ROUND((COUNT(*)*SUM(x*y) - SUM(x)*SUM(y))
        / SQRT((COUNT(*)*SUM(x*x) - POW(SUM(x),2)) * (COUNT(*)*SUM(y*y) - POW(SUM(y),2))), 3) AS correlacion
FROM con_variacion
UNION ALL
SELECT
    'variaciones mes a mes',
    COUNT(*),
    ROUND((COUNT(*)*SUM(dx*dy) - SUM(dx)*SUM(dy))
        / SQRT((COUNT(*)*SUM(dx*dx) - POW(SUM(dx),2)) * (COUNT(*)*SUM(dy*dy) - POW(SUM(dy),2))), 3)
FROM con_variacion
WHERE dx IS NOT NULL;
