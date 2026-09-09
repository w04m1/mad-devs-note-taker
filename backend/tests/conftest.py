"""Keep destructive integration fixtures on the explicitly selected database."""

import os

test_database_url = os.getenv("TEST_DATABASE_URL")
if test_database_url:
    os.environ["DATABASE_URL"] = test_database_url
