import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from tg_tree_wizard.core import (
    linear_wizard,
    Node, Option, DynamicOption, WizardState, TreeError, StaleChoiceError,
    validate_tree, choose, go_back, resolve_dynamic_options,
)


# Небольшое тестовое дерево: язык -> формат -> финал
TREE = {
    "lang": Node(
        text="Выберите язык:",
        options=(
            Option("Английский", "en", "delivery"),
            Option("Немецкий", "de", "delivery"),
        ),
    ),
    "delivery": Node(
        text="Выберите формат:",
        options=(
            Option("Очно", "offline", None),
            Option("Онлайн", "online", None),
        ),
    ),
}


def test_valid_tree_passes_validation():
    validate_tree(TREE, root="lang")  # не должно кинуть исключение


def test_tree_with_missing_root_fails():
    with pytest.raises(TreeError):
        validate_tree(TREE, root="does_not_exist")


def test_tree_with_broken_reference_fails():
    broken = {
        "lang": Node(text="x", options=(Option("a", "a", "nowhere"),)),
    }
    with pytest.raises(TreeError):
        validate_tree(broken, root="lang")


def test_happy_path_reaches_final_and_records_answers():
    state = WizardState.start("lang")
    assert state.current_node == "lang"

    state, opt, is_final = choose(TREE, state, "lang", 0)  # выбрали "Английский"
    assert opt.value == "en"
    assert is_final is False
    assert state.current_node == "delivery"

    state, opt, is_final = choose(TREE, state, "delivery", 1)  # "Онлайн"
    assert opt.value == "online"
    assert is_final is True

    assert [a.value for a in state.answers] == ["en", "online"]


def test_back_restores_previous_node_and_drops_last_answer():
    state = WizardState.start("lang")
    state, _, _ = choose(TREE, state, "lang", 0)
    assert state.current_node == "delivery"

    state = go_back(state)
    assert state.current_node == "lang"
    assert state.answers == ()  # ответ про язык тоже откатился


def test_back_at_root_is_noop():
    state = WizardState.start("lang")
    state2 = go_back(state)
    assert state2 == state


def test_stale_choice_from_old_message_is_rejected():
    """
    Пользователь дошёл до 'delivery', но нажал кнопку со старого
    сообщения 'lang' (например, открыл старый чат). Это должно
    падать с понятной ошибкой, а не молча ломать состояние.
    """
    state = WizardState.start("lang")
    state, _, _ = choose(TREE, state, "lang", 0)  # теперь мы на delivery

    with pytest.raises(StaleChoiceError):
        choose(TREE, state, "lang", 1)  # а жмём на устаревшую кнопку lang


def test_state_roundtrips_through_dict_like_fsmcontext_would_store_it():
    """Ровно то, что будет происходить в FSMContext.data на реальном боте."""
    state = WizardState.start("lang")
    state, _, _ = choose(TREE, state, "lang", 0)

    as_dict = state.to_dict()
    restored = WizardState.from_dict(as_dict)

    assert restored == state


def test_linear_wizard_plain_strings_chain_to_next_step():
    tree, root = linear_wizard([
        ("a", "Шаг A", ["X", "Y"]),
        ("b", "Шаг B", ["Z"]),
    ])
    assert root == "a"
    validate_tree(tree, root)

    state = WizardState.start(root)
    state, opt, is_final = choose(tree, state, "a", 0)
    assert opt.label == opt.value == "X"
    assert is_final is False
    assert state.current_node == "b"

    state, opt, is_final = choose(tree, state, "b", 0)
    assert is_final is True  # последний шаг - финальный по умолчанию


def test_linear_wizard_explicit_next_node_enables_branching():
    tree, root = linear_wizard([
        ("topping", "Начинка", [
            ("Пепперони", "pepperoni", "spicy"),
            ("Маргарита", "margherita", "confirm"),
        ]),
        ("spicy", "Острота", ["Да", "Нет"]),
        ("confirm", "Финал", ["OK"]),
    ])
    validate_tree(tree, root)

    state = WizardState.start(root)
    state, _, is_final = choose(tree, state, "topping", 0)
    assert state.current_node == "spicy"
    assert is_final is False

    state2 = WizardState.start(root)
    state2, _, is_final2 = choose(tree, state2, "topping", 1)
    assert state2.current_node == "confirm"
    assert is_final2 is False


def test_linear_wizard_rejects_empty_steps():
    with pytest.raises(TreeError):
        linear_wizard([])


