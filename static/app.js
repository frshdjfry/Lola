const paramGroups = [
  {
    id: "speech",
    title: "Speech",
    note: "Recognition model, utterance boundary, and input buffering.",
    controls: [
      { path: "speech.model_path", label: "Model path", type: "text", value: "./vosk-model/vosk-model" },
      { path: "speech.glasgow_csv", label: "Glasgow CSV", type: "text", value: "./glasgow.csv" },
      { path: "speech.min_partial_chars", label: "Minimum partial chars", type: "range", min: 1, max: 12, step: 1, value: 1 },
      { path: "speech.short_pause_sec", label: "Short pause", type: "range", min: 0.001, max: 0.2, step: 0.001, value: 0.005, suffix: "s" },
      { path: "speech.block_size", label: "Input block size", type: "range", min: 512, max: 8192, step: 128, value: 4000 },
      { path: "speech.audio_queue_max_chunks", label: "Audio queue chunks", type: "range", min: 32, max: 1024, step: 1, value: 256 }
    ]
  },
  {
    id: "composer",
    title: "Composer",
    note: "Rhythm, event emission, voice count, decay, and event shaping.",
    controls: [
      { path: "composer.bpm", label: "BPM", type: "range", min: 30, max: 180, step: 1, value: 120, suffix: " BPM" },
      { path: "composer.bar_beats", label: "Beats per bar", type: "range", min: 1, max: 12, step: 1, value: 4 },
      { path: "composer.max_voices", label: "Max voices", type: "range", min: 1, max: 12, step: 1, value: 4 },
      { path: "composer.rotate_patterns", label: "Rotate patterns", type: "boolean", value: true },
      { path: "composer.step_size_choices", label: "Step size choices", type: "text", value: "2, 4, 6" },
      { path: "composer.decay_per_hit", label: "Decay per hit", type: "range", min: 0.05, max: 1, step: 0.01, value: 0.5 },
      { path: "composer.min_gain", label: "Minimum gain", type: "range", min: 0.01, max: 0.5, step: 0.01, value: 0.05 },
      { path: "composer.event_duration_scale", label: "Event duration scale", type: "range", min: 0.1, max: 3, step: 0.05, value: 0.9 },
      { path: "composer.event_min_duration", label: "Minimum event duration", type: "range", min: 0.01, max: 0.5, step: 0.01, value: 0.05, suffix: "s" },
      { path: "composer.default_word_duration", label: "Default word duration", type: "range", min: 0.03, max: 1.2, step: 0.01, value: 0.2, suffix: "s" },
      { path: "composer.replacements_per_bar", label: "Replacements per bar", type: "range", min: 1, max: 8, step: 1, value: 2 }
    ]
  },
  {
    id: "composer-visual",
    title: "Composer Visual Emission",
    note: "Ranges used by composer when emitting visual events.",
    controls: [
      { path: "composer.visual_x_range", label: "Visual X range", type: "text", value: "-6.0, 6.0" },
      { path: "composer.visual_y_range", label: "Visual Y range", type: "text", value: "-1.0, 1.0" },
      { path: "composer.visual_z_range", label: "Visual Z range", type: "text", value: "-1.5, 1.5" }
    ]
  },
  {
    id: "playback",
    title: "Playback",
    note: "Simple synth output, note queue, and gain shaping.",
    controls: [
      { path: "playback.sample_rate", label: "Sample rate", type: "number", min: 8000, max: 96000, step: 1, value: 16000 },
      { path: "playback.block_size", label: "Output block size", type: "range", min: 128, max: 4096, step: 64, value: 1024 },
      { path: "playback.master_gain", label: "Master gain", type: "range", min: 0, max: 1, step: 0.01, value: 0.35 },
      { path: "playback.fade_ms", label: "Fade ms", type: "range", min: 0, max: 50, step: 1, value: 10, suffix: "ms" },
      { path: "playback.queue_size", label: "Queue size", type: "range", min: 8, max: 1024, step: 1, value: 256 }
    ]
  },
  {
    id: "visual-core",
    title: "Visual Core",
    note: "Visual engine queueing, generator choice, and shared background video.",
    controls: [
      { path: "visual.active_generator", label: "Active generator", type: "select", value: "dust", options: ["dust", "waver"] },
      { path: "visual.queue_size", label: "Visual queue size", type: "range", min: 8, max: 1024, step: 1, value: 256 },
      { path: "visual.video_enabled", label: "Background video enabled", type: "boolean", value: true },
      { path: "visual.video_path", label: "Background video path", type: "text", value: "" },
      { path: "visual.video_muted", label: "Background video muted", type: "boolean", value: true }
    ]
  },
  {
    id: "dustscene",
    title: "DustScene",
    note: "Firefly and trail scene values.",
    controls: [
      { path: "dustscene.width", label: "Window width", type: "number", min: 320, max: 3840, step: 1, value: 1280 },
      { path: "dustscene.height", label: "Window height", type: "number", min: 240, max: 2160, step: 1, value: 720 },
      { path: "dustscene.camera_distance", label: "Camera distance", type: "range", min: -40, max: -2, step: 0.1, value: -17 },
      { path: "dustscene.camera_dolly_speed", label: "Camera dolly speed", type: "range", min: 0, max: 4, step: 0.01, value: 0.2 },
      { path: "dustscene.max_trail_points", label: "Max trail points", type: "range", min: 1000, max: 500000, step: 1000, value: 250000 },
      { path: "dustscene.trail_sample_distance", label: "Trail sample distance", type: "range", min: 0.05, max: 4, step: 0.01, value: 1.0055 },
      { path: "dustscene.spawn_forward_distance", label: "Spawn forward distance", type: "range", min: 1, max: 40, step: 0.1, value: 10.5 },
      { path: "dustscene.spawn_ground_height", label: "Spawn ground height", type: "range", min: -6, max: 6, step: 0.05, value: 1.15 },
      { path: "dustscene.spawn_x_scale", label: "Spawn X scale", type: "range", min: 0.1, max: 10, step: 0.05, value: 1.5 },
      { path: "dustscene.spawn_y_scale", label: "Spawn Y scale", type: "range", min: 0.1, max: 10, step: 0.05, value: 1.35 },
      { path: "dustscene.spawn_z_scale", label: "Spawn Z scale", type: "range", min: 0.1, max: 10, step: 0.05, value: 0.8 },
      { path: "dustscene.update_hz", label: "Update Hz", type: "range", min: 10, max: 240, step: 1, value: 120 }
    ]
  },
  {
    id: "waver",
    title: "Waver",
    note: "Wave field generator values.",
    controls: [
      { path: "waver.width", label: "Window width", type: "number", min: 320, max: 3840, step: 1, value: 1280 },
      { path: "waver.height", label: "Window height", type: "number", min: 240, max: 2160, step: 1, value: 720 },
      { path: "waver.num_particles", label: "Particle count", type: "range", min: 1000, max: 60000, step: 500, value: 22000 },
      { path: "waver.camera_distance", label: "Camera distance", type: "range", min: -20, max: -1, step: 0.1, value: -5 },
      { path: "waver.stream_half_length", label: "Stream half length", type: "range", min: 0.5, max: 12, step: 0.1, value: 4.0 },
      { path: "waver.stream_half_width", label: "Stream half width", type: "range", min: 0.5, max: 12, step: 0.1, value: 3.0 },
      { path: "waver.stream_half_height", label: "Stream half height", type: "range", min: 0.5, max: 12, step: 0.1, value: 2.0 },
      { path: "waver.fade_distance", label: "Fade distance", type: "range", min: 0.5, max: 12, step: 0.1, value: 5.0 },
      { path: "waver.wind_speed", label: "Wind speed", type: "range", min: 0.01, max: 2, step: 0.01, value: 0.15 },
      { path: "waver.spawn_jitter", label: "Spawn jitter", type: "range", min: 0, max: 4, step: 0.01, value: 1.0 },
      { path: "waver.update_hz", label: "Update Hz", type: "range", min: 10, max: 240, step: 1, value: 120 }
    ]
  }
];

