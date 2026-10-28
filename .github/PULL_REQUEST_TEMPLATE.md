## Description

Please provide a clear summary of the changes introduced in this Pull Request and specify the affected subsystem(s) (`FastAPI Routers`, `SARIMAX Projection Engine`, `Berth & Lighterage Resolver`, `Voyage Costing / CVC`, `Ingestion Adapters & SQLite Cache`, `React 19 Command Deck`).

## Related Issues

- Closes #

## Type of Change

- [ ] `feat`: New feature or endpoint
- [ ] `fix`: Bug fix in econometrics, berth physics, costing, or UI
- [ ] `refactor`: Internal code restructuring without functional changes
- [ ] `data`: Berth table (`berths.csv`), lighterage (`lighterage_nodes.csv`), or snapshot (`snapshot.json`) update
- [ ] `test`: Addition or update of `pytest` / `hypothesis` test suites
- [ ] `docs`: Documentation or architecture diagram updates
- [ ] `Breaking Change`: Change that alters existing API contracts or schemas

## Test Coverage & Verification

- [ ] `cd backend && pytest tests -q` passes all backend tests (`test_berths`, `test_economics`, `test_ingestion`, `test_invariants`)
- [ ] `pytest tests -q` passes all root-level quantitative and Hypothesis property tests
- [ ] `npm run lint` (`oxlint`) passes with zero errors
- [ ] `npm run build` (`tsc -b && vite build`) compiles cleanly
- [ ] Offline path (`FREIGHTIQ_OFFLINE=1`) verified without outbound network calls

## Self-Review Checklist

- [ ] No network calls or model training (`fit()`) were introduced into FastAPI request handlers.
- [ ] `OWN_DRIVER` (`models/project.py`) and `CLASS_DRIVERS` (`data/ingest.py`) remain synchronized.
- [ ] Any updates to `berths.csv` or `lighterage_nodes.csv` include `source_url` and `source_date` provenance.
- [ ] Relevant documentation (`README.md`, `docs/ARCHITECTURE.md`, `docs/API.md`, `CHANGELOG.md`) has been updated.
