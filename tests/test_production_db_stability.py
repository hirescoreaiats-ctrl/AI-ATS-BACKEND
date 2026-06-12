import ast
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from backend import database
from backend.database import PRODUCTION_POOL_SETTINGS
from backend.main import app
from backend.routers import job as job_router
from backend.routers import resume as resume_router


def test_production_pool_settings_are_supabase_safe():
    assert PRODUCTION_POOL_SETTINGS == {
        "pool_size": 3,
        "max_overflow": 2,
        "pool_timeout": 30,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }
    if not database.settings.is_sqlite:
        for key, value in PRODUCTION_POOL_SETTINGS.items():
            assert database.engine_kwargs[key] == value


def test_get_db_closes_session(monkeypatch):
    class FakeSession:
        closed = False

        def close(self):
            self.closed = True

    fake = FakeSession()
    monkeypatch.setattr(database, "SessionLocal", lambda: fake)

    dependency = database.get_db()
    assert next(dependency) is fake
    dependency.close()

    assert fake.closed is True


def test_direct_sessionlocal_usage_has_close_in_critical_modules():
    critical_paths = [
        Path("backend/routers/job.py"),
        Path("backend/routers/resume.py"),
        Path("backend/routers/auth.py"),
        Path("backend/workers/tasks.py"),
        Path("backend/api/health.py"),
    ]
    offenders = []
    for path in critical_paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                segment = ast.get_source_segment(source, node) or ""
                if "SessionLocal()" in segment and ".close()" not in segment:
                    offenders.append(f"{path}:{node.lineno}:{node.name}")

    assert offenders == []


def test_dashboard_operational_error_returns_500_not_fake_zero():
    route_path = "/jobs-operational-error-test"
    if not any(getattr(route, "path", "") == route_path for route in app.routes):
        @app.get(route_path)
        def _raise_operational_error_for_test():
            raise OperationalError(
                "SELECT 1",
                {},
                Exception("EMAXCONNSESSION max clients reached in session mode"),
            )

    response = TestClient(app).get(route_path)

    assert response.status_code == 500
    assert response.json()["detail"] == "Database temporarily unavailable"
    assert response.json()["error_type"] == "db_connection_exhausted"
    assert "active_jobs" not in response.json()


def test_dashboard_true_empty_state_returns_empty_jobs(monkeypatch):
    class FakeQuery:
        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            return []

    class FakeDB:
        closed = False
        committed = False

        def query(self, *_args, **_kwargs):
            return FakeQuery()

        def commit(self):
            self.committed = True

        def close(self):
            self.closed = True

    fake_db = FakeDB()
    monkeypatch.setattr(job_router, "SessionLocal", lambda: fake_db)

    assert job_router.get_jobs() == []
    assert fake_db.committed is True
    assert fake_db.closed is True


def test_unauthorized_dashboard_request_returns_401_or_403():
    response = TestClient(app).get("/jobs")
    assert response.status_code in {401, 403}


def test_background_processing_concurrency_is_limited():
    assert resume_router._batch_size <= 3
    assert resume_router._resume_processing_executor._max_workers <= 3


def test_debug_runtime_endpoint_returns_pool_settings():
    response = TestClient(app).get("/api/v1/debug/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["pid"]
    assert payload["ppid"] is not None
    assert payload["environment"]
    assert "database_ready" in payload
    assert "uptime" in payload
    assert "db_pool_settings" in payload
    if not database.settings.is_sqlite:
        assert payload["db_pool_settings"]["pool_size"] == 3
