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
- `schedule-card.test.js` covers the bundled schedule card and its visual editor,
  including BCD conversion, DOM editing, conflicts, service calls and confirmation.
  Editor checks cover collapsible slots, search, PLC filtering, duplicate
  prevention and lazy picker loading. Native HA picker tests exercise the
  property/event contract; they do not establish actual picker rendering.
  Both BCD and HHMM formats cover clock validation, HA-unit service values,
  confirmation, metadata compatibility and editor selection.
  Mixed rows exercise per-entity encoding, partial failure, both picker paths,
  legacy helper compatibility and format changes during editing/confirmation.
  Bulk configuration tests exercise twelve mixed pairs, natural ordering,
  per-column reorder, retained selections/focus, duplicate exclusion and final
  validation before appending rows. Wizard interaction must not call HA services.
  Input-selection tests cover first pointer entry, subsequent caret placement,
  keyboard replacement and explicit save/cancel on the last of twelve slots.
  jsdom does not validate responsive layout or native mobile keyboard behavior;
  check touch target sizing, inner scrolling and footer reachability in HA on
  mobile Safari/Chrome when changing these styles. Also check a wide hybrid
  touchscreen/mouse desktop: targets should be enlarged while the table keeps
  its full height and the desktop layout.
- `schedule-timeline.test.js` covers the optional daily timeline: mixed time
  formats, overnight ranges, exact overlap intervals, touching endpoints,
  identical times, invalid/missing entities, drafts, explicit Save/Cancel and
  confirmation/failure states. It also checks editor opt-in and accessible,
  localized labels. These DOM tests verify data and interaction, not browser
  rendering; check the timeline in HA with narrow/wide cards and light/dark themes.
- `schedule-days.test.js` covers BYTE masks, bit-7 preservation, day selection,
  mixed time/day writes, conflicts and feedback, optional entity picking and
  weekday-aware overnight/overlap previews. The fixed mask uses Sunday bit 0
  through Saturday bit 6. Timeline weekdays identify interval start days.
  Check wrapped weekday controls and the day selector on real Safari/Chrome.
- `schedule-shortcuts.test.js` covers weekday presets and value copying:
  per-destination bit-7 preservation, mixed encodings, source/existing drafts,
  before/after previews, all-or-nothing staging, conflicts, live updates and
  explicit Save/Cancel. Check touch/keyboard activation and wrapped copy controls
  in HA; DOM tests do not validate actual browser layout.

When changing `custom_components/s7plc/www/s7plc-panel.js`, add or update a DOM test in the closest matching frontend test file. Prefer testing rendered behavior and user interactions over checking source-code strings.

Before removing a source-string check, identify its behavioral replacement and
extend that DOM test if any scenario is missing. Keep catalog parity, asset and
backend/frontend field-contract checks. CSS source checks are not evidence of
actual browser layout; retain them until an equivalent layout check exists.

Backend and integration tests remain under `tests/test_*.py`.

Shared Python helpers live in `tests/support/`. Import reusable helpers from
there instead of importing another `test_*.py` module:

- `support.write_batching` supplies the controlled scheduler and batch enqueue
  helpers used by write behavior and lifecycle tests.
- `support.retry` supplies the `rig` fixture, operation entry points and cleanup
  assertions used by retry and error-cleanup tests. Import the fixture explicitly
  (`from support.retry import rig as rig`) in each test module that uses it.

Keep scenario-specific clients local to their tests. When consolidating tests,
preserve distinct inputs and execution paths, including synchronous callbacks,
and identify the retained test for every removed regression case.

Python schema tests use the installed `voluptuous` package. Apply the actual
`data_schema` returned by a flow or the schema registered by a service to test
required fields, defaults, types, coercion, ranges and nested payloads. Calling a
flow step or service handler directly does not exercise that schema validation.

Home Assistant is stubbed in `tests/`. Selector doubles retain their configuration
and accept values unchanged; they do not cover HA selector validation or the real
flow manager. Runtime lifecycle and service dispatch have separate tests below.

