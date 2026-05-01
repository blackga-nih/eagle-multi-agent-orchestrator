"""Tests for package_doc_job_store — DOCJOB# DDB entity store.

PR2.1 of the jolly-snacking-narwhal plan. Mocks DDB at the boto3 table
level so the tests are fast and don't touch real AWS.
"""
from unittest import mock

import pytest


TENANT = "test-tenant"
PACKAGE_ID = "PKG-2026-0001"
USER = "test-user"


# ---------------------------------------------------------------------------
# Fake table — minimal in-memory DDB stand-in
# ---------------------------------------------------------------------------


class _FakeTable:
    """Minimal stand-in for the boto3 Table resource used by package_doc_job_store.

    Supports put_item, get_item, update_item, query (with KeyConditionExpression
    using begins_with on SK). Just enough to exercise the store's code paths.
    """

    def __init__(self):
        self.items: dict[tuple, dict] = {}

    # boto3 surface
    def put_item(self, Item):
        self.items[(Item["PK"], Item["SK"])] = dict(Item)
        return {}

    def get_item(self, Key):
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": dict(item)} if item else {}

    def update_item(
        self,
        Key,
        UpdateExpression,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
        ReturnValues=None,
    ):
        existing = self.items.get((Key["PK"], Key["SK"]))
        if not existing:
            return {}

        names = ExpressionAttributeNames or {}
        values = ExpressionAttributeValues or {}

        # Parse "SET a = :a, b = :b, ..." — the only form the store uses.
        assert UpdateExpression.startswith("SET ")
        for assignment in UpdateExpression[4:].split(", "):
            field_token, value_token = [t.strip() for t in assignment.split("=")]
            field_name = names.get(field_token, field_token)
            existing[field_name] = values[value_token]

        self.items[(Key["PK"], Key["SK"])] = existing
        return {"Attributes": dict(existing)} if ReturnValues == "ALL_NEW" else {}

    def query(self, KeyConditionExpression=None, Limit=None, **_):
        """Decode a boto3 KeyConditionExpression into PK eq + SK begins_with.

        boto3.dynamodb.conditions exposes ``get_expression()`` on every
        ConditionBase, returning a dict of the form
            {"format": "{0} {operator} {1}", "operator": "AND|=|begins_with|...",
             "values": [...]}.
        For our two-clause "PK eq X AND SK begins_with Y" pattern that's
        all we need — recurse into the AND and extract the two leaves.
        """
        pk_val, sk_prefix = self._decode_key_condition(KeyConditionExpression)

        items = [
            dict(v)
            for (pk, sk), v in self.items.items()
            if pk == pk_val and (not sk_prefix or sk.startswith(sk_prefix))
        ]
        if Limit:
            items = items[:Limit]
        return {"Items": items}

    @staticmethod
    def _decode_key_condition(cond):
        """Return (pk_eq_value, sk_begins_with_prefix) from a boto3 condition."""
        if cond is None:
            return None, None

        expr = cond.get_expression()  # boto3 ConditionBase API
        operator = expr.get("operator")

        if operator == "AND":
            left, right = expr["values"]
            pk_left, sk_left = _FakeTable._decode_key_condition(left)
            pk_right, sk_right = _FakeTable._decode_key_condition(right)
            return (pk_left or pk_right, sk_left or sk_right)

        if operator == "=":
            attr, value = expr["values"]
            attr_name = getattr(attr, "name", str(attr))
            if attr_name == "PK":
                return value, None

        if operator == "begins_with":
            attr, value = expr["values"]
            attr_name = getattr(attr, "name", str(attr))
            if attr_name == "SK":
                return None, value

        return None, None


@pytest.fixture
def fake_table():
    table = _FakeTable()
    with mock.patch("app.package_doc_job_store.get_table", return_value=table):
        yield table


# ---------------------------------------------------------------------------
# create_job
# ---------------------------------------------------------------------------


