"""
Middleware-система для TreeWizard.

Позволяет добавлять логирование, rate-limiting, аутентификацию и другие
перекрёстные функции без форка библиотеки.

Пример:
    async def log_mw(data: MiddlewareData):
        print(f"[{data.event_type}] user={data.user_id} node={data.node_id}")

    wizard = TreeWizard(TREE, root=ROOT, middleware=[log_mw])
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

EventType = Literal["start", "choice", "back", "cancel", "finish", "transition_to_menu"]


@dataclass(frozen=True)
class MiddlewareData:
    """Данные, передаваемые в middleware-хук при каждом событии."""

    event_type: EventType
    node_id: str | None = None
    option_index: int | None = None
    user_id: int | None = None
    target_node: str | None = None
    shared_data: dict[str, Any] = field(default_factory=dict)


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


# === Menu middleware types (P1.2) ===

MenuEventType = Literal[
    "menu_start", "menu_choice", "menu_back", "transition_to_wizard"
]


@dataclass(frozen=True)
class MenuMiddlewareData:
    """Данные, передаваемые в middleware-хук при каждом событии меню."""

    event_type: MenuEventType
    node_id: str | None = None
    option_index: int | None = None
    user_id: int | None = None
    target_node: str | None = None
    shared_data: dict[str, Any] = field(default_factory=dict)


class MenuAbortWizard(Exception):
    """
    Поднимается middleware для прерывания обработки текущего события меню.

    Пример:
        async def auth_menu_mw(data: MenuMiddlewareData):
            if not is_authenticated(data.user_id):
                raise MenuAbortWizard("Не авторизован")
    """


# Тип middleware-функции для меню: принимает MenuMiddlewareData, ничего не возвращает.
MenuMiddlewareHook = Callable[[MenuMiddlewareData], Awaitable[None]]


# === Transition middleware types (P2) ===

TransitionEventType = Literal["transition_to_wizard", "transition_to_menu"]


@dataclass(frozen=True)
class TransitionMiddlewareData:
    """Данные, передаваемые в middleware-хук при переходе между меню и опросом."""

    event_type: TransitionEventType
    user_id: int | None = None
    source_state: str | None = None
    target_state: str | None = None
    shared_data: dict[str, Any] = field(default_factory=dict)


class TransitionAbort(Exception):
    """
    Поднимается middleware для прерывания перехода между меню и опросом.

    Пример:
        async def check_age_mw(data: TransitionMiddlewareData):
            if not data.shared_data.get("age_verified"):
                raise TransitionAbort("Возраст не подтверждён")
    """


TransitionMiddlewareHook = Callable[[TransitionMiddlewareData], Awaitable[None]]


class TransitionMiddleware:
    """
    Middleware для обработки переходов между меню и опросом.

    Пример использования:
        async def log_transitions(data: TransitionMiddlewareData):
            print(f"Переход: {data.source_state} -> {data.target_state}")

        wizard = TreeWizard(TREE, root=ROOT, transition_middleware=[log_transitions])
    """

    def __init__(self, hooks: list[TransitionMiddlewareHook] | None = None) -> None:
        self._hooks = hooks or []

    async def handle(self, data: TransitionMiddlewareData) -> None:
        """Вызывает все зарегистрированные хуки для перехода."""
        for hook in self._hooks:
            await hook(data)


def transition_middleware(
    *hooks: TransitionMiddlewareHook,
) -> TransitionMiddleware:
    """
    Фабрика для создания TransitionMiddleware из списка хуков.

    Пример:
        async def log_transitions(data: TransitionMiddlewareData):
            print(f"Переход: {data.source_state} -> {data.target_state}")

        wizard = TreeWizard(TREE, root=ROOT, transition_middleware=[
            transition_middleware(log_transitions)
        ])
    """
    return TransitionMiddleware(list(hooks))