def test_state_to_dict_returns_tuples_not_lists():
    """P0.3: to_dict() должен возвращать кортежи, чтобы FSMContext не мутировал состояние."""
    state = WizardState.start("lang")
    state, _, _ = choose(TREE, state, "lang", 0)

    d = state.to_dict()
    assert isinstance(d["stack"], tuple), f"stack должен быть tuple, получен {type(d['stack'])}"
    assert isinstance(d["answers"], tuple), f"answers должен быть tuple, получен {type(d['answers'])}"


def test_state_from_dict_restores_correctly():
    """P0.3: from_dict() корректно восстанавливает состояние из кортежей."""
    state = WizardState.start("lang")
    state, _, _ = choose(TREE, state, "lang", 0)

    d = state.to_dict()
    restored = WizardState.from_dict(d)
    assert restored == state


def test_fsmcontext_cannot_mutate_state_via_to_dict():
    """P0.3: Если пользователь попытается мутировать результат to_dict(),
    оригинальное состояние не изменится (потому что это кортежи)."""
    state = WizardState.start("lang")
    state, _, _ = choose(TREE, state, "lang", 0)

    d = state.to_dict()
    # Попытка мутировать — добавление элемента в stack
    try:
        d["stack"].append("hacked")
    except AttributeError:
        pass  # Ожидаемо: tuple не имеет .append()

    # Оригинальное состояние не изменилось
    assert state.stack == ("lang", "delivery")


def test_answer_dict_has_correct_keys():
    """to_dict() должен возвращать словари с ключами node, label, value."""
    state = WizardState.start("lang")
    state, _, _ = choose(TREE, state, "lang", 0)

    d = state.to_dict()
    answer_dict = d["answers"][0]
    assert set(answer_dict.keys()) == {"node", "label", "value"}


# --- Тесты для P1.1: DynamicOption ---

def test_dynamic_option_resolves_label_from_state():
    """P1.1: DynamicOption разворачивает label через factory на основе состояния."""
    from tg_tree_wizard.core import DynamicOption, resolve_dynamic_options

    stock = {"count": 5}

    def label_factory(state):
        return f"Осталось {stock['count']} шт."

    node = Node(
        text="Товар",
        options=(DynamicOption(label_factory=label_factory, value="item1"),),
    )

    state = WizardState.start("root")
    resolved = resolve_dynamic_options(node, state=state)
    assert len(resolved) == 1
    assert resolved[0].label == "Осталось 5 шт."


def test_dynamic_option_skipped_during_validation():
    """P1.1: При валидации (state=None) DynamicOption пропускается."""
    from tg_tree_wizard.core import DynamicOption

    node = Node(
        text="Товар",
        options=(DynamicOption(label_factory=lambda s: "x", value="v"),),
    )
    resolved = resolve_dynamic_options(node, state=None)
    assert len(resolved) == 0


def test_choose_with_dynamic_option_works():
    """P1.1: choose() корректно обрабатывает DynamicOption."""
    from tg_tree_wizard.core import DynamicOption

    tree = {
        "dyn": Node(
            text="Выберите:",
            options=(DynamicOption(
                label_factory=lambda state: f"Шаг {len(state.answers) + 1}",
                value="dynamic_val",
                next_node="final",
            ),),
        ),
        "final": Node(text="Финал", options=(Option("Готово", "done"),)),
    }

    state = WizardState.start("dyn")
    new_state, opt, is_final = choose(tree, state, "dyn", 0)

    assert opt.value == "dynamic_val"
    assert not is_final
    assert new_state.current_node == "final"


def test_resolve_dynamic_options_mixed_with_regular():
    """P1.1: resolve_dynamic_options корректно смешивает обычные и динамические опции."""
    from tg_tree_wizard.core import DynamicOption

    node = Node(
        text="Test",
        options=(
            Option("Статик", "static_val"),
            DynamicOption(label_factory=lambda s: f"Динам {s.current_node}", value="dyn_val"),
            Option("Ещё статик", "static2"),
        ),
    )

    state = WizardState.start("root")
    resolved = resolve_dynamic_options(node, state=state)
    assert len(resolved) == 3
    assert isinstance(resolved[0], Option)
    assert isinstance(resolved[1], Option)  # DynamicOption развёрнут в Option
    assert isinstance(resolved[2], Option)
    assert resolved[0].label == "Статик"
    assert resolved[1].label == "Динам root"
    assert resolved[2].label == "Ещё статик"


def test_validate_tree_with_dynamic_option_passes():
    """P1.1: validate_tree проходит с деревом, содержащим DynamicOption."""
    from tg_tree_wizard.core import DynamicOption

    tree = {
        "dyn": Node(
            text="Test",
            options=(DynamicOption(
                label_factory=lambda s: "x", value="v", next_node="final",
            ),),
        ),
        "final": Node(text="Final", options=(Option("OK", "ok"),)),
    }

    # Не должно кинуть — DynamicOption пропускается при валидации
    validate_tree(tree, root="dyn")


