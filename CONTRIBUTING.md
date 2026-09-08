# Contributing to ha-s7plc

Thank you for helping improve ha-s7plc. This guide describes the development setup and the checks expected before opening a pull request.

## Requirements

- Python 3.13
- Node.js 24 and npm
- Git

Using the same major versions as CI is recommended.

## Development setup

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

Install the Python development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements_dev.txt
```

Install the frontend test dependencies from the lockfile:

```bash
npm ci
```

## Running tests

Run the Python test suite:

```bash
python -m pytest tests -v
```

Run the panel DOM test suite:

```bash
npm run test:panel
```

Run a single frontend test file:

```bash
npm run test:panel -- panel-search.test.js
```

Run the same Python coverage check used by CI:

```bash
python -m pytest tests -v \
  --cov=custom_components/s7plc \
  --cov-branch \
  --cov-fail-under=78.5 \
  --cov-report=term-missing \
  --cov-report=xml
```

Before opening a pull request, run both the Python and frontend suites:

```bash
npm run test:panel
python -m pytest tests -v
```

## Panel test structure

Frontend tests live in `tests/frontend/` and use Vitest with jsdom.

- `panel-fixture.js` provides the shared DOM environment, Home Assistant stubs, fixtures, and panel helpers.
- `panel-lifecycle.test.js` covers panel setup, refreshes, subscriptions, and cleanup.
- `panel-navigation.test.js` covers categories, layouts, and responsive controls.
- `panel-search.test.js` covers filtering and search-state preservation.
- `panel-editor.test.js` and `panel-complex-editors.test.js` cover entity editor workflows.
- The remaining files cover address handling, YAML, connection details, entities, helpers, and value conversions.

When changing `custom_components/s7plc/www/s7plc-panel.js`, add or update a DOM test in the closest matching frontend test file. Prefer testing rendered behavior and user interactions over checking source-code strings.

Backend and integration tests remain under `tests/test_*.py`.

## Python module boundaries

`custom_components/s7plc/plc/` contains helpers that depend only on Python and
pyS7. Keep imports inside this package independent of Home Assistant and the
integration modules above it.

| Module | Responsibility |
| --- | --- |
| `plc/address.py` | Address parsing, datatype limits and TIME representation |
| `plc/payload.py` | Python value validation and preparation for pyS7 writes |
| `plc/plans.py` | Read plans, postprocessing and the default REAL precision |
| `plc/read_executor.py` | Scalar/string reads and internal `S7ReadError` failures |
| `plc/connection_manager.py` | Client ownership, I/O admission, cancellation cleanup and draining |

The coordinator remains the Home Assistant adapter: it owns polling, cache and
health publication, retry policy, HA shutdown scheduling and conversion of
`S7ReadError` to `UpdateFailed`. It supplies the connection manager's lifecycle
exception type. `write_manager.py` remains outside `plc/` because it uses HA task
creation and notification services.

`tests/test_plc_package.py` imports a copy of the PLC package in an isolated
interpreter, without the integration's parent modules and with Home Assistant
imports blocked. Existing behavior tests continue to exercise the coordinator.

## Code quality

Run Ruff:

```bash
ruff check custom_components tests
```

Run pre-commit on the files you changed:

```bash
pre-commit run --files <file1> [<file2> ...]
```

## Pull requests

1. Create a focused branch.
2. Keep commits and the pull request description clear.
3. Add tests for behavioral changes and bug fixes.
4. Update user documentation when behavior or configuration changes.
5. Confirm that Python tests, panel DOM tests, pre-commit, Hassfest, and HACS validation pass.
