import pytest

def test_character_upsert(db_module):
    db = db_module
    # Предполагаем, что список персонажей уже есть. Берем любую существующую запись.
    characters = db.list_characters() if hasattr(db, "list_characters") else db.list_characters()
    assert characters, "Список персонажей пуст — проверь schema в db.py"
    any_id = characters[0]["id"]

    uid = 777001
    db.set_user_character(uid, any_id)
    p1 = db.get_user_character(uid)
    assert p1["id"] == any_id

    # Выберем другого персонажа и убедимся, что запись обновилась
    other_id = characters[-1]["id"] if characters[-1]["id"] != any_id else characters[1]["id"]
    db.set_user_character(uid, other_id)
    p2 = db.get_user_character(uid)
    assert p2["id"] == other_id

def test_models_single_active_switch(db_module):
    db = db_module
    models = db.list_models()
    assert len(models) >= 2, "Нужно >= 2 моделей в списке"
    a, b = models[0]["id"], models[1]["id"]

    # Сделать активной A
    db.set_active_model(a)
    act = db.get_active_model()
    assert act["id"] == a

    # Сделать активной B
    db.set_active_model(b)
    act2 = db.get_active_model()
    assert act2["id"] == b

    # Ровно одна активная
    with db._connect() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM models WHERE active=1").fetchone()[0]
    assert cnt == 1, "Должна быть ровно одна активная модель"

def test_set_active_model_rejects_unknown_id(db_module):
    db = db_module

    # Берем гарантированно несуществующий ID (например, очень большое число)
    unknown_id = 999999

    with pytest.raises(ValueError) as excinfo:
        db.set_active_model(unknown_id)

    # Сообщение об ошибке из db.py:
    assert "Неизвестный ID модели" in str(excinfo.value)

def test_get_user_character_falls_back_to_default(db_module):
    db = db_module

    # Берем пользователя, для которого мы точно ничего не записывали
    uid = 999001

    # Вызов без предварительного set_user_character
    ch = db.get_user_character(uid)

    # Ожидание: нам вернется существующий персонаж из таблицы characters
    all_chars = db.list_characters()
    assert all_chars, "Список персонажей пуст — проверь schema в db.py"

    ids = {c["id"] for c in all_chars}
    assert ch["id"] in ids, "get_user_character должен возвращать одного из существующих персонажей"
