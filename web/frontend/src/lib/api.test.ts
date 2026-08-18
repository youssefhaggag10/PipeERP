import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./api";

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends credentials and the double-submit CSRF token for mutations", async () => {
    Object.defineProperty(globalThis, "document", {
      value: { cookie: "pipeerp_csrf=secure-token" },
      configurable: true,
    });
    const request = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", request);

    await api("/identity/users", { method: "POST", body: "{}" });

    expect(request).toHaveBeenCalledTimes(1);
    const [, options] = request.mock.calls[0] as [string, RequestInit];
    expect(options.credentials).toBe("include");
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("secure-token");
  });

  it("surfaces the Arabic API error without hiding its status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "ليست لديك صلاحية" }), {
          status: 403,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(api("/identity/users", {}, false)).rejects.toEqual(
      new ApiError("ليست لديك صلاحية", 403),
    );
  });
});
