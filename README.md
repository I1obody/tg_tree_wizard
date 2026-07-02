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

## Структура пакета

```
tg_tree_wizard/
├── pyproject.toml              # метаданные пакета
├── src/tg_tree_wizard/
│   ├── __init__.py             # публичный API
│   ├── core.py                 # чистая логика дерева, БЕЗ aiogram
│   └── aiogram_adapter.py      # клавиатуры + хендлеры aiogram поверх core.py
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
