import importlib
import pytest

@pytest.fixture()
def tmp_db_path(tmp_path):
    """
    Путь к временной БД
    """
    return str((tmp_path / "bot_test.db").absolute())

@pytest.fixture()
def db_module(tmp_db_path, monkeypatch):
    """
    Поднимаем чистую БД в temp-файле
    """
    db = importlib.import_module("db")
    # на случай, если DB_PATH читается из config:
    monkeypatch.setattr(db, "DB_PATH", tmp_db_path, raising=False)
    db.init_db()
    return db

@pytest.fixture()
def main_module(db_module, monkeypatch):
    """
    Импортируем main.py
    """
    main = importlib.import_module("main")
    return main

@pytest.fixture()
def openrouter_module():
    """
    Импортируем openrouter_client.py
    """
    return importlib.import_module("openrouter_client")
