"""Tests for server.models — row decoding and safe projections."""
from server.models import (
    Annotation,
    ApiKey,
    AuditEvent,
    Membership,
    Project,
    User,
    new_id,
    now_iso,
)
from server.rbac import Role


def test_ids_unique_and_timestamps_sortable():
    assert new_id() != new_id()
    assert len(new_id()) == 32
    # ISO-8601 strings sort chronologically as plain strings
    assert "2020-01-01T00:00:00+00:00" < now_iso()


def test_user_from_row_and_secret_projection():
    row = {
        "id": "u1", "email": "a@b.com", "username": "alice",
        "password_hash": "scrypt$...secret...", "full_name": "Alice",
        "is_active": 1, "is_superuser": 0,
        "created_at": "2026-01-01T00:00:00+00:00", "last_login_at": None,
    }
    user = User.from_row(row)
    assert user.is_active is True and user.is_superuser is False
    # to_dict must never leak the password hash
    d = user.to_dict()
    assert "password_hash" not in d
    assert d["email"] == "a@b.com"


def test_membership_role_decoded_to_enum():
    m = Membership.from_row({
        "id": "m1", "org_id": "o1", "user_id": "u1", "role": "manager",
        "created_at": now_iso(),
    })
    assert m.role is Role.MANAGER
    assert m.to_dict()["role"] == "manager"


def test_project_json_settings_decoded():
    p = Project.from_row({
        "id": "p1", "org_id": "o1", "name": "Nuclei", "slug": "nuclei",
        "created_by": "u1", "description": None, "engine": "cellseg1",
        "settings": '{"resize_size": 512, "clahe": true}', "archived": 0,
        "created_at": now_iso(), "updated_at": now_iso(),
    })
    assert p.settings == {"resize_size": 512, "clahe": True}
    assert p.description == ""  # None coerced to ""
    assert p.archived is False


def test_project_tolerates_bad_json():
    p = Project.from_row({
        "id": "p1", "org_id": "o1", "name": "X", "slug": "x", "created_by": "u1",
        "description": "", "engine": "cellpose", "settings": "not json",
        "archived": 1, "created_at": now_iso(), "updated_at": now_iso(),
    })
    assert p.settings == {}
    assert p.archived is True


def test_annotation_and_apikey_projection():
    a = Annotation.from_row({
        "id": "a1", "task_id": "t1", "author_id": "u1",
        "data": '{"n_cells": 42}', "status": "submitted",
        "reviewed_by": None, "reviewed_at": None, "review_note": None,
        "created_at": now_iso(), "updated_at": now_iso(),
    })
    assert a.data == {"n_cells": 42}
    assert a.review_note == ""

    k = ApiKey.from_row({
        "id": "k1", "user_id": "u1", "org_id": "o1", "name": "CI",
        "prefix": "csk_ab12", "token_hash": "deadbeef",
        "created_at": now_iso(), "last_used_at": None, "expires_at": None,
        "revoked": 0,
    })
    assert "token_hash" not in k.to_dict()  # secret omitted
    assert k.to_dict()["prefix"] == "csk_ab12"


def test_audit_event_from_row():
    e = AuditEvent.from_row({
        "id": "e1", "action": "project.create", "actor_id": "u1", "org_id": "o1",
        "target_type": "project", "target_id": "p1",
        "detail": '{"name": "Nuclei"}', "created_at": now_iso(),
    })
    assert e.action == "project.create"
    assert e.detail == {"name": "Nuclei"}
