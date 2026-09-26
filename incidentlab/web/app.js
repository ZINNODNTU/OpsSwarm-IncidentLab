const state = {
  services: [],
  scenarios: [],
  runs: [],
  github: null,
  opsswarm: null,
  opsswarm: null,
  apiOk: false,
  scenarioFilter: "all",
  lastRefresh: null
};

const viewNames = {
  dashboard: "Overview",
  scenarios: "Scenarios",
  faults: "Fault Runner",
  services: "Services",
  runs: "Runs & Evidence",
  monitoring: "Integrations"
};

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function api(path, options) {
  const opts = options || {};
  const headers = Object.assign({"Content-Type": "application/json"}, opts.headers || {});
  return fetch(path, Object.assign({}, opts, {headers: headers})).then(async function(response) {
    if (!response.ok) {
      const body = await response.text();
      throw new Error(body || ("HTTP " + response.status));
    }
    return response.json();
  });
}

function toast(message, type) {
  const stack = document.getElementById("toastStack");
  const item = document.createElement("div");
  item.className = "toast " + (type || "");
  item.textContent = message;
  stack.appendChild(item);
  window.setTimeout(function() {
    item.style.opacity = "0";
    item.style.transform = "translateY(5px)";
    window.setTimeout(function() { item.remove(); }, 180);
  }, 3000);
}

function showView(id) {
  if (!document.getElementById(id)) return;
  document.querySelectorAll(".view").forEach(function(el) { el.classList.remove("active"); });
  document.getElementById(id).classList.add("active");
  document.querySelectorAll(".nav-item").forEach(function(el) {
    el.classList.toggle("active", el.dataset.view === id);
  });
  document.getElementById("currentViewName").textContent = viewNames[id] || id;
  window.scrollTo({top: 0, behavior: "smooth"});
}

function openPath(path) {
  window.open(path, "_blank", "noopener");
}

function openExternal(url) {
  window.open(url, "_blank", "noopener");
}

function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, {
    month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit"
  }).format(d);
}

function formatAgo(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  const seconds = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (seconds < 60) return seconds + "s ago";
  if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
  if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
  return Math.floor(seconds / 86400) + "d ago";
}

function runState(run) {
  return String((run && run.state) || "unknown");
}

function isActiveRun(run) {
  const s = runState(run).toLowerCase();
  return s === "fault_injected" || s === "investigating" || s === "recovering" || s === "active";
}

function isRecoveredRun(run) {
  const s = runState(run).toLowerCase();
  return s.indexOf("recover") >= 0 || s === "reset" || s === "closed" || s === "pass" || s === "verified";
}

function badge(text, kind) {
  return '<span class="status-badge ' + esc(kind || "") + '">' + esc(text) + "</span>";
}

function runBadge(run) {
  const s = runState(run);
  if (isActiveRun(run)) return badge(s.replace(/_/g, " ").toUpperCase(), "warn");
  if (isRecoveredRun(run)) return badge(s.replace(/_/g, " ").toUpperCase(), "");
  return badge(s.replace(/_/g, " ").toUpperCase(), "muted");
}

function healthBadge(service) {
  if (service && service.healthy) return badge("HEALTHY", "");
  return badge((service && service.status) || "UNHEALTHY", "bad");
}

function renderHeaderState() {
  const apiEl = document.getElementById("apiState");
  apiEl.className = "health-chip " + (state.apiOk ? "ok" : "bad");
  apiEl.innerHTML = "<i></i><span>" + (state.apiOk ? "API Online" : "API Offline") + "</span>";

  const ghEl = document.getElementById("githubState");
  if (!state.github) {
    ghEl.className = "health-chip neutral";
    ghEl.innerHTML = "<i></i><span>GitHub unknown</span>";
  } else if (state.github.enabled) {
    ghEl.className = "health-chip ok";
    ghEl.innerHTML = "<i></i><span>GitHub Ready</span>";
  } else {
    ghEl.className = "health-chip neutral";
    ghEl.innerHTML = "<i></i><span>GitHub not configured</span>";
  }
}

