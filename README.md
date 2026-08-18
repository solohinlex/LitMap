# LitMap

Вопросы и сводки по литературным корпусам. Несколько проектов изолированы: у каждого свой список папок и свой индекс. Папки с текстами только читаются.

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp example.env .env   # затем подставьте свои URL и модели
```

Локальные эндпоинты (OpenAI-compatible `/v1`):

- эмбеддинги: `http://127.0.0.1:11434/v1`
- чат: `http://127.0.0.1:8500/v1`

Рабочие значения — в `.env` (файл не коммитится). Схема ключей — в `example.env`.

## Проекты

Реестр: `~/.config/litmap/config.yaml`. Индекс: `~/.local/share/litmap/projects/<имя>/index.sqlite`.

```bash
litmap projects add severny \
  --corpus ~/writing/severny/manuscript \
  --corpus ~/writing/severny/wiki
litmap projects list
litmap -p severny index
litmap -p severny ask "где Иван теряет кольцо?"
litmap -p severny character Иван
litmap -p severny chapter 4
```

Проект задаётся `-p` / `--project`, переменной `LITMAP_PROJECT` или текущей папкой, если она лежит внутри зарегистрированного корпуса.

Тип файла берётся из YAML-frontmatter (`type: character`) или из пути:

- `characters/`, `lore/`, `plotlines/` — карточки и лор вселенной, без привязки к книге
- любая другая верхняя папка — **рукопись**: файлы внутри по умолчанию главы этого текста (`Лисьи сказки/`, `Охота на ведьму/`, `Дополнительно/`)
- вложенный `chapters/` внутри рукописи тоже главы той же книги

`--work` ограничивает поиск одной рукописью (главы этой папки + общие `characters/` и `lore/`, без соседних книг):

```bash
litmap -p foxtales ask "Какие основные сюжетные линии?" --work "Лисьи сказки"
litmap -p foxtales --work "Лисьи сказки" ask "Какие основные сюжетные линии?"
litmap -p foxtales chapter 1 --work "Лисьи сказки"
```

Алиасы персонажа:

```yaml
---
type: character
name: Иван
aliases:
  - Ваня
---
```
