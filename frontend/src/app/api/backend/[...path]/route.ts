import { NextRequest, NextResponse } from "next/server";

function buildBackendUrl(req: NextRequest, path: string[]) {
  const base = process.env.BACKEND_BASE_URL ?? "http://127.0.0.1:7130";
  const url = new URL(base);

  const restPath = path.join("/");
  url.pathname = `/${restPath}`;

  const original = new URL(req.url);
  url.search = original.search;

  return url;
}

async function proxy(req: NextRequest, path: string[]) {
  const backendUrl = buildBackendUrl(req, path);

  const upstream = await fetch(backendUrl, {
    method: req.method,
    headers: req.headers,
    body:
      req.method === "GET" || req.method === "HEAD"
        ? undefined
        : await req.arrayBuffer(),
    redirect: "manual",
  });

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: upstream.headers,
  });
}

async function getPath(ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return path;
}

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  return proxy(req, await getPath(ctx));
}
export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  return proxy(req, await getPath(ctx));
}
export async function PUT(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  return proxy(req, await getPath(ctx));
}
export async function PATCH(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  return proxy(req, await getPath(ctx));
}
export async function DELETE(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  return proxy(req, await getPath(ctx));
}
