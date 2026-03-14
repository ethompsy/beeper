#!/usr/bin/env python3
"""Beeper Investigator — local demo with mocked infrastructure.

Runs the full investigation pipeline against a simulated incident scenario,
showing each step's output as the agent works through the investigation.
"""

import json
import logging
import textwrap
from typing import Any
from unittest.mock import MagicMock

from beeper_investigator.agent import InvestigationResult, InvestigatorAgent, SourceClients
from beeper_investigator.context import InvestigationContext
from beeper_investigator.kb.schemas import SearchResult
from beeper_investigator.llm.cache import LlmResponseCache
from beeper_investigator.llm.client import LlmClient, LlmConfig

# ── Pretty output ────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"


def banner(text: str) -> None:
    print(f"\n{BOLD}{BLUE}{'=' * 70}")
    print(f"  {text}")
    print(f"{'=' * 70}{RESET}\n")


def step_header(name: str) -> None:
    print(f"  {BOLD}{CYAN}--- {name} ---{RESET}")


def kv(key: str, value: str, indent: int = 4) -> None:
    pad = " " * indent
    print(f"{pad}{DIM}{key}:{RESET} {value}")


def section(title: str) -> None:
    print(f"\n  {BOLD}{MAGENTA}{title}{RESET}")


# ── Mock LLM responses ──────────────────────────────────────────────────────

IMPACT_RESPONSE = json.dumps(
    {
        "customer_impacting": True,
        "reasoning": (
            "The /checkout endpoint is customer-facing; HTTP 5xx errors "
            "directly prevent users from completing purchases."
        ),
    }
)

RCA_RESPONSE = json.dumps(
    {
        "root_cause_hypothesis": (
            "PostgreSQL connection pool exhaustion on payments-db caused "
            "cascading query timeouts, leading to 5xx responses on /checkout"
        ),
        "confidence_level": "high",
        "confidence_percentage": 92,
        "supporting_evidence": [
            "pg_stat_activity at max_connections (100/100) for 12 min",
            "HTTP 5xx rate spiked from 0.1% to 18% at 14:32 UTC",
            "Prior incident inv-2024-042 confirms identical failure pattern",
            "Connection wait time p99 exceeded 30s (normal: <50ms)",
        ],
        "alternative_hypotheses": [],
        "additional_data_needs": [],
        "kb_citation": "inv-2024-042",
    }
)

RESOLUTION_RESPONSE = json.dumps(
    {
        "recommendations": [
            {
                "action": (
                    "Increase PgBouncer max_client_conn from 100 to 200 "
                    "and default_pool_size from 20 to 40"
                ),
                "confidence": "high",
                "expected_outcome": (
                    "Immediate relief of connection pool saturation; "
                    "5xx rate drops to baseline within 2-3 min"
                ),
                "risk_assessment": "low",
                "based_on_prior_incident": "inv-2024-042",
            },
            {
                "action": (
                    "Add circuit breaker to payments-service DB adapter "
                    "with 50% error threshold and 30s recovery window"
                ),
                "confidence": "high",
                "expected_outcome": (
                    "Prevent cascading failures; degrade gracefully "
                    "instead of hard-failing all requests"
                ),
                "risk_assessment": "low",
                "based_on_prior_incident": None,
            },
            {
                "action": (
                    "Scale payments-service deployment from 3 to 6 replicas "
                    "to distribute connection load"
                ),
                "confidence": "medium",
                "expected_outcome": (
                    "Reduce per-pod connection pressure by ~50%"
                ),
                "risk_assessment": "medium",
                "based_on_prior_incident": None,
            },
        ],
        "ranking_rationale": (
            "PgBouncer config change is proven fix from prior incident "
            "inv-2024-042; circuit breaker is preventative with no downside; "
            "scaling is complementary but addresses symptom not root cause"
        ),
        "diagnostic_actions": [
            "Verify current pg_stat_activity with: SELECT count(*) FROM pg_stat_activity",
            "Check PgBouncer stats: SHOW POOLS",
        ],
    }
)

