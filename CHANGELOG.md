# Changelog

Формат по мотивам [Keep a Changelog](https://keepachangelog.com/), версии по
[semver](https://semver.org/): `MAJOR.MINOR.PATCH`
(ломающие изменения → MAJOR, новые фичи без поломок → MINOR, багфиксы → PATCH).

## [2.0.2] — 2026-09-14

### Added
- Динамический текст узлов: `Node.text` теперь может быть `str | Callable[[WizardState | MenuState], str]`
- Пример бота с регистрацией через ввод текста и динамическим меню: `examples/pizza_bot_text_input.py`

### Fixed
- Сохранение пользовательских данных между wizard и menu через FSMContext
- `TreeMenu.start` теперь корректно сохраняет `user_credentials` в `MenuState.data`
- `TreeWizard.finish` сохраняет persistent данные при очистке состояния

## [2.0.1] — 2026-08-09

### Fixed
- `TreeMenu`: исправлена навигация при использовании `MenuOption` с `next_node=None`.
- Middleware: корректная передача `MenuMiddlewareData` в хуки для `TreeMenu`.

## [2.0.0] — 2026-08-09

### Added (Breaking)
- **`TreeMenu`** — новый адаптер для нелинейной навигации по меню с произвольными переходами между разделами.
- **`MenuOption`** — тип варианта для меню, не сохраняющий ответ в `WizardState`.
- **`MenuState`** — отдельное состояние FSM для меню (хранит текущий узел и историю переходов).
- **`MenuMiddlewareData`**, **`MenuAbortWizard`**, **`MenuMiddlewareHook`** — middleware для `TreeMenu` с новыми типами событий: `"menu_choice"`, `"menu_back"`.

### Added
- **`WizardStates`**, **`QuizStates`**, **`MenuStates`** — именованные перечисления состояний FSM.
- **`resolve_dynamic_options()`** — утилитная функция для разрешения динамических опций.

### Changed
- Публичный API расширен: `TreeMenu`, `MenuOption`, `MenuState`, middleware для меню.
- Описание пакета в `pyproject.toml`: добавлено упоминание "меню".

## [1.1.0] — 2026-08-04

### Added (P0 — Критические)
- `cancel_button` и кнопка отмены в каждом узле (`TreeWizard.cancel()`).
- Middleware-система: `MiddlewareData`, `AbortWizard`, хуки через параметр
  `middleware=[...]`. События: `"start"`, `"choice"`, `"back"`, `"cancel"`.
- `to_dict()` теперь возвращает кортежи вместо списков — состояние безопасно
  для хранения в FSMContext.

### Added (P1 — Расширение возможностей)
- `DynamicOption` — генерация клавиатуры на лету из состояния пользователя.
- `skip_to(target_node)` и `jump_to(target_node)` — переходы между узлами.
- `on_start` хук — действие при начале опроса.
- Улучшенные ошибки в `check_callback_data_limits` с указанием конкретных узлов.

### Added (P2 — Удобство)
- `URLOption` — вариант ответа с URL-кнопкой (Telegram Web App).
- `SwitchOption` — вариант ответа с кнопкой switch inline query.
- `pack_buttons` теперь учитывает визуальную ширину emoji (двойная ширина).
- `WizardManager` — управление состоянием нескольких активных опросов.
- `simulate_wizard()` и `simulate_wizard_with_state()` — прогон дерева без aiogram.

### Changed
- `pack_buttons`: emoji теперь считаются как 2 единицы ширины вместо 1.

## [1.0.2] — 2026-07-02

### Changed
- README переписан для внешней аудитории: бейджи (PyPI, CI, License),
  раздел "Зачем это нужно", Quick Start в первых строках, позиционирование
  относительно aiogram_dialog.
- Инструкции для контрибьюторов вынесены в `CONTRIBUTING.md`.

## [1.0.1] — 2026-07-02

### Fixed
- Исправлены ссылки на репозиторий в метаданных пакета (были плейсхолдером).

## [1.0.0] — 2026-07-02

Первый стабильный релиз. С этой версии публичный API (`Node`, `Option`,
`WizardState`, `TreeWizard`, `linear_wizard`, `pack_buttons`,
`check_callback_data_limits`) считается стабильным — ломающие изменения
будут только через `2.0.0`.

### Added
- `linear_wizard()` — короткий синтаксис для типовой линейной цепочки
  вопросов с точечными переопределениями для ветвления.
- `check_callback_data_limits()` — проверка при старте, что ни один узел
  не превысит лимит Telegram в 64 байта на callback_data, и что id узлов
  не содержат `:`.
- `py.typed` — пакет размечен как поддерживающий статическую типизацию.

## [0.1.0] — 2026-07-02

### Added
- `Node`/`Option` — декларативное описание дерева.
- `WizardState`, `choose`, `go_back`, `validate_tree` — чистое ядро без
  зависимости от aiogram.
- `TreeWizard` — адаптер к aiogram 3: клавиатуры, хендлеры, хранение
  состояния в `FSMContext`.
- `pack_buttons` — авто-раскладка кнопок по рядам с учётом длины текста.
