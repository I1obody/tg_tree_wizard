# tg-tree-wizard

[![PyPI](https://img.shields.io/pypi/v/tg-tree-wizard.svg)](https://pypi.org/project/tg-tree-wizard/)
[![Python](https://img.shields.io/pypi/pyversions/tg-tree-wizard.svg)](https://pypi.org/project/tg-tree-wizard/)
[![Tests](https://github.com/I1obody/tg_tree_wizard/actions/workflows/tests.yml/badge.svg)](https://github.com/I1obody/tg_tree_wizard/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Лёгкий движок древовидных inline-опросников (wizard) для [aiogram](https://github.com/aiogram/aiogram) 3.
Дерево описывается данными, а не отдельным хендлером на каждый уровень —
"назад", переходы и защита от лимита `callback_data` уже реализованы и
покрыты тестами внутри библиотеки.

## Зачем это нужно

Многошаговый inline-опрос в Telegram-боте (язык → формат → цель →
подтверждение, и подобные) в лоб на aiogram выливается в отдельный
хендлер на каждый уровень: собрать клавиатуру, распарсить `callback_data`,
руками собрать кнопку "назад". С ростом дерева это дублирование растёт
линейно, а кнопка "назад" и лимит Telegram в 64 байта на `callback_data`
почти неизбежно всплывают как баги на живых пользователях.

`tg-tree-wizard` сводит это к декларативному описанию дерева и двум
общим хендлерам внутри библиотеки — работающим для дерева любой формы
и глубины.

## Quick start

```bash
pip install tg-tree-wizard
```

```python
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from tg_tree_wizard import linear_wizard, TreeWizard

TREE, ROOT = linear_wizard([
    ("size", "Выберите размер:", ["Маленькая", "Средняя", "Большая"]),
    ("topping", "Начинка:", [
        ("Пепперони", "pepperoni", "spicy"),   # ветвление: доп. вопрос
        ("Маргарита", "margherita"),           # остальные — сразу в финал
    ]),
    ("spicy", "Поострее?", ["Да", "Нет"]),
])

async def on_finish(call, state, answers):
    await call.message.edit_text("Заказ: " + " → ".join(a.label for a in answers))

wizard = TreeWizard(TREE, root=ROOT, on_finish=on_finish)

dp = Dispatcher(storage=MemoryStorage())
dp.include_router(wizard.router)

@dp.message(Command("order"))
async def cmd_order(message, state):
    await wizard.start(message, state)
```

Всё — клавиатуры, "назад", хранение состояния в `FSMContext`, защита от
превышения лимита `callback_data` — уже внутри `TreeWizard`.

## Сколько кода экономит

Замер на дереве из 6 уровней (язык → формат → цель → индивидуально/группа →
возраст → уровень владения), с 2-7 вариантами ответа на каждом —
навигационная часть кода, без учёта бизнес-логики финального шага
(сохранение заявки и т.п. — она одинакова в обоих случаях):

| | Строк кода |
|---|---|
| Вручную (клавиатура + парсинг callback_data + кнопка "назад" на каждый уровень) | ~169 |
| `tg-tree-wizard` (`linear_wizard` + подключение роутера) | ~26 |

Разница держится **линейно** — каждое новое дерево в проекте стоит
фиксированные ~26 строк вместо ~169, потому что логика навигации уже
написана и протестирована один раз внутри библиотеки.

## Почему не aiogram_dialog?

[aiogram_dialog](https://github.com/Tishka17/aiogram_dialog) — более
мощный и зрелый фреймворк для сложных сценариев (виджеты, множественные
диалоги, кастомный рендеринг). `tg-tree-wizard` — не замена ему, а более
лёгкая альтернатива для конкретно одного случая: линейный или слабо
ветвящийся опрос с кнопкой "назад", без необходимости осваивать
Window/State-модель aiogram_dialog. Если нужен полноценный UI-фреймворк
поверх aiogram — берите aiogram_dialog; если нужен просто быстрый
древовидный визард — этого достаточно.

## Как описать своё дерево

**Короткий способ (рекомендуется для большинства случаев)** — `linear_wizard`.
Подходит, когда вопросы идут по порядку и лишь изредка нужно свернуть в
сторону:

```python
from tg_tree_wizard import linear_wizard, TreeWizard

TREE, ROOT = linear_wizard([
    ("lang", "Выберите язык:", ["Английский", "Немецкий"]),       # label == value
    ("delivery", "Формат:", [("Очно", "offline"), ("Онлайн", "online")]),
    ("topping", "Начинка:", [
        ("Пепперони", "pepperoni", "spicy"),   # явный переход = ветвление
        ("Маргарита", "margherita"),           # без 3-го элемента = следующий шаг по порядку
    ]),
    ("spicy", "Поострее?", ["Да", "Нет"]),
])

wizard = TreeWizard(TREE, root=ROOT, on_finish=my_finish_callback)
dp.include_router(wizard.router)
```

Правила для варианта ответа:
- `"Текст"` — метка и значение совпадают, переход на следующий шаг по списку;
- `("Текст", "значение")` — то же самое, но значение отдельно от текста кнопки;
- `("Текст", "значение", "id_узла")` — явный переход, для ветвления или
  для перехода не на следующий, а на произвольный узел (в т.ч. в обход
  промежуточных шагов).

Последний шаг в списке — финальный по умолчанию (после него опрос
завершается), если явно не переопределить переход у его вариантов.

**Полный способ** — `Node`/`Option` напрямую. Нужен, когда переходов в
дерево больше, чем шагов, и связь "шаг → следующий по умолчанию" не
работает (сложные ветвящиеся графы, несколько независимых корней и т.п.):

```python
from tg_tree_wizard import Node, Option, TreeWizard

TREE = {
    "start": Node(
        text="Первый вопрос:",
        options=(
            Option("Вариант A", "a", "next_node_id"),
            Option("Вариант B", "b", None),  # None = опрос завершается
        ),
    ),
    "next_node_id": Node(...),
}

wizard = TreeWizard(TREE, root="start", on_finish=my_finish_callback)
```

`TreeWizard(...)` сам вызывает `validate_tree` и `check_callback_data_limits`
при создании — если где-то опечатались в id узла или id получился слишком
длинным, бот упадёт при старте с понятной ошибкой, а не у живого
пользователя посреди опроса.

## Отмена опроса и кнопка «Назад» (v1.1.0)

По умолчанию кнопки отмены нет. Включите её, передав `cancel_button`:

```python
wizard = TreeWizard(
    TREE,
    root="start",
    cancel_button=True,           # показать кнопку «Отменить» в каждом узле
    cancel_callback_data="cancel",  # callback_data для кнопки отмены
)
```

Кнопка «Назад» добавляется автоматически на каждом шаге (кроме корневого).

## Middleware — перехват событий (v1.1.0)

Middleware-хуки позволяют логировать, валидировать или модифицировать события:

```python
from tg_tree_wizard import MiddlewareData, AbortWizard

def logging_hook(data: MiddlewareData):
    print(f"[{data.event_type}] узел={data.node_id}")
    if data.event_type == "start":
        print("Опрос начат!")

wizard = TreeWizard(
    TREE,
    root="start",
    middleware=[logging_hook],
)
```

Типы событий: `"start"`, `"choice"`, `"back"`, `"cancel"`.

Чтобы прервать опрос из middleware, бросьте `AbortWizard`:

```python
def validate_email(data: MiddlewareData):
    if data.event_type == "choice":
        value = data.selected.value
        if not "@" in value:
            raise AbortWizard("Некорректный email")
```

## Динамические варианты (DynamicOption) (v1.1.0)

`DynamicOption` позволяет генерировать клавиатуру на лету, используя данные из состояния пользователя:

```python
from tg_tree_wizard import DynamicOption

def languages_factory(state: WizardState) -> list[tuple[str, str]]:
    user_lang = state.answers.get("lang", "en")
    if user_lang == "ru":
        return [("Русский", "ru"), ("Украинский", "uk")]
    return [("English", "en"), ("German", "de")]

TREE = {
    "lang": Node(text="Язык:", options=(
        DynamicOption(label_factory=languages_factory, value="dyn_lang", next_node="format"),
    )),
    "format": Node(text="Формат:", options=(
        Option("Очно", "offline"), Option("Онлайн", "online"),
    )),
}
```

## Кнопки с URL и Switch Inline Query (v1.1.0)

```python
from tg_tree_wizard import URLOption, SwitchOption

TREE = {
    "menu": Node(text="Меню:", options=(
        Option("В каталог", "catalog"),
        URLOption(label="🌐 Наш сайт", value="url", url="https://example.com"),
        SwitchOption(label="🔍 Поиск по чату", value="search", switch_inline_query="поиск..."),
    )),
}
```

## WizardManager — управление состоянием сессий (v1.1.0)

`WizardManager` упрощает работу с несколькими активными опросами:

```python
from tg_tree_wizard import WizardManager

manager = WizardManager()
wizard = TreeWizard(TREE, root="start")
dp.include_router(wizard.router)

# Менеджер автоматически отслеживает активные опросы
active_count = manager.active_count()  # количество активных опросов
```

## Тестирование дерева без aiogram (v1.1.0)

`simulate_wizard` позволяет прогнать дерево через `asyncio.run()` без запуска бота:

```python
from tg_tree_wizard.testing import simulate_wizard, simulate_wizard_with_state
import asyncio

tree = {
    "a": Node(text="Шаг A", options=(Option("A1", "v1", "b"), Option("A2", "v2", None))),
    "b": Node(text="Шаг B", options=(Option("B1", "v3", None),)),
}

# Простой прогон: выбираем путь a->0 -> b->0
answers, final_node = asyncio.run(simulate_wizard(tree, root="a", choices=[("a", 0), ("b", 0)]))
print(final_node)  # "b"

# С полным состоянием:
answers, state = asyncio.run(simulate_wizard_with_state(tree, root="a", choices=[("a", 0), ("b", 0)]))
print(state.answers)  # {'v1': ..., 'v3': ...}
```

## Структура пакета

```
tg_tree_wizard/
├── pyproject.toml              # метаданные пакета
├── src/tg_tree_wizard/
│   ├── __init__.py             # публичный API
│   ├── core.py                 # чистая логика дерева, БЕЗ aiogram
│   ├── aiogram_adapter.py      # клавиатуры + хендлеры aiogram поверх core.py
│   ├── middleware.py            # middleware-система для перехвата событий
│   ├── manager.py              # WizardManager — управление состоянием сессий
│   └── testing.py              # simulate_wizard — прогон дерева без aiogram
├── tests/                      # тесты ядра и адаптера, без сети и без Telegram
└── examples/
    ├── simulate_flow.py        # прогон через настоящий aiogram Dispatcher, без сети
    ├── language_school_bot.py  # реальный бот
    └── pizza_bot.py            # реальный бот с ветвлением
```

Почему `core.py` отдельно от `aiogram_adapter.py`: ядро ничего не знает
про Telegram — значит, его логику (переходы, "назад", ошибки) можно
проверить обычным `pytest` за доли секунды, без сети и без живого бота.
Адаптер — тонкий слой, который только рендерит клавиатуры и дёргает ядро.

## Разработка и контрибьютинг

См. [CONTRIBUTING.md](CONTRIBUTING.md).

## Лицензия

[MIT](LICENSE)
