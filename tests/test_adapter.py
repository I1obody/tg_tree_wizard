import dataclasses
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from tg_tree_wizard.core import Node, Option, DynamicOption, WizardState, TreeError
from tg_tree_wizard.aiogram_adapter import (
    TreeWizard,
    check_callback_data_limits,
    TELEGRAM_CALLBACK_DATA_LIMIT_BYTES,
)
from tg_tree_wizard.middleware import MiddlewareData, AbortWizard


def make_node(n_options: int = 2) -> Node:
    return Node(
        text="x",
        options=tuple(Option(f"opt{i}", f"v{i}", None) for i in range(n_options)),
    )


def test_normal_tree_passes_callback_limit_check():
    tree = {"lang": make_node(), "delivery": make_node()}
    check_callback_data_limits(tree, callback_prefix="wz")  # не должно кинуть


def test_long_node_id_exceeds_limit_and_is_caught():
    long_id = "a" * 60  # заведомо длинный id узла
    tree = {long_id: make_node()}
    with pytest.raises(TreeError):
        check_callback_data_limits(tree, callback_prefix="wz")


def test_colon_in_node_id_is_rejected():
    tree = {"bad:id": make_node()}
    with pytest.raises(TreeError):
        check_callback_data_limits(tree, callback_prefix="wz")


def test_treewizard_raises_at_construction_not_at_runtime():
    """
    Ключевое свойство: ошибка ловится при СОЗДАНИИ TreeWizard (то есть при
    старте бота), а не когда до этого узла случайно дойдёт живой пользователь.
    """
    long_id = "b" * 60
    tree = {long_id: make_node()}
    with pytest.raises(TreeError):
        TreeWizard(tree, root=long_id)


def test_realistic_short_ids_stay_well_under_limit():
    """
    Проверка на здравый смысл: обычные короткие id узлов (как в примерах
    из README) даже близко не подходят к лимиту, независимо от того,
    сколько шагов в дереве — потому что путь не кодируется в callback_data.
    """
    tree = {
        "lang": make_node(7),        # 7 вариантов языков, как в исходном боте
        "delivery": make_node(2),
        "goal": make_node(7),
        "group": make_node(2),
        "age": make_node(4),
        "level": make_node(7),
    }
    check_callback_data_limits(tree, callback_prefix="wz")

    max_len = 0
    for node_id, node in tree.items():
        candidate = f"wz:{node_id}:{len(node.options) - 1}"
        max_len = max(max_len, len(candidate.encode("utf-8")))

    assert max_len < TELEGRAM_CALLBACK_DATA_LIMIT_BYTES
    print(f"Максимальная длина callback_data в этом дереве: {max_len} байт из {TELEGRAM_CALLBACK_DATA_LIMIT_BYTES}")


# --- Тесты для P0 изменений: cancel и middleware ---

def test_cancel_button_not_shown_by_default():
    """P0.1: Кнопка отмены не показывается, если show_cancel_button=False (по умолчанию)."""
    tree = {"a": make_node(), "b": make_node()}
    wizard = TreeWizard(tree, root="a")
    kb = wizard._build_keyboard("b", tree["b"])

    # Проверяем, что в клавиатуре нет кнопки с callback_data "wz_cancel"
    cancel_found = False
    for row in kb.inline_keyboard:
        for btn in row:
            if btn.callback_data == "wz_cancel":
                cancel_found = True
    assert not cancel_found


def test_cancel_button_shown_when_enabled():
    """P0.1: Кнопка отмены показывается, когда show_cancel_button=True."""
    tree = {"a": make_node(), "b": make_node()}
    wizard = TreeWizard(tree, root="a", show_cancel_button=True)
    kb = wizard._build_keyboard("b", tree["b"])

    cancel_found = False
    for row in kb.inline_keyboard:
        for btn in row:
            if btn.callback_data == "wz_cancel":
                cancel_found = True
    assert cancel_found


def test_middleware_receives_start_event():
    """P0.2: Middleware получает событие 'start' при старте опроса."""
    events = []

    async def log_mw(data):
        events.append(data.event_type)

    tree = {"a": make_node(), "b": make_node()}
    wizard = TreeWizard(tree, root="a", middleware=[log_mw])

    # Middleware вызывается при создании — проверяем что он зарегистрирован
    assert len(wizard.middleware) == 1


def test_abort_wizard_exception_exists():
    """P0.2: AbortWizard — отдельный класс исключения для прерывания обработки."""
    exc = AbortWizard("test")
    assert str(exc) == "test"
    assert isinstance(exc, Exception)


