"""The entity dataclasses — the domain model, mirroring the database rows.

These are plain dataclasses with two conveniences each: ``from_row`` (build the
object from a ``sqlite3.Row`` / mapping, decoding the JSON and boolean columns
the database stores as text/int) and ``to_dict`` (a JSON-ready projection, with
secret columns like ``password_hash`` / ``token_hash`` **omitted** so a model
can be handed to the future API layer without leaking credentials).

The shape follows Label Studio's proven hierarchy, retuned for microscopy::

    Organization ──< Membership >── User
         │
         └──< Project ──< Task ──< Annotation
                                      └─ reviewed_by → User

Ids are UUID4 hex strings: globally unique with no coordination, so rows can be
created on any node (or merged from an offline desktop) without collision — a
property that matters the day this moves off one SQLite file. Timestamps are
ISO-8601 UTC strings, which sort correctly lexicographically (so "newest first"
is a plain ``ORDER BY``) and are unambiguous across timezones.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .rbac import Role


def new_id() -> str:
    """A fresh globally-unique id (UUID4 hex, 32 chars, no coordination)."""
    return uuid.uuid4().hex


def now_iso() -> str:
    """Current UTC time as a stable, sortable, timezone-aware ISO-8601 string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_load(value: Any) -> dict:
    """Decode a JSON text column to a dict, tolerating None / already-a-dict."""
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    try:
        out = json.loads(value)
        return out if isinstance(out, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


# ── Status vocabularies (stored as plain text; validated at the service) ─────
class TaskStatus:
    PENDING = "pending"          # created, not started
    IN_PROGRESS = "in_progress"  # an annotator is working on it
    COMPLETED = "completed"      # annotation submitted, awaiting review
    REVIEWED = "reviewed"        # a reviewer has signed off
    SKIPPED = "skipped"          # explicitly set aside
    ALL = (PENDING, IN_PROGRESS, COMPLETED, REVIEWED, SKIPPED)


class AnnotationStatus:
    DRAFT = "draft"          # being worked on
    SUBMITTED = "submitted"  # handed off for review
    APPROVED = "approved"    # reviewer accepted
    REJECTED = "rejected"    # reviewer sent back
    ALL = (DRAFT, SUBMITTED, APPROVED, REJECTED)


# ── Entities ────────────────────────────────────────────────────────────────
@dataclass
class User:
    id: str
    email: str
    username: str
    password_hash: str
    full_name: str = ""
    is_active: bool = True
    is_superuser: bool = False      # platform-wide staff, distinct from org role
    created_at: str = field(default_factory=now_iso)
    last_login_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "User":
        return cls(
            id=row["id"], email=row["email"], username=row["username"],
            password_hash=row["password_hash"], full_name=row["full_name"] or "",
            is_active=bool(row["is_active"]), is_superuser=bool(row["is_superuser"]),
            created_at=row["created_at"], last_login_at=row["last_login_at"],
        )

    def to_dict(self) -> dict:
        """Public projection — never includes ``password_hash``."""
        return {
            "id": self.id, "email": self.email, "username": self.username,
            "full_name": self.full_name, "is_active": self.is_active,
            "is_superuser": self.is_superuser, "created_at": self.created_at,
            "last_login_at": self.last_login_at,
        }


@dataclass
class Organization:
    id: str
    name: str
    slug: str
    created_by: str
    created_at: str = field(default_factory=now_iso)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Organization":
        return cls(
            id=row["id"], name=row["name"], slug=row["slug"],
            created_by=row["created_by"], created_at=row["created_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "slug": self.slug,
            "created_by": self.created_by, "created_at": self.created_at,
        }


@dataclass
class Membership:
    id: str
    org_id: str
    user_id: str
    role: Role
    created_at: str = field(default_factory=now_iso)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Membership":
        return cls(
            id=row["id"], org_id=row["org_id"], user_id=row["user_id"],
            role=Role.from_str(row["role"]), created_at=row["created_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "org_id": self.org_id, "user_id": self.user_id,
            "role": self.role.value, "created_at": self.created_at,
        }


@dataclass
class Project:
    id: str
    org_id: str
    name: str
    slug: str
    created_by: str
    description: str = ""
    engine: str = "cellseg1"
    settings: dict = field(default_factory=dict)  # the ProjectSettings payload
    archived: bool = False
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Project":
        return cls(
            id=row["id"], org_id=row["org_id"], name=row["name"], slug=row["slug"],
            created_by=row["created_by"], description=row["description"] or "",
            engine=row["engine"], settings=_json_load(row["settings"]),
            archived=bool(row["archived"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "org_id": self.org_id, "name": self.name,
            "slug": self.slug, "created_by": self.created_by,
            "description": self.description, "engine": self.engine,
            "settings": self.settings, "archived": self.archived,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


@dataclass
class Task:
    id: str
    project_id: str
    name: str
    created_by: str
    source: str = ""               # image path / URI to segment
    status: str = TaskStatus.PENDING
    assignee_id: Optional[str] = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Task":
        return cls(
            id=row["id"], project_id=row["project_id"], name=row["name"],
            created_by=row["created_by"], source=row["source"] or "",
            status=row["status"], assignee_id=row["assignee_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "project_id": self.project_id, "name": self.name,
            "created_by": self.created_by, "source": self.source,
            "status": self.status, "assignee_id": self.assignee_id,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


@dataclass
class Annotation:
    id: str
    task_id: str
    author_id: str
    data: dict = field(default_factory=dict)   # mask ref / stats / label payload
    status: str = AnnotationStatus.DRAFT
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_note: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Annotation":
        return cls(
            id=row["id"], task_id=row["task_id"], author_id=row["author_id"],
            data=_json_load(row["data"]), status=row["status"],
            reviewed_by=row["reviewed_by"], reviewed_at=row["reviewed_at"],
            review_note=row["review_note"] or "",
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "task_id": self.task_id, "author_id": self.author_id,
            "data": self.data, "status": self.status,
            "reviewed_by": self.reviewed_by, "reviewed_at": self.reviewed_at,
            "review_note": self.review_note,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


@dataclass
class ApiKey:
    id: str
    user_id: str
    org_id: Optional[str]
    name: str
    prefix: str
    token_hash: str
    created_at: str = field(default_factory=now_iso)
    last_used_at: Optional[str] = None
    expires_at: Optional[str] = None
    revoked: bool = False

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ApiKey":
        return cls(
            id=row["id"], user_id=row["user_id"], org_id=row["org_id"],
            name=row["name"], prefix=row["prefix"], token_hash=row["token_hash"],
            created_at=row["created_at"], last_used_at=row["last_used_at"],
            expires_at=row["expires_at"], revoked=bool(row["revoked"]),
        )

    def to_dict(self) -> dict:
        """Public projection — never includes ``token_hash``."""
        return {
            "id": self.id, "user_id": self.user_id, "org_id": self.org_id,
            "name": self.name, "prefix": self.prefix, "created_at": self.created_at,
            "last_used_at": self.last_used_at, "expires_at": self.expires_at,
            "revoked": self.revoked,
        }


@dataclass
class Session:
    id: str
    user_id: str
    token_hash: str
    created_at: str = field(default_factory=now_iso)
    expires_at: Optional[str] = None
    revoked: bool = False

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Session":
        return cls(
            id=row["id"], user_id=row["user_id"], token_hash=row["token_hash"],
            created_at=row["created_at"], expires_at=row["expires_at"],
            revoked=bool(row["revoked"]),
        )


@dataclass
class AuditEvent:
    id: str
    action: str
    actor_id: Optional[str] = None
    org_id: Optional[str] = None
    target_type: str = ""
    target_id: str = ""
    detail: dict = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "AuditEvent":
        return cls(
            id=row["id"], action=row["action"], actor_id=row["actor_id"],
            org_id=row["org_id"], target_type=row["target_type"] or "",
            target_id=row["target_id"] or "", detail=_json_load(row["detail"]),
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "action": self.action, "actor_id": self.actor_id,
            "org_id": self.org_id, "target_type": self.target_type,
            "target_id": self.target_id, "detail": self.detail,
            "created_at": self.created_at,
        }
