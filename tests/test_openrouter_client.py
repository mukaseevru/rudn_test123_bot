import json
import responses
from importlib import reload
import pytest

@responses.activate
def test_chat_once_ok_headers_and_body(openrouter_module, monkeypatch):
    chat_once = openrouter_module.chat_once
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {"id": "cmpl_1", "choices": [{"message": {"content": "OK"}}]}
    responses.add(responses.POST, url, json=payload, status=200)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    openrouter_module = reload(openrouter_module)  # перечитает ключ
    chat_once = openrouter_module.chat_once

    text, ms = chat_once(
        messages=[{"role": "user", "content": "ping"}],
        model="mistralai/mistral-small-24b-instruct-2501:free",
        temperature=0.2,
        max_tokens=32,
        timeout_s=5,
    )
    assert text == "OK"
    # Проверяем отправленное тело
    sent = json.loads(responses.calls[0].request.body.decode())
    assert sent["model"].endswith(":free")
    assert sent["messages"][0]["role"] == "user"
    assert "temperature" in sent and "max_tokens" in sent
    # и заголовки
    hdrs = responses.calls[0].request.headers
    assert hdrs["Content-Type"] == "application/json"
    assert hdrs["Authorization"] == "Bearer test-key"

@responses.activate
def test_chat_once_errors_map_to_exception(openrouter_module, monkeypatch):
    chat_once = openrouter_module.chat_once
    OpenRouterError = openrouter_module.OpenRouterError

    url = "https://openrouter.ai/api/v1/chat/completions"
    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    responses.add(responses.POST, url, json={"error":"bad"}, status=401)

    try:
        chat_once(messages=[{"role":"user","content":"x"}],
                  model="meta-llama/llama-3.1-8b-instruct:free",
                  temperature=0.2,max_tokens=16,timeout_s=3)
        assert False, "Ожидалось исключение при 401"
    except OpenRouterError as e:
        assert "401" in str(e)

    responses.reset()
    responses.add(responses.POST, url, json={"error":"bad"}, status=429)
    try:
        chat_once(messages=[{"role":"user","content":"x"}],
                  model="meta-llama/llama-3.1-8b-instruct:free",
                  temperature=0.2,max_tokens=16,timeout_s=3)
        assert False
    except OpenRouterError as e:
        assert "429" in str(e)

@responses.activate
def test_chat_once_5xx_raises_openrouter_error(openrouter_module, monkeypatch):
    """
    При статусе 5xx клиент должен выбрасывать OpenRouterError
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    responses.add(
        responses.POST,
        url,
        json={"error": "server down"},
        status=503,
    )

    # Обновляем окружение и перечитываем модуль
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    openrouter = reload(openrouter_module)

    chat_once = openrouter.chat_once
    OpenRouterError = openrouter.OpenRouterError

    with pytest.raises(OpenRouterError) as excinfo:
        chat_once(
            messages=[{"role": "user", "content": "ping"}],
            model="meta-llama/llama-3.1-8b-instruct:free",
            temperature=0.1,
            max_tokens=16,
            timeout_s=3,
        )

    err = excinfo.value
    assert err.status == 503
    assert "Сервис недоступен" in str(err)

