#!/bin/bash
# Смоук-тест удалённого MCP-сервера: initialize, tools/list, поиск Указа № 585, карточка, ошибка, справочник.
# Использование: scripts/smoke.sh [http://localhost:8080/mcp]
set -euo pipefail
U="${1:-http://localhost:8080/mcp}"

rpc() {
  curl -sS -f -m 60 -X POST "$U" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "MCP-Protocol-Version: 2025-06-18" \
    -d "$1"
}
check() { python3 -c "import json,sys; r=json.load(sys.stdin)['result']; $1"; }

rpc '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
  | check 'print("server:", r["serverInfo"])'

rpc '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | check 'n=sorted(t["name"] for t in r["tools"]); print("tools:", n); assert n==["pravo_dictionary","pravo_document","pravo_pdf_link","pravo_search","pravo_stats"]'

rpc '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"pravo_search","arguments":{"block":"president","number":"585","signed_from":"2023-08-01","signed_to":"2023-08-31"}}}' \
  | check 'd=json.loads(r["content"][0]["text"]); print("search:", d["total"], d["items"][0]["complexName"][:70]); assert d["items"][0]["eoNumber"]=="0001202308080005"'

rpc '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"pravo_document","arguments":{"eo_number":"0001202308080005"}}}' \
  | check 'd=json.loads(r["content"][0]["text"]); print("document:", d["documentType"], d["publishDate"]); assert d["publishDate"]=="2023-08-08"'

rpc '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"pravo_document","arguments":{"eo_number":"123"}}}' \
  | check 'print("bad input -> isError:", r.get("isError")); assert r.get("isError") is True'

rpc '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"pravo_dictionary","arguments":{"kind":"blocks"}}}' \
  | check 'd=json.loads(r["content"][0]["text"]); c=[b["code"] for b in d]; print("blocks:", c[:6]); assert "president" in c'

echo "OK: $U"