function renderMetrics() {
  const total = state.services.length;
  const healthy = state.services.filter(function(s) { return !!s.healthy; }).length;
  const active = state.runs.filter(isActiveRun).length;

  document.getElementById("mServices").textContent = total || "0";
  document.getElementById("mHealthy").textContent = total ? (healthy + "/" + total) : "0";
  document.getElementById("mActive").textContent = active;
  document.getElementById("mRuns").textContent = state.runs.length;
  document.getElementById("mServiceSub").textContent = total ? "DemoMart simulator stack" : "No services reported";
  document.getElementById("mHealthySub").textContent = total && healthy === total ? "All services nominal" : ((total - healthy) + " service(s) degraded");
  document.getElementById("navServiceCount").textContent = total;
  document.getElementById("navScenarioCount").textContent = state.scenarios.length;
  document.getElementById("navRunCount").textContent = state.runs.length;
}

function renderServiceOverview() {
  const root = document.getElementById("serviceOverview");
  if (!state.services.length) {
    root.innerHTML = '<div class="empty-state">No service data available.</div>';
    return;
  }

  root.innerHTML = state.services.map(function(s) {
    const latency = s.latency_ms == null ? "—" : (s.latency_ms + " ms");
    const error = s.error_rate == null ? "—" : (Math.round(Number(s.error_rate) * 1000) / 10 + "%");
    const dot = s.healthy ? "up" : "down";
    return '<article class="service-node" onclick="serviceDetail(\'' + esc(s.service) + '\')">' +
      '<div class="service-node-top"><h3>' + esc(s.service) + '</h3><i class="health-dot ' + dot + '"></i></div>' +
      '<p>Version ' + esc(s.version || "—") + '</p>' +
      '<div class="mini-metrics">' +
        '<div class="mini-metric"><span>Latency</span><b>' + esc(latency) + '</b></div>' +
        '<div class="mini-metric"><span>Error rate</span><b>' + esc(error) + '</b></div>' +
      '</div></article>';
  }).join("");
}

function metricPercent(value, max) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, (n / max) * 100));
}

function renderServiceCards() {
  const root = document.getElementById("serviceCards");
  if (!state.services.length) {
    root.innerHTML = '<div class="empty-state">No service data available.</div>';
    return;
  }

  root.innerHTML = state.services.map(function(s) {
    const cpu = s.cpu_percent == null ? "—" : (s.cpu_percent + "%");
    const memory = s.memory_percent == null ? "—" : (s.memory_percent + "%");
    const error = s.error_rate == null ? "—" : (Math.round(Number(s.error_rate) * 1000) / 10 + "%");
    const latency = s.latency_ms == null ? "—" : (s.latency_ms + " ms");
    return '<article class="service-card">' +
      '<div class="service-card-head"><div><h3>' + esc(s.service) + '</h3><span class="version">Version ' + esc(s.version || "—") + '</span></div>' + healthBadge(s) + '</div>' +
      '<div class="metric-pairs">' +
        '<div class="metric-pair"><span>Latency</span><b>' + esc(latency) + '</b></div>' +
        '<div class="metric-pair"><span>Error rate</span><b>' + esc(error) + '</b></div>' +
        '<div class="metric-pair"><span>CPU</span><b>' + esc(cpu) + '</b></div>' +
        '<div class="metric-pair"><span>Memory</span><b>' + esc(memory) + '</b></div>' +
      '</div>' +
      '<div class="bar-row"><div class="bar-label"><span>CPU utilization</span><span>' + esc(cpu) + '</span></div><div class="bar"><i style="width:' + metricPercent(s.cpu_percent, 100) + '%"></i></div></div>' +
      '<div class="bar-row"><div class="bar-label"><span>Memory utilization</span><span>' + esc(memory) + '</span></div><div class="bar"><i style="width:' + metricPercent(s.memory_percent, 100) + '%"></i></div></div>' +
      '<div style="margin-top:13px"><button class="btn btn-secondary" onclick="serviceDetail(\'' + esc(s.service) + '\')">Inspect metrics</button></div>' +
    '</article>';
  }).join("");
}

