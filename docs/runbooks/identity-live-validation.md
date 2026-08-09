# Identity Live-Validation Runbook (Task 8.9, ADR 0002 — `[H]`)

**What this proves:** the deploy/config layer Task 8.9 built (the `ui.auth`
Helm tree, `existingSecret` pattern, and the docs) actually produces a
working system end-to-end on a real cluster — not just a chart that renders
correctly. Three scenarios, each independently runnable against the kind
demo cluster. **This document is prepared by Task 8.9; the runs themselves
are a separate `[H]` session the orchestrator executes with the user** (see
`docs/plans/react-ui.md` Task 8.9's acceptance criteria).

Style follows [`docs/design/triage-glance-test.md`](../design/triage-glance-test.md):
setup → protocol → expected observations → a results table to fill in
during the actual run → a verdict line.

---

## Shared prerequisites (all three scenarios)

- A running kind demo cluster: `make demo-up` (or, if it's already up,
  `make demo-status` to confirm). Release `beeper`, namespace `beeper`,
  cluster name `beeper-demo` — these are the Makefile's fixed names; the
  commands below assume them.
- `kubectl`, `helm` (3.x+) on PATH.
- `helm/beeper/examples/identity-secret.yaml` as a starting template for
  the one `beeper-identity` Secret every scenario below populates
  differently — **create it with `kubectl create secret generic`
  directly (never apply a file containing a real secret value)**.
- Nothing here touches the default `mode: none` demo path — every command
  below is an explicit `-f`/`--set` opt-in on top of `values-dev.yaml`,
  and `make demo-up`/`make demo-deploy` are unaffected (see Task 8.9's
  NFR26 static-test suite, `demo/tests/test_ui_auth_helm.py`).
- **Cleanup between scenarios:** each scenario's own "Rollback / cleanup"
  step returns the release to `mode: none` (`helm upgrade beeper
  ./helm/beeper --namespace beeper -f ./helm/beeper/values-dev.yaml`, no
  identity overlay) before starting the next one, so scenarios don't leak
  state into each other via the shared `beeper_users`/`beeper_groups`
  Qdrant collections. Deleting the `beeper-identity` Secret is not
  required between scenarios (harmless if left with stale keys — the app
  only reads the keys the active mode needs), but is included below for
  hygiene.

---

## Scenario 1 — `local` mode: bootstrap → login → manage users

**Proves:** FR59–FR61, the directive's SSO-off fallback, end-to-end on a
real pod (not just Flask-test-client, which Task 8.6's automated suite
already covers).

### Setup

```bash
kubectl create secret generic beeper-identity \
  --namespace beeper \
  --from-literal=secretKey="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  --from-literal=bootstrapUsername=admin \
  --from-literal=bootstrapPassword='ChangeMe123!' \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install beeper ./helm/beeper \
  --namespace beeper \
  --values ./helm/beeper/values-dev.yaml \
  --values ./helm/beeper/examples/values-identity-local.yaml \
  --set operator.image.tag=dev \
  --set ui.image.tag=dev \
  --set investigator.image.tag=dev \
  --timeout 5m --wait

kubectl -n beeper rollout status deployment/beeper-ui
```

`values-identity-local.yaml` already sets `externalScheme: http` (the kind
demo has no TLS) — see [`helm/beeper/examples/values-identity-local.yaml`](../../helm/beeper/examples/values-identity-local.yaml).

`make demo-ui` port-forwards the UI to `http://localhost:5050` as usual —
run it now if it isn't already forwarding.

### Protocol

1. **Bootstrap took effect:** `curl -s http://localhost:5050/health/api | python3 -m json.tool` — confirm `zero_active_admins: false` (the bootstrap admin exists and is active).
2. **Login:** open `http://localhost:5050/app/login`, sign in as `admin` / `ChangeMe123!`. Expect: redirected into the shell, `Manage → Users` visible in the sidebar.
3. **Create a user:** `/app/admin/users` → create dialog → username `bob`, role `user`, a password. Expect: appears in the table with origin "local", role "user", active.
4. **Assign role:** promote `bob` to `admin` via the role selector. Expect: table updates in place, no page reload needed.
5. **Last-admin refusal:** with only `admin` and `bob` both admins, demote **either one** — should succeed (two active admins). Now demote the other back to `user` — **the second demotion must be refused** (`409 last-admin`, rendered inline, not a generic error). Restore both to admin, or leave one as the sole admin.
6. **Demote/deactivate `bob`:** set `bob` back to role `user`, then deactivate `bob`. Expect: deactivated users show inactive styling; no last-admin block fires here since `bob` isn't currently the last active admin.
7. **Login-fails:** open a new private/incognito tab, attempt to log in as `bob` with the correct password. Expect: `401`, generic "invalid username or password" — no distinction from a wrong-password or unknown-user attempt (same body for all three per ADR §6).
8. **CLI recovery path (optional but recommended to actually exercise once):** `echo 'Sup3rSecret!!' | kubectl exec -i -n beeper deploy/beeper-ui -- flask --app beeper_ui create-admin carol --password-stdin`. Expect: `Admin user 'carol' created.`, and `carol` now appears in `/app/admin/users` as an active admin without ever using the web UI create-dialog.

### Rollback / cleanup

```bash
helm upgrade beeper ./helm/beeper --namespace beeper --values ./helm/beeper/values-dev.yaml \
  --set operator.image.tag=dev --set ui.image.tag=dev --set investigator.image.tag=dev --wait
kubectl delete secret beeper-identity --namespace beeper --ignore-not-found
```

### Results

| Step | Expected | Observed | Pass/Fail |
|---|---|---|---|
| 1. Bootstrap admin active | `zero_active_admins: false` | | |
| 2. Login as bootstrap admin | Redirect into shell, Manage→Users visible | | |
| 3. Create local user `bob` | Appears, origin=local, role=user | | |
| 4. Promote `bob` to admin | Live update, no reload | | |
| 5. Last-admin refusal | Second demotion → `409 last-admin` inline | | |
| 6. Deactivate `bob` | Inactive styling | | |
| 7. Login as deactivated `bob` | `401`, generic body | | |
| 8. CLI `create-admin carol` | Created, visible in table | | |

**Witnessed by:** \_\_\_\_\_\_\_\_\_\_\_ **Date:** \_\_\_\_\_\_\_\_\_\_\_
**Verdict:** ☐ PASS ☐ FAIL (notes: \_\_\_\_\_\_\_\_\_\_\_)

---

## Scenario 2 — `oidc` mode against a disposable Keycloak

**Proves:** FR55–FR56 end-to-end against a real IdP (not the `responses`-stubbed
IdP Task 8.5's automated suite uses) — real discovery document, real JWKS,
real authorization-code redirect round-trip, real groups claim.

### Setup — disposable dev Keycloak

Current coordinates (verified 2026-08-09): Keycloak **26.7.0**, image
`quay.io/keycloak/keycloak:26.7.0`, bootstrap admin via
`KC_BOOTSTRAP_ADMIN_USERNAME`/`KC_BOOTSTRAP_ADMIN_PASSWORD` (the current
env var names — older Keycloak releases used `KEYCLOAK_ADMIN`/
`KEYCLOAK_ADMIN_PASSWORD`; if you pin an older image, use those instead).
Deployed as a **plain Deployment+Service**, not the Bitnami Helm chart —
fewer values to get right for a fixture that gets deleted at the end of the
session.

```bash
kubectl create namespace beeper-idp-dev --dry-run=client -o yaml | kubectl apply -f -

cat <<'EOF' | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dev-keycloak
  namespace: beeper-idp-dev
spec:
  replicas: 1
  selector:
    matchLabels: {app: dev-keycloak}
  template:
    metadata:
      labels: {app: dev-keycloak}
    spec:
      containers:
        - name: keycloak
          image: quay.io/keycloak/keycloak:26.7.0
          args: ["start-dev"]
          env:
            - {name: KC_BOOTSTRAP_ADMIN_USERNAME, value: admin}
            - {name: KC_BOOTSTRAP_ADMIN_PASSWORD, value: admin}
            - {name: KC_HOSTNAME_STRICT, value: "false"}
          ports:
            - {containerPort: 8080, name: http}
---
apiVersion: v1
kind: Service
metadata:
  name: dev-keycloak
  namespace: beeper-idp-dev
spec:
  selector: {app: dev-keycloak}
  ports:
    - {port: 8080, targetPort: 8080}
EOF

kubectl -n beeper-idp-dev rollout status deployment/dev-keycloak --timeout=180s
kubectl -n beeper-idp-dev port-forward svc/dev-keycloak 8090:8080 &
# Admin console now at http://localhost:8090 (admin/admin)
```

**Realm/client/group/user fixture** — via `kcadm.sh` (ships in the image;
run through `kubectl exec`, no port-forward needed for this part). If any
flag below doesn't match your pulled image's `kcadm.sh --help` output, the
Admin Console at `http://localhost:8090` (port-forwarded above) is an
equally valid fallback for these few clicks.

```bash
KC_POD=$(kubectl -n beeper-idp-dev get pod -l app=dev-keycloak -o jsonpath='{.items[0].metadata.name}')
KC="kubectl -n beeper-idp-dev exec -i $KC_POD -- /opt/keycloak/bin/kcadm.sh"

$KC config credentials --server http://localhost:8080 --realm master --user admin --password admin

$KC create realms -s realm=beeper -s enabled=true

# Client: confidential, standard (authorization-code) flow, redirect back to
# the port-forwarded Beeper UI.
$KC create clients -r beeper \
  -s clientId=beeper-ui -s enabled=true -s publicClient=false -s standardFlowEnabled=true \
  -s 'redirectUris=["http://localhost:5050/auth/callback"]' \
  -s 'webOrigins=["http://localhost:5050"]'

# Capture the client's internal id, then its generated secret.
CLIENT_ID=$($KC get clients -r beeper -q clientId=beeper-ui --fields id --format csv --noquotes)
$KC get clients/$CLIENT_ID/client-secret -r beeper   # note the "value" field — this is BEEPER_OIDC_CLIENT_SECRET

# Groups claim mapper so `groups` lands in the ID token (BEEPER_OIDC_GROUPS_CLAIM default).
$KC create clients/$CLIENT_ID/protocol-mappers/models -r beeper \
  -s name=groups -s protocol=openid-connect -s protocolMapper=oidc-group-membership-mapper \
  -s 'config."full.path"=false' -s 'config."id.token.claim"=true' \
  -s 'config."access.token.claim"=true' -s 'config."userinfo.token.claim"=true' \
  -s 'config."claim.name"=groups'

# Groups + a test user in the Admins group (BEEPER_ADMIN_GROUPS default incl. "Admins").
$KC create groups -r beeper -s name=Admins
ADMINS_GROUP_ID=$($KC get groups -r beeper -q search=Admins --fields id --format csv --noquotes)
$KC create users -r beeper -s username=alice -s enabled=true -s email=alice@example.com -s emailVerified=true
ALICE_ID=$($KC get users -r beeper -q username=alice --fields id --format csv --noquotes)
$KC set-password -r beeper --username alice --new-password 'Passw0rd!123' --temporary=false
$KC update users/$ALICE_ID/groups/$ADMINS_GROUP_ID -r beeper -s realm=beeper -s userId=$ALICE_ID -s groupId=$ADMINS_GROUP_ID -n
```

**Deploy Beeper in `oidc` mode** (SCIM still **disabled** for this
scenario — pure login+claims-snapshot path; Scenario 3 turns SCIM on):

```bash
kubectl create secret generic beeper-identity \
  --namespace beeper \
  --from-literal=secretKey="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  --from-literal=clientSecret='<the client-secret value from above>' \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install beeper ./helm/beeper \
  --namespace beeper \
  --values ./helm/beeper/values-dev.yaml \
  --values ./helm/beeper/examples/values-identity-oidc.yaml \
  --set ui.auth.externalScheme=http \
  --set ui.auth.oidc.issuer=http://dev-keycloak.beeper-idp-dev.svc.cluster.local:8080/realms/beeper \
  --set operator.image.tag=dev --set ui.image.tag=dev --set investigator.image.tag=dev \
  --timeout 5m --wait

kubectl -n beeper rollout status deployment/beeper-ui
```

The issuer above is the **in-cluster** DNS name (Beeper's pod resolves it
server-side for discovery/JWKS/token exchange); your **browser** reaches
Keycloak through the `8090` port-forward instead. This asymmetry is fine —
OIDC discovery/JWKS/token calls are server-to-server, only the initial
redirect and the login form need to be browser-reachable.

### Protocol

1. **Cold login:** open `http://localhost:5050/app/investigations` while logged out. Expect: `302` to `/auth/login?next=...`, which itself redirects to Keycloak's login form (served from the `8090` port-forward — if Keycloak issues a redirect back to the in-cluster hostname instead of `localhost:8090`, that's `KC_HOSTNAME_STRICT`/hostname config to fix, not a Beeper bug).
2. **Authenticate as `alice`** (in the `Admins` group). Expect: redirected back through `/auth/callback` and landing on the *original* `/app/investigations` permalink (FR53 access-consistency through the login round-trip) — not a generic post-login landing page.
3. **Role check:** `Manage → Users` should be visible (alice resolved to `admin` from the `groups` claim). `GET /api/v1/auth/me` should show `auth_mode: "oidc"`, `authenticated: true`, `role: "admin"`.
4. **Logout:** trigger logout from the UI. Expect: session cleared, subsequent `/api/v1/auth/me` shows `authenticated: false`; a re-visit to `/app/investigations` round-trips through login again.
5. **Non-admin group mapping:** create a second Keycloak user with no group membership (or in a group not in `BEEPER_ADMIN_GROUPS`), log in as them. Expect: `role: "user"`, `Manage → Users` not shown, `/app/admin/users` direct nav shows an in-shell `403`.

### Rollback / cleanup

```bash
helm upgrade beeper ./helm/beeper --namespace beeper --values ./helm/beeper/values-dev.yaml \
  --set operator.image.tag=dev --set ui.image.tag=dev --set investigator.image.tag=dev --wait
kubectl delete secret beeper-identity --namespace beeper --ignore-not-found
kubectl delete namespace beeper-idp-dev   # deletes the disposable Keycloak entirely
# also stop the `kubectl port-forward svc/dev-keycloak 8090:8080` background job
```

### Results

| Step | Expected | Observed | Pass/Fail |
|---|---|---|---|
| 1. Cold permalink → login redirect | `302` → Keycloak login | | |
| 2. Login as `alice` | Returns to original permalink | | |
| 3. Role resolves from groups claim | `role: admin`, Manage→Users visible | | |
| 4. Logout | Session cleared, `/me` shows logged out | | |
| 5. Non-admin group mapping | `role: user`, in-shell 403 on `/app/admin/users` | | |

**Witnessed by:** \_\_\_\_\_\_\_\_\_\_\_ **Date:** \_\_\_\_\_\_\_\_\_\_\_
**Verdict:** ☐ PASS ☐ FAIL (notes: \_\_\_\_\_\_\_\_\_\_\_)

---

## Scenario 3 — SCIM push simulation (curl, against the live `/scim/v2` surface)

**Proves:** FR57–FR58, NFR25 (≤60 s propagation) against the real running
pod — store writes, TTL cache expiry, session termination. Keycloak has no
native SCIM 2.0 provisioning connector (as of Keycloak 26.x), so this
scenario simulates an IdP's SCIM pushes directly with `curl` and a bearer
token, exactly as a real SCIM connector (Okta/Entra) would call Beeper —
the OIDC login half from Scenario 2 stays in place and is reused here to
observe the *effect* of these pushes on a live browser session.

### Setup — turn SCIM on for the Scenario-2 deployment

```bash
SCIM_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
kubectl patch secret beeper-identity --namespace beeper --type=merge \
  -p "{\"stringData\":{\"scimToken\":\"$SCIM_TOKEN\"}}"

helm upgrade beeper ./helm/beeper \
  --namespace beeper \
  --values ./helm/beeper/values-dev.yaml \
  --values ./helm/beeper/examples/values-identity-oidc-scim.yaml \
  --set ui.auth.externalScheme=http \
  --set ui.auth.oidc.issuer=http://dev-keycloak.beeper-idp-dev.svc.cluster.local:8080/realms/beeper \
  --set operator.image.tag=dev --set ui.image.tag=dev --set investigator.image.tag=dev \
  --timeout 5m --wait

BASE=http://localhost:5050/scim/v2
AUTH="Authorization: Bearer $SCIM_TOKEN"
```

(If Scenario 2 wasn't run first, first repeat its Keycloak setup and its
`clientSecret`-only deploy — Scenario 3 assumes `alice` already exists and
can log in via Keycloak so you have a live browser session to observe.)

### Protocol

1. **Create via SCIM** — push a record for a *new* user, `bob2`, initially in no admin group:
   ```bash
   curl -s -X POST "$BASE/Users" -H "$AUTH" -H 'Content-Type: application/scim+json' -d '{
     "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
     "userName": "bob2@example.com",
     "externalId": "scim-bob2",
     "active": true
   }' | python3 -m json.tool
   ```
   Expect `201`, a generated `id` in the response. **Capture it** as `BOB2_ID`.
2. **Appears:** `curl -s "$BASE/Users?filter=userName%20eq%20%22bob2@example.com%22" -H "$AUTH"` → `200`, one result matching. (`bob2` isn't provisioned in Keycloak so can't actually log in for this step — that's fine, this step only proves the store write, not a live session.)
3. **Group-push admin (the alice case — live session effect):** patch/create a group containing `alice`'s SCIM `externalId`/`userName` so her *store* role becomes `admin` via SCIM rather than the login snapshot:
   ```bash
   curl -s -X POST "$BASE/Groups" -H "$AUTH" -H 'Content-Type: application/scim+json' -d '{
     "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
     "displayName": "Admins",
     "members": [{"value": "<alice-store-id-or-userName>"}]
   }' | python3 -m json.tool
   ```
   With `alice` already logged in (from Scenario 2) and SCIM now enabled, the *next* request her session makes re-resolves her role from the store (60 s TTL cache) rather than her login-time claims snapshot — reload any page in her browser tab within ~60 s. Expect: no change in this direction if she was already `admin` via the groups claim; the meaningful proof is step 4 below (demotion), where store-primacy actually diverges from what a claims-snapshot approach would show.
4. **Unassign (demote) — role drops within 60 s, no re-login:** `PATCH` the group to remove `alice`, Okta-dialect:
   ```bash
   curl -s -X PATCH "$BASE/Groups/<admins-group-scim-id>" -H "$AUTH" -H 'Content-Type: application/scim+json' -d '{
     "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
     "Operations": [{"op": "remove", "path": "members", "value": [{"value": "<alice-store-id>"}]}]
   }'
   ```
   In the browser (still logged in as `alice`, no logout/re-login): wait up to 60 s, reload `/app/admin/users`. Expect: `role` now `user` — `403` on admin routes, session **not** cleared (she's still authenticated, just no longer privileged — this is the `store role="user"` path, not a session-clear).
5. **Deactivate — session terminates, `401` within 60 s:**
   ```bash
   curl -s -X PATCH "$BASE/Users/<alice-scim-id>" -H "$AUTH" -H 'Content-Type: application/scim+json' -d '{
     "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
     "Operations": [{"op": "replace", "path": "active", "value": false}]
   }'
   ```
   In the browser: within 60 s, any request (including an open SSE stream, if one is active) returns `401 authentication-required` and the UI redirects to `/auth/login`. This is the session-clear path (ADR §5.3) — distinct from step 4's role-only demotion.
6. **Audit log check:** `kubectl -n beeper logs deploy/beeper-ui | grep beeper_ui.scim.audit` — every mutation above should have an audit line with an actor token fingerprint (`sha256[:8]`), never the raw `$SCIM_TOKEN` value, and the group-membership changes affecting `Admins` should be flagged distinctly from ordinary user field changes.

### Rollback / cleanup

```bash
helm upgrade beeper ./helm/beeper --namespace beeper --values ./helm/beeper/values-dev.yaml \
  --set operator.image.tag=dev --set ui.image.tag=dev --set investigator.image.tag=dev --wait
kubectl delete secret beeper-identity --namespace beeper --ignore-not-found
kubectl delete namespace beeper-idp-dev --ignore-not-found
```

### Results

| Step | Expected | Observed | Pass/Fail |
|---|---|---|---|
| 1. SCIM create `bob2` | `201`, id returned | | |
| 2. `bob2` appears via filter | `200`, one match | | |
| 3. Group push (Admins) | Store write succeeds | | |
| 4. Unassign `alice` from Admins | `role: user` within 60 s, `403` not `401`, no session clear | | |
| 5. Deactivate `alice` | Session cleared, `401` within 60 s, redirect to login | | |
| 6. Audit log | Fingerprints only, admin-group changes flagged | | |

**Witnessed by:** \_\_\_\_\_\_\_\_\_\_\_ **Date:** \_\_\_\_\_\_\_\_\_\_\_
**Verdict:** ☐ PASS ☐ FAIL (notes: \_\_\_\_\_\_\_\_\_\_\_)

---

## After all three scenarios

Confirm the demo is unaffected: `helm upgrade beeper ./helm/beeper --namespace beeper --values ./helm/beeper/values-dev.yaml --set operator.image.tag=dev --set ui.image.tag=dev --set investigator.image.tag=dev --wait`, then re-run `make demo-fault FAULT=payment-failure` (or any existing demo validation you use) to confirm the identity work left the core demo path untouched — this is the final leg of Task 8.9's program gate.
