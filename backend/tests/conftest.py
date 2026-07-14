# ruff: noqa: E402  # Env muss vor dem App-Import stehen.
import os
import pathlib
import tempfile

# Vor jedem App-Import: auf eine temporäre SQLite-DB umbiegen.
# Env-Variablen haben Vorrang vor der .env-Datei.
_db = pathlib.Path(tempfile.gettempdir()) / "smierx_queue_test.db"
if _db.exists():
    _db.unlink()
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_db}"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
