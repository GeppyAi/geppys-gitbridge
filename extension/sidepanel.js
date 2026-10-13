// Geppy's GitBridge - Chrome Extension Side Panel Controller
const SERVER_URL = "http://127.0.0.1:8000";

let currentMode = "brainstorm";
let apps = [];
let contextiles = [];
let activeApp = null;
let activeFilePath = null;
let fileOriginalContent = "";
let isUnsaved = false;
let backlogTasks = [];
let chatHistory = [];
let proactiveSuggestions = [];
let activeTabId = null;

// DOM Elements
const connectionStatus = document.getElementById("connection-status");
const connectionText = document.getElementById("connection-text");
const appSelect = document.getElementById("app-select");
const appLiveBadge = document.getElementById("app-live-badge");
const btnLaunchApp = document.getElementById("btn-launch-app");
const btnDetectTab = document.getElementById("btn-detect-tab");

const btnModeBrainstorm = document.getElementById("btn-mode-brainstorm");
const btnModeDesigner = document.getElementById("btn-mode-designer");
const viewBrainstorm = document.getElementById("view-brainstorm");
const viewDesigner = document.getElementById("view-designer");

// Brainstorm Elements
const chatHistoryEl = document.getElementById("chat-history");
const brainstormInput = document.getElementById("brainstorm-input");
const btnSendBrainstorm = document.getElementById("btn-send-brainstorm");
const backlogCount = document.getElementById("backlog-count");
const backlogList = document.getElementById("backlog-list");
const btnAddCustomTask = document.getElementById("btn-add-custom-task");
const btnToggleBacklog = document.getElementById("btn-toggle-backlog");
const backlogDrawer = document.getElementById("backlog-drawer");

// Designer Elements
const suggestionsCarousel = document.getElementById("suggestions-carousel");
const btnRefreshSuggestions = document.getElementById("btn-refresh-suggestions");
const designerTaskPicker = document.getElementById("designer-task-picker");
const btnApplyBacklogTask = document.getElementById("btn-apply-backlog-task");
const fileSelect = document.getElementById("file-select");
const codeEditor = document.getElementById("code-editor");
const btnSaveFile = document.getElementById("btn-save-file");
const btnReloadTab = document.getElementById("btn-reload-tab");
const btnRevertFile = document.getElementById("btn-revert-file");
const unsavedIndicator = document.getElementById("unsaved-indicator");
const designerAiInput = document.getElementById("designer-ai-input");
const btnApplyDesignerAi = document.getElementById("btn-apply-designer-ai");

// Git & Change Tracking Elements
let currentGitStatus = null;
let sessionChangesLog = [];

const btnToggleCommitDrawer = document.getElementById("btn-toggle-commit-drawer");
const btnHeaderCommit = document.getElementById("btn-header-commit");
const btnDesignerCommit = document.getElementById("btn-designer-commit");
const gitBranchText = document.getElementById("git-branch-text");
const gitStatusBadge = document.getElementById("git-status-badge");
const gitStatusLabel = document.getElementById("git-status-label");
const designerGitCount = document.getElementById("designer-git-count");

const commitModal = document.getElementById("commit-modal");
const btnCloseCommitModal = document.getElementById("btn-close-commit-modal");
const modalPcStatus = document.getElementById("modal-pc-status");
const modalGhStatus = document.getElementById("modal-gh-status");
const modalChangedCount = document.getElementById("modal-changed-count");
const modalSessionLogCount = document.getElementById("modal-session-log-count");
const tabChangedFiles = document.getElementById("tab-changed-files");
const tabSessionLog = document.getElementById("tab-session-log");
const panelChangedFiles = document.getElementById("panel-changed-files");
const panelSessionLog = document.getElementById("panel-session-log");
const modalFilesList = document.getElementById("modal-files-list");
const modalSessionTimeline = document.getElementById("modal-session-timeline");
const commitMsgInput = document.getElementById("commit-msg-input");
const btnGenerateAiCommitMsg = document.getElementById("btn-generate-ai-commit-msg");
const commitFeedback = document.getElementById("commit-feedback");
const btnCommitPcOnly = document.getElementById("btn-commit-pc-only");
const btnDoCommitAndPush = document.getElementById("btn-do-commit-and-push");

// --- Initialization ---
document.addEventListener("DOMContentLoaded", async () => {
  setupEventListeners();
  await checkServerConnection();
  await loadApps();
  await loadContextiles();
  await detectActiveTabApp();
});

// Listen for tab change events from background.js
if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "TAB_CHANGED") {
      activeTabId = msg.tabId;
      detectAppFromUrl(msg.url);
    }
  });
}

