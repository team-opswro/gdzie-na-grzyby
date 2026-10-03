import { test } from "node:test";
import assert from "node:assert/strict";
import { reserveText, ZAKAZY_URL } from "../js/popup.js";

test("reserveText with and without name", () => {
  assert.equal(reserveText("Góra Św. Anny"),
    "Rezerwat przyrody „Góra Św. Anny” — zbieranie grzybów jest co do zasady zabronione.");
  assert.equal(reserveText("rezerwat"),
    "Rezerwat przyrody — zbieranie grzybów jest co do zasady zabronione.");
});
test("zakazy URL", () => assert.equal(ZAKAZY_URL, "https://zakazywstepu.bdl.lasy.gov.pl/zakazy/"));
