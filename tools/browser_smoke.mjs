// Optional browser acceptance check: Node >=22 + Chrome/Chromium.
// Usage: node tools/browser_smoke.mjs 'http://127.0.0.1:PORT/#token=TOKEN' evidence/browser.png
import {spawn} from "node:child_process";
import {mkdtemp, readFile, writeFile, rm, mkdir} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join, dirname} from "node:path";

const [url, screenshot = "evidence/browser.png"] = process.argv.slice(2);
if (!url) throw new Error("Supply the URL printed by workbench web");
const profile = await mkdtemp(join(tmpdir(), "qsol-browser-"));
const browser = spawn(process.env.BROWSER_BIN || "google-chrome", ["--headless", "--no-sandbox",
  "--disable-gpu", "--disable-dev-shm-usage", "--remote-debugging-port=0", "--user-data-dir=" + profile,
  "--no-first-run", "about:blank"], {stdio: "ignore"});
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const pending = new Map(), errors = [];
let socket, sequence = 0;
browser.on("error", e => errors.push(String(e)));
try {
  let port;
  for (let i = 0; i < 100; i++) {
    try {port = (await readFile(join(profile, "DevToolsActivePort"), "utf8")).split("\n")[0]; break;}
    catch {await pause(100);}
  }
  if (!port) throw new Error("Browser did not start: " + errors.join("; "));
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(pages.find(p => p.type === "page").webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {socket.onopen = resolve; socket.onerror = reject;});
  socket.onmessage = event => {
    const data = JSON.parse(event.data);
    if (data.id && pending.has(data.id)) {
      const {resolve, reject, timer} = pending.get(data.id); clearTimeout(timer); pending.delete(data.id);
      if (data.error) reject(new Error(JSON.stringify(data.error))); else resolve(data.result);
    } else if (data.method === "Runtime.exceptionThrown") errors.push(JSON.stringify(data.params));
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
    for (let i = 0; i < 100; i++) {if (await evaluate(expression)) return; await pause(100);}
    throw new Error("UI check timed out: " + expression);
  };
  await call("Runtime.enable"); await call("Page.enable");
  await call("Emulation.setDeviceMetricsOverride", {width: 1360, height: 1000, deviceScaleFactor: 1, mobile: false});
  await call("Page.navigate", {url});
  await until("document.querySelector('#field-steps') !== null");
  await evaluate("document.querySelector('#field-steps').value='3'; document.querySelector('#field-seed').value='7'; document.querySelector('#field-delay').value='0'; document.querySelector('#form').requestSubmit()");
  await until("document.querySelector('#run-status').textContent.startsWith('succeeded')");
  const record = await evaluate("JSON.parse(document.querySelector('#record').textContent)");
  if (record.result.total !== 42) throw new Error("Unexpected run result");
  const screenshotData = await call("Page.captureScreenshot", {format: "png"});
  await mkdir(dirname(screenshot), {recursive: true});
  await writeFile(screenshot, Buffer.from(screenshotData.data, "base64"));
  await evaluate("document.querySelector('#field-steps').value='50'; document.querySelector('#field-delay').value='0.2'; document.querySelector('#form').requestSubmit()");
  await until("!document.querySelector('#cancel').disabled");
  await evaluate("document.querySelector('#cancel').click()");
  await until("document.querySelector('#run-status').textContent.startsWith('cancelled')");
  if (errors.length) throw new Error(errors.join("\n"));
  console.log(JSON.stringify({status: "passed", checks: ["generated form", "demo result 42", "live run polling", "cancel", "no browser exceptions"], screenshot}, null, 2));
} finally {
  socket?.close();
  for (const item of pending.values()) clearTimeout(item.timer);
  browser.kill("SIGTERM");
  await pause(500);
  await rm(profile, {recursive: true, force: true, maxRetries: 3, retryDelay: 200});
}