const state = {};
const initial = {};
const cards = new Map();
let sendTimer = null;
let lastPayload = null;
let statusTimer = null;

const controlsEl = document.querySelector("#controls");
const navEl = document.querySelector("#nav");
const payloadEl = document.querySelector("#payload");
const toastEl = document.querySelector("#toast");
const presetsEl = document.querySelector("#presets");

function getApiBase() {
  return document.querySelector("#endpoint").value.trim().replace("/\\/$/", "");
}

function isMock() {
  return document.querySelector("#mockMode").checked;
}

function flattenObject(value, prefix = "", out = {}) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return out;
  }

  Object.entries(value).forEach(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (child && typeof child === "object" && !Array.isArray(child)) {
      flattenObject(child, path, out);
    } else {
      out[path] = child;
    }
  });

  return out;
}

function nestedObjectFromState(values) {
  const out = {};

  Object.entries(values).forEach(([path, value]) => {
    const parts = path.split(".");
    let cursor = out;

    parts.forEach((part, index) => {
      if (index === parts.length - 1) {
        cursor[part] = parseSpecialValue(path, value);
        return;
      }
      if (!cursor[part] || typeof cursor[part] !== "object" || Array.isArray(cursor[part])) {
        cursor[part] = {};
      }
      cursor = cursor[part];
    });
  });

  return out;
}

