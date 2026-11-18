<div align="center">

# Assembly Line Data Platform

**Data reliability for a simulated general-assembly line: station events into PostgreSQL, dbt models
with tests and documentation, monitoring that catches data faults, fault-injection drills with
postmortems, and measured SQL optimization.**

[![CI](https://github.com/Kiran-koppera/assembly-line-data-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/Kiran-koppera/assembly-line-data-platform/actions/workflows/ci.yml)
[![Deploy](https://github.com/Kiran-koppera/assembly-line-data-platform/actions/workflows/deploy.yml/badge.svg)](https://github.com/Kiran-koppera/assembly-line-data-platform/actions/workflows/deploy.yml)
![Coverage 86%](https://img.shields.io/badge/coverage-86%25-0b6bcb)
![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-0b6bcb)
![dbt](https://img.shields.io/badge/dbt-1.10-0b6bcb)

### [▶ Live dashboard](https://kiran-koppera.github.io/assembly-line-data-platform/) · [dbt docs](https://kiran-koppera.github.io/assembly-line-data-platform/dbt-docs/) · [Fault drills](docs/fault-drills.md) · [Benchmarks](docs/benchmarks.md) · [Runbooks](docs/runbooks.md)

<img src="docs/images/dashboard.png" alt="Dashboard: KPI strip, hourly throughput against takt, station table" width="900">

</div>

> **All data is simulated.** The line is modelled on public information about general-assembly
> shops (see [simulation.md](docs/simulation.md)). Not affiliated with any vehicle manufacturer.

---

## The problem

At 60 vehicles an hour, a general-assembly line produces hundreds of thousands of events a day
from PLCs, torque tools, stoppage calls, quality gates and end-of-line tests. If one station's clock
drifts, a tool reports the wrong unit or a gateway re-sends a buffer, throughput, bottleneck and
quality KPIs quietly go wrong. This project builds the pipeline **and** the checks that keep those
KPIs trustworthy, then proves the checks work by breaking the data on purpose.

## Results

| | |
|---|---|
| Ingestion | **1,056,518 events** (one simulated week) loaded in 13 s with indexes in place; re-running a load skips every unchanged file |
| Modelling | 12 dbt models in 3 layers, **26 data tests**, generated documentation with lineage |
| Monitoring | **8 checks** across stations and time; a clean 3-day run raises **0 incidents** |
| Fault drills | **7 of 7 injected faults detected, 0 false alarms** (8/8 scenarios pass) |
| SQL optimization | **6× to 877× faster** queries after three targeted indexes (median of 7 EXPLAIN ANALYZE runs) |
| Engineering | 14 tests on a real PostgreSQL (86 % coverage in CI), CI on Python 3.11/3.12, deploy builds everything from scratch |

### Fault drills

| Injected fault | Caught by | Finding |
|---|---|---|
| Station clock jumps 3 min ahead | `clock_skew` | F07 median transfer +180 s, F08 −180 s |
| Gateway re-sends 500 events | `resent_events` | 500 duplicates ignored by the idempotent load |
| PLC restart replays entries with new ids | `duplicate_station_events` | 51 vehicles reported twice at C03 |
| Station stops reporting for an hour | `missing_station_records`, `station_silence`, dbt test | 59 vehicles without a C04 record |
| Torque tool switches to lbf·ft | `torque_level_shift` | C05-J1 median 0.73 × target |
| Firmware renames a field | `contract_violations` | 240 records quarantined, none lost |
| Files arrive six hours late | `late_arrivals` | 6,051 events loaded into the right day |

Postmortems for each: [docs/fault-drills.md](docs/fault-drills.md).

### SQL optimization (1,056,518 events)

| Query | Before | After | Speed-up |
|---|---|---|---|
| Hourly throughput | 4.13 ms · Seq Scan | 0.39 ms · Bitmap | 10.6× |
| Station dwell p50/p95 | 5.26 ms · Seq Scan | 0.85 ms · Bitmap | 6.2× |
| Torque joint, whole week | 30.95 ms · Seq Scan | 3.92 ms · Bitmap | 7.9× |
| Vehicle history lookup | 26.30 ms · Seq Scan | 0.03 ms · Index Scan | 876.7× |

Method and trade-offs: [docs/benchmarks.md](docs/benchmarks.md).

## Architecture

```
Simulator (SimPy, 40 stations, 60 s takt) ──► hourly JSON-lines files
   ▼
Ingestion: data contract → COPY → INSERT … ON CONFLICT DO NOTHING · quarantine · file checksums
   ▼
PostgreSQL: raw.events partitioned by day, PK (event_id, event_ts), 3 indexes
   ▼
dbt: staging → intermediate → marts  (throughput, station dwell, first-pass yield, torque Cpk)
   ▼
Monitoring: 8 SQL checks → monitoring.incidents        Fault drills: 7 faults + clean baseline
   ▼
FastAPI (local) · static dashboard + dbt docs on GitHub Pages
```

Design decisions: [docs/architecture.md](docs/architecture.md).

## Quick start

```bash
git clone https://github.com/Kiran-koppera/assembly-line-data-platform.git
cd assembly-line-data-platform
make install          # venv + embedded PostgreSQL 16 (no Docker needed)
make run              # simulate 3 days → ingest → dbt build → monitoring
make drills           # inject 7 faults, check each is caught
make site && make serve   # dashboard + dbt docs at http://localhost:8000
make test             # 14 tests on a separate test database
make api              # FastAPI at http://localhost:8000/docs
```

With Docker instead: `docker compose up -d` and set
`DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres`.

## Repository

```
├── src/assembly/
│   ├── simulator.py   line model (SimPy) → events          ├── monitoring.py  8 reliability checks
│   ├── contract.py    data contract                         ├── chaos.py       fault drills
│   ├── ingest.py      idempotent loader, quarantine         ├── benchmark.py   EXPLAIN ANALYZE timing
│   ├── pipeline.py    end-to-end run                        ├── api.py         FastAPI
│   └── config.py      line settings with sources            └── export.py      dashboard data
├── sql/               schema.sql, indexes.sql
├── dbt/               models/{staging,intermediate,marts}, seeds, tests, macros
├── web/               dashboard (HTML, CSS, JS)
├── tests/             pytest on real PostgreSQL
├── docs/              simulation, architecture, fault drills, benchmarks, runbooks
└── .github/           CI, deploy, pull-request template
```

## How work is done here

Changes go through pull requests with a checklist (tests, drills, docs). CI runs lint, the test
suite on a real PostgreSQL and a dbt parse; the deploy workflow rebuilds the platform on a fresh
database, **fails if any fault drill is missed**, and publishes the dashboard and dbt docs.

## Limits

- Simulated data: values are realistic in shape and scale, not in the details of any real plant.
- Single-node batch loads; a production version would stream (e.g. Kafka) into the same contract.
- Benchmarks were measured on a laptop; absolute times vary by machine, plan changes do not.

## Licence

Code: MIT.