DOCUMENTATION_RESPONSE = json.dumps(
    {
        "title": (
            "Connection Pool Exhaustion on payments-db Causing Checkout 5xx Errors"
        ),
        "summary": (
            "PostgreSQL connection pool exhaustion on payments-db caused "
            "cascading checkout failures with 18% 5xx error rate. "
            "Root cause confirmed with 92% confidence via signal correlation "
            "and prior incident match (inv-2024-042). Recommended fix: "
            "increase PgBouncer pool limits and add circuit breaker."
        ),
        "root_cause": (
            "PgBouncer max_client_conn reached 100/100 limit due to "
            "increased traffic, causing new connections to queue and timeout"
        ),
        "resolution": (
            "Increase PgBouncer pool size (proven in inv-2024-042); "
            "add circuit breaker for graceful degradation"
        ),
        "signals_summary": (
            "pg_stat_activity saturated at 100%; HTTP 5xx rate 18%; "
            "connection wait p99 > 30s; Loki shows 'connection pool exhausted' "
            "errors across all pods"
        ),
        "confidence_overview": (
            "High confidence (92%) — strong signal correlation confirmed "
            "by exact KB match from Q3 incident"
        ),
        "key_findings": [
            "DB connection pool was the bottleneck, not application code",
            "Prior incident inv-2024-042 had identical root cause and resolution",
            "All 3 payments-service pods affected simultaneously",
            "Circuit breaker absence allowed cascading failure to propagate",
        ],
    }
)


# ── Build mock LLM client ───────────────────────────────────────────────────


def make_mock_llm() -> LlmClient:
    """Create a real LlmClient with patched completion methods."""
    config = LlmConfig(
        provider="anthropic",
        model="claude-sonnet-4",
        api_key="demo-key",
        screening_model="claude-3-haiku-20240307",
        deep_rca_model="claude-opus-4",
        embedding_model="text-embedding-3-small",
        cache_enabled=False,
    )
    client = LlmClient.__new__(LlmClient)
    client.config = config
    client._model_usage = {}
    client._cache = LlmResponseCache(ttl_seconds=0, max_entries=0)

    # Route responses based on system prompt content (each step has a unique prompt)
    standard_calls = {"n": 0}
    standard_responses = [
        # KB Query synthesis (standard model, 1st call)
        json.dumps({
            "prior_research_summary": (
                "Prior incident inv-2024-042 shows identical pattern: "
                "PgBouncer pool exhaustion caused checkout 5xx errors. "
                "Resolution was increasing pool limits."
            ),
            "recommended_resolution": (
                "Increase PgBouncer max_client_conn and default_pool_size"
            ),
            "confidence_boost": "high",
        }),
        RESOLUTION_RESPONSE,     # Resolution recommendations (standard model, 2nd call)
        DOCUMENTATION_RESPONSE,  # Investigation documentation (standard model, 3rd call)
    ]

    def fake_complete_sync(
        messages: Any, max_tokens: int = 4096, temperature: float = 0.0,
        *, model: str | None = None, **kw: Any,
    ) -> str:
        effective = model or config.get_litellm_model()
        client._model_usage[effective] = client._model_usage.get(effective, 0) + 1

        # Route by model to match the correct response
        if "haiku" in effective:
            # Screening model → Customer Impact
            return IMPACT_RESPONSE
        elif "opus" in effective:
            # Deep RCA model → RCA Hypothesis
            return RCA_RESPONSE
        else:
            # Standard model → KB synthesis, Resolution, Documentation (in order)
            idx = min(standard_calls["n"], len(standard_responses) - 1)
            standard_calls["n"] += 1
            return standard_responses[idx]

    client.complete_sync = fake_complete_sync  # type: ignore[method-assign]
    client.embed_sync = lambda text: [0.01] * 1536  # type: ignore[method-assign]
    client.test_connection = lambda: True  # type: ignore[method-assign,assignment,return-value]
    return client


# ── Build mock KB client ─────────────────────────────────────────────────────


def make_mock_kb() -> MagicMock:
    """Create a mock KB client that returns prior incident data."""
    kb = MagicMock()
    kb.health_check.return_value = True

    prior_incident = SearchResult(
        id="inv-2024-042",
        score=0.94,
        payload={
            "entry_type": "investigation",
            "title": "Connection pool exhaustion on payments-db",
            "summary": (
                "PgBouncer pool saturation caused checkout failures. "
                "Fixed by increasing max_client_conn from 50 to 100."
            ),
            "service": "payments",
            "condition": "High error rate on /checkout",
            "root_cause": "PgBouncer connection pool exhaustion",
            "resolution": "Increase PgBouncer max_client_conn and default_pool_size",
            "confidence_level": "high",
        },
    )
    kb.search_investigations.return_value = [prior_incident]
    kb.search_knowledge.return_value = []
    kb.client.upsert.return_value = None
    return kb


# ── Demo runner ──────────────────────────────────────────────────────────────


class DemoStatusUpdater:
    """Status updater that prints to console instead of K8s."""

    def update_message(self, msg: str) -> None:
        print(f"    {DIM}[status] {msg}{RESET}")

    def set_completed(self, summary: str) -> None:
        print(f"    {GREEN}[completed]{RESET} {summary}")

    def set_failed(self, error: str) -> None:
        print(f"    {RED}[failed]{RESET} {error}")


