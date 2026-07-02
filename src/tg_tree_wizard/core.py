"""
Ядро дерева-опросника. Никаких импортов aiogram здесь нет и не должно быть —
это чистая логика, которую можно тестировать без Telegram и без сети.
"""

from dataclasses import dataclass, field, replace


class TreeError(Exception):
    """Ошибка в описании дерева (обнаруживается один раз, при старте бота)."""


class StaleChoiceError(Exception):
    """Пользователь нажал на кнопку из уже неактуального (старого) сообщения."""


@dataclass(frozen=True)
class Option:
    label: str
    value: str
    next_node: str | None = None  # None = после выбора опрос завершается


@dataclass(frozen=True)
class Node:
    text: str
    options: tuple[Option, ...] = field(default_factory=tuple)


def validate_tree(tree: dict[str, Node], root: str) -> None:
    """
    Проверяет дерево один раз при старте бота, а не в рантайме на живом
    пользователе. Ловит: отсутствующий root, ссылки на несуществующие
    узлы, узлы без вариантов ответа (тупик).
    """
    if root not in tree:
        raise TreeError(f"Корневой узел {root!r} отсутствует в дереве")

    for node_id, node in tree.items():
        if not node.options:
            raise TreeError(f"Узел {node_id!r} не содержит вариантов ответа")
        for opt in node.options:
            if opt.next_node is not None and opt.next_node not in tree:
                raise TreeError(
                    f"Узел {node_id!r}: вариант {opt.label!r} ссылается "
                    f"на несуществующий узел {opt.next_node!r}"
                )


@dataclass(frozen=True)
class Answer:
    node: str
    label: str
    value: str


@dataclass(frozen=True)
class WizardState:
    """
    Всё состояние одного прохождения опроса. Неизменяемое (frozen) —
    каждая операция возвращает НОВЫЙ WizardState, старый не трогается.
    Это то, что вы будете класть целиком в FSMContext.data.
    """
    stack: tuple[str, ...]
    answers: tuple[Answer, ...] = field(default_factory=tuple)

    @classmethod
    def start(cls, root: str) -> "WizardState":
        return cls(stack=(root,), answers=())

    @property
    def current_node(self) -> str:
        return self.stack[-1]

    def to_dict(self) -> dict:
        """Для сохранения в FSMContext.data (там нужны сериализуемые типы)."""
        return {
            "stack": list(self.stack),
            "answers": [a.__dict__ for a in self.answers],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WizardState":
        return cls(
            stack=tuple(data["stack"]),
            answers=tuple(Answer(**a) for a in data["answers"]),
        )


def choose(
    tree: dict[str, Node],
    state: WizardState,
    node_id: str,
    option_index: int,
) -> tuple[WizardState, Option, bool]:
    """
    Обрабатывает выбор пользователя.
    Возвращает (новое_состояние, выбранная_опция, завершён_ли_опрос).
    """
    if state.current_node != node_id:
        # Пользователь нажал кнопку из уже неактуального сообщения
        # (например, после /start заново или параллельного диалога).
        raise StaleChoiceError(
            f"Ожидался узел {state.current_node!r}, получен {node_id!r}"
        )

    node = tree[node_id]
    if not (0 <= option_index < len(node.options)):
        raise TreeError(f"Индекс {option_index} вне диапазона для узла {node_id!r}")

    opt = node.options[option_index]
    new_answers = state.answers + (Answer(node_id, opt.label, opt.value),)

    if opt.next_node is None:
        return replace(state, answers=new_answers), opt, True

    new_stack = state.stack + (opt.next_node,)
    return replace(state, stack=new_stack, answers=new_answers), opt, False


def go_back(state: WizardState) -> WizardState:
    """Отменяет последний шаг. Если мы уже в корне — ничего не делает."""
    if len(state.stack) <= 1:
        return state
    return WizardState(stack=state.stack[:-1], answers=state.answers[:-1])


# Один вариант ответа в коротком синтаксисе linear_wizard:
#   "Текст кнопки"                       -> label == value, переход на следующий шаг
#   ("Текст кнопки", "значение")         -> явное значение, переход на следующий шаг
#   ("Текст кнопки", "значение", "узел") -> явное значение + явный переход (ветвление)
ShortOption = str | tuple[str, str] | tuple[str, str, str]

# Один шаг: (id_узла, текст_вопроса, список_вариантов)
Step = tuple[str, str, list[ShortOption]]


def linear_wizard(steps: list[Step]) -> tuple[dict[str, Node], str]:
    """
    Короткий способ описать дерево для типового случая — линейной цепочки
    вопросов, где почти все варианты ведут на следующий шаг по порядку.
    Возвращает (tree, root_id), готовые для validate_tree()/TreeWizard().

    Последний шаг по умолчанию — финальный (next_node=None у всех его
    вариантов, если не переопределено явно).

    Точечное ветвление — там, где часть вариантов уходит не на следующий
    шаг, а куда-то ещё (или сразу в финал, минуя промежуточные шаги) —
    делается явным третьим элементом кортежа с id нужного узла.

    Пример:
        TREE, ROOT = linear_wizard([
            ("size", "Выберите размер:", ["Маленькая", "Средняя", "Большая"]),
            ("topping", "Начинка:", [
                ("Пепперони", "pepperoni", "spicy"),  # ветка в сторону
                "Маргарита",                          # обычный переход дальше
            ]),
            ("spicy", "Поострее?", ["Да", "Нет"]),
            ("confirm", "Подтвердить заказ?", ["Да"]),
        ])
    """
    if not steps:
        raise TreeError("Нужен хотя бы один шаг")

    node_ids = [step[0] for step in steps]
    tree: dict[str, Node] = {}

    for i, (node_id, text, options) in enumerate(steps):
        default_next = node_ids[i + 1] if i + 1 < len(node_ids) else None
        built_options = []

        for opt in options:
            if isinstance(opt, str):
                label, value, next_node = opt, opt, default_next
            elif len(opt) == 2:
                label, value = opt
                next_node = default_next
            elif len(opt) == 3:
                label, value, next_node = opt
            else:
                raise TreeError(f"Некорректный вариант ответа: {opt!r}")
            built_options.append(Option(label, value, next_node))

        tree[node_id] = Node(text=text, options=tuple(built_options))

    return tree, node_ids[0]
