import { describe, expect, it } from "vitest";

import { buildPartnerPayload } from "./partnerPayload";

describe("partner payload", () => {
  it("never sends the hidden legacy tax number", () => {
    const payload = buildPartnerPayload({
      code: "CUS-1",
      name_ar: "عميل",
      phone: "0100",
      address: "القاهرة",
      is_customer: true,
      is_supplier: false,
      version: 2,
      is_active: true,
    });

    expect(payload).not.toHaveProperty("tax_number");
  });
});