def display_result(result: InvestigationResult) -> None:
    """Pretty-print the investigation result."""
    banner("INVESTIGATION RESULT")

    status = f"{GREEN}SUCCESS{RESET}" if result.success else f"{RED}FAILED{RESET}"
    kv("Status", status, 2)
    kv("Summary", result.summary[:120], 2)

    if result.findings:
        section("Step Summaries")
        for i, finding in enumerate(result.findings, 1):
            print(f"    {DIM}{i}.{RESET} {finding[:100]}")

    # Key metadata highlights
    meta = result.metadata

    if "root_cause_hypothesis" in meta:
        section("Root Cause Analysis")
        kv("Hypothesis", meta["root_cause_hypothesis"][:100])
        kv(
            "Confidence",
            f"{meta.get('confidence_level', '?')} "
            f"({meta.get('confidence_percentage', '?')}%)",
        )
        if meta.get("kb_citation"):
            kv("KB Citation", meta["kb_citation"])
        if meta.get("supporting_evidence"):
            kv("Evidence", "")
            for e in meta["supporting_evidence"][:4]:
                print(f"        {DIM}-{RESET} {e[:90]}")

    if "recommendations" in meta:
        section("Resolution Recommendations")
        for i, rec in enumerate(meta["recommendations"][:3], 1):
            conf = rec.get("confidence", "?")
            risk = rec.get("risk_assessment", "?")
            color = GREEN if conf == "high" else YELLOW if conf == "medium" else RED
            print(f"    {color}{i}. [{conf}/{risk} risk]{RESET} {rec['action'][:80]}")
            if rec.get("based_on_prior_incident"):
                print(f"       {DIM}Based on: {rec['based_on_prior_incident']}{RESET}")

    if "model_usage" in meta:
        section("Model Usage (Tiered Selection)")
        for model, count in sorted(meta["model_usage"].items()):
            tier_label = ""
            if "haiku" in model:
                tier_label = f" {DIM}(screening){RESET}"
            elif "opus" in model:
                tier_label = f" {DIM}(deep_rca){RESET}"
            elif "sonnet" in model:
                tier_label = f" {DIM}(standard){RESET}"
            print(f"      {model}: {count} call(s){tier_label}")

    print()


def main() -> None:
    # Suppress noisy logs, keep just our demo output
    logging.getLogger("beeper_investigator").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.CRITICAL)

    banner("BEEPER INVESTIGATOR DEMO")
    print(textwrap.dedent("""\
        Beeper is an AI-powered incident investigation engine for Kubernetes.
        When an anomaly is detected, Beeper spawns an investigator agent that:

          1. Assesses customer impact (screening model — fast & cheap)
          2. Queries the knowledge base for prior incidents
          3. Correlates signals across Prometheus & Loki
          4. Generates a root cause hypothesis (deep RCA model — powerful)
          5. Produces resolution recommendations (standard model)
          6. Documents everything back to the knowledge base

        This demo simulates a real investigation with mocked infrastructure.
    """))

    # ── Scenario ──
    section("Incident Scenario")
    kv("Condition", "High error rate on /checkout endpoint")
    kv("Service", "payments")
    kv("Severity", "critical")
    kv("Namespace", "production")
    print()
    input(f"  {DIM}Press Enter to start the investigation...{RESET}")

    # ── Build agent ──
    context = InvestigationContext(
        investigation_id="inv-demo-001",
        namespace="production",
        condition="High error rate on /checkout endpoint — 5xx at 18%",
        service="payments",
        severity="critical",
    )

    llm_client = make_mock_llm()
    kb_client = make_mock_kb()
    status = DemoStatusUpdater()

    agent = InvestigatorAgent(
        context=context,
        kb_client=kb_client,
        llm_client=llm_client,
        sources=SourceClients(),
        status_updater=status,  # type: ignore[arg-type]
    )

    banner("RUNNING INVESTIGATION PIPELINE")
    result = agent.run()
    display_result(result)

    banner("DEMO COMPLETE")
    print(textwrap.dedent(f"""\
        {DIM}In production, Beeper runs inside Kubernetes:
        - The operator watches for anomaly CRDs and spawns investigator Jobs
        - Each Job runs this same pipeline against live Prometheus/Loki data
        - Results are persisted to Qdrant for future KB matches
        - The Flask UI at /investigations/ shows real-time progress
        - Tiered model selection balances cost vs capability per step{RESET}
    """))


if __name__ == "__main__":
    main()