function setupEventListeners() {
  btnModeBrainstorm.addEventListener("click", () => switchMode("brainstorm"));
  btnModeDesigner.addEventListener("click", () => switchMode("designer"));

  appSelect.addEventListener("change", (e) => onAppSelected(e.target.value));
  btnDetectTab.addEventListener("click", () => detectActiveTabApp());
  btnLaunchApp.addEventListener("click", () => launchSelectedApp());

  // Brainstorm
  btnSendBrainstorm.addEventListener("click", () => submitBrainstorm());
  brainstormInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitBrainstorm();
    }
  });

  document.querySelectorAll(".pill-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prompt = btn.dataset.prompt;
      if (prompt) submitBrainstorm(prompt);
    });
  });

  btnAddCustomTask.addEventListener("click", () => promptAddCustomTask());
  btnToggleBacklog.addEventListener("click", () => toggleBacklogDrawer());

  // Designer
  fileSelect.addEventListener("change", (e) => openFile(e.target.value));
  btnSaveFile.addEventListener("click", () => saveCurrentFile());
  btnReloadTab.addEventListener("click", () => reloadActiveTab());
  btnRevertFile.addEventListener("click", () => revertCurrentFile());
  btnRefreshSuggestions.addEventListener("click", () => refreshProactiveSuggestions());
  btnApplyDesignerAi.addEventListener("click", () => applyDesignerAiEdit());
  designerAiInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      applyDesignerAiEdit();
    }
  });

  btnApplyBacklogTask.addEventListener("click", () => applySelectedBacklogTask());

  codeEditor.addEventListener("input", () => {
    if (!isUnsaved) {
      isUnsaved = true;
      unsavedIndicator.style.display = "inline-block";
    }
  });

  // Ctrl+S / Cmd+S in editor
  codeEditor.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      saveCurrentFile();
    }
    // Tab indent support
    if (e.key === "Tab") {
      e.preventDefault();
      const start = codeEditor.selectionStart;
      const end = codeEditor.selectionEnd;
      codeEditor.value = codeEditor.value.substring(0, start) + "  " + codeEditor.value.substring(end);
      codeEditor.selectionStart = codeEditor.selectionEnd = start + 2;
    }
  });

  // Git & Commit Modal Listeners
  if (btnToggleCommitDrawer) btnToggleCommitDrawer.addEventListener("click", () => openCommitModal());
  if (btnHeaderCommit) btnHeaderCommit.addEventListener("click", () => openCommitModal());
  if (btnDesignerCommit) btnDesignerCommit.addEventListener("click", () => openCommitModal());
  if (btnCloseCommitModal) btnCloseCommitModal.addEventListener("click", () => closeCommitModal());
  if (tabChangedFiles) tabChangedFiles.addEventListener("click", () => switchCommitTab("files"));
  if (tabSessionLog) tabSessionLog.addEventListener("click", () => switchCommitTab("log"));
  if (btnGenerateAiCommitMsg) btnGenerateAiCommitMsg.addEventListener("click", () => generateAiCommitMessage());
  if (btnCommitPcOnly) btnCommitPcOnly.addEventListener("click", () => commitAndPushApp(false));
  if (btnDoCommitAndPush) btnDoCommitAndPush.addEventListener("click", () => commitAndPushApp(true));

  if (commitModal) {
    commitModal.addEventListener("click", (e) => {
      if (e.target === commitModal) closeCommitModal();
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" || e.keyCode === 27) {
      closeCommitModal();
    }
  });
}

// --- Mode Switcher ---
function switchMode(mode) {
  currentMode = mode;
  if (mode === "brainstorm") {
    btnModeBrainstorm.classList.add("active");
    btnModeDesigner.classList.remove("active");
    viewBrainstorm.classList.remove("hidden");
    viewDesigner.classList.add("hidden");
  } else {
    btnModeDesigner.classList.add("active");
    btnModeBrainstorm.classList.remove("active");
    viewDesigner.classList.remove("hidden");
    viewBrainstorm.classList.add("hidden");

    // Ensure file tree is loaded for current app
    if (activeApp && (!fileSelect.options || fileSelect.options.length <= 1)) {
      loadFileTree(activeApp.slug);
    }
    // Sync backlog picker dropdown in designer
    updateDesignerTaskPicker();
  }
}

// --- Server Connection & App Catalog ---
async function checkServerConnection() {
  try {
    const res = await fetch(`${SERVER_URL}/api/settings`, { method: "GET" });
    if (res.ok) {
      connectionStatus.className = "status-indicator";
      connectionText.innerText = "Geppy's Galactic Online";
    } else {
      setOfflineState();
    }
  } catch (e) {
    setOfflineState();
  }
}

function setOfflineState() {
  connectionStatus.className = "status-indicator offline";
  connectionText.innerText = "Geppy's Galactic Offline";
}

// --- SOT Contextiles Engine ---
async function loadContextiles() {
  try {
    const res = await fetch(`${SERVER_URL}/api/sot/contextiles`);
    if (res.ok) {
      contextiles = await res.json();
      renderSOTChips();
    }
  } catch (e) {
    console.warn("Could not load SOT contextiles:", e);
  }
}

function renderSOTChips() {
  const container = document.getElementById("sot-contextile-chips");
  if (!container) return;

  if (!contextiles || contextiles.length === 0) {
    container.innerHTML = '<span style="color: #64748b; font-size: 10.5px;">No contextiles found</span>';
    return;
  }

  const archIcons = {
    character: "👤",
    icon_set: "🎨",
    ui_component: "🧩",
    brand_asset: "🏷️",
    environment: "🌌",
    general: "✨"
  };

  container.innerHTML = "";
  contextiles.forEach((c) => {
    const chip = document.createElement("button");
    chip.className = "sot-chip";
    const icon = archIcons[c.archetype] || "✨";
    const imgCount = (c.gallery_images || []).length;
    const countTag = imgCount > 1 ? ` (${imgCount} imgs)` : "";
    chip.title = `[${c.archetype || "SOT"}] ${c.title || c.name}${countTag}: ${c.description || "Click to insert @" + c.name + " into prompt"}`;
    chip.innerHTML = `<span style="font-size: 10px; margin-right: 2px;">${icon}</span>@${escapeHtml(c.name)}`;
    chip.addEventListener("click", () => {
      insertContextileMention(`@${c.name}`);
    });
    container.appendChild(chip);
  });
}

