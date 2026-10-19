import { beforeAll, describe, expect, it } from "vitest";
import { SignJWT, createLocalJWKSet, exportJWK, generateKeyPair, type JWTVerifyGetKey } from "jose";
import { checkAccess, emailAllowed, type AccessConfig } from "../src/access";

const TEAM = "https://woodline-test.cloudflareaccess.com";
const AUD = "aud-tag-123";
const cfg: AccessConfig = { teamDomain: TEAM, aud: AUD, allowedDomains: "woodlinepartners.com", allowedEmails: "owner@gmail.com" };

let getKey: JWTVerifyGetKey;
let privateKey: CryptoKey;
let otherKey: CryptoKey;

beforeAll(async () => {
  const pair = await generateKeyPair("RS256");
  privateKey = pair.privateKey;
  otherKey = (await generateKeyPair("RS256")).privateKey;
  const jwk = { ...(await exportJWK(pair.publicKey)), kid: "k1", alg: "RS256" };
  getKey = createLocalJWKSet({ keys: [jwk] });
});

type Claims = { email?: string; iss?: string; aud?: string; exp?: string; key?: CryptoKey };
const token = ({ email = "analyst@woodlinepartners.com", iss = TEAM, aud = AUD, exp = "1h", key }: Claims = {}) =>
  new SignJWT({ email })
    .setProtectedHeader({ alg: "RS256", kid: "k1" })
    .setIssuer(iss)
    .setAudience(aud)
    .setIssuedAt()
    .setExpirationTime(exp)
    .sign(key ?? privateKey);

const req = (jwt?: string) =>
  new Request("https://woodlinepartners.night-zone.com/", { headers: jwt ? { "Cf-Access-Jwt-Assertion": jwt } : {} });

describe("checkAccess", () => {
  it("fails closed when Access is not configured", async () => {
    for (const partial of [{}, { teamDomain: TEAM }, { aud: AUD }]) {
      const res = (await checkAccess(req(await token()), partial, getKey))!;
      expect(res.status).toBe(503);
    }
  });

  it("refuses requests that did not come through Access", async () => {
    expect((await checkAccess(req(), cfg, getKey))!.status).toBe(403);
    expect((await checkAccess(req("not.a.jwt"), cfg, getKey))!.status).toBe(403);
  });

  it("refuses tokens with a bad signature, audience, issuer or expiry", async () => {
    const bad = [
      await token({ key: otherKey }),
      await token({ aud: "another-app" }),
      await token({ iss: "https://evil.cloudflareaccess.com" }),
      await token({ exp: "-1m" }),
    ];
    for (const jwt of bad) expect((await checkAccess(req(jwt), cfg, getKey))!.status).toBe(403);
  });

  it("lets a valid Woodline login through, ignoring case", async () => {
    expect(await checkAccess(req(await token()), cfg, getKey)).toBeNull();
    expect(await checkAccess(req(await token({ email: "CR@WoodlinePartners.com" })), cfg, getKey)).toBeNull();
  });

  it("lets an explicitly allowed address through", async () => {
    expect(await checkAccess(req(await token({ email: "owner@gmail.com" })), cfg, getKey)).toBeNull();
  });

  it("refuses valid logins from addresses outside the allowlist", async () => {
    for (const email of ["someone@gmail.com", "x@evil-woodlinepartners.com", "x@woodlinepartners.com.evil.com", ""]) {
      expect((await checkAccess(req(await token({ email })), cfg, getKey))!.status).toBe(403);
    }
  });
});

describe("emailAllowed", () => {
  it("matches whole domains and exact addresses only", () => {
    expect(emailAllowed("a@woodlinepartners.com", "woodlinepartners.com", "")).toBe(true);
    expect(emailAllowed("a@mail.woodlinepartners.com", "woodlinepartners.com", "")).toBe(false);
    expect(emailAllowed("a@woodlinepartners.co", "woodlinepartners.com", "")).toBe(false);
    expect(emailAllowed("owner@gmail.com", "woodlinepartners.com", " owner@gmail.com , x@y.com")).toBe(true);
    expect(emailAllowed("owner@gmail.com.au", "", "owner@gmail.com")).toBe(false);
    expect(emailAllowed("", "", "")).toBe(false);
  });
});
