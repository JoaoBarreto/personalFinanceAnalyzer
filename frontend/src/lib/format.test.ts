import { describe, expect, it } from "vitest";
import { dataPt, eur, mesPt, pct } from "./format";

describe("format", () => {
  it("eur agrupa milhares e usa vírgula", () => {
    expect(eur("1234.56")).toBe("1 234,56 €");
    expect(eur("-1234567.5")).toBe("-1 234 567,50 €");
    expect(eur("0.00")).toBe("0,00 €");
    expect(eur("5")).toBe("5,00 €");
  });
  it("eur não perde precisão em valores grandes", () => {
    expect(eur("12345678901234567.89")).toBe("12 345 678 901 234 567,89 €");
  });
  it("nulos", () => {
    expect(eur(null)).toBe("—");
    expect(pct(null)).toBe("—");
  });
  it("pct, datas e meses", () => {
    expect(pct("73.39")).toBe("73,39 %");
    expect(dataPt("2026-10-05")).toBe("05/10/2026");
    expect(mesPt("2026-10")).toBe("out 2026");
  });
});

import { fromCents, toCents } from "./format";
describe("cêntimos", () => {
  it("ida e volta sem erros de float", () => {
    for (const s of ["0.10", "0.20", "-2.25", "2380.91", "-668.14"]) expect(fromCents(toCents(s))).toBe(s);
    expect(fromCents(toCents("0.10") + toCents("0.20"))).toBe("0.30"); // 0.1+0.2 em float dá 0.30000000000000004
  });
});
