"""Tests for test result persistence system.

Validates:
  - test_result_store.py: DDB write/read operations, decimal conversion, error handling
  - conftest.py: pytest hook behavior, env var control
  - API endpoints: GET /api/admin/test-runs, GET /api/admin/test-runs/{run_id}

All tests are fast (mocked DDB, no AWS) unless noted otherwise.
"""
import inspect
from decimal import Decimal
from unittest import mock



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_RUN_ID = "2026-03-04T04-00-00-000000Z"
MOCK_SUMMARY = {
    "timestamp": "2026-03-04T04:00:00.000000Z",
    "total": 10,
    "passed": 9,
    "failed": 1,
    "skipped": 0,
    "errors": 0,
    "duration_s": 12.5,
    "pass_rate": 90.0,
    "model": "minimax.minimax-m2.1",
    "trigger": "pytest",
    "hostname": "test-host",
}


# ---------------------------------------------------------------------------
# TestDecimalSafe
# ---------------------------------------------------------------------------

class TestDecimalSafe:
    """Verify _decimal_safe converts floats for DynamoDB."""

    def test_converts_float_to_decimal(self):
        from app.test_result_store import _decimal_safe
        result = _decimal_safe(3.14)
        assert isinstance(result, Decimal)
        assert result == Decimal("3.14")

    def test_handles_nested_dict(self):
        from app.test_result_store import _decimal_safe
        result = _decimal_safe({"a": 1.5, "b": {"c": 2.5}})
        assert isinstance(result["a"], Decimal)
        assert isinstance(result["b"]["c"], Decimal)
        assert result["a"] == Decimal("1.5")
        assert result["b"]["c"] == Decimal("2.5")

    def test_handles_list(self):
        from app.test_result_store import _decimal_safe
        result = _decimal_safe([1.1, 2.2, 3.3])
        assert all(isinstance(v, Decimal) for v in result)

    def test_passthrough_non_float(self):
        from app.test_result_store import _decimal_safe
        assert _decimal_safe(42) == 42
        assert _decimal_safe("hello") == "hello"
        assert _decimal_safe(None) is None
        assert _decimal_safe(True) is True


# ---------------------------------------------------------------------------
# TestSaveTestRun
# ---------------------------------------------------------------------------

class TestSaveTestRun:
    """Verify save_test_run writes correct PK/SK and handles errors."""

    def test_writes_correct_pk_sk(self):
        from app.test_result_store import save_test_run

        mock_table = mock.MagicMock()
        with mock.patch("app.test_result_store._get_table", return_value=mock_table):
            result = save_test_run(MOCK_RUN_ID, MOCK_SUMMARY)

        assert result is True
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["PK"] == "TESTRUN#system"
        assert item["SK"] == f"RUN#{MOCK_RUN_ID}"
        assert item["run_id"] == MOCK_RUN_ID
        assert item["total"] == 10
        assert item["passed"] == 9
        assert item["failed"] == 1
        assert isinstance(item["duration_s"], Decimal)
        assert "ttl" in item

    def test_returns_false_on_ddb_error(self):
        from app.test_result_store import save_test_run

        mock_table = mock.MagicMock()
        mock_table.put_item.side_effect = Exception("DDB down")
        with mock.patch("app.test_result_store._get_table", return_value=mock_table):
            result = save_test_run(MOCK_RUN_ID, MOCK_SUMMARY)

        assert result is False


# ---------------------------------------------------------------------------
# TestSaveTestResult
# ---------------------------------------------------------------------------

class TestSaveTestResult:
    """Verify save_test_result writes correct PK/SK and truncates errors."""

    def test_writes_correct_pk_sk(self):
        from app.test_result_store import save_test_result

        mock_table = mock.MagicMock()
        result_data = {
            "test_file": "test_foo.py",
            "test_name": "test_bar",
            "status": "passed",
            "duration_s": 0.5,
            "error": "",
        }
        with mock.patch("app.test_result_store._get_table", return_value=mock_table):
            ok = save_test_result(MOCK_RUN_ID, "tests/test_foo.py::test_bar", result_data)

        assert ok is True
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["PK"] == f"TESTRUN#RUN#{MOCK_RUN_ID}"
        assert item["SK"] == "RESULT#tests/test_foo.py::test_bar"
        assert item["status"] == "passed"
        assert isinstance(item["duration_s"], Decimal)

    def test_truncates_long_errors(self):
        from app.test_result_store import save_test_result

        mock_table = mock.MagicMock()
        long_error = "x" * 5000
        result_data = {
            "test_file": "test_foo.py",
            "test_name": "test_fail",
            "status": "failed",
            "duration_s": 1.0,
            "error": long_error,
        }
        with mock.patch("app.test_result_store._get_table", return_value=mock_table):
            save_test_result(MOCK_RUN_ID, "tests/test_foo.py::test_fail", result_data)

        item = mock_table.put_item.call_args[1]["Item"]
        assert len(item["error"]) < 2100
        assert item["error"].endswith("... [truncated]")

    def test_returns_false_on_error(self):
        from app.test_result_store import save_test_result

        mock_table = mock.MagicMock()
        mock_table.put_item.side_effect = Exception("boom")
        with mock.patch("app.test_result_store._get_table", return_value=mock_table):
            ok = save_test_result(MOCK_RUN_ID, "nodeid", {"status": "passed"})
        assert ok is False


# ---------------------------------------------------------------------------
# TestListTestRuns
# ---------------------------------------------------------------------------

