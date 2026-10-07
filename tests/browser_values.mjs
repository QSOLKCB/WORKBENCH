import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../src/qsol_workbench/static/app.js", import.meta.url), "utf8");

async function browser(spec = {name: "seed", type: "integer", label: "Seed", required: true}) {
  const elements = new Map(), requests = [];
  class Element {
    constructor() {this.children = []; this.value = ""; this.classList = {toggle() {}};}
    set id(value) {this._id = value; elements.set(value, this);}
    get id() {return this._id;}
    set textContent(value) {this._text = value; this.children = [];}
    get textContent() {return this._text || "";}
    append(...children) {this.children.push(...children);}
  }
  const document = {
    getElementById(id) {if (!elements.has(id)) {const e = new Element(); e.id = id;} return elements.get(id);},
    createElement() {return new Element();}
  };
  const context = vm.createContext({document, URLSearchParams, location: {hash: "", pathname: "/"},
    sessionStorage: {getItem() {return "";}, setItem() {}}, history: {replaceState() {}},
    setInterval() {}, localStorage: {getItem() {return null;}, setItem() {}},
    async fetch(path, options) {
      requests.push({path, options});
      const data = path === "/api/manifest" ? {actions: [], connections: []} : path === "/api/runs" ? [] :
        {id: "a".repeat(32), action: "fixture", status: "succeeded", stdout: "", stderr: ""};
      return {ok: true, async json() {return data;}};
    }});
  vm.runInContext(source, context);
  // Let startup manifest/history requests finish before selecting the fixture.
  await new Promise(resolve => setImmediate(resolve));
  context.fixture = {id: "fixture", title: "Fixture", description: "", schema_sha256: "fixture-hash", fields: [spec]};
  vm.runInContext("choose(fixture)", context);
  return {document, requests, async submit(value) {
    if (value !== undefined) document.getElementById("field-seed").value = value;
    await document.getElementById("form").onsubmit({preventDefault() {}});
  }};
}

test("browser sends the exact safe integer boundaries", async () => {
  for (const value of ["9007199254740991", "-9007199254740991", "42", "+00042"]) {
    const b = await browser();
    await b.submit(value);
    const run = b.requests.find(r => r.path === "/api/run");
    assert.ok(run);
    assert.equal(JSON.parse(run.options.body).parameters.seed, Number(BigInt(value)));
  }
});

test("browser rejects unsafe 64-bit integer inputs before dispatch", async () => {
  for (const value of ["9007199254740992", "9007199254740993", "9223372036854775807", "-9223372036854775808"]) {
    const b = await browser();
    await b.submit(value);
    assert.equal(b.requests.filter(r => r.path === "/api/run").length, 0);
    assert.match(b.document.getElementById("notice").textContent, /safe integer range/);
  }
});

test("browser rejects fractional strings that Number would round to integers", async () => {
  for (const value of ["9007199254740990.5", "1.0000000000000000001", "1e3", ""]) {
    const b = await browser();
    await b.submit(value);
    assert.equal(b.requests.filter(r => r.path === "/api/run").length, 0);
    assert.match(b.document.getElementById("notice").textContent, /whole decimal integer/);
  }
});

test("unsafe JSON defaults and choices cannot dispatch a rounded value", async () => {
  for (const spec of [
    JSON.parse('{"name":"seed","type":"integer","label":"Seed","default":9223372036854775807}'),
    JSON.parse('{"name":"seed","type":"integer","label":"Seed","default":9223372036854775807,"choices":[9223372036854775807]}')
  ]) {
    const b = await browser(spec);
    await b.submit();
    assert.equal(b.requests.filter(r => r.path === "/api/run").length, 0);
    assert.match(b.document.getElementById("notice").textContent, /safe integer range/);
  }
});
