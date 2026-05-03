const params = [
  {
    id: "audio-recognition",
    title: "Audio Recognition",
    note: "Vosk input, utterance detection, and word slicing.",
    controls: [
      { path: "audio.recognition.min_partial_chars", label: "Minimum partial characters", type: "range", min: 1, max: 12, step: 1, value: 1, help: "From MIN_PARTIAL_CHARS." },
      { path: "audio.recognition.min_word_duration_sec", label: "Minimum word duration", type: "range", min: 0.01, max: 0.4, step: 0.01, value: 0.05, suffix: "s", help: "From MIN_WORD_DURATION_SEC." },
      { path: "audio.word.word_trail_ms", label: "Word trail", type: "range", min: 0, max: 180, step: 1, value: 40, suffix: "ms", help: "Padding before and after word slices." },
      { path: "audio.word.fade_ms", label: "Slice fade", type: "range", min: 0, max: 40, step: 1, value: 8, suffix: "ms", help: "Small fade to avoid clicks." },
      { path: "audio.io.block_size", label: "Input block size", type: "range", min: 512, max: 8192, step: 128, value: 4000, help: "From BLOCK_SIZE." },
      { path: "audio.io.max_audio_queue_chunks", label: "Audio queue chunks", type: "range", min: 32, max: 1024, step: 1, value: 256, help: "Input queue limit." }
    ]
  },
  {
    id: "audio-rhythm",
    title: "Rhythm Engine",
    note: "Controls phrase arrangement, voice count, and rhythmic pattern generation.",
    controls: [
      { path: "audio.rhythm.bpm", label: "BPM", type: "range", min: 30, max: 180, step: 1, value: 60, suffix: " BPM", help: "From BPM." },
      { path: "audio.rhythm.max_voices", label: "Max voices", type: "range", min: 1, max: 12, step: 1, value: 4, help: "From MAX_VOICES." },
      { path: "audio.rhythm.rhythm_type", label: "Rhythm type", type: "select", value: "debruijn", options: ["debruijn", "euclidian", "christoffel"], help: "From RHYTHM_TYPE." },
      { path: "audio.rhythm.rotate_patterns", label: "Rotate patterns", type: "boolean", value: true, help: "From ROTATE_PATTERNS." },
      { path: "audio.rhythm.step_size_choices", label: "Step size choices", type: "text", value: "4, 6, 8", help: "From STEP_SIZE_CHOICES." },
      { path: "audio.rhythm.decay_per_hit", label: "Decay per hit", type: "range", min: 0.05, max: 1, step: 0.01, value: 0.5, help: "From DECAY_PER_HIT." },
      { path: "audio.rhythm.min_gain", label: "Minimum gain", type: "range", min: 0, max: 0.5, step: 0.01, value: 0.05, help: "From MIN_GAIN." }
    ]
  },
  {
    id: "audio-synthesis",
    title: "Synthesis",
    note: "Sine, bass, glitch, click, hat, and pitch palette controls.",
    controls: [
      { path: "audio.synthesis.sine_amp", label: "Synth amplitude", type: "range", min: 0, max: 1, step: 0.01, value: 0.35, help: "From SINE_AMP." },
      { path: "audio.synthesis.voice_engine", label: "Voice engine", type: "select", value: "synth_sine", options: ["synth_sine", "synth_glitch", "synth_electro_bass", "synth_click", "synth_bass", "synth_hat", "synth_bitcrush_lead"], help: "Future UI control for the synth functions already in code." },
      { path: "audio.synthesis.pitch_mode", label: "Pitch mode", type: "select", value: "random_mode", options: ["random_mode", "ionian", "lydian", "locrian"], help: "Based on MODES_CHOICES." },
      { path: "audio.queue.max_playback_queue", label: "Playback queue", type: "range", min: 1, max: 128, step: 1, value: 32, help: "From MAX_PLAYBACK_QUEUE." }
    ]
  },
  {
    id: "audio-osc",
    title: "Audio OSC Output",
    note: "The audio system sends wave events to the visual system.",
    controls: [
      { path: "audio.osc.enabled", label: "OSC enabled", type: "boolean", value: true, help: "From OSC_ENABLED." },
      { path: "audio.osc.host", label: "OSC host", type: "text", value: "127.0.0.1", help: "From OSC_HOST." },
      { path: "audio.osc.port", label: "OSC port", type: "number", min: 1, max: 65535, step: 1, value: 9000, help: "From OSC_PORT." },
      { path: "audio.osc.address", label: "OSC address", type: "text", value: "/wave", help: "From OSC_ADDRESS." },
      { path: "audio.osc.x_range", label: "OSC X range", type: "text", value: "-6.0, 6.0", help: "From OSC_X_RANGE." },
      { path: "audio.osc.y_range", label: "OSC Y range", type: "text", value: "-1.0, 1.0", help: "From OSC_Y_RANGE." },
      { path: "audio.osc.z_range", label: "OSC Z range", type: "text", value: "-1.5, 1.5", help: "From OSC_Z_RANGE." },
      { path: "audio.osc.duration_scale", label: "Duration scale", type: "range", min: 0.1, max: 3, step: 0.05, value: 0.9, help: "From OSC_DURATION_SCALE." },
      { path: "audio.osc.min_duration", label: "Minimum duration", type: "range", min: 0.01, max: 0.4, step: 0.01, value: 0.05, suffix: "s", help: "From OSC_MIN_DURATION." }
    ]
  },
  {
    id: "visual-scene",
    title: "Visual Scene",
    note: "Window, video, camera, and scene movement.",
    controls: [
      { path: "visual.window.width", label: "Window width", type: "number", min: 320, max: 3840, step: 1, value: 1280, help: "From WIDTH." },
      { path: "visual.window.height", label: "Window height", type: "number", min: 240, max: 2160, step: 1, value: 720, help: "From HEIGHT." },
      { path: "visual.camera.distance", label: "Camera distance", type: "range", min: -40, max: -2, step: 0.1, value: -17, help: "From CAMERA_DISTANCE." },
      { path: "visual.camera.dolly_speed", label: "Camera dolly speed", type: "range", min: 0, max: 4, step: 0.01, value: 1.095, help: "From CAMERA_DOLLY_SPEED." },
      { path: "visual.video.path", label: "Video path", type: "text", value: "background.mp4", help: "From VIDEO_PATH." },
      { path: "visual.video.muted", label: "Video muted", type: "boolean", value: true, help: "From VIDEO_MUTED." }
    ]
  },
  {
    id: "visual-trails",
    title: "Fireflies & Trails",
    note: "Particle capacity, spawn plane, trail spacing, and motion feel.",
    controls: [
      { path: "visual.trails.max_points", label: "Max trail points", type: "range", min: 1000, max: 500000, step: 1000, value: 250000, help: "From MAX_TRAIL_POINTS." },
      { path: "visual.trails.sample_distance", label: "Trail sample distance", type: "range", min: 0.05, max: 4, step: 0.01, value: 1.0055, help: "From TRAIL_SAMPLE_DISTANCE." },
      { path: "visual.spawn.forward_distance", label: "Spawn forward distance", type: "range", min: 1, max: 40, step: 0.1, value: 15.5, help: "From SPAWN_FORWARD_DISTANCE." },
      { path: "visual.spawn.ground_height", label: "Spawn ground height", type: "range", min: -6, max: 4, step: 0.05, value: -1.15, help: "From SPAWN_GROUND_HEIGHT." },
      { path: "visual.spawn.x_scale", label: "Spawn X scale", type: "range", min: 0.1, max: 10, step: 0.05, value: 3.1, help: "From SPAWN_X_SCALE." },
      { path: "visual.spawn.y_scale", label: "Spawn Y scale", type: "range", min: 0.1, max: 8, step: 0.05, value: 1.35, help: "From SPAWN_Y_SCALE." },
      { path: "visual.spawn.z_scale", label: "Spawn Z scale", type: "range", min: 0.1, max: 8, step: 0.05, value: 0.8, help: "From SPAWN_Z_SCALE." }
    ]
  },
  {
    id: "visual-shader",
    title: "Shader & Glow",
    note: "Values currently hard-coded in draw_points for trails and heads.",
    controls: [
      { path: "visual.shader.trail_size_scale", label: "Trail size scale", type: "range", min: 1, max: 80, step: 1, value: 20, help: "Currently draw_points trail size_scale." },
      { path: "visual.shader.trail_max_size", label: "Trail max point size", type: "range", min: 1, max: 80, step: 1, value: 20, help: "Currently draw_points trail max_size." },
      { path: "visual.shader.trail_glow_power", label: "Trail glow power", type: "range", min: 0.05, max: 2, step: 0.01, value: 0.28, help: "Currently draw_points trail glow_power." },
      { path: "visual.shader.trail_twinkle", label: "Trail twinkle", type: "range", min: 0, max: 1, step: 0.01, value: 0, help: "Currently draw_points trail twinkle_amount." },
      { path: "visual.shader.head_size_scale", label: "Head size scale", type: "range", min: 1, max: 100, step: 1, value: 24, help: "Currently draw_points head size_scale." },
      { path: "visual.shader.head_max_size", label: "Head max point size", type: "range", min: 1, max: 100, step: 1, value: 24, help: "Currently draw_points head max_size." },
      { path: "visual.shader.head_glow_power", label: "Head glow power", type: "range", min: 0.05, max: 2, step: 0.01, value: 0.45, help: "Currently draw_points head glow_power." },
      { path: "visual.shader.head_twinkle", label: "Head twinkle", type: "range", min: 0, max: 1, step: 0.01, value: 0.08, help: "Currently draw_points head twinkle_amount." }
    ]
  }
];