## Real Home Assistant runtime tests

`tests_homeassistant/` is a small, separate suite using the installed Home Assistant
runtime, config-entry manager, platforms, entity registry, state machine, storage
and service dispatcher. Only the external pyS7 client is mocked; no PLC is needed.
The integration's frontend/HTTP dependencies and panel registration also run,
but these tests do not verify browser rendering or PLC protocol behavior.

Use a **separate Python 3.14 virtual environment**. The pinned test plugin selects
Home Assistant 2026.9.1; the frontend version matches that HA release. Update the
plugin and frontend pins together when intentionally upgrading this test baseline.
This baseline does not establish compatibility with older HA versions.

```bash
python3.14 -m venv .venv-ha
.venv-ha/bin/python -m pip install -r requirements_test_homeassistant.txt
.venv-ha/bin/python -m pip check
.venv-ha/bin/python -m pytest -c tests_homeassistant/pytest.ini tests_homeassistant -v
```

On Windows, use `py -3.14 -m venv .venv-ha` and
`.venv-ha\Scripts\python.exe` for the following commands.

Do not install these dependencies in the stub suite's environment or collect both
suites in one pytest process: `tests/conftest.py` replaces HA modules globally.
The root `pytest.ini` defaults to `tests/`; the runtime suite has its own config
and an explicit command. CI runs each suite in a separate job, keeping the existing
coverage gate and lightweight dependencies unchanged.

The runtime suite covers:

- Setup, reload and unload through HA, including stable entity registration,
  fresh runtime data, PLC disconnect and service cleanup.
- A real failed coordinator refresh: the data sensor becomes unavailable while
  the connection switch remains usable through `switch.turn_off`; its disabled
  state survives reload without new PLC I/O.
- `health_check` and `write_multi` through HA's dispatcher, including rejection
  of invalid required fields and nested write payloads before PLC access.
- Schedule-card registration through HA's actual frontend URL manager and
  Lovelace resource collection, including persisted resource updates, YAML
  resource handling, repeated setup, reload and serving the JavaScript over HTTP.
- LOGO clock number metadata, HHMM state and `number.set_value` dispatch through
  the real HA runtime, with exactly one BCD conversion before PLC transport.
- Raw BYTE weekday metadata and full-mask `number.set_value` dispatch without
  conversion, including preservation of bit 7 in the payload supplied by the card.

The dashboard asset is registered by `frontend.py` during integration setup,
independently of `panel.py`. Lovelace is a setup dependency so its resource
collection exists before registration. UI-managed resources are created or
updated through the collection API, after loading existing storage. The extra
frontend module supports YAML-managed resources without editing the user's YAML.
When changing `s7plc-schedule-card.js`, increment
`SCHEDULE_CARD_BUILD` in `frontend.py` to invalidate browser module caches and
update the relevant DOM tests. `s7_raw_word` on number entities describes scalar
WORD read/write channels without value conversion; the card still validates
the HA numeric bounds and step separately. LOGO-converted writable WORD numbers
expose `s7_time_format: hhmm`. S7 format detection is always automatic.
`s7_raw_byte` identifies scalar BYTE read/write channels without conversions for
the optional weekday picker. Unknown external helpers are validated as raw BYTE
values at edit/save time; do not infer S7 capabilities from their current state.
For clock entities, format metadata takes precedence over any old card/row
format settings. Keep those
legacy settings only as a fallback for external helpers without S7 metadata;
the editor must not expose format selectors or generate new settings.
Never infer encoding from the numeric state itself.
Do not use the administration panel's WebSocket endpoints for normal dashboard
reads or writes.

Platforms add read tags concurrently, so the fixtures explicitly await a real
coordinator refresh after setup rather than relying on debounce timer timing.
The offline test advances the fixture clock to make sensor reads due; it does not
sleep or replace coordinator availability behavior.

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
