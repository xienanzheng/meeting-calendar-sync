import { Container, getContainer } from "@cloudflare/containers";
import { checkBasicAuth } from "./auth";

export interface Env {
  MCS: DurableObjectNamespace<McsContainer>;
  APP_PASSWORD?: string;
  ANTHROPIC_API_KEY?: string;
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
    const denied = checkBasicAuth(request, env.APP_PASSWORD);
    if (denied) return denied;
    return getContainer(env.MCS, "main").fetch(request);
  },
} satisfies ExportedHandler<Env>;
