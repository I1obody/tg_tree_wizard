# Releasing (для мейнтейнера)

Чек-лист публикации новой версии на PyPI.

## 1. Поднять версию

В `pyproject.toml`:

```toml
version = "X.Y.Z"
```

По [semver](https://semver.org/): багфикс → `PATCH`, новая фича без
поломки API → `MINOR`, ломающее изменение публичного API → `MAJOR`.

Добавить запись в `CHANGELOG.md`.

## 2. Прогнать тесты

```bash
pytest tests/ -v
```

Все должны быть зелёные — CI на GitHub это тоже проверит при пуше, но
проверить локально быстрее, чем ждать Actions.

## 3. Собрать дистрибутив

```bash
rm -rf dist build *.egg-info src/*.egg-info      # PowerShell: Remove-Item -Recurse -Force dist,build,*.egg-info,src\*.egg-info -ErrorAction SilentlyContinue
python -m build
```

## 4. (Опционально, для изменений в самом коде — не обязательно для
   мелких фиксов метаданных) Проверить на TestPyPI

```bash
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ tg-tree-wizard==X.Y.Z
```

## 5. Опубликовать на настоящий PyPI

```bash
twine upload dist/*
```

`username`: `__token__`, `password`: токен с pypi.org (см. Account
settings → API tokens). Хранить токен можно в `~/.pypirc` (в
`.gitignore`, не коммитить):

```ini
[testpypi]
username = __token__
password = pypi-...

[pypi]
username = __token__
password = pypi-...
```

## 6. Проверить

Открыть `https://pypi.org/project/tg-tree-wizard/X.Y.Z/` — метаданные,
ссылки, README должны отображаться корректно. `pip install tg-tree-wizard`
на чистом окружении — установиться и импортироваться без ошибок.

## 7. Тег в git

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```
