"""Taxonomy adapters."""

from pathlib import Path
from typing import Any

import yaml

from whyfxpg.config.models import TaxonomyNode
from whyfxpg.ports.taxonomy import TaxonomyPort


class LocalYamlTaxonomyAdapter(TaxonomyPort):
    """Load a taxonomy from a local YAML file."""

    def __init__(self, path: Path, taxonomy_id: str = ""):
        self.path = Path(path)
        self.taxonomy_id = taxonomy_id or self.path.stem
        self._nodes: list[TaxonomyNode] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        payload = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        nodes = payload.get("nodes") or []
        self._nodes = [TaxonomyNode.from_dict(n) for n in nodes if isinstance(n, dict)]
        for node in self._nodes:
            if not node.taxonomy_id:
                node.taxonomy_id = payload.get("taxonomy_id") or self.taxonomy_id

    def list_children(self, parent_id: str | None) -> list[TaxonomyNode]:
        parent = parent_id if parent_id is not None else ""
        return [n for n in self._nodes if (n.parent_id or "") == parent]

    def search(self, keyword: str) -> list[TaxonomyNode]:
        kw = keyword.lower()
        results = []
        for n in self._nodes:
            texts = [n.name, *n.aliases, *n.keywords, n.node_id]
            if any(kw in t.lower() for t in texts if isinstance(t, str)):
                results.append(n)
        return results

    def map_event(self, event: dict[str, Any]) -> TaxonomyNode | None:
        # Prefer explicit hs_code match, then product_category, then product_name.
        hs = str(event.get("hs_code") or "")
        category = str(event.get("product_category") or "")
        name = str(event.get("product_name") or "")

        for n in self._nodes:
            if hs and n.node_id and n.node_id == hs:
                return n
            terms = [t.lower() for t in [n.name, *n.aliases, *n.keywords] if t]
            if category and any(category.lower() in t or t in category.lower() for t in terms):
                return n
            if name and any(name.lower() in t or t in name.lower() for t in terms):
                return n
        return None


class InMemoryTaxonomyAdapter(TaxonomyPort):
    """In-memory taxonomy for tests and demos."""

    def __init__(self, nodes: list[TaxonomyNode]):
        self._nodes = nodes

    def list_children(self, parent_id: str | None) -> list[TaxonomyNode]:
        parent = parent_id if parent_id is not None else ""
        return [n for n in self._nodes if (n.parent_id or "") == parent]

    def search(self, keyword: str) -> list[TaxonomyNode]:
        kw = keyword.lower()
        results = []
        for n in self._nodes:
            texts = [n.name, *n.aliases, *n.keywords, n.node_id]
            if any(kw in t.lower() for t in texts if isinstance(t, str)):
                results.append(n)
        return results

    def map_event(self, event: dict[str, Any]) -> TaxonomyNode | None:
        hs = str(event.get("hs_code") or "")
        category = str(event.get("product_category") or "")
        name = str(event.get("product_name") or "")

        for n in self._nodes:
            if hs and n.node_id and n.node_id == hs:
                return n
            terms = [t.lower() for t in [n.name, *n.aliases, *n.keywords] if t]
            if category and any(category.lower() in t or t in category.lower() for t in terms):
                return n
            if name and any(name.lower() in t or t in name.lower() for t in terms):
                return n
        return None
