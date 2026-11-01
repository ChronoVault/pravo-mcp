#!/usr/bin/env python3
"""
MCP-сервер (stdio) для API «Официальное опубликование правовых актов»
publication.pravo.gov.ru. Только чтение, ключ не нужен.
Без внешних зависимостей: Python 3.8+.

Документация API: http://publication.pravo.gov.ru/help
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

BASE = os.environ.get("PRAVO_BASE", "http://publication.pravo.gov.ru")
DOWNLOAD_DIR = os.environ.get(
    "PRAVO_DOWNLOAD_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads"),
)
UA = "pravo-mcp/1.0 (+https://github.com/ChronoVault/pravo-mcp)"
TIMEOUT = 60
PROTOCOL_VERSION = "2025-03-26"

SORT_FIELDS = {
    "signing_date": 0,
    "doc_type": 1,
    "authority": 2,
    "number": 3,
    "publish_date": 4,
    "publish_number": 5,
}
NUMBER_MODES = {"exact": 0, "starts": 1, "ends": 2, "contains": 3}


# ---------------------------------------------------------------- HTTP

# Кэш ответов в памяти: справочники меняются редко, карточки неизменны после опубликования.
TTL_DICT = 24 * 3600
TTL_DOC = 7 * 24 * 3600
TTL_SEARCH = 300
_CACHE = {}
_CACHE_MAX = 2000


def _cached_get(path, params, ttl):
    key = (path, json.dumps(params, sort_keys=True, ensure_ascii=False, default=str))
    hit = _CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    res = _get(path, params)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = (time.time() + ttl, res)
    return res


def _get(path, params=None, raw=False):
    q = ""
    if params:
        clean = []
        for k, v in params.items():
            if v is None or v == "":
                continue
            if isinstance(v, (list, tuple)):
                clean.extend((k, str(x)) for x in v)
            else:
                clean.append((k, str(v)))
        q = "?" + urllib.parse.urlencode(clean)
    url = BASE + path + q
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, */*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
    if raw:
        return data, url
    return json.loads(data.decode("utf-8")), url


def _date(v):
    """Принимает YYYY-MM-DD или DD.MM.YYYY, отдаёт DD.MM.YYYY (формат API)."""
    if not v:
        return None
    v = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(v, fmt).strftime("%d.%m.%Y")
        except ValueError:
            pass
    raise ValueError(f"Дата {v!r}: нужен формат YYYY-MM-DD или DD.MM.YYYY")


def _doc_links(eo):
    return {
        "card": f"{BASE}/document/{eo}",
        "pdf": f"{BASE}/file/pdf?eoNumber={eo}",
    }


def _short(item):
    eo = item.get("eoNumber")
    out = {
        "eoNumber": eo,
        "complexName": (item.get("complexName") or "").replace("\n", " ").strip(),
        "number": item.get("number"),
        "documentDate": (item.get("documentDate") or "")[:10] or None,
        "publishDate": (item.get("publishDateShort") or "")[:10] or None,
        "pagesCount": item.get("pagesCount"),
    }
    if item.get("jdRegNumber"):
        out["minjustReg"] = {"number": item.get("jdRegNumber"), "date": (item.get("jdRegDate") or "")[:10] or None}
    if eo:
        out["links"] = _doc_links(eo)
    return out


# ---------------------------------------------------------------- tools

def t_search(a):
    params = {
        "Block": a.get("block"),
        "Category": a.get("category"),
        "SignatoryAuthorityId": a.get("signatory_authority_id"),
        "DocumentTypes": a.get("document_type_ids"),
        "EoNumber": a.get("eo_number"),
        "Name": a.get("name"),
        "DocumentText": a.get("text"),
        "Number": a.get("number"),
        "NumberSearchType": NUMBER_MODES.get(a.get("number_mode") or "exact") if a.get("number") else None,
        "DocumentDateFrom": _date(a.get("signed_from")),
        "DocumentDateTo": _date(a.get("signed_to")),
        "PublishDateFrom": _date(a.get("published_from")),
        "PublishDateTo": _date(a.get("published_to")),
        "JdRegNumber": a.get("minjust_reg_number"),
        "PageSize": a.get("page_size") or 30,
        "Index": a.get("page") or 1,
        "SortedBy": SORT_FIELDS.get(a.get("sort_by") or "publish_date", 4),
        "SortDestination": 1 if a.get("descending", True) else 0,
    }
    if params["PageSize"] not in (10, 30, 100, 200):
        params["PageSize"] = 30
    data, url = _cached_get("/api/Documents", params, TTL_SEARCH)
    return {
        "total": data.get("itemsTotalCount"),
        "page": data.get("currentPage"),
        "pages": data.get("pagesTotalCount"),
        "items": [_short(i) for i in data.get("items") or []],
        "query_url": url,
    }


def t_document(a):
    eo = (a.get("eo_number") or "").strip()
    if not re.fullmatch(r"\d{16}", eo):
        raise ValueError("eo_number — 16-значный номер электронного опубликования")
    data, url = _cached_get("/api/Document", {"eoNumber": eo}, TTL_DOC)
    out = _short(data)
    out["title"] = re.sub(r"<br\s*/?>", " ", data.get("title") or "")
    out["documentType"] = (data.get("documentType") or {}).get("name")
    out["signatoryAuthorities"] = [s.get("name") for s in data.get("signatoryAuthorities") or []]
    out["hasAttachmentsZip"] = bool(data.get("zipFileLength"))
    return out


def t_dictionary(a):
    kind = a.get("kind")
    if kind == "blocks":
        data, _ = _cached_get("/api/PublicBlocks/", {"parent": a.get("parent")}, TTL_DICT)
        def walk(items):
            return [{"code": i.get("code"), "name": i.get("name"),
                     "children": walk(i.get("items") or [])} for i in items or []]
        return walk(data)
    if kind == "categories":
        if not a.get("block"):
            raise ValueError("для categories нужен block")
        data, _ = _cached_get("/api/Categories", {"block": a.get("block")}, TTL_DICT)
        return [{"code": i.get("code"), "name": i.get("name")} for i in data]
    if kind == "authorities":
        data, _ = _cached_get("/api/SignatoryAuthorities", {"block": a.get("block"), "category": a.get("category")}, TTL_DICT)
        return [{"id": i.get("id"), "name": i.get("name")} for i in data]
    if kind == "document_types":
        data, _ = _cached_get("/api/DocumentTypes", {"block": a.get("block"), "category": a.get("category"),
                                                     "SignatoryAuthorityId": a.get("signatory_authority_id")}, TTL_DICT)
        return [{"id": i.get("id"), "name": i.get("name")} for i in data]
    raise ValueError("kind: blocks | categories | authorities | document_types")


def t_download_pdf(a):
    eo = (a.get("eo_number") or "").strip()
    if not re.fullmatch(r"\d{16}", eo):
        raise ValueError("eo_number — 16-значный номер электронного опубликования")
    dest = os.path.expanduser(a.get("dest_dir") or DOWNLOAD_DIR)
    os.makedirs(dest, exist_ok=True)
    data, url = _get("/file/pdf", {"eoNumber": eo}, raw=True)
    path = os.path.join(dest, f"{eo}.pdf")
    with open(path, "wb") as f:
        f.write(data)
    return {"path": path, "bytes": len(data), "source": url}


def t_pdf_link(a):
    eo = (a.get("eo_number") or "").strip()
    if not re.fullmatch(r"\d{16}", eo):
        raise ValueError("eo_number — 16-значный номер электронного опубликования")
    return {"eoNumber": eo, **_doc_links(eo),
            "note": "PDF — скан без текстового слоя: текст из него без OCR не извлекается."}


def t_stats(a):
    period = a.get("period") or "daily"
    if period not in ("daily", "weekly", "monthly"):
        raise ValueError("period: daily | weekly | monthly")
    data, _ = _cached_get(f"/api/BlockStatistics/{period}", None, TTL_SEARCH)
    return data


TOOLS = [
    {
        "name": "pravo_search",
        "description": (
            "Поиск официально опубликованных актов на publication.pravo.gov.ru. "
            "Федеральные законы и указы — block='president' (уточнить вид документа: pravo_dictionary kind=document_types). "
            "Поиск по названию буквальный: учитывайте падеж (например, 'Налогового кодекса'). "
            "Даты — YYYY-MM-DD или DD.MM.YYYY. По умолчанию сортировка по дате опубликования, новые сверху."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Фрагмент названия документа"},
                "text": {"type": "string", "description": "Поиск по тексту документа"},
                "number": {"type": "string", "description": "Номер акта, например '585' или '342-ФЗ'"},
                "number_mode": {"type": "string", "enum": list(NUMBER_MODES)},
                "block": {"type": "string", "description": "Код блока: president, government, federal_authorities, assembly, court, subjects, international…"},
                "category": {"type": "string"},
                "signatory_authority_id": {"type": "string"},
                "document_type_ids": {"type": "array", "items": {"type": "string"}},
                "eo_number": {"type": "string", "description": "Номер электронного опубликования"},
                "signed_from": {"type": "string"}, "signed_to": {"type": "string"},
                "published_from": {"type": "string"}, "published_to": {"type": "string"},
                "minjust_reg_number": {"type": "string"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer", "enum": [10, 30, 100, 200]},
                "sort_by": {"type": "string", "enum": list(SORT_FIELDS)},
                "descending": {"type": "boolean"},
            },
        },
    },
    {
        "name": "pravo_document",
        "description": "Карточка документа по номеру электронного опубликования: вид, принявший орган, даты подписания и опубликования, ссылки на карточку и PDF.",
        "inputSchema": {"type": "object", "properties": {"eo_number": {"type": "string"}}, "required": ["eo_number"]},
    },
    {
        "name": "pravo_dictionary",
        "description": "Справочники API: blocks (блоки публикации), categories (нужен block), authorities (принявшие органы), document_types (виды документов, GUID для pravo_search).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["blocks", "categories", "authorities", "document_types"]},
                "block": {"type": "string"}, "category": {"type": "string"},
                "signatory_authority_id": {"type": "string"}, "parent": {"type": "string"},
            },
            "required": ["kind"],
        },
    },
    {
        "name": "pravo_download_pdf",
        "description": "Скачать официальный PDF документа (по eoNumber) в локальную папку и вернуть путь к файлу.",
        "inputSchema": {
            "type": "object",
            "properties": {"eo_number": {"type": "string"}, "dest_dir": {"type": "string"}},
            "required": ["eo_number"],
        },
    },
    {
        "name": "pravo_stats",
        "description": "Сколько документов опубликовано по блокам за период: daily, weekly, monthly.",
        "inputSchema": {"type": "object", "properties": {"period": {"type": "string", "enum": ["daily", "weekly", "monthly"]}}},
    },
]
# Удалённая версия не пишет на диск: вместо pravo_download_pdf отдаёт ссылку.
PDF_LINK_TOOL = {
    "name": "pravo_pdf_link",
    "description": "Ссылки на официальный PDF и HTML-карточку документа по eoNumber. PDF — скан без текстового слоя.",
    "inputSchema": {"type": "object", "properties": {"eo_number": {"type": "string"}}, "required": ["eo_number"]},
}

HANDLERS = {
    "pravo_search": t_search,
    "pravo_document": t_document,
    "pravo_dictionary": t_dictionary,
    "pravo_download_pdf": t_download_pdf,
    "pravo_pdf_link": t_pdf_link,
    "pravo_stats": t_stats,
}


# ---------------------------------------------------------------- JSON-RPC over stdio

def _send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _handle(req):
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        return {"protocolVersion": req.get("params", {}).get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "pravo", "version": "1.0.0"}}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        p = req.get("params") or {}
        fn = HANDLERS.get(p.get("name"))
        if not fn:
            raise KeyError(f"Неизвестный инструмент {p.get('name')}")
        try:
            result = fn(p.get("arguments") or {})
            text = json.dumps(result, ensure_ascii=False, indent=1)
            return {"content": [{"type": "text", "text": text}]}
        except Exception as e:  # ошибка инструмента — отдаём как результат, а не как сбой протокола
            return {"content": [{"type": "text", "text": f"Ошибка: {e}"}], "isError": True}
    if method == "ping":
        return {}
    if rid is None:  # уведомления (notifications/initialized и т.п.)
        return None
    raise KeyError(f"Метод {method} не поддерживается")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = req.get("id")
        try:
            res = _handle(req)
            if rid is not None and res is not None:
                _send({"jsonrpc": "2.0", "id": rid, "result": res})
        except Exception as e:
            if rid is not None:
                _send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": str(e)}})


def selftest():
    r = t_search({"block": "president", "number": "585", "signed_from": "2023-08-01", "signed_to": "2023-08-31"})
    print("Поиск Указа № 585 от 08.08.2023:", r["total"], "док.")
    for i in r["items"]:
        print(" ", i["eoNumber"], i["complexName"][:110])
    if r["items"]:
        d = t_document({"eo_number": r["items"][0]["eoNumber"]})
        print("Карточка:", d["documentType"], "| опубликован", d["publishDate"], "|", d["links"]["pdf"])
    print("OK" if r["total"] else "Пусто — проверьте доступ к publication.pravo.gov.ru")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
