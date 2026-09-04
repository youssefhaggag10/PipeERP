import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { BrandMark } from "./BrandMark";

describe("BrandMark", () => {
  it("exposes the product name and Arabic descriptor", () => {
    const markup = renderToStaticMarkup(<BrandMark />);

    expect(markup).toContain("PipeERP");
    expect(markup).toContain("إدارة المصنع بوضوح");
  });

  it("can render a compact mark without hidden copy", () => {
    const markup = renderToStaticMarkup(<BrandMark compact />);

    expect(markup).not.toContain("إدارة المصنع بوضوح");
  });
});
