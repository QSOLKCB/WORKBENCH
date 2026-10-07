"use strict";
const byId = id => document.getElementById(id);
const fragment = new URLSearchParams(location.hash.slice(1));
const token = fragment.get("token") || sessionStorage.getItem("workbench-token") || "";
if (token) sessionStorage.setItem("workbench-token", token);
history.replaceState(null, "", location.pathname);
let manifest, selected, runId, currentRecord, polling = false;
const notice = message => { byId("notice").textContent = message; };
async function api(path, body) {
  const response = await fetch(path, {method: body === undefined ? "GET" : "POST",
    headers: {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}
function choose(action) {
  selected = action;
  byId("action-id").textContent = action.id;
  byId("title").textContent = action.title;
  byId("description").textContent = action.description;
  byId("identity").textContent = JSON.stringify(action, null, 2);
  byId("fields").textContent = "";
  for (const spec of action.fields) {
    const wrapper = document.createElement("div");
    wrapper.className = "field" + (spec.multiline ? " wide" : "");
    const label = document.createElement("label");
    label.textContent = spec.label + (spec.required ? " *" : "");
    label.htmlFor = "field-" + spec.name;
    let input;
    if (spec.choices) {
      input = document.createElement("select");
      for (const value of spec.choices) {
        const option = document.createElement("option");
        option.value = String(value); option.textContent = String(value); input.append(option);
      }
    } else if (spec.multiline) {
      input = document.createElement("textarea");
    } else {
      input = document.createElement("input");
      input.type = spec.type === "boolean" ? "checkbox" : ["integer", "number"].includes(spec.type) ? "number" : "text";
      if (input.type === "number") input.step = spec.type === "integer" ? "1" : "any";
    }
    input.id = label.htmlFor; input.name = spec.name;
    if (input.type === "checkbox") input.checked = spec.default === true;
    else if (spec.default !== undefined) input.value = String(spec.default);
    input.required = !!spec.required;
    if (spec.minimum !== undefined) input.min = spec.minimum;
    if (spec.maximum !== undefined) input.max = spec.maximum;
    if (spec.max_length !== undefined) input.maxLength = spec.max_length;
    wrapper.append(label, input);
    if (spec.help) {const help = document.createElement("span"); help.className = "help"; help.textContent = spec.help; wrapper.append(help);}
    byId("fields").append(wrapper);
  }
  byId("run").disabled = false;
  for (const button of byId("actions").children) button.classList.toggle("selected", button.dataset.id === action.id);
}
function values() {
  const result = {};
  for (const spec of selected.fields) {
    const input = byId("field-" + spec.name);
    if (input.value === "" && !spec.required && spec.default === undefined) continue;
    if (spec.type === "integer") {
      const raw = input.value.trim();
      if (!/^[+-]?\d+$/.test(raw)) throw new Error(spec.label + " must be a whole decimal integer");
      const integer = BigInt(raw);
      if (integer < BigInt(Number.MIN_SAFE_INTEGER) || integer > BigInt(Number.MAX_SAFE_INTEGER)) {
        throw new Error(spec.label + " is outside the browser's safe integer range; use CLI or TUI for larger integers");
      }
      result[spec.name] = Number(integer);
    } else if (spec.type === "boolean") {
      result[spec.name] = input.type === "checkbox" ? input.checked : JSON.parse(input.value);
    } else {
      result[spec.name] = spec.type === "number" ? Number(input.value) : input.value;
    }
  }
  return result;
}
async function connect(refresh = false) {
  manifest = await api(refresh ? "/api/refresh" : "/api/manifest", refresh ? {} : undefined);
  byId("connections").textContent = "";
  for (const connection of manifest.connections) {
    const element = document.createElement("div"); element.className = "connection " + connection.status;
    element.textContent = connection.id + " · " + connection.status;
    if (connection.reason) {const reason = document.createElement("p"); reason.textContent = connection.reason; element.append(reason);}
    byId("connections").append(element);
  }
  byId("actions").textContent = "";
  for (const action of manifest.actions) {
    const button = document.createElement("button"); button.type = "button"; button.textContent = action.title;
    button.dataset.id = action.id; button.onclick = () => choose(action); byId("actions").append(button);
  }
  const next = manifest.actions.find(a => a.id === selected?.id) || manifest.actions[0];
  if (next) choose(next);
  else {selected = null; byId("run").disabled = true; byId("fields").textContent = ""; byId("title").textContent = "No available actions";}
  await historyList();
}
async function historyList() {
  const records = await api("/api/runs"); byId("history").textContent = "";
  for (const record of records.slice(0, 15)) {
    const button = document.createElement("button"); button.type = "button";
    button.textContent = record.action + " · " + record.status + " · " + record.id.slice(0, 6);
    button.onclick = () => {runId = record.id; poll().catch(e => notice(e.message));};
    byId("history").append(button);
  }
}
async function poll() {
  if (!runId || polling) return;
  polling = true;
  const requested = runId;
  try {
    const record = await api("/api/runs/" + requested);
    if (runId !== requested) return;
    const changed = !currentRecord || currentRecord.id !== record.id || currentRecord.status !== record.status;
    currentRecord = record;
    byId("run-status").textContent = record.status + " · " + record.id.slice(0, 12);
    byId("cancel").disabled = !["queued", "running"].includes(record.status);
    byId("download").disabled = false;
    let output = record.stdout || "";
    if (record.action === "inference.generate") {
      output = output.split("\n").flatMap(line => {try {return [JSON.parse(line).response || ""];} catch {return [];}}).join("");
    }
    byId("output").textContent = [record.stderr, output, record.error, record.persistence_error].filter(Boolean).join("\n");
    byId("record").textContent = JSON.stringify(record, null, 2);
    if (changed) await historyList();
  } finally {polling = false;}
}
byId("form").onsubmit = async event => {
  event.preventDefault(); if (!selected) return;
  try {
    const record = await api("/api/run", {action: selected.id, parameters: values(), schema_sha256: selected.schema_sha256});
    runId = record.id; notice("Run started. Inputs and outputs are saved locally."); await poll(); await historyList();
  } catch (error) {notice(error.message);}
};
byId("refresh").onclick = () => connect(true).then(() => notice("Connections refreshed.")).catch(e => notice(e.message));
byId("cancel").onclick = () => api("/api/cancel", {id: runId}).then(poll).catch(e => notice(e.message));
byId("download").onclick = () => {
  if (!currentRecord) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(currentRecord, null, 2)], {type: "application/json"}));
  const link = document.createElement("a"); link.href = url; link.download = "workbench-run-" + currentRecord.id + ".json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
byId("save-preset").onclick = () => {
  if (!selected) return;
  try {localStorage.setItem("preset-" + selected.id, JSON.stringify(values())); notice("Preset saved in this browser, including any prompt text.");}
  catch (e) {notice(e.message);}
};
byId("load-preset").onclick = () => {
  if (!selected) return;
  try {
    const saved = JSON.parse(localStorage.getItem("preset-" + selected.id) || "null");
    if (!saved) return notice("No saved preset for this action.");
    for (const spec of selected.fields) if (saved[spec.name] !== undefined) {
      const input = byId("field-" + spec.name);
      if (input.type === "checkbox") input.checked = saved[spec.name]; else input.value = String(saved[spec.name]);
    }
    notice("Preset loaded; current backend validation still applies.");
  } catch (e) {notice(e.message);}
};
connect().catch(e => notice(e.message));
setInterval(() => poll().catch(e => notice(e.message)), 500);
