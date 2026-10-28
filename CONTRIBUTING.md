# Contributing to FreightIQ

Thank you for contributing to **FreightIQ** (`SIH_Freight-Forecasting`)! This guide outlines our branching conventions, commit rules, architectural invariants, and pre-commit verification workflow.

---

## 1. Branching Conventions

Create feature and bugfix branches off `main` using the following prefixes:

| Prefix | Purpose | Example |
| :--- | :--- | :--- |
| `feat/` | New forecasting features, routers, or React views | `feat/multiport-split-optimiser` |
| `fix/` | Bug fixes in SARIMAX, berth resolution, or UI | `fix/haldia-lighterage-draft-margin` |
| `chore/` | Dependency updates, snapshot refreshes, or docs | `chore/refresh-baseline-snapshot` |
| `refactor/` | Internal code restructuring with identical behavior | `refactor/consolidate-berth-resolver` |
| `test/` | Adding pytest or Hypothesis property tests | `test/circularity-guard-invariant` |

---

## 2. Conventional Commits Guidelines

All commits must follow the [Conventional Commits v1.0.0](https://www.conventionalcommits.org/) specification:

```text
<type>(<scope>): <short imperative summary>

[optional body explaining quantitative or architectural rationale]

[optional footer(s): Closes #123, BREAKING CHANGE: ...]
```

### Allowed Types & Scopes
- **Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`
- **Scopes**: `forecast`, `berths`, `costing`, `ingest`, `cache`, `api`, `ui`, `evaluate`

**Examples:**
- `feat(berths): distinguish ACCEPT_HIGH_TIDE_ONLY from ACCEPT_ALL_TIDE in resolver`
- `fix(forecast): standardise exogenous regressors before SARIMAX L-BFGS fit`
- `test(costing): verify CVC break-even monotonicity with Hypothesis`

---

## 3. Core Architectural Invariants to Preserve

1. **Zero Network Calls on Request Path**: Never invoke an external HTTP request inside a FastAPI router (`backend/app/routers/`). New external feeds must subclass `SourceAdapter` in `backend/data/adapters/` and write to `cache.db` via `ingest.refresh_all()`.
2. **No Model Fitting on Request Path**: `models/project.py:fit()` is only called by `train.py`. Request handlers must use `SARIMAXResults.apply(..., refit=False)`.
3. **Keep `OWN_DRIVER` and `CLASS_DRIVERS` Synchronized**: When modifying proxy drivers in `backend/data/ingest.py` (`CLASS_DRIVERS`), update `OWN_DRIVER` in `backend/models/project.py` so no vessel class regresses on its own target generator.
4. **Preserve Provenance on Berth Edits**: Every row added to `backend/data/ports/berths.csv` or `lighterage_nodes.csv` must include `source_url` and `source_date` and be documented in `backend/data/ports/PROVENANCE.md`.

---

## 4. Pre-Commit Checks & Verification

Run the unified verification suite before opening a Pull Request:

```bash
# Run both backend pytest and frontend tsc + oxlint + vite build
./run.sh --test

# Or run each suite individually:
cd backend && pytest tests -q
pytest tests -q
npm run lint
npm run build
```

---

## 5. Pull Request Lifecycle

1. Push your branch and open a Pull Request against `main`.
2. Complete all sections of `.github/PULL_REQUEST_TEMPLATE.md`.
3. Confirm that offline mode (`FREIGHTIQ_OFFLINE=1`) and client-side fallback rendering (`src/lib/fallbacks.ts`) remain intact.
4. Once reviewed and all checks pass, maintainers will squash-merge your PR.