function parseSpecialValue(path, value) {
  if (typeof value !== "string") {
    return value;
  }

  const rangeKeys = new Set([
    "composer.visual_x_range",
    "composer.visual_y_range",
    "composer.visual_z_range"
  ]);

  if (rangeKeys.has(path)) {
    return value
      .split(",")
      .map(part => Number(part.trim()))
      .filter(part => !Number.isNaN(part));
  }

  if (path === "composer.step_size_choices") {
    return value
      .split(",")
      .map(part => Number(part.trim()))
      .filter(part => !Number.isNaN(part));
  }

  return value;
}

function controlByPath(path) {
  for (const group of paramGroups) {
    const control = group.controls.find(item => item.path === path);
    if (control) return control;
  }
  return null;
}

function initState() {
  paramGroups.forEach(group => {
    group.controls.forEach(control => {
      state[control.path] = control.value;
      initial[control.path] = control.value;
    });
  });
}

function initUi() {
  paramGroups.forEach(group => {
    const navLink = document.createElement("a");
    navLink.href = `#${group.id}`;
    navLink.innerHTML = `<span>${group.title}</span><span>${group.controls.length}</span>`;
    navEl.appendChild(navLink);

    const section = document.createElement("section");
    section.className = "group";
    section.id = group.id;
    section.innerHTML = `
      <div class="group-head">
        <div>
          <h3>${group.title}</h3>
          <p>${group.note}</p>
        </div>
      </div>
      <div class="group-grid"></div>
    `;

    const grid = section.querySelector(".group-grid");

    group.controls.forEach(control => {
      grid.appendChild(createControl(control));
    });

    controlsEl.appendChild(section);
  });
}

