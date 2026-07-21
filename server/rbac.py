"""Role-based access control — the permission matrix and its checks.

Access in this product is **per-organization**: a user holds one :class:`Role`
in each organization they belong to (via a ``Membership`` row), and that role
decides what they may do to that org's projects, tasks, and annotations. This
mirrors Label Studio's org/role model, retuned for a segmentation workflow
where *reviewer* (approves annotations) and *annotator* (produces them) are
distinct jobs.

The design keeps authorization data-driven and pure:

* :data:`ROLE_PERMISSIONS` maps each role to the exact set of permissions it
  grants — the single source of truth. There is **no** implicit inheritance in
  the data; each role lists everything it can do (built by composing the tier
  below it, so the table stays readable but the runtime lookup is a flat set
  membership test, O(1) and impossible to get subtly wrong via a broken
  hierarchy walk).
* :func:`can` answers "may this role do this?" and :func:`require` raises
  :class:`server.errors.PermissionDenied` when the answer is no — services call
  ``require`` at the top of every mutating method.
* :data:`ROLE_RANK` orders the roles so :func:`assignable_roles` can stop a
  manager from granting someone *owner* (privilege escalation): you may only
  assign a role strictly below your own.

Nothing here reads the database — a caller resolves a user's role for an org
(one indexed lookup) and passes it in. That keeps the whole module pure and
exhaustively unit-testable.
"""
from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """A member's role within one organization (subclasses ``str`` so it
    serialises to its value directly in JSON and stores as plain text)."""

    OWNER = "owner"          # the org creator; full control incl. deletion
    ADMIN = "admin"          # manage members and every project
    MANAGER = "manager"      # create/run projects, assign & review tasks
    REVIEWER = "reviewer"    # review/approve annotations, can't manage members
    ANNOTATOR = "annotator"  # produce annotations on assigned tasks
    VIEWER = "viewer"        # read-only

    @classmethod
    def from_str(cls, value: str) -> "Role":
        """Parse a stored/API role string, raising ValueError if unknown."""
        return cls(value)


# ── Permissions (stable string constants, usable in an API/audit log) ────────
# Grouped by the entity they act on. Kept as plain strings (not an enum) so
# they read well in an audit event's ``action`` field and in tests.
class Perm:
    # Organization
    ORG_VIEW = "org.view"
    ORG_EDIT = "org.edit"
    ORG_DELETE = "org.delete"
    ORG_MANAGE_MEMBERS = "org.manage_members"   # invite / change role / remove
    # Projects
    PROJECT_VIEW = "project.view"
    PROJECT_CREATE = "project.create"
    PROJECT_EDIT = "project.edit"
    PROJECT_DELETE = "project.delete"
    # Tasks
    TASK_VIEW = "task.view"
    TASK_CREATE = "task.create"
    TASK_ASSIGN = "task.assign"
    TASK_DELETE = "task.delete"
    # Annotations
    ANNOTATION_VIEW = "annotation.view"
    ANNOTATION_CREATE = "annotation.create"     # produce/submit an annotation
    ANNOTATION_REVIEW = "annotation.review"     # approve / reject someone's
    # API keys (a user manages their own; org-scoped keys need this)
    APIKEY_MANAGE = "apikey.manage"
    # Audit log
    AUDIT_VIEW = "audit.view"


# Build each role's permission set by composing the tier below it, so the table
# is easy to read and reason about, then freeze it into a flat set for O(1)
# runtime checks. This is intentionally *materialised* inheritance: the runtime
# never walks a hierarchy, it just tests membership.
_VIEWER = frozenset({
    Perm.ORG_VIEW, Perm.PROJECT_VIEW, Perm.TASK_VIEW, Perm.ANNOTATION_VIEW,
})
_ANNOTATOR = _VIEWER | {Perm.ANNOTATION_CREATE}
_REVIEWER = _ANNOTATOR | {Perm.ANNOTATION_REVIEW}
_MANAGER = _REVIEWER | {
    Perm.PROJECT_CREATE, Perm.PROJECT_EDIT,
    Perm.TASK_CREATE, Perm.TASK_ASSIGN, Perm.TASK_DELETE,
    Perm.AUDIT_VIEW,
}
_ADMIN = _MANAGER | {
    Perm.ORG_EDIT, Perm.ORG_MANAGE_MEMBERS,
    Perm.PROJECT_DELETE, Perm.APIKEY_MANAGE,
}
_OWNER = _ADMIN | {Perm.ORG_DELETE}

ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.OWNER: frozenset(_OWNER),
    Role.ADMIN: frozenset(_ADMIN),
    Role.MANAGER: frozenset(_MANAGER),
    Role.REVIEWER: frozenset(_REVIEWER),
    Role.ANNOTATOR: frozenset(_ANNOTATOR),
    Role.VIEWER: frozenset(_VIEWER),
}

# Seniority order (higher = more privileged). Drives assignable_roles(): you may
# only grant a role strictly below your own, which blocks privilege escalation
# (a manager can't mint an admin) and lateral self-preserving grants.
ROLE_RANK: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.ANNOTATOR: 1,
    Role.REVIEWER: 2,
    Role.MANAGER: 3,
    Role.ADMIN: 4,
    Role.OWNER: 5,
}


def _as_role(role: "Role | str") -> Role:
    return role if isinstance(role, Role) else Role.from_str(role)


def permissions_for(role: "Role | str") -> frozenset[str]:
    """Every permission a role grants (empty for an unknown role string)."""
    try:
        return ROLE_PERMISSIONS[_as_role(role)]
    except (ValueError, KeyError):
        return frozenset()


def can(role: "Role | str", permission: str) -> bool:
    """Whether ``role`` grants ``permission``. Never raises."""
    return permission in permissions_for(role)


def require(role: "Role | str", permission: str, *, message: str | None = None) -> None:
    """Raise :class:`PermissionDenied` unless ``role`` grants ``permission``.

    Services call this at the top of each mutating operation, having resolved
    the caller's role for the relevant org.
    """
    from .errors import PermissionDenied

    if not can(role, permission):
        raise PermissionDenied(
            message or f"Your role ({_role_name(role)}) can't perform this action."
        )


def assignable_roles(actor_role: "Role | str") -> list[Role]:
    """Roles ``actor_role`` is allowed to grant to others.

    Rule: strictly below your own rank — this stops a manager from minting an
    admin/owner, or an admin from minting another admin/owner (a lateral grant
    that could then remove the grantor is a real risk we forbid). The **owner**
    tier is the one exception: an owner may also grant *owner*, because that is
    co-ownership / ownership transfer, not escalation (the grantee never exceeds
    the grantor, who is already at the top). Ordered most-senior first; an actor
    without member-management permission gets an empty list.
    """
    actor = _as_role(actor_role)
    if not can(actor, Perm.ORG_MANAGE_MEMBERS):
        return []
    ceiling = ROLE_RANK[actor]
    grantable = [r for r in Role if ROLE_RANK[r] < ceiling]
    if actor is Role.OWNER:
        grantable.append(Role.OWNER)  # owners may share ownership / hand it over
    grantable.sort(key=lambda r: ROLE_RANK[r], reverse=True)
    return grantable


def can_assign_role(actor_role: "Role | str", target_role: "Role | str") -> bool:
    """Whether ``actor_role`` may grant ``target_role`` to someone."""
    return _as_role(target_role) in assignable_roles(actor_role)


def _role_name(role: "Role | str") -> str:
    try:
        return _as_role(role).value
    except ValueError:
        return str(role)
