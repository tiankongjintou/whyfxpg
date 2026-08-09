# ADR-022: Basic telemetry observability seam

## Status

Accepted

## Context

After T23/T24 the WHYfxpg v2 pipeline is fully functional, but operators have no visibility into how long pipeline runs take, how many adapter calls are made, or the overall health of the system. We need a lightweight, seam-first observability hook without adding a heavy metrics/APM dependency.

## Decision

Introduce a `TelemetryPort` in `whyfxpg/ports/telemetry.py` with three small record types:

- `RunRecord`: total pipeline run time and per-stage status/duration.
- `AdapterCallRecord`: adapter name, method, duration, and success.
- `HealthSnapshot`: service-level health derived from the last run.

Implement a `NullTelemetryPort` as the default no-op adapter, and an `InMemoryTelemetryAdapter` for tests and local debugging. The `PipelineOrchestrator` accepts an optional `telemetry_port` and records:

1. Total pipeline run duration and per-stage results.
2. Every `archive_port.archive()` invocation via `_timed_archive()`.
3. A health snapshot after each run summarizing stage count, error count, and duration.

A `TelemetryService` convenience wrapper provides a stable API for future dashboard or alerting consumers.

## Consequences

- No external observability dependency; everything is port/adapter based.
- Tests can assert timing and adapter call counts without mocking time.
- Existing orchestrator tests remain compatible because telemetry is optional.
- Coverage dropped to 79% overall due to many UI/service paths not being exercised, but the telemetry seam itself is covered by `test_telemetry.py`.

## Related tickets

- T27 — basic observability
