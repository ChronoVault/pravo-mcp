# pravo-mcp

MCP-сервер для API «Официальное опубликование правовых актов»
([publication.pravo.gov.ru](http://publication.pravo.gov.ru)): поиск федеральных законов, указов,
постановлений и других актов, их карточки и ссылки на официальные PDF прямо из Claude
и других MCP-клиентов.

API портала открытый, только на чтение, ключ не нужен. Проект неофициальный и не связан с порталом.

## Варианты

| Вариант | Для кого | Где код |
| --- | --- | --- |
| **Cloudflare Workers** | Публичный сервер одной ссылкой, бесплатно, без карты | [`cloudflare/`](cloudflare/), [инструкция](deploy/cloudflare.md) |
| **Yandex Serverless Containers** (или любой Docker-хостинг) | Публичный сервер в РФ | [`server_http.py`](server_http.py), [`Dockerfile`](Dockerfile), [инструкция](deploy/yandex.md) |
| **Локально** (stdio) | Claude Desktop, Claude Code; Python 3.8+ без зависимостей | [`pravo_mcp.py`](pravo_mcp.py) |

Удалённые версии работают по Streamable HTTP на пути `/mcp`, без сессий и без авторизации.

## Инструменты

| Инструмент | Что делает |
| --- | --- |
| `pravo_search` | Поиск актов: название, текст, номер, блок, вид документа, даты подписания и опубликования |
| `pravo_document` | Карточка документа по номеру электронного опубликования (eoNumber) |
| `pravo_dictionary` | Справочники: блоки, категории, принявшие органы, виды документов |
| `pravo_pdf_link` | Ссылки на официальный PDF и HTML-карточку (удалённые версии) |
| `pravo_download_pdf` | Скачать PDF в папку `downloads` рядом со скриптом (только локальная версия) |
| `pravo_stats` | Статистика опубликования по блокам за день, неделю, месяц |

## Подключение к Claude

### Удалённый сервер

**Settings → Connectors → Add custom connector**, адрес вида `https://<ваш-домен>/mcp`.
Как поднять свой сервер: [Cloudflare](deploy/cloudflare.md) или [Yandex Cloud](deploy/yandex.md).

### ChatGPT

Нужен режим разработчика (Developer mode); на каких тарифах он доступен, смотрите в справке OpenAI.
Settings → Apps & Connectors → Create (или New connector): адрес `https://<ваш-домен>/mcp`,
аутентификация **No authentication**.

### Codex

```bash
codex mcp add pravo --url https://<ваш-домен>/mcp
```

или в `~/.codex/config.toml`:

```toml
[mcp_servers.pravo]
url = "https://<ваш-домен>/mcp"
```

Локальная версия в Codex: `codex mcp add pravo -- python3 /полный/путь/к/pravo_mcp.py`.

### Локально (Claude Desktop)

Файл `claude_desktop_config.json` (Settings → Developer → Edit Config) должен быть целым JSON-объектом:

```json
{
  "mcpServers": {
    "pravo": {
      "command": "python3",
      "args": ["/полный/путь/к/pravo_mcp.py"]
    }
  }
}
```

Затем полностью перезапустите Claude Desktop. Проверка без Claude:

```bash
python3 pravo_mcp.py --selftest
```

Должен найти Указ Президента РФ от 08.08.2023 № 585.

### Локально (Claude Code)

```bash
claude mcp add pravo -- python3 /полный/путь/к/pravo_mcp.py
```

## Особенности API, которых нет в документации

Сервер обходит их сам, но о них полезно знать:

- **Даты только `ДД.ММ.ГГГГ`.** Дату `2026-09-01` портал молча игнорирует и возвращает всё подряд.
  Инструменты принимают оба формата и приводят к нужному.
- **Фильтр по виду документа — параметр `DocumentTypes`**, а не `DocumentTypeId`, как в документации.
- **Поиск по названию буквальный**, без морфологии: «Налоговый кодекс» и «Налогового кодекса» — разные запросы.
- Федеральные законы и указы Президента лежат в блоке `president`.
  GUID вида «Федеральный закон»: `82a8bf1c-3bc7-47ed-827f-7affd43a7f27`.
- `eoNumber` — 16 цифр: код блока или региона (`0001` — федеральный уровень), дата, порядковый номер.
- **PDF — сканы без текстового слоя.** Текст из них без OCR не извлечь.
- Поиск по названию находит акты, которые *изменяют* документ, если его номер есть в их названии.
  Изменяющие акты, которые правят сразу несколько документов, так не находятся.

## Разработка

```bash
# Python: stdio и HTTP
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python server_http.py            # http://localhost:8080/mcp
scripts/smoke.sh http://localhost:8080/mcp

# Cloudflare Worker
cd cloudflare && npm install && npm run dev  # http://localhost:8787/mcp
../scripts/smoke.sh http://localhost:8787/mcp
```

Логика инструментов есть в двух копиях: `pravo_mcp.py` (Python) и `cloudflare/src/pravo.ts` (TypeScript).
Меняя одну, меняйте и другую; CI прогоняет одинаковый смоук-тест на обеих.

---

## English

MCP server for the Russian official legal publication portal
[publication.pravo.gov.ru](http://publication.pravo.gov.ru): search federal laws, presidential decrees
and other acts, get document cards and links to official PDFs. The portal API is open and read-only.

- **Remote, Cloudflare Workers:** [`cloudflare/`](cloudflare/), see [deploy/cloudflare.md](deploy/cloudflare.md).
- **Remote, Docker / Yandex Serverless Containers:** [`server_http.py`](server_http.py), see [deploy/yandex.md](deploy/yandex.md).
- **Local stdio:** [`pravo_mcp.py`](pravo_mcp.py), Python 3.8+, no dependencies.

Add a remote server to Claude via **Settings → Connectors → Add custom connector** with the URL `https://<host>/mcp`.
ChatGPT: Developer mode → new connector, URL `https://<host>/mcp`, no authentication.
Codex: `codex mcp add pravo --url https://<host>/mcp`.

## License

[MIT](LICENSE)