function insertContextileMention(mentionHandle) {
  if (currentMode === "brainstorm") {
    const val = brainstormInput.value;
    brainstormInput.value = val ? `${val.trimEnd()} ${mentionHandle} ` : `${mentionHandle} `;
    brainstormInput.focus();
  } else {
    const val = designerAiInput.value;
    designerAiInput.value = val ? `${val.trimEnd()} ${mentionHandle} ` : `${mentionHandle} `;
    designerAiInput.focus();
  }
}

async function loadApps() {
  try {
    const res = await fetch(`${SERVER_URL}/api/apps?include_hidden=true`);
    if (!res.ok) return;
    apps = await res.json();
    populateAppDropdown();
  } catch (e) {
    console.error("Failed to load apps:", e);
  }
}

function populateAppDropdown() {
  appSelect.innerHTML = "";
  if (!apps || apps.length === 0) {
    appSelect.innerHTML = '<option value="">No apps found</option>';
    return;
  }

  const optDefault = document.createElement("option");
  optDefault.value = "";
  optDefault.innerText = "-- Select Application --";
  appSelect.appendChild(optDefault);

  apps.forEach((a) => {
    const opt = document.createElement("option");
    opt.value = a.slug;
    opt.innerText = `${a.name}${a.is_live ? " 🟢 (Live)" : ""}${a.is_hidden ? " 👁️ (Hidden)" : ""}`;
    appSelect.appendChild(opt);
  });

  if (activeApp) {
    appSelect.value = activeApp.slug;
  }
}

// --- Active Tab App Detection ---
async function detectActiveTabApp() {
  if (typeof chrome === "undefined" || !chrome.tabs) return;

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.url) {
      activeTabId = tab.id;
      await detectAppFromUrl(tab.url);
    }
  } catch (e) {
    console.warn("Could not query active tab:", e);
  }
}

async function detectAppFromUrl(url) {
  if (!url) return;
  try {
    const res = await fetch(`${SERVER_URL}/api/extension/detect-app?url=${encodeURIComponent(url)}`);
    if (res.ok) {
      const data = await res.json();
      if (data.matched && data.app) {
        setActiveApp(data.app);
        return;
      }
    }
  } catch (e) {
    console.warn("App detection request failed:", e);
  }

  // Fallback: If no app matched and none is selected, select the first available app
  if (!activeApp && apps.length > 0) {
    setActiveApp(apps[0]);
  }
}

function onAppSelected(slug) {
  if (!slug) return;
  const app = apps.find((a) => a.slug === slug);
  if (app) setActiveApp(app);
}

async function setActiveApp(app) {
  activeApp = app;
  appSelect.value = app.slug;

  if (app.is_live) {
    appLiveBadge.style.display = "inline-block";
    appLiveBadge.innerText = app.live_url ? `Live (${new URL(app.live_url).port || "80"})` : "Live";
  } else {
    appLiveBadge.style.display = "none";
  }

  // Load backlog
  await loadBacklog(app.slug);

  // Load file tree for designer
  await loadFileTree(app.slug);

  // Load Git status & Session Changelog
  loadSessionLog(app.slug);
  await refreshGitStatus();
}