function renderLatestRuns() {
  const root = document.getElementById("latestRuns");
  const runs = state.runs.slice().sort(function(a, b) {
    return String(b.created_at || "").localeCompare(String(a.created_at || ""));
  }).slice(0, 6);

  if (!runs.length) {
    root.innerHTML = '<div class="empty-state compact">No runs yet. Launch a scenario to create evidence.</div>';
    return;
  }

  root.innerHTML = runs.map(function(run) {
    const activeClass = isActiveRun(run) ? "active" : (isRecoveredRun(run) ? "done" : "");
    return '<div class="timeline-item">' +
      '<i class="timeline-bullet ' + activeClass + '"></i>' +
      '<div><strong>' + esc(run.scenario_id || "Scenario") + ' · ' + esc(run.service || "unknown") + '</strong>' +
      '<p>' + esc(run.fault || "fault") + ' · ' + esc(run.run_id || "run") + '</p></div>' +
      '<time>' + esc(formatAgo(run.created_at)) + '</time></div>';
  }).join("");
}

function buildScenarioFilters() {
  const root = document.getElementById("scenarioFilters");
  const services = Array.from(new Set(state.scenarios.map(function(s) { return s.service; }).filter(Boolean))).sort();
  root.innerHTML = '<button class="filter ' + (state.scenarioFilter === "all" ? "active" : "") + '" data-filter="all">All</button>' +
    services.map(function(name) {
      return '<button class="filter ' + (state.scenarioFilter === name ? "active" : "") + '" data-filter="' + esc(name) + '">' + esc(name) + '</button>';
    }).join("");

  root.querySelectorAll(".filter").forEach(function(button) {
    button.addEventListener("click", function() {
      state.scenarioFilter = button.dataset.filter;
      buildScenarioFilters();
      renderScenarios();
    });
  });
}

function renderScenarios() {
  const query = document.getElementById("scenarioSearch").value.trim().toLowerCase();
  const filtered = state.scenarios.filter(function(s) {
    const matchesFilter = state.scenarioFilter === "all" || s.service === state.scenarioFilter;
    const haystack = [s.id, s.name, s.description, s.service, s.fault].join(" ").toLowerCase();
    return matchesFilter && (!query || haystack.indexOf(query) >= 0);
  });

  const root = document.getElementById("scenarioList");
  if (!filtered.length) {
    root.innerHTML = '<div class="empty-state">No scenarios match this filter.</div>';
    return;
  }

  root.innerHTML = filtered.map(function(s) {
    const expected = Array.isArray(s.expected_alerts) && s.expected_alerts.length ? s.expected_alerts[0] : "monitoring event";
    return '<article class="scenario-card">' +
      '<div class="scenario-head"><span class="scenario-id">' + esc(s.id) + '</span><span class="service-tag">' + esc(s.service) + '</span></div>' +
      '<h3>' + esc(s.name || s.id) + '</h3>' +
      '<p>' + esc(s.description || "Controlled incident scenario") + '</p>' +
      '<div class="scenario-contract"><span class="fault-tag">' + esc(s.fault) + '</span>' +
        (s.value !== undefined ? '<span class="service-tag">value: ' + esc(s.value) + '</span>' : '') +
      '</div>' +
      '<div class="scenario-footer"><small>Alert: ' + esc(expected) + '</small><button class="btn btn-primary" onclick="selectScenario(\'' + esc(s.id) + '\')">Use scenario</button></div>' +
    '</article>';
  }).join("");
}

