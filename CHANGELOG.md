# Changelog

Формат по мотивам [Keep a Changelog](https://keepachangelog.com/), версии по
[semver](https://semver.org/): `MAJOR.MINOR.PATCH`
(ломающие изменения → MAJOR, новые фичи без поломок → MINOR, багфиксы → PATCH).

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