async function launchSelectedApp() {
  if (!activeApp) {
    alert("Please select an application to launch from the dropdown.");
    return;
  }

  const origHtml = btnLaunchApp.innerHTML;
  btnLaunchApp.disabled = true;
  btnLaunchApp.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> <span>Launching...</span>';

  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/launch`, {
      method: "POST"
    });
    const data = await res.json();

    if (res.ok && data.launched && data.target) {
      // Open in browser tab
      if (typeof chrome !== "undefined" && chrome.tabs) {
        chrome.tabs.create({ url: data.target }, (newTab) => {
          if (newTab) activeTabId = newTab.id;
        });
      } else {
        window.open(data.target, "_blank");
      }

      activeApp.is_live = true;
      activeApp.live_url = data.target;
      appLiveBadge.style.display = "inline-block";
      appLiveBadge.innerText = data.port ? `Live (${data.port})` : "Live";

      btnLaunchApp.innerHTML = '<i class="fa-solid fa-check text-emerald-300"></i> <span>Opened!</span>';
      setTimeout(() => {
        btnLaunchApp.disabled = false;
        btnLaunchApp.innerHTML = '<i class="fa-solid fa-rocket"></i> <span>Launch</span>';
      }, 1500);

      // Refresh app catalog dropdown
      await loadApps();
    } else if (data.target) {
      // Server already running or available, open or focus tab
      if (typeof chrome !== "undefined" && chrome.tabs) {
        chrome.tabs.create({ url: data.target }, (newTab) => {
          if (newTab) activeTabId = newTab.id;
        });
      } else {
        window.open(data.target, "_blank");
      }

      btnLaunchApp.innerHTML = '<i class="fa-solid fa-check text-emerald-300"></i> <span>Opened!</span>';
      setTimeout(() => {
        btnLaunchApp.disabled = false;
        btnLaunchApp.innerHTML = '<i class="fa-solid fa-rocket"></i> <span>Launch</span>';
      }, 1500);
    } else {
      alert(`Launch status: ${data.message || data.detail || "Could not launch application"}`);
      btnLaunchApp.disabled = false;
      btnLaunchApp.innerHTML = origHtml;
    }
  } catch (e) {
    alert("Launch error: " + e);
    btnLaunchApp.disabled = false;
    btnLaunchApp.innerHTML = origHtml;
  }
}

// --- Brainstorm Mode Logic ---
async function submitBrainstorm(overridePrompt = null) {
  const prompt = overridePrompt || brainstormInput.value.trim();
  if (!prompt) return;

  if (!overridePrompt) brainstormInput.value = "";

  appendChatBubble("user", prompt);
  chatHistory.push({ sender: "user", text: prompt });
  logSessionChange("brainstorm", `Chat with Captain Geppy: "${prompt.substring(0, 45)}${prompt.length > 45 ? "..." : ""}"`);

  const loadingBubble = appendChatBubble("ai", '<i class="fa-solid fa-spinner animate-spin"></i> Captain Geppy is navigating the Galactic stars...');

  btnSendBrainstorm.disabled = true;

  try {
    const res = await fetch(`${SERVER_URL}/api/extension/brainstorm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: activeApp ? activeApp.slug : "",
        message: prompt,
        history: chatHistory,
        file_path: activeFilePath
      })
    });

    const data = await res.json();
    loadingBubble.remove();

    if (res.ok) {
      appendChatBubble("ai", formatMarkdown(data.text));
      chatHistory.push({ sender: "ai", text: data.text });
      refreshGitStatus();

      // Automatically incorporate newly extracted ideas into backlog!
      if (data.extracted_tasks && data.extracted_tasks.length > 0) {
        logSessionChange("tasks", `Extracted ${data.extracted_tasks.length} new ideas from Captain Geppy chat`);
        data.extracted_tasks.forEach((t) => {
          backlogTasks.push({
            id: `task-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
            title: t.title,
            category: t.category || "feature",
            description: t.description || "",
            suggested_prompt: t.suggested_prompt || t.title,
            completed: false
          });
        });
        await saveBacklogToServer();
        renderBacklog();
      }
    } else {
      appendChatBubble("ai", `Error: ${data.detail || "Failed to brainstorm"}`);
    }
  } catch (e) {
    loadingBubble.remove();
    appendChatBubble("ai", `Connection error: ${e}`);
  } finally {
    btnSendBrainstorm.disabled = false;
  }
}

function appendChatBubble(sender, htmlContent) {
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${sender}`;
  if (sender === "ai") {
    bubble.innerHTML = `
      <div class="captain-badge">
        <span class="captain-avatar">👨‍🚀</span>
        <div>
          <strong style="color: #818cf8;">Captain Geppy</strong>
          <span class="captain-sub">Galactic Commander</span>
        </div>
      </div>
      <div class="ai-body">${htmlContent}</div>
    `;
  } else {
    bubble.innerHTML = htmlContent;
  }
  chatHistoryEl.appendChild(bubble);
  chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
  return bubble;
}

// --- Ideas & Tasks Backlog System ---
async function loadBacklog(slug) {
  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${slug}/backlog`);
    if (res.ok) {
      const data = await res.json();
      backlogTasks = data.tasks || [];
      renderBacklog();
      updateDesignerTaskPicker();
    }
  } catch (e) {
    console.error("Failed to load backlog:", e);
  }
}

async function saveBacklogToServer() {
  if (!activeApp) return;
  try {
    await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/backlog`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tasks: backlogTasks })
    });
    updateDesignerTaskPicker();
  } catch (e) {
    console.error("Failed to save backlog:", e);
  }
}

function renderBacklog() {
  backlogCount.innerText = backlogTasks.length;
  backlogList.innerHTML = "";

  if (backlogTasks.length === 0) {
    backlogList.innerHTML = '<div style="color: #64748b; font-size: 11px; text-align: center; padding: 12px 0;">No brainstormed tasks yet. Chat with AI or click a prompt pill above!</div>';
    return;
  }

  backlogTasks.forEach((t, idx) => {
    const card = document.createElement("div");
    card.className = `task-card ${t.completed ? "completed" : ""}`;

    const catClass = ["design", "feature", "ux", "polish"].includes(t.category?.toLowerCase())
      ? t.category.toLowerCase()
      : "feature";

    card.innerHTML = `
      <div class="task-card-top">
        <span class="task-tag ${catClass}">${escapeHtml(t.category || "Task")}</span>
        <span class="task-title">${escapeHtml(t.title)}</span>
        <button class="btn-icon-subtle btn-delete-task" title="Delete task"><i class="fa-solid fa-trash-can"></i></button>
      </div>
      <div class="task-desc">${escapeHtml(t.description || "")}</div>
      <div class="task-actions">
        <label style="font-size: 10px; color: #94a3b8; display: flex; align-items: center; gap: 4px; cursor: pointer;">
          <input type="checkbox" class="chk-task-done" ${t.completed ? "checked" : ""}> Done
        </label>
        <button class="btn-push-designer" title="Open in Designer and apply this edit">
          <i class="fa-solid fa-wand-magic-sparkles"></i> Push to Designer
        </button>
      </div>
    `;

    // Done Checkbox
    card.querySelector(".chk-task-done").addEventListener("change", (e) => {
      t.completed = e.target.checked;
      card.classList.toggle("completed", t.completed);
      saveBacklogToServer();
    });

    // Delete Button
    card.querySelector(".btn-delete-task").addEventListener("click", () => {
      backlogTasks.splice(idx, 1);
      renderBacklog();
      saveBacklogToServer();
    });

    // Push to Designer Button
    card.querySelector(".btn-push-designer").addEventListener("click", () => {
      pushTaskToDesigner(t);
    });

    backlogList.appendChild(card);
  });
}