function populateScenarioSelect() {
  const select = document.getElementById("scenarioSelect");
  const previous = select.value;
  select.innerHTML = state.scenarios.map(function(s) {
    return '<option value="' + esc(s.id) + '">' + esc(s.id) + " — " + esc(s.name || (s.service + " / " + s.fault)) + '</option>';
  }).join("");
  if (previous && state.scenarios.some(function(s) { return s.id === previous; })) select.value = previous;
  updateFaultInfo();
}

function selectedScenario() {
  const id = document.getElementById("scenarioSelect").value;
  return state.scenarios.find(function(s) { return s.id === id; }) || null;
}

function updateFaultInfo() {
  const s = selectedScenario();
  const root = document.getElementById("faultInfo");
  if (!s) {
    root.innerHTML = '<div class="empty-state compact">Select a scenario.</div>';
    document.getElementById("readyService").textContent = "—";
    return;
  }
  const alertName = Array.isArray(s.expected_alerts) ? s.expected_alerts.join(", ") : "—";
  root.innerHTML =
    '<div class="preview-title"><strong>' + esc(s.name || s.id) + '</strong><span class="service-tag">' + esc(s.service) + '</span></div>' +
    '<div class="preview-grid">' +
      '<div class="preview-cell"><span>Fault</span><b>' + esc(s.fault) + '</b></div>' +
      '<div class="preview-cell"><span>Expected state</span><b>' + esc(s.expected_state || "—") + '</b></div>' +
      '<div class="preview-cell"><span>Expected alert</span><b>' + esc(alertName) + '</b></div>' +
    '</div>';
  document.getElementById("readyService").textContent = s.service + " · " + (state.services.find(function(x){return x.service === s.service;})?.healthy ? "healthy" : "check state");
}

function selectScenario(id) {
  const select = document.getElementById("scenarioSelect");
  select.value = id;
  updateFaultInfo();
  showView("faults");
}

function renderRuns() {
  const q = document.getElementById("runSearch").value.trim().toLowerCase();
  const runs = state.runs.slice().sort(function(a, b) {
    return String(b.created_at || "").localeCompare(String(a.created_at || ""));
  }).filter(function(run) {
    if (!q) return true;
    return [run.run_id, run.scenario_id, run.service, run.fault, run.state].join(" ").toLowerCase().indexOf(q) >= 0;
  });

  const body = document.getElementById("runTableBody");
  if (!runs.length) {
    body.innerHTML = '<tr><td colspan="8"><div class="empty-state">No evidence runs found.</div></td></tr>';
    return;
  }

  body.innerHTML = runs.map(function(run, index) {
    let github = "—";
    if (run.github && run.github.issue_url) {
      github = '<a class="github-link" href="' + esc(run.github.issue_url) + '" target="_blank" rel="noopener">Issue #' + esc(run.github.issue_number || "↗") + '</a>';
    } else if (run.github && run.github.status) {
      github = esc(run.github.status);
    }
    return '<tr>' +
      '<td><strong class="mono">' + esc(run.run_id || "—") + '</strong></td>' +
      '<td>' + esc(run.scenario_id || "—") + '</td>' +
      '<td>' + esc(run.service || "—") + '</td>' +
      '<td><span class="mono">' + esc(run.fault || "—") + '</span></td>' +
      '<td>' + runBadge(run) + '</td>' +
      '<td>' + esc(formatDate(run.created_at)) + '</td>' +
      '<td>' + github + '</td>' +
      '<td><button class="row-link" onclick="showRunDetail(' + index + ', true)">Inspect →</button></td>' +
    '</tr>';
  }).join("");

  body.querySelectorAll(".row-link").forEach(function(button, index) {
    button.onclick = function() { showRunObject(runs[index]); };
  });
}

