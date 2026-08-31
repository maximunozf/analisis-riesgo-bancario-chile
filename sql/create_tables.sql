-- ===========================================================================
-- analisis-riesgo-bancario-chile — modelo relacional
-- Fuente: data/processed/consolidado_cmf.csv (2.460 filas, formato largo)
-- Motor: MySQL 8.0+ / InnoDB / utf8mb4
--
-- POR QUE UN ESQUEMA EN ESTRELLA Y NO UNA TABLA UNICA:
-- el CSV consolidado ya es analizable tal cual, pero deja tres cosas sin
-- lugar donde vivir: (1) la jerarquia de segmentos, (2) la clasificacion de
-- banco en tipo_institucion, que es el eje del insight central, y (3) el
-- calendario continuo que Power BI necesita para inteligencia de tiempo.
-- Las dimensiones son el lugar donde esas reglas quedan declaradas una vez y
-- se aplican en todas las consultas, en vez de repetirse en cada CASE WHEN.
-- ===========================================================================

DROP DATABASE IF EXISTS riesgo_bancario_cmf;
CREATE DATABASE riesgo_bancario_cmf
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE riesgo_bancario_cmf;


-- ---------------------------------------------------------------------------
-- dim_banco
--
-- tipo_institucion es el eje del insight central del proyecto: todo el
-- analisis compara retail financiero contra banca tradicional. Vive aca y no
-- como texto repetido en la tabla de hechos, porque es una regla de negocio
-- (una clasificacion que yo defini, no un dato de la CMF) y debe poder
-- auditarse en un solo lugar.
-- ---------------------------------------------------------------------------
CREATE TABLE dim_banco (
    id_banco          TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    codigo_banco      VARCHAR(30)  NOT NULL COMMENT 'Clave tecnica del CSV, snake_case',
    nombre_banco      VARCHAR(80)  NOT NULL COMMENT 'Nombre para mostrar en el dashboard',
    tipo_institucion  ENUM('banca_tradicional','retail_financiero') NOT NULL,

    PRIMARY KEY (id_banco),
    UNIQUE KEY uq_dim_banco_codigo (codigo_banco),
    KEY ix_dim_banco_tipo (tipo_institucion)
) ENGINE=InnoDB
  COMMENT='5 bancos del alcance. No es el sistema bancario chileno completo.';


-- ---------------------------------------------------------------------------
-- dim_tiempo
--
-- La clave es AAAAMM (202301) y no un AUTO_INCREMENT: es estable entre
-- recargas, legible al depurar una consulta y ordenable sin join. El costo es
-- que deja de ser una clave 100% opaca; el beneficio practico en un modelo
-- mensual de 41 filas lo justifica.
--
-- La tabla se genera completa y continua desde el rango del CSV. Un calendario
-- con huecos rompe la inteligencia de tiempo en DAX y hace que un mes sin dato
-- se lea como un mes en cero en vez de como un mes ausente.
-- ---------------------------------------------------------------------------
CREATE TABLE dim_tiempo (
    id_tiempo    INT UNSIGNED NOT NULL COMMENT 'AAAAMM, ej. 202301',
    fecha        DATE         NOT NULL COMMENT 'Primer dia del mes',
    anio         SMALLINT UNSIGNED NOT NULL,
    mes          TINYINT  UNSIGNED NOT NULL,
    trimestre    TINYINT  UNSIGNED NOT NULL,
    nombre_mes   VARCHAR(12)  NOT NULL,
    anio_mes     CHAR(7)      NOT NULL COMMENT 'AAAA-MM, para ejes de grafico',

    PRIMARY KEY (id_tiempo),
    UNIQUE KEY uq_dim_tiempo_fecha (fecha),
    KEY ix_dim_tiempo_anio (anio)
) ENGINE=InnoDB
  COMMENT='Calendario mensual continuo ene-2023 a may-2026 (41 meses).';


