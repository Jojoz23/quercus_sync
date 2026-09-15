const $ = (sel) => document.querySelector(sel);

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

function setStatus(el, text, ok = true) {
  el.hidden = !text;
  el.textContent = text;
  el.className = `status ${ok ? "ok" : "bad"}`;
}

function includesFromForm(form) {
  return [...form.querySelectorAll('input[name="include"]:checked')].map((n) => n.value);
}

async function loadConfig() {
  const cfg = await api("/api/config");
  const form = $("#settings-form");
  form.canvas_url.value = cfg.canvas_url;
  form.download_dir.value = cfg.download_dir;
  form.querySelectorAll('input[name="include"]').forEach((box) => {
    box.checked = cfg.include.includes(box.value);
  });
  $("#token-hint").textContent = cfg.token_set
    ? `Saved token ${cfg.token_preview}. It stays in data/config.json on this computer.`
    : "No token saved — demo library is active.";
  const demo = cfg.demo_mode || !cfg.token_set;
  $("#mode-pill").textContent = demo ? "Demo campus" : "Live Quercus";
  $("#mode-pill").classList.toggle("live", !demo);
  $("#toggle-demo").textContent = demo ? "Use live Quercus" : "Use demo campus";
  return cfg;
}

async function loadMe() {
  try {
    const me = await api("/api/me");
    $("#who").textContent = me.demo
      ? `${me.name} · sample student`
      : `${me.name} · ${me.login || "signed in"}`;
  } catch (err) {
    $("#who").textContent = err.message;
  }
}

async function loadCourses() {
  const empty = $("#course-empty");
  const list = $("#course-list");
  list.innerHTML = "";
  empty.hidden = false;
  empty.textContent = "Loading courses…";
  try {
    const data = await api("/api/courses");
    if (!data.courses.length) {
      empty.textContent = "No courses came back. Check the token — this lists every course you can still open, including past terms.";
      return;
    }
    empty.hidden = true;
    for (const course of data.courses) {
      const li = document.createElement("li");
      const access = course.access === "past" ? "Past term" : "Current";
      li.innerHTML = `
        <input type="checkbox" checked data-id="${course.id}">
        <div>
          <strong>${escapeHtml(course.course_code || "Course")}</strong>
          ${escapeHtml(course.name || "")}
          <span>${escapeHtml(course.term || "No term")} · ${access}</span>
        </div>`;
      list.appendChild(li);
    }
  } catch (err) {
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
  return boxes.filter((b) => all || b.checked).map((b) => Number(b.dataset.id));
}

function logLine(text, cls) {
  const item = document.createElement("li");
  if (cls) item.className = cls;
  item.textContent = text;
  $("#log").appendChild(item);
  item.scrollIntoView({ block: "end" });
}

async function runSync(all = false) {
  const ids = selectedCourseIds(all);
  if (!ids.length) {
    logLine("Select at least one course.", "fail");
    return;
  }
  $("#sync-btn").disabled = true;
  $("#sync-all").disabled = true;
  $("#log").innerHTML = "";
  $("#log-meta").textContent = "Starting…";
  try {
    const { job_id } = await api("/api/sync", {
      method: "POST",
      body: JSON.stringify({ course_ids: ids }),
    });
    const events = new EventSource(`/api/sync/${job_id}/events`);
    events.onmessage = (msg) => {
      const event = JSON.parse(msg.data);
      if (event.type === "log") logLine(event.message);
      if (event.type === "course_start") logLine(`${event.course} · ${event.term}`, "course");
      if (event.type === "item") {
        const cls = event.status === "downloaded" ? "down" : event.status === "skipped" ? "skip" : "fail";
        const extra = event.reason ? ` (${event.reason})` : "";
        logLine(`${event.status}  ${event.path}${extra}`, cls);
      }
      if (event.type === "error") logLine(event.message, "error");
      if (event.type === "done") {
        const s = event.stats || {};
        $("#log-meta").textContent = `Saved ${s.downloaded || 0} · skipped ${s.skipped || 0} · failed ${s.failed || 0}`;
        events.close();
        $("#sync-btn").disabled = false;
        $("#sync-all").disabled = false;
        loadLibrary();
      }
    };
    events.onerror = () => {
      events.close();
      $("#sync-btn").disabled = false;
      $("#sync-all").disabled = false;
    };
  } catch (err) {
    logLine(err.message, "error");
    $("#sync-btn").disabled = false;
    $("#sync-all").disabled = false;
  }
}

$("#settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const status = $("#save-status");
  try {
    await api("/api/config", {
      method: "PUT",
      body: JSON.stringify({
        canvas_url: form.canvas_url.value,
        token: form.token.value || null,
        download_dir: form.download_dir.value,
        include: includesFromForm(form),
        demo_mode: !form.token.value,
      }),
    });
    form.token.value = "";
    setStatus(status, "Saved on this machine.", true);
    await loadConfig();
    await loadMe();
    await loadCourses();
  } catch (err) {
    setStatus(status, err.message, false);
  }
});

$("#clear-token").addEventListener("click", async () => {
  await api("/api/config", {
    method: "PUT",
    body: JSON.stringify({ canvas_url: "https://q.utoronto.ca", clear_token: true, demo_mode: true }),
  });
  await loadConfig();
  await loadMe();
  await loadCourses();
  setStatus($("#save-status"), "Token cleared. Demo campus is on.", true);
});

$("#toggle-demo").addEventListener("click", async () => {
  const cfg = await api("/api/config");
  const currentlyDemo = cfg.demo_mode || !cfg.token_set;
  if (currentlyDemo && !cfg.token_set) {
    setStatus($("#save-status"), "Paste a Quercus token before leaving the demo campus.", false);
    return;
  }
  await api("/api/config", {
    method: "PUT",
    body: JSON.stringify({ canvas_url: cfg.canvas_url, demo_mode: !currentlyDemo }),
  });
  await loadConfig();
  await loadMe();
  await loadCourses();
});

$("#reload-courses").addEventListener("click", loadCourses);
$("#sync-btn").addEventListener("click", () => runSync(false));
$("#sync-all").addEventListener("click", () => runSync(true));

loadConfig().then(loadMe).then(loadCourses).then(loadLibrary);