function showRunObject(run) {
  if (!run) return;
  const githubUrl = run.github && run.github.issue_url;
  const githubText = githubUrl
    ? '<a href="' + esc(githubUrl) + '" target="_blank" rel="noopener">' + esc(githubUrl) + '</a>'
    : esc((run.github && run.github.status) || "Not linked");
  const verification = run.verification || {};
  const verificationStatus = verification.status || "PENDING";
  const verificationKind = verificationStatus === "PASS" ? "" : (verificationStatus === "FAIL" ? "bad" : "muted");
  const faultVerification = run.fault_verification || {};
  const faultVerificationStatus = faultVerification.status || "NOT VERIFIED";
  const faultVerificationKind = faultVerificationStatus === "PASS" ? "" : "bad";
  const evidenceFile = run.evidence_file || "runtime-data/incidentlab/runs/<run_id>.json";

  const timeline = Array.isArray(run.timeline) ? run.timeline : [];
  const timelineHtml = timeline.length ? timeline.map(function(item) {
    const health = item.health || {};
    const metrics = item.metrics || {};
    const workload = item.workload || {};
    const healthText = health.healthy === true ? "HEALTHY" : (health.status || (health.healthy === false ? "UNHEALTHY" : "—"));
    const httpText = health.http_status == null ? "—" : ("HTTP " + health.http_status);
    const metricsText = [
      metrics.error_rate == null ? null : ("error=" + metrics.error_rate),
      metrics.latency_ms == null ? null : ("latency=" + metrics.latency_ms + "ms"),
      metrics.cpu_percent == null ? null : ("cpu=" + metrics.cpu_percent + "%"),
      metrics.memory_percent == null ? null : ("memory=" + metrics.memory_percent + "%")
    ].filter(Boolean).join(" · ");
    const workloadText = workload.http_status == null ? "" : (" · workload HTTP " + workload.http_status + " / " + (workload.elapsed_ms == null ? "—" : workload.elapsed_ms + "ms"));
    const eventKind = health.healthy === false ? "active" : ((item.event || "").indexOf("recover") >= 0 ? "done" : "");
    return '<div class="timeline-item">' +
      '<i class="timeline-bullet ' + eventKind + '"></i>' +
      '<div><strong>' + esc(item.event || "snapshot") + '</strong>' +
      '<p>' + esc(healthText + " · " + httpText + workloadText + (metricsText ? " · " + metricsText : "")) + '</p></div>' +
      '<time>' + esc(formatDate(item.timestamp)) + '</time>' +
    '</div>';
  }).join("") : '<div class="empty-state compact">No snapshots recorded.</div>';

  const recoveryEvents = Array.isArray(run.recovery_events) ? run.recovery_events : [];
  const recoveryText = recoveryEvents.length
    ? recoveryEvents.map(function(item) { return (item.action || "recovery") + " · " + (item.request_id || "—"); }).join("<br>")
    : "No recovery action recorded yet.";

  const activeAction = isActiveRun(run)
    ? '<div style="margin:14px 0"><button class="btn btn-primary" onclick="recoverRun(\'' + esc(run.service || "") + '\',\'' + esc(run.run_id || "") + '\')">Manual fallback: diagnose & patch</button></div>'
    : "";

  document.getElementById("modalTitle").textContent = run.run_id || "Run details";
  document.getElementById("modalBody").innerHTML =
    '<div class="detail-grid">' +
      '<div class="detail-cell"><span>Scenario</span><b>' + esc(run.scenario_id || "—") + '</b></div>' +
      '<div class="detail-cell"><span>Service</span><b>' + esc(run.service || "—") + '</b></div>' +
      '<div class="detail-cell"><span>Fault</span><b>' + esc(run.fault || "—") + '</b></div>' +
      '<div class="detail-cell"><span>State</span><b>' + esc(runState(run)) + '</b></div>' +
      '<div class="detail-cell"><span>Fault effect proof</span>' + badge(faultVerificationStatus, faultVerificationKind) + '</div>' +
      '<div class="detail-cell"><span>Recovery verification</span>' + badge(verificationStatus, verificationKind) + '</div>' +
      '<div class="detail-cell"><span>Evidence file</span><b class="mono">' + esc(evidenceFile) + '</b></div>' +
      '<div class="detail-cell"><span>GitHub</span>' + githubText + '</div>' +
      '<div class="detail-cell"><span>Recovery action</span><b>' + recoveryText + '</b></div>' +
    '</div>' +
    activeAction +
    '<div class="panel-kicker" style="margin-top:16px">EVIDENCE TIMELINE</div>' +
    '<div class="timeline">' + timelineHtml + '</div>' +
    '<div class="panel-kicker" style="margin-top:18px">RAW EVIDENCE</div>' +
    '<div class="json-block">' + esc(JSON.stringify(run, null, 2)) + '</div>';
  document.getElementById("modalBackdrop").classList.add("show");
}

