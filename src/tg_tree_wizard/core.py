"""
Ядро дерева-опросника.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any


class TreeError(Exception):
    """Ошибка в описании дерева (обнаруживается один раз, при старте бота)."""


class StaleChoiceError(Exception):
    """Пользователь нажал на кнопку из уже неактуального (старого) сообщения."""


# Тип для factory-функций динамических опций — принимает WizardState или MenuState.
DynamicLabelFactory = Callable[["WizardState | MenuState"], str]


@dataclass(frozen=True)
class DynamicOption:
    """
    Вариант ответа, текст кнопки которого вычисляется в рантайме
    на основе текущего состояния WizardState.

    Используется когда нужно показать актуальные данные (остатки, цены,
    количество мест и т.д.) без изменения структуры дерева.

    Пример:
        DynamicOption(
            label_factory=lambda state: f"Осталось {get_stock()} шт.",
            value="product_a",
            next_node="confirm",
        )
    """

    label_factory: DynamicLabelFactory
    value: str
    next_node: str | None = None


@dataclass(frozen=True)
class Option:
    label: str
    value: str
    next_node: str | None = None  # None = после выбора опрос завершается


@dataclass(frozen=True)
class URLOption(Option):
    """
    Вариант ответа с URL-кнопкой (P2.2).

    При выборе этой опции бот открывает указанный URL в Telegram Web App
    или отправляет его пользователю.

    Пример:
        URLOption(label="🌐 Сайт", value="url", url="https://example.com")
    """

    url: str | None = None


@dataclass(frozen=True)
class SwitchOption(Option):
    """
    Вариант ответа с кнопкой switch inline query (P2.2).

    При выборе этой опции открывается диалог ввода с предзаполненным
    текстом для переключения inline-запроса.

    Пример:
        SwitchOption(label="🔍 Поиск", value="search", switch_inline_query="поиск...")
    """

    switch_inline_query: str | None = None


@dataclass(frozen=True)
class MenuOption(Option):
    """
    Вариант ответа, который отображается в меню (P1.2).

    Отличается от обычного Option флагом `is_menu_item`, который позволяет
    TreeMenu отличать опции для клавиатуры от опций для меню. По умолчанию
    все MenuOption имеют is_menu_item=True.

    Пример:
        MenuOption(label="📋 Список заказов", value="orders")
        MenuOption(label="ℹ️ О нас", value="about", next_node="about_page")
        # Кастомный callback_data для внешних обработчиков (не перехватывается TreeMenu):
        MenuOption(label="📝 Пройти опрос", value="survey_btn", callback_data="custom:survey_btn")
    """

    is_menu_item: bool = True
    callback_data: str | None = (
        None  # Переопределяет автоматически генерируемый формат {prefix}:{node_id}:{index}
    )


@dataclass(frozen=True)
class Node:
    text: str | Callable[["WizardState | MenuState"], str]
    # Поддерживает как обычные Option, так и DynamicOption (P1.1).
    options: tuple[Option | DynamicOption, ...] = field(default_factory=tuple)


from typing import Optional


def resolve_dynamic_options(
    node: Node, state: Optional["WizardState | MenuState"] = None
) -> tuple[Option, ...]:
    """
    Разворачивает DynamicOption в обычные Option на лету (P1.1).

    Если state=None, DynamicOption пропускается без развёртки — используется
    для валидации дерева при старте бота.

    Поддерживает как WizardState (для TreeWizard), так и MenuState (для TreeMenu).
    """
    result: list[Option] = []
    for opt in node.options:
        if isinstance(opt, DynamicOption):
            if state is not None:
                label = opt.label_factory(state)
                result.append(
                    Option(label=label, value=opt.value, next_node=opt.next_node)
                )
            # Если state=None (валидация), пропускаем DynamicOption —
            # его next_node будет проверен при следующем рендере.
        else:
            result.append(opt)
    return tuple(result)


def validate_tree(
    tree: dict[str, Node], root: str, allow_external_refs: bool = False
) -> None:
    """
    Проверяет дерево один раз при старте бота, а не в рантайме на живом
    пользователе. Ловит: отсутствующий root, ссылки на несуществующие
    узлы, узлы без вариантов ответа (тупик).

    DynamicOption пропускаются при проверке next_node — их валидация
    происходит при каждом рендере клавиатуры.

    Если allow_external_refs=True, MenuOption с ссылками вне дерева
    пропускаются (используется для TreeWizard, где меню может ссылаться
    на main_menu).
    """
    if root not in tree:
        raise TreeError(f"Корневой узел {root!r} отсутствует в дереве")

    for node_id, node in tree.items():
        # resolve_dynamic_options с state=None пропускает DynamicOption.
        # Если все опции — DynamicOption, это допустимо (валидация в рантайме).
        resolved = resolve_dynamic_options(node, state=None)
        if not resolved and not any(isinstance(o, DynamicOption) for o in node.options):
            raise TreeError(f"Узел {node_id!r} не содержит вариантов ответа")
        for opt in resolved:
            # MenuOption может ссылаться на узлы вне этого дерева (например, main_menu)
            if isinstance(opt, MenuOption) and allow_external_refs:
                continue
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

    shared_data — общий словарь, который сохраняется при переходах между
    меню и опросом. Используется для передачи данных (например, выбранный
    товар из опроса, который потом отображается в меню).
    """

    stack: tuple[str, ...]
    answers: tuple[Answer, ...] = field(default_factory=tuple)
    shared_data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def start(cls, root: str) -> "WizardState":
        return cls(stack=(root,), answers=(), shared_data={})

    @property
    def current_node(self) -> str:
        return self.stack[-1]

    def to_dict(self) -> dict:
        """
        Для сохранения в FSMContext.data (там нужны сериализуемые типы).

        Возвращает кортежи вместо списков, чтобы гарантировать
        неизменяемость состояния — FSMContext не сможет случайно
        мутировать данные через .append() или прямое присвоение.
        """
        return {
            "stack": tuple(self.stack),
            "answers": tuple(
                {"node": a.node, "label": a.label, "value": a.value}
                for a in self.answers
            ),
            "shared_data": dict(self.shared_data),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WizardState":
        return cls(
            stack=tuple(data["stack"]),
            answers=tuple(
                Answer(node=a["node"], label=a["label"], value=a["value"])
                for a in data["answers"]
            ),
            shared_data=data.get("shared_data", {}),
        )


@dataclass(frozen=True)
class MenuState:
    """
    Состояние для меню — текущий узел, родительский узел и собранные данные.

    parent_node используется для корректной навигации "Назад" —
    запоминает, откуда пользователь пришёл в текущий узел.

    shared_data — общий словарь, который сохраняется при переходах между
    меню и опросом. Используется для передачи данных (например, выбранный
    товар из опроса, который потом отображается в меню).
    """

    current_node: str
    data: dict[str, Any] = field(default_factory=dict)
    parent_node: str | None = None
    shared_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "current_node": self.current_node,
            "parent_node": self.parent_node,
            "data": self.data,
            "shared_data": dict(self.shared_data),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MenuState":
        return cls(
            current_node=data["current_node"],
            parent_node=data.get("parent_node"),
            data=data.get("data", {}),
            shared_data=data.get("shared_data", {}),
        )


def choose(
    tree: dict[str, Node],
    state: WizardState,
    node_id: str,
    option_index: int,
) -> tuple[WizardState, Option | DynamicOption, bool]:
    """
    Обрабатывает выбор пользователя.
    Возвращает (новое_состояние, выбранная_опция, завершён_ли_опрос).

    DynamicOption разворачиваются в обычные Option на лету через
    resolve_dynamic_options() перед обработкой выбора.
    """
    if state.current_node != node_id:
        # Пользователь нажал кнопку из уже неактуального сообщения
        # (например, после /start заново или параллельного диалога).
        raise StaleChoiceError(
            f"Ожидался узел {state.current_node!r}, получен {node_id!r}"
        )

    node = tree[node_id]
    resolved_options = resolve_dynamic_options(node, state=state)

    if not (0 <= option_index < len(resolved_options)):
        raise TreeError(f"Индекс {option_index} вне диапазона для узла {node_id!r}")

    opt = resolved_options[option_index]
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
#   DynamicOption(...)                   -> метка вычисляется в рантайме
ShortOption = str | tuple[str, str] | tuple[str, str, str] | DynamicOption

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
            elif isinstance(opt, DynamicOption):
                # DynamicOption — метка вычисляется в рантайме (placeholder)
                label, value, next_node = "", opt.value, opt.next_node or default_next
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
