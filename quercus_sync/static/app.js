const $ = (sel) => document.querySelector(sel);

let activeJob = null;
let eventSource = null;

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const message = typeof detail === "string" ? detail : res.statusText;
    throw new Error(message);
  }
  return data;
}

function setRunning(running) {
  $("#sync-btn").disabled = running;
  $("#sync-all").disabled = running;
  $("#stop-btn").disabled = !running;
}

async function loadConfig() {
  const cfg = await api("/api/config");
  const demo = cfg.demo_mode || !cfg.token_set;
  $("#mode-pill").textContent = demo ? "Demo" : "Live";
  $("#mode-pill").classList.toggle("live", !demo);
  $("#env-banner").hidden = !demo;
  $("#folder-hint").textContent = cfg.download_dir || "";
  return cfg;
}

async function loadMe() {
  try {
    const me = await api("/api/me");
    $("#who").textContent = me.name || "";
  } catch (err) {
    $("#who").textContent = err.message;
  }
}

let coursesLoad = 0;

async function loadCourses() {
  const gen = ++coursesLoad;
  const empty = $("#course-empty");
  const list = $("#course-list");
  list.innerHTML = "";
  empty.hidden = false;
  empty.textContent = "Loading…";
  try {
    const data = await api("/api/courses");
    if (gen !== coursesLoad) return;
    const seen = new Set();
    const courses = [];
    for (const course of data.courses || []) {
      if (seen.has(course.id)) continue;
      seen.add(course.id);
      courses.push(course);
    }
    if (!courses.length) {
      empty.textContent = "No open courses.";
      return;
    }
    empty.hidden = true;
    for (const course of courses) {
      const li = document.createElement("li");
      const access = course.access === "past" ? "Past" : "Current";
      li.innerHTML = `
        <input type="checkbox" checked data-id="${course.id}">
        <div>
          <strong>${escapeHtml(course.course_code || "Course")}</strong>
          ${escapeHtml(course.name || "")}
          <span>${escapeHtml(course.term || "")} · ${access}</span>
        </div>`;
      list.appendChild(li);
    }
  } catch (err) {
    if (gen !== coursesLoad) return;
    empty.textContent = err.message;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function loadLibrary() {
  const data = await api("/api/library");
  $("#lib-root").textContent = data.root;
  const body = $("#library tbody");
  body.innerHTML = "";
  $("#lib-empty").hidden = data.items.length > 0;
  for (const item of data.items) {
    const tr = document.createElement("tr");
    const href = `/api/library/file?path=${encodeURIComponent(item.path)}`;
    tr.innerHTML = `<td><a href="${href}" target="_blank" rel="noreferrer">${escapeHtml(item.path)}</a></td><td>${escapeHtml(item.kind)}</td><td>${formatSize(item.size)}</td>`;
    body.appendChild(tr);
  }
}

function formatSize(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function selectedCourseIds(all = false) {
  const boxes = [...document.querySelectorAll('#course-list input[type="checkbox"]')];
  const ids = [];
  const seen = new Set();
  for (const box of boxes) {
    if (!all && !box.checked) continue;
    const id = Number(box.dataset.id);
    if (seen.has(id)) continue;
    seen.add(id);
    ids.push(id);
  }
  return ids;
}

function logLine(text, cls) {
  const item = document.createElement("li");
  if (cls) item.className = cls;
  item.textContent = text;
  $("#log").appendChild(item);
  item.scrollIntoView({ block: "end" });
}

function finishSync(stats) {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  activeJob = null;
  setRunning(false);
  if (stats) {
    $("#log-meta").textContent = `Saved ${stats.downloaded || 0} · skipped ${stats.skipped || 0} · failed ${stats.failed || 0}`;
  }
  loadLibrary();
}

async function runSync(all = false) {
  const ids = selectedCourseIds(all);
  if (!ids.length) {
    logLine("Select at least one course.", "fail");
    return;
  }
  setRunning(true);
  $("#log").innerHTML = "";
  $("#log-meta").textContent = "Starting…";
  try {
    const { job_id } = await api("/api/sync", {
      method: "POST",
      body: JSON.stringify({ course_ids: ids }),
    });
    activeJob = job_id;
    eventSource = new EventSource(`/api/sync/${job_id}/events`);
    eventSource.onmessage = (msg) => {
      const event = JSON.parse(msg.data);
      if (event.type === "log") logLine(event.message);
      if (event.type === "course_start") logLine(`${event.course} · ${event.term}`, "course");
      if (event.type === "item") {
        const cls = event.status === "downloaded" ? "down" : event.status === "skipped" ? "skip" : "fail";
        const extra = event.reason ? ` (${event.reason})` : "";
        logLine(`${event.status}  ${event.path}${extra}`, cls);
      }
      if (event.type === "error") logLine(event.message, "error");
      if (event.type === "done") finishSync(event.stats);
    };
    eventSource.onerror = () => finishSync();
  } catch (err) {
    logLine(err.message, "error");
    finishSync();
  }
}

async function stopSync() {
  if (!activeJob) return;
  $("#stop-btn").disabled = true;
  $("#log-meta").textContent = "Stopping…";
  try {
    await api(`/api/sync/${activeJob}/stop`, { method: "POST" });
  } catch (err) {
    logLine(err.message, "error");
    finishSync();
  }
}

$("#reload-courses").addEventListener("click", loadCourses);
$("#sync-btn").addEventListener("click", () => runSync(false));
$("#sync-all").addEventListener("click", () => runSync(true));
$("#stop-btn").addEventListener("click", stopSync);

loadConfig().then(loadMe).then(loadCourses).then(loadLibrary);