function createControl(control) {
  const card = document.createElement("article");
  card.className = "control";
  card.dataset.path = control.path;
  card.dataset.search = `${control.path} ${control.label} ${control.help || ""} ${control.type}`.toLowerCase();

  const valueText = formatValue(control, state[control.path]);

  card.innerHTML = `
    <div class="control-head">
      <div>
        <h4>${control.label}</h4>
        <p>${control.help || ""}</p>
      </div>
      <span class="value">${valueText}</span>
    </div>
    <div class="input-slot"></div>
  `;

  const slot = card.querySelector(".input-slot");
  const valueEl = card.querySelector(".value");
  const syncers = [];

  if (control.type === "range") {
    slot.classList.add("range-row");

    const range = document.createElement("input");
    range.type = "range";
    range.min = control.min;
    range.max = control.max;
    range.step = control.step;
    range.value = state[control.path];

    const number = document.createElement("input");
    number.type = "number";
    number.min = control.min;
    number.max = control.max;
    number.step = control.step;
    number.value = state[control.path];

    range.addEventListener("input", () => updateControl(control, castValue(control, range.value), valueEl));
    number.addEventListener("input", () => updateControl(control, castValue(control, number.value), valueEl));

    syncers.push(value => {
      range.value = value;
      number.value = value;
    });

    slot.append(range, number);
  }

  if (control.type === "number") {
    const input = document.createElement("input");
    input.type = "number";
    input.min = control.min ?? "";
    input.max = control.max ?? "";
    input.step = control.step ?? 1;
    input.value = state[control.path];
    input.addEventListener("input", () => updateControl(control, castValue(control, input.value), valueEl));
    syncers.push(value => {
      input.value = value;
    });
    slot.appendChild(input);
  }

  if (control.type === "text") {
    const input = document.createElement("input");
    input.type = "text";
    input.value = state[control.path];
    input.addEventListener("input", () => updateControl(control, input.value, valueEl));
    syncers.push(value => {
      input.value = value;
    });
    slot.appendChild(input);
  }

  if (control.type === "select") {
    const input = document.createElement("select");
    control.options.forEach(option => {
      const opt = document.createElement("option");
      opt.value = option;
      opt.textContent = option;
      input.appendChild(opt);
    });
    input.value = state[control.path];
    input.addEventListener("change", () => updateControl(control, input.value, valueEl));
    syncers.push(value => {
      input.value = value;
    });
    slot.appendChild(input);
  }

  if (control.type === "boolean") {
    const label = document.createElement("label");
    label.className = "toggle";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = !!state[control.path];
    input.addEventListener("change", () => updateControl(control, input.checked, valueEl));
    const span = document.createElement("span");
    span.textContent = "Enabled";
    label.append(input, span);
    syncers.push(value => {
      input.checked = !!value;
    });
    slot.appendChild(label);
  }

  cards.set(control.path, {
    card,
    control,
    valueEl,
    sync(value) {
      syncers.forEach(fn => fn(value));
    }
  });

  return card;
}

function castValue(control, raw) {
  if (control.type === "number" || control.type === "range") {
    return Number(raw);
  }
  if (control.type === "boolean") {
    return !!raw;
  }
  return raw;
}

function formatValue(control, value) {
  if (typeof value === "boolean") return value ? "on" : "off";
  if (Array.isArray(value)) return value.join(", ");
  return `${value}${control.suffix || ""}`;
}

function updateControl(control, value, valueEl, silent = false) {
  const previous = state[control.path];
  state[control.path] = value;
  valueEl.textContent = formatValue(control, value);
  const entry = cards.get(control.path);
  if (entry) entry.sync(value);

  updateReadouts();

  if (silent) return;

  const payload = {
    source: "control-panel",
    timestamp: new Date().toISOString(),
    request: "config/set",
    key: control.path,
    value: parseSpecialValue(control.path, value),
    previous
  };

  showPayload(payload);

  if (document.querySelector("#autoSend").checked) {
    scheduleSend(() => sendSingle(control.path, value), payload);
  }
}

function scheduleSend(action, payload) {
  clearTimeout(sendTimer);
  sendTimer = setTimeout(async () => {
    await action();
    if (payload) lastPayload = payload;
  }, 180);
}

function showPayload(payload) {
  lastPayload = payload;
  payloadEl.textContent = JSON.stringify(payload, null, 2);
}

async function apiFetch(path, options = {}) {
  const response = await fetch(`${getApiBase()}${path}`, options);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const text = await response.text();
  return text ? JSON.parse(text) : {};
}

async function sendSingle(path, value) {
  if (isMock()) {
    setStatus("Mock mode", false);
    document.querySelector("#lastSync").textContent = new Date().toLocaleTimeString();
    toast("Mock config/set");
    return;
  }

  try {
    const payload = {
      key: path,
      value: parseSpecialValue(path, value)
    };
    const data = await apiFetch("/config/set", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    setStatus("Connected", true);
    document.querySelector("#lastSync").textContent = new Date().toLocaleTimeString();
    toast("Config updated");
    if (data.config) {
      applyBackendConfig(data.config, false);
    }
  } catch (error) {
    setStatus("Endpoint unavailable", false);
    toast(error.message);
  }
}

async function sendAll() {
  const values = nestedObjectFromState(state);
  const payload = {
    source: "control-panel",
    timestamp: new Date().toISOString(),
    request: "config/update",
    values
  };

  showPayload(payload);

  if (isMock()) {
    toast("Mock config/update");
    return;
  }

  try {
    const data = await apiFetch("/config/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values, merge: true })
    });
    setStatus("Connected", true);
    document.querySelector("#lastSync").textContent = new Date().toLocaleTimeString();
    toast("All values sent");
    if (data.config) {
      applyBackendConfig(data.config, false);
    }
  } catch (error) {
    setStatus("Endpoint unavailable", false);
    toast(error.message);
  }
}

