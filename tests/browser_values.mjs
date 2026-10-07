import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../src/qsol_workbench/static/app.js", import.meta.url), "utf8");

async function browser(spec = {name: "seed", type: "integer", label: "Seed", required: true},
                       record = {id: "a".repeat(32), action: "fixture", status: "succeeded", stdout: "", stderr: ""}) {
  const elements = new Map(), requests = [], presets = new Map();
  let manifestFixture = {actions: [], connections: []};
  class Element {
    constructor(tag = "div") {
      this.tagName = tag.toUpperCase(); this.children = []; this.value = "";
      this.dataset = {};
      this.type = tag === "select" ? "select-one" : "";
      this.classList = {toggle() {}};
    }
    set type(value) {this._type = value; if (value === "checkbox") this.value = "on";}
    get type() {return this._type;}
    set id(value) {this._id = value; elements.set(value, this);}
    get id() {return this._id;}
    set textContent(value) {this._text = value; this.children = [];}
    get textContent() {return this._text || "";}
    append(...children) {
      if (this.tagName === "SELECT" && !this.children.length && children.length) this.value = children[0].value;
      this.children.push(...children);
    }
  }
  const document = {
    getElementById(id) {if (!elements.has(id)) {const e = new Element(); e.id = id;} return elements.get(id);},
    createElement(tag) {return new Element(tag);}
  };
  const context = vm.createContext({document, URLSearchParams, location: {hash: "", pathname: "/"},
    sessionStorage: {getItem() {return "";}, setItem() {}}, history: {replaceState() {}},
    setInterval() {}, localStorage: {getItem(key) {return presets.get(key) ?? null;}, setItem(key, value) {presets.set(key, value);}},
    async fetch(path, options) {
      requests.push({path, options});
      const data = ["/api/manifest", "/api/refresh"].includes(path) ? manifestFixture : path === "/api/runs" ? [record] : record;
      return {ok: true, async json() {return data;}};
    }});
  vm.runInContext(source, context);
  // Let startup manifest/history requests finish before selecting the fixture.
  await new Promise(resolve => setImmediate(resolve));
  context.fixture = {id: "fixture", title: "Fixture", description: "", schema_sha256: "fixture-hash", fields: [spec]};
  vm.runInContext("choose(fixture)", context);
  return {document, requests, async refresh(action) {
    manifestFixture = {actions: [action], connections: [{id: "qec", status: "available"}]};
    await document.getElementById("refresh").onclick();
  }, async submit(value) {
    if (value !== undefined) document.getElementById("field-" + spec.name).value = value;
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

test("boolean choices submit selected values and restore defaults and presets", async () => {
  for (const value of [true, false]) {
    const b = await browser({name: "enabled", type: "boolean", label: "Enabled", required: true,
      choices: [true, false], default: value});
    const input = b.document.getElementById("field-enabled");
    assert.equal(input.value, String(value));
    await b.submit();
    assert.equal(JSON.parse(b.requests.find(r => r.path === "/api/run").options.body).parameters.enabled, value);
    input.value = String(!value);
    b.document.getElementById("save-preset").onclick();
    input.value = String(value);
    b.document.getElementById("load-preset").onclick();
    assert.equal(input.value, String(!value));
    await b.submit();
    assert.equal(JSON.parse(b.requests.filter(r => r.path === "/api/run").at(-1).options.body).parameters.enabled, !value);
  }
  const b = await browser({name: "enabled", type: "boolean", label: "Enabled", required: true, choices: [true, false]});
  await b.submit("true");
  assert.equal(JSON.parse(b.requests.find(r => r.path === "/api/run").options.body).parameters.enabled, true);
});

test("required boolean checkboxes submit both states and restore presets", async () => {
  for (const value of [true, false]) {
    const b = await browser({name: "enabled", type: "boolean", label: "Enabled", required: true, default: value});
    const input = b.document.getElementById("field-enabled");
    assert.equal(input.required, false);
    assert.equal(input.checked, value);
    input.checked = !value;
    b.document.getElementById("save-preset").onclick();
    input.checked = value;
    b.document.getElementById("load-preset").onclick();
    assert.equal(input.checked, !value);
    await b.submit();
    assert.equal(JSON.parse(b.requests.find(r => r.path === "/api/run").options.body).parameters.enabled, !value);
  }
});

test("history renders legacy inference records without stdout and clears stale output", async () => {
  const record = {id: "b".repeat(32), action: "inference.generate", status: "interrupted", error: "Owner process ended"};
  const b = await browser(undefined, record);
  b.document.getElementById("output").textContent = "stale output";
  b.document.getElementById("record").textContent = "stale record";
  b.document.getElementById("result-view").textContent = "stale artifacts";
  b.document.getElementById("result-view").hidden = false;
  await b.document.getElementById("history").children[0].onclick();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(b.document.getElementById("output").textContent, record.error);
  assert.deepEqual(JSON.parse(b.document.getElementById("record").textContent), record);
  assert.doesNotMatch(b.document.getElementById("notice").textContent, /split/);
  assert.equal(b.document.getElementById("result-view").textContent, "");
  assert.equal(b.document.getElementById("result-view").hidden, true);
});

test("refresh regenerates a newly declared field and submits the new fingerprint", async () => {
  const b = await browser();
  await b.refresh({id: "fixture", title: "Updated", description: "", schema_sha256: "new-fingerprint",
    fields: [{name: "seed", type: "integer", label: "Seed", default: 2},
      {name: "new_option", type: "integer", label: "New option", choices: [7, 9], default: 7}]});
  assert.equal(b.document.getElementById("field-new_option").value, "7");
  b.document.getElementById("field-new_option").value = "9";
  await b.submit();
  const request = JSON.parse(b.requests.find(r => r.path === "/api/run").options.body);
  assert.deepEqual(request.parameters, {seed: 2, new_option: 9});
  assert.equal(request.schema_sha256, "new-fingerprint");
});

test("structured views show backend artifact hashes and validation receipts as text", async () => {
  for (const view of ["artifact-manifest", "validation-receipt"]) {
    const record = {id: "c".repeat(32), action: "qec.fixture", status: "succeeded", stdout: "", stderr: "",
      capability: {output: {view, directory_field: "output"}}, parameters: {output: "relative output"},
      result: {passed: true, files: {"<img src=x onerror=evil>": "a".repeat(64)}}};
    const b = await browser(undefined, record);
    await b.document.getElementById("history").children[0].onclick();
    await new Promise(resolve => setImmediate(resolve));
    const element = b.document.getElementById("result-view");
    assert.equal(element.hidden, false);
    assert.match(element.textContent, view === "artifact-manifest" ? /backend-reported.*\nrelative output/ : /Validation passed/);
    assert.ok(element.textContent.includes("<img src=x onerror=evil>"));
    assert.equal(element.children.length, 0);
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