class TestListTestRuns:
    """Verify list_test_runs queries and formats results."""

    def test_returns_formatted_runs(self):
        from app.test_result_store import list_test_runs

        mock_table = mock.MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {
                    "run_id": MOCK_RUN_ID,
                    "timestamp": "2026-03-04T04:00:00Z",
                    "total": Decimal("10"),
                    "passed": Decimal("9"),
                    "failed": Decimal("1"),
                    "skipped": Decimal("0"),
                    "errors": Decimal("0"),
                    "duration_s": Decimal("12.5"),
                    "pass_rate": Decimal("90.0"),
                    "model": "minimax.minimax-m2.1",
                    "trigger": "pytest",
                },
            ]
        }
        with mock.patch("app.test_result_store._get_table", return_value=mock_table):
            runs = list_test_runs(limit=5)

        assert len(runs) == 1
        run = runs[0]
        assert run["run_id"] == MOCK_RUN_ID
        assert isinstance(run["total"], int)
        assert isinstance(run["duration_s"], float)
        assert isinstance(run["pass_rate"], float)
        assert run["passed"] == 9
        assert run["failed"] == 1

        # Verify query params
        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["ScanIndexForward"] is False  # newest first
        assert call_kwargs["Limit"] == 5

    def test_returns_empty_on_error(self):
        from app.test_result_store import list_test_runs

        mock_table = mock.MagicMock()
        mock_table.query.side_effect = Exception("timeout")
        with mock.patch("app.test_result_store._get_table", return_value=mock_table):
            runs = list_test_runs()

        assert runs == []


# ---------------------------------------------------------------------------
# TestGetRunResults
# ---------------------------------------------------------------------------

class TestGetRunResults:
    """Verify get_test_run_results queries and sorts."""

    def test_returns_sorted_results(self):
        from app.test_result_store import get_test_run_results

        mock_table = mock.MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {"nodeid": "tests/test_b.py::test_2", "test_file": "test_b.py",
                 "test_name": "test_2", "status": "passed", "duration_s": Decimal("0.1"), "error": ""},
                {"nodeid": "tests/test_a.py::test_1", "test_file": "test_a.py",
                 "test_name": "test_1", "status": "failed", "duration_s": Decimal("1.5"), "error": "AssertionError"},
            ]
        }
        with mock.patch("app.test_result_store._get_table", return_value=mock_table):
            results = get_test_run_results(MOCK_RUN_ID)

        assert len(results) == 2
        # Sorted by nodeid
        assert results[0]["nodeid"] == "tests/test_a.py::test_1"
        assert results[1]["nodeid"] == "tests/test_b.py::test_2"
        assert isinstance(results[0]["duration_s"], float)

    def test_returns_empty_on_error(self):
        from app.test_result_store import get_test_run_results

        mock_table = mock.MagicMock()
        mock_table.query.side_effect = Exception("DDB unreachable")
        with mock.patch("app.test_result_store._get_table", return_value=mock_table):
            results = get_test_run_results(MOCK_RUN_ID)

        assert results == []


# ---------------------------------------------------------------------------
# TestApiEndpoints
# ---------------------------------------------------------------------------

class TestApiEndpoints:
    """Verify admin test-run API endpoints return correct shapes."""

    def test_list_runs_returns_200(self):
        from fastapi.testclient import TestClient
        from app.main import app

        with mock.patch("app.test_result_store.list_test_runs", return_value=[
            {"run_id": MOCK_RUN_ID, "timestamp": "2026-03-04T04:00:00Z",
             "total": 10, "passed": 9, "failed": 1, "skipped": 0, "errors": 0,
             "duration_s": 12.5, "pass_rate": 90.0, "model": "test", "trigger": "pytest"},
        ]):
            client = TestClient(app)
            resp = client.get("/api/admin/test-runs?limit=5")

        assert resp.status_code == 200
        body = resp.json()
        assert "runs" in body
        assert "count" in body
        assert body["count"] == 1
        assert body["runs"][0]["run_id"] == MOCK_RUN_ID

    def test_detail_returns_200(self):
        from fastapi.testclient import TestClient
        from app.main import app

        with mock.patch("app.test_result_store.get_test_run_results", return_value=[
            {"nodeid": "test_a.py::test_1", "test_file": "test_a.py",
             "test_name": "test_1", "status": "passed", "duration_s": 0.5, "error": ""},
        ]):
            client = TestClient(app)
            resp = client.get(f"/api/admin/test-runs/{MOCK_RUN_ID}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == MOCK_RUN_ID
        assert body["count"] == 1
        assert body["results"][0]["status"] == "passed"


# ---------------------------------------------------------------------------
# TestConftest
# ---------------------------------------------------------------------------

class TestConftest:
    """Verify conftest.py hook behavior via source inspection."""

    @staticmethod
    def _load_conftest():
        import importlib.util
        import pathlib
        conftest_path = pathlib.Path(__file__).parent / "conftest.py"
        spec = importlib.util.spec_from_file_location("conftest", conftest_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_persist_env_var_controls_write(self):
        """conftest checks EAGLE_PERSIST_TEST_RESULTS before writing."""
        conftest_mod = self._load_conftest()
        source = inspect.getsource(conftest_mod.pytest_sessionfinish)
        assert "_PERSIST" in source or "EAGLE_PERSIST_TEST_RESULTS" in source

    def test_only_captures_call_phase(self):
        """conftest filters to when=='call' (not setup/teardown)."""
        conftest_mod = self._load_conftest()
        source = inspect.getsource(conftest_mod.pytest_runtest_makereport)
        assert '"call"' in source or "'call'" in source

    def test_run_id_is_url_safe(self):
        """run_id replaces colons and dots so it's safe in URL paths."""
        conftest_mod = self._load_conftest()
        source = inspect.getsource(conftest_mod.pytest_sessionfinish)
        assert 'replace(":", "-")' in source
        assert 'replace(".", "-")' in source