class TestCreateJob:
    def test_creates_queued_job_with_required_fields(self, fake_table):
        from app.package_doc_job_store import create_job

        job = create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)

        assert job["job_id"]  # uuid
        assert job["tenant_id"] == TENANT
        assert job["package_id"] == PACKAGE_ID
        assert job["doc_type"] == "sow"
        assert job["status"] == "queued"
        assert job["actor_user_id"] == USER
        assert job["created_at"]
        assert job["updated_at"] == job["created_at"]
        # Persisted under both keys
        assert (job["PK"], job["SK"]) in fake_table.items
        # GSI1 keys are populated for status-by-time queries
        assert job["GSI1PK"] == f"TENANT#{TENANT}"
        assert job["GSI1SK"].startswith("DOCJOB#queued#")

    def test_session_id_optional(self, fake_table):
        from app.package_doc_job_store import create_job

        with_session = create_job(
            TENANT, PACKAGE_ID, "sow", actor_user_id=USER, session_id="sess-1"
        )
        without_session = create_job(
            TENANT, PACKAGE_ID, "sow", actor_user_id=USER
        )
        assert with_session["session_id"] == "sess-1"
        assert "session_id" not in without_session

    def test_job_spec_persisted_when_provided(self, fake_table):
        from app.package_doc_job_store import create_job

        spec = {"title": "Test SOW", "data": {"scope": "Test scope"}}
        job = create_job(
            TENANT, PACKAGE_ID, "sow", actor_user_id=USER, job_spec=spec
        )
        assert job["job_spec"] == spec


# ---------------------------------------------------------------------------
# update_job_status
# ---------------------------------------------------------------------------


class TestUpdateJobStatus:
    def test_transition_to_running(self, fake_table):
        from app.package_doc_job_store import create_job, update_job_status

        job = create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)
        updated = update_job_status(
            TENANT, PACKAGE_ID, job["job_id"], "running"
        )
        assert updated["status"] == "running"
        # GSI1SK rewritten to reflect new status
        assert updated["GSI1SK"].startswith("DOCJOB#running#")
        # No completed_at on running
        assert "completed_at" not in updated

    def test_transition_to_done_stamps_completed_at_and_doc_id(self, fake_table):
        from app.package_doc_job_store import create_job, update_job_status

        job = create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)
        updated = update_job_status(
            TENANT,
            PACKAGE_ID,
            job["job_id"],
            "done",
            document_id="doc-uuid-123",
        )
        assert updated["status"] == "done"
        assert updated["completed_at"]
        assert updated["document_id"] == "doc-uuid-123"

    def test_transition_to_failed_stamps_error_message(self, fake_table):
        from app.package_doc_job_store import create_job, update_job_status

        job = create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)
        updated = update_job_status(
            TENANT,
            PACKAGE_ID,
            job["job_id"],
            "failed",
            error_message="bedrock timeout after 120s",
        )
        assert updated["status"] == "failed"
        assert updated["completed_at"]
        assert updated["error_message"] == "bedrock timeout after 120s"

    def test_huge_error_message_is_truncated_to_2kb(self, fake_table):
        from app.package_doc_job_store import create_job, update_job_status

        job = create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)
        massive = "x" * 50_000
        updated = update_job_status(
            TENANT, PACKAGE_ID, job["job_id"], "failed", error_message=massive
        )
        # Cap at 2000 chars so a runaway stack trace doesn't blow the 400KB
        # DDB item limit.
        assert len(updated["error_message"]) == 2000

    def test_invalid_status_raises(self, fake_table):
        from app.package_doc_job_store import create_job, update_job_status

        job = create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)
        with pytest.raises(ValueError, match="invalid status"):
            update_job_status(TENANT, PACKAGE_ID, job["job_id"], "exploded")

    def test_returns_none_when_job_missing(self, fake_table):
        from app.package_doc_job_store import update_job_status

        result = update_job_status(TENANT, PACKAGE_ID, "no-such-job", "done")
        assert result is None


# ---------------------------------------------------------------------------
# list_jobs_for_package
# ---------------------------------------------------------------------------


