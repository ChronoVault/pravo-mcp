// Cloudflare Worker: удалённый MCP-сервер (Streamable HTTP, без сессий) на /mcp.
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { HANDLERS, TOOLS } from "./pravo.js";

const INFO = `pravo-mcp — MCP-сервер для publication.pravo.gov.ru

Подключение к Claude: Settings → Connectors → Add custom connector,
адрес: <этот домен>/mcp

https://github.com/ChronoVault/pravo-mcp
`;

function buildServer(): Server {
  const server = new Server({ name: "pravo", version: "1.0.0" }, { capabilities: { tools: {} } });
  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS as any }));
  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const fn = HANDLERS[req.params.name];
    if (!fn) throw new Error(`Неизвестный инструмент ${req.params.name}`);
    try {
      const result = await fn(req.params.arguments ?? {});
      return { content: [{ type: "text", text: JSON.stringify(result, null, 1) }] };
    } catch (e) {
      // ошибка инструмента — отдаём как результат, а не как сбой протокола
      return { content: [{ type: "text", text: `Ошибка: ${(e as Error).message}` }], isError: true };
    }
  });
  return server;
}

export default {
  async fetch(request: Request): Promise<Response> {
    const { pathname } = new URL(request.url);
    if (pathname === "/mcp") {
      // Без сессий: на каждый запрос свой сервер и транспорт, состояние не нужно.
      const transport = new WebStandardStreamableHTTPServerTransport({
        sessionIdGenerator: undefined,
        enableJsonResponse: true,
      });
      await buildServer().connect(transport);
      return transport.handleRequest(request);
    }
    if (pathname === "/") {
      return new Response(INFO, { headers: { "content-type": "text/plain; charset=utf-8" } });
    }
    return new Response("Not found", { status: 404 });
  },
};