-- ---------------------------------------------------------------------------
-- dim_segmento
--
-- Esta es la dimension que evita el error mas caro del dataset. Los segmentos
-- NO estan al mismo nivel: total_colocaciones agrupa a comerciales y a
-- personas_total, y personas_total a su vez agrupa a consumo y vivienda.
-- Sin nivel_agregacion, un grafico que ponga los 6 segmentos lado a lado esta
-- mostrando totales y sus propias partes como si fueran categorias
-- comparables.
--
-- id_segmento_padre es una FK a esta misma tabla (autorreferencia): deja la
-- jerarquia declarada en los datos en vez de escrita en un comentario.
--
-- OJO — no es una jerarquia sumable. El campo valor es un INDICE porcentual,
-- no un monto: sumar los segmentos hijos no da el padre, y promediarlos
-- tampoco. Reconstruir el total exige los saldos en pesos, que estos dos
-- reportes de la CMF no entregan. La jerarquia sirve para FILTRAR y AGRUPAR,
-- nunca para agregar.
--
-- adeudado_bancos queda en nivel 1 sin padre: en el marco contable de la CMF
-- es un rubro distinto de las colocaciones a clientes, no una parte de ellas.
-- Se marca incluido_en_analisis = FALSE (ver docs/limitaciones.md).
-- ---------------------------------------------------------------------------
CREATE TABLE dim_segmento (
    id_segmento           TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    codigo_segmento       VARCHAR(30) NOT NULL,
    nombre_segmento       VARCHAR(60) NOT NULL,
    nivel_agregacion      TINYINT UNSIGNED NOT NULL
        COMMENT '1=rubro raiz, 2=subtotal, 3=detalle',
    id_segmento_padre     TINYINT UNSIGNED NULL
        COMMENT 'NULL en los rubros raiz. FK a esta misma tabla.',
    incluido_en_analisis  BOOLEAN NOT NULL DEFAULT TRUE
        COMMENT 'FALSE = se carga pero se excluye de consultas y dashboard',

    PRIMARY KEY (id_segmento),
    UNIQUE KEY uq_dim_segmento_codigo (codigo_segmento),
    CONSTRAINT fk_segmento_padre
        FOREIGN KEY (id_segmento_padre) REFERENCES dim_segmento (id_segmento)
) ENGINE=InnoDB
  COMMENT='Segmentos de cartera con su jerarquia. Los valores son indices %, no montos: no sumar.';


