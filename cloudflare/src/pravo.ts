// Логика инструментов: порт pravo_mcp.py на TypeScript.
// Держите поведение и схемы синхронными с Python-версией.

export const BASE = "http://publication.pravo.gov.ru";
const UA = "pravo-mcp/1.0 (+https://github.com/ChronoVault/pravo-mcp)";

// Сколько секунд Cloudflare хранит ответы портала в своём кэше.
const TTL_DICT = 24 * 3600; // справочники меняются редко
const TTL_DOC = 7 * 24 * 3600; // карточка неизменна после опубликования
const TTL_SEARCH = 300;

const SORT_FIELDS: Record<string, number> = {
  signing_date: 0,
  doc_type: 1,
  authority: 2,
  number: 3,
  publish_date: 4,
  publish_number: 5,
};
const NUMBER_MODES: Record<string, number> = { exact: 0, starts: 1, ends: 2, contains: 3 };

type Args = Record<string, any>;
type Params = Record<string, unknown>;

// ---------------------------------------------------------------- HTTP

function buildUrl(path: string, params?: Params): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => q.append(k, String(x)));
    else q.append(k, String(v));
  }
  const s = q.toString();
  return BASE + path + (s ? "?" + s : "");
}

async function get(path: string, params: Params | undefined, ttl: number): Promise<[any, string]> {
  const url = buildUrl(path, params);
  const r = await fetch(url, {
    headers: { "User-Agent": UA, Accept: "application/json, */*" },
    cf: { cacheTtl: ttl, cacheEverything: true },
  } as RequestInit);
  if (!r.ok) throw new Error(`HTTP ${r.status} от ${url}`);
  return [await r.json(), url];
}

function toApiDate(v: unknown): string | undefined {
  if (v === undefined || v === null || v === "") return undefined;
  const s = String(v).trim();
  let m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (m) return `${m[3]}.${m[2]}.${m[1]}`;
  m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(s);
  if (m) return s;
  throw new Error(`Дата '${s}': нужен формат YYYY-MM-DD или DD.MM.YYYY`);
}

function eoNumber(a: Args): string {
  const eo = String(a.eo_number ?? "").trim();
  if (!/^\d{16}$/.test(eo)) throw new Error("eo_number — 16-значный номер электронного опубликования");
  return eo;
}

export function docLinks(eo: string) {
  return { card: `${BASE}/document/${eo}`, pdf: `${BASE}/file/pdf?eoNumber=${eo}` };
}

function day(v: unknown): string | null {
  return (typeof v === "string" && v.slice(0, 10)) || null;
}

function short(item: any) {
  const eo = item.eoNumber;
  const out: any = {
    eoNumber: eo,
    complexName: String(item.complexName ?? "").replace(/\n/g, " ").trim(),
    number: item.number,
    documentDate: day(item.documentDate),
    publishDate: day(item.publishDateShort),
    pagesCount: item.pagesCount,
  };
  if (item.jdRegNumber) out.minjustReg = { number: item.jdRegNumber, date: day(item.jdRegDate) };
  if (eo) out.links = docLinks(eo);
  return out;
}

// ---------------------------------------------------------------- tools

async function search(a: Args) {
  let pageSize = a.page_size ?? 30;
  if (![10, 30, 100, 200].includes(pageSize)) pageSize = 30;
  const params: Params = {
    Block: a.block,
    Category: a.category,
    SignatoryAuthorityId: a.signatory_authority_id,
    DocumentTypes: a.document_type_ids,
    EoNumber: a.eo_number,
    Name: a.name,
    DocumentText: a.text,
    Number: a.number,
    NumberSearchType: a.number ? NUMBER_MODES[a.number_mode ?? "exact"] : undefined,
    DocumentDateFrom: toApiDate(a.signed_from),
    DocumentDateTo: toApiDate(a.signed_to),
    PublishDateFrom: toApiDate(a.published_from),
    PublishDateTo: toApiDate(a.published_to),
    JdRegNumber: a.minjust_reg_number,
    PageSize: pageSize,
    Index: a.page ?? 1,
    SortedBy: SORT_FIELDS[a.sort_by ?? "publish_date"] ?? 4,
    SortDestination: a.descending === false ? 0 : 1,
  };
  const [data, url] = await get("/api/Documents", params, TTL_SEARCH);
  return {
    total: data.itemsTotalCount,
    page: data.currentPage,
    pages: data.pagesTotalCount,
    items: (data.items ?? []).map(short),
    query_url: url,
  };
}

async function document(a: Args) {
  const [data] = await get("/api/Document", { eoNumber: eoNumber(a) }, TTL_DOC);
  const out = short(data);
  out.title = String(data.title ?? "").replace(/<br\s*\/?>/gi, " ");
  out.documentType = data.documentType?.name;
  out.signatoryAuthorities = (data.signatoryAuthorities ?? []).map((s: any) => s.name);
  out.hasAttachmentsZip = Boolean(data.zipFileLength);
  return out;
}

