import { describe, expect, it } from "vitest";

import { label, pct, worst } from "./report";

describe("report helpers", () => {
  it("orders statuses worst first", () => {
    expect(worst(["pass", "warn", "n/a"])).toBe("warn");
    expect(worst(["pass", "fail", "crash"])).toBe("crash");
    expect(worst([])).toBe("none");
  });
  it("formats", () => {
    expect(pct(0.517)).toBe("52%");
    expect(label("cache_double_count")).toBe("cache double count");
  });
});