-- ---------------------------------------------------------------------------
-- fact_riesgo_crediticio
--
-- Grano: un banco, un mes, un segmento, un indicador.
-- 5 bancos x 41 meses x 6 segmentos x 2 indicadores = 2.460 filas.
--
-- POR QUE FORMATO LARGO Y NO UNA COLUMNA POR INDICADOR: agregar un tercer
-- indicador de la CMF manana es insertar filas, no alterar la tabla y
-- reescribir el script de carga. El costo es que la cobertura
-- (provisiones / morosidad) exige un self-join en vez de una division directa;
-- ese join esta resuelto una sola vez en la vista de mas abajo.
--
-- POR QUE indicador ES TEXTO Y NO UNA dim_indicador: son dos valores fijos,
-- sin atributos propios que describir. Una dimension de dos filas y cero
-- atributos agrega un join a cada consulta sin agregar informacion. Es una
-- dimension degenerada, y esta bien que lo sea.
--
-- POR QUE DECIMAL Y NO FLOAT/DOUBLE: son indicadores financieros. DOUBLE es
-- binario y arrastra error de representacion; dos corridas del mismo SUM()
-- pueden diferir en el ultimo decimal. En datos financieros eso no se discute.
--
-- valor ADMITE NULL a proposito: la CMF publica "---" cuando un banco no opera
-- un segmento. Falabella y Ripley no tienen adeudado_bancos, lo que da
-- 2 bancos x 41 meses x 2 indicadores = 164 nulos estructurales. Guardarlos
-- como 0 seria inventar un dato: 0% de morosidad y "no participa" no son lo
-- mismo, y el 0 contaminaria cualquier promedio.
-- ---------------------------------------------------------------------------
CREATE TABLE fact_riesgo_crediticio (
    id_hecho     INT UNSIGNED NOT NULL AUTO_INCREMENT,
    id_tiempo    INT UNSIGNED     NOT NULL,
    id_banco     TINYINT UNSIGNED NOT NULL,
    id_segmento  TINYINT UNSIGNED NOT NULL,
    indicador    ENUM('morosidad_90d','indice_provisiones') NOT NULL
        COMMENT 'Dimension degenerada: 2 valores fijos, sin atributos propios',
    valor        DECIMAL(9,6) NULL
        COMMENT 'Indice en %, ej. 4.871234. NULL = la CMF publica --- (segmento no operado)',

    PRIMARY KEY (id_hecho),

    -- Esta UNIQUE es la garantia de integridad del grano: si el script de
    -- carga se corre dos veces sin limpiar, o si un Excel de la CMF trae un
    -- banco repetido, el INSERT falla en vez de duplicar en silencio.
    UNIQUE KEY uq_grano_hecho (id_tiempo, id_banco, id_segmento, indicador),

    -- Indice pensado para la consulta tipica del proyecto: una serie temporal
    -- de un indicador. Va (indicador, id_tiempo) y no al reves porque el
    -- filtro por indicador siempre esta presente y es el mas selectivo.
    KEY ix_hecho_indicador_tiempo (indicador, id_tiempo),

    CONSTRAINT fk_hecho_tiempo
        FOREIGN KEY (id_tiempo)   REFERENCES dim_tiempo (id_tiempo),
    CONSTRAINT fk_hecho_banco
        FOREIGN KEY (id_banco)    REFERENCES dim_banco (id_banco),
    CONSTRAINT fk_hecho_segmento
        FOREIGN KEY (id_segmento) REFERENCES dim_segmento (id_segmento)
) ENGINE=InnoDB
  COMMENT='Tabla de hechos en formato largo. Grano: banco x mes x segmento x indicador.';


-- ---------------------------------------------------------------------------
-- vw_riesgo_ancho
--
-- El self-join que el formato largo cobra, resuelto una vez.
-- Deja una fila por banco x mes x segmento con los dos indicadores en columnas
-- y la cobertura ya calculada, que es la forma en que se consumen desde
-- Power BI y desde los analisis de los Dias 6-8.
--
-- NULLIF en el denominador evita la division por cero cuando un segmento tiene
-- morosidad 0,00 (pasa en adeudado_bancos de los tres bancos tradicionales).
-- Sin el, MySQL devuelve NULL igual, pero de forma implicita: dejarlo explicito
-- documenta que el caso se penso.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_riesgo_ancho AS
SELECT
    t.id_tiempo,
    t.fecha,
    t.anio,
    t.mes,
    t.anio_mes,
    b.codigo_banco,
    b.nombre_banco,
    b.tipo_institucion,
    s.codigo_segmento,
    s.nombre_segmento,
    s.nivel_agregacion,
    MAX(CASE WHEN f.indicador = 'morosidad_90d'      THEN f.valor END) AS morosidad_90d,
    MAX(CASE WHEN f.indicador = 'indice_provisiones' THEN f.valor END) AS indice_provisiones,
    MAX(CASE WHEN f.indicador = 'indice_provisiones' THEN f.valor END)
        / NULLIF(MAX(CASE WHEN f.indicador = 'morosidad_90d' THEN f.valor END), 0)
        AS indice_cobertura
FROM fact_riesgo_crediticio f
JOIN dim_tiempo   t ON t.id_tiempo   = f.id_tiempo
JOIN dim_banco    b ON b.id_banco    = f.id_banco
JOIN dim_segmento s ON s.id_segmento = f.id_segmento
GROUP BY
    t.id_tiempo, t.fecha, t.anio, t.mes, t.anio_mes,
    b.codigo_banco, b.nombre_banco, b.tipo_institucion,
    s.codigo_segmento, s.nombre_segmento, s.nivel_agregacion;
