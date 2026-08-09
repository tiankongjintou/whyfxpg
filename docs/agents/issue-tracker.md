# Issue Tracker

This project uses a **local Markdown issue tracker** under `.scratch/wayfinder/`.
The map is the single source of truth for the current plan. Ask the agent to read it before starting a new frontier ticket.

## Map

- `.scratch/wayfinder/map.md` — WHYfxpg v2 Wayfinder map (Phase 6).

## Tickets

- `.scratch/wayfinder/issues/T<NN>-<slug>.md` — individual tickets.
- T15–T22 are the current frontier for WHYfxpg v2.
- Research branches: `.scratch/wayfinder/research/<name>/`

## Creating a ticket

1. Number the next issue in dependency order (blockers first).
2. Write one file per ticket using the template in `docs/agents/ticket-template.md`.
3. In `map.md`, link the ticket under the relevant frontier or fog section.

## Blockers

In a ticket body, use a `Blocked by:` section listing the numbers/titles of
tickets that must close first. Native tracker links are not available, so we use
the file number.

## PRs as a request surface

Disabled for this project. Pull requests are not part of the local tracker workflow.
