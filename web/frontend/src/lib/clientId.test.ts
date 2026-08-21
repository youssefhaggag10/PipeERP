import { afterEach, describe, expect, it, vi } from "vitest";

import { clientId } from "./clientId";

describe("clientId", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses randomUUID when the browser provides it", () => {
    vi.stubGlobal("crypto", { randomUUID: () => "native-id" });
    expect(clientId("sale")).toBe("sale-native-id");
  });

  it("works on mobile HTTP browsers without randomUUID", () => {
    vi.stubGlobal("crypto", {
      getRandomValues: (bytes: Uint8Array) => {
        bytes.fill(7);
        return bytes;
      },
    });
    expect(clientId("purchase")).toMatch(
      /^purchase-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
  });

  it("keeps working when Web Crypto is unavailable", () => {
    vi.stubGlobal("crypto", undefined);
    expect(clientId("return")).toMatch(/^return-[a-z0-9-]+$/);
  });
});
