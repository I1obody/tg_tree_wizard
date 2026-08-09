# tg-tree-wizard

[![PyPI](https://img.shields.io/pypi/v/tg-tree-wizard.svg)](https://pypi.org/project/tg-tree-wizard/)
[![Python](https://img.shields.io/pypi/pyversions/tg-tree-wizard.svg)](https://pypi.org/project/tg-tree-wizard/)
[![Tests](https://github.com/I1obody/tg_tree_wizard/actions/workflows/tests.yml/badge.svg)](https://github.com/I1obody/tg_tree_wizard/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Лёгкий движок древовидных inline-опросников и меню для [aiogram](https://github.com/aiogram/aiogram) 3. Дерево описывается данными — не отдельным хендлером на каждый уровень. «Назад», переходы, защита от лимита `callback_data` — всё уже внутри библиотеки и покрыто тестами.

## Quick start

```bash
pip install tg-tree-wizard
```

### Опрос (wizard)

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

### Меню (menu)

```python
from tg_tree_wizard import Node, MenuOption, TreeMenu

TREE = {
    "main_menu": Node(
        text="Главное меню:",
        options=(
            MenuOption("📋 Заказы", "orders"),
            MenuOption("👤 Профиль", "profile"),
            MenuOption("💬 Поддержка", "support"),
        ),
    ),
    "orders": Node(
        text="Ваши заказы:",
        options=(
            MenuOption("📦 Активные", "active"),
            MenuOption("✅ Завершённые", "completed"),
            MenuOption("⬅️ В главное меню", "back", "main_menu"),
        ),
    ),
}

menu = TreeMenu(TREE, root="main_menu")
dp.include_router(menu.router)

@dp.message(Command("start"))
async def cmd_start(message, state):
    await menu.start(message, state)
```

## Зачем это нужно

Многошаговый inline-опрос или меню в Telegram-боте на чистом aiogram — это отдельный хендлер на каждый уровень: собрать клавиатуру, распарсить `callback_data`, вручную добавить кнопку «Назад». С ростом дерева дублирование растёт линейно, а кнопка «Назад» и лимит Telegram в 64 байта на `callback_data` почти неизбежно всплывают как баги.

`tg-tree-wizard` сводит это к декларативному описанию дерева и двум общим хендлерам — работающим для дерева любой формы и глубины, будь то опрос с ответами или навигационное меню без сохранения состояния выбора.

## Сколько кода экономит

Замер на дереве из 6 уровней (язык → формат → цель → индивидуально/группа → возраст → уровень владения), с 2–7 вариантами ответа на каждом — навигационная часть кода, без учёта бизнес-логики финального шага:

| | Строк кода |
|---|---|
| Вручную (клавиатура + парсинг callback_data + кнопка «Назад» на каждый уровень) | ~169 |
| `tg-tree-wizard` (`linear_wizard` + подключение роутера) | ~26 |

Разница держится **линейно** — каждое новое дерево в проекте стоит фиксированные ~26 строк вместо ~169, потому что логика навигации уже написана и протестирована один раз внутри библиотеки.

## TreeWizard — древовидные опросы

### Короткий способ: `linear_wizard`

Подходит для большинства случаев — вопросы идут по порядку, ветвление лишь изредка:

```python
from tg_tree_wizard import linear_wizard, TreeWizard

TREE, ROOT = linear_wizard([
    ("lang", "Выберите язык:", ["Английский", "Немецкий"]),
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
- `("Текст", "значение", "id_узла")` — явный переход, для ветвления или перехода не на следующий, а на произвольный узел.

Последний шаг в списке — финальный по умолчанию (после него опрос завершается), если явно не переопределить переход у его вариантов.

### Полный способ: `Node` / `Option` напрямую

Нужен для сложных ветвящихся графов, нескольких независимых корней и т.п.:

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

`TreeWizard(...)` сам вызывает `validate_tree` и `check_callback_data_limits` при создании — если где-то опечатались в id узла или id получился слишком длинным, бот упадёт при старте с понятной ошибкой.

### Кнопка «Назад» и отмена

Кнопка «Назад» добавляется автоматически на каждом шаге (кроме корневого). Для кнопки отмены:

```python
wizard = TreeWizard(
    TREE, root="start",
    cancel_button=True,
    cancel_callback_data="cancel",
)
```

### Middleware — перехват событий

Middleware-хуки позволяют логировать, валидировать или модифицировать события:

```python
from tg_tree_wizard import MiddlewareData, AbortWizard

def logging_hook(data: MiddlewareData):
    print(f"[{data.event_type}] узел={data.node_id}")

wizard = TreeWizard(TREE, root="start", middleware=[logging_hook])
```

Типы событий: `"start"`, `"choice"`, `"back"`, `"cancel"`. Чтобы прервать опрос из middleware — бросьте `AbortWizard`.

### Динамические варианты (DynamicOption)

Генерирует клавиатуру на лету, используя данные из состояния пользователя:

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
}
```

### Кнопки с URL и Switch Inline Query

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

## TreeMenu — навигационные меню

### Простые линейные меню: `TreeWizard` + `MenuOption`

Если нужно простое линейное меню (как опрос, но без сохранения ответов), используйте `TreeWizard` с `MenuOption`:

```python
from tg_tree_wizard import Node, MenuOption, TreeWizard

TREE = {
    "main_menu": Node(
        text="Главное меню:",
        options=(
            MenuOption("⚙️ Настройки", "settings", "settings_menu"),
            MenuOption("👤 Профиль", "profile", "profile_page"),
            MenuOption("📖 Помощь", "help", "help_page"),
        ),
    ),
}

wizard = TreeWizard(TREE, root="main_menu")
```

`MenuOption` полностью совместим со всеми возможностями библиотеки: middleware, FSMContext, динамические опции и т.д.

### Нелинейная навигация: `TreeMenu`

Для меню с произвольной навигацией (пользователь может переходить между разделами без линейного порядка) используется `TreeMenu`:

```python
from tg_tree_wizard import Node, MenuOption, TreeMenu

TREE = {
    "main_menu": Node(
        text="Главное меню:",
        options=(
            MenuOption("📋 Заказы", "orders"),
            MenuOption("👤 Профиль", "profile"),
            MenuOption("💬 Поддержка", "support"),
        ),
    ),
    "orders": Node(
        text="Ваши заказы:",
        options=(
            MenuOption("📦 Активные", "active"),
            MenuOption("✅ Завершённые", "completed"),
            MenuOption("⬅️ В главное меню", "back", "main_menu"),
        ),
    ),
}

menu = TreeMenu(TREE, root="main_menu")
dp.include_router(menu.router)
```

`TreeMenu` отличается от `TreeWizard`:
- Использует `MenuState` — хранит текущий узел и историю переходов;
- Поддерживает произвольную навигацию между разделами меню;
- Middleware получает новые типы событий: `"menu_choice"`, `"menu_back"`.

## WizardManager — управление состоянием сессий

```python
from tg_tree_wizard import WizardManager

manager = WizardManager()
wizard = TreeWizard(TREE, root="start")
dp.include_router(wizard.router)

active_count = manager.active_count()  # количество активных опросов
```

## Тестирование дерева без aiogram

`simulate_wizard` позволяет прогнать дерево через `asyncio.run()` без запуска бота:

```python
from tg_tree_wizard.testing import simulate_wizard, simulate_wizard_with_state
import asyncio

tree = {
    "a": Node(text="Шаг A", options=(Option("A1", "v1", "b"), Option("A2", "v2", None))),
    "b": Node(text="Шаг B", options=(Option("B1", "v3", None),)),
}

answers, final_node = asyncio.run(simulate_wizard(tree, root="a", choices=[("a", 0), ("b", 0)]))
print(final_node)  # "b"
```

## Почему не aiogram_dialog?

[aiogram_dialog](https://github.com/Tishka17/aiogram_dialog) — более мощный и зрелый фреймворк для сложных сценариев (виджеты, множественные диалоги, кастомный рендеринг). `tg-tree-wizard` — не замена ему, а более лёгкая альтернатива для конкретно одного случая: линейный или слабо ветвящийся опрос / меню с кнопкой «Назад», без необходимости осваивать Window/State-модель aiogram_dialog. Если нужен полноценный UI-фреймворк поверх aiogram — берите aiogram_dialog; если нужен просто быстрый древовидный визард или меню — этого достаточно.

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
    ├── language_school_bot.py  # реальный бот с опросом
    ├── pizza_bot.py            # реальный бот с ветвлением
    └── menu_bot.py             # пример меню с TreeMenu и MenuOption
```

Почему `core.py` отдельно от `aiogram_adapter.py`: ядро ничего не знает про Telegram — значит, его логику (переходы, «Назад», ошибки) можно проверить обычным `pytest` за доли секунды, без сети и без живого бота. Адаптер — тонкий слой, который только рендерит клавиатуры и дёргает ядро.

## Разработка и контрибьютинг

Если вы обнаружили уязвимость безопасности, пожалуйста, прочитайте [SECURITY.md](SECURITY.md) перед тем как открыть issue.

## Лицензия

[MIT](LICENSE)
