# Repository Guidelines

## Project Structure & Module Organization

This mushroom forecast map combines static forest habitat scores with weather forecasts.

- `pipeline/`: BDL ingestion, habitat and terrain processing, PMTiles generation, and R2 publishing.
- `forecast/`: weather retrieval, species models, scheduled runs, and health checks.
- `web/`: static frontend; ES modules in `js/`, styles in `css/`, vendored libraries in `vendor/`, and service worker files at the root.
- `tests/` and `web/tests/`: Python and JavaScript tests; shared datasets in `tests/fixtures/`.
- `species.yaml` and `content/gatunki.yaml`: species parameters and display content.
- `docs/data/`: data contracts and source documentation; `docs/superpowers/`: specifications and implementation plans.

## Build, Test, and Development Commands

Run commands from the repository root.

- `python -m venv .venv` then `.venv/bin/pip install -r requirements-dev.txt -r pipeline/requirements.txt`: prepare Python dependencies, including forecast dependencies.
- `.venv/bin/pytest -v`: run the Python suite.
- `node --test web/tests/*.test.js`: run frontend tests; pass the file glob explicitly for Node 22.
- `docker compose -f docker-compose.local.yml up --build -d`: build and serve locally at `http://localhost:8080`, using data from `pipeline/data/out/`.
- `docker compose -f docker-compose.local.yml --profile forecast run --rm forecast`: generate local weather data using Open-Meteo.
- `python -m pipeline.ingest`: ingest local BDL packages. Follow README prerequisites before running `pipeline.build` inside the pipeline image, which supplies tippecanoe.

Use Compose or a server supporting HTTP Range requests for PMTiles.

## Coding Style & Naming Conventions

Follow surrounding code: Python uses four spaces, `snake_case` functions, `PascalCase` classes, and type hints; JavaScript uses two spaces, ES modules, `camelCase` functions, double quotes, and semicolons. No formatter or linter is configured. Preserve Polish UI wording and existing species keys.

## Testing Guidelines

Use pytest (`tests/test_*.py`) and Node's built-in test runner (`web/tests/*.test.js`). Add regression cases for changed behavior; mock external services and reuse fixtures. Keep Python and JavaScript scoring calculations consistent through shared fixtures. No coverage threshold is configured.

## Commit & Pull Request Guidelines

History uses `feat(scope):`, `fix(scope):`, and `docs:` prefixes, often with Polish summaries; scopes include `web`, `forecast`, and `pipeline`. Keep commits focused. PRs should describe behavior changes, link relevant issues or specifications, record test commands and results, and include screenshots for UI changes.

## Data & Configuration

Keep credentials outside Git. Generated datasets and `Nadlesnictwa/` inputs remain untracked. Review `docs/data/api.md` and `schema/pogoda.schema.json` when changing data formats. Update vendored frontend libraries through `scripts/vendor.sh`.
