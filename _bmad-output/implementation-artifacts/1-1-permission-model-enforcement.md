# Story 1.1: Permission Model Enforcement

Status: ready-for-dev

## Story

As an **admin**,
I want role-based access control enforced across all UI routes and APIs,
so that only authorized users can configure trust levels, SLOs, and other safety-critical settings.

## Acceptance Criteria

1. **AC1: Admin-only route protection**
   **Given** a Flask route decorated with `@require_role("admin")`
   **When** a user with role "user" attempts to access it
   **Then** the request is rejected with HTTP 403 and an RFC 7807 error response
   **And** the rejection is logged with the user context

2. **AC2: Role resolution middleware**
   **Given** the UI application starts up
   **When** the permission middleware initializes
   **Then** user role is determined from K8s ServiceAccount token (production), `X-Beeper-Role` header (development), or defaults to "user"
   **And** the role is set on Flask `g.user_role` for the request lifecycle

3. **AC3: No regression on existing routes**
   **Given** all existing UI routes (investigations, knowledge, sources, metrics, spending)
   **When** the permission model is applied
   **Then** all existing routes remain accessible to role "user" (no regression)
   **And** all existing tests (626 UI tests) continue passing

## Tasks / Subtasks

- [ ] Task 1: Create permission middleware module (AC: #2)
  - [ ] 1.1: Create `ui/beeper_ui/middleware/__init__.py` package
  - [ ] 1.2: Create `ui/beeper_ui/middleware/permissions.py` with `require_role()` decorator and `before_request` role resolver
  - [ ] 1.3: Implement role resolution chain: K8s ServiceAccount token → `X-Beeper-Role` header → default "user"
  - [ ] 1.4: Set `g.user_role` in `before_request` handler

- [ ] Task 2: Create RFC 7807 error response for 403 (AC: #1)
  - [ ] 2.1: Implement `permission_denied()` helper returning RFC 7807 JSON with type, title, status=403, detail
  - [ ] 2.2: Log rejection with user context (role, path, method) using structured format

- [ ] Task 3: Register middleware in app factory (AC: #2)
  - [ ] 3.1: Add `before_request` handler registration in `create_app()` in `app.py`
  - [ ] 3.2: Ensure middleware runs before all route handlers

- [ ] Task 4: Verify existing routes remain unprotected (AC: #3)
  - [ ] 4.1: Verify all existing blueprints (investigations, knowledge, sources, metrics, spending, health) do NOT have `@require_role` — they are accessible to all authenticated users by default
  - [ ] 4.2: Run full existing test suite (626 tests) to confirm zero regressions

- [ ] Task 5: Write comprehensive tests (AC: #1, #2, #3)
  - [ ] 5.1: Add auth fixtures to `conftest.py` — `admin_client` and `user_client` with appropriate headers
  - [ ] 5.2: Test `@require_role("admin")` rejects role "user" with 403 + RFC 7807
  - [ ] 5.3: Test `@require_role("admin")` allows role "admin"
  - [ ] 5.4: Test `@require_role("user")` allows both roles
  - [ ] 5.5: Test default role is "user" when no header/token present
  - [ ] 5.6: Test `X-Beeper-Role` header sets role in development mode
  - [ ] 5.7: Test `g.user_role` is available in request context
  - [ ] 5.8: Test RFC 7807 error response format (type, title, status, detail, instance fields)
  - [ ] 5.9: Test all existing routes still accessible without role header (defaults to "user", all current routes are user-accessible)

## Dev Notes

### Architecture Compliance

**Permission Enforcement Pattern (from architecture.md):**
```python
# Flask decorator — applied to every route
@require_role("admin")  # or "user" (default)
def configure_trust_level(service_name):
    ...

# Middleware sets g.user_role from:
# 1. K8s ServiceAccount token (production)
# 2. X-Beeper-Role header (development)
# 3. Default "user" if no auth configured
```
[Source: _bmad-output/planning-artifacts/architecture.md#Authentication & Security]

**Admin-only operations (for future stories, NOT this story):**
- Trust level configuration (FR16, FR22)
- ServiceLevel CRD management (FR1, FR5)
- Repository CRD management (FR23)
- Error budget policies (FR5)
- Noise report access (FR20)

**User operations (accessible to both roles):**
- View/interact with investigations
- Configure notification channels
- KB read/write/correct
- View dashboards
[Source: _bmad-output/planning-artifacts/architecture.md#Authentication & Security]

### Implementation Approach

**Key Design Decisions:**

1. **Two-tier only (admin/user):** Do NOT implement fine-grained RBAC. The architecture explicitly states 2-tier is sufficient for v0.2.0. Fine-grained roles are deferred.
   [Source: _bmad-output/planning-artifacts/architecture.md#Acceptable MVP Trade-offs]

2. **`require_role()` is a decorator, not middleware for every route.** The `before_request` handler ONLY resolves the role and sets `g.user_role`. The decorator checks the role on specific routes. Existing routes do NOT get decorated — they are accessible to all.

3. **RFC 7807 error format** is mandatory for all API errors. The 403 response MUST follow this format:
   ```json
   {
     "type": "https://beeper.dev/errors/permission-denied",
     "title": "Permission Denied",
     "status": 403,
     "detail": "Admin role required to access this resource",
     "instance": "/path/that/was/requested"
   }
   ```
   [Source: _bmad-output/planning-artifacts/architecture.md#Format Patterns]

4. **K8s ServiceAccount token parsing** in production: Read from `Authorization: Bearer <token>` header, decode JWT to extract group/role claims. For v0.2.0 MVP, use a simple approach — check for `beeper-admin` group in token claims. If token parsing fails or no token, default to "user".

5. **Structured logging** for rejections:
   ```json
   {
     "timestamp": "...",
     "level": "WARN",
     "component": "ui",
     "message": "Permission denied",
     "context": {
       "user_role": "user",
       "required_role": "admin",
       "path": "/admin/config",
       "method": "POST"
     }
   }
   ```
   [Source: _bmad-output/planning-artifacts/architecture.md#Process Patterns]

### Technical Requirements

- **Python 3.11+** — use `|` union types, not `Optional[]`
- **Flask 3.0** — use `g` object for request-scoped role storage
- **No new dependencies** — this uses only Flask built-ins (`g`, `request`, `functools.wraps`, `before_request`)
- **Pydantic NOT required** — simple decorator + dict response for RFC 7807
- **Content-Type:** Return `application/problem+json` for RFC 7807 errors

### File Structure Requirements

**New files to create:**
```
ui/beeper_ui/middleware/
├── __init__.py
└── permissions.py          # require_role() decorator + role resolver
```

**Files to modify:**
```
ui/beeper_ui/app.py         # Register before_request handler
ui/beeper_ui/config.py      # No changes needed (role comes from header/token, not config)
ui/tests/conftest.py         # Add admin_client and user_client fixtures
```

**New test file:**
```
ui/tests/test_permissions.py  # Comprehensive permission tests
```

### Testing Requirements

- **Framework:** pytest (existing)
- **Mocking:** No external services to mock — permission is purely request-level
- **Test isolation:** Each test should set/not set the `X-Beeper-Role` header independently
- **Regression testing:** Run full `poetry run pytest` and `poetry run ruff check .` and `poetry run mypy .`
- **Target:** All 626 existing tests MUST continue passing. New permission tests should add ~15-25 tests.

### Critical Guardrails

1. **DO NOT add `@require_role` to any existing routes** — this story only creates the infrastructure. Future stories (1.3+) will use it on new admin-only routes.
2. **DO NOT introduce any new Python dependencies** — use only Flask/Werkzeug built-ins.
3. **DO NOT modify existing route files** — middleware registration goes in `app.py` only.
4. **DO NOT implement session/login/logout** — this is header-based role checking, not authentication.
5. **DO NOT break the existing test client** — the default role must be "user" when no header is present, ensuring all existing tests pass unmodified.
6. **`before_request` handler must be lightweight** — just extract header/token and set `g.user_role`. No database calls, no external service calls.

### Project Structure Notes

- Alignment with unified project structure: New `middleware/` package follows existing pattern of `routes/`, `services/`, `utils/` packages under `beeper_ui/`.
- Permission module placement matches architecture decision: "Permission model (decorator + middleware) — foundation for everything" [Source: architecture.md#Decision Impact Analysis]

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Authentication & Security] — Permission model design
- [Source: _bmad-output/planning-artifacts/architecture.md#Permission Enforcement Pattern] — Code pattern
- [Source: _bmad-output/planning-artifacts/architecture.md#Format Patterns] — RFC 7807 error format
- [Source: _bmad-output/planning-artifacts/architecture.md#Process Patterns] — Structured logging format
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision Impact Analysis] — Implementation sequence (permissions first)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.1] — Acceptance criteria and user story
- [Source: _bmad-output/planning-artifacts/prd.md#FR58] — FR58: 2-tier permissions across all APIs and UI routes

### Git Intelligence

- Recent commits: `8f9dd61` fixed pre-existing lint/type issues, `a73bffc` committed v0.2.0 planning artifacts
- Code patterns: pytest with respx for HTTP mocking, class-based test organization, HTMX partial response pattern
- No existing auth code in codebase — fully greenfield implementation
- 626 existing UI tests, 406 investigator tests — all passing as of latest commit

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