function promptAddCustomTask() {
  const title = prompt("Enter new Task / Feature Idea for backlog:");
  if (!title || !title.trim()) return;

  const desc = prompt("Optional short description or implementation hint:", "");

  backlogTasks.unshift({
    id: `task-${Date.now()}`,
    title: title.trim(),
    category: "feature",
    description: (desc || "").trim(),
    suggested_prompt: title.trim(),
    completed: false
  });

  renderBacklog();
  saveBacklogToServer();
}

function toggleBacklogDrawer() {
  if (backlogDrawer.style.maxHeight === "38px") {
    backlogDrawer.style.maxHeight = "38%";
    btnToggleBacklog.innerHTML = '<i class="fa-solid fa-chevron-up"></i>';
  } else {
    backlogDrawer.style.maxHeight = "38px";
    btnToggleBacklog.innerHTML = '<i class="fa-solid fa-chevron-down"></i>';
  }
}

function pushTaskToDesigner(task) {
  switchMode("designer");
  designerAiInput.value = task.suggested_prompt || task.title;
  designerAiInput.focus();

  // Highlight input briefly
  designerAiInput.style.borderColor = "#38bdf8";
  setTimeout(() => {
    designerAiInput.style.borderColor = "";
  }, 1000);
}

function updateDesignerTaskPicker() {
  designerTaskPicker.innerHTML = '<option value="">Select idea to apply...</option>';
  backlogTasks.forEach((t) => {
    if (!t.completed) {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.innerText = t.title;
      designerTaskPicker.appendChild(opt);
    }
  });
}

function applySelectedBacklogTask() {
  const taskId = designerTaskPicker.value;
  if (!taskId) return;
  const task = backlogTasks.find((t) => t.id === taskId);
  if (!task) return;

  designerAiInput.value = task.suggested_prompt || task.title;
  applyDesignerAiEdit();
}

// --- Live Designer & Code Editor ---
async function loadFileTree(slug) {
  if (!slug) return;
  fileSelect.innerHTML = '<option value="">Loading files...</option>';

  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${slug}/files/tree`);
    if (!res.ok) return;

    const data = await res.json();
    const files = data.files || [];

    fileSelect.innerHTML = "";
    if (files.length === 0) {
      fileSelect.innerHTML = '<option value="">No editable files found</option>';
      return;
    }

    files.forEach((f) => {
      const opt = document.createElement("option");
      opt.value = f.path;
      opt.innerText = f.path;
      fileSelect.appendChild(opt);
    });

    // Auto-select preferred starter file (index.html, App.jsx, main.py)
    const preferred = files.find((f) =>
      /index\.html|app\.(jsx|tsx|vue|js)|main\.py/i.test(f.name)
    ) || files[0];

    if (preferred) {
      fileSelect.value = preferred.path;
      openFile(preferred.path);
    }
  } catch (e) {
    console.error("Failed to load file tree:", e);
  }
}

async function openFile(filePath) {
  if (!activeApp || !filePath) return;
  activeFilePath = filePath;

  try {
    const res = await fetch(
      `${SERVER_URL}/api/apps/${activeApp.slug}/files/content?file_path=${encodeURIComponent(filePath)}`
    );
    if (!res.ok) return;

    const data = await res.json();
    fileOriginalContent = data.content || "";
    codeEditor.value = fileOriginalContent;
    isUnsaved = false;
    unsavedIndicator.style.display = "none";

    // Proactively fetch AI suggestions for this file
    fetchProactiveSuggestions(activeApp.slug, filePath, fileOriginalContent);
  } catch (e) {
    console.error("Failed to read file:", e);
  }
}

async function fetchProactiveSuggestions(slug, filePath, content) {
  suggestionsCarousel.innerHTML = '<div style="color: #64748b; font-size: 11px; padding: 8px 0;"><i class="fa-solid fa-spinner animate-spin"></i> Analyzing component for design suggestions...</div>';

  try {
    const res = await fetch(`${SERVER_URL}/api/extension/proactive-suggestions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: slug,
        file_path: filePath,
        content: content
      })
    });

    if (!res.ok) throw new Error("Could not fetch suggestions");

    const data = await res.json();
    proactiveSuggestions = data.suggestions || [];
    renderProactiveSuggestions();
  } catch (e) {
    suggestionsCarousel.innerHTML = '<div style="color: #ef4444; font-size: 11px; padding: 8px 0;">Could not load AI suggestions.</div>';
  }
}

function refreshProactiveSuggestions() {
  if (!activeApp || !activeFilePath) return;
  fetchProactiveSuggestions(activeApp.slug, activeFilePath, codeEditor.value);
}

