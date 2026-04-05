import { describe, expect, it } from "vitest";

import { buildAssetUrl, cardAssetUrl, gemAssetUrl, nobleAssetUrl } from "./assets";

describe("asset helpers", () => {
  it("builds stable asset urls against the backend origin", () => {
    expect(buildAssetUrl("/assets/gems/diamond.png", "http://127.0.0.1:8000")).toBe(
      "http://127.0.0.1:8000/assets/gems/diamond.png",
    );
    expect(gemAssetUrl("white", "http://127.0.0.1:8000")).toContain("/assets/gems/diamond.png");
  });

  it("returns card and noble urls only when asset ids are present", () => {
    expect(cardAssetUrl({ asset_id: "level_one0", masked: false }, "http://127.0.0.1:8000")).toBe(
      "http://127.0.0.1:8000/assets/cards/level_one0.png",
    );
    expect(cardAssetUrl({ asset_id: "level_one0", masked: true }, "http://127.0.0.1:8000")).toBeNull();
    expect(nobleAssetUrl({ asset_id: "noble0" }, "http://127.0.0.1:8000")).toBe(
      "http://127.0.0.1:8000/assets/nobles/noble0.png",
    );
  });
});
