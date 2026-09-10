# Berth data provenance

## Read this before quoting a number from `berths.csv`

The berth dimensions in this directory were **compiled from public
port-authority material, not transcribed from a single authoritative document**.
They are indicative and internally consistent, and they are good enough to drive
the resolver's logic and to demonstrate the system. They are **not** verified
commercial data.

Verify against the operator's current publication before any of it reaches a
fixture note or a recap. Each row carries the `source_url` it should be checked
against and the `source_date` it was compiled on, and both travel through the
API so the UI can show them per number rather than per page.

| Port | Verify against |
|---|---|
| Paradip | Paradip Port Authority, port facilities and vessel-related particulars |
| Visakhapatnam | Visakhapatnam Port Authority, inner and outer harbour berth particulars |
| Gangavaram | Adani Gangavaram Port, berth specifications |
| Dhamra | Adani Dhamra Port, berth specifications |
| Gopalpur | Gopalpur Ports Limited, berth specifications |
| Haldia | Syama Prasad Mookerjee Port Kolkata, Haldia Dock Complex particulars |
| Sandheads and Sagar | SMP Kolkata pilotage and anchorage notices |

Declared drafts change. Ports dredge, siltation cuts them back, and operators
issue revised particulars several times a year. Treat this file as perishable.

## Column semantics

Two columns carry meaning that is not obvious from the name.

`draft_max_m` is the permissible arrival and sailing draft **at all states of
tide**. A vessel inside it can work whenever she arrives.

`tide_required_m` is the *additional* draft the berth can accept inside a
high-water window. The maximum on tide is `draft_max_m + tide_required_m`. A
vessel in that band is workable but tide-bound, which buys waiting days. The
resolver keeps that as its own outcome, `ACCEPT_HIGH_TIDE_ONLY`, because it is a
different commercial answer from a clean yes and pricing it as one is wrong.

## Sagar and Sandheads

Deliberately absent from `berths.csv`. They are anchorages, not berths, and they
live in `lighterage_nodes.csv`. Modelling an anchorage as a berth would let the
resolver accept a vessel at a place where she cannot discharge.

## Visakhapatnam

Modelled as two basins in one table. The outer harbour berths carry roughly
eighteen metres and handle iron ore and coking coal; the inner harbour carries
roughly fourteen and a half and handles thermal coal, fertiliser and general
cargo. There is no `basin` column, and that is on purpose: the commodity list on
each berth already decides which basin a cargo can go to, and the draft decides
the rest. Encoding the basin separately would create a second source of truth
that could disagree with the first.