function renderProactiveSuggestions() {
  suggestionsCarousel.innerHTML = "";

  if (proactiveSuggestions.length === 0) {
    suggestionsCarousel.innerHTML = '<div style="color: #64748b; font-size: 11px; padding: 8px 0;">No suggestions available for this file.</div>';
    return;
  }

  proactiveSuggestions.forEach((sug) => {
    const card = document.createElement("div");
    card.className = "suggestion-card";

    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <span class="sug-title">${escapeHtml(sug.title)}</span>
        <span class="sug-badge">${escapeHtml(sug.preview_badge || sug.category || "Design")}</span>
      </div>
      <div class="sug-desc">${escapeHtml(sug.description)}</div>
      <button class="btn-apply-suggestion">
        <i class="fa-solid fa-bolt"></i> Apply Design
      </button>
    `;

    card.querySelector(".btn-apply-suggestion").addEventListener("click", () => {
      applySuggestionDirect(sug);
    });

    suggestionsCarousel.appendChild(card);
  });
}

async function applySuggestionDirect(sug) {
  if (!activeApp || !activeFilePath) return;

  const btn = event.currentTarget;
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Applying...';

  try {
    const res = await fetch(`${SERVER_URL}/api/extension/apply-design`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: activeApp.slug,
        file_path: activeFilePath,
        current_code: codeEditor.value,
        instruction: sug.prompt || sug.title
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      codeEditor.value = data.modified_code;
      isUnsaved = true;
      unsavedIndicator.style.display = "inline-block";
      logSessionChange("ai_suggestion", `Applied suggestion "${sug.title}" to ${activeFilePath}`, activeFilePath);
      alert(`✨ Suggestion Applied!\n"${sug.title}" has been merged into the editor.\nClick [Save] to write changes to your PC.`);
    } else {
      alert(`Failed to apply suggestion: ${data.explanation || "Unknown error"}`);
    }
  } catch (e) {
    alert("Error applying suggestion: " + e);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

async function applyDesignerAiEdit() {
  const instruction = designerAiInput.value.trim();
  if (!instruction || !activeApp || !activeFilePath) return;

  btnApplyDesignerAi.disabled = true;
  btnApplyDesignerAi.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Generating...';

  try {
    const res = await fetch(`${SERVER_URL}/api/extension/apply-design`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: activeApp.slug,
        file_path: activeFilePath,
        current_code: codeEditor.value,
        instruction: instruction
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      codeEditor.value = data.modified_code;
      isUnsaved = true;
      unsavedIndicator.style.display = "inline-block";
      designerAiInput.value = "";
      logSessionChange("ai_edit", `Applied AI edit to ${activeFilePath}: "${instruction}"`, activeFilePath);
      alert("✨ AI Edit applied to editor! Review code and click [Save] to persist.");
    } else {
      alert(`AI Edit error: ${data.explanation || "Could not generate code"}`);
    }
  } catch (e) {
    alert("Error applying AI edit: " + e);
  } finally {
    btnApplyDesignerAi.disabled = false;
    btnApplyDesignerAi.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> <span>Apply</span>';
  }
}

async function saveCurrentFile() {
  if (!activeApp || !activeFilePath) return;

  btnSaveFile.disabled = true;
  btnSaveFile.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Saving...';

  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/files/content`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_path: activeFilePath,
        content: codeEditor.value
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      isUnsaved = false;
      fileOriginalContent = codeEditor.value;
      unsavedIndicator.style.display = "none";
      btnSaveFile.innerHTML = '<i class="fa-solid fa-check"></i> Saved!';
      logSessionChange("manual_save", `Saved changes to ${activeFilePath}`, activeFilePath);
      await refreshGitStatus();

      setTimeout(() => {
        btnSaveFile.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> <span>Save</span>';
        btnSaveFile.disabled = false;
      }, 1200);

      // Auto reload the browser tab if app is live
      reloadActiveTab();
    } else {
      alert(`Save failed: ${data.message || data.detail || "Unknown error"}`);
      btnSaveFile.disabled = false;
    }
  } catch (e) {
    alert("Save error: " + e);
    btnSaveFile.disabled = false;
  }
}

function revertCurrentFile() {
  if (!isUnsaved || confirm("Revert all unsaved changes to this file?")) {
    codeEditor.value = fileOriginalContent;
    isUnsaved = false;
    unsavedIndicator.style.display = "none";
  }
}

function reloadActiveTab() {
  if (typeof chrome !== "undefined" && chrome.tabs) {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs && tabs[0]) {
        chrome.tabs.reload(tabs[0].id);
      }
    });
  }
}

