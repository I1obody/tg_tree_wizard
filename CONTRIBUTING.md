# Contributing

Спасибо, что хотите помочь `tg-tree-wizard`! Если у вас есть идеи или баг-репорт —
откройте issue или PR.

## Установка для разработки

```bash
git clone https://github.com/I1obody/tg_tree_wizard.git
cd tg_tree_wizard
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

`-e` (editable) позволяет вносить изменения прямо в `src/tg_tree_wizard/` без
повторной установки пакета.

## Запуск тестов

```bash
pytest tests/ -v
```

Тесты ядра (`core.py`) не зависят от aiogram и Telegram — они быстрые и надёжные.

## Примеры

```bash
python examples/simulate_flow.py
```

Запускает `Dispatcher` с `MemoryStorage`, без реальных HTTP-запросов к `api.telegram.org`.

Для запуска с реальным ботом:

```bash
export BOT_TOKEN=ваш_токен
python examples/pizza_bot.py
```

## Структура проекта

`src/tg_tree_wizard/core.py` — чистое ядро (без зависимостей от aiogram). Все
логические изменения должны идти сюда. В `aiogram_adapter.py`, `manager.py`,
`middleware.py`, `testing.py` — только привязки к конкретным фреймворкам/задачам.

Если ваш PR добавляет новую функциональность, убедитесь, что ядро (`core.py`)
остается чистым и тестируемым без aiogram.

## Semver

Начиная с `1.0.0` публичный API считается стабильным:
- `Node`, `Option`, `DynamicOption`, `URLOption`, `SwitchOption`
- `WizardState`, `TreeError`, `StaleChoiceError`
- `linear_wizard()`, `choose()`, `go_back()`
- `TreeWizard`, `WizardManager`
- `pack_buttons()`, `check_callback_data_limits()`
- `MiddlewareData`, `AbortWizard`, `MiddlewareHook`
- `simulate_wizard()`, `simulate_wizard_with_state()`

Ломающие изменения будут только в `2.0.0`.

## Открытие PR

1. Создайте ветку от `main`.
2. Убедитесь, что `pytest tests/ -v` проходит (CI также проверяет на 3.10/3.11/3.12).
3. Обновите CHANGELOG.md и README.md при необходимости.
4. Отправьте PR с понятным описанием изменений.
