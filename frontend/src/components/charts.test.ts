import { describe, expect, it } from "vitest";
import { niceTicks } from "./charts";

describe("niceTicks", () => {
  it("usa passos redondos e inclui o 0 (valores em cêntimos)", () => {
    expect(niceTicks(-57926, 1000000)).toEqual([-200000, 0, 200000, 400000, 600000, 800000, 1000000]);
    expect(niceTicks(0, 550000).map((c) => c / 100)).toEqual([0, 1000, 2000, 3000, 4000, 5000, 6000]);
  });
  it("lida com tudo a zero", () => {
    expect(niceTicks(0, 0).length).toBeGreaterThan(1);
  });
});