// --- Utility Helpers ---
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatMarkdown(text) {
  if (!text) return "";
  let html = escapeHtml(text);
  // Code blocks
  html = html.replace(/```([a-z]*)\n([\s\S]*?)```/g, "<pre><code>$2</code></pre>");
  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  // Headers
  html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
  html = html.replace(/^## (.*$)/gim, "<h2>$1</h2>");
  html = html.replace(/^# (.*$)/gim, "<h1>$1</h1>");
  // Newlines
  html = html.replace(/\n\n/g, "</p><p>");
  html = html.replace(/\n/g, "<br>");
  return `<p>${html}</p>`;
}

// --- Session Change Tracking & Git Sync ---
function logSessionChange(actionType, summary, filePath = null) {
  const item = {
    time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    actionType,
    summary,
    filePath,
    timestamp: Date.now()
  };
  sessionChangesLog.unshift(item);
  if (sessionChangesLog.length > 60) sessionChangesLog.pop();

  if (activeApp) {
    try {
      localStorage.setItem(`galactic_changelog_${activeApp.slug}`, JSON.stringify(sessionChangesLog));
    } catch (e) {}
  }
}

function loadSessionLog(slug) {
  sessionChangesLog = [];
  try {
    const raw = localStorage.getItem(`galactic_changelog_${slug}`);
    if (raw) {
      sessionChangesLog = JSON.parse(raw);
    }
  } catch (e) {}
}

async function refreshGitStatus() {
  if (!activeApp) return;

  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/git-status`);
    if (!res.ok) return;

    currentGitStatus = await res.json();
    renderGitStatusBadge();
  } catch (e) {
    console.warn("Could not refresh git status:", e);
  }
}

function renderGitStatusBadge() {
  if (!currentGitStatus) return;

  if (gitBranchText) {
    gitBranchText.innerText = currentGitStatus.branch || "main";
  }

  const hasChanges = currentGitStatus.has_changes;
  const count = currentGitStatus.total_changes || 0;

  if (gitStatusBadge) {
    if (hasChanges) {
      gitStatusBadge.className = "git-badge has-changes";
      gitStatusBadge.innerHTML = `<i class="fa-solid fa-pen-to-square"></i> <span id="git-status-label">${count} ${count === 1 ? "change" : "changes"}</span>`;
    } else {
      gitStatusBadge.className = "git-badge clean";
      gitStatusBadge.innerHTML = `<i class="fa-solid fa-check"></i> <span id="git-status-label">Clean</span>`;
    }
  }

  if (designerGitCount) {
    designerGitCount.innerText = count;
  }
}

async function openCommitModal() {
  if (!activeApp) {
    alert("Please select an application first.");
    return;
  }

  await refreshGitStatus();

  // Populate Persistence Banner
  if (modalPcStatus) {
    if (currentGitStatus?.is_git_repo) {
      modalPcStatus.innerText = `Branch: ${currentGitStatus.branch || "main"} (${currentGitStatus.total_changes || 0} modified)`;
    } else {
      modalPcStatus.innerText = "New local repository ready to initialize";
    }
  }

  if (modalGhStatus) {
    if (currentGitStatus?.has_remote && currentGitStatus.remote_url) {
      modalGhStatus.innerText = currentGitStatus.remote_url.replace("https://github.com/", "");
    } else if (activeApp.github_url) {
      modalGhStatus.innerText = activeApp.github_url.replace("https://github.com/", "");
    } else {
      modalGhStatus.innerText = "Will create new GitHub repo on sync";
    }
  }

  // Populate Changed Files List
  renderModalFilesList();

  // Populate Session Log
  renderModalSessionLog();

  // Default Commit Message if blank
  if (commitMsgInput && !commitMsgInput.value.trim()) {
    if (currentGitStatus?.files && currentGitStatus.files.length > 0) {
      const topFiles = currentGitStatus.files.slice(0, 2).map((f) => f.path.split("/").pop());
      commitMsgInput.value = `feat: update ${topFiles.join(", ")} via Geppy's Galactic`;
    } else {
      commitMsgInput.value = `feat: update ${activeApp.name} via Geppy's Galactic`;
    }
  }

  if (commitFeedback) {
    commitFeedback.className = "commit-feedback hidden";
    commitFeedback.innerHTML = "";
  }

  switchCommitTab("files");
  if (commitModal) {
    commitModal.classList.remove("hidden");
    commitModal.style.display = "flex";
  }
}

function closeCommitModal() {
  if (commitModal) {
    commitModal.classList.add("hidden");
    commitModal.style.display = "none";
  }
}

// Export to window for inline onclick handlers
window.closeCommitModal = closeCommitModal;
window.openCommitModal = openCommitModal;

function switchCommitTab(tab) {
  if (tab === "files") {
    tabChangedFiles.classList.add("active");
    tabSessionLog.classList.remove("active");
    panelChangedFiles.classList.remove("hidden");
    panelSessionLog.classList.add("hidden");
  } else {
    tabSessionLog.classList.add("active");
    tabChangedFiles.classList.remove("active");
    panelSessionLog.classList.remove("hidden");
    panelChangedFiles.classList.add("hidden");
  }
}

function renderModalFilesList() {
  const files = currentGitStatus?.files || [];
  modalChangedCount.innerText = files.length;

  if (files.length === 0) {
    modalFilesList.innerHTML = '<div style="color: #64748b; font-size: 11px; text-align: center; padding: 14px 0;"><i class="fa-solid fa-circle-check text-emerald-400" style="margin-right: 4px;"></i> All files are committed and saved. Working tree clean!</div>';
    return;
  }

  modalFilesList.innerHTML = "";
  files.forEach((f) => {
    const row = document.createElement("div");
    row.className = "file-diff-item";
    row.title = `Click to open ${f.path} in Live Designer`;

    const codeClass = f.code === "M" ? "M" : (f.code === "A" ? "A" : (f.code === "D" ? "D" : "untracked"));

    row.innerHTML = `
      <div style="display: flex; align-items: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 80%;">
        <span class="file-badge-code ${codeClass}">${escapeHtml(f.code || "M")}</span>
        <span style="color: #f1f5f9; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(f.path)}</span>
      </div>
      <span style="color: #64748b; font-size: 10px; text-transform: uppercase;">${escapeHtml(f.status)}</span>
    `;

    row.addEventListener("click", () => {
      closeCommitModal();
      switchMode("designer");
      fileSelect.value = f.path;
      openFile(f.path);
    });

    modalFilesList.appendChild(row);
  });
}

