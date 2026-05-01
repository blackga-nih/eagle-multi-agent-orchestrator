"""Tests for exec_batch_generate_documents and exec_get_doc_jobs.

PR2.2 of the jolly-snacking-narwhal plan. These tests mock the DOCJOB#
store and the create_document handler so we can exercise the batch
loop end-to-end without DDB or Bedrock.
"""
import pytest


TENANT = "test-tenant"
USER = "test-user"
PACKAGE_ID = "PKG-2026-0001"


# ---------------------------------------------------------------------------
# Test fixtures — fake docjob store + fake create_document
# ---------------------------------------------------------------------------


class _FakeDocJobStore:
    """Mimics package_doc_job_store at module-attribute level so we can
    track every transition the batch tool issues."""

    def __init__(self):
        self._counter = 0
        self.jobs: dict[str, dict] = {}

    def create_job(
        self,
        tenant_id,
        package_id,
        doc_type,
        actor_user_id,
        session_id=None,
        job_spec=None,
    ):
        self._counter += 1
        job_id = f"job-{self._counter}"
        job = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "package_id": package_id,
            "doc_type": doc_type,
            "status": "queued",
            "actor_user_id": actor_user_id,
            "session_id": session_id,
            "job_spec": job_spec or {},
            "created_at": f"2026-05-01T15:00:0{self._counter}+00:00",
            "updated_at": f"2026-05-01T15:00:0{self._counter}+00:00",
        }
        self.jobs[job_id] = job
        return dict(job)

    def update_job_status(
        self,
        tenant_id,
        package_id,
        job_id,
        status,
        document_id=None,
        error_message=None,
    ):
        job = self.jobs.get(job_id)
        if not job:
            return None
        job["status"] = status
        job["updated_at"] = "2026-05-01T15:01:00+00:00"
        if status in {"done", "failed"}:
            job["completed_at"] = "2026-05-01T15:01:00+00:00"
        if document_id is not None:
            job["document_id"] = document_id
        if error_message is not None:
            job["error_message"] = error_message[:2000]
        return dict(job)

    def list_jobs_for_package(self, tenant_id, package_id, limit=100):
        return [
            dict(j)
            for j in sorted(self.jobs.values(), key=lambda x: x["created_at"])
            if j["package_id"] == package_id
        ][:limit]

    def list_recently_completed(self, tenant_id, package_id, since_iso):
        return [
            dict(j)
            for j in self.jobs.values()
            if j["package_id"] == package_id
            and j["status"] == "done"
            and j.get("completed_at", "") >= since_iso
        ]

    def list_pending_for_package(self, tenant_id, package_id):
        return [
            dict(j)
            for j in self.jobs.values()
            if j["package_id"] == package_id and j["status"] in {"queued", "running"}
        ]


@pytest.fixture
def fake_store(monkeypatch):
    store = _FakeDocJobStore()
    # Patch the docjob_store module reference inside batch_doc_gen_tools
    from app.tools import batch_doc_gen_tools

    monkeypatch.setattr(batch_doc_gen_tools, "docjob_store", store)
    return store


@pytest.fixture
def approved_package(monkeypatch):
    pkg = {
        "package_id": PACKAGE_ID,
        "tenant_id": TENANT,
        "status": "drafting",
        "intake_approved_at": "2026-04-30T10:00:00+00:00",
    }
    from app.tools import batch_doc_gen_tools

    monkeypatch.setattr(
        batch_doc_gen_tools, "get_package", lambda t, p: pkg if p == PACKAGE_ID else None
    )
    return pkg


# ---------------------------------------------------------------------------
# exec_batch_generate_documents
# ---------------------------------------------------------------------------


