import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from tg_tree_wizard.core import (
    linear_wizard,
    Node, Option, WizardState, TreeError, StaleChoiceError,
    validate_tree, choose, go_back,
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
