# ADR 0002 — Verified identity for the Beeper UI: OIDC login, SCIM provisioning, and a local fallback

- **Status:** **Proposed** — awaiting `[H]` user approval (the Q11 architecture gate; see §0 and §12). No implementation may start before that approval is recorded here.
- **Date:** 2026-08-08 (proposed)
- **Author:** Claude (Synthesis Architect), Q11 / Task 6.2b design program
- **Affects:** `ui/beeper_ui/middleware/permissions.py`, `ui/beeper_ui/config.py`, `ui/beeper_ui/app.py`, new `ui/beeper_ui/routes/auth.py` + `scim.py` + `admin_users.py`, new `ui/beeper_ui/services/identity_store.py`, `ui/pyproject.toml`, `ui/frontend/src/api/*`, `ui/frontend/src/lib/*`, `helm/beeper/templates/ui-deployment.yaml`, `helm/beeper/values.yaml`, `Makefile` (demo targets), `docs/reqs/main.md` (FR54–FR62, NFR25–NFR26), `docs/deployment-guide.md`, `docs/design/route-parity-targets.md` (new §9 net-new-route convention)
- **Related:** [ADR 0001](0001-rbac-and-realtime-collaboration-in-react-ui.md) §0(a)/§1/§8; `docs/plans/react-ui.md` Q11, Task 6.2b, Milestone 2.3; `docs/plans/main.md` Phase 6 (demo workflow)

## 0. The directive, and what this ADR decides

**The user's directive (verbatim, 2026-08-08):** "Beeper should support OIDC/SSO in front with SCIM for group passthrough and assignment. But if SSO is disabled then there should still be an admin interface that allows admins to group users into Admins or Users groups."

*(Provenance note: during the design program the directive text was garbled in orchestration transit; the designers worked from an accurate reconstruction in the program brief. The orchestrator restored the verbatim text above from the conversation record after synthesis and confirmed the reconstruction matched it — no design input was invalidated.)*

This ADR is the joint decision record for all three pillars (OIDC, SCIM, local fallback) plus the resolutions of two adversarial reviews (security, operations/delivery). It supersedes the three per-pillar ADR proposals — there is exactly one ADR, one mode knob, one store, one resolver, one frontend seam.

## 1. Architecture overview — one mode enum

A single authoritative knob, refused-fast on contradiction at `create_app()` boot (all enforcement in `create_app()`, never `ProductionConfig.__init__`, which is dead code under `from_object(<class>)`):

```
BEEPER_AUTH_MODE = "none" | "local" | "oidc"        (default: "none")
BEEPER_SCIM_ENABLED = true|false                     (valid ONLY when mode == "oidc"; else boot ERROR + refused)
```

| Mode | Identity | Role source at request time | Who uses it |
|---|---|---|---|
| `none` (default) | anonymous | `X-Beeper-Role` header if `ALLOW_ROLE_HEADER` (dev/test), else default `user`; production = ADR 0001 §8 fail-closed (no admin path) | **demo/dev — `make demo-up`/`demo-deploy` unchanged, zero config (hard requirement)** |
| `local` | session cookie ↔ local account in the shared store | store lookup: `user.active` ⇒ `user.role` | production/staging without an IdP — the directive's fallback |
| `oidc` | session cookie established by a server-side OIDC authorization-code flow | **SCIM enabled:** store lookup (store-primary, authoritative). **SCIM disabled:** login-time claims snapshot (see §5.3 limitation) | production with an IdP |

Derived, never independent: "SSO enabled" ≡ `mode == "oidc"`; local password login is registered **only** in `local` mode (there is no password bypass of the IdP — resolves security CRITICAL-3); the SCIM blueprint is registered **only** when `oidc` + `BEEPER_SCIM_ENABLED` (disabled ⇒ plain 404, no fingerprintable surface).

**Topology: app-level OIDC in the Flask BFF** (Relying Party in-process; HttpOnly session cookie; tokens validated at the callback and discarded). Rejected: authenticating reverse proxy (trusted-header topology recreates the `X-Beeper-Role` spoof one hop up under `kubectl port-forward`); SPA-held bearer tokens (structurally cannot serve `EventSource` SSE, the `<a href>` CSV export, or the 10 retained Jinja remainder pages, and adds an XSS token-exfiltration surface). The cookie-session model was the one point both adversarial reviews endorsed; it is load-bearing for everything below.

## 2. Session, CSRF, and the 401/403 contract (all modes)

