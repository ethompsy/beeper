"""Atomic-migration smoke test for Story 3.2 (AC3 / AC6).

Renders every one of the 29 page templates that extend ``base.html`` and
asserts each one renders inside the new layout shell without a Jinja error.

This proves the atomic ``base.html`` rewrite did not break any route's
template inheritance. Templates are rendered directly through the Jinja
environment with a permissive ``Undefined`` so no operator HTTP mocking is
required — the only thing under test here is template inheritance + shell
wrapping, not route data handling (that is covered by the per-route suites).
"""

from __future__ import annotations

from collections.abc import Iterator

import jinja2
import pytest
from flask import Flask

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig

# The 29 page templates that extend base.html (per Story 3.2 Dev Notes).
PAGE_TEMPLATES: list[str] = [
    "analytics/dashboard.html",
    "handoff/handoff.html",
    "health/status.html",
    "investigations/detail.html",
    "investigations/list.html",
    "knowledge/diff.html",
    "knowledge/edit.html",
    "knowledge/entry.html",
    "knowledge/history.html",
    "knowledge/import.html",
    "knowledge/index.html",
    "knowledge/learning.html",
    "knowledge/service_knowledge.html",
    "knowledge/trust_settings.html",
    "knowledge/version.html",
    "metrics/mttr.html",
    "notifications/config.html",
    "reports/executive.html",
    "reports/noise.html",
    "services/detail.html",
    "services/list.html",
    "slo/dashboard.html",
    "slo/service.html",
    "sources/list.html",
    "spending/costs.html",
    "spending/spending.html",
    "topology/index.html",
    "trust/history.html",
    "trust/settings.html",
]


class _Silent(jinja2.Undefined):
    """Undefined that swallows every operation.

    Lets any page template render without route context: missing variables,
    attribute/index chains, iteration, arithmetic, comparison and string
    coercion all degrade quietly. Jinja's own slot attributes
    (``_undefined_name`` etc.) resolve via the slot descriptors before
    ``__getattr__`` is consulted, so internal Jinja behaviour is unaffected.
    """

    __slots__ = ()

    def _self(self, *args: object, **kwargs: object) -> "_Silent":
        return self

    __getattr__ = _self
    __getitem__ = _self
    __call__ = _self
    __add__ = __radd__ = _self
    __sub__ = __rsub__ = _self
    __mul__ = __rmul__ = _self
    __truediv__ = __rtruediv__ = _self
    __floordiv__ = __rfloordiv__ = _self
    __mod__ = __rmod__ = _self
    __pow__ = __rpow__ = _self
    __neg__ = __pos__ = __abs__ = _self

    def __iter__(self) -> Iterator["_Silent"]:
        return iter(())

    def __len__(self) -> int:
        return 0

    def __bool__(self) -> bool:
        return False

    def __int__(self) -> int:
        return 0

    def __float__(self) -> float:
        return 0.0

    def __str__(self) -> str:
        return ""

    def __html__(self) -> str:
        return ""

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Silent)

    def __ne__(self, other: object) -> bool:
        return not isinstance(other, _Silent)

    def __lt__(self, other: object) -> bool:
        return False

    __le__ = __lt__
    __gt__ = __lt__
    __ge__ = __lt__

    def __hash__(self) -> int:
        return 0


@pytest.fixture(scope="module")
def app() -> Flask:
    return create_app(TestingConfig)


def test_all_page_templates_present() -> None:
    """Guard: the curated list matches Story 3.2's documented count of 29."""
    assert len(PAGE_TEMPLATES) == 29
    assert len(set(PAGE_TEMPLATES)) == 29


@pytest.mark.parametrize("template_name", PAGE_TEMPLATES)
def test_page_template_renders_in_layout_shell(app: Flask, template_name: str) -> None:
    """Each page template renders inside the new layout shell (AC3, AC6)."""
    env = app.jinja_env.overlay(undefined=_Silent)
    with app.test_request_context():
        html = env.get_template(template_name).render()
    assert 'id="sidebar"' in html, f"{template_name}: sidebar slot missing"
    assert 'id="main-content"' in html, f"{template_name}: main content area missing"
    assert 'id="app-shell"' in html, f"{template_name}: app shell wrapper missing"
    assert "<!DOCTYPE html>" in html, f"{template_name}: not a full document"