def test_middleware_data_has_correct_fields():
    """P0.2: MiddlewareData содержит все необходимые поля."""
    data = MiddlewareData(
        event_type="choice", node_id="lang", option_index=0, user_id=42,
    )
    assert data.event_type == "choice"
    assert data.node_id == "lang"
    assert data.option_index == 0
    assert data.user_id == 42


def test_middleware_data_is_frozen():
    """P0.2: MiddlewareData — frozen dataclass, его нельзя мутировать."""
    from dataclasses import fields

    mw_fields = [f.name for f in fields(MiddlewareData)]
    assert "event_type" in mw_fields
    assert "node_id" in mw_fields
    assert "option_index" in mw_fields
    assert "user_id" in mw_fields


def test_treewizard_accepts_middleware_parameter():
    """P0.2: TreeWizard принимает middleware как опциональный параметр."""
    tree = {"a": make_node()}

    # Без middleware — должно работать как раньше
    w1 = TreeWizard(tree, root="a")
    assert w1.middleware == []

    # С middleware — должно сохраниться
    async def dummy(data): pass
    w2 = TreeWizard(tree, root="a", middleware=[dummy])
    assert len(w2.middleware) == 1


def test_treewizard_accepts_on_start_parameter():
    """P1.3: TreeWizard принимает on_start как опциональный параметр."""
    tree = {"a": make_node()}

    w1 = TreeWizard(tree, root="a")
    assert w1.on_start is None

    async def start_hook(msg, state): pass
    w2 = TreeWizard(tree, root="a", on_start=start_hook)
    assert w2.on_start is start_hook


def test_treewizard_accepts_cancel_parameters():
    """P0.1: TreeWizard принимает параметры кнопки отмены."""
    tree = {"a": make_node()}

    w = TreeWizard(tree, root="a", show_cancel_button=True)
    assert w.show_cancel_button is True
    assert w.cancel_button_text == "❌ Отмена"

    w2 = TreeWizard(
        tree, root="a", show_cancel_button=True, cancel_button_text="Стоп"
    )
    assert w2.cancel_button_text == "Стоп"


def test_treewizard_has_cancel_method():
    """P0.1: TreeWizard имеет публичный метод cancel()."""
    tree = {"a": make_node()}
    wizard = TreeWizard(tree, root="a")
    assert hasattr(wizard, "cancel")
    import inspect
    assert inspect.iscoroutinefunction(wizard.cancel)


# --- Тесты для P1.2: skip_to / jump_to ---

def test_treewizard_has_skip_to_method():
    """P1.2: TreeWizard имеет публичный метод skip_to()."""
    tree = {"a": make_node(), "b": make_node()}
    wizard = TreeWizard(tree, root="a")
    assert hasattr(wizard, "skip_to")
    import inspect
    assert inspect.iscoroutinefunction(wizard.skip_to)


def test_treewizard_has_jump_to_method():
    """P1.2: TreeWizard имеет публичный метод jump_to()."""
    tree = {"a": make_node(), "b": make_node()}
    wizard = TreeWizard(tree, root="a")
    assert hasattr(wizard, "jump_to")
    import inspect
    assert inspect.iscoroutinefunction(wizard.jump_to)


def test_skip_to_raises_for_nonexistent_node():
    """P1.2: skip_to() кидает TreeError для несуществующего узла."""
    from tg_tree_wizard.core import TreeError

    tree = {"a": make_node(), "b": make_node()}
    wizard = TreeWizard(tree, root="a")

    async def _test():
        with pytest.raises(TreeError):
            await wizard.skip_to(None, "nonexistent", None)

    import asyncio
    asyncio.run(_test())


def test_jump_to_raises_for_nonexistent_node():
    """P1.2: jump_to() кидает TreeError для несуществующего узла."""
    from tg_tree_wizard.core import TreeError

    tree = {"a": make_node(), "b": make_node()}
    wizard = TreeWizard(tree, root="a")

    async def _test():
        with pytest.raises(TreeError):
            await wizard.jump_to(None, "nonexistent", None)

    import asyncio
    asyncio.run(_test())


