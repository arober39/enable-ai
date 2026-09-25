import assert from "node:assert/strict";
import { test } from "node:test";

import { visiblePickerItems } from "./pickerItems.ts";

const roles = [
  "customer_success",
  "devrel",
  "marketing",
  "support",
  "travel_coordinator",
];

test("a researched role past the preview stays visible and first", () => {
  const shown = visiblePickerItems({
    items: roles,
    query: "",
    matches: (item, query) => item.includes(query),
    isSelected: (item) => item === "travel_coordinator",
    previewCount: 3,
    pinSelected: true,
  });
  assert.equal(shown[0], "travel_coordinator");
  assert.ok(shown.includes("travel_coordinator"));
  assert.equal(shown.length, 4);
});

test("a researched tool stays in the list after the query is cleared", () => {
  const tools = ["alpha", "beta", "gamma", "navan"];
  const shown = visiblePickerItems({
    items: tools,
    query: "",
    matches: (item, query) => item.includes(query),
    isSelected: (item) => item === "navan",
    previewCount: 3,
    pinSelected: true,
  });
  assert.equal(shown[0], "navan");
  assert.ok(shown.includes("navan"));
});

test("selected rows stay visible while a search does not match them", () => {
  const shown = visiblePickerItems({
    items: roles,
    query: "zzz",
    matches: (item, query) => item.includes(query),
    isSelected: (item) => item === "travel_coordinator",
    previewCount: 3,
    pinSelected: true,
  });
  assert.deepEqual(shown, ["travel_coordinator"]);
});