class TestBatchGenerateDocuments:
    def test_happy_path_three_doc_types_all_succeed(
        self, fake_store, approved_package, monkeypatch
    ):
        from app.tools import batch_doc_gen_tools

        # Stub create_document so each call returns a unique document_id
        call_count = {"n": 0}

        def fake_create(params, tenant_id, session_id=None):
            call_count["n"] += 1
            return {
                "document_id": f"doc-{call_count['n']}",
                "doc_type": params["doc_type"],
                "status": "draft",
            }

        monkeypatch.setattr(batch_doc_gen_tools, "exec_create_document", fake_create)

        result = batch_doc_gen_tools.exec_batch_generate_documents(
            {
                "package_id": PACKAGE_ID,
                "doc_types": ["sow", "igce", "acquisition_plan"],
                "actor_user_id": USER,
            },
            tenant_id=TENANT,
        )

        assert result["package_id"] == PACKAGE_ID
        assert len(result["jobs"]) == 3
        assert result["summary"] == {"queued": 0, "running": 0, "done": 3, "failed": 0}
        # All jobs hit done with a document_id
        for j in result["jobs"]:
            assert j["status"] == "done"
            assert j["document_id"].startswith("doc-")

    def test_one_failure_does_not_abort_remaining(
        self, fake_store, approved_package, monkeypatch
    ):
        from app.tools import batch_doc_gen_tools

        def fake_create(params, tenant_id, session_id=None):
            if params["doc_type"] == "igce":
                return {"error": "template_missing", "message": "no IGCE template"}
            return {"document_id": f"doc-{params['doc_type']}", "status": "draft"}

        monkeypatch.setattr(batch_doc_gen_tools, "exec_create_document", fake_create)

        result = batch_doc_gen_tools.exec_batch_generate_documents(
            {
                "package_id": PACKAGE_ID,
                "doc_types": ["sow", "igce", "acquisition_plan"],
                "actor_user_id": USER,
            },
            tenant_id=TENANT,
        )

        assert result["summary"] == {"queued": 0, "running": 0, "done": 2, "failed": 1}
        statuses_by_type = {j["doc_type"]: j["status"] for j in result["jobs"]}
        assert statuses_by_type == {"sow": "done", "igce": "failed", "acquisition_plan": "done"}
        # Failure carries the error_message through
        igce_job = next(j for j in result["jobs"] if j["doc_type"] == "igce")
        assert "no IGCE template" in igce_job["error_message"]

    def test_create_document_raises_recorded_as_failed(
        self, fake_store, approved_package, monkeypatch
    ):
        from app.tools import batch_doc_gen_tools

        def fake_create(params, tenant_id, session_id=None):
            raise RuntimeError("bedrock 503")

        monkeypatch.setattr(batch_doc_gen_tools, "exec_create_document", fake_create)

        result = batch_doc_gen_tools.exec_batch_generate_documents(
            {
                "package_id": PACKAGE_ID,
                "doc_types": ["sow"],
                "actor_user_id": USER,
            },
            tenant_id=TENANT,
        )

        assert result["jobs"][0]["status"] == "failed"
        assert "bedrock 503" in result["jobs"][0]["error_message"]

    def test_missing_package_id_returns_error(self):
        from app.tools.batch_doc_gen_tools import exec_batch_generate_documents

        result = exec_batch_generate_documents(
            {"doc_types": ["sow"], "actor_user_id": USER}, tenant_id=TENANT
        )
        assert result["error"] == "missing_package_id"

    def test_missing_actor_user_id_returns_error(self):
        from app.tools.batch_doc_gen_tools import exec_batch_generate_documents

        result = exec_batch_generate_documents(
            {"package_id": PACKAGE_ID, "doc_types": ["sow"]}, tenant_id=TENANT
        )
        assert result["error"] == "missing_actor_user_id"

    def test_invalid_doc_types_returns_error(self):
        from app.tools.batch_doc_gen_tools import exec_batch_generate_documents

        result = exec_batch_generate_documents(
            {"package_id": PACKAGE_ID, "doc_types": [], "actor_user_id": USER},
            tenant_id=TENANT,
        )
        assert result["error"] == "invalid_doc_types"

    def test_too_many_doc_types_capped(self, monkeypatch):
        from app.tools import batch_doc_gen_tools

        result = batch_doc_gen_tools.exec_batch_generate_documents(
            {
                "package_id": PACKAGE_ID,
                "doc_types": [f"slot-{i}" for i in range(50)],
                "actor_user_id": USER,
            },
            tenant_id=TENANT,
        )
        assert result["error"] == "too_many_doc_types"

    def test_package_not_found(self, monkeypatch):
        from app.tools import batch_doc_gen_tools

        monkeypatch.setattr(batch_doc_gen_tools, "get_package", lambda t, p: None)

        result = batch_doc_gen_tools.exec_batch_generate_documents(
            {
                "package_id": "PKG-MISSING",
                "doc_types": ["sow"],
                "actor_user_id": USER,
            },
            tenant_id=TENANT,
        )
        assert result["error"] == "package_not_found"

    def test_invalid_doc_type_string_handled_per_entry(
        self, fake_store, approved_package, monkeypatch
    ):
        """A blank doc_type entry doesn't crash the loop; it surfaces as a
        per-entry failure and the rest of the list still runs."""
        from app.tools import batch_doc_gen_tools

        def fake_create(params, tenant_id, session_id=None):
            return {"document_id": "doc-ok", "status": "draft"}

        monkeypatch.setattr(batch_doc_gen_tools, "exec_create_document", fake_create)

        result = batch_doc_gen_tools.exec_batch_generate_documents(
            {
                "package_id": PACKAGE_ID,
                "doc_types": ["sow", "", "igce"],
                "actor_user_id": USER,
            },
            tenant_id=TENANT,
        )
        assert result["summary"]["done"] == 2
        assert result["summary"]["failed"] == 1


