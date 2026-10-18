const REALM = 'Basic realm="Meeting Calendar Sync", charset="UTF-8"';

export function constantTimeEqual(a: string, b: string): boolean {
  const x = new TextEncoder().encode(a);
  const y = new TextEncoder().encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

export function checkBasicAuth(request: Request, password: string | undefined): Response | null {
  if (!password) {
    return new Response("APP_PASSWORD is not set, so every request is refused.", { status: 503 });
  }
  const [scheme, encoded] = (request.headers.get("Authorization") ?? "").split(" ");
  if (scheme === "Basic" && encoded) {
    let decoded = "";
    try {
      decoded = atob(encoded);
    } catch {
      decoded = "";
    }
    const colon = decoded.indexOf(":");
    if (colon >= 0 && constantTimeEqual(decoded.slice(colon + 1), password)) return null;
  }
  return new Response("Sign in to Meeting Calendar Sync.", { status: 401, headers: { "WWW-Authenticate": REALM } });
}
