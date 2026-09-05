// @vitest-environment jsdom

import { beforeAll, describe, expect, test } from "vitest";

import { getPanelTestHelpers, installPanel } from "./panel-fixture.js";

beforeAll(() => installPanel());

describe("S7 address helpers", () => {
  test("round-trips every supported token into its stable spelling", () => {
    const { PARSE_S7_ADDRESS, SERIALIZE_S7_ADDRESS } = getPanelTestHelpers();
    const cases = [
      ["DB1,X10.3", "DB1,X10.3"], ["I3.0", "I3.0"], ["Q2.6", "Q2.6"],
      ["M7.1", "M7.1"], ["DB36,B2", "DB36,B2"], ["DB1,USINT2", "DB1,USINT2"],
      ["DB1,SINT2", "DB1,SINT2"], ["DB102,C4", "DB102,C4"], ["DB17,W4", "DB17,W4"],
      ["DB10,I3", "DB10,I3"], ["DB51,DW6", "DB51,DW6"], ["DB103,DI3", "DB103,DI3"],
      ["DB21,R14", "DB21,R14"], ["DB21,LR14", "DB21,LR14"], ["DB1,TIME4", "DB1,TIME4"],
      ["DB102,S10.15", "DB102,S10.15"], ["DB2,WS0.128", "DB2,WS0.128"],
      ["IB10", "IB10"], ["QW8", "QW8"], ["MD72", "MDW72"],
    ];

    for (const [source, canonical] of cases) {
      const parsed = PARSE_S7_ADDRESS(source);
      expect(parsed.error, source).toBeUndefined();
      expect(SERIALIZE_S7_ADDRESS(parsed), source).toBe(canonical);
    }
  });

  test("rejects invalid combinations and restricts datatypes by field", () => {
    const { ADDRESS_TYPES_FOR_FIELD, PARSE_S7_ADDRESS, SERIALIZE_S7_ADDRESS } = getPanelTestHelpers();

    expect(PARSE_S7_ADDRESS("DB1,X0.8").error).toBe("invalid");
    expect(PARSE_S7_ADDRESS("DB1,S0").error).toBe("incomplete");
    expect(PARSE_S7_ADDRESS("MTIME0").error).toBe("unsupported");
    expect(PARSE_S7_ADDRESS("DB1,").error).toBe("invalid");
    expect(PARSE_S7_ADDRESS("").empty).toBe(true);
    expect(SERIALIZE_S7_ADDRESS({ empty: true })).toBe("");
    expect(ADDRESS_TYPES_FOR_FIELD("binary_sensors", "address")).toEqual(["BIT"]);
    expect(ADDRESS_TYPES_FOR_FIELD("texts", "address")).toEqual(["STRING", "WSTRING"]);
    expect(ADDRESS_TYPES_FOR_FIELD("selects", "address")).toEqual([
      "BYTE", "USINT", "SINT", "WORD", "INT", "DWORD", "DINT", "TIME",
    ]);
  });

  test("requires every visible component while preserving numeric zero", () => {
    const { ADDRESS_FIELD_VISIBILITY, SERIALIZE_S7_ADDRESS } = getPanelTestHelpers();

    expect([
      ADDRESS_FIELD_VISIBILITY("DB", "BIT"),
      ADDRESS_FIELD_VISIBILITY("I", "STRING"),
      ADDRESS_FIELD_VISIBILITY("Q", "WSTRING"),
      ADDRESS_FIELD_VISIBILITY("M", "INT"),
    ]).toEqual([
      { dbNumber: true, bit: true, length: false },
      { dbNumber: false, bit: false, length: true },
      { dbNumber: false, bit: false, length: true },
      { dbNumber: false, bit: false, length: false },
    ]);
    expect(SERIALIZE_S7_ADDRESS({ area: "DB", dbNumber: "", dataType: "INT", offset: "0" })).toEqual({ error: "incomplete" });
    expect(SERIALIZE_S7_ADDRESS({ area: "M", dataType: "INT", offset: "" })).toEqual({ error: "incomplete" });
    expect(SERIALIZE_S7_ADDRESS({ area: "M", dataType: "BIT", offset: "0", bit: "" })).toEqual({ error: "incomplete" });
    expect(SERIALIZE_S7_ADDRESS({ area: "DB", dbNumber: "1", dataType: "STRING", offset: "0", length: "" })).toEqual({ error: "incomplete" });
    expect(SERIALIZE_S7_ADDRESS({ area: "DB", dbNumber: "0", dataType: "BIT", offset: "0", bit: "0" })).toBe("DB0,X0.0");
  });
});

describe("LOGO address helpers", () => {
  const profile = {
    family: "logo_9",
    vm_last_byte: 850,
    areas: [{ name: "I", first: 1, last: 64, vm_offset: 6024, data_type: "X" }],
    vm_areas: [
      { name: "V", first: 0, last: 850, data_type: "X", width: 1, bit_min: 0, bit_max: 7 },
      { name: "VB", first: 0, last: 850, data_type: "BYTE", width: 1 },
      { name: "VW", first: 0, last: 849, data_type: "WORD", width: 2 },
      { name: "VD", first: 0, last: 847, data_type: "DWORD", width: 4 },
    ],
  };

  test("converts named areas in both directions and rejects gaps", () => {
    const { LOGO_TO_S7, S7_TO_LOGO } = getPanelTestHelpers();

    expect(LOGO_TO_S7(profile, "I1").canonical).toBe("DB1,X6024.0");
    expect(S7_TO_LOGO(profile, "DB1,X6024.0").symbol).toBe("I1");
    expect(LOGO_TO_S7(profile, "I65").error).toBe("address_out_of_range");
    expect(S7_TO_LOGO(profile, "DB1,X6032.0")).toBeNull();
  });

  test("converts VM addresses and identifies only LOGO candidates", () => {
    const { LOGO_ADDRESS_CANDIDATE, LOGO_TO_S7, S7_TO_LOGO } = getPanelTestHelpers();
    const symbols = ["V0.0", "V850.7", "VB850", "VW849", "VD847"];
    expect(symbols.map((value) => LOGO_TO_S7(profile, value).canonical)).toEqual([
      "DB1,X0.0", "DB1,X850.7", "DB1,BYTE850", "DB1,WORD849", "DB1,DWORD847",
    ]);
    expect(["V0", "V0.8", "VB0.0", "VW850", "VD848", "VB-1"].map(
      (value) => LOGO_TO_S7(profile, value).error,
    ).every(Boolean)).toBe(true);
    expect(["DB1,X0.0", "DB1,BYTE10", "DB1,WORD20", "DB1,DWORD30"].map(
      (value) => S7_TO_LOGO(profile, value)?.symbol,
    )).toEqual(["V0.0", "VB10", "VW20", "VD30"]);
    expect(["V0.0", "V0.8", "VW850", "IB10", "QW8", "MD72", "DB1,X0.0"].map(
      (value) => LOGO_ADDRESS_CANDIDATE(profile, value),
    )).toEqual([true, true, true, false, false, false, false]);
  });
});
