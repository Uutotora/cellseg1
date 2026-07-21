"""Tests for server.rbac — the permission matrix and role hierarchy."""
import pytest

from server.errors import PermissionDenied
from server.rbac import (
    Perm,
    Role,
    assignable_roles,
    can,
    can_assign_role,
    permissions_for,
    require,
)


def test_owner_is_superset_of_admin_of_manager():
    assert permissions_for(Role.MANAGER) <= permissions_for(Role.ADMIN)
    assert permissions_for(Role.ADMIN) <= permissions_for(Role.OWNER)
    assert permissions_for(Role.VIEWER) <= permissions_for(Role.ANNOTATOR)


def test_role_specific_capabilities():
    # Annotator can create annotations but not review them.
    assert can(Role.ANNOTATOR, Perm.ANNOTATION_CREATE)
    assert not can(Role.ANNOTATOR, Perm.ANNOTATION_REVIEW)
    # Reviewer can review but can't create projects.
    assert can(Role.REVIEWER, Perm.ANNOTATION_REVIEW)
    assert not can(Role.REVIEWER, Perm.PROJECT_CREATE)
    # Manager can create projects but can't manage members or delete the org.
    assert can(Role.MANAGER, Perm.PROJECT_CREATE)
    assert not can(Role.MANAGER, Perm.ORG_MANAGE_MEMBERS)
    assert not can(Role.MANAGER, Perm.ORG_DELETE)
    # Only the owner can delete the org.
    assert can(Role.OWNER, Perm.ORG_DELETE)
    assert not can(Role.ADMIN, Perm.ORG_DELETE)


def test_viewer_is_read_only():
    perms = permissions_for(Role.VIEWER)
    assert perms == {Perm.ORG_VIEW, Perm.PROJECT_VIEW, Perm.TASK_VIEW, Perm.ANNOTATION_VIEW}


def test_can_accepts_role_or_string():
    assert can("owner", Perm.ORG_DELETE)
    assert not can("viewer", Perm.PROJECT_CREATE)
    assert not can("nonsense-role", Perm.PROJECT_VIEW)  # unknown => no perms


def test_require_raises_or_passes():
    require(Role.OWNER, Perm.ORG_DELETE)  # no raise
    with pytest.raises(PermissionDenied):
        require(Role.VIEWER, Perm.PROJECT_CREATE)


def test_assignable_roles_prevents_escalation():
    # An admin can grant up to manager (strictly below admin), never owner/admin.
    admin_grants = assignable_roles(Role.ADMIN)
    assert Role.MANAGER in admin_grants
    assert Role.OWNER not in admin_grants
    assert Role.ADMIN not in admin_grants
    # An owner can grant admin and below, AND owner (co-ownership / transfer).
    owner_grants = assignable_roles(Role.OWNER)
    assert Role.ADMIN in owner_grants
    assert Role.OWNER in owner_grants
    # A manager can't manage members at all.
    assert assignable_roles(Role.MANAGER) == []
    assert assignable_roles(Role.VIEWER) == []


def test_can_assign_role():
    assert can_assign_role(Role.OWNER, Role.ADMIN)
    assert can_assign_role(Role.OWNER, Role.OWNER)  # ownership transfer allowed
    assert not can_assign_role(Role.ADMIN, Role.OWNER)
    assert not can_assign_role(Role.ADMIN, Role.ADMIN)  # no lateral admin grant
    assert not can_assign_role(Role.MANAGER, Role.VIEWER)


def test_assignable_roles_are_ordered_senior_first():
    grants = assignable_roles(Role.OWNER)
    ranks = [Role.OWNER, Role.ADMIN, Role.MANAGER, Role.REVIEWER, Role.ANNOTATOR, Role.VIEWER]
    assert grants == ranks
