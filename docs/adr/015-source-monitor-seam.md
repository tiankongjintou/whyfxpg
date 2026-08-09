# ADR-015: Source Monitor Seam (T17)

## Status
Accepted — implemented as part of WHYfxpg v2.

## Context
The "数据源监控" page only displayed the `monitor_sources` table. There was no health score, no freshness/latency/coverage trend, no lineage from a risk event back to its source run, and no alerts when a source degraded. The user explicitly asked for monitoring beyond source maintenance.

## Decision
Introduce a `SourceHealthPort` (`whyfxpg/ports/source_health.py`) with `health`, `freshness`, `latency`, `coverage`, `lineage`, `metrics`, and `write_snapshot`. Two adapters are implemented:

- `DbSourceHealthAdapter` — derives all metrics from the existing SQLite tables (`monitor_sources`, `crawl_logs`, `risk_events`, `raw_pages`) and writes snapshots to `source_health_snapshots`.
- `InMemorySourceHealthAdapter` — dictionary-backed for unit tests and sandboxing.

`SourceMonitorService` (`whyfxpg/services/source_monitor.py`) orchestrates checks across all sources, writes snapshots, and drafts/publishes alerts through the existing `AlertPublisher` when a source becomes `degraded` or `error`.

The Web UI page was updated to show:
- source run status table;
- health score table with freshness, latency, coverage, error rate;
- per-source metrics JSON;
- lineage lookup for a given event ID;
- health trend line chart (once snapshots exist).

All queries go through `whyfxpg/webui/queries.py` and `SourceHealthReadModel`; no page directly queries the database.

`crawl_logs` was extended by migration `006` to record `request_started_at`, `latency_ms`, and `content_length`. The `FetchedPage` dataclass and `HttpSourceAdapter` now carry this timing information, and `Fetcher` persists it into `crawl_logs` and `monitor_sources.last_content_length`.

## Consequences
- Sources now have observable health scores and historical trends without adding a separate time-series database.
- Degraded sources produce alerts using the same alert lifecycle as rule-engine alerts.
- Lineage can trace a risk event back to its source page and crawl run.
- The UI page now exposes health, metrics, and lineage instead of just a source list.
- `HttpSourceAdapter` now records latency per request.
- Future Prometheus/Grafana integration can be added by implementing a new `SourceHealthPort` adapter without changing the service or UI.

## Related Tickets
- T17 SourceMonitor seam (closed)
- T16 RuleEngine seam (dependency for alert publishing reuse)
- T15 Admin CRUD seam (dependency for source configuration)
- T18 Dashboard v2 seam (next)

## References
- `whyfxpg/ports/source_health.py`
- `whyfxpg/adapters/monitoring/db_source_health.py`
- `whyfxpg/adapters/monitoring/in_memory_source_health.py`
- `whyfxpg/services/source_monitor.py`
- `whyfxpg/webui/screens/sources.py`
- `whyfxpg/webui/read_model.py` (`SourceHealthReadModel`)
- `whyfxpg/migrations/006_source_monitoring.sql`