function applyStateValue(path, value, syncInitial = false) {
  const control = controlByPath(path);
  if (!control) return;

  let nextValue = value;
  if (Array.isArray(value)) {
    nextValue = value.join(", ");
  }

  state[path] = nextValue;
  if (syncInitial) {
    initial[path] = nextValue;
  }

  const entry = cards.get(path);
  if (!entry) return;

  entry.valueEl.textContent = formatValue(control, nextValue);
  entry.sync(nextValue);
}

function applyBackendConfig(config, syncInitial = true) {
  const flat = flattenObject(config);

  Object.entries(flat).forEach(([path, value]) => {
    if (cards.has(path)) {
      applyStateValue(path, value, syncInitial);
    }
  });

  updateReadouts();
}

async function pullConfig() {
  if (isMock()) {
    toast("Mock pull");
    return;
  }

  try {
    const data = await apiFetch("/config");
    if (data.config) {
      applyBackendConfig(data.config, true);
      showPayload({ source: "control-panel", request: "get/config", received: data.config });
      setStatus("Connected", true);
      document.querySelector("#lastSync").textContent = new Date().toLocaleTimeString();
      toast("Config pulled");
    }
  } catch (error) {
    setStatus("Endpoint unavailable", false);
    toast(error.message);
  }
}

async function loadPresets() {
  presetsEl.innerHTML = "";

  if (isMock()) {
    return;
  }

  try {
    const data = await apiFetch("/presets");
    const presets = Array.isArray(data.presets) ? data.presets : [];

    if (!presets.length) {
      const empty = document.createElement("span");
      empty.className = "secondary small";
      empty.textContent = "No presets";
      presetsEl.appendChild(empty);
      return;
    }

    presets.forEach(name => {
      const btn = document.createElement("button");
      btn.className = "secondary small";
      btn.type = "button";
      btn.textContent = name;
      btn.addEventListener("click", async () => {
        await loadPreset(name);
      });
      presetsEl.appendChild(btn);
    });
  } catch (error) {
    toast(error.message);
  }
}

async function loadPreset(name) {
  if (isMock()) {
    toast(`Mock preset load: ${name}`);
    return;
  }

  try {
    const data = await apiFetch("/preset/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name })
    });

    if (data.config) {
      applyBackendConfig(data.config, true);
      document.querySelector("#presetName").value = name;
      showPayload({ source: "control-panel", request: "preset/load", name });
      setStatus("Connected", true);
      document.querySelector("#lastSync").textContent = new Date().toLocaleTimeString();
      toast(`Preset loaded: ${name}`);
    }
  } catch (error) {
    setStatus("Endpoint unavailable", false);
    toast(error.message);
  }
}

async function savePreset() {
  const name = document.querySelector("#presetName").value.trim();
  if (!name) {
    toast("Enter a preset name");
    return;
  }

  showPayload({ source: "control-panel", request: "preset/save", name });

  if (isMock()) {
    toast(`Mock preset save: ${name}`);
    return;
  }

  try {
    await apiFetch("/preset/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name })
    });
    toast(`Preset saved: ${name}`);
    await loadPresets();
  } catch (error) {
    toast(error.message);
  }
}