def test_validate_tree_with_dynamic_option_fails_on_bad_next():
    """P1.1: validate_tree ловит несуществующий next_node у обычного Option."""
    from tg_tree_wizard.core import DynamicOption

    tree = {
        "mixed": Node(
            text="Test",
            options=(
                DynamicOption(label_factory=lambda s: "x", value="v"),
                Option("Bad", "bad_val", "nonexistent"),  # плохая ссылка
            ),
        ),
    }

    with pytest.raises(TreeError):
        validate_tree(tree, root="mixed")


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_simulate_wizard_simple_path():
    """P2.4: simulate_wizard прогоняет дерево и возвращает ответы + финальный узел."""
    from tg_tree_wizard.testing import simulate_wizard

    tree = {
        "a": Node(text="Step A", options=(Option("A1", "v1", "b"), Option("A2", "v2", "c"))),
        "b": Node(text="Step B", options=(Option("B1", "v3", None),)),
        "c": Node(text="Step C", options=(Option("C1", "v4", None),)),
    }

    answers, final_node = _run(simulate_wizard(tree, root="a", choices=[("a", 0), ("b", 0)]))
    assert len(answers) == 2
    assert answers[0].value == "v1"
    assert answers[1].value == "v3"
    assert final_node == "b"


def test_simulate_wizard_branching():
    """P2.4: simulate_wizard корректно обрабатывает ветвление."""
    from tg_tree_wizard.testing import simulate_wizard

    tree = {
        "a": Node(text="Step A", options=(Option("A1", "v1", "b"), Option("A2", "v2", "c"))),
        "b": Node(text="Step B", options=(Option("B1", "v3", None),)),
        "c": Node(text="Step C", options=(Option("C1", "v4", None),)),
    }

    answers, final_node = _run(simulate_wizard(tree, root="a", choices=[("a", 1), ("c", 0)]))
    assert len(answers) == 2
    assert answers[0].value == "v2"
    assert answers[1].value == "v4"
    assert final_node == "c"


def test_simulate_wizard_raises_for_missing_node():
    """P2.4: simulate_wizard поднимает KeyError для несуществующего узла."""
    from tg_tree_wizard.testing import simulate_wizard

    tree = {"a": Node(text="A", options=(Option("A1", "v1", None),))}

    with pytest.raises(KeyError):
        _run(simulate_wizard(tree, root="a", choices=[("nonexistent", 0)]))


def test_simulate_wizard_raises_for_invalid_index():
    """P2.4: simulate_wizard поднимает TreeError для неверного индекса."""
    from tg_tree_wizard.testing import simulate_wizard

    tree = {"a": Node(text="A", options=(Option("A1", "v1", None),))}

    with pytest.raises(TreeError):
        _run(simulate_wizard(tree, root="a", choices=[("a", 99)]))


def test_simulate_wizard_with_state_returns_full_state():
    """P2.4: simulate_wizard_with_state возвращает полный WizardState."""
    from tg_tree_wizard.testing import simulate_wizard_with_state

    tree = {
        "a": Node(text="Step A", options=(Option("A1", "v1", "b"),)),
        "b": Node(text="Step B", options=(Option("B1", "v2", None),)),
    }

    answers, state = _run(simulate_wizard_with_state(tree, root="a", choices=[("a", 0), ("b", 0)]))
    assert len(answers) == 2
    assert state.current_node == "b"
    assert len(state.answers) == 2


def test_simulate_wizard_empty_choices():
    """P2.4: simulate_wizard с пустым choices возвращает корневой узел."""
    from tg_tree_wizard.testing import simulate_wizard

    tree = {"a": Node(text="A", options=(Option("A1", "v1", None),))}

    answers, final_node = _run(simulate_wizard(tree, root="a", choices=[]))
    assert answers == []
    assert final_node == "a"


def test_simulate_wizard_with_dynamic_option():
    """P2.4: simulate_wizard корректно обрабатывает DynamicOption."""
    from tg_tree_wizard.testing import simulate_wizard

    tree = {
        "a": Node(text="A", options=(DynamicOption(
            label_factory=lambda s: f"Dynamic {len(s.answers)}", value="dv1", next_node="b",
        ),)),
        "b": Node(text="B", options=(Option("B1", "v2", None),)),
    }

    answers, final_node = _run(simulate_wizard(tree, root="a", choices=[("a", 0), ("b", 0)]))
    assert len(answers) == 2
    assert answers[0].label == "Dynamic 0"
    assert final_node == "b"
