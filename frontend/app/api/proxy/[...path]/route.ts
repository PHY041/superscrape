import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.BACKEND_URL ?? "http://localhost:8000";

function buildBackendUrl(pathParts: string[], searchParams: URLSearchParams): string {
  const path = pathParts.join("/");
  const qs = searchParams.toString();
  return qs
    ? `${BACKEND_URL}/${path}?${qs}`
    : `${BACKEND_URL}/${path}`;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
type RouteContext = { params: any };

export async function GET(request: NextRequest, context: RouteContext) {
  const resolvedParams = await Promise.resolve(context.params);
  const pathParts: string[] = resolvedParams.path;
  const url = buildBackendUrl(pathParts, request.nextUrl.searchParams);
  const isStream = url.includes("/stream");

  try {
    const backendRes = await fetch(url, {
      headers: {
        Accept: isStream ? "text/event-stream" : "application/json",
      },
      cache: "no-store",
    });

    if (isStream) {
      return new NextResponse(backendRes.body, {
        status: backendRes.status,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          "X-Accel-Buffering": "no",
          Connection: "keep-alive",
        },
      });
    }

    const contentType = backendRes.headers.get("content-type") ?? "";

    if (contentType.includes("text/html")) {
      const html = await backendRes.text();
      return new NextResponse(html, {
        status: backendRes.status,
        headers: { "Content-Type": "text/html; charset=utf-8" },
      });
    }

    if (contentType.includes("application/pdf")) {
      return new NextResponse(backendRes.body, {
        status: backendRes.status,
        headers: {
          "Content-Type": "application/pdf",
          "Content-Disposition": backendRes.headers.get("content-disposition") ?? "attachment",
        },
      });
    }

    // Handle ZIP / octet-stream (exports)
    if (contentType.includes("application/zip") || contentType.includes("application/octet-stream")) {
      return new NextResponse(backendRes.body, {
        status: backendRes.status,
        headers: {
          "Content-Type": contentType,
          "Content-Disposition": backendRes.headers.get("content-disposition") ?? "attachment",
        },
      });
    }

    const data = await backendRes.json().catch(() => null);
    return NextResponse.json(data, { status: backendRes.status });
  } catch (err) {
    return NextResponse.json(
      { error: "Backend unreachable", detail: String(err) },
      { status: 502 }
    );
  }
}

export async function POST(request: NextRequest, context: RouteContext) {
  const resolvedParams = await Promise.resolve(context.params);
  const pathParts: string[] = resolvedParams.path;
  const url = buildBackendUrl(pathParts, request.nextUrl.searchParams);

  let body: BodyInit | null = null;
  const headers: Record<string, string> = {};
  const contentType = request.headers.get("content-type") ?? "";

  if (contentType.includes("multipart/form-data")) {
    // Stream multipart body directly to preserve boundary
    body = request.body;
    headers["content-type"] = contentType;
  } else if (contentType.includes("application/json")) {
    body = await request.text();
    headers["content-type"] = "application/json";
  }

  try {
    const backendRes = await fetch(url, {
      method: "POST",
      headers,
      body: body ?? undefined,
      cache: "no-store",
    });

    const data = await backendRes.json().catch(() => null);
    return NextResponse.json(data, { status: backendRes.status });
  } catch (err) {
    return NextResponse.json(
      { error: "Backend unreachable", detail: String(err) },
      { status: 502 }
    );
  }
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  const resolvedParams = await Promise.resolve(context.params);
  const pathParts: string[] = resolvedParams.path;
  const url = buildBackendUrl(pathParts, request.nextUrl.searchParams);

  try {
    const backendRes = await fetch(url, {
      method: "DELETE",
      cache: "no-store",
    });

    const data = await backendRes.json().catch(() => null);
    return NextResponse.json(data, { status: backendRes.status });
  } catch (err) {
    return NextResponse.json(
      { error: "Backend unreachable", detail: String(err) },
      { status: 502 }
    );
  }
}
