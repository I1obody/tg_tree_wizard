import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from tg_tree_wizard.core import Node, Option, TreeError
from tg_tree_wizard.aiogram_adapter import (
    TreeWizard,
    check_callback_data_limits,
    TELEGRAM_CALLBACK_DATA_LIMIT_BYTES,
)


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
