"""
Реестр метрик для бота.

Метрики хранятся в памяти процесса, без Prometheus и внешних систем.
Используются для команды /stats и простой диагностики.
"""

import threading
import time
import functools
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, Callable, TypeVar

T = TypeVar("T")

class Counter:
    """
    Простой счетчик.

    Пример использования:

        total = metric.counter("commands_total")
        total.inc()
        total.inc(5)

    Значения не сбрасываются автоматически при рестарте процесса.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.value = 0

    def inc(self, amount: int = 1) -> None:
        # Увеличить счетчик на amount (по умолчанию на 1)
        if amount < 0:
            raise ValueError("Ошибка при увеличении счетчика метрик: количество должно быть >= 0")
        self.value += amount

    def get(self) -> int:
        return self.value


@dataclass
class LatencyStats:
    """
    Статистика по задержке в миллисекундах.

    count    — сколько раз мы замерили время;
    total_ms — сумма всех задержек;
    min_ms   — минимальное значение;
    max_ms   — максимальное значение.
    """
    count: int = 0
    total_ms: int = 0
    min_ms: int = 0
    max_ms: int = 0

    def observe(self, ms: int) -> None:
        # Учесть одно измерение задержки
        if ms < 0:
            return
        if self.count == 0:
            self.min_ms = ms
            self.max_ms = ms
        else:
            self.min_ms = min(self.min_ms, ms)
            self.max_ms = max(self.max_ms, ms)
        self.count += 1
        self.total_ms += ms

    @property
    def avg_ms(self) -> float:
        # Средняя задержка в мс
        if self.count == 0:
            return 0.0
        return self.total_ms / self.count


class LatencyMetric:
    """
    Обертка для LatencyStats, чтобы иметь единообразный API

    Пример использования:

        metric.latency("openrouter_latency_ms").observe(500)
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.stats = LatencyStats()

    def observe(self, ms: int) -> None:
        self.stats.observe(ms)

    def snapshot(self) -> Dict[str, Any]:
        """
        Срез статистики для этой метрики

        Возвращает dict с полями:
        count, total_ms, min_ms, max_ms, avg_ms
        """
        data = asdict(self.stats)
        data["avg_ms"] = self.stats.avg_ms
        return data


class MetricsRegistry:
    """
    Реестр метрик

    Основное API:

        from metrics import metric

        metric.counter("commands_total").inc()
        metric.latency("openrouter_latency_ms").observe(812)

    и метод snapshot() для команды /stats
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, Counter] = {}
        self._latencies: Dict[str, LatencyMetric] = {}

    # --- Счетчики ---

    def counter(self, name: str) -> Counter:
        """
        Получить (или создать) счетчик с именем name.
        Если счетчик еще не зарегистрирован, создается новый.
        """
        with self._lock:
            c = self._counters.get(name)
            if c is None:
                c = Counter(name)
                self._counters[name] = c
            return c

    # --- Метрики задержки ---

    def latency(self, name: str) -> LatencyMetric:
        """
        Получить (или создать) метрику задержки с именем name.

        Если не было — создается новая.
        """
        with self._lock:
            m = self._latencies.get(name)
            if m is None:
                m = LatencyMetric(name)
                self._latencies[name] = m
            return m

    # --- Срез всех метрик ---

    def snapshot(self) -> Dict[str, Any]:
        """
        Вернуть все метрики в виде словаря:

        {
          "counters": {"commands_total": 10, ...},
          "latencies": {
             "openrouter_latency_ms": {
                 "count": ...,
                 "total_ms": ...,
                 "min_ms": ...,
                 "max_ms": ...,
                 "avg_ms": ...
             },
             "build_messages_ms": { ... },
             ...
          }
        }

        Используется для команды /stats.
        """
        with self._lock:
            counters = {name: c.get() for name, c in self._counters.items()}
            latencies = {
                name: metric.snapshot()
                for name, metric in self._latencies.items()
            }
        return {"counters": counters, "latencies": latencies}


# Глобальный реестр метрик
metric = MetricsRegistry()


def timed(metric_name: str, logger: logging.Logger | None = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Декоратор для замера времени выполнения функции.

    Пример:

        from metrics import metric, timed
        import logging

        log = logging.getLogger(__name__)

        @timed("build_messages_ms", logger=log)
        def build_messages(...):
            ...

    При каждом вызове:
    - замеряется время выполнения функции в миллисекундах
    - значение записывается в metric.latency(metric_name)
    - если передан logger, пишется DEBUG-запись со временем
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            t0 = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                dt_ms = int((time.perf_counter() - t0) * 1000)
                metric.latency(metric_name).observe(dt_ms)
                if logger is not None:
                    logger.debug("timed %s: %s ms", func.__qualname__, dt_ms)

        return wrapper

    return decorator