async function recoverRun(service, runId) {
  if (!service || !runId) return;
  try {
    const pair = await Promise.all([
      api("/api/services/" + encodeURIComponent(service) + "/state"),
      api("/api/services/" + encodeURIComponent(service) + "/baseline")
    ]);
    const live = (pair[0] && pair[0].state) || {};
    const baseline = (pair[1] && pair[1].baseline) || {};
    const patch = {};
    Object.keys(baseline).forEach(function(key) {
      if (JSON.stringify(live[key]) !== JSON.stringify(baseline[key])) patch[key] = baseline[key];
    });
    if (!Object.keys(patch).length) {
      toast("No persisted state difference to patch.", "success");
      await refreshAll(false);
      return;
    }
    const result = await api("/api/recovery/" + encodeURIComponent(service), {
      method: "POST",
      body: JSON.stringify({
        action: "diagnose_and_patch",
        request_id: "web-" + runId + "-" + Date.now(),
        patch: patch
      })
    });
    const status = result.verification && result.verification.status ? result.verification.status : result.state;
    toast("Patch " + JSON.stringify(patch) + " · verification: " + status, status === "PASS" ? "success" : "error");
    document.getElementById("modalBackdrop").classList.remove("show");
    await refreshAll(false);
  } catch (error) {
    toast("Recovery failed: " + error.message, "error");
  }
}

function showRunDetail() {}

async function serviceDetail(name) {
  try {
    const results = await Promise.all([
      api("/api/services/" + encodeURIComponent(name) + "/health"),
      api("/api/services/" + encodeURIComponent(name) + "/metrics"),
      api("/api/services/" + encodeURIComponent(name) + "/probe"),
      api("/api/services/" + encodeURIComponent(name) + "/state")
    ]);
    const detail = Object.assign({}, results[0] || {}, results[1] || {}, {workload_probe: results[2] || {}, persisted_state: results[3] || {}});
    document.getElementById("modalTitle").textContent = name + " live runtime";
    document.getElementById("modalBody").innerHTML =
      '<div class="detail-grid">' +
        '<div class="detail-cell"><span>Health</span><b>' + esc(detail.healthy ? "HEALTHY" : (detail.status || "UNHEALTHY")) + '</b></div>' +
        '<div class="detail-cell"><span>Version</span><b>' + esc(detail.version || "—") + '</b></div>' +
        '<div class="detail-cell"><span>Latency</span><b>' + esc(detail.latency_ms == null ? "—" : detail.latency_ms + " ms") + '</b></div>' +
        '<div class="detail-cell"><span>Error rate</span><b>' + esc(detail.error_rate == null ? "—" : Math.round(Number(detail.error_rate) * 1000) / 10 + "%") + '</b></div>' +
        '<div class="detail-cell"><span>Live workload</span><b>' + esc(detail.workload_probe && detail.workload_probe.http_status != null ? ("HTTP " + detail.workload_probe.http_status + " · " + detail.workload_probe.elapsed_ms + " ms") : "unreachable") + '</b></div>' +
      '</div>' +
      '<div class="json-block">' + esc(JSON.stringify(detail, null, 2)) + '</div>';
    document.getElementById("modalBackdrop").classList.add("show");
  } catch (error) {
    toast("Metrics unavailable for " + name + ": " + error.message, "error");
  }
}

