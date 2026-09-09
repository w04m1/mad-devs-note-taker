"""Keep destructive integration fixtures on an explicitly isolated database."""

import os

import pytest
from sqlalchemy.engine import make_url

test_database_url = os.getenv("TEST_DATABASE_URL")
if test_database_url:
    database = make_url(test_database_url).database or ""
    if not any(token in database.lower() for token in ("test", "qa")):
        raise RuntimeError(
            "Refusing destructive integration tests: TEST_DATABASE_URL database name must contain test or qa"
        )
    os.environ["DATABASE_URL"] = test_database_url


_skipped_reports: list[str] = []


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if os.getenv("FAIL_ON_SKIP") == "1" and report.skipped:
        _skipped_reports.append(report.nodeid)


def pytest_sessionfinish(session: pytest.Session) -> None:
    if _skipped_reports:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_sep("=", "FAIL_ON_SKIP rejected skipped tests")
            for nodeid in _skipped_reports:
                reporter.write_line(nodeid)