class TestListJobsForPackage:
    def test_returns_jobs_in_chronological_order(self, fake_table):
        from app.package_doc_job_store import create_job, list_jobs_for_package

        # Create three jobs with controlled timestamps via monkeypatched now_iso
        with mock.patch("app.package_doc_job_store.now_iso") as mock_now:
            mock_now.return_value = "2026-05-01T10:00:00+00:00"
            create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)
            mock_now.return_value = "2026-05-01T10:05:00+00:00"
            create_job(TENANT, PACKAGE_ID, "igce", actor_user_id=USER)
            mock_now.return_value = "2026-05-01T10:02:00+00:00"
            create_job(TENANT, PACKAGE_ID, "acquisition_plan", actor_user_id=USER)

        jobs = list_jobs_for_package(TENANT, PACKAGE_ID)
        assert [j["doc_type"] for j in jobs] == ["sow", "acquisition_plan", "igce"]

    def test_only_returns_jobs_for_target_package(self, fake_table):
        from app.package_doc_job_store import create_job, list_jobs_for_package

        create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)
        create_job(TENANT, "PKG-OTHER", "igce", actor_user_id=USER)

        jobs = list_jobs_for_package(TENANT, PACKAGE_ID)
        assert len(jobs) == 1
        assert jobs[0]["doc_type"] == "sow"

    def test_empty_list_for_no_jobs(self, fake_table):
        from app.package_doc_job_store import list_jobs_for_package

        assert list_jobs_for_package(TENANT, PACKAGE_ID) == []


# ---------------------------------------------------------------------------
# list_recently_completed
# ---------------------------------------------------------------------------


class TestListRecentlyCompleted:
    def test_returns_only_done_after_threshold(self, fake_table):
        from app.package_doc_job_store import (
            create_job,
            list_recently_completed,
            update_job_status,
        )

        # Two completed before threshold, one after, one still running
        with mock.patch("app.package_doc_job_store.now_iso") as mock_now:
            mock_now.return_value = "2026-05-01T09:00:00+00:00"
            old = create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)
            mock_now.return_value = "2026-05-01T09:05:00+00:00"
            update_job_status(TENANT, PACKAGE_ID, old["job_id"], "done", document_id="d1")

            mock_now.return_value = "2026-05-01T10:00:00+00:00"
            new = create_job(TENANT, PACKAGE_ID, "igce", actor_user_id=USER)
            mock_now.return_value = "2026-05-01T10:05:00+00:00"
            update_job_status(TENANT, PACKAGE_ID, new["job_id"], "done", document_id="d2")

            mock_now.return_value = "2026-05-01T10:10:00+00:00"
            running = create_job(TENANT, PACKAGE_ID, "ap", actor_user_id=USER)
            update_job_status(TENANT, PACKAGE_ID, running["job_id"], "running")

        recent = list_recently_completed(
            TENANT, PACKAGE_ID, since_iso="2026-05-01T10:00:00+00:00"
        )
        assert len(recent) == 1
        assert recent[0]["doc_type"] == "igce"
        assert recent[0]["document_id"] == "d2"

    def test_excludes_failed_jobs(self, fake_table):
        from app.package_doc_job_store import (
            create_job,
            list_recently_completed,
            update_job_status,
        )

        job = create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)
        update_job_status(
            TENANT, PACKAGE_ID, job["job_id"], "failed", error_message="oops"
        )

        # since_iso old enough that the failed job's completed_at is >= it
        recent = list_recently_completed(
            TENANT, PACKAGE_ID, since_iso="2020-01-01T00:00:00+00:00"
        )
        assert recent == []


# ---------------------------------------------------------------------------
# list_pending_for_package
# ---------------------------------------------------------------------------


class TestListPendingForPackage:
    def test_returns_queued_and_running_only(self, fake_table):
        from app.package_doc_job_store import (
            create_job,
            list_pending_for_package,
            update_job_status,
        )

        queued = create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)
        running = create_job(TENANT, PACKAGE_ID, "igce", actor_user_id=USER)
        update_job_status(TENANT, PACKAGE_ID, running["job_id"], "running")
        done = create_job(TENANT, PACKAGE_ID, "ap", actor_user_id=USER)
        update_job_status(TENANT, PACKAGE_ID, done["job_id"], "done", document_id="d")

        pending = list_pending_for_package(TENANT, PACKAGE_ID)
        statuses = sorted(j["status"] for j in pending)
        ids = sorted(j["job_id"] for j in pending)
        assert statuses == ["queued", "running"]
        assert ids == sorted([queued["job_id"], running["job_id"]])