async function saveCurrentPreset() {
  showPayload({ source: "control-panel", request: "preset/save-current" });

  if (isMock()) {
    toast("Mock save current preset");
    return;
  }

  try {
    await apiFetch("/preset/save-current", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    toast("Current preset saved");
    await loadPresets();
  } catch (error) {
    toast(error.message);
  }
}

function resetAll() {
  Object.entries(initial).forEach(([path, value]) => {
    applyStateValue(path, value, false);
  });

  updateReadouts();

  const payload = {
    source: "control-panel",
    action: "reset-ui",
    timestamp: new Date().toISOString()
  };

  showPayload(payload);
  toast("UI reset");
}

function updateReadouts() {
  document.querySelector("#bpmReadout").textContent = state["composer.bpm"];
  document.querySelector("#generatorReadout").textContent = state["visual.active_generator"];

  const generator = state["visual.active_generator"];
  const budget = generator === "waver"
    ? `${Math.round(Number(state["waver.num_particles"]) / 1000)}k`
    : `${Math.round(Number(state["dustscene.max_trail_points"]) / 1000)}k`;

  document.querySelector("#budgetReadout").textContent = budget;
  document.querySelector("#videoReadout").textContent =
  state["visual.video_enabled"]
    ? (state["visual.video_path"] || "enabled")
    : "off";
}

function setStatus(text, online) {
  document.querySelector("#statusText").textContent = text;
  document.querySelector("#statusDot").classList.toggle("online", !!online);
}

function searchControls(query) {
  const q = query.trim().toLowerCase();

  document.querySelectorAll(".control").forEach(card => {
    card.classList.toggle("hidden", !!q && !card.dataset.search.includes(q));
  });

  document.querySelectorAll(".group").forEach(section => {
    const hasVisible = Array.from(section.querySelectorAll(".control")).some(card => !card.classList.contains("hidden"));
    section.classList.toggle("hidden", !!q && !hasVisible);
  });
}

async function stopApp() {
  showPayload({
    source: "control-panel",
    action: "stop",
    timestamp: new Date().toISOString()
  });

  if (isMock()) {
    toast("Mock stop action");
    return;
  }

  try {
    await apiFetch("/stop", { method: "POST" });
    toast("Stop request sent");
  } catch (error) {
    toast(error.message);
  }
}

async function refreshStatus() {
  if (isMock()) {
    setStatus("Mock mode", false);
    return;
  }

  try {
    const data = await apiFetch("/status");
    const running = !!data.running;
    setStatus(running ? "Connected" : "Stopped", running);
    document.querySelector("#lastSync").textContent = new Date().toLocaleTimeString();
  } catch (error) {
    setStatus("Endpoint unavailable", false);
  }
}

function copyPayload() {
  const text = payloadEl.textContent;
  navigator.clipboard?.writeText(text);
  toast("Payload copied");
}

function toast(message) {
  const item = document.createElement("div");
  item.className = "toast";
  item.textContent = message;
  toastEl.appendChild(item);

  setTimeout(() => {
    item.remove();
  }, 2600);
}

function wireEvents() {
  document.querySelector("#sendAllBtn").addEventListener("click", sendAll);
  document.querySelector("#pullConfigBtn").addEventListener("click", pullConfig);
  document.querySelector("#refreshBtn").addEventListener("click", async () => {
    await refreshStatus();
    await loadPresets();
  });
  document.querySelector("#resetBtn").addEventListener("click", resetAll);
  document.querySelector("#copyBtn").addEventListener("click", copyPayload);
  document.querySelector("#stopBtn").addEventListener("click", stopApp);
  document.querySelector("#savePresetBtn").addEventListener("click", savePreset);
  document.querySelector("#saveCurrentPresetBtn").addEventListener("click", saveCurrentPreset);

  document.querySelector("#search").addEventListener("input", event => {
    searchControls(event.target.value);
  });

  document.querySelector("#mockMode").addEventListener("change", async event => {
    if (event.target.checked) {
      setStatus("Mock mode", false);
      presetsEl.innerHTML = "";
    } else {
      await refreshStatus();
      await loadPresets();
    }
  });

  document.querySelector("#endpoint").addEventListener("change", async () => {
    if (!isMock()) {
      await refreshStatus();
      await loadPresets();
    }
  });
}

async function init() {
  initState();
  initUi();
  wireEvents();
  updateReadouts();

  if (!isMock()) {
    await refreshStatus();
    await pullConfig();
    await loadPresets();
  } else {
    setStatus("Mock mode", false);
  }

  clearInterval(statusTimer);
  statusTimer = setInterval(() => {
    if (!isMock()) {
      refreshStatus();
    }
  }, 3000);
}

init();