function renderModalSessionLog() {
  modalSessionLogCount.innerText = sessionChangesLog.length;

  if (sessionChangesLog.length === 0) {
    modalSessionTimeline.innerHTML = '<div style="color: #64748b; font-size: 11px; text-align: center; padding: 14px 0;">No edits recorded in this session yet.</div>';
    return;
  }

  modalSessionTimeline.innerHTML = "";
  sessionChangesLog.forEach((item) => {
    const el = document.createElement("div");
    el.className = "timeline-item";
    el.innerHTML = `
      <span class="timeline-time">${escapeHtml(item.time)}</span>
      <span class="timeline-desc">${escapeHtml(item.summary)}</span>
    `;
    modalSessionTimeline.appendChild(el);
  });
}

async function generateAiCommitMessage() {
  if (!activeApp) return;

  const origHtml = btnGenerateAiCommitMsg.innerHTML;
  btnGenerateAiCommitMsg.disabled = true;
  btnGenerateAiCommitMsg.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Generating...';

  try {
    const files = (currentGitStatus?.files || []).map((f) => f.path);
    const recent = sessionChangesLog.slice(0, 5).map((s) => s.summary);

    const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/generate-commit-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files, recent_actions: recent })
    });

    if (res.ok) {
      const data = await res.json();
      if (data.commit_message) {
        commitMsgInput.value = data.commit_message;
      }
    }
  } catch (e) {
    console.error("AI commit message generation failed:", e);
  } finally {
    btnGenerateAiCommitMsg.disabled = false;
    btnGenerateAiCommitMsg.innerHTML = origHtml;
  }
}

async function commitAndPushApp(pushRemote = true) {
  if (!activeApp) return;

  const msg = commitMsgInput.value.trim() || `Update ${activeApp.name} via Geppy's Galactic`;

  btnCommitPcOnly.disabled = true;
  btnDoCommitAndPush.disabled = true;

  commitFeedback.className = "commit-feedback";
  commitFeedback.style.display = "block";
  commitFeedback.innerHTML = `
    <div style="display: flex; align-items: center; gap: 8px; color: #a5b4fc;">
      <i class="fa-solid fa-spinner animate-spin"></i>
      <span>${pushRemote ? "Saving to disk, committing to local Git, and pushing to GitHub..." : "Saving and committing to local Git on computer..."}</span>
    </div>
  `;

  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/push-github`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        commit_message: msg,
        push_remote: pushRemote
      })
    });

    const data = await res.json();

    if (data.success) {
      if (pushRemote && data.pushed_to_github) {
        commitFeedback.className = "commit-feedback success";
        commitFeedback.innerHTML = `
          <div style="font-weight: 700; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
            <i class="fa-solid fa-circle-check"></i>
            <span>Successfully Synced to Computer &amp; GitHub!</span>
          </div>
          <div style="font-size: 10.5px; opacity: 0.95;">
            💻 <strong>Local PC:</strong> Saved to disk &amp; committed (<code>${data.commit_hash || "HEAD"}</code>)<br>
            🐙 <strong>GitHub:</strong> Pushed to <code>${data.branch || "main"}</code>
            ${data.github_url ? ` (<a href="${data.github_url}" target="_blank" style="color: #67e8f9; text-decoration: underline;">Open GitHub Repo</a>)` : ""}
          </div>
        `;
      } else {
        // Saved locally, push pending/warning or local-only
        commitFeedback.className = data.warning ? "commit-feedback warning" : "commit-feedback success";
        commitFeedback.innerHTML = `
          <div style="font-weight: 700; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
            <i class="fa-solid fa-hard-drive"></i>
            <span>Changes Saved to Computer Disk!</span>
          </div>
          <div style="font-size: 10.5px; opacity: 0.95;">
            💻 Committed to local Git (<code>${data.commit_hash || "HEAD"}</code>) on branch <code>${data.branch || "main"}</code>.<br>
            ${data.warning ? `<span style="color: #fbbf24;">⚠️ GitHub note: ${escapeHtml(data.warning)}</span>` : "Ready to push to GitHub anytime."}
          </div>
        `;
      }

      logSessionChange("commit", `Committed changes (${data.commit_hash || "HEAD"}): "${msg}"${pushRemote && data.pushed_to_github ? " (Pushed to GitHub)" : ""}`);
      await refreshGitStatus();
      commitMsgInput.value = "";
    } else {
      commitFeedback.className = "commit-feedback error";
      commitFeedback.innerHTML = `
        <div style="font-weight: 700; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
          <i class="fa-solid fa-circle-exclamation"></i>
          <span>Save / Push Failed</span>
        </div>
        <div style="font-size: 10.5px;">${escapeHtml(data.message || "Unknown error occurred.")}</div>
      `;
    }
  } catch (e) {
    commitFeedback.className = "commit-feedback error";
    commitFeedback.innerHTML = `
      <div style="font-weight: 700; margin-bottom: 4px;">Save / Push Exception</div>
      <div style="font-size: 10.5px;">${escapeHtml(String(e))}</div>
    `;
  } finally {
    btnCommitPcOnly.disabled = false;
    btnDoCommitAndPush.disabled = false;
  }
}