const presets = {
  "Dreamy": {
    "audio.rhythm.bpm": 48,
    "audio.rhythm.max_voices": 3,
    "audio.synthesis.sine_amp": 0.28,
    "visual.shader.trail_glow_power": 0.18,
    "visual.shader.head_twinkle": 0.16,
    "visual.trails.sample_distance": 0.7
  },
  "Dense": {
    "audio.rhythm.bpm": 96,
    "audio.rhythm.max_voices": 6,
    "audio.rhythm.decay_per_hit": 0.72,
    "visual.trails.max_points": 420000,
    "visual.shader.trail_size_scale": 28,
    "visual.shader.head_size_scale": 36
  },
  "Minimal": {
    "audio.rhythm.bpm": 60,
    "audio.rhythm.max_voices": 2,
    "audio.synthesis.sine_amp": 0.18,
    "visual.trails.max_points": 80000,
    "visual.shader.trail_twinkle": 0,
    "visual.shader.head_twinkle": 0.04
  }
};

const state = {};
const initial = {};
const cards = new Map();
let lastPayload = null;
let sendTimer = null;

const controlsEl = document.querySelector("#controls");
const navEl = document.querySelector("#nav");
const payloadEl = document.querySelector("#payload");
const toastEl = document.querySelector("#toast");

