---
name: Feature Request
about: Propose a new econometric feature, port/berth coverage expansion, chartering structure, or UI enhancement
title: "[FEAT] "
labels: ["enhancement"]
assignees: ""
---

## Problem Statement
Describe the dry-bulk chartering, port feasibility, or freight forecasting problem this feature addresses.

## Proposed Solution
Provide a detailed technical description of the proposed change:
- **Backend / Quantitative Impact**: Does this affect `backend/models/project.py`, `backend/app/costing.py`, `backend/data/ports/resolver.py`, or add a new `SourceAdapter`?
- **API & Frontend Impact**: Which FastAPI routers (`backend/app/routers/`) and React pages (`src/pages/`) will consume or display this capability?
- **Data Provenance**: If adding berths, anchorages, or market series, what is the authoritative data source (`source_url`) and is it a direct series or a proxy (`is_proxy`)?

## Alternative Considerations
Describe any alternative modeling approaches or UI workflows considered and why the proposed design is preferred.

## Additional Context
Include any relevant formulas, port circulars, or mock payloads.
