# Security Policy

## 1. Supported Versions

The following versions of **FreightIQ** (`SIH_Freight-Forecasting`) receive security updates:

| Version | FastAPI Backend | React / TypeScript Client | Supported |
| :--- | :--- | :--- | :--- |
| `0.2.x` (`main`) | `0.2.0` (Python 3.11–3.13) | React `19.2.8` / TS `6.0.2` | :white_check_mark: Yes |
| `< 0.2.0` | `0.1.x` | `< 19.2` | :x: No |

---

## 2. Security Architecture & Controls

- **Zero Credential Requirement by Default**: FreightIQ runs without requiring third-party API keys; all configuration is read from environment variables (`backend/app/config.py`) and optional secrets (`FRED_API_KEY`, `TRADINGECONOMICS_KEY`) are never committed to source control.
- **Parameterized SQLite Queries (`backend/data/cache.py`)**: All reads and writes to `cache.db` use bound SQLite parameters (`?`), preventing SQL injection across `/api/series` and status endpoints.
- **Strict Pydantic v2 Boundary Validation (`backend/app/schemas.py`)**: All request bodies and query parameters enforce strict numeric bounds (`gt`, `le`, `ge`), literal enums (`VesselClassName`, `BerthOutcome`), and array length caps (`MAX_METRICS = 40`, `MAX_POINTS_PER_METRIC = 2000`) to prevent denial-of-service payloads.
- **Explicit CORS Allowlist (`backend/app/main.py`)**: Cross-origin requests are restricted to origins declared in `FREIGHTIQ_CORS_ORIGINS` (`http://localhost:5173,http://localhost:5174` by default) and limited to `GET`, `POST`, and `OPTIONS`.
- **Trusted Local Model Pickles (`backend/models/project.py`)**: `ProjectionBundle` `.pkl` files (`models/sarimax_<class>.pkl`) are git-ignored and generated locally by `train.py` from validated cache data. Never load untrusted `.pkl` or `.joblib` files from external sources.

---

## 3. Vulnerability Disclosure Process

**Please do not report security vulnerabilities through public GitHub issues, discussions, or pull requests.**

If you identify a security vulnerability in FreightIQ:
1. **Report Privately**: Email **security@freightiq-maritime.org** or submit a report via GitHub's [Private Vulnerability Reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability) advisory tab.
2. **Provide Details**:
   - Affected component (`backend/app/routers/`, `backend/data/cache.py`, `src/lib/api.ts`, etc.).
   - Reproducible HTTP request payload or proof-of-concept script.
   - Assessment of potential impact.

---

## 4. Response Timeline

| Milestone | Target SLA | Action |
| :--- | :--- | :--- |
| **Initial Acknowledgment** | **Within 48 hours** | Confirm receipt of the vulnerability report. |
| **Triage & Reproduction** | **Within 5 business days** | Validate severity, scope, and affected versions. |
| **Remediation & Patch** | **Within 14 days** | Develop, test, and merge a fix to `main`. |
| **Public Disclosure** | **Post-Release** | Publish advisory and credit reporter in `CHANGELOG.md`. |
