import { Container, getContainer } from "@cloudflare/containers";
import { checkAccess } from "./access";
import { checkBasicAuth } from "./auth";

export interface Env {
  MCS: DurableObjectNamespace<McsContainer>;
  APP_PASSWORD?: string;
  ANTHROPIC_API_KEY?: string;
  ACCESS_TEAM_DOMAIN?: string;
  ACCESS_AUD?: string;
  ALLOWED_EMAIL_DOMAINS?: string;
  ALLOWED_EMAILS?: string;
}

export class McsContainer extends Container<Env> {
  defaultPort = 8080;
  sleepAfter = "2h";
  enableInternet = true;

  constructor(ctx: DurableObjectState<{}>, env: Env) {
    super(ctx, env);
    this.envVars = { ANTHROPIC_API_KEY: env.ANTHROPIC_API_KEY ?? "" };
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const blocked = await checkAccess(request, {
      teamDomain: env.ACCESS_TEAM_DOMAIN,
      aud: env.ACCESS_AUD,
      allowedDomains: env.ALLOWED_EMAIL_DOMAINS,
      allowedEmails: env.ALLOWED_EMAILS,
    });
    if (blocked) return blocked;
    const denied = checkBasicAuth(request, env.APP_PASSWORD);
    if (denied) return denied;
    return getContainer(env.MCS, "main").fetch(request);
  },
} satisfies ExportedHandler<Env>;
