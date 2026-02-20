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

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  const url = buildBackendUrl(params.path, request.nextUrl.searchParams);
  const isStream = url.includes("/stream");

  const backendRes = await fetch(url, {
    headers: {
      Accept: isStream ? "text/event-stream" : "application/json",
    },
    // Disable Next.js caching for streaming / real-time endpoints
    cache: "no-store",
  });

  if (isStream) {
    // Forward the SSE stream body directly
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

  // Forward HTML responses as-is (e.g. report pages)
  if (contentType.includes("text/html")) {
    const html = await backendRes.text();
    return new NextResponse(html, {
      status: backendRes.status,
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  }

  // Forward PDF responses as-is
  if (contentType.includes("application/pdf")) {
    return new NextResponse(backendRes.body, {
      status: backendRes.status,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": backendRes.headers.get("content-disposition") ?? "attachment",
      },
    });
  }

  const data = await backendRes.json().catch(() => null);
  return NextResponse.json(data, { status: backendRes.status });
}

export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  const url = buildBackendUrl(params.path, request.nextUrl.searchParams);

  let body: BodyInit | null = null;
  const contentType = request.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    body = await request.text();
  }

  const backendRes = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: body ?? undefined,
    cache: "no-store",
  });

  const data = await backendRes.json().catch(() => null);
  return NextResponse.json(data, { status: backendRes.status });
}