async function dictionary(a: Args) {
  switch (a.kind) {
    case "blocks": {
      const [data] = await get("/api/PublicBlocks/", { parent: a.parent }, TTL_DICT);
      const walk = (items: any[]): any[] =>
        (items ?? []).map((i) => ({ code: i.code, name: i.name, children: walk(i.items) }));
      return walk(data);
    }
    case "categories": {
      if (!a.block) throw new Error("для categories нужен block");
      const [data] = await get("/api/Categories", { block: a.block }, TTL_DICT);
      return data.map((i: any) => ({ code: i.code, name: i.name }));
    }
    case "authorities": {
      const [data] = await get("/api/SignatoryAuthorities", { block: a.block, category: a.category }, TTL_DICT);
      return data.map((i: any) => ({ id: i.id, name: i.name }));
    }
    case "document_types": {
      const [data] = await get(
        "/api/DocumentTypes",
        { block: a.block, category: a.category, SignatoryAuthorityId: a.signatory_authority_id },
        TTL_DICT,
      );
      return data.map((i: any) => ({ id: i.id, name: i.name }));
    }
  }
  throw new Error("kind: blocks | categories | authorities | document_types");
}

async function pdfLink(a: Args) {
  const eo = eoNumber(a);
  return {
    eoNumber: eo,
    ...docLinks(eo),
    note: "PDF — скан без текстового слоя: текст из него без OCR не извлекается.",
  };
}

async function stats(a: Args) {
  const period = a.period ?? "daily";
  if (!["daily", "weekly", "monthly"].includes(period)) throw new Error("period: daily | weekly | monthly");
  const [data] = await get(`/api/BlockStatistics/${period}`, undefined, TTL_SEARCH);
  return data;
}

// ---------------------------------------------------------------- schemas

const ro = { readOnlyHint: true, openWorldHint: true };

export const TOOLS = [
  {
    name: "pravo_search",
    description:
      "Поиск официально опубликованных актов на publication.pravo.gov.ru. " +
      "Федеральные законы и указы — block='president' (уточнить вид документа: pravo_dictionary kind=document_types). " +
      "Поиск по названию буквальный: учитывайте падеж (например, 'Налогового кодекса'). " +
      "Даты — YYYY-MM-DD или DD.MM.YYYY. По умолчанию сортировка по дате опубликования, новые сверху.",
    annotations: { title: "Поиск актов", ...ro },
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Фрагмент названия документа" },
        text: { type: "string", description: "Поиск по тексту документа" },
        number: { type: "string", description: "Номер акта, например '585' или '342-ФЗ'" },
        number_mode: { type: "string", enum: Object.keys(NUMBER_MODES) },
        block: {
          type: "string",
          description: "Код блока: president, government, federal_authorities, assembly, court, subjects, international…",
        },
        category: { type: "string" },
        signatory_authority_id: { type: "string" },
        document_type_ids: { type: "array", items: { type: "string" } },
        eo_number: { type: "string", description: "Номер электронного опубликования" },
        signed_from: { type: "string" },
        signed_to: { type: "string" },
        published_from: { type: "string" },
        published_to: { type: "string" },
        minjust_reg_number: { type: "string" },
        page: { type: "integer" },
        page_size: { type: "integer", enum: [10, 30, 100, 200] },
        sort_by: { type: "string", enum: Object.keys(SORT_FIELDS) },
        descending: { type: "boolean" },
      },
    },
  },
  {
    name: "pravo_document",
    description:
      "Карточка документа по номеру электронного опубликования: вид, принявший орган, даты подписания и опубликования, ссылки на карточку и PDF.",
    annotations: { title: "Карточка документа", ...ro },
    inputSchema: { type: "object", properties: { eo_number: { type: "string" } }, required: ["eo_number"] },
  },
  {
    name: "pravo_dictionary",
    description:
      "Справочники API: blocks (блоки публикации), categories (нужен block), authorities (принявшие органы), document_types (виды документов, GUID для pravo_search).",
    annotations: { title: "Справочники", ...ro },
    inputSchema: {
      type: "object",
      properties: {
        kind: { type: "string", enum: ["blocks", "categories", "authorities", "document_types"] },
        block: { type: "string" },
        category: { type: "string" },
        signatory_authority_id: { type: "string" },
        parent: { type: "string" },
      },
      required: ["kind"],
    },
  },
  {
    name: "pravo_pdf_link",
    description: "Ссылки на официальный PDF и HTML-карточку документа по eoNumber. PDF — скан без текстового слоя.",
    annotations: { title: "Ссылка на PDF", ...ro },
    inputSchema: { type: "object", properties: { eo_number: { type: "string" } }, required: ["eo_number"] },
  },
  {
    name: "pravo_stats",
    description: "Сколько документов опубликовано по блокам за период: daily, weekly, monthly.",
    annotations: { title: "Статистика опубликования", ...ro },
    inputSchema: { type: "object", properties: { period: { type: "string", enum: ["daily", "weekly", "monthly"] } } },
  },
];

export const HANDLERS: Record<string, (a: Args) => Promise<unknown>> = {
  pravo_search: search,
  pravo_document: document,
  pravo_dictionary: dictionary,
  pravo_pdf_link: pdfLink,
  pravo_stats: stats,
};