function closeModal(event) {
  if (event && event.target !== document.getElementById("modalBackdrop")) return;
  document.getElementById("modalBackdrop").classList.remove("show");
}

function renderGithub() {
  const text = document.getElementById("githubIntegrationText");
  const repo = document.getElementById("githubRepoText");
  const badgeEl = document.getElementById("githubIntegrationBadge");
  const ready = document.getElementById("readyGithub");

  if (!state.github) {
    text.textContent = "Integration status unavailable.";
    repo.textContent = "—";
    badgeEl.className = "status-badge muted";
    badgeEl.textContent = "UNKNOWN";
    ready.textContent = "Unknown";
    return;
  }

  repo.textContent = state.github.repo || "—";
  if (state.github.enabled) {
    text.textContent = "Automatic Issue creation is configured for incident runs.";
    badgeEl.className = "status-badge";
    badgeEl.textContent = "READY";
    ready.textContent = "Ready · " + (state.github.repo || "configured");
  } else {
    text.textContent = "Repository known, but no GitHub token is configured in IncidentLab.";
    badgeEl.className = "status-badge warn";
    badgeEl.textContent = "NOT CONFIGURED";
    ready.textContent = "Not configured";
  }
}

function renderOpsswarm() {
  const text = document.getElementById("opsswarmIntegrationText");
  const url = document.getElementById("opsswarmUrlText");
  const badgeEl = document.getElementById("opsswarmIntegrationBadge");
  const ready = document.getElementById("readyOpsswarm");
  if (!text || !url || !badgeEl || !ready) return;
  if (state.opsswarm && state.opsswarm.enabled) {
    text.textContent = "Orchestration runtime is online; verified faults are handed to OpsSwarm for OpenClaw processing.";
    url.textContent = state.opsswarm.url || "configured";
    badgeEl.className = "status-badge";
    badgeEl.textContent = "ONLINE";
    ready.textContent = "Online";
  } else {
    text.textContent = "OpsSwarm runtime is offline. Faults remain real, but Issue creation falls back to direct GitHub mode.";
    url.textContent = (state.opsswarm && state.opsswarm.url) || "not reachable";
    badgeEl.className = "status-badge warn";
    badgeEl.textContent = "OFFLINE";
    ready.textContent = "Offline · fallback only";
  }
}

function renderReadiness() {
  const readyApi = document.getElementById("readyApi");
  const badgeEl = document.getElementById("readyBadge");
  readyApi.textContent = state.apiOk ? "Online" : "Offline";
  if (state.apiOk && state.scenarios.length && state.services.length && state.opsswarm && state.opsswarm.enabled) {
    badgeEl.className = "status-badge";
    badgeEl.textContent = "READY";
  } else {
    badgeEl.className = "status-badge bad";
    badgeEl.textContent = "NOT READY";
  }
}

