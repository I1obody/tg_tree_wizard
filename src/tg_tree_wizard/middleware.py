"""
Middleware-система для TreeWizard.

Позволяет добавлять логирование, rate-limiting, аутентификацию и другие
перекрёстные функции без форка библиотеки.

Пример:
    async def log_mw(data: MiddlewareData):
        print(f"[{data.event_type}] user={data.user_id} node={data.node_id}")

    wizard = TreeWizard(TREE, root=ROOT, middleware=[log_mw])
"""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal


EventType = Literal["start", "choice", "back", "cancel", "finish"]


@dataclass(frozen=True)
class MiddlewareData:
    """Данные, передаваемые в middleware-хук при каждом событии."""

    event_type: EventType
    node_id: str | None = None
    option_index: int | None = None
    user_id: int | None = None


class AbortWizard(Exception):
    """
    Поднимается middleware для прерывания обработки текущего события.

    Пример:
        async def auth_mw(data: MiddlewareData):
            if not is_authenticated(data.user_id):
                raise AbortWizard("Не авторизован")
    """


# Тип middleware-функции: принимает MiddlewareData, ничего не возвращает.
MiddlewareHook = Callable[[MiddlewareData], Awaitable[None]]
