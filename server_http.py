#!/usr/bin/env python3
"""
Удалённый MCP-сервер (Streamable HTTP, без сессий) для publication.pravo.gov.ru.
Логика инструментов — из pravo_mcp.py. Эндпоинт: /mcp.

Запуск: pip install -r requirements.txt && python server_http.py
Порт берётся из переменной PORT (так его передаёт Yandex Serverless Containers), по умолчанию 8080.
"""
import json
import os

import anyio
import mcp_types as types
import uvicorn
from mcp.server.lowlevel import Server
from starlette.responses import PlainTextResponse
from starlette.routing import Route

import pravo_mcp

# Удалённо файлы не скачиваем: pravo_download_pdf заменён на pravo_pdf_link.
TOOL_DEFS = [t for t in pravo_mcp.TOOLS if t["name"] != "pravo_download_pdf"] + [pravo_mcp.PDF_LINK_TOOL]
TOOLS = [
    types.Tool(
        name=t["name"],
        description=t["description"],
        input_schema=t["inputSchema"],
        annotations=types.ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    for t in TOOL_DEFS
]

INFO = """pravo-mcp — MCP-сервер для publication.pravo.gov.ru

Подключение к Claude: Settings → Connectors → Add custom connector,
адрес: <этот домен>/mcp

https://github.com/ChronoVault/pravo-mcp
"""


async def list_tools(ctx, params):
    return types.ListToolsResult(tools=TOOLS)


async def call_tool(ctx, params):
    fn = pravo_mcp.HANDLERS.get(params.name)
    if not fn or params.name == "pravo_download_pdf":
        raise ValueError(f"Неизвестный инструмент {params.name}")
    try:
        # urllib блокирующий — уводим в поток, чтобы не держать event loop
        result = await anyio.to_thread.run_sync(fn, params.arguments or {})
        text = json.dumps(result, ensure_ascii=False, indent=1)
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)])
    except Exception as e:  # ошибка инструмента — отдаём как результат, а не как сбой протокола
        return types.CallToolResult(content=[types.TextContent(type="text", text=f"Ошибка: {e}")], is_error=True)


server = Server("pravo", version="1.0.0", on_list_tools=list_tools, on_call_tool=call_tool)


async def info(request):
    return PlainTextResponse(INFO)


app = server.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",  # публичный сервер: защита от DNS rebinding для localhost не нужна
    custom_starlette_routes=[Route("/", info)],
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