function init() {
  params.forEach(group => {
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
      state[control.path] = control.value;
      initial[control.path] = control.value;
      grid.appendChild(createControl(control));
    });

    controlsEl.appendChild(section);
  });

  renderPresets();
  wireEvents();
  updateReadouts();
}

function createControl(control) {
  const card = document.createElement("article");
  card.className = "control";
  card.dataset.path = control.path;
  card.dataset.search = `${control.path} ${control.label} ${control.help || ""}`.toLowerCase();

  const value = formatValue(control, control.value);

  card.innerHTML = `
    <div class="control-head">
      <div>
        <h4>${control.label}</h4>
        <p>${control.help || ""}</p>
      </div>
      <span class="value">${value}</span>
    </div>
    <div class="input-slot"></div>
  `;

  const slot = card.querySelector(".input-slot");
  const valueEl = card.querySelector(".value");

  let input;

  if (control.type === "range") {
    slot.className = "input-slot range-row";
    input = document.createElement("input");
    input.type = "range";
    input.min = control.min;
    input.max = control.max;
    input.step = control.step;
    input.value = control.value;

    const number = document.createElement("input");
    number.type = "number";
    number.min = control.min;
    number.max = control.max;
    number.step = control.step;
    number.value = control.value;

    input.addEventListener("input", () => {
      number.value = input.value;
      updateControl(control, castValue(control, input.value), valueEl);
    });

    number.addEventListener("input", () => {
      input.value = number.value;
      updateControl(control, castValue(control, number.value), valueEl);
    });

    slot.append(input, number);
  }

  if (control.type === "number") {
    input = document.createElement("input");
    input.type = "number";
    input.min = control.min ?? "";
    input.max = control.max ?? "";
    input.step = control.step ?? 1;
    input.value = control.value;
    input.addEventListener("input", () => updateControl(control, castValue(control, input.value), valueEl));
    slot.appendChild(input);
  }

  if (control.type === "text") {
    input = document.createElement("input");
    input.type = "text";
    input.value = control.value;
    input.addEventListener("input", () => updateControl(control, input.value, valueEl));
    slot.appendChild(input);
  }

  if (control.type === "select") {
    input = document.createElement("select");
    control.options.forEach(option => {
      const opt = document.createElement("option");
      opt.value = option;
      opt.textContent = option;
      input.appendChild(opt);
    });
    input.value = control.value;
    input.addEventListener("change", () => updateControl(control, input.value, valueEl));
    slot.appendChild(input);
  }

  if (control.type === "boolean") {
    const label = document.createElement("label");
    label.className = "toggle";
    input = document.createElement("input");
    input.type = "checkbox";
    input.checked = control.value;
    input.addEventListener("change", () => updateControl(control, input.checked, valueEl));
    label.append(input, document.createElement("span"));
    label.querySelector("span").textContent = "Enabled";
    slot.appendChild(label);
  }

  cards.set(control.path, { card, control, valueEl, input });
  return card;
}

