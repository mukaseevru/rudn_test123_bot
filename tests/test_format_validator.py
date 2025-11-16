import pytest

POINT_PREFIXES = (
    "1.", "2.", "3.", "4.", "5.", "6.",
    "1)", "2)", "3)", "4)", "5)", "6)", "- ",
)

def validate_formatted_answer(
        text: str,
        min_points: int = 3,
        max_points: int = 5,
        max_intro_words: int = 12) -> bool:
    """
    Простая эвристика: есть короткое вступление (первая строка),
    есть 3–5 нумерованных пунктов, и есть короткий финальный вывод.
    """
    # 1) Разбить текст на непустые строки
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 3:
        return False

    # 2) Вступление: первая строка, не слишком длинная
    intro_words = len(lines[0].split())
    if intro_words == 0 or intro_words > max_intro_words:
        return False

    # 3) Пункты: строки между первой и последней, начинающиеся с префиксов
    points = [ln for ln in lines[1:-1] if ln.startswith(POINT_PREFIXES)]
    if not (min_points <= len(points) <= max_points):
        return False

    # 4) Вывод: последняя строка, не слишком длинная (<= 20 слов)
    return len(lines[-1].split()) <= 20

@pytest.mark.parametrize(
    "text, expected_ok, reason",
    [
        (
            "Краткое вступление.\n\n"
            "1. Первый пункт\n"
            "2. Второй пункт\n"
            "3. Третий пункт\n\n"
            "Короткий вывод.",
            True,
            "минимальный валидный случай (3 пункта)",
        ),
        (
            "Вступление без пунктов.\n\n"
            "Вывод один.",
            False,
            "нет нумерованных пунктов",
        ),
        (
            "Очень длинное вступление с большим количеством слов, "
            "которое должно провалить проверку, "
            "потому что оно превышает max_intro_words.\n\n"
            "1. Пункт\n"
            "2. Пункт\n"
            "3. Пункт\n\n"
            "Вывод.",
            False,
            "слишком длинное вступление",
        ),
        (
            "Вступление.\n\n"
            "1) Пункт\n"
            "2) Пункт\n\n"
            "Вывод.",
            False,
            "слишком мало пунктов (< min_points)",
        ),
        (
            "Вступление.\n\n"
            "1. Пункт\n"
            "2. Пункт\n"
            "3. Пункт\n"
            "4. Пункт\n"
            "5. Пункт\n"
            "6. Пункт\n\n"
            "Вывод.",
            False,
            "слишком много пунктов (> max_points)",
        ),
        (
            "Вступление.\n\n"
            "1. Пункт\n"
            "2. Пункт\n"
            "3. Пункт\n\n"
            "Это очень длинный вывод, который содержит существенно больше "
            "двадцати слов, потому что мы специально набиваем его лишними "
            "фразами, чтобы эвристика validate_formatted_answer посчитала "
            "его слишком длинным и отклонила формат ответа.",
            False,
            "слишком длинный вывод",
        ),
    ],
    ids=[
        "ok_3_points",
        "no_points",
        "too_long_intro",
        "too_few_points",
        "too_many_points",
        "too_long_outro",
    ],
)
def test_validate_formatted_answer_variants(text, expected_ok, reason):
    assert validate_formatted_answer(text) is expected_ok, reason