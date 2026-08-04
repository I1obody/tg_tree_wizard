"""
Менеджер для нескольких TreeWizard в одном боте (P2.1).

Позволяет зарегистрировать несколько wizard'ов и автоматически маршрутизировать
обновления к нужному экземпляру на основе callback_data / command prefix.
"""

from __future__ import annotations

import hashlib


class WizardManager:
    """Управляет несколькими TreeWizard в одном боте."""

    def __init__(self) -> None:
        self._wizards: dict[str, object] = {}

    def register(self, name: str, wizard: object) -> None:
        """Регистрирует wizard по имени.

        Имя используется для маршрутизации callback_data — каждый wizard
        имеет уникальный prefix, который автоматически генерируется как
        ``f"wm_{hash}_{wizard.prefix}"``.
        """
        if name in self._wizards:
            raise ValueError(f"Wizard с именем {name!r} уже зарегистрирован")

        # Генерируем уникальный prefix для каждого wizard чтобы избежать
        # коллизий callback_data между разными wizard'ами в одном боте.
        hash_prefix = hashlib.md5(name.encode()).hexdigest()[:6]
        original_prefix = getattr(wizard, "prefix", "wz")
        wizard.prefix = f"wm_{hash_prefix}_{original_prefix}"

        self._wizards[name] = wizard

    def unregister(self, name: str) -> None:
        """Удаляет зарегистрированный wizard."""
        if name not in self._wizards:
            raise ValueError(f"Wizard с именем {name!r} не найден")
        del self._wizards[name]

    @property
    def wizards(self) -> dict[str, object]:
        """Возвращает копию словаря зарегистрированных wizard'ов."""
        return dict(self._wizards)