function updateControl(control, value, valueEl, silent = false) {
  const previous = state[control.path];
  state[control.path] = value;
  valueEl.textContent = formatValue(control, value);

  updateReadouts();

  if (!silent) {
    const patch = {
      source: "control-panel",
      timestamp: new Date().toISOString(),
      changes: [{ path: control.path, value, previous }]
    };

    showPayload(patch);

    if (document.querySelector("#autoSend").checked) {
      scheduleSend(patch);
    }
  }
}

function castValue(control, raw) {
  if (control.type === "number" || control.type === "range") {
    return Number(raw);
  }
  return raw;
}

function formatValue(control, value) {
  if (typeof value === "boolean") return value ? "on" : "off";
  return `${value}${control.suffix || ""}`;
}

function scheduleSend(payload) {
  clearTimeout(sendTimer);
  sendTimer = setTimeout(() => sendPayload(payload), 180);
}

async function sendPayload(payload) {
  lastPayload = payload;

  const mock = document.querySelector("#mockMode").checked;
  const endpoint = document.querySelector("#endpoint").value;

  if (mock) {
    setStatus("Mock sent", false);
    document.querySelector("#lastSync").textContent = new Date().toLocaleTimeString();
    toast("Mock patch created");
    return;
  }

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    setStatus("Connected", true);
    document.querySelector("#lastSync").textContent = new Date().toLocaleTimeString();
    toast("Patch sent");
  } catch (error) {
    setStatus("Endpoint unavailable", false);
    toast(error.message);
  }
}

