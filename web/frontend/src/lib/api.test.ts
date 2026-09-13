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
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe(
      "secure-token",
    );
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

  it("surfaces stable return business error codes and their Arabic message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: "PURCHASE_RETURN_ATTRIBUTABLE_STOCK_INSUFFICIENT",
              message: "المتاح من نفس استلام الشراء أقل من المطلوب",
            },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(api("/returns/documents", { method: "POST" }, false)).rejects.toEqual(
      new ApiError(
        "المتاح من نفس استلام الشراء أقل من المطلوب",
        409,
        "PURCHASE_RETURN_ATTRIBUTABLE_STOCK_INSUFFICIENT",
      ),
    );
  });

  it("surfaces unresolved historical purchase provenance for administrative correction", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: "PURCHASE_RETURN_PROVENANCE_UNRESOLVED",
              message:
                "تعذر إثبات مصدر استلام الشراء التاريخي ويحتاج إلى مراجعة إدارية",
            },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(
      api("/returns/invoices/purchase/1/lines", {}, false),
    ).rejects.toEqual(
      new ApiError(
        "تعذر إثبات مصدر استلام الشراء التاريخي ويحتاج إلى مراجعة إدارية",
        409,
        "PURCHASE_RETURN_PROVENANCE_UNRESOLVED",
      ),
    );
  });

  it("accepts successful responses without a JSON body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );

    await expect(
      api("/manufacturing/orders/1", { method: "DELETE" }),
    ).resolves.toBeUndefined();
  });
});
