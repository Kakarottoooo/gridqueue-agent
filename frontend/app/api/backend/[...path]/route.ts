import { NextRequest } from "next/server";

function backendUrl() {
  if (process.env.BACKEND_API_URL) {
    return process.env.BACKEND_API_URL;
  }

  if (process.env.BACKEND_API_HOST) {
    const port = process.env.BACKEND_API_PORT ? `:${process.env.BACKEND_API_PORT}` : "";
    return `http://${process.env.BACKEND_API_HOST}${port}`;
  }

  return "http://127.0.0.1:8000";
}

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function forward(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const sourceUrl = new URL(request.url);
  const target = new URL(path.join("/"), `${backendUrl().replace(/\/$/, "")}/`);
  target.search = sourceUrl.search;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  const response = await fetch(target, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
    cache: "no-store"
  });

  return new Response(await response.arrayBuffer(), {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json"
    }
  });
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const DELETE = forward;
