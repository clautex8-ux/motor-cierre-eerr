# Atajos del proyecto (requiere PYTHONPATH=src, lo define cada objetivo)
export PYTHONPATH := src

datos:        ## Genera los 6 meses de datos sintéticos
	python -m motor.generar_datos

cierre:       ## Procesa todos los meses disponibles en data/raw
	python -m motor.pipeline --todos

mes:          ## Procesa un mes: make mes MES=2026-09
	python -m motor.pipeline --mes $(MES)

kpis:         ## Calcula los KPIs IL3, IL4 e IL5
	python -m motor.kpis

test:         ## Ejecuta las pruebas automáticas
	python -m pytest -q

lint:         ## Revisa estilo del código
	ruff check src tests
