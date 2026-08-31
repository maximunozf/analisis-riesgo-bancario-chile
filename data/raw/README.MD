# Datos originales CMF

Esta carpeta contiene los Excel descargados de la CMF y **nunca se modifican**.

Los archivos no se versionan en el repositorio (ver `.gitignore`) por peso.
Para obtenerlos:

```bash
python scripts/descargar_cmf.py
```

Estructura esperada tras la descarga:

- `morosidad/AAAA-MM.xlsx` — Indicador de morosidad de 90 días o más
- `provisiones/AAAA-MM.xlsx` — Indicadores de Provisiones por Riesgo de Crédito

Período de alcance: enero 2023 – mayo 2026 (41 meses por fuente).