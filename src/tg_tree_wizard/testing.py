"""
Тестовый хелпер для прогона дерева без aiogram (P2.4).

Позволяет проверить логику дерева-опросника, не поднимая бота и не
используя FSMContext — полезно для unit-тестирования.
"""

from __future__ import annotations

from typing import Any

from .core import Node, WizardState, choose


async def simulate_wizard(
    tree: dict[str, Node],
    root: str,
    choices: list[tuple[str, int]],
) -> tuple[list[Any], str]:
    """
    Прогоняет дерево без aiogram. Возвращает ответы и финальный узел.

    Args:
        tree: Дерево узлов (как в TreeWizard).
        root: ID корневого узла.
        choices: Список пар [(node_id, option_index), ...], определяющих путь.

    Returns:
        Кортеж из списка ответов (Option) и финального node_id.

    Raises:
        ValueError: Если указанный индекс опции выходит за границы.
        KeyError: Если узел не найден в дереве.
    """
    state = WizardState.start(root)
    answers: list[Any] = []

    for node_id, option_index in choices:
        if node_id not in tree:
            raise KeyError(f"Узел {node_id!r} отсутствует в дереве")

        new_state, selected, _finished = choose(tree, state, node_id, option_index)
        state = new_state
        answers.append(selected)

    return answers, state.current_node


async def simulate_wizard_with_state(
    tree: dict[str, Node],
    root: str,
    choices: list[tuple[str, int]],
) -> tuple[list[Any], WizardState]:
    """
    Прогоняет дерево и возвращает полный WizardState в конце.

    Полезно для проверки промежуточных состояний (answers, current_node).
    """
    state = WizardState.start(root)
    answers: list[Any] = []

    for node_id, option_index in choices:
        if node_id not in tree:
            raise KeyError(f"Узел {node_id!r} отсутствует в дереве")

        new_state, selected, _finished = choose(tree, state, node_id, option_index)
        state = new_state
        answers.append(selected)

    return answers, state
