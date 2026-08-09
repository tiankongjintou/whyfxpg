# Domain Docs

This project uses a **single-context** layout:

- `CONTEXT.md` at repo root: canonical glossary of the risk-assessment domain.
- `docs/adr/`: architecture decision records for system-wide decisions.

## Consumer rules

- Always read `CONTEXT.md` before making naming or modeling decisions in any session.
- Use the canonical terms found there; do not invent synonyms.
- Create or update an ADR in `docs/adr/` when a decision is hard to reverse, surprising
  without context, and the result of a genuine trade-off.

## Writing CONTEXT.md

- Keep implementation details out. Record only the domain vocabulary and relationships.
- Use the format: `Term` — definition, boundaries, and examples.
- Cross-reference related terms where ambiguity could arise.
