# CellSeg1 Server — the multi-user backend

The accounts + shared-database contour the desktop apps (`napari_app/`,
`studio/`) never had. This is what turns CellSeg1 from a single-machine tool
into something a **team** can use, and it is the substrate a future web
deployment (Label-Studio-style) is built on.

> **Status: tested foundation, no web tier yet.** Everything below the HTTP
> layer is built and unit-tested: accounts, sessions, API keys, the
> organization/project/task/annotation/review model, role-based access control,
> and an immutable audit log — all on a database designed to scale. The REST API
> that exposes it over the network is the next slice (see *Roadmap*). You can
> use the whole thing today from Python.

## Why a server at all

The request that started this was *"accounts + a database for 10 000+ users a
day, so nothing hangs."* That requirement only has meaning for a **service** —
a desktop app doesn't serve users per day. So this is a new, **additive**
top-level package: the classic napari app and Studio are untouched and keep
working exactly as before; `server/` is the piece they (or a browser) will talk
to when a team needs shared accounts and data.

The shape follows **Label Studio**'s proven model, retuned for microscopy:

```
Organization ──< Membership >── User          (a lab / team and its people)
     │              (role)
     └──< Project ──< Task ──< Annotation      (a cohort · an image · a mask)
                                  └─ reviewed_by → User   (annotator ≠ reviewer)
```

## Design principles

1. **Runs with zero infrastructure.** The default store is stdlib `sqlite3` in
   WAL mode — one file, no server, no container, nothing to configure. A lab
   gets a working multi-user backend immediately. This is the whole reason the
   foundation is usable *before* any web tier exists.
2. **Scales to a real deployment without a rewrite.** Auth is stateless-token
   based and every storage access goes through a thin repository layer with
   portable SQL, so the path to 10k+ users/day (below) is configuration and a
   driver swap, not a redesign.
3. **Pure standard library.** No torch, napari, Qt, or third-party package — so
   its test suite runs in CI's light `test` dependency-group like the rest of
   this repo's pure-logic core, and there is nothing to `pip install` to use it.

## Quick start (from Python)

```python
from server.service import ServerApp

app = ServerApp.create("cellseg1.db")     # or ServerApp.create() for in-memory

# accounts
alice = app.auth.register("alice@lab.org", "alice", "a-strong-password")
user, token = app.auth.login("alice", "a-strong-password")   # token = bearer
assert app.auth.resolve_session(token).id == alice.id        # one lookup/request

# a team, with roles
org = app.orgs.create(alice.id, "Imaging Lab")               # alice is OWNER
bob = app.auth.register("bob@lab.org", "bob", "another-password")
app.orgs.add_member(alice.id, org.id, bob.id, "annotator")

# a project → task → annotation → review
proj = app.projects.create(alice.id, org.id, "DAPI nuclei",
                           settings={"engine": "cellseg1", "resize_size": 512})
task = app.tasks.create(alice.id, proj.id, "well_A1.tif", source="/data/A1.tif")
app.tasks.assign(alice.id, task.id, bob.id)
ann  = app.annotations.submit(bob.id, task.id, {"n_cells": 128})   # → COMPLETED
app.annotations.review(alice.id, ann.id, approve=True)             # → REVIEWED

# everything above is in the immutable audit log
for e in app.audit.list_for_org(alice.id, org.id):
    print(e.created_at, e.action)
```

## Roles & permissions (RBAC)

Access is **per-organization**: a user holds one role in each org they belong
to. Higher roles include everything below them.

| Role | Can… |
|------|------|
| **owner** | everything, incl. delete the org and transfer/share ownership |
| **admin** | manage members, delete projects, manage API keys |
| **manager** | create/edit projects, create & assign tasks, view the audit log |
| **reviewer** | approve/reject annotations (a distinct job from producing them) |
| **annotator** | produce/submit annotations on assigned tasks |
| **viewer** | read-only |

Guardrails enforced in `rbac.py` + `service.py`: you can only grant a role
**strictly below your own** (an owner may additionally grant *owner*, for
co-ownership/transfer) — so no privilege escalation; and an org **always keeps
at least one owner** (the last owner can't be demoted or removed).

## How it stays fast under load ("nothing hangs")

- **SQLite in WAL mode** gives concurrent readers alongside one writer instead
  of a single global lock, and **`busy_timeout`** makes a write burst *queue
  briefly* rather than error out — the "doesn't fall over" behaviour, on a
  single file, with no tuning.
- **Stateless token auth**: validating a request is one indexed lookup of a
  token *hash* (we never store raw tokens) — there is no server-side session
  memory to become a bottleneck or force sticky sessions, so the future web
  tier scales **horizontally** (N identical workers behind a load balancer).
- **Indexed on every hot column** (foreign keys, `token_hash`, `prefix`,
  `(project_id, status)`, audit `created_at`, …) so lookups stay O(log n) as
  tables grow.

### The path to 10 000+ users/day

The storage layer is deliberately thin so this is a swap, not a rewrite:

1. **Postgres** for the write concurrency a busy multi-tenant deployment needs
   (many simultaneous writers, which is where a single SQLite writer becomes the
   ceiling). The schema uses only portable types; the repositories issue plain
   parameterised SQL — the port is a pooled `psycopg` connection factory in
   `db.py` and translating the `?` placeholders to `%s`.
2. **A connection pool** (pgbouncer / SQLAlchemy pool) in front of Postgres.
3. **A task queue** (Celery/RQ/Ray) for the heavy ML work — segmentation must
   never run inside a request. The `Task`/`Annotation` model already anticipates
   this: a task is a unit of work whose result (an annotation) arrives
   asynchronously.
4. **Object storage** (S3/MinIO) for images and masks; the DB stores references
   (`Task.source`, `Annotation.data`), not pixels.

None of steps 1–4 change the service or API code — that is the point of the
repository boundary.

## Layout

```
errors.py       domain exceptions (each carries an API code + HTTP status)
security.py     scrypt password hashing + opaque session/API-key tokens
validation.py   email/username/password/name/slug validation + normalisation
rbac.py         Role, the permission matrix, can()/require(), escalation guard
models.py       the entity dataclasses (from_row / secret-omitting to_dict)
db.py           sqlite3 connection factory (WAL) + schema DDL + migrations
repository.py   data access — one repo per entity, plain parameterised SQL
service.py      the business API + ServerApp front door
tests/          the pure-stdlib test suite (runs in CI's light `test` group)
```

## Roadmap (next slices)

Built here is the tested foundation. On top of it, in rough order:

- **HTTP API tier** — FastAPI over these services (a new `server` extra:
  `fastapi`/`uvicorn`), bearer-token + API-key auth dependencies, request
  validation, and the error→status mapping the exceptions already carry.
- **Studio as a client** — an optional "sign in / sync to a server" path so the
  desktop app can push/pull projects to a shared backend.
- **SSO (OIDC/SAML) + API-key scopes + rate limits + webhooks** — the identity
  and integration surface from `docs/AUDIT_2026.md` §8.
- **Postgres driver + object storage + task queue** — the production scale-out
  above.
- **Reviewer analytics / inter-annotator agreement** — the collaboration
  features that make the review workflow worth having.

## Testing

```
.venv/bin/python -m pytest server/tests -q
```

Pure stdlib, no GPU/GUI/heavy deps — so it also runs under the repo's
throwaway light-group check (`pip install --group test`) exactly like CI.
