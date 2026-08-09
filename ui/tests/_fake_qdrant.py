"""In-memory fake `QdrantClient` double for identity-store tests.

Implements just enough of `qdrant_client.QdrantClient`'s surface for
`IdentityStoreService`: `get_collection`/`create_collection` (collection
lifecycle), `scroll` (generic `FieldCondition` equality-filter matching),
and `upsert`. A real in-memory fake — rather than a per-call `MagicMock` —
keeps the tests exercising the SAME `qdrant_client` model classes
(`Filter`/`FieldCondition`/`MatchValue`/`PointStruct`) the production code
builds, while swapping only the network transport, so a bug in how the
service constructs a filter would actually be caught here.

Not a test file itself (no `test_` prefix — not collected by pytest);
imported by `test_identity_store.py`, `test_identity_resolver.py`, and
`test_sse_reauth.py`.
"""

from __future__ import annotations

from typing import Any


class _FakePoint:
    """Mimics the subset of `qdrant_client.models.Record` the service reads."""

    def __init__(self, point_id: str, payload: dict[str, Any]) -> None:
        self.id = point_id
        self.payload = payload


class FakeQdrantClient:
    """Minimal in-memory stand-in for `QdrantClient`.

    `self.collections[name]` is a `dict[point_id, payload]`. Construct with
    a `unittest.mock.patch`/`monkeypatch` replacing
    `beeper_ui.services.identity_store.QdrantClient` with a callable that
    returns a shared instance of this class, so a test controls exactly
    what's "in Qdrant" for the `IdentityStoreService` under test.
    """

    def __init__(self) -> None:
        self.collections: dict[str, dict[str, dict[str, Any]]] = {}
        self._known_collections: set[str] = set()

    def get_collection(self, collection_name: str) -> Any:
        if collection_name not in self._known_collections:
            raise ValueError(f"Collection {collection_name!r} does not exist")
        return object()

    def create_collection(self, collection_name: str, vectors_config: Any = None) -> bool:
        self._known_collections.add(collection_name)
        self.collections.setdefault(collection_name, {})
        return True

    def upsert(self, collection_name: str, points: list[Any]) -> Any:
        self._known_collections.add(collection_name)
        store = self.collections.setdefault(collection_name, {})
        for point in points:
            store[point.id] = dict(point.payload)
        return object()

    def scroll(
        self,
        collection_name: str,
        scroll_filter: Any = None,
        limit: int = 10,
        offset: Any = None,
        with_payload: bool = True,
        with_vectors: bool = True,
    ) -> tuple[list[_FakePoint], Any]:
        store = self.collections.get(collection_name, {})
        conditions = []
        if scroll_filter is not None and getattr(scroll_filter, "must", None):
            conditions = scroll_filter.must
        results = [
            _FakePoint(point_id, dict(payload) if with_payload else {})
            for point_id, payload in store.items()
            if _matches(payload, conditions)
        ]
        # Deterministic ordering for reproducible test assertions.
        results.sort(key=lambda p: p.id)
        return results[:limit], None

    def delete(self, collection_name: str, points_selector: Any = None, **_kwargs: Any) -> Any:
        """ADDITIVE (Task 8.8 — SCIM surface): hard-delete support.

        `points_selector` is accepted as a plain list of point ids (the
        only shape `IdentityStoreService.delete_user()`/`delete_group()`
        pass) — a real `PointIdsList`/`Filter` selector is not modeled
        here since production code never constructs one.
        """
        store = self.collections.get(collection_name, {})
        ids = list(points_selector) if points_selector is not None else []
        for point_id in ids:
            store.pop(point_id, None)
        return object()

    def close(self) -> None:
        pass


def _matches(payload: dict[str, Any], conditions: list[Any]) -> bool:
    for cond in conditions:
        key = cond.key
        expected = cond.match.value
        if payload.get(key) != expected:
            return False
    return True