- **Session cookie:** Flask signed cookie (itsdangerous, `SECRET_KEY`), `HttpOnly`, `SameSite=Lax`. `Secure` is driven by an **explicit** config (`BEEPER_EXTERNAL_SCHEME=https|http`, default `https` ⇒ Secure on; the localhost/port-forward demo and dev set `http`) — never inferred from request introspection, so a TLS-terminating ingress speaking http to the pod cannot silently strip the flag (security LOW-10 adopted).
- **Content:** identity snapshot only — `{sub_or_user_id, email, name, role_snapshot, iat, exp}`. The snapshot is *authoritative in exactly one configuration* (`oidc` without SCIM, §5.3); in `local` and `oidc`+SCIM the role is re-resolved per request from the store behind a **60 s TTL in-process cache** (one TTL program-wide — ops F11.4). Session is rotated on login (fixation), absolute lifetime `BEEPER_SESSION_LIFETIME_HOURS` (default 8), no sliding refresh in v1.
- **SECRET_KEY becomes load-bearing:** in `local`/`oidc` modes `create_app()` refuses to start unless `SECRET_KEY` is supplied via env (the `secrets.token_hex(32)` per-process fallback would invalidate sessions on every restart and break multi-replica).
- **CSRF — one mechanism, one place** (resolves security MEDIUM-8 / ops F6): an **Origin/Referer host-equality check** on all unsafe methods (POST/PUT/PATCH/DELETE) whenever a session cookie authenticates the request, applied in the shared `before_request`. Mismatch ⇒ 403. This is the only scheme that covers React `fetch`, HTMX, and the retained Jinja remainder `<form>` posts with zero markup changes. `SameSite=Lax` is the browser backstop. The duplicate `X-Beeper-Csrf` header and `Content-Type: application/json` schemes from the pillar drafts are **dropped**. `/scim/v2/*` (bearer, no cookie) is exempt.
- **401 vs 403:**
  - `401` + `application/problem+json` (`…/errors/authentication-required`) — no/expired/invalid session in `local`/`oidc` mode, on `/api/v1/*` and SSE. New status; never a 302 (fetch/EventSource cannot follow a login redirect).
  - `403` — authenticated (or defaulted) caller lacking the required role. The existing RFC7807 body from `require_role` is unchanged byte-for-byte; `require_role` and its `.required_role` marker are untouched.
  - Retained Jinja remainder **page** routes: `302 → <login>?next=<path+query>` (FR53 permalinks stay access-consistent through the login round-trip). `next` is percent-**decoded before** validation; must be a same-origin relative path (reject decoded `//`, `\`, any scheme) — security LOW-10 adopted.
- **The React shell and its hashed assets are served unauthenticated in every mode.** The shell is static and data-free; all data sits behind the gated `/api/v1/*` surface. This collapses the three divergent per-pillar exemption lists into one small matrix (ops F11.5), tested table-driven:

| Path | none | local | oidc | Notes |
|---|---|---|---|---|
| `/health/api` | open | open | open | k8s probes must never 401 (crash-loop) |
| `/app/*` + shell assets | open | open (shell only; data via APIs) | open | login page renders inside the shell |
| `/auth/*`, `/api/v1/auth/*` | open | open | open | login/me must be reachable logged-out |
| `/socket.io/*` | 410 | 410 | 410 | 6.2a tombstone, exact body preserved |
| `/scim/v2/*` | 404 | 404 | own bearer check | never session/CSRF-gated |
| `/api/v1/*` (rest) + SSE | role chain | 401 unless session | 401 unless session | |
| Jinja remainder pages | role chain | 302 → login | 302 → login | |

- **SSE streams re-check authorization mid-flight** (security MEDIUM-7 adopted): the event-stream generators (`/api/v1/investigations/{id}/events`, retained HTML SSE) re-resolve the role on each keepalive/poll tick and terminate the stream when the identity is deactivated or drops below the gate; the 2.6b reconnect-backfill fetch then converts termination into the normal 401 → login path. This is what makes NFR25's ≤60 s bound true for the endpoints that stream the most sensitive data.

## 3. OIDC login (`oidc` mode)

- **Library: Authlib** (`authlib ^1.6` in `ui/pyproject.toml`) — maintained de-facto standard Flask RP: discovery, `state`/`nonce`, code exchange, JWKS fetch/rotation-cache, full ID-token validation. Deliberate transitive additions, recorded: `requests`, `cryptography`. Hand-rolled JOSE and stale wrappers rejected (ADR 0001 §4's "auth is easy to get subtly wrong").
- **Endpoints** (`auth_bp`, `/auth`): `GET /auth/login?next=` (code flow start; `next` validated per §2), `GET /auth/callback` (validate `state`; exchange; validate ID token — signature via issuer JWKS restricted to asymmetric algs, exact `iss`, `aud` contains client id, `exp`/`iat` leeway, `nonce` match; reject tokens missing `sub`; one-shot UserInfo fallback when the groups claim is absent from the ID token), `POST /auth/logout` (POST, Origin-checked; RP-initiated logout when configured), and the shared `GET /api/v1/auth/me` (§6).
- **Groups → role, one config pair for both OIDC and SCIM** (ops F7 adopted): `BEEPER_ADMIN_GROUPS` (comma-separated, case-insensitive; **default `Admins,beeper-admin`** — `Admins` per the directive's naming, `beeper-admin` for continuity with the group name the deleted token path historically looked for) and optional `BEEPER_USER_GROUPS` (default empty = any authenticated principal is `user`).
  - **SCIM disabled:** the callback maps claims → role and snapshots it into the session. Non-empty `BEEPER_USER_GROUPS` and membership in neither set ⇒ login refused (403 `not-provisioned`, no session).
  - **SCIM enabled:** the callback performs **no group-based refusal** — provisioning state decides (§5.2). This routes around Entra's dropped-`groups`-claim-over-200-groups failure, the exact claims defect store-primacy exists to avoid.
- **Steady state has no request-time JWT validation** — after login the credential is the signed session cookie. The only path to `admin` is a signature-verified login (or the store it feeds), satisfying ADR 0001 §0(a) item 2.

## 4. SCIM 2.0 provisioning (`oidc` mode + `BEEPER_SCIM_ENABLED`)

- **Surface** (`scim_bp`, `/scim/v2`, per the verified Okta/Entra/Keycloak client behavior): `ServiceProviderConfig` / `ResourceTypes` / `Schemas` (static); `/Users` GET(list: `userName eq`/`externalId eq` filters only, 1-based `startIndex`/`count`)+POST(201; duplicate `userName` ⇒ 409 `uniqueness`); `/Users/{id}` GET/PUT/PATCH/DELETE; `/Groups` GET(`displayName eq`, honor `excludedAttributes=members`)+POST; `/Groups/{id}` GET/PUT/PATCH/DELETE with **both** membership-delta dialects (Okta `{op:"remove",path:"members",value:[…]}` and Entra `members[value eq "…"]` path syntax); everything else 501. SCIM error schema (`urn:ietf:params:scim:api:messages:2.0:Error`) exclusively on `/scim/v2/*` — a recorded deviation from the house RFC7807 style; do not "fix" it later. Documented vendor quirks tolerated and fixture-tested: case-insensitive PATCH ops, string booleans for `active`, path-less ops, unknown attributes ignored. Zero new Python dependencies for this pillar (the `eq` filter is a ~10-line parse; JSON-Schema response validation is a dev-dependency only).
- **Auth:** long-lived bearer token(s) from one K8s Secret, compared with `hmac.compare_digest`; dual-token (`scimToken` + `scimTokenSecondary`) zero-downtime rotation; enabled-but-tokenless ⇒ every route 403 naming the misconfiguration (never open); disabled ⇒ blueprint not registered. Tokens never logged; audit lines carry a `sha256[:8]` fingerprint.
- **Blast-radius mitigations** (security HIGH-5 adopted — the SCIM token is an **admin-equivalent secret**, since group membership *is* the admin grant): (1) every provisioning mutation is audit-logged at INFO (op, resource, actor fingerprint), with admin-group membership changes flagged distinctly; (2) an optional chart `NetworkPolicy` (`ui.auth.scim.networkPolicy.*`) restricts `/scim/v2` ingress to the IdP egress range; (3) the deployment guide states the token's handling rules equal `SECRET_KEY`'s; (4) rotation runbook + token-age observability documented.
- **No JIT provisioning:** login never creates a store record. SCIM (in `oidc` mode) and the admin UI (in `local` mode) are the only writers.

## 5. The shared identity store — one store, two writers

**One** service, `ui/beeper_ui/services/identity_store.py` (`IdentityStoreService`), owning two Qdrant payload-only collections (zero-vector points, scroll+filter, `_ensure_collection`, module singleton + `reset_*` — the `collaboration_service.py` pattern; per the no-new-datastore constraint). Collections are created only on first `local`/`oidc` boot, so demo Qdrant stays clean. Resolves ops F1: the SCIM pillar's `scim_users`/`scim_groups` and the fallback pillar's `beeper_users`/two-fixed-groups designs are **merged and superseded**.

### 5.1 Schema

`beeper_users` (point id = uuid4): `external_id` (SCIM externalId, nullable), `user_name` (verbatim as sent/created), **`user_name_lc`** (casefolded — the canonical identity key, keyword-indexed), `display_name`, `emails`, `active` (bool; soft deactivation), `origin` (`"local" | "scim"`), **`password_hash`** (argon2id; nullable — pure-SCIM users have none), **`role`** (`"admin" | "user"` — THE authorization value; directly assigned in `local` mode, **derived** from group membership for SCIM-linked records and recomputed at write time on every group mutation), `group_ids` (read-model), `created` / `last_modified` / `last_login_at`.

`beeper_groups` (point id = uuid4): `external_id`, `display_name`, `display_name_lc` (indexed), `member_ids`. **Arbitrary** IdP-pushed groups are stored (passthrough — push two groups or fifty); the fallback pillar's two-fixed-rows concept is deleted. "Admins/Users" is realized as the configured `BEEPER_ADMIN_GROUPS` set, not physical rows; in `local` mode the groups collection is unused and the admin UI writes `role` directly.

Uniqueness: `user_name_lc` unique, service-layer check-then-insert under a process lock — safe at `replicaCount: 1`; a named invariant to revisit before any multi-replica change (§11).

### 5.2 Source-of-truth rule (resolves security CRITICAL-2 / HIGH-6, ops F5) — ONE answer

> **The session cookie carries identity, never authority — except in the one configuration that has no store source (`oidc` without SCIM), where the login-time claims snapshot is authoritative for the session's bounded lifetime.**

- **`local`:** per request, `store.get_by_id(session.user_id)` (60 s cache). Active ⇒ `role`; inactive/deleted ⇒ session cleared, 401.
- **`oidc` + SCIM:** per request, `store.lookup(email_lc, external_id)` — the pinned seam interface: `lookup(email_lc: str, external_id: str | None) -> {role, active} | None`, matching `user_name_lc` first, `external_id` fallback. Found+active ⇒ store `role` (claims snapshot ignored; mismatch logged, store wins). Found+inactive ⇒ **session cleared, 401** — a deactivated user never falls to default. Not found (authenticated but never provisioned) ⇒ default `user` (`BEEPER_SCIM_STRICT=true` opts into 403); never admin under any setting. The SCIM-push-races-first-login sequence therefore self-heals: login ⇒ `user`, push arrives, ≤60 s later ⇒ `admin`, no re-login.
- **`oidc` without SCIM:** snapshot from the callback; a demotion/deprovisioning takes effect at session expiry or next login (IdP refuses re-auth). **Documented limitation:** the revocation bound is `BEEPER_SESSION_LIFETIME_HOURS` (default 8, configurable down). Deployments needing prompt revocation enable SCIM — that is the feature's point.
- **Adopt-and-link with authoritative role recompute** (security HIGH-6 adopted): when SCIM POSTs a `userName` matching an existing local record (`user_name_lc`), the record is adopted — `external_id` set, `origin` linkage marked, `password_hash` retained inert — and **`role` is recomputed from SCIM group membership, discarding any prior local role**. On adoption the record's authority becomes SCIM-owned; the admin UI renders it read-only (409 `scim-owned-user` on writes) while in `oidc` mode. Required test: local-admin `alice@corp.com` + SCIM push placing alice only in a non-admin group ⇒ resolves to `user`. Flipping back to `local` mode restores local login (hash intact) and admin-UI write access.

### 5.3 Lifecycle guarantees (SCIM enabled)

Deactivate/delete ⇒ live sessions 401 within ≤60 s of the SCIM write **arriving at Beeper** (IdP push latency is out of our control — NFR25 is worded accordingly, ops F11.3); demote ⇒ admin routes 403 within ≤60 s, session survives; promote ⇒ effective ≤60 s, no re-login; in-flight SSE streams terminate per §2. **Zero-active-admins safeguard** (security MEDIUM-9, adopted in part): the store emits a CRITICAL log and a `/health/api` detail flag whenever a write (SCIM *or* admin UI *or* CLI) leaves zero active admins; the admin UI additionally refuses last-admin demotion/deactivation with 409 `last-admin`. SCIM writes are not refused (a hard 409 to the IdP would page someone with a permanent provisioning error) — they alarm instead.

## 6. Local fallback (`local` mode) — what a "user" is when SSO is off

**Decision: minimal, admin-managed local username/password accounts** (`[H]` — the key judgment call; see §12 D1). Rejected alternatives, recorded:

- **(c) anonymous + "identifier → admin" allowlist — unworkable.** There is no per-person identifier to allowlist: ClusterIP, port-forward, no ingress auth, no client certs, and the only trusted-ish header was removed by 6.2a. This option collapses back to the spoofable header.
- **(b) admin-issued personal access tokens — strictly worse (a).** The token *is* a password with worse ergonomics and worse leak characteristics (shell history, chat pastes, URLs), and all the hard parts (secret storage, hashing, sessions, revocation) remain.
- **(a) — chosen.** Grafana/MinIO-style admin-managed accounts, **not** an IdP: no self-registration, no email of any kind, no reset-by-link, no MFA, no password self-service UI (ops F10 cut — admin reset covers it), no profile pages, no third role. One new dependency: `argon2-cffi` (argon2id at rest; min length 12, no composition/rotation policy — NIST 800-63-aligned).

Sub-decisions: **login is required for everyone in `local` mode** (anonymous readers would make the Users group vestigial and the directive unmeetable — §12 D1 covers this too); login failures return an identical 401 body for unknown-user/bad-password/deactivated, with a small constant delay (no lockout table — lockout is a DoS lever against the only admin); hashes live in Qdrant payloads, accepted as same-trust-domain data with "do not expose Qdrant" documented; no hard delete in v1 (soft deactivation keeps history and prevents username-reuse identity confusion).

**Bootstrap (non-interactive, idempotent, demo-safe):** on `local`-mode boot, `ensure_bootstrap_admin()` reads `BEEPER_BOOTSTRAP_ADMIN_USERNAME`/`_PASSWORD` (Helm Secret-mounted env): absent user ⇒ created as active admin; existing user ⇒ **never overwritten** (a rotated password must not revert on pod restart). No seed + no active admin ⇒ prominent startup ERROR (not a crash) + `/health/api` flag; the recovery/secondary path is `flask --app beeper_ui create-admin <username>` (`--password-stdin`; documented `kubectl exec` runbook). No first-run setup page (an unauthenticated admin-creating page is a race/security hazard). The default demo path sets none of this and is untouched.

**Endpoints:** `auth_api_bp` (`/api/v1/auth`): `POST /login` (registered only in `local` mode), `POST /logout`, `GET /me` — all modes, shape `{auth_mode, authenticated, username?, email?, role?}`; **the unauthenticated response contains no `bootstrap_required` or other posture detail beyond `auth_mode`** (security LOW-11 adopted in part; `auth_mode` must stay — the shell needs it to route the login redirect). `admin_users_api_bp` (`/api/v1/admin/users`, every route `@require_role("admin")` with `.required_role` structurally tested): list / create / `PATCH {role|active|display_name}` (last-admin 409; scim-owned 409) / admin password reset. No DELETE.

**Admin UI (React, D3 — the first net-new route with no Jinja ancestor):** `/app/login` (minimal centered card outside the sidebar shell) and `/app/admin/users` (user table with role chip + origin badge + active status, role toggle, create dialog, deactivate/reactivate confirm, password reset, last-admin/scim-owned error states rendered from the RFC7807 bodies, FR22-style never-blank states). Lib primitives + Storybook stories: `LoginForm`, `UserTable`, `RoleSelect`, `UserFormDialog`, `ConfirmActionDialog`, `OriginBadge`, `UserMenu`; reuse `StatusBadge` variants where they fit. Role-aware nav (Manage → Users hidden for non-admins) is an affordance only — the BFF gates remain the boundary. `docs/design/route-parity-targets.md` gains a **§9 "Net-new React routes (no Jinja ancestor)"** block convention (`Jinja URL(s): none (net-new)`, `Parity target: FR<id>`), with the guard test extended for that shape.

## 7. The unified resolver — one function, one spec

`resolve_user_role()` becomes `resolve_request_identity()` (same `init_permissions` registration; sets `g.user_role` + new `g.user`; `require_role` untouched):

```
0. Path in the §2 exemption matrix → handle per matrix; return.
1. mode != "none" AND valid (signature+exp) session:
     local        → store.get_by_id(session.user_id)          # 60s cache
     oidc + SCIM  → store.lookup(session.email_lc, session.external_id)
     oidc, no SCIM→ session.role_snapshot
     inactive/missing-where-required → clear session, fall to step 2
     else → g.user = identity; g.user_role = role; return
2. mode != "none" AND no valid session:
     API/SSE path → 401 application/problem+json (authentication-required)
     page path    → 302 → <mode login>?next=<decoded-validated path+query>
3. mode == "none":
     ALLOW_ROLE_HEADER and X-Beeper-Role in VALID_ROLES → that role; return
     default "user".
```

**`_extract_role_from_k8s_token` is deleted unconditionally, in every mode, as an independent hotfix (Task 8.2) that does not wait for any pillar** — security CRITICAL-1. Verified against current `main`: the unverified Bearer peek runs *first* on every request and is **not** gated by `ALLOW_ROLE_HEADER`, so a crafted 3-segment token with `{"groups":["beeper-admin"]}` passes `require_role("admin")` in production **today**; `ProductionConfig`'s docstring claim that "every `@require_role('admin')` route resolves to 403 for every caller in production" is false and is corrected in the same change. The crafted-JWT regression test is retained permanently as a guard against the path's return (it must now assert "ignored", not "500-proofed"). A stray `Authorization: Bearer` header is simply ignored in all modes. The fallback pillar's "keep the peek in mode `none`" position is **overruled**.

The 31-test `test_permissions.py` suite stays the gate-semantics spec: header-path, default-role, production-refusal, `require_role`, RFC7807-403 tests unchanged; the tests pinning the unverified-JWT-groups path are deleted **with named replacements** (verified-login ⇒ admin; tampered/expired session ⇒ never admin), recorded in the Task 8.2/8.3 ACs so the swap is auditable. `TestingConfig` keeps `ALLOW_ROLE_HEADER=True` and `AUTH_MODE=none` — the `_RoleClient`/`admin_client`/`user_client` conftest fixtures and every dependent suite run unmodified.

## 8. Config and deployment surface

**Flask config** (env-backed class attributes; boot enforcement in `create_app()`): `BEEPER_AUTH_MODE`, `BEEPER_SCIM_ENABLED`, `BEEPER_ADMIN_GROUPS`, `BEEPER_USER_GROUPS`, `BEEPER_SCIM_STRICT`, `BEEPER_OIDC_ISSUER` / `_CLIENT_ID` / `_CLIENT_SECRET` / `_REDIRECT_URL` (empty ⇒ derived from request host, covers port-forward) / `_SCOPES` (default `openid profile email groups`) / `_GROUPS_CLAIM` (default `groups`) / `_POST_LOGOUT_REDIRECT_URL`, `BEEPER_SESSION_LIFETIME_HOURS` (8), `BEEPER_EXTERNAL_SCHEME`, `BEEPER_SCIM_TOKEN` / `_SECONDARY`, `BEEPER_BOOTSTRAP_ADMIN_USERNAME` / `_PASSWORD`, existing `ALLOW_ROLE_HEADER` unchanged. Boot refusals: `oidc` without issuer/client-id/client-secret; `local`/`oidc` without env `SECRET_KEY`; `BEEPER_SCIM_ENABLED` outside `oidc`; SCIM enabled without a token (surface registers fail-closed 403, per §4).

**Helm — one `ui.auth` tree, one Secret** (ops F9 adopted; the plaintext `token:` convenience value is deleted):

```yaml
ui:
  flaskEnv: production            # see below; make demo-* overrides to development
  auth:
    mode: none                    # none | local | oidc — demo default: none
    existingSecret: ""            # keys per mode: sessionSecret (local/oidc, required);
                                  # clientSecret (oidc); scimToken, scimTokenSecondary (scim);
                                  # bootstrapUsername, bootstrapPassword (local)
    oidc:  { issuer: "", clientId: "", redirectUrl: "", scopes: "...", groupsClaim: "groups", postLogoutRedirectUrl: "" }
    scim:  { enabled: false, strict: false, networkPolicy: { enabled: false, allowFrom: [] } }
    local: { bootstrapFromSecret: true }
    adminGroups: "Admins,beeper-admin"
    userGroups: ""
```

**`FLASK_ENV` (the pre-existing hole, resolved):** verified — nothing in `helm/`, `Makefile`, or `ui/Dockerfile` sets `FLASK_ENV`, so a Helm-deployed pod runs `DevelopmentConfig` and honors `X-Beeper-Role: admin` in-cluster today, making 6.2a's production refusal latent. Resolution (security HIGH-4 adopted; ops F3's default-development counter-proposal **rebutted in part**): the chart defaults `ui.flaskEnv: production`; `make demo-up`/`demo-deploy` explicitly pass `ui.flaskEnv=development` in the same PR, so the demo's header-driven admin affordance keeps working with zero interactive steps (the demo-workflow requirement is preserved by the Makefile, not by an insecure chart default). `get_config()`'s unknown/unset-value fallback flips from `DevelopmentConfig` to `ProductionConfig` so a typo fails safe. The "default manifest byte-identical" snapshot guard is re-pinned to **demo values** output (`ui.flaskEnv=development`, `auth.mode=none` ⇒ everything else byte-identical to today).

No ServiceAccount, no volumes, no sidecars, no ingress requirement — the design adds zero cluster-identity surface (TokenReview was not chosen: it authenticates pods/kubeconfig-holders, not people, and needs RBAC the chart deliberately lacks).

**Frontend seam (one, shared by all modes — ops F4/F6):** `src/api/http.ts` `apiFetch` (same-origin credentials; on 401-`authentication-required` redirect to the mode's login — `oidc` → `/auth/login?next=`, `local` → `/app/login?next=`, **`none` → never redirect**; 403 → typed `PermissionDeniedError` rendered as a permission state); all 8 existing clients migrate (static-sweep test per the client-side test convention); `useCurrentUser` hydrates from `/api/v1/auth/me` and is **failure-tolerant** (unreachable/unmocked ⇒ treated as `{auth_mode:"none"}`) — this plus never-redirect-in-`none` is what keeps the existing 87 Playwright e2e specs (which run against `vite preview` with no Flask) green; a shared e2e auth fixture mocks `/api/v1/auth/me` for the specs that assert auth states. The stub-IdP full-flow e2e AC from the OIDC draft is downgraded to Flask test-client integration tests (a real second Playwright project against Flask+stub IdP is optional follow-on work, costed honestly — ops F4c).

## 9. Adversarial-review resolutions (HIGH and above)

| Finding | Resolution |
|---|---|
| SEC CRITICAL-1 (unverified-JWT admin bypass live in prod; fallback pillar kept it in mode `none`) | **Adopted.** Deleted unconditionally as standalone hotfix Task 8.2; docstring corrected; permanent regression guard. Fallback position overruled. §7. |
| SEC CRITICAL-2 (role-in-cookie stale-admin window; pillars contradict) | **Adopted with one bounded exception.** Identity-only cookie + per-request store resolution wherever a store source exists (`local`, `oidc`+SCIM). The exception — `oidc` without SCIM uses the login-time snapshot — is retained deliberately: there is no store to consult and no JIT writes; the revocation bound equals the configurable session lifetime and is documented as the reason to enable SCIM. The review's "cap far below 8h" is **rebutted**: 8h default, configurable, ClusterIP-internal tool, IdP still gates re-login. §5.2/§5.3. |
| SEC CRITICAL-3 / OPS F2 (three mode knobs; SSO+local password bypass) | **Adopted.** One enum `BEEPER_AUTH_MODE`; SCIM valid only under `oidc`; local login registered only in `local`; contradictions refused at boot. §1. |
| SEC HIGH-4 / OPS F3 (FLASK_ENV unset; contradictory fixes) | **Adopted (security's default), ops partially rebutted.** Chart defaults `production`; demo opts into `development` via `make demo-*` in the same PR; `get_config()` falls back safe; snapshot guard re-pinned to demo values. §8. |
| SEC HIGH-5 (SCIM token = self-provision-an-admin credential) | **Adopted.** Audit logging with fingerprints + flagged admin-group changes, optional NetworkPolicy, admin-equivalent-secret documentation, dual-token rotation + age observability. §4. |
| SEC HIGH-6 / OPS F5 (adopt-and-link role retention; `sub` vs email key mismatch) | **Adopted.** Canonical key `user_name_lc` (casefolded email/username) + `external_id` machine join; pinned `lookup(email_lc, external_id)` seam; adoption recomputes role authoritatively (SCIM-owned thereafter); the named local-admin-demoted-by-SCIM test is a required AC. §5. |
| OPS F1 (two incompatible stores) | **Adopted.** One store/service/schema (§5.1); two-fixed-groups deleted; one owning task (8.3). |
| OPS F4 (87 e2e broken; unimplementable stub-IdP AC) | **Adopted.** Failure-tolerant probe, never-redirect-in-`none`, shared e2e auth fixture task, AC downgraded to integration tests. §8. |
| OPS F6 (frontend seam specified twice; CSRF conflict) | **Adopted.** One `apiFetch`, one `/api/v1/auth/me`, mode-derived redirect; Origin/Referer as the single CSRF mechanism. §2/§8. |
| SEC MEDIUM-7/8/9, LOW-10/11; OPS F7–F11 | Adopted as specified inline (§2 SSE re-check, §2 single CSRF, §5.3 zero-admin alarm + last-admin 409 [break-glass stays **no** — rebutted in part: recovery is the `create-admin` CLI via `kubectl exec` plus the CRITICAL alarm; a standing password bypass of the IdP is the worse trade], §2 cookie/`next` hardening, §6 minimal unauthenticated `/me` [keeping `auth_mode` — rebutted in part, the shell needs it], §3 unified group config, this ADR as the single rollout order, §8 single values tree, §6 password-self-service cut, `responses` not `respx` for Authlib stubs / 60 s TTL unified / NFR25 wording / one exemption matrix / suite-green-in-mode-none promoted to a program-level gate at every step). |

## 10. Rollout order (every step lands default-off; production stays fail-closed; demo output stays byte-identical throughout)

1. **8.1** — this ADR approved (`[H]`), FR54–FR62/NFR25–26 landed.
2. **8.2** — fail-closed hotfix (JWT-peek deletion + docstring + `ui.flaskEnv` + demo Makefile + `get_config` safe fallback). *Not blocked on 8.1 — ship even if the rest slips.*
3. **8.3** — shared store + unified resolver + session core + CSRF + exemption matrix.
4. **8.4** — frontend auth seam + e2e auth fixture.
5. **8.5 / 8.6 / 8.8** in parallel — OIDC login; local auth + bootstrap; SCIM surface.
6. **8.7** — admin users view. **8.9** — Helm/secrets consolidation, deployment guide, live-IdP `[H]` validation, demo regression gate.

Program-level gate at every step: the full existing pytest suite (2282) green **unmodified** under `AUTH_MODE=none`, plus the demo-values Helm snapshot unchanged.

## 11. Non-goals and named invariants (v1)

No third role/tier (two-tier `admin`/`user` only, per the directive). No self-registration, email flows, MFA, password self-service, or profile pages. No JIT provisioning. No API tokens for scripted `/api/v1/*` access (follow-on if demanded; never an unverified stopgap). No break-glass password login in `oidc` mode. No hard user delete in `local` mode. No server-side session store / pre-expiry cookie revocation (escalation path: Qdrant-backed sessions, only under a compliance requirement). **Named invariant:** store uniqueness and the bootstrap idempotency lock are process-local — revisit before `ui.replicaCount > 1`.

## 12. Decision points requiring explicit `[H]` blessing (batched into Task 8.1)

| # | Decision | Recommendation | Live alternative |
|---|---|---|---|
| D1 | What a "user" is with SSO off: **admin-managed local username/password accounts, login required for everyone in `local` mode** | Adopt (a): the only workable identity source; scope held to Grafana-style minimal | (b) admin-issued tokens (same machinery, worse leaks); accept `user`-only production + `kubectl`-only admin (Q11 option (c), no admin UI) |
| D2 | Role source when SCIM is enabled: **store-primary**, authenticated-but-unprovisioned ⇒ default `user` (`BEEPER_SCIM_STRICT` for 403) | Adopt: makes deprovisioning real (≤60 s); default-`user` hides IdP push lag | claims-primary (breaks on Entra group-claim overflow; 8h stale-role windows); strict-by-default |
| D3 | Chart defaults `ui.flaskEnv: production`; demo opts into development via `make demo-*` | Adopt: secure-by-default; demo preserved by the Makefile in the same PR | default `development` (leaves the in-cluster header hole open by default) |
| D4 | No break-glass local login in `oidc` mode; recovery = `create-admin` CLI via `kubectl exec` + zero-admin CRITICAL alarm | Adopt: no standing IdP bypass | gated `BEEPER_BREAK_GLASS=true` bootstrap-admin login (classic lockout mitigation, at the cost of an MFA/conditional-access bypass) |
