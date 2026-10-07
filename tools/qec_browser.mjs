// Real Chromium form acceptance; Node >=22. No backend dispatch logic here.
// URL is supplied privately in WORKBENCH_URL and is never written to evidence.
import {spawn, spawnSync} from "node:child_process";
import {mkdtemp, readFile, writeFile, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";

const [casesFile, receiptFile, timeoutText = "120"] = process.argv.slice(2);
const url = process.env.WORKBENCH_URL, binary = process.env.BROWSER_BIN || "google-chrome";
if (!url || !casesFile || !receiptFile) throw new Error("Supply cases, receipt and WORKBENCH_URL");
const cases = JSON.parse(await readFile(casesFile, "utf8"));
const receipt = {engine: spawnSync(binary, ["--version"], {encoding: "utf8"}).stdout.trim(),
  status: "running", transport: "real Chromium DOM form submission", runs: [], exceptions: []};
const profile = await mkdtemp(join(tmpdir(), "qsol-qec-browser-"));
const browser = spawn(binary, ["--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
  "--remote-debugging-port=0", "--user-data-dir=" + profile, "--no-first-run", "about:blank"], {stdio: "ignore"});
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const pending = new Map();
let socket, sequence = 0;
browser.on("error", e => receipt.exceptions.push(String(e)));
try {
  let port;
  for (let i = 0; i < 100; i++) {
    try {port = (await readFile(join(profile, "DevToolsActivePort"), "utf8")).split("\n")[0]; break;}
    catch {await pause(100);}
  }
  if (!port) throw new Error("Browser did not start: " + receipt.exceptions.join("; "));
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(pages.find(p => p.type === "page").webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {socket.onopen = resolve; socket.onerror = reject;});
  socket.onmessage = event => {
    const data = JSON.parse(event.data);
    if (data.id && pending.has(data.id)) {
      const item = pending.get(data.id); clearTimeout(item.timer); pending.delete(data.id);
      if (data.error) item.reject(new Error(JSON.stringify(data.error))); else item.resolve(data.result);
    } else if (data.method === "Runtime.exceptionThrown") receipt.exceptions.push(JSON.stringify(data.params));
  };
  const call = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => {pending.delete(id); reject(new Error("CDP timeout: " + method));}, 15000);
    pending.set(id, {resolve, reject, timer}); socket.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const response = await call("Runtime.evaluate", {expression, returnByValue: true, awaitPromise: true});
    if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
    return response.result.value;
  };
  const until = async expression => {
    const deadline = Date.now() + Number(timeoutText) * 1000;
    while (Date.now() < deadline) {
      const value = await evaluate(expression); if (value) return value;
      await pause(100);
    }
    throw new Error("Browser acceptance deadline reached");
  };
  await call("Runtime.enable"); await call("Page.enable");
  await call("Page.navigate", {url});
  await until("document.querySelector('#actions button') !== null");
  for (const entry of cases) {
    const action = entry.action || "qec.ququart.benchmark";
    await evaluate(`(() => {
      const button = Array.from(document.querySelectorAll('#actions button')).find(b => b.dataset.id === ${JSON.stringify(action)});
      if (!button) throw new Error('QEC action was not discovered');
      button.click();
    })()`);
    const oldId = await evaluate("document.querySelector('#record').textContent ? JSON.parse(document.querySelector('#record').textContent).id : null");
    await evaluate(`(() => {
      const parameters = ${JSON.stringify(entry.parameters)};
      for (const [name, value] of Object.entries(parameters)) {
        const input = document.getElementById('field-' + name);
        if (!input) throw new Error('Missing generated field: ' + name);
        if (input.type === 'checkbox') input.checked = value;
        else input.value = String(value);
      }
      document.getElementById('form').requestSubmit();
    })()`);
    const record = await until(`(() => {
      const text = document.getElementById('record').textContent; if (!text) return false;
      const record = JSON.parse(text);
      return record.id !== ${JSON.stringify(oldId)} && !['queued','running'].includes(record.status) ? record : false;
    })()`);
    await writeFile(entry.record, JSON.stringify(record, null, 2) + "\n");
    const view = await evaluate("({hidden:document.getElementById('result-view').hidden,text:document.getElementById('result-view').textContent})");
    receipt.runs.push({case: entry.name, action: record.action, id: record.id, status: record.status, expected_status: entry.status,
      parameters: record.parameters, schema_sha256: record.capability.schema_sha256, view});
    await writeFile(receiptFile, JSON.stringify(receipt, null, 2) + "\n");
    if (record.status !== entry.status || record.persistence_error) throw new Error("Unexpected browser run outcome");
    if (record.action !== action) throw new Error("Browser submitted a different action");
    if (entry.view && (view.hidden || !view.text.startsWith(entry.view))) throw new Error("Missing structured result view");
    if (JSON.stringify(Object.entries(record.parameters).sort()) !== JSON.stringify(Object.entries(entry.parameters).sort())) {
      throw new Error("Browser submitted different parameters");
    }
  }
  if (receipt.exceptions.length) throw new Error(receipt.exceptions.join("\n"));
  receipt.status = "passed";
  console.log(JSON.stringify({status: receipt.status, engine: receipt.engine, runs: receipt.runs.map(r => r.status)}));
} catch (error) {
  receipt.status = "failed"; receipt.error = String(error); throw error;
} finally {
  await writeFile(receiptFile, JSON.stringify(receipt, null, 2) + "\n");
  socket?.close();
  for (const item of pending.values()) clearTimeout(item.timer);
  browser.kill("SIGTERM");
  await pause(500);
  await rm(profile, {recursive: true, force: true, maxRetries: 3, retryDelay: 200});
}