# ---------------------------------------------------------------------------
# exec_get_doc_jobs
# ---------------------------------------------------------------------------


class TestGetDocJobs:
    def test_no_since_returns_all_jobs_with_summary(self, fake_store):
        from app.tools.batch_doc_gen_tools import exec_get_doc_jobs

        # Pre-seed a few jobs of various statuses
        j1 = fake_store.create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)
        fake_store.update_job_status(TENANT, PACKAGE_ID, j1["job_id"], "done", document_id="d1")
        j2 = fake_store.create_job(TENANT, PACKAGE_ID, "igce", actor_user_id=USER)
        fake_store.update_job_status(TENANT, PACKAGE_ID, j2["job_id"], "running")
        fake_store.create_job(TENANT, PACKAGE_ID, "acquisition_plan", actor_user_id=USER)

        result = exec_get_doc_jobs(
            {"package_id": PACKAGE_ID}, tenant_id=TENANT
        )
        assert result["package_id"] == PACKAGE_ID
        assert len(result["jobs"]) == 3
        assert result["summary"] == {"queued": 1, "running": 1, "done": 1, "failed": 0}
        # Pending list excludes the done one
        pending_types = {p["doc_type"] for p in result["pending"]}
        assert pending_types == {"igce", "acquisition_plan"}

    def test_since_returns_recently_completed_only(self, fake_store):
        from app.tools.batch_doc_gen_tools import exec_get_doc_jobs

        j_old = fake_store.create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)
        # Override the completed_at of j_old with an earlier timestamp
        fake_store.update_job_status(TENANT, PACKAGE_ID, j_old["job_id"], "done", document_id="d-old")
        fake_store.jobs[j_old["job_id"]]["completed_at"] = "2026-05-01T09:00:00+00:00"

        j_new = fake_store.create_job(TENANT, PACKAGE_ID, "igce", actor_user_id=USER)
        fake_store.update_job_status(TENANT, PACKAGE_ID, j_new["job_id"], "done", document_id="d-new")
        fake_store.jobs[j_new["job_id"]]["completed_at"] = "2026-05-01T15:00:00+00:00"

        result = exec_get_doc_jobs(
            {"package_id": PACKAGE_ID, "since_iso": "2026-05-01T10:00:00+00:00"},
            tenant_id=TENANT,
        )

        assert "recently_completed" in result
        assert len(result["recently_completed"]) == 1
        assert result["recently_completed"][0]["document_id"] == "d-new"

    def test_missing_package_id_returns_error(self):
        from app.tools.batch_doc_gen_tools import exec_get_doc_jobs

        result = exec_get_doc_jobs({}, tenant_id=TENANT)
        assert result["error"] == "missing_package_id"

    def test_include_pending_false_omits_pending_list(self, fake_store):
        from app.tools.batch_doc_gen_tools import exec_get_doc_jobs

        fake_store.create_job(TENANT, PACKAGE_ID, "sow", actor_user_id=USER)

        result = exec_get_doc_jobs(
            {"package_id": PACKAGE_ID, "include_pending": False}, tenant_id=TENANT
        )
        assert "pending" not in result


# ---------------------------------------------------------------------------
# Dispatch registration
# ---------------------------------------------------------------------------


class TestDispatchRegistration:
    def test_handlers_in_dispatch_dict(self):
        from app.tools.legacy_dispatch import get_tool_dispatch

        dispatch = get_tool_dispatch()
        assert "batch_generate_documents" in dispatch
        assert "get_doc_jobs" in dispatch

    def test_session_aware(self):
        from app.tools.legacy_dispatch import TOOLS_NEEDING_SESSION

        assert "batch_generate_documents" in TOOLS_NEEDING_SESSION
        assert "get_doc_jobs" in TOOLS_NEEDING_SESSION
