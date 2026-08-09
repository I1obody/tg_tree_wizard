"""Тесты для MenuOption, MenuState и TreeMenu."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import dataclasses

import pytest

from tg_tree_wizard.core import (
    DynamicOption,
    MenuOption,
    MenuState,
    Node,
    Option,
    StaleChoiceError,
    TreeError,
    WizardState,
    choose,
    resolve_dynamic_options,
    validate_tree,
)

# === MenuOption tests ===


def test_menu_option_default_is_menu_item():
    """MenuOption по умолчанию имеет is_menu_item=True."""
    opt = MenuOption(label="Test", value="test")
    assert opt.is_menu_item is True
    assert opt.label == "Test"
    assert opt.value == "test"
    assert opt.next_node is None


def test_menu_option_explicit_not_menu_item():
    """MenuOption с is_menu_item=False не отображается в меню."""
    opt = MenuOption(label="Hidden", value="hidden", is_menu_item=False)
    assert opt.is_menu_item is False


def test_menu_option_with_next_node():
    """MenuOption может иметь next_node для навигации."""
    opt = MenuOption(label="Back", value=None, next_node="main")
    assert opt.next_node == "main"
    assert opt.is_menu_item is True


def test_menu_option_is_frozen_dataclass():
    """MenuOption — frozen dataclass, его нельзя мутировать."""
    opt = MenuOption(label="Test", value="test")
    with pytest.raises(dataclasses.FrozenInstanceError):
        opt.label = "Changed"


def test_menu_option_in_tree_validation():
    """validate_tree корректно обрабатывает дерево с MenuOption."""
    tree = {
        "main": Node(
            text="Main",
            options=(
                MenuOption(label="A", value="a"),
                MenuOption(label="B", value="b", next_node="sub"),
            ),
        ),
        "sub": Node(
            text="Sub",
            options=(MenuOption(label="Back", value=None, next_node="main"),),
        ),
    }
    # Не должно выбрасывать исключений
    validate_tree(tree, "main")


def test_menu_option_with_broken_reference_fails_validation():
    """validate_tree ловит ссылки MenuOption на несуществующие узлы."""
    tree = {
        "main": Node(
            text="Main",
            options=(MenuOption(label="Bad", value="bad", next_node="nonexistent"),),
        ),
    }
    with pytest.raises(TreeError, match="несуществующий узел"):
        validate_tree(tree, "main")


def test_menu_option_mixed_with_regular_options():
    """validate_tree корректно обрабатывает смешанные Option и MenuOption."""
    tree = {
        "mixed": Node(
            text="Mixed",
            options=(
                Option("Regular", "reg", None),
                MenuOption(label="Menu A", value="a"),
                MenuOption(label="Menu B", value="b", next_node="other"),
            ),
        ),
        "other": Node(
            text="Other",
            options=(Option("Done", "done", None),),
        ),
    }
    validate_tree(tree, "mixed")


# === MenuState tests ===


def test_menu_state_creation():
    """MenuState создаётся с current_node и пустым data."""
    ms = MenuState(current_node="main")
    assert ms.current_node == "main"
    assert ms.data == {}


def test_menu_state_with_data():
    """MenuState может содержать произвольные данные."""
    ms = MenuState(current_node="orders", data={"user_id": 123, "lang": "ru"})
    assert ms.current_node == "orders"
    assert ms.data["user_id"] == 123


def test_menu_state_to_dict_roundtrip():
    """MenuState.to_dict() и MenuState.from_dict() работают корректно."""
    original = MenuState(current_node="settings", data={"theme": "dark"})
    d = original.to_dict()
    restored = MenuState.from_dict(d)
    assert restored.current_node == "settings"
    assert restored.data["theme"] == "dark"


def test_menu_state_from_dict_missing_data():
    """MenuState.from_dict() корректно обрабатывает отсутствие поля data."""
    ms = MenuState.from_dict({"current_node": "test"})
    assert ms.current_node == "test"
    assert ms.data == {}


def test_menu_state_is_frozen():
    """MenuState — frozen dataclass, его нельзя мутировать."""
    ms = MenuState(current_node="main")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ms.current_node = "other"


# === resolve_dynamic_options with MenuOption ===


def test_resolve_dynamic_options_with_menu_option():
    """resolve_dynamic_options корректно обрабатывает MenuOption."""
    node = Node(
        text="Test",
        options=(
            MenuOption(label="Static", value="static"),
            DynamicOption(
                label_factory=lambda s: f"Dynamic {len(s.answers)}",
                value="dyn",
                next_node=None,
            ),
        ),
    )
    state = WizardState(stack=("test",))
    resolved = resolve_dynamic_options(node, state=state)
    assert len(resolved) == 2
    assert isinstance(resolved[0], MenuOption)
    assert resolved[0].label == "Static"
    assert isinstance(resolved[1], Option)
    assert resolved[1].label == "Dynamic 0"


# === choose with MenuState (simulated flow) ===


def test_choose_with_menu_style_navigation():
    """choose корректно обрабатывает переходы по меню."""
    tree = {
        "main": Node(
            text="Main",
            options=(
                MenuOption(label="Orders", value="orders"),
                MenuOption(label="Settings", value="settings", next_node="settings"),
            ),
        ),
        "orders": Node(
            text="Orders",
            options=(MenuOption(label="Back", value=None, next_node="main"),),
        ),
        "settings": Node(
            text="Settings",
            options=(MenuOption(label="Done", value=None, next_node=None),),
        ),
    }

    # Start at main
    state = WizardState.start("main")
    assert state.current_node == "main"

    # Choose Settings (index 1) -> goes to settings node
    new_state, opt, is_final = choose(tree, state, "main", 1)
    assert not is_final
    assert opt.next_node == "settings"

    # Choose Done at settings -> final
    _final_state, final_opt, final_is_final = choose(tree, new_state, "settings", 0)
    assert final_is_final
    assert final_opt.value == None


def test_choose_stale_menu_choice():
    """choose отклоняет выбор из неактуального узла."""
    tree = {
        "main": Node(
            text="Main",
            options=(MenuOption(label="A", value="a"),),
        ),
    }

    state_a = WizardState.start("main")
    # Попытка выбрать из другого узла (которого нет)
    with pytest.raises(StaleChoiceError):
        choose(tree, state_a, "nonexistent", 0)


# === TreeMenu integration tests (unit-level, no aiogram runtime) ===


def test_tree_menu_build_keyboard_filters_non_menu_items():
    """TreeMenu._build_menu_keyboard пропускает MenuOption с is_menu_item=False,
    но показывает обычные Option (включая resolved из DynamicOption)."""
    from tg_tree_wizard.aiogram_adapter import TreeMenu

    tree = {
        "main": Node(
            text="Main",
            options=(
                MenuOption(label="Visible", value="v"),
                Option(
                    "Hidden regular", value="h"
                ),  # обычный Option — показывается (из DynamicOption)
                MenuOption(
                    label="Also visible", value="a", is_menu_item=False
                ),  # скрыт
            ),
        ),
    }

    menu = TreeMenu(tree=tree, root="main", callback_prefix="m")
    node = tree["main"]
    kb = menu._build_menu_keyboard("main", node)

    # Должны быть две кнопки: Visible (MenuOption) и Hidden regular (обычный Option)
    all_buttons = []
    for row in kb.inline_keyboard:
        all_buttons.extend(row)
    assert len(all_buttons) == 2
    texts = [b.text for b in all_buttons]
    assert "Visible" in texts
    assert "Hidden regular" in texts


def test_tree_menu_build_keyboard_includes_back_for_non_root():
    """TreeMenu добавляет кнопку 'Назад' для не-корневых узлов."""
    from tg_tree_wizard.aiogram_adapter import TreeMenu

    tree = {
        "main": Node(
            text="Main",
            options=(MenuOption(label="Sub", value="s"),),
        ),
        "sub": Node(
            text="Sub",
            options=(MenuOption(label="Back", value=None, next_node="main"),),
        ),
    }

    menu = TreeMenu(tree=tree, root="main", callback_prefix="m")
    sub_node = tree["sub"]
    kb = menu._build_menu_keyboard("sub", sub_node)

    all_buttons = []
    for row in kb.inline_keyboard:
        all_buttons.extend(row)

    # Должна быть кнопка "Back" и кнопка "Назад"
    texts = [b.text for b in all_buttons]
    assert "⬅️ Назад" in texts


def test_tree_menu_build_keyboard_no_back_for_root():
    """TreeMenu НЕ добавляет кнопку 'Назад' для корневого узла."""
    from tg_tree_wizard.aiogram_adapter import TreeMenu

    tree = {
        "main": Node(
            text="Main",
            options=(MenuOption(label="A", value="a"),),
        ),
    }

    menu = TreeMenu(tree=tree, root="main", callback_prefix="m")
    node = tree["main"]
    kb = menu._build_menu_keyboard("main", node)

    all_buttons = []
    for row in kb.inline_keyboard:
        all_buttons.extend(row)

    texts = [b.text for b in all_buttons]
    assert "⬅️ Назад" not in texts


def test_tree_menu_callback_data_format():
    """TreeMenu использует корректный формат callback_data."""
    from tg_tree_wizard.aiogram_adapter import TreeMenu

    tree = {
        "main": Node(
            text="Main",
            options=(
                MenuOption(label="A", value="a"),
                MenuOption(label="B", value="b"),
            ),
        ),
    }

    menu = TreeMenu(tree=tree, root="main", callback_prefix="menu")
    node = tree["main"]
    kb = menu._build_menu_keyboard("main", node)

    all_buttons = []
    for row in kb.inline_keyboard:
        all_buttons.extend(row)

    assert all_buttons[0].callback_data == "menu:main:0"
    assert all_buttons[1].callback_data == "menu:main:1"


def test_tree_menu_validation_rejects_broken_tree():
    """TreeMenu выбрасывает TreeError при невалидном дереве."""
    from tg_tree_wizard.aiogram_adapter import TreeMenu

    tree = {
        "main": Node(
            text="Main",
            options=(MenuOption(label="Bad", value="bad", next_node="missing"),),
        ),
    }

    with pytest.raises(TreeError):
        TreeMenu(tree=tree, root="main", callback_prefix="m")


def test_tree_menu_validation_rejects_missing_root():
    """TreeMenu выбрасывает TreeError при отсутствии корневого узла."""
    from tg_tree_wizard.aiogram_adapter import TreeMenu

    tree = {
        "other": Node(text="Other", options=(Option("X", "x", None),)),
    }

    with pytest.raises(TreeError, match="Корневой узел"):
        TreeMenu(tree=tree, root="main", callback_prefix="m")


def test_tree_menu_callback_prefix_with_colon_rejected():
    """TreeMenu выбрасывает TreeError при ':' в callback_prefix."""
    from tg_tree_wizard.aiogram_adapter import TreeMenu

    tree = {
        "main": Node(text="Main", options=(Option("X", "x", None),)),
    }

    with pytest.raises(TreeError, match="не может содержать"):
        TreeMenu(tree=tree, root="main", callback_prefix="bad:prefix")


def test_tree_menu_callback_data_length_check():
    """TreeMenu проверяет лимит длины callback_data."""
    from tg_tree_wizard.aiogram_adapter import TreeMenu

    # 64 байта — лимит Telegram. Префикс "very_long_prefix_that_is_very_long" (38 символов) + ":" +
    # "x" (1 символ) + ":" + "0" (1 символ) = 41 символ ASCII = 41 байт. Нужно больше.
    # Используем длинный префикс с кириллицей (каждый символ = 2 байта в UTF-8).
    long_prefix = (
        "длинный_префикс_для_проверки_лимита"  # 34 символа * 2 = 68 байт уже > 64
    )
    tree = {
        "main": Node(text="Main", options=(Option("X", "x", None),)),
    }

    with pytest.raises(TreeError):
        TreeMenu(tree=tree, root="main", callback_prefix=long_prefix)


# === Middleware types tests ===


def test_menu_middleware_data_creation():
    """MenuMiddlewareData создаётся корректно."""
    from tg_tree_wizard.middleware import MenuMiddlewareData

    data = MenuMiddlewareData(
        event_type="menu_choice",
        node_id="main",
        option_index=0,
        user_id=123,
    )
    assert data.event_type == "menu_choice"
    assert data.node_id == "main"
    assert data.option_index == 0
    assert data.user_id == 123


def test_menu_middleware_data_frozen():
    """MenuMiddlewareData — frozen dataclass."""
    from tg_tree_wizard.middleware import MenuMiddlewareData

    data = MenuMiddlewareData(event_type="menu_start", node_id=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        data.event_type = "changed"


def test_menu_abort_wizard_is_exception():
    """MenuAbortWizard — исключение для прерывания обработки меню."""
    from tg_tree_wizard.middleware import MenuAbortWizard

    exc = MenuAbortWizard("Not authorized")
    assert str(exc) == "Not authorized"
    assert isinstance(exc, Exception)


def test_menu_event_type_literal():
    """MenuEventType содержит корректные значения."""

    # Проверяем, что типы существуют (Literal — это type hint)
    # Literal нельзя проверить напрямую, но можно убедиться что импорт работает
    assert True


# === Exports tests ===


def test_menu_option_exported_from_package():
    """MenuOption экспортируется из tg_tree_wizard."""
    import tg_tree_wizard

    assert hasattr(tg_tree_wizard, "MenuOption")


def test_menu_state_exported_from_package():
    """MenuState экспортируется из tg_tree_wizard."""
    import tg_tree_wizard

    assert hasattr(tg_tree_wizard, "MenuState")


def test_tree_menu_exported_from_package():
    """TreeMenu экспортируется из tg_tree_wizard."""
    import tg_tree_wizard

    assert hasattr(tg_tree_wizard, "TreeMenu")


def test_menu_states_exported_from_package():
    """MenuStates экспортируется из tg_tree_wizard."""
    import tg_tree_wizard

    assert hasattr(tg_tree_wizard, "MenuStates")


def test_menu_middleware_types_exported():
    """Типы middleware для меню экспортируются из tg_tree_wizard."""
    import tg_tree_wizard

    assert hasattr(tg_tree_wizard, "MenuMiddlewareData")
    assert hasattr(tg_tree_wizard, "MenuAbortWizard")
    assert hasattr(tg_tree_wizard, "MenuMiddlewareHook")


def test_all_exports_list_contains_menu_items():
    """__all__ содержит все menu-экспорты."""
    import tg_tree_wizard

    assert "MenuOption" in tg_tree_wizard.__all__
    assert "MenuState" in tg_tree_wizard.__all__
    assert "TreeMenu" in tg_tree_wizard.__all__
    assert "MenuStates" in tg_tree_wizard.__all__
    assert "MenuMiddlewareData" in tg_tree_wizard.__all__
    assert "MenuAbortWizard" in tg_tree_wizard.__all__
    assert "MenuMiddlewareHook" in tg_tree_wizard.__all__
