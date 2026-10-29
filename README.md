# Motor de cierre EERR con alertas de fuga de ingresos

Producto de datos que automatiza el cierre mensual del Estado de Resultados (EERR) de una empresa BPO multipaís:
consolida la base contable del ERP, valida su calidad, distribuye gerencias, áreas STAFF, OH Latam e impuesto a cada
proyecto con cuadratura exacta, y alerta las diferencias entre ingreso provisionado y facturado.

**Autor:** Claudio Choque Peña · Proyecto final individual · Diploma Ciencia de Datos para las Finanzas, FEN U. de Chile

> **Declaración de datos.** Todos los archivos de `data/` son **sintéticos, anonimizados y escalados** por seguridad de
> la información. Replican la estructura real del extracto EERR del ERP (27 columnas, CSV `;`, latin1) y las reglas de
> negocio del cierre, pero proyectos, clientes y montos son ficticios. Se generan con `motor.generar_datos`.

![Arquitectura](docs/img/arquitectura.png)

## Inicio rápido

```bash
pip install -r requirements.txt
export PYTHONPATH=src            # en Windows: set PYTHONPATH=src

python -m motor.generar_datos    # 6 meses sintéticos (abr–sep 2026) en data/raw
python -m motor.pipeline --todos # cierra todos los meses
python -m motor.kpis             # KPIs IL3, IL4, IL5 -> output/kpis_producto.csv
python -m pytest -q              # 16 pruebas de calidad y cuadratura
```

Con `make`: `make datos`, `make cierre`, `make mes MES=2026-09`, `make kpis`, `make test`, `make lint`.

## Estructura

```
motor-cierre-eerr/
├── config/reglas.yaml          # parámetros de negocio versionados (tasas, criterios, umbrales, línea base)
├── data/
│   ├── raw/                    # Base_EERR, Provision_Ingresos y Facturacion por mes (sintéticos)
│   └── maestros/               # maestro de proyectos (FTE, línea) y mapeo de campañas
├── src/motor/
│   ├── extraer.py              # capa de entrada: lectura y contrato de estructura
│   ├── validar.py              # capa de calidad (IL3): normalización, 7 reglas, cuarentena
│   ├── distribuir.py           # reglas de distribución con cuadratura exacta
│   ├── alertar.py              # conciliación provisión vs. facturación
│   ├── exportar.py             # Excel formato IBR y tabla para Power BI
│   ├── pipeline.py             # orquestador + registro de ejecución (IL4)
│   ├── kpis.py                 # KPIs del producto por nivel de madurez
│   └── generar_datos.py        # generador de datos sintéticos
├── tests/                      # pytest: validación, distribución, alertas, punta a punta
├── logs/
│   ├── ejecuciones.csv         # una fila por corrida: estado, tiempos, calidad, cuadratura, alertas
│   └── seguimiento_productividad.csv  # horas de cierre por mes (seguimiento IL5)
├── output/                     # EERR_Distribuido_AAAA-MM.xlsx, alertas, powerbi/, kpis_producto.csv
├── docs/                       # diagramas (HTML -> PNG) y gráficos del informe
└── .github/workflows/ci.yml    # CI: ruff + pytest + corrida de humo en cada push
```

## Reglas de negocio

| Regla | Qué hace | Base de prorrateo |
|---|---|---|
| Gerencias de línea | Reparte cada fila de "Gerencia X" entre los proyectos de su misma línea | % de ingresos del proyecto en la línea |
| STAFF | Reparte cada fila STAFF según el criterio de la columna `Tabla` | Ingresos Local, Offshore, Local + Offshore o FTE |
| OH Latam | Crea un cargo por proyecto | -3% de los ingresos del proyecto |
| Impuesto a la renta | Crea un cargo por proyecto (los de pérdida generan crédito) | -27% del RAI del proyecto |

La distribución es fila a fila: cada fila origen se reemplaza por N filas destino que conservan toda la información
contable y quedan marcadas en la columna `Cross` (`Cross_gerencia`, `Cross_STAFF`, `Calculo_OH`, `Calculo_Impuesto`).
El redondeo es a pesos y el residuo va al destino de mayor base: **la cuadratura contra el origen es siempre $0**, y si no
lo es la corrida falla sin publicar salidas.

## Contrato de datos (IL3)

| Regla | Acción si no se cumple |
|---|---|
| R1 proyecto informado | cuarentena |
| R2 código existe en el maestro | cuarentena |
| R3 línea de negocio válida (se corrige desde el maestro si el código existe) | corrección automática o cuarentena |
| R4 monto numérico | cuarentena |
| R5 saldo = haber − debe | cuarentena |
| R6 mes coherente con el archivo | cuarentena |
| R7 fila STAFF con criterio de distribución válido | cuarentena |

Las filas en cuarentena quedan en la hoja `Cuarentena` del Excel con su motivo, para revisión de Control de Gestión.

## KPIs del producto

| Nivel | KPI | Meta |
|---|---|---|
| IL3 | % de filas con proyecto, línea y cuenta válidos | ≥ 99,5% |
| IL3 | Diferencia de cuadratura origen vs. distribuido | $0 |
| IL4 | % de ejecuciones mensuales sin error | ≥ 99% |
| IL4 | Tiempo de ejecución por cierre | < 60 s |
| IL5 | Horas de cierre por mes (40 h manual → meta 16 h) | ahorro ≥ 24 h/mes |
| IL5 | Aumento de productividad del cierre (horas ahorradas / horas base) | ≥ 60% |

El IL5 se mide con `logs/seguimiento_productividad.csv`: Control de Gestión registra las horas efectivas de cada cierre
con el motor; `motor.kpis` compara contra la línea base manual y marca el KPI como *Pendiente* mientras no haya
mediciones reales.

## Mantenimiento

- **Versionado:** código y `config/reglas.yaml` en Git; un cambio de tasa o criterio es un commit revisable.
- **CI:** cada push ejecuta lint, pruebas de cuadratura y una corrida de humo; el Excel resultante queda como artefacto.
- **Monitoreo:** `logs/ejecuciones.csv` y `logs/motor.log` registran cada corrida; `motor.kpis` resume el estado.
- **Responsable:** Jefe de Control de Gestión (dueño del producto y de las reglas).
- **Próximo paso:** reemplazar la lectura de CSV por extracción SuiteQL directa del ERP cuando TI habilite el acceso.
