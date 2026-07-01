import { NextRequest } from "next/server";

// Server-side proxy for /api/* -> the backend. Replaces the next.config.js
// rewrite so we can inject a shared secret header that never reaches the
// browser. BACKEND_URL + BACKEND_API_KEY are server-only env vars (NOT
// NEXT_PUBLIC_*), read at request time.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:3001";
const BACKEND_API_KEY = process.env.BACKEND_API_KEY ?? "";

export const dynamic = "force-dynamic";

async function proxy(req: NextRequest, path: string[]): Promise<Response> {
  const target = `${BACKEND_URL}/api/${path.join("/")}${req.nextUrl.search}`;

  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("connection");
  if (BACKEND_API_KEY) headers.set("x-backend-key", BACKEND_API_KEY);

  const init: RequestInit = { method: req.method, headers, redirect: "manual" };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  const resp = await fetch(target, init);

  // Strip hop-by-hop / length headers that don't survive re-streaming.
  const respHeaders = new Headers(resp.headers);
  respHeaders.delete("content-encoding");
  respHeaders.delete("content-length");
  respHeaders.delete("transfer-encoding");

  return new Response(resp.body, { status: resp.status, headers: respHeaders });
}

type Ctx = { params: { path: string[] } };

export function GET(req: NextRequest, { params }: Ctx) {
  return proxy(req, params.path);
}
export function POST(req: NextRequest, { params }: Ctx) {
  return proxy(req, params.path);
}
export function PUT(req: NextRequest, { params }: Ctx) {
  return proxy(req, params.path);
}
export function PATCH(req: NextRequest, { params }: Ctx) {
  return proxy(req, params.path);
}
export function DELETE(req: NextRequest, { params }: Ctx) {
  return proxy(req, params.path);
}
export function HEAD(req: NextRequest, { params }: Ctx) {
  return proxy(req, params.path);
}