async function injectSelected() {
  const s = selectedScenario();
  if (!s) {
    toast("Select a scenario first.", "error");
    return;
  }
  const duration = Number(document.getElementById("durationInput").value) || 30;
  const autoReset = !!document.getElementById("autoResetInput").checked;
  const button = document.getElementById("injectButton");
  button.disabled = true;
  button.textContent = "Injecting…";

  try {
    const result = await api("/api/faults/inject", {
      method: "POST",
      body: JSON.stringify({
        scenario_id: s.id,
        service: s.service,
        fault: s.fault,
        duration_seconds: duration,
        auto_reset: autoReset,
        metadata: {source: "incidentlab-web-demo"}
      })
    });

    const proof = result.fault_verification || {};
    let message = "REAL FAULT VERIFIED · " + result.run_id;
    if (proof.mode === "monitoring_only") message = "MONITORING FAULT VERIFIED · " + result.run_id;
    message += result.auto_reset ? " · timed auto-reset enabled" : " · persists until recovery";
    if (proof.checks && proof.checks.persisted_artifact_mutated) message += " · persisted Docker artifact changed";
    if (result.opsswarm && result.opsswarm.enabled) message += " · handed to OpsSwarm/OpenClaw";
    else message += " · OpsSwarm offline, GitHub fallback";
    if (result.github && result.github.issue_number) message += " · GitHub Issue #" + result.github.issue_number;
    toast(message, "success");
    await refreshAll(false);
    showView("runs");
  } catch (error) {
    toast("Injection failed: " + error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "⚡ Inject persistent real fault";
  }
}

async function resetAll() {
  if (!window.confirm("Reset every simulated service to its clean baseline?")) return;
  try {
    await api("/api/reset", {method: "POST", body: "{}"});
    toast("Lab reset to clean state.", "success");
    await refreshAll(false);
  } catch (error) {
    toast("Reset failed: " + error.message, "error");
  }
}

async function loadServiceMetrics(services) {
  const merged = await Promise.all(services.map(async function(service) {
    try {
      const metrics = await api("/api/services/" + encodeURIComponent(service.service) + "/metrics");
      return Object.assign({}, service, metrics || {});
    } catch (_) {
      return service;
    }
  }));
  return merged;
}

async function refreshAll(manual) {
  const healthPromise = api("/api/health");
  const scenarioPromise = api("/api/scenarios");
  const servicePromise = api("/api/services");
  const runPromise = api("/api/evidence");
  const githubPromise = api("/api/integrations/github");
  const opsswarmPromise = api("/api/integrations/opsswarm");

  const results = await Promise.allSettled([healthPromise, scenarioPromise, servicePromise, runPromise, githubPromise, opsswarmPromise]);

  state.apiOk = results[0].status === "fulfilled" && !!results[0].value.ok;
  if (results[1].status === "fulfilled") state.scenarios = Array.isArray(results[1].value) ? results[1].value : [];
  if (results[2].status === "fulfilled") {
    const base = Array.isArray(results[2].value) ? results[2].value : [];
    state.services = await loadServiceMetrics(base);
  }
  if (results[3].status === "fulfilled") state.runs = Array.isArray(results[3].value) ? results[3].value : [];
  if (results[4].status === "fulfilled") state.github = results[4].value;
  if (results[5].status === "fulfilled") state.opsswarm = results[5].value;

  renderHeaderState();
  renderMetrics();
  renderServiceOverview();
  renderServiceCards();
  renderLatestRuns();
  buildScenarioFilters();
  renderScenarios();
  populateScenarioSelect();
  renderRuns();
  renderGithub();
  renderOpsswarm();
  renderReadiness();

  state.lastRefresh = new Date();
  document.getElementById("lastUpdated").textContent = "Updated " + state.lastRefresh.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"});

  if (manual) {
    if (state.apiOk) toast("Live data refreshed.", "success");
    else toast("IncidentLab API is offline.", "error");
  }
}

function setupEvents() {
  document.querySelectorAll(".nav-item").forEach(function(button) {
    button.addEventListener("click", function() { showView(button.dataset.view); });
  });

  document.getElementById("scenarioSearch").addEventListener("input", renderScenarios);
  document.getElementById("runSearch").addEventListener("input", renderRuns);
  document.getElementById("scenarioSelect").addEventListener("change", updateFaultInfo);

  const duration = document.getElementById("durationInput");
  const autoReset = document.getElementById("autoResetInput");
  function syncRecoveryMode() {
    const enabled = !!autoReset.checked;
    duration.disabled = !enabled;
    document.getElementById("durationLabel").textContent = duration.value + "s";
    document.getElementById("readyRecovery").textContent = enabled ? ("Auto-reset after " + duration.value + " seconds") : "Persistent until recovery";
  }
  duration.addEventListener("input", syncRecoveryMode);
  autoReset.addEventListener("change", syncRecoveryMode);
  syncRecoveryMode();

  document.addEventListener("keydown", function(event) {
    if (event.key === "Escape") closeModal();
  });
}

setupEvents();
refreshAll(false);
window.setInterval(function() { refreshAll(false); }, 5000);
