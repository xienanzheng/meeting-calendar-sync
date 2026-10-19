import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey } from "jose";

export interface AccessConfig {
  teamDomain?: string; // e.g. https://<team>.cloudflareaccess.com
  aud?: string; // the Access application's Audience (AUD) tag
  allowedDomains?: string; // comma-separated, e.g. "woodlinepartners.com"
  allowedEmails?: string; // comma-separated exact addresses
}

const list = (csv: string | undefined) =>
  (csv ?? "")
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

export function emailAllowed(email: string, allowedDomains?: string, allowedEmails?: string): boolean {
  const e = email.trim().toLowerCase();
  if (!e.includes("@")) return false;
  if (list(allowedEmails).includes(e)) return true;
  const domain = e.slice(e.lastIndexOf("@") + 1);
  return list(allowedDomains).includes(domain);
}

const jwksByTeam = new Map<string, JWTVerifyGetKey>();
function remoteKeys(teamDomain: string): JWTVerifyGetKey {
  let keys = jwksByTeam.get(teamDomain);
  if (!keys) {
    keys = createRemoteJWKSet(new URL(`${teamDomain}/cdn-cgi/access/certs`));
    jwksByTeam.set(teamDomain, keys);
  }
  return keys;
}

const forbidden = () => new Response("Sign in through Woodline's Cloudflare Access first.", { status: 403 });

// Second line of defence behind the Cloudflare Access policy: only requests carrying a valid
// Access token for this application, from an allowed address, reach the password check.
export async function checkAccess(request: Request, cfg: AccessConfig, getKey?: JWTVerifyGetKey): Promise<Response | null> {
  const teamDomain = cfg.teamDomain?.replace(/\/+$/, "");
  if (!teamDomain || !cfg.aud) {
    return new Response("Cloudflare Access is not configured, so every request is refused.", { status: 503 });
  }
  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) return forbidden();
  try {
    const { payload } = await jwtVerify(token, getKey ?? remoteKeys(teamDomain), {
      issuer: teamDomain,
      audience: cfg.aud,
      algorithms: ["RS256"],
    });
    const email = typeof payload.email === "string" ? payload.email : "";
    return emailAllowed(email, cfg.allowedDomains, cfg.allowedEmails) ? null : forbidden();
  } catch {
    return forbidden();
  }
}