function showPayload(payload) {
  lastPayload = payload;
  payloadEl.textContent = JSON.stringify(payload, null, 2);
}

function sendAll() {
  const changes = Object.entries(state).map(([path, value]) => ({
    path,
    value,
    previous: initial[path]
  }));

  const payload = {
    source: "control-panel",
    timestamp: new Date().toISOString(),
    changes
  };

  showPayload(payload);
  sendPayload(payload);
}

function renderPresets() {
  const wrap = document.querySelector("#presets");

  Object.entries(presets).forEach(([name, values]) => {
    const btn = document.createElement("button");
    btn.className = "secondary small";
    btn.type = "button";
    btn.textContent = name;
    btn.addEventListener("click", () => applyPreset(name, values));
    wrap.appendChild(btn);
  });
}

function applyPreset(name, values) {
  const changes = [];

  Object.entries(values).forEach(([path, value]) => {
    const entry = cards.get(path);
    if (!entry) return;

    const previous = state[path];
    state[path] = value;
    entry.valueEl.textContent = formatValue(entry.control, value);
    syncInput(entry.input, value);

    changes.push({ path, value, previous });
  });

  updateReadouts();

  const payload = {
    source: "control-panel",
    preset: name,
    timestamp: new Date().toISOString(),
    changes
  };

  showPayload(payload);

  if (document.querySelector("#autoSend").checked) {
    sendPayload(payload);
  }
}

function syncInput(input, value) {
  if (!input) return;
  if (input.type === "checkbox") input.checked = value;
  else input.value = value;
}

function resetAll() {
  const changes = [];

  Object.entries(initial).forEach(([path, value]) => {
    const entry = cards.get(path);
    if (!entry) return;

    const previous = state[path];
    state[path] = value;
    entry.valueEl.textContent = formatValue(entry.control, value);
    syncInput(entry.input, value);

    changes.push({ path, value, previous });
  });

  updateReadouts();

  const payload = {
    source: "control-panel",
    action: "reset-ui",
    timestamp: new Date().toISOString(),
    changes
  };

  showPayload(payload);
  toast("UI reset");
}

function updateReadouts() {
  document.querySelector("#bpmReadout").textContent = state["audio.rhythm.bpm"];
  document.querySelector("#rhythmReadout").textContent = state["audio.rhythm.rhythm_type"];
  document.querySelector("#trailReadout").textContent = `${Math.round(state["visual.trails.max_points"] / 1000)}k`;
  document.querySelector("#oscReadout").textContent =
    `${state["audio.osc.host"]}:${state["audio.osc.port"]}`;
}

function setStatus(text, online) {
  document.querySelector("#statusText").textContent = text;
  document.querySelector("#statusDot").classList.toggle("online", online);
}

function searchControls(query) {
  const q = query.trim().toLowerCase();

  document.querySelectorAll(".control").forEach(card => {
    card.classList.toggle("hidden", q && !card.dataset.search.includes(q));
  });
}

async function stopApp() {
  const mock = document.querySelector("#mockMode").checked;

  if (mock) {
    toast("Mock stop action");
    showPayload({
      source: "control-panel",
      action: "stop",
      timestamp: new Date().toISOString()
    });
    return;
  }

  try {
    await fetch("http://127.0.0.1:8000/stop", { method: "POST" });
    toast("Stop request sent");
  } catch (error) {
    toast(error.message);
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
  document.querySelector("#resetBtn").addEventListener("click", resetAll);
  document.querySelector("#copyBtn").addEventListener("click", copyPayload);
  document.querySelector("#stopBtn").addEventListener("click", stopApp);

  document.querySelector("#search").addEventListener("input", event => {
    searchControls(event.target.value);
  });

  document.querySelector("#mockMode").addEventListener("change", event => {
    setStatus(event.target.checked ? "Mock UI mode" : "Backend mode", false);
  });
}

init();