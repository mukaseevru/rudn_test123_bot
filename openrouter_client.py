"""
Клиент взаимодействия с сервисом Openrouter
"""

from __future__ import annotations
import os, time, requests
from dataclasses import dataclass
from typing import Dict, List, Tuple
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

@dataclass
class OpenRouterError(Exception):
    status: int
    msg: str
    def __str__(self) -> str:
        return f"[{self.status}] {self.msg}"

def _friendly(status: int) -> str:
    return {
        400: "Неверный формат запроса.",
        401: "Ключ OpenRouter отклонён. Проверьте OPENROUTER_API_KEY.",
        403: "Нет прав доступа к модели.",
        404: "Эндпоинт не найден. Проверьте URL /api/v1/chat/completions.",
        429: "Превышены лимиты бесплатной модели. Попробуйте позднее.",
    }.get(status, "Сервис недоступен. Повторите попытку позже.")

def chat_once(messages: List[Dict], *,
              model: str,
              temperature: float = 0.2,
              max_tokens: int = 400,
              timeout_s: int = 30) -> Tuple[str, int]:
    if not OPENROUTER_API_KEY:
        raise OpenRouterError(401, "Отсутствует OPENROUTER_API_KEY (.env).")
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    t0 = time.perf_counter()
    r = requests.post(OPENROUTER_API, json=payload, headers=headers, timeout=timeout_s)
    dt_ms = int((time.perf_counter() - t0) * 1000)
    if r.status_code // 100 != 2:
        raise OpenRouterError(r.status_code, _friendly(r.status_code))
    try:
        data = r.json()
        text = data["choices"][0]["message"]["content"]
    except Exception:
        raise OpenRouterError(500, "Неожиданная структура ответа OpenRouter.")
    return text, dt_ms
