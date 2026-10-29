# Plan — Issue #32: reorganizar `scripts/` por tema

> Plan de trabajo vivo. Cada sección tiene un estado: `[OPEN]` o `[RESOLVED]`. Una sección `[RESOLVED]` no se vuelve a mostrar salvo que se reabra.

## 1. Layout [RESOLVED]

`scripts/` tiene 21 archivos (el issue decía 18; se sumaron `evaluate_ingestion`, `measure_latency` y `smoke_test_docker`). Se agrupan por rol:

```text
scripts/
  operate/      load_dataset, extract_dataset, manual_extraction, check_llm
  dataset/      check_dataset, orgchart, retrieval_bank*, chat_bank*
  quality/
    chat_judge, run_log                      (usados por las mediciones y por check_dataset)
    checks/     smoke_test*, check_chat_judge, check_bank_sensitivity      (sin LLM)
    evals/      evaluate_*, measure_latency                                (LLM real)
```

La carga y extracción de documentos como pipeline disparable por la app no entra acá: es el issue #48 (Post-V0). Mientras tanto `operate/` agrupa los scripts que lo hacen hoy.

## 2. Imports entre scripts: paquete con imports absolutos [RESOLVED]

Opción A. `scripts/` pasa a ser un paquete (`__init__.py` en cada carpeta) y los imports son absolutos (`from scripts.dataset.chat_bank import ...`).

- Los scripts que no importan `app` (`chat_bank`, `retrieval_bank`, `check_chat_judge`) agregan la raíz del repo a `sys.path`, como ya hacen los demás, porque al correr por ruta solo queda su propia carpeta.
- `pytest` queda con `pythonpath = ["."]`; se saca `scripts`.
- La importación dinámica de las preguntas de cada empresa pasa a `scripts.dataset.chat_bank_<empresa>` y `scripts.dataset.retrieval_bank_<empresa>`; desaparece el `sys.path.insert` de `retrieval_bank`.
- Los comandos siguen siendo `uv run scripts/<carpeta>/<script>.py`.
- Rechazadas: mantener nombres planos sumando cada subcarpeta al path (los `sys.path.insert` se multiplican y un nombre repetido se pisa sin avisar); `python -m` (cambia todos los comandos sin aportar más que A).
- Se registra en `docs/DECISIONS.md` al terminar.

## 3. Orden de ejecución [RESOLVED]

Un grupo por vez, con `git mv` (mueve el archivo conservando su historial). Después de cada grupo: ajustar sus imports y correr `pytest` y los comandos del CI.

1. `dataset/` → `pytest` y `check_dataset`.
2. `quality/` → `pytest` y los comandos del CI.
3. `operate/` → Dockerfile, y los smoke tests.

## 4. Referencias que apuntan a los scripts [OPEN]

Se actualizan al final, una vez movidos los tres grupos:

- `.github/workflows/ci.yml` (rutas de los comandos).
- `Dockerfile:17` (`COPY scripts/check_llm.py`); y la decisión "The Docker image carries only `scripts/check_llm.py`" en `docs/DECISIONS.md` (nota "Refined", una línea).
- `README.md` (unas 30 líneas), `CLAUDE.md` (dos líneas), `docs/` (incluida `DATASET.md`).
- Docstrings de uso de cada script y mensajes como `run scripts/chat_bank.py ... first`.
- `data/lamanija/ORGCHART.md` ("Generated ... by `scripts/orgchart.py`") y el generador que escribe esa línea.
- `scripts/measure_latency.py:245`, que imprime su propio comando en el reporte.
- `tests/`: imports de módulos movidos.

Rutas viejas dentro de `docs/PROGRESS.md`, `docs/PROGRESS_ARCHIVE.md` y `docs/DECISIONS.md` (no se reescriben) [RESOLVED]: no se agrega tabla de equivalencias, que sería una segunda fuente de verdad y cambiaría el contrato de documentación. Cada script conserva su nombre de archivo, que es único. El registro con fecha va en la entrada de `docs/PROGRESS.md` de #32, y el `CLAUDE.md` del proyecto suma una línea: las entradas anteriores al 2026-10-29 citan los scripts con ruta plana; se ubican con `find scripts -name <nombre>.py`. Nada en `docs/DECISIONS.md` ni en las entradas viejas.