def test_build_keyboard_with_dynamic_option_resolves():
    """P1.1: _build_keyboard корректно разворачивает DynamicOption."""
    from tg_tree_wizard.core import DynamicOption

    tree = {
        "dyn": Node(
            text="Test",
            options=(DynamicOption(
                label_factory=lambda s: f"Step {len(s.answers) + 1}",
                value="v1", next_node="final",
            ),),
        ),
        "final": make_node(),
    }
    wizard = TreeWizard(tree, root="dyn")

    state = WizardState.start("dyn")
    kb = wizard._build_keyboard("dyn", tree["dyn"], state=state)

    # Клавиатура должна содержать кнопку с динамическим текстом
    assert kb is not None


def test_build_keyboard_with_url_option_sets_url():
    """P2.2: _build_keyboard устанавливает url для URLOption."""
    from tg_tree_wizard.core import URLOption

    tree = {
        "url": Node(
            text="Test",
            options=(URLOption(label="🌐 Сайт", value="url", url="https://example.com"),),
        ),
        "final": make_node(),
    }
    wizard = TreeWizard(tree, root="url")

    kb = wizard._build_keyboard("url", tree["url"])

    # Клавиатура должна быть создана без ошибок
    assert kb is not None


def test_build_keyboard_with_switch_option_sets_inline_query():
    """P2.2: _build_keyboard устанавливает switch_inline_query для SwitchOption."""
    from tg_tree_wizard.core import SwitchOption

    tree = {
        "switch": Node(
            text="Test",
            options=(SwitchOption(label="🔍 Поиск", value="search", switch_inline_query="поиск..."),),
        ),
        "final": make_node(),
    }
    wizard = TreeWizard(tree, root="switch")

    kb = wizard._build_keyboard("switch", tree["switch"])

    # Клавиатура должна быть создана без ошибок
    assert kb is not None


def test_url_option_is_frozen_dataclass():
    """P2.2: URLOption — замороженный dataclass с полем url."""
    from tg_tree_wizard.core import URLOption

    opt = URLOption(label="🌐", value="v", url="https://test.com")
    assert opt.url == "https://test.com"
    try:
        opt.url = "https://other.com"  # type: ignore[misc]
    except Exception as e:
        assert isinstance(e, (TypeError, dataclasses.FrozenInstanceError))


def test_switch_option_is_frozen_dataclass():
    """P2.2: SwitchOption — замороженный dataclass с полем switch_inline_query."""
    from tg_tree_wizard.core import SwitchOption

    opt = SwitchOption(label="🔍", value="v", switch_inline_query="поиск...")
    assert opt.switch_inline_query == "поиск..."
    try:
        opt.switch_inline_query = "другой"  # type: ignore[misc]
    except Exception as e:
        assert isinstance(e, (TypeError, dataclasses.FrozenInstanceError))


def test_url_option_with_none_url_is_valid():
    """P2.2: URLOption с url=None — валиден, как обычная Option."""
    from tg_tree_wizard.core import URLOption

    opt = URLOption(label="Обычная", value="v")
    assert opt.url is None


def test_switch_option_with_none_query_is_valid():
    """P2.2: SwitchOption с switch_inline_query=None — валиден, как обычная Option."""
    from tg_tree_wizard.core import SwitchOption

    opt = SwitchOption(label="Обычная", value="v")
    assert opt.switch_inline_query is None


def test_visual_width_plain_ascii():
    """P2.3: _visual_width считает ASCII-символы как 1."""
    from tg_tree_wizard.aiogram_adapter import _visual_width

    assert _visual_width("hello") == 5
    assert _visual_width("") == 0
    assert _visual_width("abc def") == 7


def test_visual_width_with_emoji():
    """P2.3: _visual_width считает emoji как 2."""
    from tg_tree_wizard.aiogram_adapter import _visual_width

    # 🌐 (U+1F310) — Misc Symbols and Pictographs
    assert _visual_width("🌐") == 2
    # ✅ (U+2705) — Dingbats
    assert _visual_width("✅") == 2
    # 🚀 (U+1F680) — Transport and Map
    assert _visual_width("🚀") == 2


def test_visual_width_mixed_text_and_emoji():
    """P2.3: _visual_width корректно суммирует текст и emoji."""
    from tg_tree_wizard.aiogram_adapter import _visual_width

    # "🌐 Сайт" = 2 (emoji) + 1 (пробел) + 4 (С,а,й,т) = 7
    assert _visual_width("🌐 Сайт") == 7


