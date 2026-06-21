import os
import pytest
import config
import models


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'test.db')
    monkeypatch.setattr(config, 'DATABASE_PATH', db_path)
    models.init_db()
    yield db_path
