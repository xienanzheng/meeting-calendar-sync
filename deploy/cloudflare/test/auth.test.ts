import { describe, expect, it } from "vitest";
import { checkBasicAuth, constantTimeEqual } from "../src/auth";

const req = (auth?: string) => new Request("https://x.test/api/health", { headers: auth ? { Authorization: auth } : {} });
const basic = (user: string, pass: string) => `Basic ${btoa(`${user}:${pass}`)}`;

describe("checkBasicAuth", () => {
  it("fails closed when no password is configured", async () => {
    const res = checkBasicAuth(req(basic("a", "b")), undefined)!;
    expect(res.status).toBe(503);
  });
  it("asks for credentials when missing or wrong", () => {
    for (const r of [req(), req("Bearer abc"), req(basic("coordinator", "wrong")), req("Basic !!!notbase64")]) {
      const res = checkBasicAuth(r, "s3cret-pass")!;
      expect(res.status).toBe(401);
      expect(res.headers.get("WWW-Authenticate")).toContain('Basic realm="Meeting Calendar Sync"');
    }
  });
  it("lets the right password through with any user name", () => {
    expect(checkBasicAuth(req(basic("coordinator", "s3cret-pass")), "s3cret-pass")).toBeNull();
    expect(checkBasicAuth(req(basic("", "s3cret-pass")), "s3cret-pass")).toBeNull();
  });
  it("handles passwords containing colons", () => {
    expect(checkBasicAuth(req(basic("u", "a:b:c")), "a:b:c")).toBeNull();
  });
});

describe("constantTimeEqual", () => {
  it("compares exactly", () => {
    expect(constantTimeEqual("abc", "abc")).toBe(true);
    expect(constantTimeEqual("abc", "abd")).toBe(false);
    expect(constantTimeEqual("abc", "abcd")).toBe(false);
    expect(constantTimeEqual("", "")).toBe(true);
  });
});