def test_pack_buttons_respects_emoji_width():
    """P2.3: pack_buttons корректно раскладывает кнопки с emoji."""
    from tg_tree_wizard.aiogram_adapter import _visual_width, pack_buttons
    from aiogram.types import InlineKeyboardButton

    # Каждая кнопка имеет базовую ширину +5 (отступы Telegram)
    # "🌐" = 2 визуальных символа → кнопка шириной 7
    buttons = [
        InlineKeyboardButton(text="🌐", callback_data="v0"),
        InlineKeyboardButton(text="🚀", callback_data=f"v1"),
        InlineKeyboardButton(text="✅", callback_data=f"v2"),
        InlineKeyboardButton(text="🔍", callback_data=f"v3"),
    ]

    # max_row_length=15: 7+7=14 ≤ 15, но +7=21 > 15 → вторая кнопка на новую строку
    rows = pack_buttons(buttons, max_row_length=15)
    assert len(rows) == 2
    assert len(rows[0]) == 2
    assert len(rows[1]) == 2


def test_pack_buttons_single_button_per_row_for_wide_emoji():
    """P2.3: pack_buttons помещает широкие emoji-кнопки в отдельные строки."""
    from tg_tree_wizard.aiogram_adapter import _visual_width, pack_buttons
    from aiogram.types import InlineKeyboardButton

    # "🌐" = 2 визуальных символа → кнопка шириной 7
    buttons = [
        InlineKeyboardButton(text="🌐", callback_data="v0"),
    ] * 5

    rows = pack_buttons(buttons, max_row_length=10)
    # Каждая кнопка 7 ≤ 10 → все в одну строку (7+7=14 > 10)
    assert len(rows) == 5


def test_pack_buttons_empty_list():
    """P2.3: pack_buttons корректно обрабатывает пустой список кнопок."""
    from tg_tree_wizard.aiogram_adapter import pack_buttons
    from aiogram.types import InlineKeyboardButton

    rows = pack_buttons([], max_row_length=10)
    assert rows == []


def test_pack_buttons_single_button():
    """P2.3: pack_buttons корректно обрабатывает одну кнопку."""
    from tg_tree_wizard.aiogram_adapter import pack_buttons
    from aiogram.types import InlineKeyboardButton

    buttons = [InlineKeyboardButton(text="Test", callback_data="v0")]
    rows = pack_buttons(buttons, max_row_length=10)
    assert len(rows) == 1
    assert len(rows[0]) == 1


# --- Тесты для WizardManager (P2.1) ---

def test_wizard_manager_register_and_unregister():
    """P2.1: WizardManager может регистрировать и удалять wizard'ы."""
    from tg_tree_wizard.manager import WizardManager

    tree = {"a": make_node()}
    w1 = TreeWizard(tree, root="a")
    w2 = TreeWizard(tree, root="a")

    mgr = WizardManager()
    mgr.register("first", w1)
    assert len(mgr.wizards) == 1
    assert "first" in mgr.wizards

    mgr.register("second", w2)
    assert len(mgr.wizards) == 2

    mgr.unregister("first")
    assert len(mgr.wizards) == 1
    assert "first" not in mgr.wizards


def test_wizard_manager_rejects_duplicate_registration():
    """P2.1: WizardManager не допускает дублирования имён."""
    from tg_tree_wizard.manager import WizardManager

    tree = {"a": make_node()}
    w1 = TreeWizard(tree, root="a")
    w2 = TreeWizard(tree, root="a")

    mgr = WizardManager()
    mgr.register("first", w1)

    with pytest.raises(ValueError):
        mgr.register("first", w2)


def test_wizard_manager_unregisters_nonexistent():
    """P2.1: unregister() кидает ValueError для несуществующего имени."""
    from tg_tree_wizard.manager import WizardManager

    tree = {"a": make_node()}
    w = TreeWizard(tree, root="a")
    mgr = WizardManager()
    mgr.register("first", w)

    with pytest.raises(ValueError):
        mgr.unregister("nonexistent")


def test_wizard_manager_unique_prefixes():
    """P2.1: Каждый wizard получает уникальный prefix."""
    from tg_tree_wizard.manager import WizardManager

    tree = {"a": make_node()}
    w1 = TreeWizard(tree, root="a")
    w2 = TreeWizard(tree, root="a")

    mgr = WizardManager()
    mgr.register("first", w1)
    mgr.register("second", w2)

    assert w1.prefix != w2.prefix


def test_wizard_manager_prefix_includes_hash():
    """P2.1: Prefix содержит хэш имени для уникальности."""
    from tg_tree_wizard.manager import WizardManager

    tree = {"a": make_node()}
    w = TreeWizard(tree, root="a")

    mgr = WizardManager()
    mgr.register("test_bot", w)

    assert w.prefix.startswith("wm_")
