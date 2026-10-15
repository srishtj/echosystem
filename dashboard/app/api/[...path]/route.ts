// Server-side pass-through to the FastAPI backend. The browser only talks to this
// dashboard's own origin; the backend URL and X-API-Key stay in server-side env
// (API_URL, API_KEY) instead of being compiled into the client bundle.
//
// This does not authenticate dashboard visitors: anyone who can open the dashboard
// can use these routes. Put the dashboard itself behind access control if it is
// reachable from the internet.

const BACKEND_URL = process.env.API_URL ?? 'http://localhost:8000';
const API_KEY = process.env.API_KEY;

async function forward(
  req: Request,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await params;
  const target = `${BACKEND_URL}/api/${path.map(encodeURIComponent).join('/')}${new URL(req.url).search}`;

  const headers = new Headers();
  const contentType = req.headers.get('content-type');
  if (contentType) headers.set('content-type', contentType);
  if (API_KEY) headers.set('X-API-Key', API_KEY);

  const hasBody = req.method !== 'GET' && req.method !== 'HEAD';
  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? await req.text() : undefined,
      cache: 'no-store',
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { 'content-type': upstream.headers.get('content-type') ?? 'application/json' },
    });
  } catch {
    return Response.json({ detail: 'Backend unreachable' }, { status: 502 });
  }
}

export { forward as GET, forward as POST, forward as DELETE };
