// Geppy's GitBridge - Chrome Extension Side Panel Controller
const SERVER_URL = "http://127.0.0.1:8000";
const ANTIGRAVITY_SERVICE_URL = "http://127.0.0.1:8001";

let _aiHudTimerInterval = null;
let _aiHudPollInterval = null;
let _aiHudHideTimeout = null;
let _aiHudStartedAt = 0;
let _aiHudSoundEnabled = localStorage.getItem("geppy_ai_hud_sound") !== "0";

function playAiCompletionChime(success = true) {
  if (!_aiHudSoundEnabled) return;
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const now = ctx.currentTime;
    const notes = success ? [587.33, 880.0] : [330.0, 246.94]; // D5 -> A5 chime on success
    notes.forEach((freq, idx) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, now + idx * 0.11);
      gain.gain.setValueAtTime(0.001, now + idx * 0.11);
      gain.gain.exponentialRampToValueAtTime(0.11, now + idx * 0.11 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + idx * 0.11 + 0.28);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + idx * 0.11);
      osc.stop(now + idx * 0.11 + 0.3);
    });
  } catch (e) {}
}

function showInPageAiCompletionToast(titleText, elapsedSec, modifiedFiles = []) {
  try {
    if (!chrome || !chrome.scripting || !activeTabId) return;
    const filesLabel = Array.isArray(modifiedFiles) && modifiedFiles.length > 0
      ? ` • Updated ${modifiedFiles.join(", ")}`
      : "";
    chrome.scripting.executeScript({
      target: { tabId: activeTabId },
      func: (msg, sub) => {
        try {
          const old = document.getElementById("geppy-ai-done-toast");
          if (old) old.remove();
          const t = document.createElement("div");
          t.id = "geppy-ai-done-toast";
          t.style.cssText = "position:fixed;top:16px;right:16px;z-index:2147483647;background:linear-gradient(135deg,#064e3b,#0f172a);color:#ecfdf5;border:1.5px solid #10b981;border-radius:12px;padding:10px 14px;box-shadow:0 12px 30px rgba(0,0,0,0.55);font-family:system-ui,-apple-system,sans-serif;font-size:12px;max-width:340px;display:flex;align-items:center;gap:10px;transition:opacity 0.3s ease;";
          t.innerHTML = `<div style="width:26px;height:26px;border-radius:8px;background:rgba(16,185,129,0.25);color:#34d399;display:flex;align-items:center;justify-content:center;font-size:15px;flex-shrink:0;">✅</div><div style="min-width:0;"><div style="font-weight:800;color:#6ee7b7;font-size:12px;">Geppy AI Task Complete!</div><div style="color:#cbd5e1;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${msg}${sub}</div></div>`;
          document.body.appendChild(t);
          setTimeout(() => {
            t.style.opacity = "0";
            setTimeout(() => t.remove(), 350);
          }, 5500);
        } catch (e) {}
      },
      args: [titleText, ` (${elapsedSec}s)${filesLabel}`],
    }).catch(() => {});
  } catch (e) {}
}

function initAiHudControls() {
  const hud = document.getElementById("ai-live-flight-deck-hud");
  if (!hud || hud.dataset.bound === "1") return;
  hud.dataset.bound = "1";

  const soundBtn = document.getElementById("btn-ai-hud-sound-toggle");
  const jumpBtn = document.getElementById("btn-ai-hud-jump");
  const dismissBtn = document.getElementById("btn-ai-hud-dismiss");

  if (soundBtn) {
    soundBtn.textContent = _aiHudSoundEnabled ? "🔔" : "🔕";
    soundBtn.style.opacity = _aiHudSoundEnabled ? "1" : "0.55";
    soundBtn.addEventListener("click", () => {
      _aiHudSoundEnabled = !_aiHudSoundEnabled;
      localStorage.setItem("geppy_ai_hud_sound", _aiHudSoundEnabled ? "1" : "0");
      soundBtn.textContent = _aiHudSoundEnabled ? "🔔" : "🔕";
      soundBtn.style.opacity = _aiHudSoundEnabled ? "1" : "0.55";
      if (_aiHudSoundEnabled) playAiCompletionChime(true);
    });
  }
  if (jumpBtn) {
    jumpBtn.addEventListener("click", () => {
      const chatContainer = document.getElementById("chat-history");
      if (chatContainer) {
        chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: "smooth" });
      }
    });
  }
  if (dismissBtn) {
    dismissBtn.addEventListener("click", () => {
      hud.classList.add("hidden");
    });
  }
}

function startAiLiveHud(taskTitle = "AI Task Running", targetFile = "", modeLabel = "⚡ AI RUNNING") {
  initAiHudControls();
  const hud = document.getElementById("ai-live-flight-deck-hud");
  if (!hud) return;

  if (_aiHudHideTimeout) {
    clearTimeout(_aiHudHideTimeout);
    _aiHudHideTimeout = null;
  }
  if (_aiHudTimerInterval) clearInterval(_aiHudTimerInterval);
  if (_aiHudPollInterval) clearInterval(_aiHudPollInterval);

  _aiHudStartedAt = performance.now();
  hud.classList.remove("hidden");
  hud.style.background = "linear-gradient(135deg, rgba(30, 27, 75, 0.96), rgba(15, 23, 42, 0.98))";
  hud.style.borderColor = "rgba(168, 85, 247, 0.75)";
  hud.style.animation = "none";

  const progressBar = document.getElementById("ai-hud-progress-bar");
  const stateIcon = document.getElementById("ai-hud-state-icon");
  const stateBadge = document.getElementById("ai-hud-state-badge");
  const titleEl = document.getElementById("ai-hud-task-title");
  const timerEl = document.getElementById("ai-hud-elapsed-timer");
  const phaseEl = document.getElementById("ai-hud-phase-text");
  const fileEl = document.getElementById("ai-hud-target-file");
  const stepsEl = document.getElementById("ai-hud-live-steps");
  const jumpBtn = document.getElementById("btn-ai-hud-jump");
  const agHeaderBtn = document.getElementById("btn-antigravity-status");

  if (progressBar) {
    progressBar.style.background = "linear-gradient(90deg, #ec4899, #8b5cf6, #06b6d4, #10b981, #f59e0b)";
    progressBar.style.backgroundSize = "200% 100%";
    progressBar.style.animation = "geppyHudShimmer 1.4s linear infinite";
  }
  if (stateIcon) {
    stateIcon.style.background = "rgba(168, 85, 247, 0.25)";
    stateIcon.style.color = "#e879f9";
    stateIcon.innerHTML = '<i class="fa-solid fa-atom fa-spin"></i>';
  }
  if (stateBadge) {
    stateBadge.style.background = "rgba(168, 85, 247, 0.3)";
    stateBadge.style.color = "#f5d0fe";
    stateBadge.style.borderColor = "rgba(192, 132, 252, 0.5)";
    stateBadge.textContent = modeLabel;
  }
  if (titleEl) titleEl.textContent = taskTitle;
  if (timerEl) {
    timerEl.style.color = "#38bdf8";
    timerEl.textContent = "0.0s";
  }
  if (phaseEl) phaseEl.textContent = "Dispatching to warm Antigravity session on Port 8001...";
  if (fileEl) {
    fileEl.textContent = targetFile || "";
    fileEl.style.display = targetFile ? "inline-block" : "none";
  }
  if (stepsEl) stepsEl.innerHTML = "";
  if (jumpBtn) jumpBtn.classList.add("hidden");
  if (agHeaderBtn) {
    agHeaderBtn.style.borderColor = "#f59e0b";
    agHeaderBtn.style.boxShadow = "0 0 10px rgba(245, 158, 11, 0.55)";
  }

  _aiHudTimerInterval = setInterval(() => {
    const sec = ((performance.now() - _aiHudStartedAt) / 1000).toFixed(1);
    if (timerEl) timerEl.textContent = `${sec}s`;
  }, 100);

  _aiHudPollInterval = setInterval(async () => {
    try {
      const r = await fetch(`${ANTIGRAVITY_SERVICE_URL}/live`).catch(() => fetch(`${SERVER_URL}/api/extension/antigravity/live`));
      if (!r || !r.ok) return;
      const live = await r.json();
      if (!live || !live.is_busy) return;
      if (phaseEl && live.phase) phaseEl.textContent = live.phase;
      if (fileEl && live.target_file) {
        fileEl.textContent = live.target_file;
        fileEl.style.display = "inline-block";
      }
      if (stepsEl && Array.isArray(live.live_steps) && live.live_steps.length > 0) {
        stepsEl.innerHTML = live.live_steps.slice(-4).map((s) =>
          `<span style="font-size:9.5px; padding:1px 6px; border-radius:4px; background:rgba(30,41,59,0.95); color:#e2e8f0; border:1px solid rgba(148,163,184,0.25); white-space:nowrap;">${escapeHtml(s.label || s.tool || "Step")} <code style="color:#67e8f9;">${escapeHtml((s.detail || s.file || "").slice(0, 28))}</code></span>`
        ).join("");
      }
    } catch (e) {}
  }, 450);
}

function finishAiLiveHud({ success = true, title = "Task Complete", summary = "", modifiedFiles = [] } = {}) {
  if (_aiHudTimerInterval) {
    clearInterval(_aiHudTimerInterval);
    _aiHudTimerInterval = null;
  }
  if (_aiHudPollInterval) {
    clearInterval(_aiHudPollInterval);
    _aiHudPollInterval = null;
  }

  const elapsedSec = _aiHudStartedAt ? ((performance.now() - _aiHudStartedAt) / 1000).toFixed(1) : "0.0";
  const hud = document.getElementById("ai-live-flight-deck-hud");
  const agHeaderBtn = document.getElementById("btn-antigravity-status");
  if (agHeaderBtn) {
    agHeaderBtn.style.borderColor = "rgba(168, 85, 247, 0.55)";
    agHeaderBtn.style.boxShadow = "none";
  }
  if (!hud) return;

  const progressBar = document.getElementById("ai-hud-progress-bar");
  const stateIcon = document.getElementById("ai-hud-state-icon");
  const stateBadge = document.getElementById("ai-hud-state-badge");
  const titleEl = document.getElementById("ai-hud-task-title");
  const timerEl = document.getElementById("ai-hud-elapsed-timer");
  const phaseEl = document.getElementById("ai-hud-phase-text");
  const fileEl = document.getElementById("ai-hud-target-file");
  const jumpBtn = document.getElementById("btn-ai-hud-jump");

  if (success) {
    hud.style.background = "linear-gradient(135deg, rgba(6, 78, 59, 0.96), rgba(15, 23, 42, 0.98))";
    hud.style.borderColor = "#10b981";
    hud.style.animation = "geppyDonePulse 1.6s ease-in-out 3";
    if (progressBar) {
      progressBar.style.animation = "none";
      progressBar.style.background = "linear-gradient(90deg, #10b981, #34d399, #06b6d4)";
    }
    if (stateIcon) {
      stateIcon.style.background = "rgba(16, 185, 129, 0.25)";
      stateIcon.style.color = "#34d399";
      stateIcon.innerHTML = '<i class="fa-solid fa-check"></i>';
    }
    if (stateBadge) {
      stateBadge.style.background = "rgba(16, 185, 129, 0.28)";
      stateBadge.style.color = "#a7f3d0";
      stateBadge.style.borderColor = "rgba(52, 211, 153, 0.65)";
      stateBadge.textContent = "✅ AI DONE!";
    }
    if (timerEl) {
      timerEl.style.color = "#34d399";
      timerEl.textContent = `${elapsedSec}s`;
    }
    if (jumpBtn) jumpBtn.classList.remove("hidden");
  } else {
    hud.style.background = "linear-gradient(135deg, rgba(127, 29, 29, 0.95), rgba(15, 23, 42, 0.98))";
    hud.style.borderColor = "#f87171";
    if (progressBar) {
      progressBar.style.animation = "none";
      progressBar.style.background = "#ef4444";
    }
    if (stateIcon) {
      stateIcon.style.background = "rgba(239, 68, 68, 0.25)";
      stateIcon.style.color = "#fca5a5";
      stateIcon.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
    }
    if (stateBadge) {
      stateBadge.style.background = "rgba(239, 68, 68, 0.28)";
      stateBadge.style.color = "#fecaca";
      stateBadge.style.borderColor = "rgba(248, 113, 113, 0.6)";
      stateBadge.textContent = "⚠️ AI ERROR";
    }
  }

  if (titleEl) titleEl.textContent = title;
  if (phaseEl) {
    phaseEl.textContent = summary || (success ? `Finished in ${elapsedSec}s — Ready in Chat below!` : "Task encountered an error.");
  }
  if (fileEl && Array.isArray(modifiedFiles) && modifiedFiles.length > 0) {
    fileEl.textContent = modifiedFiles.join(", ");
    fileEl.style.display = "inline-block";
  }

  playAiCompletionChime(success);
  if (success) {
    showInPageAiCompletionToast(title, elapsedSec, modifiedFiles);
  }

  _aiHudHideTimeout = setTimeout(() => {
    if (hud) hud.classList.add("hidden");
  }, 14000);
}

async function fetchAntigravityApi(path, options = {}) {
  const isAiHeavyAction = /\/(brainstorm|apply-design|edit|execute|agents\/run|agents\/council)/i.test(path);
  let hudTitle = "Running AI Task...";
  let hudTargetFile = "";
  let hudMode = "⚡ AI RUNNING";

  if (isAiHeavyAction) {
    try {
      const bodyObj = options && options.body ? JSON.parse(options.body) : {};
      hudTargetFile = bodyObj.file_path || "";
      if (/apply-design|edit/i.test(path)) {
        hudMode = "✏️ SURGICAL EDIT";
        hudTitle = (bodyObj.instruction || "Applying code modification").slice(0, 75);
      } else if (/brainstorm/i.test(path)) {
        hudMode = bodyObj.agent_id ? `🤖 @${bodyObj.agent_id.toUpperCase()}` : "🧠 AI BRAINSTORM";
        hudTitle = (bodyObj.message || bodyObj.prompt || "Analyzing & brainstorming").slice(0, 75);
      } else {
        hudTitle = (bodyObj.task_title || bodyObj.prompt || "Executing AI Mission").slice(0, 75);
      }
    } catch (e) {}
    startAiLiveHud(hudTitle, hudTargetFile, hudMode);
  }

  try {
    let res = null;
    try {
      res = await fetch(`${ANTIGRAVITY_SERVICE_URL}${path}`, options);
      if (!res.ok && res.status !== 400 && res.status !== 404) {
        res = null;
      }
    } catch (e) {
      res = null;
    }
    if (!res) {
      res = await fetch(`${SERVER_URL}${path}`, options);
    }

    if (isAiHeavyAction) {
      try {
        const cloned = res.clone();
        const d = await cloned.json();
        if (d && d.antigravity_error && typeof window.showAntigravityErrorInGalactic === "function") {
          window.showAntigravityErrorInGalactic(d.antigravity_error);
        }
        const modFiles = d.modified_files || (d.target_file ? [d.target_file] : []);
        const tasksCount = Array.isArray(d.extracted_tasks) ? d.extracted_tasks.length : 0;
        const doneSummary = modFiles.length > 0
          ? `Updated ${modFiles.join(", ")} — Live in Studio!`
          : tasksCount > 0
          ? `Response ready + ${tasksCount} Proceed task${tasksCount === 1 ? "" : "s"} queued!`
          : "Response ready in Chat!";
        finishAiLiveHud({
          success: res.ok && d.success !== false,
          title: hudTitle,
          summary: doneSummary,
          modifiedFiles: modFiles,
        });
      } catch (e) {
        finishAiLiveHud({ success: res.ok, title: hudTitle });
      }
    }
    return res;
  } catch (err) {
    if (isAiHeavyAction) {
      finishAiLiveHud({ success: false, title: hudTitle, summary: String(err) });
    }
    throw err;
  }
}

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
const btnStopApp = document.getElementById("btn-stop-app");
const btnTogglePortDrawer = document.getElementById("btn-toggle-port-drawer");
const runningPortsCount = document.getElementById("running-ports-count");
const galacticPortDrawer = document.getElementById("galactic-port-drawer");
const galacticPortList = document.getElementById("galactic-port-list");
const btnRefreshPortDrawer = document.getElementById("btn-refresh-port-drawer");
const btnOpenFullPortWatcher = document.getElementById("btn-open-full-port-watcher");
const btnStopAllPorts = document.getElementById("btn-stop-all-ports");
const btnClosePortDrawer = document.getElementById("btn-close-port-drawer");
const btnDetectTab = document.getElementById("btn-detect-tab");

const btnModeBrainstorm = document.getElementById("btn-mode-brainstorm");
const btnModeDesigner = document.getElementById("btn-mode-designer");
const btnModeAssets = document.getElementById("btn-mode-assets");
const viewBrainstorm = document.getElementById("view-brainstorm");
const viewDesigner = document.getElementById("view-designer");
const viewAssets = document.getElementById("view-assets");

// Assets Subnav & Image Management Elements
let activeAppImages = [];
let currentSynthesizedAsset = null;
let selectedTaskIds = new Set();
let isBatchRunning = false;

const btnAssetsSubManager = document.getElementById("btn-assets-sub-manager");
const btnAssetsSubLab = document.getElementById("btn-assets-sub-lab");
const btnBackupAllImages = document.getElementById("btn-backup-all-images");
const btnRefreshAppImages = document.getElementById("btn-refresh-app-images");
const sectionAppImages = document.getElementById("section-app-images");
const sectionAssetLab = document.getElementById("section-asset-lab");
const detectedImagesCount = document.getElementById("detected-images-count");
const imagesTotalSize = document.getElementById("images-total-size");
const appImagesGrid = document.getElementById("app-images-grid");

// Asset Lab Station Elements
const extLabPurpose = document.getElementById("ext-lab-purpose");
const extLabPurposeSelect = document.getElementById("ext-lab-purpose-select");
const extLabBrandSelect = document.getElementById("ext-lab-brand-select");
const extLabShapePreset = document.getElementById("ext-lab-shape-preset");
const extLabStyleContextile = document.getElementById("ext-lab-style-contextile");
const extLabStyle = document.getElementById("ext-lab-style");
const extLabStyleSelect = document.getElementById("ext-lab-style-select");
const btnOpenCreateContextileModal = document.getElementById("btn-open-create-contextile-modal");

// Asset Lab Brand & Style Reference Widgets
let extLabUploadedRefImageUrl = null;
const extLabBrandChip = document.getElementById("ext-lab-brand-chip");
const extLabBrandThumb = document.getElementById("ext-lab-brand-thumb");
const extLabBrandName = document.getElementById("ext-lab-brand-name");
const extLabRefFile = document.getElementById("ext-lab-ref-file");
const extLabRefDropzone = document.getElementById("ext-lab-ref-dropzone");
const extLabRefPromptText = document.getElementById("ext-lab-ref-prompt-text");
const extLabRefPreviewBar = document.getElementById("ext-lab-ref-preview-bar");
const extLabRefThumb = document.getElementById("ext-lab-ref-thumb");
const extLabRefName = document.getElementById("ext-lab-ref-name");
const extLabRefStatus = document.getElementById("ext-lab-ref-status");
const btnRemoveExtLabRef = document.getElementById("btn-remove-ext-lab-ref");
const btnUseAppIconRef = document.getElementById("btn-use-app-icon-ref");

const btnExtBrainstormConcepts = document.getElementById("btn-ext-brainstorm-concepts");
const btnExtInstantSynthesize = document.getElementById("btn-ext-instant-synthesize");
const extLabConceptsBox = document.getElementById("ext-lab-concepts-box");
const extLabConceptsList = document.getElementById("ext-lab-concepts-list");
const extLabDropDock = document.getElementById("ext-lab-drop-dock");
const extLabPreviewImg = document.getElementById("ext-lab-preview-img");
const extLabPreviewSvg = document.getElementById("ext-lab-preview-svg");
const extLabAssetTitle = document.getElementById("ext-lab-asset-title");
const extLabPaletteChips = document.getElementById("ext-lab-palette-chips");
const extLabTargetFolder = document.getElementById("ext-lab-target-folder");
const extLabCustomFolder = document.getElementById("ext-lab-custom-folder");
const extLabFilename = document.getElementById("ext-lab-filename");
const chkSetAppIcon = document.getElementById("chk-set-app-icon");
const chkUpdateCodeRefs = document.getElementById("chk-update-code-refs");
const btnDropAssetToApp = document.getElementById("btn-drop-asset-to-app");
const btnDropSaveOnly = document.getElementById("btn-drop-save-only");
const dropAssetFeedback = document.getElementById("drop-asset-feedback");

// Direct App Upload Elements
const btnToggleAppUpload = document.getElementById("btn-toggle-app-upload");
const appUploadDock = document.getElementById("app-upload-dock");
const btnCloseAppUpload = document.getElementById("btn-close-app-upload");
const appUploadFileInput = document.getElementById("app-upload-file-input");
const appUploadDropzone = document.getElementById("app-upload-dropzone");
const appUploadPromptText = document.getElementById("app-upload-prompt-text");
const appUploadTargetFolder = document.getElementById("app-upload-target-folder");
const chkAppUploadSetIcon = document.getElementById("chk-app-upload-set-icon");
const chkAppUploadCodeRefs = document.getElementById("chk-app-upload-code-refs");
const btnDoAppUpload = document.getElementById("btn-do-app-upload");
const appUploadFeedback = document.getElementById("app-upload-feedback");
let pendingAppUploadFile = null;
let appFileList = [];

// Modal Save Context Style Elements
let uploadedCtxStyleImageUrl = null;
const modalSaveContextile = document.getElementById("modal-save-contextile");
const btnCloseSaveContextile = document.getElementById("btn-close-save-contextile");
const btnCancelSaveCtx = document.getElementById("btn-cancel-save-ctx");
const btnSubmitSaveCtx = document.getElementById("btn-submit-save-ctx");
const ctxStyleHandle = document.getElementById("ctx-style-handle");
const ctxStyleTitle = document.getElementById("ctx-style-title");
const ctxStyleDropzone = document.getElementById("ctx-style-dropzone");
const ctxStyleFile = document.getElementById("ctx-style-file");
const ctxStyleUploadPrompt = document.getElementById("ctx-style-upload-prompt");
const ctxStyleFilePreview = document.getElementById("ctx-style-file-preview");
const ctxStylePreviewImg = document.getElementById("ctx-style-preview-img");
const ctxStyleFileName = document.getElementById("ctx-style-file-name");
const ctxStyleFileMeta = document.getElementById("ctx-style-file-meta");
const btnClearCtxFile = document.getElementById("btn-clear-ctx-file");
const ctxStyleShape = document.getElementById("ctx-style-shape");
const ctxStyleAccentPicker = document.getElementById("ctx-style-accent-picker");
const ctxStyleAccentHex = document.getElementById("ctx-style-accent-hex");
const ctxStyleBg = document.getElementById("ctx-style-bg");
const ctxStyleArchetype = document.getElementById("ctx-style-archetype");
const ctxStylePrompt = document.getElementById("ctx-style-prompt");
const ctxStyleFeedback = document.getElementById("ctx-style-feedback");

// Backlog Batch Runner Elements
const chkBacklogSelectAll = document.getElementById("chk-backlog-select-all");
const chkAlwaysConfirmTarget = document.getElementById("chk-always-confirm-target");
const batchSelectedCount = document.getElementById("batch-selected-count");
const btnRunBatchTasks = document.getElementById("btn-run-batch-tasks");
const btnRunNextBatch = document.getElementById("btn-run-next-batch");
const batchProgressBanner = document.getElementById("batch-progress-banner");
const batchProgressStatus = document.getElementById("batch-progress-status");
const batchProgressPercent = document.getElementById("batch-progress-percent");
const batchProgressBar = document.getElementById("batch-progress-bar");

// Implementation Control Center Elements
const implementationModal = document.getElementById("implementation-modal");
const btnCloseImplModal = document.getElementById("btn-close-impl-modal");
const implModalTitle = document.getElementById("impl-modal-title");
const implModalDesc = document.getElementById("impl-modal-desc");
const implModalCategory = document.getElementById("impl-modal-category");
const implModalStatusBadge = document.getElementById("impl-modal-status-badge");
const implTargetFileSelect = document.getElementById("impl-target-file-select");
const implBtnNewFileToggle = document.getElementById("impl-btn-new-file-toggle");
const implNewFileBox = document.getElementById("impl-new-file-box");
const implNewFilePath = document.getElementById("impl-new-file-path");
const implSuggestedTag = document.getElementById("impl-suggested-tag");
const radioImplReview = document.getElementById("radio-impl-review");
const radioImplDirect = document.getElementById("radio-impl-direct");
const modeCardReview = document.getElementById("mode-card-review");
const modeCardDirect = document.getElementById("mode-card-direct");
const implChkSaveDisk = document.getElementById("impl-chk-save-disk");
const implChkReloadTab = document.getElementById("impl-chk-reload-tab");
const implChkMarkDone = document.getElementById("impl-chk-mark-done");
const implProgressTracker = document.getElementById("impl-progress-tracker");
const implFeedbackBanner = document.getElementById("impl-feedback-banner");
const btnExecuteImplementation = document.getElementById("btn-execute-implementation");
let currentImplTask = null;
let currentImplCard = null;

// Brainstorm Elements
const chatHistoryEl = document.getElementById("chat-history");
const brainstormInput = document.getElementById("brainstorm-input");
const btnSendBrainstorm = document.getElementById("btn-send-brainstorm");
const btnChatModeImage = document.getElementById("btn-chat-mode-image");
const chatContextDrawer = document.getElementById("chat-context-drawer");
const btnToggleContextDrawer = document.getElementById("btn-toggle-context-drawer");
const btnCloseContextDrawer = document.getElementById("btn-close-context-drawer");
let isChatImageMode = false;
const backlogCount = document.getElementById("backlog-count");
const backlogSummaryDone = document.getElementById("backlog-summary-done");
const backlogHeader = document.getElementById("backlog-header");
const backlogList = document.getElementById("backlog-list");
const btnAddCustomTask = document.getElementById("btn-add-custom-task");
const btnToggleBacklog = document.getElementById("btn-toggle-backlog");
const backlogDrawer = document.getElementById("backlog-drawer");

// Backlog Folder & Done Pile Elements
const tabBacklogActive = document.getElementById("tab-backlog-active");
const tabBacklogDone = document.getElementById("tab-backlog-done");
const badgeActiveTasksCount = document.getElementById("badge-active-tasks-count");
const badgeDoneTasksCount = document.getElementById("badge-done-tasks-count");
const backlogBatchBar = document.getElementById("backlog-batch-bar");
const backlogDoneDock = document.getElementById("backlog-done-dock");
const doneFolderToggle = document.getElementById("done-folder-toggle");
const doneFolderIcon = document.getElementById("done-folder-icon");
const doneFolderCountBadge = document.getElementById("done-folder-count-badge");
const btnClearDonePile = document.getElementById("btn-clear-done-pile");
const doneFolderChevron = document.getElementById("done-folder-chevron");
const backlogDoneList = document.getElementById("backlog-done-list");
const btnBatchMarkDone = document.getElementById("btn-batch-mark-done");

let currentBacklogTab = "active"; // "active" | "done"
let isDoneFolderExpanded = false;

// Designer Elements
const proactiveSuggestionsDrawer = document.getElementById("proactive-suggestions-drawer");
const btnToggleSuggestionsDrawer = document.getElementById("btn-toggle-suggestions-drawer");
const btnCloseSuggestionsDrawer = document.getElementById("btn-close-suggestions-drawer");
const btnToggleCodeDrawer = document.getElementById("btn-toggle-code-drawer");
const btnCloseCodeDrawer = document.getElementById("btn-close-code-drawer");
const btnChatDirectEdit = document.getElementById("btn-chat-direct-edit");
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

// Central API Key Vault & Antigravity SDK elements
const btnAntigravityStatus = document.getElementById("btn-antigravity-status");
const btnCentralKeyVault = document.getElementById("btn-central-key-vault");
const centralKeyLabel = document.getElementById("central-key-label");
const centralKeyModal = document.getElementById("central-key-modal");
const btnCloseKeyModal = document.getElementById("btn-close-key-modal");
const btnDoneKeyModal = document.getElementById("btn-done-key-modal");
const vaultStatusBadge = document.getElementById("vault-status-badge");
const vaultMaskedKey = document.getElementById("vault-masked-key");
const vaultActiveModel = document.getElementById("vault-active-model");
const btnTestGeminiKey = document.getElementById("btn-test-gemini-key");
const btnSyncAllAppsKey = document.getElementById("btn-sync-all-apps-key");
const btnOpenGitbridgeSettings = document.getElementById("btn-open-gitbridge-settings");
const vaultActionFeedback = document.getElementById("vault-action-feedback");

// Unrecognized Tab Bar, Off-Target Page Banner & Registration Modal Elements
let lastDetectedUnrecognized = null;
let activeTabInstance = { tabId: null, url: null, port: null, slug: null };
let currentBrowserTabUrl = "";
let currentTabDetectedApp = null;
const unrecognizedAppBar = document.getElementById("unrecognized-app-bar");
const unrecognizedUrlLabel = document.getElementById("unrecognized-url-label");
const btnReassociateTab = document.getElementById("btn-reassociate-tab");
const reassociateBtnText = document.getElementById("reassociate-btn-text");
const btnShowAddAppModal = document.getElementById("btn-show-add-app-modal");
const btnHeaderAddApp = document.getElementById("btn-header-add-app");

const offTargetPageBanner = document.getElementById("off-target-page-banner");
const offTargetPageText = document.getElementById("off-target-page-text");
const btnOffTargetOpenApp = document.getElementById("btn-off-target-open-app");
const btnOffTargetOpenLabel = document.getElementById("btn-off-target-open-label");
const btnOffTargetSwitchApp = document.getElementById("btn-off-target-switch-app");
const btnOffTargetSwitchLabel = document.getElementById("btn-off-target-switch-label");

const modalRegisterApp = document.getElementById("modal-register-app");
const btnCloseRegisterModal = document.getElementById("btn-close-register-modal");
const btnCancelRegister = document.getElementById("btn-cancel-register");
const regAppName = document.getElementById("reg-app-name");
const regAppUrl = document.getElementById("reg-app-url");
const regModeWorkspace = document.getElementById("reg-mode-workspace");
const regModeCustom = document.getElementById("reg-mode-custom");
const regAppCustomPath = document.getElementById("reg-app-custom-path");
const regRunDeepAnalysis = document.getElementById("reg-run-deep-analysis");
const regActionFeedback = document.getElementById("reg-action-feedback");
const btnSubmitRegisterApp = document.getElementById("btn-submit-register-app");

// SOT Fleet Big List Modal Elements
const btnOpenSotFleet = document.getElementById("btn-open-sot-fleet");
const modalSotFleet = document.getElementById("modal-sot-fleet");
const btnCloseSotFleet = document.getElementById("btn-close-sot-fleet");
const modalSotCountBadge = document.getElementById("modal-sot-count-badge");
const sotQuickbarCount = document.getElementById("sot-quickbar-count");
const sotSearchInput = document.getElementById("sot-search-input");
const sotFleetCardsList = document.getElementById("sot-fleet-cards-list");
const btnFleetCreateNew = document.getElementById("btn-fleet-create-new");
const btnOpenSotWebHub = document.getElementById("btn-open-sot-web-hub");
let currentSotFilter = "all";


// --- Initialization ---
document.addEventListener("DOMContentLoaded", async () => {
  setupEventListeners();
  // Fire initial startup queries in parallel so Galactic opens near-instantly
  await Promise.allSettled([
    checkServerConnection(),
    checkCentralKeyStatus(),
    checkAntigravityStatus(),
    loadApps(),
    loadContextiles(),
    refreshRunningServersState()
  ]);
  await detectActiveTabApp({ autoSwitchApp: true });
  setInterval(() => refreshRunningServersState(), 6000);
});

// Track tab switches so Watchdog ignores browser background-tab timer throttling when leaving/returning to a tab
let lastTabSwitchTimestamp = Date.now();

// Listen for tab change events from background.js and chrome.tabs directly
if (typeof chrome !== "undefined") {
  if (chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((msg) => {
      if (msg.type === "TAB_CHANGED") {
        lastTabSwitchTimestamp = Date.now();
        consecutiveHeartbeatTimeouts = 0;
        activeTabId = msg.tabId;
        detectAppFromUrl(msg.url, msg.tabId, { autoSwitchApp: !activeApp });
      }
    });
  }
  if (chrome.tabs) {
    if (chrome.tabs.onActivated) {
      chrome.tabs.onActivated.addListener(async (activeInfo) => {
        lastTabSwitchTimestamp = Date.now();
        consecutiveHeartbeatTimeouts = 0;
        try {
          const tab = await chrome.tabs.get(activeInfo.tabId);
          if (tab && tab.url) {
            activeTabId = tab.id;
            detectAppFromUrl(tab.url, tab.id, { autoSwitchApp: !activeApp });
          }
        } catch (e) {}
      });
    }
    if (chrome.tabs.onUpdated) {
      chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
        if (tab && tab.active && (changeInfo.url || changeInfo.status === "complete") && tab.url) {
          lastTabSwitchTimestamp = Date.now();
          consecutiveHeartbeatTimeouts = 0;
          activeTabId = tabId;
          detectAppFromUrl(tab.url, tabId, { autoSwitchApp: !activeApp });
        }
      });
    }
  }
}

function toggleChatContextDrawer(forceOpen = null) {
  if (!chatContextDrawer) return;
  const isHidden = chatContextDrawer.classList.contains("hidden");
  const shouldOpen = forceOpen !== null ? forceOpen : isHidden;
  if (shouldOpen) {
    chatContextDrawer.classList.remove("hidden");
    if (btnToggleContextDrawer) btnToggleContextDrawer.classList.add("active");
  } else {
    chatContextDrawer.classList.add("hidden");
    if (btnToggleContextDrawer) btnToggleContextDrawer.classList.remove("active");
  }
}

function setupEventListeners() {
  btnModeBrainstorm.addEventListener("click", () => switchMode("brainstorm"));
  btnModeDesigner.addEventListener("click", () => switchMode("designer"));
  if (btnAntigravityStatus) {
    btnAntigravityStatus.addEventListener("click", () => openActiveAppInAntigravityIde());
  }

  appSelect.addEventListener("change", (e) => onAppSelected(e.target.value));
  btnDetectTab.addEventListener("click", () => detectActiveTabApp({ autoSwitchApp: true }));
  btnLaunchApp.addEventListener("click", () => launchSelectedApp());
  if (btnStopApp) btnStopApp.addEventListener("click", () => stopSelectedApp());
  if (appLiveBadge) appLiveBadge.addEventListener("click", () => toggleGalacticPortDrawer());
  if (btnTogglePortDrawer) btnTogglePortDrawer.addEventListener("click", () => toggleGalacticPortDrawer());
  if (btnRefreshPortDrawer) btnRefreshPortDrawer.addEventListener("click", () => refreshRunningServersState());
  if (btnOpenFullPortWatcher) {
    btnOpenFullPortWatcher.addEventListener("click", () => {
      window.open(`${SERVER_URL}/#monitor`, "_blank");
    });
  }
  if (btnStopAllPorts) btnStopAllPorts.addEventListener("click", () => stopAllRunningAppsFromGalactic());
  if (btnClosePortDrawer) btnClosePortDrawer.addEventListener("click", () => toggleGalacticPortDrawer(false));

  if (btnOffTargetOpenApp) {
    btnOffTargetOpenApp.addEventListener("click", async () => {
      if (!activeApp) return;
      if (isGitBridgeApp(activeApp)) {
        await openOrFocusAppPortTab(SERVER_URL, activeApp.slug, 8000);
        currentBrowserTabUrl = SERVER_URL;
        currentTabDetectedApp = activeApp;
        updatePageMatchIndicator();
      } else if (activeApp.is_live && activeApp.live_url) {
        let portNum = null;
        try { portNum = new URL(activeApp.live_url).port; } catch (e) {}
        await openOrFocusAppPortTab(activeApp.live_url, activeApp.slug, portNum);
        currentBrowserTabUrl = activeApp.live_url;
        currentTabDetectedApp = activeApp;
        updatePageMatchIndicator();
      } else {
        await launchSelectedApp();
      }
    });
  }

  if (btnOffTargetSwitchApp) {
    btnOffTargetSwitchApp.addEventListener("click", async () => {
      if (currentTabDetectedApp) {
        const appInCatalog = (apps || []).find((a) => a.slug === currentTabDetectedApp.slug) || currentTabDetectedApp;
        await setActiveApp(appInCatalog);
      } else {
        await detectActiveTabApp({ autoSwitchApp: true });
      }
    });
  }

  // Brainstorm & Unified Studio Input + Context/Prompt Drawer
  if (btnToggleContextDrawer) btnToggleContextDrawer.addEventListener("click", () => toggleChatContextDrawer());
  if (btnCloseContextDrawer) btnCloseContextDrawer.addEventListener("click", () => toggleChatContextDrawer(false));
  if (btnChatModeImage) btnChatModeImage.addEventListener("click", () => toggleChatImageMode());
  btnSendBrainstorm.addEventListener("click", () => {
    toggleChatContextDrawer(false);
    submitBrainstorm();
  });
  if (btnChatDirectEdit) {
    btnChatDirectEdit.addEventListener("click", () => {
      const prompt = brainstormInput ? brainstormInput.value.trim() : "";
      if (!prompt) {
        if (brainstormInput) brainstormInput.focus();
        return;
      }
      toggleChatContextDrawer(false);
      brainstormInput.value = "";
      applyDesignerAiEdit(prompt);
    });
  }
  brainstormInput.addEventListener("input", () => {
    const val = brainstormInput.value;
    if (val.endsWith("@")) {
      toggleChatContextDrawer(true);
    }
  });
  brainstormInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      toggleChatContextDrawer(false);
      if ((e.ctrlKey || e.metaKey) && btnChatDirectEdit) {
        btnChatDirectEdit.click();
      } else {
        submitBrainstorm();
      }
    }
  });

  document.querySelectorAll(".pill-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prompt = btn.dataset.prompt;
      toggleChatContextDrawer(false);
      if (prompt) submitBrainstorm(prompt);
    });
  });

  btnAddCustomTask.addEventListener("click", (e) => {
    e.stopPropagation();
    promptAddCustomTask();
  });
  btnToggleBacklog.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleBacklogDrawer();
  });
  if (backlogHeader) {
    backlogHeader.addEventListener("click", (e) => {
      if (backlogDrawer && backlogDrawer.dataset.justDragged === "1") {
        backlogDrawer.dataset.justDragged = "0";
        return;
      }
      if (e.target.closest("#btn-add-custom-task") || e.target.closest("#btn-toggle-backlog")) return;
      toggleBacklogDrawer();
    });
  }
  initBacklogDrawerResize();

  // Inline Designer Drawers & File Bar
  if (btnToggleSuggestionsDrawer) {
    btnToggleSuggestionsDrawer.addEventListener("click", () => toggleSuggestionsDrawer());
  }
  if (btnCloseSuggestionsDrawer) {
    btnCloseSuggestionsDrawer.addEventListener("click", () => toggleSuggestionsDrawer(false));
  }
  if (btnToggleCodeDrawer) {
    btnToggleCodeDrawer.addEventListener("click", () => toggleCodeDrawer());
  }
  if (btnCloseCodeDrawer) {
    btnCloseCodeDrawer.addEventListener("click", () => toggleCodeDrawer(false));
  }

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

  // Central Key Vault Listeners
  if (btnCentralKeyVault) btnCentralKeyVault.addEventListener("click", () => openKeyModal());
  if (btnCloseKeyModal) btnCloseKeyModal.addEventListener("click", () => closeKeyModal());
  if (btnDoneKeyModal) btnDoneKeyModal.addEventListener("click", () => closeKeyModal());
  if (btnTestGeminiKey) btnTestGeminiKey.addEventListener("click", () => testCentralGeminiKey());
  if (btnSyncAllAppsKey) btnSyncAllAppsKey.addEventListener("click", () => syncCentralKeyToApps());
  if (btnOpenGitbridgeSettings) {
    btnOpenGitbridgeSettings.addEventListener("click", () => {
      window.open(`${SERVER_URL}/?action=settings`, "_blank");
    });
  }

  if (commitModal) {
    commitModal.addEventListener("click", (e) => {
      if (e.target === commitModal) closeCommitModal();
    });
  }

  if (centralKeyModal) {
    centralKeyModal.addEventListener("click", (e) => {
      if (e.target === centralKeyModal) closeKeyModal();
    });
  }

  // App Registration Listeners
  if (btnShowAddAppModal) btnShowAddAppModal.addEventListener("click", () => openRegisterModal());
  if (btnHeaderAddApp) btnHeaderAddApp.addEventListener("click", () => openRegisterModal());
  if (btnCloseRegisterModal) btnCloseRegisterModal.addEventListener("click", () => closeRegisterModal());
  if (btnCancelRegister) btnCancelRegister.addEventListener("click", () => closeRegisterModal());
  if (btnSubmitRegisterApp) btnSubmitRegisterApp.addEventListener("click", () => submitRegisterApp());

  if (regModeWorkspace) {
    regModeWorkspace.addEventListener("change", () => {
      if (regModeWorkspace.checked && regAppCustomPath) {
        regAppCustomPath.classList.add("hidden");
      }
    });
  }
  if (regModeCustom) {
    regModeCustom.addEventListener("change", () => {
      if (regModeCustom.checked && regAppCustomPath) {
        regAppCustomPath.classList.remove("hidden");
        regAppCustomPath.focus();
      }
    });
  }

  if (modalRegisterApp) {
    modalRegisterApp.addEventListener("click", (e) => {
      if (e.target === modalRegisterApp) closeRegisterModal();
    });
  }

  // Reassociate & Link Tab Listener
  if (btnReassociateTab) {
    btnReassociateTab.addEventListener("click", () => reassociateCurrentTabToActiveApp());
  }

  // Asset Lab & Image Manager Listeners
  if (btnModeAssets) btnModeAssets.addEventListener("click", () => switchMode("assets"));
  if (btnAssetsSubManager) btnAssetsSubManager.addEventListener("click", () => switchAssetsSubTab("manager"));
  if (btnAssetsSubLab) btnAssetsSubLab.addEventListener("click", () => switchAssetsSubTab("lab"));
  if (btnRefreshAppImages) btnRefreshAppImages.addEventListener("click", () => { if (activeApp) loadAppImages(activeApp.slug); });
  if (btnBackupAllImages) btnBackupAllImages.addEventListener("click", () => { if (activeApp) backupAppImages(activeApp.slug); });
  if (btnExtBrainstormConcepts) btnExtBrainstormConcepts.addEventListener("click", () => brainstormExtConcepts());
  if (btnExtInstantSynthesize) btnExtInstantSynthesize.addEventListener("click", () => instantSynthesizeExtAsset());
  if (btnDropAssetToApp) btnDropAssetToApp.addEventListener("click", () => dropAssetToApp());
  if (btnDropSaveOnly) btnDropSaveOnly.addEventListener("click", () => dropAssetToApp(false, false));

  // Implementation Modal Listeners
  if (btnCloseImplModal) btnCloseImplModal.addEventListener("click", () => closeImplementationModal());
  if (btnExecuteImplementation) btnExecuteImplementation.addEventListener("click", () => executeImplementationFromModal());
  if (implBtnNewFileToggle) {
    implBtnNewFileToggle.addEventListener("click", () => {
      if (implNewFileBox) {
        implNewFileBox.classList.toggle("hidden");
        if (!implNewFileBox.classList.contains("hidden") && implNewFilePath) {
          implNewFilePath.focus();
        }
      }
    });
  }

  // App Direct Upload Listeners
  if (btnToggleAppUpload) {
    btnToggleAppUpload.addEventListener("click", () => {
      if (!appUploadDock) return;
      appUploadDock.classList.toggle("hidden");
    });
  }
  if (btnCloseAppUpload) {
    btnCloseAppUpload.addEventListener("click", () => {
      if (appUploadDock) appUploadDock.classList.add("hidden");
    });
  }
  if (appUploadDropzone && appUploadFileInput) {
    appUploadDropzone.addEventListener("click", () => appUploadFileInput.click());
    appUploadDropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      appUploadDropzone.classList.add("dragover");
    });
    appUploadDropzone.addEventListener("dragleave", () => appUploadDropzone.classList.remove("dragover"));
    appUploadDropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      appUploadDropzone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleAppDirectUploadSelect(e.dataTransfer.files[0]);
      }
    });
    appUploadFileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        handleAppDirectUploadSelect(e.target.files[0]);
      }
    });
  }
  if (btnDoAppUpload) {
    btnDoAppUpload.addEventListener("click", () => executeDirectAppUpload());
  }

  // 3-Step Pipeline Listeners
  document.querySelectorAll(".btn-step-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      const parentShortcuts = btn.closest(".lab-pill-shortcuts");
      if (parentShortcuts) {
        parentShortcuts.querySelectorAll(".btn-step-pill").forEach(b => b.classList.remove("active"));
      } else {
        document.querySelectorAll(".btn-step-pill").forEach(b => b.classList.remove("active"));
      }
      btn.classList.add("active");

      if (extLabPurpose && btn.dataset.purpose) {
        extLabPurpose.value = btn.dataset.purpose;
        if (extLabPurposeSelect) {
          for (let i = 0; i < extLabPurposeSelect.options.length; i++) {
            if (extLabPurposeSelect.options[i].value === btn.dataset.purpose || extLabPurposeSelect.options[i].value.startsWith(btn.dataset.purpose)) {
              extLabPurposeSelect.selectedIndex = i;
              break;
            }
          }
        }
      }
      if (extLabStyle && btn.dataset.style) {
        extLabStyle.value = btn.dataset.style;
        if (extLabStyleSelect) {
          for (let i = 0; i < extLabStyleSelect.options.length; i++) {
            if (extLabStyleSelect.options[i].value === btn.dataset.style || extLabStyleSelect.options[i].value.startsWith(btn.dataset.style)) {
              extLabStyleSelect.selectedIndex = i;
              break;
            }
          }
        }
      }
      if (extLabShapePreset && btn.dataset.shape) {
        extLabShapePreset.value = btn.dataset.shape;
        onShapePresetChanged();
      }
    });
  });

  if (extLabPurposeSelect) {
    extLabPurposeSelect.addEventListener("change", () => {
      const val = extLabPurposeSelect.value;
      if (val && extLabPurpose) {
        extLabPurpose.value = val;
      }
    });
  }

  if (extLabStyleSelect) {
    extLabStyleSelect.addEventListener("change", () => {
      const val = extLabStyleSelect.value;
      if (val && extLabStyle) {
        extLabStyle.value = val;
      }
    });
  }

  if (extLabShapePreset) extLabShapePreset.addEventListener("change", () => onShapePresetChanged());
  if (extLabStyleContextile) extLabStyleContextile.addEventListener("change", () => onStyleContextileChanged());
  if (extLabBrandSelect) extLabBrandSelect.addEventListener("change", () => updateExtLabBrandChip());

  // Direct Style Reference Upload & Shortcuts
  if (extLabRefDropzone && extLabRefFile) {
    extLabRefDropzone.addEventListener("click", () => extLabRefFile.click());
    extLabRefDropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      extLabRefDropzone.classList.add("dragover");
    });
    extLabRefDropzone.addEventListener("dragleave", () => extLabRefDropzone.classList.remove("dragover"));
    extLabRefDropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      extLabRefDropzone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleExtLabRefFileUpload(e.dataTransfer.files[0]);
      }
    });
  }
  if (extLabRefFile) {
    extLabRefFile.addEventListener("change", (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleExtLabRefFileUpload(e.target.files[0]);
      }
    });
  }
  if (btnRemoveExtLabRef) btnRemoveExtLabRef.addEventListener("click", () => removeExtLabRef());
  if (btnUseAppIconRef) btnUseAppIconRef.addEventListener("click", () => useActiveAppIconAsRef());

  // Save Context Style Modal Listeners
  if (btnOpenCreateContextileModal) btnOpenCreateContextileModal.addEventListener("click", () => openSaveContextileModal());
  if (btnCloseSaveContextile) btnCloseSaveContextile.addEventListener("click", () => closeSaveContextileModal());
  if (btnCancelSaveCtx) btnCancelSaveCtx.addEventListener("click", () => closeSaveContextileModal());
  if (btnSubmitSaveCtx) btnSubmitSaveCtx.addEventListener("click", () => submitSaveContextile());

  if (ctxStyleDropzone && ctxStyleFile) {
    ctxStyleDropzone.addEventListener("click", (e) => {
      if (e.target !== btnClearCtxFile && !btnClearCtxFile?.contains(e.target)) {
        ctxStyleFile.click();
      }
    });
    ctxStyleFile.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        handleContextileFileUpload(e.target.files[0]);
      }
    });

    ctxStyleDropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      ctxStyleDropzone.classList.add("dragover");
    });
    ctxStyleDropzone.addEventListener("dragleave", () => ctxStyleDropzone.classList.remove("dragover"));
    ctxStyleDropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      ctxStyleDropzone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleContextileFileUpload(e.dataTransfer.files[0]);
      }
    });
  }

  if (btnClearCtxFile) {
    btnClearCtxFile.addEventListener("click", (e) => {
      e.stopPropagation();
      clearUploadedContextileFile();
    });
  }

  if (ctxStyleShape) ctxStyleShape.addEventListener("change", () => updateContextileModalPrompt());
  if (ctxStyleAccentPicker && ctxStyleAccentHex) {
    ctxStyleAccentPicker.addEventListener("input", () => {
      ctxStyleAccentHex.value = ctxStyleAccentPicker.value.toUpperCase();
      updateContextileModalPrompt();
    });
    ctxStyleAccentHex.addEventListener("input", () => {
      ctxStyleAccentPicker.value = ctxStyleAccentHex.value;
      updateContextileModalPrompt();
    });
  }
  if (ctxStyleBg) ctxStyleBg.addEventListener("change", () => updateContextileModalPrompt());
  if (ctxStyleArchetype) ctxStyleArchetype.addEventListener("change", () => updateContextileModalPrompt());

  if (modalSaveContextile) {
    modalSaveContextile.addEventListener("click", (e) => {
      if (e.target === modalSaveContextile) closeSaveContextileModal();
    });
  }

  // Backlog Batch Runner Listeners
  if (chkBacklogSelectAll) chkBacklogSelectAll.addEventListener("change", (e) => toggleSelectAllTasks(e.target.checked));
  if (btnRunBatchTasks) btnRunBatchTasks.addEventListener("click", () => runSelectedBatch());
  if (btnRunNextBatch) btnRunNextBatch.addEventListener("click", () => runNextBatch(3));
  if (btnBatchMarkDone) btnBatchMarkDone.addEventListener("click", () => markSelectedTasksDone());

  // Backlog Folder Tabs & Done Pile Listeners
  if (tabBacklogActive) tabBacklogActive.addEventListener("click", () => switchBacklogFolder("active"));
  if (tabBacklogDone) tabBacklogDone.addEventListener("click", () => switchBacklogFolder("done"));
  if (doneFolderToggle) {
    doneFolderToggle.addEventListener("click", (e) => {
      if (e.target.closest("#btn-clear-done-pile")) return;
      toggleDoneFolder();
    });
  }
  if (btnClearDonePile) {
    btnClearDonePile.addEventListener("click", (e) => {
      e.stopPropagation();
      clearDoneTasks();
    });
  }

  // Designer Task Picker Change: auto-populate prompt
  if (designerTaskPicker) {
    designerTaskPicker.addEventListener("change", (e) => {
      const taskId = e.target.value;
      if (!taskId) return;
      const task = backlogTasks.find((t) => t.id === taskId);
      if (task) {
        designerAiInput.value = task.suggested_prompt || task.title;
        designerAiInput.focus();
      }
    });
  }

  // SOT Fleet Modal Listeners
  if (btnOpenSotFleet) btnOpenSotFleet.addEventListener("click", () => openSotFleetModal());
  if (btnCloseSotFleet) btnCloseSotFleet.addEventListener("click", () => closeSotFleetModal());
  if (btnFleetCreateNew) {
    btnFleetCreateNew.addEventListener("click", () => {
      closeSotFleetModal();
      openSaveContextileModal();
    });
  }
  if (btnOpenSotWebHub) {
    btnOpenSotWebHub.addEventListener("click", () => {
      window.open(`${SERVER_URL}/#sot`, "_blank");
    });
  }
  if (sotSearchInput) {
    sotSearchInput.addEventListener("input", (e) => {
      renderSotFleetList(currentSotFilter, e.target.value);
    });
  }

  document.querySelectorAll(".sot-arch-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".sot-arch-pill").forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      currentSotFilter = pill.dataset.archetype || "all";
      renderSotFleetList(currentSotFilter, sotSearchInput?.value || "");
    });
  });

  if (modalSotFleet) {
    modalSotFleet.addEventListener("click", (e) => {
      if (e.target === modalSotFleet) closeSotFleetModal();
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" || e.keyCode === 27) {
      closeCommitModal();
      closeKeyModal();
      closeRegisterModal();
      closeSaveContextileModal();
      closeSotFleetModal();
    }
  });
}

// --- Mode Switcher & Inline Studio Drawers ---
function toggleSuggestionsDrawer(forceOpen = null) {
  if (!proactiveSuggestionsDrawer) return;
  const isHidden = proactiveSuggestionsDrawer.classList.contains("hidden");
  const shouldOpen = forceOpen !== null ? forceOpen : isHidden;
  if (shouldOpen) {
    proactiveSuggestionsDrawer.classList.remove("hidden");
    if (btnToggleSuggestionsDrawer) btnToggleSuggestionsDrawer.classList.add("active");
    updateDesignerTaskPicker();
    if (activeApp && activeFilePath && (!proactiveSuggestions || proactiveSuggestions.length === 0)) {
      fetchProactiveSuggestions(activeApp.slug, activeFilePath, codeEditor ? codeEditor.value : "");
    }
  } else {
    proactiveSuggestionsDrawer.classList.add("hidden");
    if (btnToggleSuggestionsDrawer) btnToggleSuggestionsDrawer.classList.remove("active");
  }
}

function toggleCodeDrawer(forceOpen = null) {
  if (!viewDesigner) return;
  const isHidden = viewDesigner.classList.contains("hidden");
  const shouldOpen = forceOpen !== null ? forceOpen : isHidden;
  if (shouldOpen) {
    viewBrainstorm.classList.remove("hidden");
    if (viewAssets) viewAssets.classList.add("hidden");
    viewDesigner.classList.remove("hidden");
    if (btnToggleCodeDrawer) btnToggleCodeDrawer.classList.add("active");
    if (btnModeDesigner) btnModeDesigner.classList.add("active");
    if (btnModeBrainstorm) btnModeBrainstorm.classList.remove("active");
    if (btnModeAssets) btnModeAssets.classList.remove("active");
    currentMode = "designer";

    if (activeApp && (!fileSelect.options || fileSelect.options.length <= 1)) {
      loadFileTree(activeApp.slug);
    }
    updateDesignerTaskPicker();
  } else {
    viewDesigner.classList.add("hidden");
    if (btnToggleCodeDrawer) btnToggleCodeDrawer.classList.remove("active");
    if (btnModeDesigner) btnModeDesigner.classList.remove("active");
    if (!viewAssets || viewAssets.classList.contains("hidden")) {
      if (btnModeBrainstorm) btnModeBrainstorm.classList.add("active");
      currentMode = "brainstorm";
    }
  }
}

function ensureStudioChatVisible() {
  if (viewAssets && !viewAssets.classList.contains("hidden")) {
    viewAssets.classList.add("hidden");
  }
  if (viewBrainstorm) {
    viewBrainstorm.classList.remove("hidden");
  }
  if (btnModeAssets) btnModeAssets.classList.remove("active");
  if (viewDesigner && !viewDesigner.classList.contains("hidden")) {
    if (btnModeDesigner) btnModeDesigner.classList.add("active");
  } else {
    if (btnModeBrainstorm) btnModeBrainstorm.classList.add("active");
  }
}

function switchMode(mode) {
  currentMode = mode;
  if (mode === "brainstorm") {
    viewBrainstorm.classList.remove("hidden");
    if (viewAssets) viewAssets.classList.add("hidden");
    toggleCodeDrawer(false);
    btnModeBrainstorm.classList.add("active");
    btnModeDesigner.classList.remove("active");
    if (btnModeAssets) btnModeAssets.classList.remove("active");
  } else if (mode === "designer") {
    viewBrainstorm.classList.remove("hidden");
    if (viewAssets) viewAssets.classList.add("hidden");
    // Toggle inline Code Drawer open while keeping Central Chat visible!
    const isCurrentlyOpen = !viewDesigner.classList.contains("hidden");
    toggleCodeDrawer(!isCurrentlyOpen ? true : true);
  } else if (mode === "assets") {
    if (btnModeAssets) btnModeAssets.classList.add("active");
    btnModeBrainstorm.classList.remove("active");
    btnModeDesigner.classList.remove("active");
    if (viewAssets) viewAssets.classList.remove("hidden");
    viewBrainstorm.classList.add("hidden");

    populateExtLabBrandSelect();
    if (activeApp) {
      loadAppImages(activeApp.slug);
    }
  }
}

function switchAssetsSubTab(tab) {
  if (tab === "manager") {
    if (btnAssetsSubManager) btnAssetsSubManager.classList.add("active");
    if (btnAssetsSubLab) btnAssetsSubLab.classList.remove("active");
    if (sectionAppImages) sectionAppImages.classList.remove("hidden");
    if (sectionAssetLab) sectionAssetLab.classList.add("hidden");
  } else {
    if (btnAssetsSubLab) btnAssetsSubLab.classList.add("active");
    if (btnAssetsSubManager) btnAssetsSubManager.classList.remove("active");
    if (sectionAssetLab) sectionAssetLab.classList.remove("hidden");
    if (sectionAppImages) sectionAppImages.classList.add("hidden");
  }
}

// --- Server Connection & App Catalog ---
async function checkServerConnection() {
  try {
    const res = await fetch(`${SERVER_URL}/api/settings`, { method: "GET" });
    if (res.ok) {
      connectionStatus.className = "status-indicator status-dot-pill";
      connectionStatus.title = "Geppy's Galactic Online";
      if (connectionText) connectionText.innerText = "Geppy's Galactic Online";
    } else {
      setOfflineState();
    }
  } catch (e) {
    setOfflineState();
  }
}

function setOfflineState() {
  connectionStatus.className = "status-indicator status-dot-pill offline";
  connectionStatus.title = "Geppy's Galactic Offline";
  if (connectionText) connectionText.innerText = "Geppy's Galactic Offline";
}

// --- Central API Key Vault Handlers ---
async function checkCentralKeyStatus() {
  if (!centralKeyLabel) return;
  try {
    const res = await fetch(`${SERVER_URL}/api/keys/status`);
    if (res.ok) {
      const data = await res.json();
      if (data.configured) {
        if (btnCentralKeyVault) {
          btnCentralKeyVault.className = "key-vault-badge status-dot-pill active";
          btnCentralKeyVault.title = `Gemini 2.5 Active (${data.masked_key}) — Click for Central Key Vault options`;
        }
        centralKeyLabel.innerText = "Gemini 2.5 Active";
        if (vaultStatusBadge) {
          vaultStatusBadge.className = "git-badge clean";
          vaultStatusBadge.innerText = "Connected";
        }
        if (vaultMaskedKey) vaultMaskedKey.innerText = data.masked_key || "Configured";
        if (vaultActiveModel) vaultActiveModel.innerText = data.active_model || "gemini-2.5-flash";
      } else {
        if (btnCentralKeyVault) {
          btnCentralKeyVault.className = "key-vault-badge status-dot-pill missing";
          btnCentralKeyVault.title = "Key Missing — No Gemini API Key found in Central Vault (Click to configure)";
        }
        centralKeyLabel.innerText = "Key Missing";
        if (vaultStatusBadge) {
          vaultStatusBadge.className = "git-badge dirty";
          vaultStatusBadge.innerText = "Missing";
        }
        if (vaultMaskedKey) vaultMaskedKey.innerText = "None (Configure in Settings)";
      }
    }
  } catch (err) {
    if (btnCentralKeyVault) {
      btnCentralKeyVault.className = "key-vault-badge status-dot-pill missing";
      btnCentralKeyVault.title = "Gemini Key Vault Offline";
    }
    if (centralKeyLabel) centralKeyLabel.innerText = "Key: Offline";
  }
}

async function checkAntigravityStatus() {
  if (!btnAntigravityStatus) return;
  try {
    const res = await fetchAntigravityApi("/api/extension/antigravity/status");
    if (res.ok) {
      const data = await res.json();
      if (data.sdk_available) {
        btnAntigravityStatus.className = "key-vault-badge status-dot-pill active";
        btnAntigravityStatus.style.borderColor = "rgba(139, 92, 246, 0.6)";
        btnAntigravityStatus.style.color = "#c4b5fd";
        const portBadge = data.service_port ? `:${data.service_port}` : ":8001";
        const warmCount = data.warm_session_count || 0;
        const speedInfo = data.last_turn_ms ? ` • Last turn: ${data.last_turn_ms}ms` : "";
        btnAntigravityStatus.title = `Antigravity Service (${portBadge}) • ${warmCount} Warm Session(s) Active${speedInfo} — Click to open active app in Antigravity IDE`;
      } else {
        btnAntigravityStatus.className = "key-vault-badge status-dot-pill missing";
        btnAntigravityStatus.title = "Antigravity SDK not loaded — Click to open active app in Antigravity IDE";
      }
    }
  } catch (e) {
    // Keep default badge if server is still booting
  }
}

async function prewarmAntigravityForApp(app) {
  if (!app || !app.slug) return;
  try {
    await fetchAntigravityApi("/api/extension/antigravity/warm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: app.slug,
        name: app.name || app.slug,
        local_path: app.local_path || ""
      })
    });
    setTimeout(() => checkAntigravityStatus(), 700);
  } catch (e) {}
}

async function openActiveAppInAntigravityIde(targetFileOverride = null) {
  const slug = activeApp ? activeApp.slug : (appSelect ? appSelect.value : "");
  if (!slug) {
    alert("Please select an application first to open in Antigravity IDE.");
    return;
  }
  const fileToOpen = targetFileOverride || activeFilePath || null;
  if (btnAntigravityStatus) {
    btnAntigravityStatus.style.opacity = "0.6";
  }
  try {
    const res = await fetch(`${SERVER_URL}/api/extension/antigravity/open-ide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: slug,
        file_path: fileToOpen
      })
    });
    const data = await res.json();
    if (!res.ok || data.status === "error") {
      alert(data.detail || data.message || "Could not launch Antigravity IDE.");
    }
  } catch (e) {
    alert(`Error launching Antigravity IDE: ${e}`);
  } finally {
    if (btnAntigravityStatus) {
      btnAntigravityStatus.style.opacity = "1";
    }
  }
}

function openKeyModal() {
  if (!centralKeyModal) return;
  if (vaultActionFeedback) vaultActionFeedback.classList.add("hidden");
  centralKeyModal.classList.remove("hidden");
  checkCentralKeyStatus();
}

function closeKeyModal() {
  if (centralKeyModal) centralKeyModal.classList.add("hidden");
}

async function testCentralGeminiKey() {
  if (!btnTestGeminiKey || !vaultActionFeedback) return;
  btnTestGeminiKey.disabled = true;
  btnTestGeminiKey.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Testing...';
  vaultActionFeedback.className = "commit-feedback";
  vaultActionFeedback.classList.remove("hidden");
  vaultActionFeedback.innerText = "Pinging Google Gemini API through GitBridge Central Vault...";

  try {
    const res = await fetch(`${SERVER_URL}/api/keys/test`, { method: "POST" });
    const data = await res.json();
    if (data.success) {
      vaultActionFeedback.className = "commit-feedback success";
      vaultActionFeedback.innerHTML = `<i class="fa-solid fa-circle-check"></i> <strong>Success!</strong> Connected in ${data.latency_ms}ms via <code>${data.model}</code>. Central key is active and responding.`;
    } else {
      vaultActionFeedback.className = "commit-feedback error";
      vaultActionFeedback.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <strong>Test Failed:</strong> ${data.message || "Could not reach Gemini."}`;
    }
  } catch (err) {
    vaultActionFeedback.className = "commit-feedback error";
    vaultActionFeedback.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Error connecting to GitBridge: ${err}`;
  } finally {
    btnTestGeminiKey.disabled = false;
    btnTestGeminiKey.innerHTML = '<i class="fa-solid fa-bolt" style="color: #fbbf24;"></i> Test API Connection';
    checkCentralKeyStatus();
  }
}

async function syncCentralKeyToApps() {
  if (!btnSyncAllAppsKey || !vaultActionFeedback) return;
  btnSyncAllAppsKey.disabled = true;
  btnSyncAllAppsKey.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Syncing...';
  vaultActionFeedback.className = "commit-feedback";
  vaultActionFeedback.classList.remove("hidden");
  vaultActionFeedback.innerText = "Synchronizing .env files across all workspace applications...";

  try {
    const res = await fetch(`${SERVER_URL}/api/keys/sync-all-apps`, { method: "POST" });
    const data = await res.json();
    if (data.success) {
      vaultActionFeedback.className = "commit-feedback success";
      vaultActionFeedback.innerHTML = `<i class="fa-solid fa-circle-check"></i> <strong>Synced!</strong> Propagated central key to <strong>${data.apps_updated} apps</strong> in workspace.`;
    } else {
      vaultActionFeedback.className = "commit-feedback error";
      vaultActionFeedback.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Sync failed: ${data.message}`;
    }
  } catch (err) {
    vaultActionFeedback.className = "commit-feedback error";
    vaultActionFeedback.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Error syncing: ${err}`;
  } finally {
    btnSyncAllAppsKey.disabled = false;
    btnSyncAllAppsKey.innerHTML = '<i class="fa-solid fa-arrows-rotate" style="color: #34d399;"></i> Sync to All Apps';
  }
}

// --- App Registration & Deep Analysis Modal ---
function openRegisterModal(prefillData = null) {
  if (!modalRegisterApp) return;
  modalRegisterApp.classList.remove("hidden");
  if (regActionFeedback) {
    regActionFeedback.className = "commit-feedback hidden";
    regActionFeedback.innerHTML = "";
  }

  const data = prefillData || lastDetectedUnrecognized;
  if (data) {
    if (regAppName) regAppName.value = data.suggested_name || "";
    if (regAppUrl) regAppUrl.value = data.url || "";
  } else {
    if (regAppName) regAppName.value = "";
    if (regAppUrl) regAppUrl.value = "";
  }

  if (regModeWorkspace) regModeWorkspace.checked = true;
  if (regAppCustomPath) {
    regAppCustomPath.value = "";
    regAppCustomPath.classList.add("hidden");
  }
  if (regAppName) regAppName.focus();
}

function closeRegisterModal() {
  if (modalRegisterApp) modalRegisterApp.classList.add("hidden");
  if (regActionFeedback) {
    regActionFeedback.className = "commit-feedback hidden";
    regActionFeedback.innerHTML = "";
  }
}

async function submitRegisterApp() {
  const name = regAppName ? regAppName.value.trim() : "";
  const liveUrl = regAppUrl ? regAppUrl.value.trim() : "";
  const isCustomPath = regModeCustom ? regModeCustom.checked : false;
  const customPath = regAppCustomPath ? regAppCustomPath.value.trim() : "";
  const runDeepAnalysis = regRunDeepAnalysis ? regRunDeepAnalysis.checked : true;

  if (!name) {
    regActionFeedback.className = "commit-feedback error";
    regActionFeedback.innerHTML = "Please enter an application name.";
    return;
  }

  if (isCustomPath && !customPath) {
    regActionFeedback.className = "commit-feedback error";
    regActionFeedback.innerHTML = "Please enter the folder path on your PC.";
    return;
  }

  btnSubmitRegisterApp.disabled = true;
  btnSubmitRegisterApp.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Registering &amp; Analyzing...';
  regActionFeedback.className = "commit-feedback warning";
  regActionFeedback.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Analyzing code architecture, generating HELP.md guide &amp; injecting Gemini key...';

  try {
    const res = await fetch(`${SERVER_URL}/api/extension/register-app`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name,
        live_url: liveUrl,
        custom_path: isCustomPath ? customPath : null,
        run_deep_analysis: runDeepAnalysis
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      regActionFeedback.className = "commit-feedback success";
      regActionFeedback.innerHTML = `
        <div style="font-weight: 700; margin-bottom: 2px;">
          <i class="fa-solid fa-circle-check"></i> Registered "${escapeHtml(data.app.name)}"!
        </div>
        <div style="font-size: 10.5px; opacity: 0.95;">
          📁 <code>${escapeHtml(data.app.local_path)}</code><br>
          ${data.help_file_created ? "✨ Created comprehensive <strong>HELP.md</strong> user guide!<br>" : ""}
          🔑 Injected Central Gemini API key.
        </div>
      `;

      // Reload app list and switch to the newly registered app
      await loadApps();
      const newApp = apps.find((a) => a.slug === data.app.slug) || data.app;
      await setActiveApp(newApp);

      if (unrecognizedAppBar) unrecognizedAppBar.classList.add("hidden");
      lastDetectedUnrecognized = null;

      setTimeout(() => {
        closeRegisterModal();
      }, 1800);
    } else {
      regActionFeedback.className = "commit-feedback error";
      regActionFeedback.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> ${escapeHtml(data.detail || data.message || "Registration failed")}`;
    }
  } catch (e) {
    regActionFeedback.className = "commit-feedback error";
    regActionFeedback.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> ${escapeHtml(String(e))}`;
  } finally {
    btnSubmitRegisterApp.disabled = false;
    btnSubmitRegisterApp.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> <span>Register &amp; Analyze</span>';
  }
}

// --- SOT Contextiles Engine ---
async function loadContextiles() {
  try {
    const res = await fetch(`${SERVER_URL}/api/sot/contextiles`);
    if (res.ok) {
      contextiles = await res.json();
      renderSOTChips();
      populateExtLabBrandSelect();
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

  if (sotQuickbarCount) {
    sotQuickbarCount.innerText = contextiles ? contextiles.length : 0;
  }
  if (modalSotCountBadge) {
    modalSotCountBadge.innerText = `${contextiles ? contextiles.length : 0} Active SOTs`;
  }

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
      toggleChatContextDrawer(false);
    });
    container.appendChild(chip);
  });

  // Trailing "View All..." button in quickbar
  const viewAllChip = document.createElement("button");
  viewAllChip.className = "sot-chip";
  viewAllChip.style.background = "rgba(99, 102, 241, 0.2)";
  viewAllChip.style.borderColor = "rgba(99, 102, 241, 0.4)";
  viewAllChip.style.color = "#c7d2fe";
  viewAllChip.innerHTML = '<i class="fa-solid fa-list-ul"></i> View All...';
  viewAllChip.addEventListener("click", () => {
    toggleChatContextDrawer(false);
    openSotFleetModal();
  });
  container.appendChild(viewAllChip);
}

// --- SOT Fleet Big List Modal Logic ---
function openSotFleetModal() {
  if (!modalSotFleet) return;
  modalSotFleet.classList.remove("hidden");
  modalSotFleet.style.display = "flex";
  currentSotFilter = "all";
  if (sotSearchInput) {
    sotSearchInput.value = "";
    setTimeout(() => sotSearchInput.focus(), 100);
  }
  document.querySelectorAll(".sot-arch-pill").forEach((p) => {
    p.classList.toggle("active", (p.dataset.archetype || "all") === "all");
  });
  renderSotFleetList("all", "");
}

function closeSotFleetModal() {
  if (!modalSotFleet) return;
  modalSotFleet.classList.add("hidden");
  modalSotFleet.style.display = "none";
}

function renderSotFleetList(filterArchetype = "all", searchQuery = "") {
  if (!sotFleetCardsList) return;
  sotFleetCardsList.innerHTML = "";

  if (!contextiles || contextiles.length === 0) {
    sotFleetCardsList.innerHTML = '<div style="color: #64748b; font-size: 11px; text-align: center; padding: 24px 0;">No Sources of Truth found. Create your first context style!</div>';
    return;
  }

  // Update counts on filter pills
  const counts = {
    all: contextiles.length,
    character: contextiles.filter((c) => c.archetype === "character").length,
    style: contextiles.filter((c) => c.archetype === "style").length,
    icon_set: contextiles.filter((c) => c.archetype === "icon_set").length,
    brand_asset: contextiles.filter((c) => c.archetype === "brand_asset").length,
    ui_component: contextiles.filter((c) => c.archetype === "ui_component").length,
    output: contextiles.filter((c) => ["output", "output_spec"].includes(c.archetype)).length
  };

  const setElCount = (id, count) => {
    const el = document.getElementById(id);
    if (el) el.innerText = count;
  };
  setElCount("sot-filter-all-count", counts.all);
  setElCount("sot-filter-char-count", counts.character);
  setElCount("sot-filter-style-count", counts.style);
  setElCount("sot-filter-icon-count", counts.icon_set);
  setElCount("sot-filter-brand-count", counts.brand_asset);
  setElCount("sot-filter-ui-count", counts.ui_component);
  setElCount("sot-filter-output-count", counts.output);

  if (modalSotCountBadge) {
    modalSotCountBadge.innerText = `${counts.all} Active SOTs`;
  }

  const query = searchQuery.trim().toLowerCase();
  const filtered = contextiles.filter((c) => {
    const matchesArch = filterArchetype === "all" ||
      (filterArchetype === "output" ? ["output", "output_spec"].includes(c.archetype) : c.archetype === filterArchetype);
    if (!matchesArch) return false;

    if (!query) return true;
    const matchName = (c.name || "").toLowerCase().includes(query);
    const matchTitle = (c.title || "").toLowerCase().includes(query);
    const matchDesc = (c.description || c.reference_text || "").toLowerCase().includes(query);
    const matchTags = (c.tags || []).some((t) => t.toLowerCase().includes(query));
    return matchName || matchTitle || matchDesc || matchTags;
  });

  if (filtered.length === 0) {
    sotFleetCardsList.innerHTML = `<div style="color: #64748b; font-size: 11px; text-align: center; padding: 24px 0;">No matching Sources of Truth found for "${escapeHtml(searchQuery)}"</div>`;
    return;
  }

  const archIcons = {
    character: "👤 Character",
    icon_set: "🔶 App Icon Set",
    style: "🎨 Visual Style",
    ui_component: "🧩 UI Component",
    brand_asset: "🏷️ Brand Asset",
    output: "✨ Output Spec",
    output_spec: "✨ Output Spec",
    general: "✨ General SOT"
  };

  filtered.forEach((c) => {
    const card = document.createElement("div");
    card.className = "sot-fleet-card";

    const imgUrl = c.primary_image_url || c.reference_image_url || ((c.gallery_images && c.gallery_images[0]) || null);
    const thumbHtml = imgUrl
      ? `<img src="${SERVER_URL}${imgUrl}?t=${Date.now()}" class="sot-card-thumb" alt="${escapeHtml(c.name)}" />`
      : `<div class="sot-card-thumb-placeholder">${(archIcons[c.archetype] || "✨").split(" ")[0]}</div>`;

    const tagChips = (c.tags || []).slice(0, 5).map((t) => `<span class="sot-card-tag">${escapeHtml(t)}</span>`).join("");
    const archLabel = archIcons[c.archetype] || "✨ SOT Standard";

    card.innerHTML = `
      <div class="sot-card-header">
        ${thumbHtml}
        <div class="sot-card-meta">
          <div class="sot-card-title-row">
            <span class="sot-card-handle">@${escapeHtml(c.name)}</span>
            <span class="sot-card-tag" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border-color: rgba(56, 189, 248, 0.3); font-weight: 600;">${archLabel}</span>
          </div>
          <div class="sot-card-title">${escapeHtml(c.title || c.name)}</div>
          <div class="sot-card-desc">${escapeHtml(c.description || c.reference_text || c.assembled_prompt || "Ground-truth standard")}</div>
          ${tagChips ? `<div class="sot-card-tags">${tagChips}</div>` : ""}
        </div>
      </div>
      <div class="sot-card-actions">
        <button class="btn-sot-action primary btn-card-insert" title="Insert @${escapeHtml(c.name)} into prompt">
          <i class="fa-solid fa-at"></i> Insert @handle
        </button>
        <button class="btn-sot-action btn-card-lab" title="Load into Asset Lab Synthesizer">
          <i class="fa-solid fa-flask text-amber"></i> Use in Asset Lab
        </button>
        <button class="btn-sot-action btn-card-copy" title="Copy prompt instructions">
          <i class="fa-regular fa-copy"></i> Copy Prompt
        </button>
      </div>
    `;

    // Action: Insert @handle
    card.querySelector(".btn-card-insert").addEventListener("click", () => {
      insertContextileMention(`@${c.name}`);
      closeSotFleetModal();
    });

    // Action: Use in Asset Lab
    card.querySelector(".btn-card-lab").addEventListener("click", () => {
      switchMode("assets");
      closeSotFleetModal();
      if (["character", "brand_asset"].includes(c.archetype)) {
        if (extLabBrandSelect) extLabBrandSelect.value = c.name;
      } else if (["output", "output_spec"].includes(c.archetype)) {
        if (extLabOutputPreset) extLabOutputPreset.value = c.name;
      } else {
        if (extLabStyleContextile) {
          extLabStyleContextile.value = c.name;
          onStyleContextileChanged();
        }
      }
    });

    // Action: Copy prompt
    card.querySelector(".btn-card-copy").addEventListener("click", (e) => {
      const textToCopy = c.assembled_prompt || c.reference_text || `@${c.name}: ${c.title || ""}`;
      navigator.clipboard.writeText(textToCopy);
      const btn = e.currentTarget;
      const origHtml = btn.innerHTML;
      btn.innerHTML = '<i class="fa-solid fa-check text-emerald-400"></i> Copied!';
      setTimeout(() => { btn.innerHTML = origHtml; }, 1500);
    });

    sotFleetCardsList.appendChild(card);
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

// --- Active Tab App Detection, Off-Target Page Indicator & Instance Tracking ---
let tabAppMap = {};   // tabId -> appSlug
let hostAppMap = {};  // hostname:port -> appSlug

function doesUrlMatchApp(url, app) {
  if (!url || !app) return false;
  try {
    const parsedTab = new URL(url);
    if (parsedTab.protocol === "chrome-extension:") return true;
    const isLocal = ["localhost", "127.0.0.1", "0.0.0.0"].includes(parsedTab.hostname);
    const tabPort = parsedTab.port || (parsedTab.protocol === "https:" ? "443" : "80");

    // 1. Control plane (Geppy's GitBridge) runs on port 8000
    if (isGitBridgeApp(app)) {
      if (isLocal && String(tabPort) === "8000") return true;
    }

    // 2. Check live_url host or localhost port match
    if (app.live_url) {
      try {
        const parsedLive = new URL(app.live_url);
        const liveIsLocal = ["localhost", "127.0.0.1", "0.0.0.0"].includes(parsedLive.hostname);
        const livePort = parsedLive.port || (parsedLive.protocol === "https:" ? "443" : "80");
        if (parsedTab.host === parsedLive.host) return true;
        if (isLocal && liveIsLocal && String(tabPort) === String(livePort)) return true;
      } catch (e) {}
    }

    // 3. Check known hostAppMap or backend-detected app for current tab
    if (parsedTab.host && hostAppMap[parsedTab.host] === app.slug) return true;
    if (currentTabDetectedApp && currentTabDetectedApp.slug === app.slug) return true;

    // 4. Check GitHub repo URL match
    if (app.github_url && url.toLowerCase().startsWith(app.github_url.toLowerCase())) return true;
  } catch (e) {}
  return false;
}

function formatTabShortLabel(url) {
  if (!url) return "another tab";
  try {
    const u = new URL(url);
    if (u.protocol === "chrome:" || u.protocol === "edge:" || u.protocol === "about:") {
      return "Browser Page";
    }
    const isLocal = ["localhost", "127.0.0.1", "0.0.0.0"].includes(u.hostname);
    if (isLocal) {
      const port = u.port || "80";
      if (String(port) === "8000") return "GitBridge (:8000)";
      if (currentTabDetectedApp && currentTabDetectedApp.name) {
        return `${currentTabDetectedApp.name} (:${port})`;
      }
      return `localhost:${port}`;
    }
    return u.hostname.replace(/^www\./, "");
  } catch (e) {
    return "another tab";
  }
}

function updatePageMatchIndicator() {
  if (!offTargetPageBanner) return;
  if (!activeApp || !currentBrowserTabUrl) {
    offTargetPageBanner.classList.add("hidden");
    document.body.classList.remove("page-mismatch-dimmed");
    return;
  }

  try {
    const u = new URL(currentBrowserTabUrl);
    if (u.protocol === "chrome-extension:") {
      offTargetPageBanner.classList.add("hidden");
      document.body.classList.remove("page-mismatch-dimmed");
      return;
    }
  } catch (e) {}

  const matched = doesUrlMatchApp(currentBrowserTabUrl, activeApp);
  if (matched) {
    offTargetPageBanner.classList.add("hidden");
    document.body.classList.remove("page-mismatch-dimmed");
    return;
  }

  // Browser tab is NOT on the app currently selected in Galactic!
  offTargetPageBanner.classList.remove("hidden");
  document.body.classList.add("page-mismatch-dimmed");

  const tabLabel = formatTabShortLabel(currentBrowserTabUrl);
  if (offTargetPageText) {
    offTargetPageText.innerHTML = `Viewing <strong>${escapeHtml(tabLabel)}</strong> • Editing <strong>${escapeHtml(activeApp.name)}</strong>`;
  }

  if (btnOffTargetOpenLabel) {
    if (isGitBridgeApp(activeApp)) {
      btnOffTargetOpenLabel.innerText = "Go to GitBridge (:8000)";
    } else if (activeApp.is_live && activeApp.live_url) {
      let portStr = "";
      try {
        const p = new URL(activeApp.live_url).port;
        if (p) portStr = ` (:${p})`;
      } catch (e) {}
      btnOffTargetOpenLabel.innerText = `Go to ${activeApp.name}${portStr}`;
    } else {
      btnOffTargetOpenLabel.innerText = `Launch ${activeApp.name}`;
    }
  }

  if (btnOffTargetSwitchApp && btnOffTargetSwitchLabel) {
    if (currentTabDetectedApp && currentTabDetectedApp.slug && currentTabDetectedApp.slug !== activeApp.slug) {
      btnOffTargetSwitchLabel.innerText = `Edit ${currentTabDetectedApp.name}`;
      btnOffTargetSwitchApp.classList.remove("hidden");
    } else {
      btnOffTargetSwitchApp.classList.add("hidden");
    }
  }
}

async function detectActiveTabApp(options = { autoSwitchApp: true }) {
  if (typeof chrome === "undefined" || !chrome.tabs) return;

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.url) {
      activeTabId = tab.id;
      currentBrowserTabUrl = tab.url;
      await detectAppFromUrl(tab.url, tab.id, options);
    }
  } catch (e) {
    console.warn("Could not query active tab:", e);
  }
}

async function detectAppFromUrl(url, explicitTabId = null, options = { autoSwitchApp: true }) {
  if (!url) return;
  const autoSwitch = options && typeof options.autoSwitchApp === "boolean" ? options.autoSwitchApp : true;
  const currentTabId = explicitTabId || activeTabId;
  if (currentTabId) activeTabId = currentTabId;
  currentBrowserTabUrl = url;

  let parsedHost = null;
  let parsedPort = null;
  let isLocal = false;
  try {
    const parsedTab = new URL(url);
    parsedHost = parsedTab.host;
    parsedPort = parsedTab.port;
    isLocal = ["localhost", "127.0.0.1", "0.0.0.0"].includes(parsedTab.hostname);
  } catch (e) {}

  // Fast check: Port 8000 is always Geppy's GitBridge
  if (isLocal && String(parsedPort) === "8000") {
    const gbApp = (apps || []).find((a) => isGitBridgeApp(a));
    if (gbApp) {
      currentTabDetectedApp = gbApp;
      if (unrecognizedAppBar) unrecognizedAppBar.classList.add("hidden");
      lastDetectedUnrecognized = null;
      if (currentTabId) tabAppMap[currentTabId] = gbApp.slug;
      if (parsedHost) hostAppMap[parsedHost] = gbApp.slug;
      if (autoSwitch || !activeApp) {
        await setActiveApp(gbApp);
      } else {
        updatePageMatchIndicator();
      }
      return;
    }
  }

  // 1. Check if host was already mapped to a specific app
  if (parsedHost && hostAppMap[parsedHost]) {
    const mappedSlug = hostAppMap[parsedHost];
    const targetApp = (apps || []).find((a) => a.slug === mappedSlug);
    if (targetApp) {
      currentTabDetectedApp = targetApp;
      if (unrecognizedAppBar) unrecognizedAppBar.classList.add("hidden");
      lastDetectedUnrecognized = null;
      if (currentTabId) tabAppMap[currentTabId] = targetApp.slug;
      if (autoSwitch || !activeApp) {
        activeTabInstance.tabId = currentTabId;
        activeTabInstance.url = url;
        activeTabInstance.slug = targetApp.slug;
        if (!activeApp || activeApp.slug !== targetApp.slug) {
          await setActiveApp(targetApp);
        }
      }
      updatePageMatchIndicator();
      return;
    }
  }

  // 2. Does this tab URL match any loaded app's live_url?
  if (apps && apps.length > 0) {
    const liveMatchedApp = apps.find((a) => {
      if (!a.live_url) return false;
      try {
        const u = new URL(a.live_url);
        return (parsedHost && u.host === parsedHost) || (isLocal && parsedPort && u.port === parsedPort);
      } catch (e) {
        return false;
      }
    });
    if (liveMatchedApp) {
      currentTabDetectedApp = liveMatchedApp;
      if (unrecognizedAppBar) unrecognizedAppBar.classList.add("hidden");
      lastDetectedUnrecognized = null;
      if (currentTabId) tabAppMap[currentTabId] = liveMatchedApp.slug;
      if (parsedHost) hostAppMap[parsedHost] = liveMatchedApp.slug;
      if (autoSwitch || !activeApp) {
        activeTabInstance.tabId = currentTabId;
        activeTabInstance.url = url;
        activeTabInstance.slug = liveMatchedApp.slug;
        if (!activeApp || activeApp.slug !== liveMatchedApp.slug) {
          await setActiveApp(liveMatchedApp);
        }
      }
      updatePageMatchIndicator();
      return;
    }
  }

  // 3. Query backend detect-app
  try {
    const res = await fetch(`${SERVER_URL}/api/extension/detect-app?url=${encodeURIComponent(url)}`);
    if (res.ok) {
      const data = await res.json();
      if (data.matched && data.app) {
        const catalogApp = (apps || []).find((a) => a.slug === data.app.slug) || data.app;
        currentTabDetectedApp = catalogApp;
        if (unrecognizedAppBar) unrecognizedAppBar.classList.add("hidden");
        lastDetectedUnrecognized = null;
        if (currentTabId) tabAppMap[currentTabId] = catalogApp.slug;
        if (parsedHost) hostAppMap[parsedHost] = catalogApp.slug;
        if (autoSwitch || !activeApp) {
          activeTabInstance.tabId = currentTabId;
          activeTabInstance.url = url;
          activeTabInstance.slug = catalogApp.slug;
          await setActiveApp(catalogApp);
        } else {
          updatePageMatchIndicator();
        }
        return;
      } else {
        currentTabDetectedApp = null;
        if (isLocal && unrecognizedAppBar) {
          lastDetectedUnrecognized = { ...data, tabId: currentTabId, url: url };
          if (unrecognizedUrlLabel) {
            unrecognizedUrlLabel.innerText = data.port ? `localhost:${data.port}` : url;
          }

          if (activeApp && btnReassociateTab) {
            btnReassociateTab.classList.remove("hidden");
            if (reassociateBtnText) {
              reassociateBtnText.innerText = `Link to ${activeApp.name}`;
            }
          } else if (btnReassociateTab) {
            btnReassociateTab.classList.add("hidden");
          }

          unrecognizedAppBar.classList.remove("hidden");
        } else if (unrecognizedAppBar) {
          unrecognizedAppBar.classList.add("hidden");
        }
      }
    }
  } catch (e) {
    console.warn("App detection request failed:", e);
  }

  // Fallback: If no app matched and none is currently active, select first app
  if (!activeApp && apps.length > 0) {
    await setActiveApp(apps[0]);
  }
  updatePageMatchIndicator();
}

async function onAppSelected(slug) {
  if (!slug) return;
  const app = apps.find((a) => a.slug === slug);
  if (app) await setActiveApp(app);
}

async function setActiveApp(app) {
  if (isGitBridgeApp(app)) {
    app.is_live = true;
    app.live_url = app.live_url || SERVER_URL;
  }

  // If already active app and same slug, just sync instance info
  if (activeApp && activeApp.slug === app.slug) {
    if (app.live_url) {
      activeTabInstance.url = app.live_url;
      try {
        const u = new URL(app.live_url);
        activeTabInstance.port = u.port || "80";
        hostAppMap[u.host] = app.slug;
      } catch (e) {}
    }
    if (activeTabId && doesUrlMatchApp(currentBrowserTabUrl, app)) {
      tabAppMap[activeTabId] = app.slug;
    }
    updatePageMatchIndicator();
    return;
  }

  // 1. If switching away from another app, save its chat history first (non-blocking)
  if (activeApp && activeApp.slug) {
    saveAppChatHistory(activeApp.slug, chatHistory);
  }

  activeApp = app;
  appSelect.value = app.slug;

  // Track active app instance & mappings without falsely overwriting tabAppMap for unrelated tabs
  activeTabInstance.slug = app.slug;
  if (app.live_url) {
    activeTabInstance.url = app.live_url;
    try {
      const u = new URL(app.live_url);
      activeTabInstance.port = u.port || "80";
      hostAppMap[u.host] = app.slug;
    } catch (e) {}
  }
  if (activeTabId && doesUrlMatchApp(currentBrowserTabUrl, app)) {
    tabAppMap[activeTabId] = app.slug;
  }

  // Update reassociate button if unrecognized bar is open
  if (lastDetectedUnrecognized && btnReassociateTab) {
    btnReassociateTab.classList.remove("hidden");
    if (reassociateBtnText) reassociateBtnText.innerText = `Link to ${app.name}`;
  }

  if (app.is_live) {
    appLiveBadge.style.display = "inline-block";
    appLiveBadge.innerText = app.live_url ? `Live (${new URL(app.live_url).port || "80"})` : "Live";
    if (btnStopApp) {
      btnStopApp.style.display = isGitBridgeApp(app) ? "none" : "inline-flex";
    }
  } else {
    appLiveBadge.style.display = "none";
    if (btnStopApp) btnStopApp.style.display = "none";
  }

  updatePageMatchIndicator();
  refreshRunningServersState();
  prewarmAntigravityForApp(app);

  // 2. Load Session Changelog & Watchdog Error Log immediately from localStorage
  loadSessionLog(app.slug);
  if (typeof loadWatchdogLog === "function") {
    loadWatchdogLog(app.slug);
  }

  // 3. Reset & load Backlog FIRST so activeApp's saved tasks are authoritative before Chat History renders
  backlogTasks = [];
  selectedTaskIds.clear();
  renderBacklog();
  await loadBacklog(app.slug);

  await Promise.allSettled([
    loadAppChatHistory(app.slug),
    loadFileTree(app.slug),
    refreshGitStatus()
  ]);

  // 4. If in Asset Lab mode, load app images
  if (currentMode === "assets") {
    loadAppImages(app.slug);
  }
}

// --- Per-App Chat History Isolation & Management ---
async function loadAppChatHistory(slug) {
  if (!slug) return;
  chatHistory = [];

  // 1. Instant local cache load
  try {
    const raw = localStorage.getItem(`galactic_chat_${slug}`);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        chatHistory = parsed;
      }
    }
  } catch (e) {
    console.warn("Could not read local chat history cache:", e);
  }

  // Render immediately with local cache
  renderChatHistoryForActiveApp();

  // 2. Fetch fresh chat from server DB
  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${slug}/chat`);
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data.chat_history) && data.chat_history.length > 0) {
        if (data.chat_history.length >= chatHistory.length) {
          chatHistory = data.chat_history;
          try {
            localStorage.setItem(`galactic_chat_${slug}`, JSON.stringify(chatHistory));
          } catch (e) {}
          renderChatHistoryForActiveApp();
        }
      }
    }
  } catch (e) {
    console.warn("Could not fetch remote chat history:", e);
  }
}

async function saveAppChatHistory(slug, history) {
  if (!slug || !Array.isArray(history)) return;
  try {
    localStorage.setItem(`galactic_chat_${slug}`, JSON.stringify(history));
    await fetch(`${SERVER_URL}/api/apps/${slug}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_history: history })
    });
  } catch (e) {
    console.warn("Could not persist chat history:", e);
  }
}

function isGitBridgeApp(app = activeApp) {
  if (!app) return false;
  const s = (app.slug || "").toLowerCase();
  const n = (app.name || "").toLowerCase();
  return s === "geppys-gitbridge" || s === "gitbridge" || n.includes("gitbridge");
}

function getGeppyName(app = activeApp) {
  return isGitBridgeApp(app) ? "Captain Geppy" : "Geppy";
}

function getGeppyTitle(app = activeApp) {
  return isGitBridgeApp(app) ? "Galactic Commander" : "AI App Co-Pilot";
}

function renderChatHistoryForActiveApp() {
  if (!chatHistoryEl) return;
  chatHistoryEl.innerHTML = "";

  const appName = activeApp ? activeApp.name : "Active Application";
  const isGb = isGitBridgeApp(activeApp);
  const gName = getGeppyName(activeApp);
  const gTitle = getGeppyTitle(activeApp);

  if (brainstormInput && !isChatImageMode) {
    brainstormInput.placeholder = `Ask ${gName} or type /image to generate visuals...`;
  }

  // Welcome Banner personalized for this app (Captain Geppy only in GitBridge; Geppy everywhere else)
  const welcomeBubble = document.createElement("div");
  welcomeBubble.className = "chat-bubble ai";
  welcomeBubble.innerHTML = `
    <div class="captain-badge">
      <span class="captain-avatar"><img src="icons/icon48.png" alt="${escapeHtml(gName)}" class="captain-avatar-img" /></span>
      <div>
        <strong style="color: #818cf8;">${escapeHtml(gName)}</strong>
        <span class="captain-sub">${escapeHtml(gTitle)} &bull; ${escapeHtml(appName)}</span>
      </div>
    </div>
    <div class="ai-body">
      ${isGb
        ? `<p>Greetings, Commander! Welcome aboard <strong>Geppy's GitBridge</strong>.</p>
           <p>I am <strong>Captain Geppy</strong>, your commander for <em>${escapeHtml(appName)}</em>. Click the ideation pills above or ask me for visual makeovers, UX polish, and killer features!</p>`
        : `<p>Hey there! Ready to build and polish <strong>${escapeHtml(appName)}</strong>.</p>
           <p>I'm <strong>Geppy</strong>, your AI co-pilot for <em>${escapeHtml(appName)}</em>. Click the ideation pills above or ask me for visual makeovers, bug fixes, UX polish, and features tailored specifically to this app!</p>`
      }
      <p>✨ <strong>Source of Truth:</strong> Click <strong>SOT Fleet</strong> above or type <code>@contextile_name</code> to anchor ideas in your saved standards.</p>
    </div>
  `;
  chatHistoryEl.appendChild(welcomeBubble);

  // Collect all completion messages so we know which tasks were already applied in chat history
  const completedTextCorpus = chatHistory
    .filter((m) => m && m.sender === "ai" && /Finished updating|Successfully applied|Applied targeted patch/i.test(m.text || ""))
    .map((m) => (m.text || "").toLowerCase())
    .join("\n");

  // Render each conversation turn for this app without overwriting the authoritative backlogTasks
  chatHistory.forEach((msg) => {
    const sysOpt = { isSystemTriggered: Boolean(msg.isSystemTriggered) };
    if (msg.sender === "user") {
      appendChatBubble("user", escapeHtml(msg.text), sysOpt);
    } else {
      const rawText = msg.text || "";
      const isCompletionTurn = /Finished updating|Could not finish updating|Successfully applied|Applied targeted patch/i.test(rawText);
      const parsedFromText = isCompletionTurn ? { cleanText: rawText, tasks: [] } : extractAndStripEmbeddedTasks(rawText);
      const displayMarkdown = parsedFromText.cleanText || rawText;
      const bubble = appendChatBubble("ai", formatMarkdown(displayMarkdown), sysOpt);
      if (Array.isArray(msg.tool_steps) && msg.tool_steps.length > 0) {
        attachAntigravityToolTraceToBubble(bubble, msg.tool_steps, msg.engine || "antigravity_sdk", msg.modified_files || []);
      }
      const seriesTasks = isCompletionTurn
        ? []
        : msg.extracted_tasks && msg.extracted_tasks.length > 0
        ? msg.extracted_tasks
        : parsedFromText.tasks.length > 0
        ? parsedFromText.tasks
        : extractActionSeriesFromText(displayMarkdown);

      if (seriesTasks && seriesTasks.length > 0) {
        const objTitle = msg.objective_title || deriveObjectiveTitle(seriesTasks, displayMarkdown);
        const fallbackObjId = `obj-hist-${msg.timestamp || Date.now()}`;
        seriesTasks.forEach((t, idx) => {
          if (!t.id) t.id = `task-hist-${msg.timestamp || Date.now()}-${idx}`;
          if (!t.objective_id) t.objective_id = fallbackObjId;
          if (!t.objective_title) t.objective_title = objTitle;
          const matchingSaved = backlogTasks.find(
            (bt) => bt.id === t.id || (bt.title && t.title && bt.title.toLowerCase() === t.title.toLowerCase())
          );
          if (matchingSaved) {
            t.completed = Boolean(matchingSaved.completed);
          } else if (t.title && completedTextCorpus.includes(t.title.toLowerCase())) {
            t.completed = true;
          }
        });
        msg.extracted_tasks = seriesTasks;
        msg.text = displayMarkdown;
        attachIdeasDockToBubble(bubble, seriesTasks, objTitle);
      }
      if (msg.image_data) {
        attachImageCardToBubble(bubble, msg.image_data);
      }
    }
  });

  chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
}

function deriveObjectiveTitle(tasks = [], contextText = "") {
  if (!tasks || tasks.length === 0) return "Implementation Objective";
  const fromTask = tasks.find((t) => t && t.objective_title)?.objective_title;
  if (fromTask) return fromTask;

  if (contextText && typeof contextText === "string") {
    const headingMatch = contextText.match(/(?:^|\n)#{1,3}\s+([^\n]+)/);
    if (headingMatch && headingMatch[1]) {
      const cleanHeading = headingMatch[1].replace(/[*`_~]/g, "").trim();
      if (cleanHeading.length >= 4 && cleanHeading.length <= 72) {
        return cleanHeading;
      }
    }
    if (/Watchdog|runtime error|UI freeze/i.test(contextText)) {
      return `Watchdog Diagnostic & Fix Plan`;
    }
  }

  if (tasks.length === 1) {
    return tasks[0].title || "Implementation Task";
  }
  return `${tasks[0].title || "Action Plan"} (+${tasks.length - 1} step${tasks.length - 1 === 1 ? "" : "s"})`;
}

function extractAndStripEmbeddedTasks(text = "") {
  if (!text || typeof text !== "string") {
    return { cleanText: "", tasks: [] };
  }
  const fenceRegex = /```(?:tasks|json)?\s*(\[\s*\{[\s\S]*?\}\s*\])\s*```/i;
  const match = fenceRegex.exec(text);
  if (match && match[1]) {
    try {
      const parsed = JSON.parse(match[1]);
      if (
        Array.isArray(parsed) &&
        parsed.some((item) => item && typeof item === "object" && (item.title || item.suggested_prompt))
      ) {
        const cleanText = (text.slice(0, match.index) + text.slice(match.index + match[0].length)).trim();
        return { cleanText, tasks: parsed };
      }
    } catch (e) {}
  }
  return { cleanText: text, tasks: [] };
}

function extractActionSeriesFromText(text = "") {
  if (!text || typeof text !== "string") return [];
  const embedded = extractAndStripEmbeddedTasks(text);
  if (embedded.tasks && embedded.tasks.length > 0) {
    return embedded.tasks;
  }
  const results = [];
  const regex = /(?:^|\n)\s*(?:\d+[\.\)]|[-*•])\s*\*\*([^*:\n]{3,85}):?\*\*[:\s—–-]*(.+?)(?=\n\s*(?:\d+[\.\)]|[-*•]|\n|#|$))/gs;
  let match;
  while ((match = regex.exec(text)) !== null) {
    const rawTitle = (match[1] || "").trim().replace(/:$/, "");
    const rawDesc = (match[2] || "").replace(/\s+/g, " ").trim();
    if (rawTitle && rawDesc.length > 8) {
      const isFix = /\b(fix|error|bug|crash|freeze|watchdog|resolve|patch|issue)\b/i.test(`${rawTitle} ${rawDesc}`);
      results.push({
        title: rawTitle.slice(0, 75),
        category: isFix ? "fix" : "feature",
        description: rawDesc.slice(0, 200),
        suggested_prompt: `${rawTitle}: ${rawDesc.slice(0, 300)}`
      });
    }
  }
  return results.length >= 2 ? results.slice(0, 10) : [];
}

function attachIdeasDockToBubble(aiBubble, extractedTasks, objectiveTitleOverride = null) {
  if (!aiBubble || !extractedTasks || extractedTasks.length === 0) return;
  const targetContainer = aiBubble.querySelector(".ai-body") || aiBubble;

  // Avoid duplicate docks
  if (targetContainer.querySelector(".chat-ideas-box")) return;

  const mainObjectiveTitle = objectiveTitleOverride || deriveObjectiveTitle(extractedTasks);
  const stepPreviewText = extractedTasks
    .map((t, idx) => `#${idx + 1} ${t.title}`)
    .join("  →  ");

  const ideasDock = document.createElement("div");
  ideasDock.className = "chat-ideas-box objective-card";
  ideasDock.innerHTML = `
    <div class="chat-ideas-header">
      <div class="chat-ideas-header-left" style="flex: 1; min-width: 0;">
        <span class="task-tag objective"><i class="fa-solid fa-bullseye"></i> Objective</span>
        <span class="objective-card-title" title="${escapeHtml(mainObjectiveTitle)}">${escapeHtml(mainObjectiveTitle)}</span>
        <span class="objective-steps-badge">${extractedTasks.length} step${extractedTasks.length === 1 ? "" : "s"}</span>
      </div>
      <div class="chat-ideas-header-actions">
        <button type="button" class="btn-toggle-objective-outline" title="Expand or collapse the step-by-step outline to inspect or check/uncheck individual steps">
          <i class="fa-solid fa-list-ol"></i>
          <span class="outline-btn-text">Outline</span>
          <i class="fa-solid fa-chevron-down outline-chevron" style="font-size: 8px;"></i>
        </button>
        <button type="button" class="btn-series-proceed" title="Run all checked steps in this objective systematically in order">
          <i class="fa-solid fa-bolt"></i>
          <span class="btn-series-proceed-label">Proceed</span>
        </button>
        <button type="button" class="btn-series-stop hidden" title="Stop after the current step finishes">
          <i class="fa-solid fa-stop"></i>
          <span>Stop</span>
        </button>
      </div>
    </div>
    <div class="objective-compact-preview" title="Click to toggle step-by-step outline: ${escapeHtml(stepPreviewText)}">
      <i class="fa-solid fa-route" style="color: #818cf8; margin-right: 4px;"></i>${escapeHtml(stepPreviewText)}
    </div>
    <div class="chat-series-progress hidden">
      <div class="chat-series-progress-top">
        <span class="chat-series-progress-status"><i class="fa-solid fa-spinner animate-spin"></i> Preparing series...</span>
        <span class="chat-series-progress-pct">0%</span>
      </div>
      <div class="chat-series-progress-track">
        <div class="chat-series-progress-fill"></div>
      </div>
    </div>
    <div class="chat-ideas-list hidden"></div>
  `;
  const listEl = ideasDock.querySelector(".chat-ideas-list");
  const previewBar = ideasDock.querySelector(".objective-compact-preview");
  const btnOutline = ideasDock.querySelector(".btn-toggle-objective-outline");
  const outlineChevron = ideasDock.querySelector(".outline-chevron");
  const stepsBadge = ideasDock.querySelector(".objective-steps-badge");
  const btnProceed = ideasDock.querySelector(".btn-series-proceed");
  const btnProceedLabel = ideasDock.querySelector(".btn-series-proceed-label");
  const btnStop = ideasDock.querySelector(".btn-series-stop");
  const progressBox = ideasDock.querySelector(".chat-series-progress");
  const progressStatus = ideasDock.querySelector(".chat-series-progress-status");
  const progressPct = ideasDock.querySelector(".chat-series-progress-pct");
  const progressFill = ideasDock.querySelector(".chat-series-progress-fill");

  function toggleOutlineDrawer(forceOpen = null) {
    if (!listEl) return;
    const isHidden = listEl.classList.contains("hidden");
    const shouldOpen = forceOpen !== null ? forceOpen : isHidden;
    if (shouldOpen) {
      listEl.classList.remove("hidden");
      if (btnOutline) btnOutline.classList.add("active");
      if (outlineChevron) outlineChevron.className = "fa-solid fa-chevron-up outline-chevron";
    } else {
      listEl.classList.add("hidden");
      if (btnOutline) btnOutline.classList.remove("active");
      if (outlineChevron) outlineChevron.className = "fa-solid fa-chevron-down outline-chevron";
    }
  }

  if (btnOutline) {
    btnOutline.addEventListener("click", () => toggleOutlineDrawer());
  }
  if (previewBar) {
    previewBar.addEventListener("click", () => toggleOutlineDrawer());
  }

  const seriesEntries = [];
  let isSeriesRunning = false;
  let stopRequested = false;

  function updateProceedButtonState() {
    if (!btnProceed) return;
    const enabledPending = seriesEntries.filter((e) => !e.taskObj.completed && e.includeInRun !== false);
    const doneCount = seriesEntries.filter((e) => e.taskObj.completed).length;
    if (stepsBadge) {
      stepsBadge.innerText = doneCount > 0 ? `${doneCount}/${seriesEntries.length} done` : `${seriesEntries.length} step${seriesEntries.length === 1 ? "" : "s"}`;
    }
    if (isSeriesRunning) {
      btnProceed.disabled = true;
      return;
    }
    btnProceed.disabled = false;
    if (enabledPending.length > 0) {
      btnProceed.innerHTML = `<i class="fa-solid fa-bolt"></i> <span class="btn-series-proceed-label">Proceed (${enabledPending.length === seriesEntries.length ? `All ${enabledPending.length}` : `${enabledPending.length}`})</span>`;
    } else if (doneCount === seriesEntries.length) {
      btnProceed.innerHTML = `<i class="fa-solid fa-check text-emerald-300"></i> <span class="btn-series-proceed-label">Done (Re-run)</span>`;
    } else {
      btnProceed.innerHTML = `<i class="fa-solid fa-bolt"></i> <span class="btn-series-proceed-label">Proceed</span>`;
    }
  }

  extractedTasks.forEach((t, index) => {
    const stepNumber = index + 1;
    // Check if task exists in backlogTasks to mirror completion status
    const existingTask = backlogTasks.find((bt) => bt.id === t.id || bt.title === t.title);
    const isCompleted = existingTask ? existingTask.completed : (t.completed || false);
    const taskObj = existingTask || {
      id: t.id || `task-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
      title: t.title,
      category: t.category || "feature",
      description: t.description || "",
      suggested_prompt: t.suggested_prompt || t.title,
      objective_id: t.objective_id || null,
      objective_title: t.objective_title || mainObjectiveTitle,
      completed: isCompleted
    };

    const ideaCard = document.createElement("div");
    const catClass = ["design", "feature", "ux", "polish", "fix"].includes(taskObj.category?.toLowerCase())
      ? taskObj.category.toLowerCase()
      : "feature";

    const entryRecord = {
      taskObj,
      ideaCard,
      stepNumber,
      includeInRun: !taskObj.completed,
      updateChatCardUi: null,
      setStepRunning: null
    };

    function setStepRunning(running, currentIdx = stepNumber, totalSteps = extractedTasks.length) {
      if (running) {
        ideaCard.classList.add("running-step");
        const impBtn = ideaCard.querySelector(".btn-chat-implement");
        if (impBtn) {
          impBtn.disabled = true;
          impBtn.innerHTML = `<i class="fa-solid fa-spinner animate-spin"></i> <span>Step ${currentIdx}/${totalSteps}...</span>`;
        }
      } else {
        ideaCard.classList.remove("running-step");
      }
    }

    function updateChatCardUi() {
      ideaCard.classList.remove("running-step");
      if (taskObj.completed) {
        ideaCard.className = "chat-idea-card completed";
        ideaCard.innerHTML = `
          <div class="chat-idea-info">
            <div style="display: flex; align-items: center; gap: 5px; flex-wrap: wrap;">
              <span style="font-size: 9.5px; color: #64748b; font-family: monospace; font-weight: 700;">#${stepNumber}</span>
              <span class="chat-idea-done-badge"><i class="fa-solid fa-check"></i> Done</span>
              <span class="task-tag ${catClass}">${escapeHtml(taskObj.category || "Task")}</span>
              <strong>${escapeHtml(taskObj.title)}</strong>
            </div>
            <div class="chat-idea-desc">${escapeHtml(taskObj.description || "")}</div>
          </div>
          <div class="chat-idea-actions">
            <button type="button" class="btn-chat-view-done" title="Open and view this task in the Done Pile">
              <i class="fa-solid fa-folder-closed"></i> Done Pile
            </button>
            <label class="chat-idea-done-label" title="Uncheck to restore to active tasks" style="color: #64748b;">
              <input type="checkbox" class="chk-chat-done" checked> Done
            </label>
          </div>
        `;
        const viewBtn = ideaCard.querySelector(".btn-chat-view-done");
        if (viewBtn) {
          viewBtn.addEventListener("click", () => {
            toggleBacklogDrawer(true);
            switchBacklogFolder("done");
          });
        }
        const chk = ideaCard.querySelector(".chk-chat-done");
        if (chk) {
          chk.addEventListener("change", async (e) => {
            taskObj.completed = e.target.checked;
            entryRecord.includeInRun = !taskObj.completed;
            await saveBacklogToServer();
            renderBacklog();
            updateDesignerTaskPicker();
            updateChatCardUi();
            updateProceedButtonState();
          });
        }
      } else {
        ideaCard.className = "chat-idea-card";
        ideaCard.innerHTML = `
          <div class="chat-idea-info">
            <div style="display: flex; align-items: center; gap: 5px; flex-wrap: wrap;">
              <label title="Check to include this step when clicking Proceed" style="display: inline-flex; align-items: center; cursor: pointer;">
                <input type="checkbox" class="chk-step-include" ${entryRecord.includeInRun !== false ? "checked" : ""}>
              </label>
              <span style="font-size: 9.5px; color: #818cf8; font-family: monospace; font-weight: 700;">#${stepNumber}</span>
              <span class="task-tag ${catClass}">${escapeHtml(taskObj.category || "Task")}</span>
              <strong>${escapeHtml(taskObj.title)}</strong>
            </div>
            <div class="chat-idea-desc">${escapeHtml(taskObj.description || "")}</div>
          </div>
          <div class="chat-idea-actions">
            <label class="chat-idea-done-label" title="File this step directly to Done Pile">
              <input type="checkbox" class="chk-chat-done"> Done
            </label>
            <button type="button" class="btn-chat-implement" title="Run only this single step right now">
              <i class="fa-solid fa-wand-magic-sparkles"></i>
              <span>Run Step</span>
            </button>
            <button type="button" class="btn-task-config btn-chat-config" title="Configure target file & implementation options">
              <i class="fa-solid fa-gear"></i>
            </button>
          </div>
        `;
        const chkInc = ideaCard.querySelector(".chk-step-include");
        if (chkInc) {
          chkInc.addEventListener("change", (e) => {
            entryRecord.includeInRun = Boolean(e.target.checked);
            updateProceedButtonState();
          });
        }
        const chk = ideaCard.querySelector(".chk-chat-done");
        if (chk) {
          chk.addEventListener("change", async (e) => {
            taskObj.completed = e.target.checked;
            if (!backlogTasks.some((bt) => bt.id === taskObj.id)) {
              backlogTasks.push(taskObj);
            }
            await saveBacklogToServer();
            renderBacklog();
            updateDesignerTaskPicker();
            updateChatCardUi();
            updateProceedButtonState();
          });
        }
        const btnCfg = ideaCard.querySelector(".btn-chat-config");
        if (btnCfg) {
          btnCfg.addEventListener("click", () => {
            openImplementationModal(taskObj, ideaCard);
          });
        }
        const impBtn = ideaCard.querySelector(".btn-chat-implement");
        if (impBtn) {
          impBtn.addEventListener("click", async () => {
            if (!backlogTasks.some((bt) => bt.id === taskObj.id)) {
              backlogTasks.push(taskObj);
            }
            await implementTaskDirectly(taskObj, ideaCard);
            taskObj.completed = true;
            updateChatCardUi();
            updateProceedButtonState();
          });
        }
      }
    }

    entryRecord.updateChatCardUi = updateChatCardUi;
    entryRecord.setStepRunning = setStepRunning;
    updateChatCardUi();
    listEl.appendChild(ideaCard);
    seriesEntries.push(entryRecord);
  });

  updateProceedButtonState();

  if (btnStop) {
    btnStop.addEventListener("click", () => {
      stopRequested = true;
      btnStop.disabled = true;
      btnStop.innerHTML = '<i class="fa-solid fa-hand"></i> <span>Stopping...</span>';
    });
  }

  if (btnProceed) {
    btnProceed.addEventListener("click", async () => {
      if (isSeriesRunning) return;
      if (!activeApp) {
        alert("Please select or detect an active app first.");
        return;
      }

      // Determine checked pending steps (if all are already completed, allow re-running all)
      let queue = seriesEntries.filter((e) => !e.taskObj.completed && e.includeInRun !== false);
      if (queue.length === 0) {
        const anyUncompleted = seriesEntries.filter((e) => !e.taskObj.completed);
        if (anyUncompleted.length > 0) {
          alert("Please check at least one step in the Outline to run.");
          toggleOutlineDrawer(true);
          return;
        }
        seriesEntries.forEach((e) => {
          e.taskObj.completed = false;
          e.includeInRun = true;
          e.updateChatCardUi();
        });
        queue = [...seriesEntries];
      }

      isSeriesRunning = true;
      stopRequested = false;
      btnProceed.disabled = true;
      btnProceed.innerHTML = `<i class="fa-solid fa-spinner animate-spin"></i> <span class="btn-series-proceed-label">Running 1/${queue.length}...</span>`;
      if (btnStop) {
        btnStop.disabled = false;
        btnStop.innerHTML = '<i class="fa-solid fa-stop"></i> <span>Stop</span>';
        btnStop.classList.remove("hidden");
      }
      if (progressBox) progressBox.classList.remove("hidden");

      ensureStudioChatVisible();

      if (!appFileList || appFileList.length === 0) {
        await loadFileTree(activeApp.slug);
      }

      const total = queue.length;
      let completedCount = 0;
      const stepSummaries = [];
      const allToolSteps = [];
      const allModifiedFiles = new Set();
      const firstGuess = guessBestTargetFile(queue[0].taskObj, appFileList) || activeFilePath || (fileSelect && fileSelect.value);
      if (firstGuess && firstGuess !== activeFilePath) {
        if (fileSelect) fileSelect.value = firstGuess;
        await openFile(firstGuess);
      } else if (!activeFilePath && fileSelect && fileSelect.value) {
        await openFile(fileSelect.value);
      }

      const initialBaseline = codeEditor ? codeEditor.value : "";
      const seriesBubble = startActionChatBubble({
        actionType: "batch",
        title: `${mainObjectiveTitle} (${total} Step${total === 1 ? "" : "s"})`,
        instruction: queue.map((q, idx) => `${idx + 1}. ${q.taskObj.title}`).join(" • "),
        targetFile: activeFilePath || "app files"
      });

      for (let i = 0; i < total; i++) {
        if (stopRequested) {
          stepSummaries.push(`• ⏹️ **Stopped after ${completedCount}/${total} steps** by user.`);
          break;
        }

        const entry = queue[i];
        const { taskObj, ideaCard } = entry;
        if (!backlogTasks.some((bt) => bt.id === taskObj.id)) {
          backlogTasks.push(taskObj);
        }

        const pct = Math.round((i / total) * 100);
        if (progressFill) progressFill.style.width = `${pct}%`;
        if (progressPct) progressPct.innerText = `${pct}%`;
        if (progressStatus) {
          progressStatus.innerHTML = `<i class="fa-solid fa-spinner animate-spin text-sky-400"></i> Step ${i + 1} of ${total}: ${escapeHtml(taskObj.title)}`;
        }
        btnProceed.innerHTML = `<i class="fa-solid fa-spinner animate-spin"></i> <span class="btn-series-proceed-label">Running ${i + 1}/${total}...</span>`;

        entry.setStepRunning(true, i + 1, total);

        // Smart-select target file for this specific step
        const stepFile = guessBestTargetFile(taskObj, appFileList) || activeFilePath || (fileSelect && fileSelect.value);
        if (stepFile && stepFile !== activeFilePath) {
          if (fileSelect) fileSelect.value = stepFile;
          await openFile(stepFile);
        }

        const targetFile = activeFilePath || stepFile || "index.html";
        const beforeStepCode = codeEditor ? codeEditor.value : "";
        const instruction = taskObj.suggested_prompt || `${taskObj.title}: ${taskObj.description || ""}`;

        updateActionChatBubbleStep(
          seriesBubble,
          `[Step ${i + 1}/${total}] Antigravity Agent implementing <strong>${escapeHtml(taskObj.title)}</strong> in <code>${escapeHtml(targetFile)}</code>...`
        );

        try {
          const res = await fetchAntigravityApi("/api/extension/apply-design", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              slug: activeApp.slug,
              file_path: targetFile,
              current_code: beforeStepCode,
              instruction: instruction,
              save_to_disk: true
            })
          });

          const data = await res.json();
          if (Array.isArray(data.tool_steps)) {
            allToolSteps.push(...data.tool_steps);
          }
          if (Array.isArray(data.modified_files)) {
            data.modified_files.forEach((f) => allModifiedFiles.add(f));
          }
          if (res.ok && data.success) {
            const finalTargetFile = data.target_file || targetFile;
            allModifiedFiles.add(finalTargetFile);
            const baselineUsed = typeof data.baseline_code === "string" ? data.baseline_code : beforeStepCode;
            if (finalTargetFile !== activeFilePath) {
              activeFilePath = finalTargetFile;
              if (fileSelect) fileSelect.value = finalTargetFile;
            }
            if (codeEditor) codeEditor.value = data.modified_code;
            recordEditedFileState(finalTargetFile, baselineUsed, data.modified_code, true);
            isUnsaved = false;
            if (unsavedIndicator) unsavedIndicator.style.display = "none";
            if (!data.saved_to_disk) {
              await saveCurrentFile();
            }

            taskObj.completed = true;
            selectedTaskIds.delete(taskObj.id);
            completedCount++;
            entry.updateChatCardUi();
            stepSummaries.push(`• **Step ${i + 1} (${taskObj.title})** [\`${finalTargetFile}\`]: ${data.explanation || "Completed."}`);
            logSessionChange(
              taskObj.category === "fix" ? "watchdog_fix" : "ai_implementation",
              `[Series ${i + 1}/${total}] Implemented "${taskObj.title}" in ${finalTargetFile}`,
              finalTargetFile,
              data.explanation
            );
          } else {
            entry.setStepRunning(false);
            entry.updateChatCardUi();
            stepSummaries.push(`• ⚠️ **Step ${i + 1} (${taskObj.title})**: ${data.explanation || "Failed to generate code."}`);
          }
        } catch (err) {
          entry.setStepRunning(false);
          entry.updateChatCardUi();
          stepSummaries.push(`• ⚠️ **Step ${i + 1} (${taskObj.title})**: ${String(err)}`);
        }

        await saveBacklogToServer();
        renderBacklog();
        updateDesignerTaskPicker();
      }

      if (progressFill) progressFill.style.width = "100%";
      if (progressPct) progressPct.innerText = "100%";
      if (progressStatus) {
        progressStatus.innerHTML = `<i class="fa-solid fa-circle-check text-emerald-400"></i> Objective finished (${completedCount}/${total} steps completed & saved)`;
      }
      if (btnStop) btnStop.classList.add("hidden");

      finishActionChatBubble(seriesBubble, {
        success: completedCount > 0,
        actionType: "batch",
        title: `${mainObjectiveTitle} (${completedCount}/${total} Steps Completed)`,
        targetFile: activeFilePath || "app files",
        explanation: stepSummaries.join("\n"),
        baselineCode: initialBaseline,
        modifiedCode: codeEditor ? codeEditor.value : "",
        toolSteps: allToolSteps,
        modifiedFiles: Array.from(allModifiedFiles),
        engine: "antigravity_sdk",
        errorMsg: completedCount === 0 ? "Could not complete the steps in this objective." : ""
      });

      if (completedCount > 0) {
        reloadActiveTab();
      }
      await refreshGitStatus();
      isSeriesRunning = false;
      updateProceedButtonState();
    });
  }

  targetContainer.appendChild(ideasDock);
}

function toggleChatImageMode(forceVal = null) {
  if (forceVal !== null) isChatImageMode = forceVal;
  else isChatImageMode = !isChatImageMode;

  if (btnChatModeImage) {
    btnChatModeImage.classList.toggle("active", isChatImageMode);
  }
  const gName = getGeppyName(activeApp);
  if (brainstormInput) {
    if (isChatImageMode) {
      brainstormInput.placeholder = `🎨 Describe image or icon to generate (e.g. ${gName} badge, Hex icon)...`;
      brainstormInput.focus();
    } else {
      brainstormInput.placeholder = `Ask ${gName} or type /image to generate visuals...`;
    }
  }
}

function attachImageCardToBubble(aiBubble, imageData) {
  if (!aiBubble || !imageData || !imageData.image_url) return;
  const targetContainer = aiBubble.querySelector(".ai-body") || aiBubble;

  // Avoid duplicates
  if (targetContainer.querySelector(".chat-image-card")) return;

  const card = document.createElement("div");
  card.className = "chat-image-card";

  const fullSrc = imageData.image_url.startsWith("http") ? imageData.image_url : `${SERVER_URL}${imageData.image_url}`;
  const title = imageData.title || "Synthesized Visual Asset";
  const filename = imageData.filename || "icon.png";

  const paletteHtml = (imageData.color_palette || []).map((color) => {
    const m = color.match(/#[0-9a-fA-F]{6}/);
    const hex = m ? m[0] : "#818cf8";
    return `<span style="background: ${hex}; width: 10px; height: 10px; border-radius: 50%; display: inline-block; border: 1px solid rgba(255,255,255,0.2);" title="${escapeHtml(color)}"></span>`;
  }).join("");

  card.innerHTML = `
    <div class="chat-image-preview-frame" title="Click to view full size">
      <img src="${fullSrc}" alt="${escapeHtml(title)}" class="chat-gen-img" />
    </div>
    <div class="chat-image-meta">
      <strong class="chat-image-title">${escapeHtml(title)}</strong>
      <div class="chat-image-palette">${paletteHtml}</div>
    </div>
    <div class="chat-image-actions">
      <button type="button" class="btn-chat-img-action primary btn-chat-set-icon" title="Apply as official App Launcher Icon">
        <i class="fa-solid fa-star text-amber"></i> Set as App Icon
      </button>
      <button type="button" class="btn-chat-img-action secondary btn-chat-drop-app" title="Save file to App's assets folder">
        <i class="fa-solid fa-cloud-arrow-down"></i> Save to App
      </button>
      <button type="button" class="btn-chat-img-action subtle btn-chat-open-lab" title="Fine-tune in Asset Laboratory">
        <i class="fa-solid fa-flask"></i> In Asset Lab
      </button>
      <button type="button" class="btn-chat-img-action subtle btn-chat-view-full" title="Open full resolution in new tab">
        <i class="fa-solid fa-arrow-up-right-from-square"></i> Full Res
      </button>
    </div>
  `;

  // Full resolution view
  card.querySelector(".chat-image-preview-frame").addEventListener("click", () => {
    window.open(fullSrc, "_blank");
  });
  card.querySelector(".btn-chat-view-full").addEventListener("click", () => {
    window.open(fullSrc, "_blank");
  });

  // Open in Asset Lab
  card.querySelector(".btn-chat-open-lab").addEventListener("click", () => {
    switchMode("assets");
    switchAssetsSubTab("lab");
    currentSynthesizedAsset = {
      type: "url",
      url: imageData.image_url,
      filename: filename,
      title: title,
      colors: imageData.color_palette || []
    };
    if (extLabPreviewImg) {
      extLabPreviewImg.src = `${fullSrc}?t=${Date.now()}`;
      extLabPreviewImg.classList.remove("hidden");
    }
    if (extLabPreviewSvg) extLabPreviewSvg.classList.add("hidden");
    if (extLabAssetTitle) extLabAssetTitle.innerText = title;
    if (extLabFilename) extLabFilename.value = filename;
    if (extLabDropDock) {
      extLabDropDock.classList.remove("hidden");
      extLabDropDock.scrollIntoView({ behavior: "smooth" });
    }
  });

  // Set as Official App Icon
  const btnSetIcon = card.querySelector(".btn-chat-set-icon");
  btnSetIcon.addEventListener("click", async () => {
    if (!activeApp) {
      alert("Please select or detect an application first.");
      return;
    }
    const origText = btnSetIcon.innerHTML;
    btnSetIcon.disabled = true;
    btnSetIcon.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Setting...';

    try {
      const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/images/drop-asset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_folder: "assets",
          target_filename: filename,
          set_as_app_icon: true,
          update_code_references: true,
          asset_url: imageData.image_url
        })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        btnSetIcon.innerHTML = '<i class="fa-solid fa-check text-emerald-400"></i> App Icon Applied!';
        logSessionChange("asset_drop", `Applied ${filename} as official app icon`, data.rel_path);
        await loadAppImages(activeApp.slug);
        await refreshGitStatus();
        reloadActiveTab();
        setTimeout(() => {
          btnSetIcon.disabled = false;
          btnSetIcon.innerHTML = origText;
        }, 2500);
      } else {
        alert(`Error applying icon: ${data.detail || data.message || "Failed"}`);
        btnSetIcon.disabled = false;
        btnSetIcon.innerHTML = origText;
      }
    } catch (err) {
      alert(`Error: ${err}`);
      btnSetIcon.disabled = false;
      btnSetIcon.innerHTML = origText;
    }
  });

  // Save to App Folder
  const btnDropApp = card.querySelector(".btn-chat-drop-app");
  btnDropApp.addEventListener("click", async () => {
    if (!activeApp) {
      alert("Please select or detect an application first.");
      return;
    }
    const origText = btnDropApp.innerHTML;
    btnDropApp.disabled = true;
    btnDropApp.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Saving...';

    try {
      const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/images/drop-asset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_folder: "assets",
          target_filename: filename,
          set_as_app_icon: false,
          update_code_references: true,
          asset_url: imageData.image_url
        })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        btnDropApp.innerHTML = '<i class="fa-solid fa-check text-emerald-400"></i> Saved to assets/!';
        logSessionChange("asset_drop", `Saved ${filename} to assets/`, data.rel_path);
        await loadAppImages(activeApp.slug);
        await refreshGitStatus();
        setTimeout(() => {
          btnDropApp.disabled = false;
          btnDropApp.innerHTML = origText;
        }, 2500);
      } else {
        alert(`Error saving: ${data.detail || data.message || "Failed"}`);
        btnDropApp.disabled = false;
        btnDropApp.innerHTML = origText;
      }
    } catch (err) {
      alert(`Error: ${err}`);
      btnDropApp.disabled = false;
      btnDropApp.innerHTML = origText;
    }
  });

  targetContainer.appendChild(card);
}


async function reassociateCurrentTabToActiveApp() {
  if (!activeApp) {
    alert("Please select an application to associate with this tab.");
    return;
  }
  const tabData = lastDetectedUnrecognized;
  const targetUrl = tabData?.url || (tabData?.port ? `http://localhost:${tabData.port}` : null);
  if (!targetUrl) {
    alert("No active tab URL detected to associate.");
    return;
  }

  if (btnReassociateTab) {
    btnReassociateTab.disabled = true;
    btnReassociateTab.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Linking...';
  }

  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/associate-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ live_url: targetUrl })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      activeApp.live_url = targetUrl;
      activeApp.is_live = true;

      // Update active instance
      activeTabInstance.slug = activeApp.slug;
      activeTabInstance.url = targetUrl;
      if (activeTabId) activeTabInstance.tabId = activeTabId;
      try {
        const u = new URL(targetUrl);
        activeTabInstance.port = u.port || "80";
      } catch (e) {}

      // Update badge
      if (appLiveBadge) {
        appLiveBadge.style.display = "inline-block";
        appLiveBadge.innerText = activeTabInstance.port ? `Live (${activeTabInstance.port})` : "Live";
      }

      // Hide unrecognized bar
      if (unrecognizedAppBar) {
        unrecognizedAppBar.classList.add("hidden");
      }
      lastDetectedUnrecognized = null;
      logSessionChange("reassociate", `Linked live tab ${targetUrl} to ${activeApp.name}`);

      // Refresh apps list in memory so live status is updated
      await loadApps();
    } else {
      alert(`Could not link tab: ${data.detail || data.message || "Unknown error"}`);
    }
  } catch (err) {
    console.error("Reassociation failed:", err);
    alert(`Reassociation error: ${err}`);
  } finally {
    if (btnReassociateTab) {
      btnReassociateTab.disabled = false;
      btnReassociateTab.innerHTML = '<i class="fa-solid fa-link"></i> <span id="reassociate-btn-text">Link to App</span>';
    }
  }
}

async function ensureServerAndTrayRunning() {
  try {
    const res = await fetch(`${SERVER_URL}/api/tray/ensure`, { method: "POST" });
    if (res.ok) {
      await checkServerConnection();
      return true;
    }
  } catch (e) {
    // Server / Tray Menu is offline — invoke the registered Windows gitbridge:// protocol handler to launch Tray App!
  }

  // Trigger Windows custom URL protocol `gitbridge://launch-tray` via hidden iframe
  try {
    const iframe = document.createElement("iframe");
    iframe.style.display = "none";
    iframe.src = "gitbridge://launch-tray";
    document.body.appendChild(iframe);
    setTimeout(() => {
      try { iframe.remove(); } catch (err) {}
    }, 3000);
  } catch (e) {}

  // Poll up to 10 seconds for the Tray App & Server (port 8000) to come online
  const startWait = Date.now();
  while (Date.now() - startWait < 10000) {
    await new Promise((r) => setTimeout(r, 700));
    try {
      const checkRes = await fetch(`${SERVER_URL}/api/tray/ensure`, { method: "POST" });
      if (checkRes.ok) {
        await checkServerConnection();
        if (!apps || apps.length === 0) {
          await loadApps();
        }
        return true;
      }
    } catch (e) {}
  }
  return false;
}

async function openOrFocusAppPortTab(targetUrl, appSlug, portNum) {
  if (typeof chrome !== "undefined" && chrome.tabs) {
    let targetPort = portNum ? String(portNum) : null;
    try {
      const parsed = new URL(targetUrl);
      if (!targetPort && parsed.port) targetPort = parsed.port;
    } catch (e) {}

    // Check if a tab for this localhost port is already open so we can focus & refresh it
    try {
      const allTabs = await chrome.tabs.query({ currentWindow: true });
      const existingTab = allTabs.find((t) => {
        if (!t.url) return false;
        try {
          const u = new URL(t.url);
          const isLoc = ["localhost", "127.0.0.1", "0.0.0.0"].includes(u.hostname);
          return isLoc && targetPort && u.port === String(targetPort);
        } catch (err) {
          return false;
        }
      });

      if (existingTab && existingTab.id) {
        activeTabId = existingTab.id;
        activeTabInstance.tabId = existingTab.id;
        activeTabInstance.url = targetUrl;
        activeTabInstance.slug = appSlug;
        activeTabInstance.port = targetPort || "80";
        tabAppMap[existingTab.id] = appSlug;
        currentBrowserTabUrl = targetUrl;
        if (targetPort) {
          hostAppMap[`localhost:${targetPort}`] = appSlug;
          hostAppMap[`127.0.0.1:${targetPort}`] = appSlug;
        }
        await chrome.tabs.update(existingTab.id, { active: true, url: targetUrl });
        updatePageMatchIndicator();
        return;
      }
    } catch (e) {}

    chrome.tabs.create({ url: targetUrl }, (newTab) => {
      if (newTab) {
        activeTabId = newTab.id;
        activeTabInstance.tabId = newTab.id;
        activeTabInstance.url = targetUrl;
        activeTabInstance.slug = appSlug;
        activeTabInstance.port = targetPort || "80";
        tabAppMap[newTab.id] = appSlug;
        currentBrowserTabUrl = targetUrl;
        if (targetPort) {
          hostAppMap[`localhost:${targetPort}`] = appSlug;
          hostAppMap[`127.0.0.1:${targetPort}`] = appSlug;
        }
        updatePageMatchIndicator();
      }
    });
  } else {
    currentBrowserTabUrl = targetUrl;
    window.open(targetUrl, "_blank");
    updatePageMatchIndicator();
  }
}

async function launchSelectedApp() {
  const origHtml = btnLaunchApp.innerHTML;
  btnLaunchApp.disabled = true;
  btnLaunchApp.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> <span>Starting Tray &amp; App...</span>';

  try {
    // 1. Ensure the Windows System Tray Menu & GitBridge Server are running!
    const trayOnline = await ensureServerAndTrayRunning();
    if (!trayOnline) {
      alert("Could not reach or start Geppy's GitBridge Tray App on port 8000.");
      btnLaunchApp.disabled = false;
      btnLaunchApp.innerHTML = origHtml;
      return;
    }

    // If activeApp was not selected yet (e.g. sidebar opened while server was offline), pick selected dropdown or first app
    if (!activeApp && appSelect && appSelect.value) {
      activeApp = apps.find((a) => a.slug === appSelect.value) || null;
    }
    if (!activeApp && apps && apps.length > 0) {
      await setActiveApp(apps[0]);
    }
    if (!activeApp) {
      alert("Tray Menu launched! Please select an application from the dropdown to launch on localhost.");
      btnLaunchApp.disabled = false;
      btnLaunchApp.innerHTML = origHtml;
      return;
    }

    if (isGitBridgeApp(activeApp)) {
      await openOrFocusAppPortTab(SERVER_URL, activeApp.slug, 8000);
      activeApp.is_live = true;
      activeApp.live_url = SERVER_URL;
      if (appLiveBadge) {
        appLiveBadge.style.display = "inline-block";
        appLiveBadge.innerText = "Live (8000)";
      }
      if (btnStopApp) btnStopApp.style.display = "none";
      btnLaunchApp.innerHTML = '<i class="fa-solid fa-check text-emerald-300"></i> <span>:8000</span>';
      setTimeout(() => {
        btnLaunchApp.disabled = false;
        btnLaunchApp.innerHTML = '<i class="fa-solid fa-rocket"></i> <span>Launch</span>';
      }, 1500);
      updatePageMatchIndicator();
      return;
    }

    btnLaunchApp.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> <span>Launching Port...</span>';

    // 2. Launch the app on its dedicated localhost port via GitBridge's AppLauncherService
    const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/launch`, {
      method: "POST"
    });
    const data = await res.json();

    if (res.ok && (data.launched || data.target)) {
      const targetUrl = data.target || activeApp.live_url;
      await openOrFocusAppPortTab(targetUrl, activeApp.slug, data.port);

      activeApp.is_live = true;
      activeApp.live_url = targetUrl;
      appLiveBadge.style.display = "inline-block";
      if (btnStopApp) btnStopApp.style.display = isGitBridgeApp(activeApp) ? "none" : "inline-flex";
      let displayPort = data.port;
      if (!displayPort && targetUrl) {
        try { displayPort = new URL(targetUrl).port; } catch (e) {}
      }
      appLiveBadge.innerText = displayPort ? `Live (${displayPort})` : "Live";

      btnLaunchApp.innerHTML = `<i class="fa-solid fa-check text-emerald-300"></i> <span>:${displayPort || "Live"}</span>`;
      setTimeout(() => {
        btnLaunchApp.disabled = false;
        btnLaunchApp.innerHTML = '<i class="fa-solid fa-rocket"></i> <span>Launch</span>';
      }, 1800);

      // Refresh app catalog dropdown and running ports drawer so System Tray, Port Watcher, and Galactic match
      await loadApps();
      await refreshRunningServersState();
      updatePageMatchIndicator();
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

async function closeLocalhostTabForApp(appSlug, port, liveUrl) {
  if (typeof chrome === "undefined" || !chrome.tabs) return;
  try {
    const allTabs = await chrome.tabs.query({});
    const targetPortStr = port ? String(port) : (liveUrl ? (() => { try { return new URL(liveUrl).port; } catch (e) { return ""; } })() : "");
    for (const tab of allTabs) {
      if (!tab.url) continue;
      let shouldClose = false;
      if (appSlug && tabAppMap[tab.id] === appSlug) {
        try {
          const u = new URL(tab.url);
          if (["localhost", "127.0.0.1", "0.0.0.0"].includes(u.hostname) && u.port !== "8000") {
            shouldClose = true;
          }
        } catch (e) {}
      }
      if (!shouldClose && targetPortStr && targetPortStr !== "8000") {
        try {
          const u = new URL(tab.url);
          if (["localhost", "127.0.0.1", "0.0.0.0"].includes(u.hostname) && u.port === targetPortStr) {
            shouldClose = true;
          }
        } catch (e) {}
      }
      if (shouldClose && tab.id) {
        try {
          await chrome.tabs.remove(tab.id);
        } catch (e) {}
        delete tabAppMap[tab.id];
      }
    }
  } catch (e) {
    console.warn("Could not close localhost tab:", e);
  }
}

async function stopSelectedApp(targetSlug = null, targetPort = null, targetLiveUrl = null) {
  const slug = targetSlug || (activeApp ? activeApp.slug : (appSelect ? appSelect.value : ""));
  if (!slug) {
    alert("No active application selected to stop.");
    return;
  }

  const origHtml = btnStopApp ? btnStopApp.innerHTML : "";
  if (btnStopApp && (!targetSlug || (activeApp && activeApp.slug === slug))) {
    btnStopApp.disabled = true;
    btnStopApp.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> <span>Stopping...</span>';
  }

  try {
    const portToClose = targetPort || (activeApp && activeApp.slug === slug && activeApp.live_url ? (() => { try { return new URL(activeApp.live_url).port; } catch (e) { return null; } })() : null);
    const urlToClose = targetLiveUrl || (activeApp && activeApp.slug === slug ? activeApp.live_url : null);

    const res = await fetch(`${SERVER_URL}/api/servers/${slug}`, { method: "DELETE" });
    await closeLocalhostTabForApp(slug, portToClose, urlToClose);

    if (activeApp && activeApp.slug === slug) {
      activeApp.is_live = false;
      if (appLiveBadge) appLiveBadge.style.display = "none";
      if (btnStopApp) btnStopApp.style.display = "none";
    }

    await loadApps();
    await refreshRunningServersState();
  } catch (e) {
    console.error("Failed to stop app:", e);
  } finally {
    if (btnStopApp) {
      btnStopApp.disabled = false;
      btnStopApp.innerHTML = origHtml || '<i class="fa-solid fa-stop"></i> <span>Stop</span>';
    }
  }
}

function toggleGalacticPortDrawer(forceOpen = null) {
  if (!galacticPortDrawer) return;
  const isHidden = galacticPortDrawer.classList.contains("hidden");
  const shouldOpen = forceOpen !== null ? forceOpen : isHidden;
  if (shouldOpen) {
    galacticPortDrawer.classList.remove("hidden");
    refreshRunningServersState();
  } else {
    galacticPortDrawer.classList.add("hidden");
  }
}

async function stopAllRunningAppsFromGalactic() {
  if (btnStopAllPorts) {
    btnStopAllPorts.disabled = true;
    btnStopAllPorts.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Stopping...';
  }
  try {
    const srvRes = await fetch(`${SERVER_URL}/api/servers`);
    const runningList = srvRes.ok ? await srvRes.json() : [];
    await fetch(`${SERVER_URL}/api/servers`, { method: "DELETE" });
    for (const s of runningList) {
      await closeLocalhostTabForApp(s.slug, s.port, s.url);
    }
    if (activeApp) {
      activeApp.is_live = false;
      if (appLiveBadge) appLiveBadge.style.display = "none";
      if (btnStopApp) btnStopApp.style.display = "none";
    }
    await loadApps();
    await refreshRunningServersState();
  } catch (e) {
    console.error("Failed to stop all apps:", e);
  } finally {
    if (btnStopAllPorts) {
      btnStopAllPorts.disabled = false;
      btnStopAllPorts.innerHTML = '<i class="fa-solid fa-power-off"></i> Stop All';
    }
  }
}

async function refreshRunningServersState() {
  try {
    const res = await fetch(`${SERVER_URL}/api/servers`);
    if (!res.ok) return;
    const servers = await res.json();
    const count = Array.isArray(servers) ? servers.length : 0;

    if (runningPortsCount) {
      runningPortsCount.innerText = String(count);
    }
    if (btnTogglePortDrawer) {
      btnTogglePortDrawer.style.borderColor = count > 0 ? "rgba(16, 185, 129, 0.55)" : "rgba(100, 116, 139, 0.35)";
      btnTogglePortDrawer.style.color = count > 0 ? "#34d399" : "#94a3b8";
      btnTogglePortDrawer.title = count > 0
        ? `${count} Running App(s) on Localhost — Click to Select, Open, or Stop`
        : "0 Running Localhost Apps — Click to open Port Watcher";
    }

    // Sync activeApp live state & Stop button visibility
    if (activeApp) {
      const match = (servers || []).find((s) => s.slug === activeApp.slug);
      if (match || isGitBridgeApp(activeApp)) {
        activeApp.is_live = true;
        activeApp.live_url = (match && match.url) || activeApp.live_url || (isGitBridgeApp(activeApp) ? SERVER_URL : `http://localhost:${match.port}`);
        if (appLiveBadge) {
          appLiveBadge.style.display = "inline-block";
          const allPorts = match && Array.isArray(match.all_ports) && match.all_ports.length > 1
            ? match.all_ports.join(", ")
            : (match ? match.port : "8000");
          appLiveBadge.innerText = `Live (${allPorts})`;
        }
        if (btnStopApp) {
          btnStopApp.style.display = isGitBridgeApp(activeApp) ? "none" : "inline-flex";
        }
      } else {
        activeApp.is_live = false;
        if (appLiveBadge) appLiveBadge.style.display = "none";
        if (btnStopApp) btnStopApp.style.display = "none";
      }
      updatePageMatchIndicator();
    }

    // Populate Galactic Port Watcher Drawer if present
    if (galacticPortList) {
      if (count === 0) {
        galacticPortList.innerHTML = `<div style="font-size: 10.5px; color: #94a3b8; text-align: center; padding: 8px;">No localhost app servers currently running. Use <strong>Launch</strong> to start an app.</div>`;
      } else {
        galacticPortList.innerHTML = "";
        servers.forEach((srv) => {
          const isSelectedInGalactic = Boolean(activeApp && activeApp.slug === srv.slug);
          const isControlPlane = Boolean(srv.is_control_plane || Number(srv.port) === 8000 || srv.slug === "geppys-gitbridge");
          const row = document.createElement("div");
          row.style.cssText = isSelectedInGalactic
            ? "display: flex; align-items: center; justify-content: space-between; gap: 6px; padding: 5px 8px; background: rgba(49, 46, 129, 0.42); border: 1px solid rgba(129, 140, 248, 0.7); border-radius: 6px;"
            : "display: flex; align-items: center; justify-content: space-between; gap: 6px; padding: 5px 8px; background: rgba(30, 41, 59, 0.85); border: 1px solid rgba(51, 65, 85, 0.8); border-radius: 6px;";
          const portsLabel = Array.isArray(srv.all_ports) && srv.all_ports.length > 1
            ? `:${srv.all_ports.join(" / :")}`
            : `:${srv.port}`;
          const displayName = srv.name || srv.app_name || srv.slug;
          row.innerHTML = `
            <div class="port-row-title-click" style="display: flex; align-items: center; gap: 6px; min-width: 0; flex: 1; cursor: pointer;" title="Click to select ${escapeHtml(displayName)} in Galactic">
              <span style="width: 7px; height: 7px; border-radius: 50%; background: ${isControlPlane ? "#38bdf8" : "#10b981"}; box-shadow: 0 0 6px ${isControlPlane ? "#38bdf8" : "#10b981"}; flex-shrink: 0;"></span>
              <span style="font-size: 11px; font-weight: 700; color: #f8fafc; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(displayName)}</span>
              <span style="font-size: 10px; font-family: monospace; color: ${isControlPlane ? "#7dd3fc" : "#34d399"}; background: ${isControlPlane ? "rgba(56, 189, 248, 0.15)" : "rgba(16, 185, 129, 0.14)"}; padding: 1px 5px; border-radius: 4px; flex-shrink: 0;">${escapeHtml(portsLabel)}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 4px; flex-shrink: 0;">
              <button class="btn-mini-action btn-port-select" style="font-size: 9.5px; padding: 2px 6px; color: ${isSelectedInGalactic ? "#a7f3d0" : "#c7d2fe"}; border-color: ${isSelectedInGalactic ? "rgba(16, 185, 129, 0.55)" : "rgba(99, 102, 241, 0.55)"}; background: ${isSelectedInGalactic ? "rgba(16, 185, 129, 0.18)" : "rgba(99, 102, 241, 0.18)"};" title="Select ${escapeHtml(displayName)} as the active app to edit in Galactic">
                <i class="fa-solid ${isSelectedInGalactic ? "fa-check" : "fa-crosshairs"}"></i> ${isSelectedInGalactic ? "Editing" : "Select"}
              </button>
              <button class="btn-mini-action btn-port-open" style="font-size: 9.5px; padding: 2px 6px; color: #93c5fd;" title="Focus or open browser tab">
                <i class="fa-solid fa-arrow-up-right-from-square"></i> Open
              </button>
              ${isControlPlane ? `
                <span style="font-size: 9px; font-weight: 700; color: #7dd3fc; background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.35); padding: 1px 5px; border-radius: 4px;" title="GitBridge Control Plane Server (Always Active)">Core</span>
              ` : `
                <button class="btn-mini-action btn-port-restart" style="font-size: 9.5px; padding: 2px 6px; color: #fcd34d;" title="Restart server">
                  <i class="fa-solid fa-rotate-right"></i>
                </button>
                <button class="btn-mini-action btn-port-stop" style="font-size: 9.5px; padding: 2px 6px; color: #fca5a5; border-color: rgba(239, 68, 68, 0.45); background: rgba(239, 68, 68, 0.16);" title="Stop server and close browser tab">
                  <i class="fa-solid fa-stop"></i> Stop
                </button>
              `}
            </div>
          `;
          const titleClick = row.querySelector(".port-row-title-click");
          const btnSelect = row.querySelector(".btn-port-select");
          const btnOpen = row.querySelector(".btn-port-open");
          const btnRestart = row.querySelector(".btn-port-restart");
          const btnStop = row.querySelector(".btn-port-stop");

          const selectPortAppInGalactic = async () => {
            let targetApp = (apps || []).find((a) => a.slug === srv.slug);
            if (!targetApp) {
              await loadApps();
              targetApp = (apps || []).find((a) => a.slug === srv.slug);
            }
            if (targetApp) {
              targetApp.is_live = true;
              targetApp.live_url = srv.url || `http://localhost:${srv.port}`;
              await setActiveApp(targetApp);
            }
          };

          if (titleClick) titleClick.addEventListener("click", selectPortAppInGalactic);
          if (btnSelect) btnSelect.addEventListener("click", selectPortAppInGalactic);

          if (btnOpen) {
            btnOpen.addEventListener("click", async () => {
              const targetUrl = srv.url || `http://localhost:${srv.port}`;
              await openOrFocusAppPortTab(targetUrl, srv.slug, srv.port);
              currentBrowserTabUrl = targetUrl;
              await selectPortAppInGalactic();
            });
          }
          if (btnRestart) {
            btnRestart.addEventListener("click", async () => {
              btnRestart.disabled = true;
              btnRestart.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i>';
              try {
                await fetch(`${SERVER_URL}/api/servers/${srv.slug}/restart`, { method: "POST" });
                await refreshRunningServersState();
              } catch (e) {}
            });
          }
          if (btnStop) {
            btnStop.addEventListener("click", async () => {
              btnStop.disabled = true;
              btnStop.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i>';
              await stopSelectedApp(srv.slug, srv.port, srv.url);
            });
          }
          galacticPortList.appendChild(row);
        });
      }
    }
  } catch (e) {
    // Ignore transient offline errors
  }
}

// --- Brainstorm Mode Logic ---
function isWatchdogOrSystemDiagnosticText(str = "") {
  if (!str) return false;
  return (
    /Watchdog|Fix runtime|Look into this runtime issue|Review these \d+ runtime|runtime error|unhandledrejection|console_error|hard_freeze|hung_request|server_error|network_error/i.test(str) ||
    /(🛠️|🎨|🚀|✅\s*(Fixed!|Finished!|\*\*Finished updating)|⚠️\s*(I ran into an issue|Could not finish updating))/u.test(str)
  );
}

function shouldClampDiagnosticContent(str = "", forceSystem = false) {
  if (!str) return false;
  const isSys = forceSystem || isWatchdogOrSystemDiagnosticText(str);
  if (!isSys) return false;
  const plain = str.replace(/<[^>]+>/g, "").trim();
  const lineBreaks = (plain.match(/\n/g) || []).length + (str.match(/<br\s*\/?>|<\/p>|<\/li>/gi) || []).length;
  return plain.length > 150 || lineBreaks >= 3;
}

function buildClampedDiagnosticHtml(innerHtml) {
  return `
    <div class="chat-diagnostic-clamp-wrap">
      <div class="chat-diagnostic-clamp">${innerHtml}</div>
      <button type="button" class="btn-chat-show-more" aria-expanded="false">
        <span>Show more</span>
        <i class="fa-solid fa-chevron-down" style="font-size: 8px;"></i>
      </button>
    </div>
  `;
}

function wireDiagnosticClampToggles(rootEl) {
  if (!rootEl) return;
  rootEl.querySelectorAll(".chat-diagnostic-clamp-wrap").forEach((wrap) => {
    if (wrap.dataset.clampWired === "1") return;
    wrap.dataset.clampWired = "1";
    const clampEl = wrap.querySelector(".chat-diagnostic-clamp");
    const btn = wrap.querySelector(".btn-chat-show-more");
    if (!clampEl || !btn) return;
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isExpanded = clampEl.classList.toggle("expanded");
      btn.setAttribute("aria-expanded", isExpanded ? "true" : "false");
      btn.innerHTML = isExpanded
        ? '<span>Show less</span> <i class="fa-solid fa-chevron-up" style="font-size: 8px;"></i>'
        : '<span>Show more</span> <i class="fa-solid fa-chevron-down" style="font-size: 8px;"></i>';
    });
  });
}

let activeGalacticAgentId = "";

function initGalacticAgentCrewBar() {
  const bar = document.getElementById("galactic-agent-crew-bar");
  if (!bar || bar.dataset.initialized === "1") return;
  bar.dataset.initialized = "1";

  bar.addEventListener("click", (e) => {
    const pill = e.target.closest(".galactic-agent-pill");
    if (!pill) return;
    const agentId = pill.getAttribute("data-agent-id") || "";
    activeGalacticAgentId = agentId;

    bar.querySelectorAll(".galactic-agent-pill").forEach((btn) => {
      const id = btn.getAttribute("data-agent-id") || "";
      const isSelected = id === activeGalacticAgentId;
      btn.classList.toggle("active", isSelected);
      if (isSelected) {
        btn.style.background = "rgba(217,70,239,0.28)";
        btn.style.color = "#f5d0fe";
        btn.style.borderColor = "rgba(217,70,239,0.65)";
        btn.style.fontWeight = "700";
      } else {
        btn.style.background = id === "crew-council" ? "rgba(134,25,143,0.3)" : "rgba(30,41,59,0.9)";
        btn.style.color = id === "crew-council" ? "#f0abfc" : "#cbd5e1";
        btn.style.borderColor = id === "crew-council" ? "rgba(217,70,239,0.4)" : "rgba(148,163,184,0.25)";
        btn.style.fontWeight = "500";
      }
    });

    if (brainstormInput) {
      if (activeGalacticAgentId === "crew-council") {
        brainstormInput.placeholder = "⚡ Briefing Full AI Crew Council (@design + @arch + @social + @strategy)...";
      } else if (activeGalacticAgentId) {
        brainstormInput.placeholder = `Briefing ${pill.textContent.trim()} specialist...`;
      } else {
        brainstormInput.placeholder = "Chat with Geppy or @design / @arch / @social / @crew...";
      }
      brainstormInput.focus();
    }
  });
}

function attachSocialKitCardToBubble(bubble, kit) {
  if (!bubble || !kit) return;
  const card = document.createElement("div");
  card.style.cssText = "margin-top:10px; padding:10px; border-radius:10px; background:rgba(15,23,42,0.95); border:1px solid rgba(245,158,11,0.4); display:flex; flex-direction:column; gap:8px;";

  const xThreadText = Array.isArray(kit.x_thread) ? kit.x_thread.join("\n\n---\n\n") : (kit.x_thread || "");
  const linkedinText = kit.linkedin_post || "";
  const phRedditText = kit.reddit_producthunt || "";
  const videoScript = kit.short_video_script || "";
  const hashtagsText = Array.isArray(kit.hashtags) ? kit.hashtags.join(" ") : (kit.hashtags || "");

  card.innerHTML = `
    <div style="display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid rgba(245,158,11,0.2); padding-bottom:5px;">
      <span style="font-size:11px; font-weight:700; color:#fbbf24;">📣 Social Media Launch Kit</span>
      <span style="font-size:9px; color:#94a3b8; font-family:monospace;">1-Click Copy</span>
    </div>
    ${kit.hook_headline ? `<div style="font-size:11px; font-weight:600; color:#f8fafc; background:rgba(30,41,59,0.8); padding:6px 8px; border-radius:6px;">🔥 ${escapeHtml(kit.hook_headline)}</div>` : ""}
    <div style="display:flex; flex-wrap:wrap; gap:5px;">
      <button type="button" class="btn-copy-social-field" data-field="x" style="padding:4px 8px; border-radius:6px; font-size:10px; font-weight:600; background:rgba(56,189,248,0.18); color:#7dd3fc; border:1px solid rgba(56,189,248,0.35); cursor:pointer;">🐦 Copy X Thread</button>
      <button type="button" class="btn-copy-social-field" data-field="linkedin" style="padding:4px 8px; border-radius:6px; font-size:10px; font-weight:600; background:rgba(59,130,246,0.18); color:#93c5fd; border:1px solid rgba(59,130,246,0.35); cursor:pointer;">💼 Copy LinkedIn</button>
      <button type="button" class="btn-copy-social-field" data-field="ph" style="padding:4px 8px; border-radius:6px; font-size:10px; font-weight:600; background:rgba(249,115,22,0.18); color:#fdba74; border:1px solid rgba(249,115,22,0.35); cursor:pointer;">🚀 Copy PH/Reddit</button>
      <button type="button" class="btn-copy-social-field" data-field="video" style="padding:4px 8px; border-radius:6px; font-size:10px; font-weight:600; background:rgba(236,72,153,0.18); color:#f9a8d4; border:1px solid rgba(236,72,153,0.35); cursor:pointer;">🎬 Copy 30s Script</button>
      ${hashtagsText ? `<button type="button" class="btn-copy-social-field" data-field="tags" style="padding:4px 8px; border-radius:6px; font-size:10px; font-weight:600; background:rgba(245,158,11,0.18); color:#fcd34d; border:1px solid rgba(245,158,11,0.35); cursor:pointer;">#️⃣ Copy Tags</button>` : ""}
    </div>
  `;

  card.querySelectorAll(".btn-copy-social-field").forEach((btn) => {
    btn.addEventListener("click", () => {
      const f = btn.getAttribute("data-field");
      const map = { x: xThreadText, linkedin: linkedinText, ph: phRedditText, video: videoScript, tags: hashtagsText };
      navigator.clipboard.writeText(map[f] || "");
      const orig = btn.textContent;
      btn.textContent = "✅ Copied!";
      setTimeout(() => { btn.textContent = orig; }, 1400);
    });
  });

  bubble.appendChild(card);
}

setTimeout(initGalacticAgentCrewBar, 150);

async function submitBrainstorm(overridePrompt = null, extraOptions = {}) {
  initGalacticAgentCrewBar();
  let prompt = overridePrompt || brainstormInput.value.trim();
  if (!prompt) return;

  // If user is replying to an active Antigravity error via the main chat input (when reply mode is toggled or prompt starts with @antigravity)
  if (!overridePrompt && (window._replyingToAntigravityErrorId || /^@antigravity\b/i.test(prompt))) {
    const cleanReply = prompt.replace(/^@antigravity\s*/i, "").trim() || prompt;
    brainstormInput.value = "";
    const errId = window._replyingToAntigravityErrorId || (window._latestAntigravityError && window._latestAntigravityError.id) || null;
    window._replyingToAntigravityErrorId = null;
    await sendResponseToAntigravityInChat(cleanReply, errId, "reply");
    return;
  }

  if (!overridePrompt && activeGalacticAgentId === "crew-council" && !prompt.toLowerCase().includes("@crew")) {
    prompt = `@crew ${prompt}`;
  }

  const isSystemTriggered = Boolean(overridePrompt) || isWatchdogOrSystemDiagnosticText(prompt);
  if (!overridePrompt) brainstormInput.value = "";

  appendChatBubble("user", escapeHtml(prompt), { isSystemTriggered });
  chatHistory.push({ sender: "user", text: prompt, isSystemTriggered, timestamp: Date.now() });
  if (activeApp && activeApp.slug) {
    saveAppChatHistory(activeApp.slug, chatHistory);
  }

  const gName = getGeppyName(activeApp);
  logSessionChange("brainstorm", `Chat with ${gName}: "${prompt.substring(0, 45)}${prompt.length > 45 ? "..." : ""}"`);

  const isImgReq = isChatImageMode ||
    prompt.startsWith("/image") || prompt.startsWith("/img") || prompt.startsWith("/icon") || prompt.startsWith("/draw") || prompt.startsWith("/pic") ||
    /\b(generate|create|make|draw|synthesize|design)\s+(an?\s+)?(app\s+)?(image|icon|logo|badge|mascot|graphic|sticker|artwork)\b/i.test(prompt);

  const useConsultCrew = Boolean(extraOptions.consult_crew !== undefined ? extraOptions.consult_crew : window._galacticConsultCrewEnabled);
  const useVoiceMode = Boolean(extraOptions.voice_mode !== undefined ? extraOptions.voice_mode : (window._galacticVoiceChatActive || window._galacticTtsEnabled));

  const loadingText = isImgReq
    ? `<i class="fa-solid fa-spinner animate-spin text-amber"></i> ${gName} is synthesizing your visual asset...`
    : useConsultCrew
    ? `<i class="fa-solid fa-spinner animate-spin text-cyan"></i> ${gName} is consulting with the Agent Crew...`
    : `<i class="fa-solid fa-spinner animate-spin"></i> ${activeGalacticAgentId ? "Specialist Agent" : gName} is thinking...`;

  const loadingBubble = appendChatBubble("ai", loadingText);

  btnSendBrainstorm.disabled = true;

  try {
    let liveFrameB64 = extraOptions.screen_frame_b64 || window._latestGalacticStreamFrameB64 || null;
    if (!liveFrameB64 && window._galacticScreenStreamActive && typeof window.captureGalacticTabFrameB64 === "function") {
      liveFrameB64 = await window.captureGalacticTabFrameB64();
    }

    const res = await fetchAntigravityApi("/api/extension/brainstorm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: activeApp ? activeApp.slug : "",
        message: prompt,
        history: chatHistory,
        file_path: activeFilePath,
        is_image: isImgReq,
        agent_id: (activeGalacticAgentId && activeGalacticAgentId !== "crew-council") ? activeGalacticAgentId : null,
        screen_frame_b64: liveFrameB64,
        voice_mode: useVoiceMode,
        consult_crew: useConsultCrew
      })
    });

    const data = await res.json();
    loadingBubble.remove();

    if (res.ok) {
      const parsedFromText = extractAndStripEmbeddedTasks(data.text || "");
      const displayMarkdown = parsedFromText.cleanText || data.text || "";
      const seriesTasks =
        data.extracted_tasks && data.extracted_tasks.length > 0
          ? data.extracted_tasks
          : parsedFromText.tasks.length > 0
          ? parsedFromText.tasks
          : extractActionSeriesFromText(displayMarkdown);
      const objectiveTitle =
        seriesTasks && seriesTasks.length > 0
          ? deriveObjectiveTitle(seriesTasks, displayMarkdown || prompt)
          : null;
      const objectiveId = `obj-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;

      if (seriesTasks && seriesTasks.length > 0) {
        seriesTasks.forEach((t) => {
          t.objective_id = t.objective_id || objectiveId;
          t.objective_title = t.objective_title || objectiveTitle;
        });
      }

      const consultedBadgesHtml = Array.isArray(data.consulted_agents) && data.consulted_agents.length > 0
        ? `<div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px;">
             ${data.consulted_agents.map((ca) => `<span style="font-size:9.5px; padding:1px 6px; border-radius:999px; background:rgba(6,182,212,0.18); color:#67e8f9; border:1px solid rgba(6,182,212,0.4);">${escapeHtml(ca.icon || "🤖")} @${escapeHtml(ca.handle || ca.id)}</span>`).join("")}
           </div>`
        : "";

      const streamSeenBadgeHtml = data.live_stream_seen
        ? `<span style="font-size:9px; padding:1px 5px; border-radius:4px; background:rgba(16,185,129,0.2); color:#6ee7b7; border:1px solid rgba(16,185,129,0.4); margin-left:auto;">📺 Live Screen Seen</span>`
        : "";

      const agentBadgeHtml = data.agent
        ? `<div style="display:flex; align-items:center; gap:6px; margin-bottom:6px; padding-bottom:4px; border-bottom:1px solid rgba(148,163,184,0.18);">
             <span style="font-size:13px;">${data.agent.icon || "🤖"}</span>
             <span style="font-size:11px; font-weight:700; color:#f5d0fe;">${escapeHtml(data.agent.name || "Specialist Agent")}</span>
             <span style="font-size:9px; padding:1px 5px; border-radius:4px; background:rgba(217,70,239,0.2); color:#e879f9; font-family:monospace;">${escapeHtml(data.agent.role || data.agent.handle || "")}</span>
             ${streamSeenBadgeHtml}
           </div>${consultedBadgesHtml}`
        : (streamSeenBadgeHtml || consultedBadgesHtml)
        ? `<div style="display:flex; align-items:center; gap:6px; margin-bottom:5px;">${consultedBadgesHtml}${streamSeenBadgeHtml}</div>`
        : "";

      const aiBubble = appendChatBubble("ai", agentBadgeHtml + formatMarkdown(displayMarkdown), { isSystemTriggered });
      if (Array.isArray(data.tool_steps) && data.tool_steps.length > 0) {
        attachAntigravityToolTraceToBubble(aiBubble, data.tool_steps, data.engine || "antigravity_sdk", []);
      }
      if (data.social_kit) {
        attachSocialKitCardToBubble(aiBubble, data.social_kit);
      }
      if (data.antigravity_error && typeof window.showAntigravityErrorInGalactic === "function") {
        window.showAntigravityErrorInGalactic(data.antigravity_error, aiBubble);
      }
      if (useVoiceMode && typeof window.speakGeppyText === "function") {
        window.speakGeppyText(data.spoken_reply || displayMarkdown);
      }
      chatHistory.push({
        sender: "ai",
        text: displayMarkdown,
        isSystemTriggered,
        is_image: data.is_image || false,
        image_data: data.image_data || null,
        objective_title: objectiveTitle,
        extracted_tasks: seriesTasks || [],
        tool_steps: data.tool_steps || [],
        engine: data.engine || "antigravity_sdk",
        timestamp: Date.now()
      });
      if (activeApp && activeApp.slug) {
        saveAppChatHistory(activeApp.slug, chatHistory);
      }
      refreshGitStatus();

      // If an image asset was generated, attach the interactive card
      if (data.is_image && data.image_data) {
        attachImageCardToBubble(aiBubble, data.image_data);
        if (isChatImageMode) toggleChatImageMode(false);
      }

      // Automatically incorporate newly extracted ideas/series into backlog & chat dock!
      if (seriesTasks && seriesTasks.length > 0) {
        logSessionChange("tasks", `Extracted "${objectiveTitle}" (${seriesTasks.length} steps) from ${gName} chat`);
        seriesTasks.forEach((t) => {
          const newId = t.id || `task-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`;
          t.id = newId;
          backlogTasks.push({
            id: newId,
            title: t.title,
            category: t.category || "feature",
            target_file: t.target_file || "",
            description: t.description || "",
            suggested_prompt: t.suggested_prompt || t.prompt || t.title,
            objective_id: t.objective_id || objectiveId,
            objective_title: t.objective_title || objectiveTitle,
            completed: false
          });
        });

        attachIdeasDockToBubble(aiBubble, seriesTasks, objectiveTitle);
        chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;

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

function renderAntigravityToolTraceHtml(toolSteps = [], engine = "antigravity_sdk", modifiedFiles = []) {
  const steps = Array.isArray(toolSteps) ? toolSteps.filter(Boolean) : [];
  const modFiles = Array.isArray(modifiedFiles) ? modifiedFiles.filter(Boolean) : [];
  const isAg = String(engine || "").includes("antigravity") || steps.length > 0;
  if (!isAg && steps.length === 0 && modFiles.length === 0) return "";

  const stepItemsHtml = steps.map((st, idx) => {
    const label = st.label || st.tool || `Step ${idx + 1}`;
    const detail = st.detail || st.path || "";
    return `
      <div style="display: flex; align-items: flex-start; gap: 6px; padding: 2px 0; font-size: 10.5px; color: #cbd5e1; border-bottom: 1px dashed rgba(139, 92, 246, 0.16);">
        <span style="color: #a78bfa; font-family: monospace; font-weight: 700; flex-shrink: 0;">#${idx + 1}</span>
        <span style="font-weight: 600; color: #e2e8f0;">${escapeHtml(label)}</span>
        ${detail ? `<code style="font-size: 9.5px; color: #93c5fd; background: rgba(15, 23, 42, 0.65); padding: 0 4px; border-radius: 3px; word-break: break-all;">${escapeHtml(detail)}</code>` : ""}
      </div>
    `;
  }).join("");

  const multiFileBadges = modFiles.length > 1
    ? `<div style="display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px;">
         ${modFiles.map((fp) => `<span class="chat-action-badge file" style="font-size: 9.5px;"><i class="fa-solid fa-file-pen"></i> ${escapeHtml(fp)}</span>`).join("")}
       </div>`
    : "";

  return `
    <div class="antigravity-trace-box" style="margin: 5px 0; background: rgba(46, 16, 101, 0.25); border: 1px solid rgba(139, 92, 246, 0.42); border-radius: 7px; padding: 5px 8px;">
      <div class="antigravity-trace-header" style="display: flex; align-items: center; justify-content: space-between; gap: 6px; cursor: ${steps.length > 0 ? "pointer" : "default"};">
        <div style="display: flex; align-items: center; gap: 6px; min-width: 0;">
          <i class="fa-solid fa-atom" style="color: #c4b5fd; font-size: 11px;"></i>
          <span style="font-size: 10.5px; font-weight: 700; color: #ddd6fe;">Antigravity Agent</span>
          ${steps.length > 0 ? `<span style="font-size: 9.5px; background: rgba(139, 92, 246, 0.28); color: #ede9fe; padding: 1px 6px; border-radius: 999px; font-family: monospace;">${steps.length} surgical tool step${steps.length === 1 ? "" : "s"}</span>` : ""}
        </div>
        ${steps.length > 0 ? `<span class="ag-trace-toggle-label" style="font-size: 9.5px; color: #a78bfa; display: inline-flex; align-items: center; gap: 3px;"><span>Trace</span> <i class="fa-solid fa-chevron-down" style="font-size: 8px;"></i></span>` : ""}
      </div>
      ${multiFileBadges}
      ${steps.length > 0 ? `<div class="antigravity-trace-steps hidden" style="margin-top: 5px; padding-top: 4px; border-top: 1px solid rgba(139, 92, 246, 0.28); max-height: 165px; overflow-y: auto;">${stepItemsHtml}</div>` : ""}
    </div>
  `;
}

function wireAntigravityTraceToggles(rootEl) {
  if (!rootEl) return;
  rootEl.querySelectorAll(".antigravity-trace-box").forEach((box) => {
    if (box.dataset.agWired === "1") return;
    box.dataset.agWired = "1";
    const hdr = box.querySelector(".antigravity-trace-header");
    const stepsEl = box.querySelector(".antigravity-trace-steps");
    const toggleLbl = box.querySelector(".ag-trace-toggle-label");
    if (hdr && stepsEl) {
      hdr.addEventListener("click", () => {
        const isHidden = stepsEl.classList.toggle("hidden");
        if (toggleLbl) {
          toggleLbl.innerHTML = isHidden
            ? '<span>Trace</span> <i class="fa-solid fa-chevron-down" style="font-size: 8px;"></i>'
            : '<span>Hide</span> <i class="fa-solid fa-chevron-up" style="font-size: 8px;"></i>';
        }
      });
    }
  });
}

function attachAntigravityToolTraceToBubble(aiBubble, toolSteps = [], engine = "antigravity_sdk", modifiedFiles = []) {
  if (!aiBubble) return;
  const target = aiBubble.querySelector(".ai-body") || aiBubble;
  if (target.querySelector(".antigravity-trace-box")) return;
  const html = renderAntigravityToolTraceHtml(toolSteps, engine, modifiedFiles);
  if (!html) return;
  const wrapper = document.createElement("div");
  wrapper.innerHTML = html;
  const traceEl = wrapper.firstElementChild;
  if (traceEl) {
    target.insertBefore(traceEl, target.firstChild);
    wireAntigravityTraceToggles(target);
  }
}

function appendChatBubble(sender, htmlContent, options = {}) {
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${sender}`;
  const alreadyHasClamp = typeof htmlContent === "string" && htmlContent.includes("chat-diagnostic-clamp-wrap");
  const processedHtml =
    !alreadyHasClamp && shouldClampDiagnosticContent(htmlContent, Boolean(options.isSystemTriggered))
      ? buildClampedDiagnosticHtml(htmlContent)
      : htmlContent;

  if (sender === "ai") {
    const gName = getGeppyName(activeApp);
    const gTitle = getGeppyTitle(activeApp);
    bubble.innerHTML = `
      <div class="captain-badge">
        <span class="captain-avatar"><img src="icons/icon48.png" alt="${escapeHtml(gName)}" class="captain-avatar-img" /></span>
        <div>
          <strong style="color: #818cf8;">${escapeHtml(gName)}</strong>
          <span class="captain-sub">${escapeHtml(gTitle)}</span>
        </div>
      </div>
      <div class="ai-body">${processedHtml}</div>
    `;
    // Wire inline code block actions (Copy, Load in </> Code Drawer)
    bubble.querySelectorAll(".chat-code-block-wrapper").forEach((wrap) => {
      const codeEl = wrap.querySelector("pre code");
      const btnCopy = wrap.querySelector(".btn-code-copy");
      const btnLoad = wrap.querySelector(".btn-code-load-drawer");
      if (btnCopy && codeEl) {
        btnCopy.addEventListener("click", () => {
          navigator.clipboard.writeText(codeEl.innerText || "");
          const orig = btnCopy.innerHTML;
          btnCopy.innerHTML = '<i class="fa-solid fa-check text-emerald-400"></i> Copied';
          setTimeout(() => { btnCopy.innerHTML = orig; }, 1400);
        });
      }
      if (btnLoad && codeEl) {
        btnLoad.addEventListener("click", () => {
          toggleCodeDrawer(true);
          if (codeEditor) {
            codeEditor.value = codeEl.innerText || "";
            isUnsaved = true;
            if (unsavedIndicator) unsavedIndicator.style.display = "inline-block";
          }
        });
      }
    });
  } else {
    bubble.innerHTML = processedHtml;
  }
  wireDiagnosticClampToggles(bubble);
  wireAntigravityTraceToggles(bubble);
  chatHistoryEl.appendChild(bubble);
  chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
  return bubble;
}

// --- Conversational Action Progress & Completion Bubbles in Central Chat ---
function computeCodeDiffStats(beforeCode = "", afterCode = "") {
  const beforeLines = (beforeCode || "").split("\n");
  const afterLines = (afterCode || "").split("\n");
  const beforeSet = new Set(beforeLines.map((l) => l.trim()).filter(Boolean));
  const afterSet = new Set(afterLines.map((l) => l.trim()).filter(Boolean));

  let added = 0;
  let removed = 0;
  afterSet.forEach((l) => {
    if (!beforeSet.has(l)) added++;
  });
  beforeSet.forEach((l) => {
    if (!afterSet.has(l)) removed++;
  });

  const delta = afterLines.length - beforeLines.length;
  const deltaLabel = delta > 0 ? `+${delta} net lines` : (delta < 0 ? `${delta} net lines` : `${afterLines.length} lines`);
  return {
    added,
    removed,
    totalLines: afterLines.length,
    summary: `+${added} / -${removed} lines (${deltaLabel})`
  };
}

function startActionChatBubble({ actionType = "implement", title = "Code Update", instruction = "", targetFile = "", userPromptText = null }) {
  ensureStudioChatVisible();

  if (userPromptText) {
    appendChatBubble("user", escapeHtml(userPromptText), { isSystemTriggered: true });
    chatHistory.push({ sender: "user", text: userPromptText, isSystemTriggered: true, timestamp: Date.now() });
    if (activeApp && activeApp.slug) {
      saveAppChatHistory(activeApp.slug, chatHistory);
    }
  }

  const gName = getGeppyName(activeApp);
  const fileLabel = targetFile || activeFilePath || "target file";
  const verbPhrase =
    actionType === "fix"
      ? `🛠️ <strong>I'm fixing that now with Antigravity!</strong> Searching &amp; surgically updating <code>${escapeHtml(fileLabel)}</code> to resolve: <strong>${escapeHtml(title)}</strong>...`
      : actionType === "suggestion"
      ? `🎨 <strong>I'm applying that design now with Antigravity!</strong> Updating <code>${escapeHtml(fileLabel)}</code> with <strong>${escapeHtml(title)}</strong>...`
      : actionType === "batch"
      ? `🚀 <strong>I'm running your batch of tasks now with Antigravity!</strong> Updating <code>${escapeHtml(fileLabel)}</code> starting with <strong>${escapeHtml(title)}</strong>...`
      : `🛠️ <strong>I'm working on that now with Antigravity!</strong> Surgically updating <code>${escapeHtml(fileLabel)}</code> to implement <strong>${escapeHtml(title)}</strong>...`;

  const verbHtml = shouldClampDiagnosticContent(verbPhrase, true)
    ? buildClampedDiagnosticHtml(`<p style="margin:0;">${verbPhrase}</p>`)
    : `<p>${verbPhrase}</p>`;

  const instructionHtml =
    instruction && instruction !== title
      ? shouldClampDiagnosticContent(instruction, true)
        ? `<div style="width: 100%; margin-top: 2px; font-size: 11px; color: #94a3b8;">${buildClampedDiagnosticHtml(escapeHtml(instruction))}</div>`
        : `<span class="chat-action-badge" style="max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(instruction.slice(0, 85))}${instruction.length > 85 ? "..." : ""}</span>`
      : "";

  const html = `
    ${verbHtml}
    <div class="chat-action-card running">
      <div class="chat-action-step-pill">
        <i class="fa-solid fa-atom animate-spin" style="color: #c4b5fd;"></i>
        <span class="chat-action-step-text">${escapeHtml(gName)} + Antigravity Agent is inspecting <code>${escapeHtml(fileLabel)}</code> &amp; applying surgical edits...</span>
      </div>
      <div class="chat-action-meta-row">
        <span class="chat-action-badge file"><i class="fa-solid fa-file-code"></i> ${escapeHtml(fileLabel)}</span>
        <span class="chat-action-badge" style="color: #c4b5fd; border-color: rgba(139, 92, 246, 0.45); background: rgba(139, 92, 246, 0.14);"><i class="fa-solid fa-atom"></i> Antigravity SDK</span>
        ${instructionHtml}
      </div>
    </div>
  `;

  const bubble = appendChatBubble("ai", html);
  if (chatHistoryEl) {
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
  }
  return bubble;
}

function updateActionChatBubbleStep(bubble, stepHtml) {
  if (!bubble) return;
  const stepEl = bubble.querySelector(".chat-action-step-text");
  if (stepEl) {
    stepEl.innerHTML = stepHtml;
  }
  if (chatHistoryEl) {
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
  }
}

function finishActionChatBubble(bubble, {
  success = true,
  actionType = "implement",
  title = "Code Update",
  targetFile = "",
  explanation = "",
  baselineCode = "",
  modifiedCode = "",
  toolSteps = [],
  modifiedFiles = [],
  engine = "antigravity_sdk",
  errorMsg = ""
}) {
  if (!bubble) return;
  const aiBody = bubble.querySelector(".ai-body") || bubble;
  const fileLabel = targetFile || activeFilePath || "file";

  if (!success) {
    const errText = errorMsg || explanation || "Could not complete the requested code change.";
    const errHtml = shouldClampDiagnosticContent(errText, true)
      ? buildClampedDiagnosticHtml(escapeHtml(errText))
      : escapeHtml(errText);
    const traceHtml = renderAntigravityToolTraceHtml(toolSteps, engine, modifiedFiles);
    aiBody.innerHTML = `
      <p>⚠️ <strong>I ran into an issue while updating <code>${escapeHtml(fileLabel)}</code>:</strong></p>
      ${traceHtml}
      <div class="chat-action-card error">
        <div style="font-size: 11.5px; color: #fca5a5;">${errHtml}</div>
        <div class="chat-action-meta-row">
          <span class="chat-action-badge file"><i class="fa-solid fa-file-code"></i> ${escapeHtml(fileLabel)}</span>
          <button type="button" class="btn-chat-action-ctrl btn-bubble-open-ag-ide" title="Open this project and file directly in Antigravity IDE">
            <i class="fa-solid fa-atom" style="color: #c4b5fd;"></i>
            <span>Open in Antigravity IDE</span>
          </button>
        </div>
      </div>
    `;
    wireDiagnosticClampToggles(aiBody);
    wireAntigravityTraceToggles(aiBody);
    const btnOpenAgErr = aiBody.querySelector(".btn-bubble-open-ag-ide");
    if (btnOpenAgErr) {
      btnOpenAgErr.addEventListener("click", () => openActiveAppInAntigravityIde(fileLabel));
    }
    chatHistory.push({
      sender: "ai",
      text: `⚠️ Could not finish updating \`${fileLabel}\` for **${title}**: ${errText}`,
      isSystemTriggered: true,
      tool_steps: toolSteps || [],
      engine: engine,
      timestamp: Date.now()
    });
    if (activeApp && activeApp.slug) {
      saveAppChatHistory(activeApp.slug, chatHistory);
    }
    if (chatHistoryEl) chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
    return;
  }

  const diffStats = computeCodeDiffStats(baselineCode, modifiedCode);
  const cleanSummary = explanation || `Successfully updated ${fileLabel} to implement "${title}".`;
  const introLine =
    actionType === "fix"
      ? `✅ <strong>Fixed! Here's what I changed in <code>${escapeHtml(fileLabel)}</code>:</strong>`
      : `✅ <strong>Finished! Here's what happened in <code>${escapeHtml(fileLabel)}</code>:</strong>`;

  const formattedSummary = formatMarkdown(cleanSummary);
  const summaryHtml = shouldClampDiagnosticContent(cleanSummary, true)
    ? buildClampedDiagnosticHtml(formattedSummary)
    : formattedSummary;
  const traceHtml = renderAntigravityToolTraceHtml(toolSteps, engine, modifiedFiles);

  aiBody.innerHTML = `
    <p>${introLine}</p>
    ${traceHtml}
    <div style="margin: 4px 0 6px 0; font-size: 12px; color: #e2e8f0; line-height: 1.45;">
      ${summaryHtml}
    </div>
    <div class="chat-action-card completed">
      <div class="chat-action-meta-row">
        <span class="chat-action-badge file"><i class="fa-solid fa-file-code"></i> ${escapeHtml(fileLabel)}</span>
        <span class="chat-action-badge success"><i class="fa-solid fa-code-commit"></i> ${escapeHtml(diffStats.summary)}</span>
        <span class="chat-action-badge preview-state-badge" style="color: ${isLivePreviewEnabled ? "#34d399" : "#94a3b8"};">
          <i class="fa-solid fa-shield-check"></i> ${isLivePreviewEnabled ? "Saved to Disk • Live (No Page Reset)" : "Staged in Editor (Preview Paused)"}
        </span>
      </div>
      <div class="chat-action-btn-row">
        <button type="button" class="btn-chat-action-ctrl primary btn-bubble-inspect-code" title="Open or collapse the inline Code Drawer to inspect this change">
          <i class="fa-solid fa-code"></i>
          <span>Inspect Code</span>
        </button>
        <button type="button" class="btn-chat-action-ctrl btn-bubble-open-ag-ide" title="Open this file in Antigravity IDE" style="border-color: rgba(139, 92, 246, 0.5); color: #ddd6fe;">
          <i class="fa-solid fa-atom" style="color: #c4b5fd;"></i>
          <span>Antigravity IDE</span>
        </button>
        <button type="button" class="btn-chat-action-ctrl emerald btn-bubble-toggle-preview" title="Toggle Live Preview ON/OFF in the paired browser window">
          <i class="fa-solid fa-eye"></i>
          <span>Live Preview: ${isLivePreviewEnabled ? "ON" : "OFF"}</span>
        </button>
        <button type="button" class="btn-chat-action-ctrl btn-bubble-save-disk" title="Ensure these changes are permanently saved to disk">
          <i class="fa-solid ${isLivePreviewEnabled ? "fa-check text-emerald-400" : "fa-floppy-disk"}"></i>
          <span>${isLivePreviewEnabled ? "Saved to Disk" : "Save to Disk"}</span>
        </button>
        <button type="button" class="btn-chat-action-ctrl btn-bubble-undo-edit" title="Revert this file back to how it was before this action">
          <i class="fa-solid fa-rotate-left"></i>
          <span>Undo</span>
        </button>
      </div>
    </div>
  `;
  wireDiagnosticClampToggles(aiBody);
  wireAntigravityTraceToggles(aiBody);

  // Wire interactive buttons inside the completion chat bubble
  const btnInspect = aiBody.querySelector(".btn-bubble-inspect-code");
  if (btnInspect) {
    btnInspect.addEventListener("click", () => {
      const willOpen = viewDesigner ? viewDesigner.classList.contains("hidden") : true;
      toggleCodeDrawer(willOpen);
      if (willOpen && codeEditor) {
        codeEditor.focus();
      }
    });
  }

  const btnOpenAg = aiBody.querySelector(".btn-bubble-open-ag-ide");
  if (btnOpenAg) {
    btnOpenAg.addEventListener("click", () => openActiveAppInAntigravityIde(fileLabel));
  }

  const btnPreview = aiBody.querySelector(".btn-bubble-toggle-preview");
  const previewBadge = aiBody.querySelector(".preview-state-badge");
  if (btnPreview) {
    btnPreview.addEventListener("click", async () => {
      await onLivePreviewCheckboxChanged(!isLivePreviewEnabled);
      btnPreview.innerHTML = `<i class="fa-solid fa-eye"></i> <span>Live Preview: ${isLivePreviewEnabled ? "ON" : "OFF"}</span>`;
      if (previewBadge) {
        previewBadge.style.color = isLivePreviewEnabled ? "#34d399" : "#94a3b8";
        previewBadge.innerHTML = `<i class="fa-solid fa-shield-check"></i> ${isLivePreviewEnabled ? "Saved to Disk • Live (No Page Reset)" : "Staged in Editor (Preview Paused)"}`;
      }
    });
  }

  const btnSave = aiBody.querySelector(".btn-bubble-save-disk");
  if (btnSave) {
    btnSave.addEventListener("click", async () => {
      btnSave.disabled = true;
      btnSave.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> <span>Saving...</span>';
      const ok = await saveCurrentFile();
      if (ok) {
        btnSave.innerHTML = '<i class="fa-solid fa-check text-emerald-400"></i> <span>Saved to Disk</span>';
      } else {
        btnSave.disabled = false;
        btnSave.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> <span>Save to Disk</span>';
      }
    });
  }

  const btnUndo = aiBody.querySelector(".btn-bubble-undo-edit");
  if (btnUndo) {
    btnUndo.addEventListener("click", async () => {
      if (baselineCode !== undefined && baselineCode !== null) {
        activeFilePath = fileLabel;
        if (fileSelect) fileSelect.value = fileLabel;
        codeEditor.value = baselineCode;
        recordEditedFileState(fileLabel, baselineCode, baselineCode, true);
        isUnsaved = false;
        if (unsavedIndicator) unsavedIndicator.style.display = "none";
        await syncLivePreviewToWindow(false, false);
        btnUndo.disabled = true;
        btnUndo.innerHTML = '<i class="fa-solid fa-check"></i> <span>Reverted</span>';
        if (previewBadge) {
          previewBadge.style.color = "#fbbf24";
          previewBadge.innerHTML = '<i class="fa-solid fa-rotate-left"></i> Reverted to Pre-Edit Code';
        }
      }
    });
  }

  // Persist conversational summary to app chat history
  chatHistory.push({
    sender: "ai",
    text: `✅ **Finished updating \`${fileLabel}\` (${diffStats.summary}):**\n${cleanSummary}`,
    isSystemTriggered: true,
    tool_steps: toolSteps || [],
    modified_files: modifiedFiles || [fileLabel],
    engine: engine,
    timestamp: Date.now()
  });
  if (activeApp && activeApp.slug) {
    saveAppChatHistory(activeApp.slug, chatHistory);
  }

  if (chatHistoryEl) {
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
  }
}


// --- Ideas & Tasks Backlog System ---
async function loadBacklog(slug) {
  if (!slug) return;
  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${slug}/backlog`);
    if (res.ok) {
      const data = await res.json();
      backlogTasks = Array.isArray(data.tasks) ? data.tasks : [];
      try {
        localStorage.setItem(`galactic_backlog_${slug}`, JSON.stringify(backlogTasks));
      } catch (e) {}
      renderBacklog();
      updateDesignerTaskPicker();
      return;
    }
  } catch (e) {
    console.error("Failed to load backlog from server:", e);
  }
  try {
    const cached = localStorage.getItem(`galactic_backlog_${slug}`);
    if (cached) {
      backlogTasks = JSON.parse(cached) || [];
      renderBacklog();
      updateDesignerTaskPicker();
    }
  } catch (e) {}
}

async function saveBacklogToServer(showFlash = false) {
  if (!activeApp || !activeApp.slug) return;
  const statusEl = document.getElementById("backlog-save-status");
  if (statusEl) {
    statusEl.textContent = "⏳ Saving...";
    statusEl.style.color = "#fbbf24";
  }
  try {
    localStorage.setItem(`galactic_backlog_${activeApp.slug}`, JSON.stringify(backlogTasks));
  } catch (e) {}
  try {
    await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/backlog`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tasks: backlogTasks })
    });
    updateDesignerTaskPicker();
    if (statusEl) {
      statusEl.textContent = showFlash ? "💾 Saved!" : "✓ Saved";
      statusEl.style.color = "#34d399";
    }
  } catch (e) {
    console.error("Failed to save backlog:", e);
    if (statusEl) {
      statusEl.textContent = "✓ Saved (Local)";
      statusEl.style.color = "#38bdf8";
    }
  }
}

function switchBacklogFolder(tab) {
  currentBacklogTab = tab;
  if (tab === "active") {
    if (tabBacklogActive) tabBacklogActive.classList.add("active");
    if (tabBacklogDone) tabBacklogDone.classList.remove("active");
    if (backlogBatchBar) backlogBatchBar.style.display = "";
    if (backlogList) backlogList.style.display = "";
    if (backlogDoneDock) backlogDoneDock.style.display = "";
    if (backlogDoneList) {
      if (isDoneFolderExpanded) {
        backlogDoneList.classList.remove("hidden");
      } else {
        backlogDoneList.classList.add("hidden");
      }
    }
  } else {
    // "done" tab: Focus completely on Done Pile
    if (tabBacklogDone) tabBacklogDone.classList.add("active");
    if (tabBacklogActive) tabBacklogActive.classList.remove("active");
    if (backlogBatchBar) backlogBatchBar.style.display = "none";
    if (backlogList) backlogList.style.display = "none";
    if (backlogDoneDock) backlogDoneDock.style.display = "";
    if (backlogDoneList) backlogDoneList.classList.remove("hidden");
    if (doneFolderChevron) {
      doneFolderChevron.className = "fa-solid fa-chevron-up";
    }
    if (doneFolderIcon) {
      doneFolderIcon.className = "fa-solid fa-folder-open text-emerald-400";
    }
  }
}

function toggleDoneFolder(forceExpand = null) {
  if (forceExpand !== null) {
    isDoneFolderExpanded = forceExpand;
  } else {
    isDoneFolderExpanded = !isDoneFolderExpanded;
  }

  if (backlogDoneList) {
    if (isDoneFolderExpanded) {
      backlogDoneList.classList.remove("hidden");
    } else {
      backlogDoneList.classList.add("hidden");
    }
  }

  if (doneFolderChevron) {
    doneFolderChevron.className = isDoneFolderExpanded
      ? "fa-solid fa-chevron-up"
      : "fa-solid fa-chevron-down";
  }
  if (doneFolderIcon) {
    doneFolderIcon.className = isDoneFolderExpanded
      ? "fa-solid fa-folder-open text-emerald-400"
      : "fa-solid fa-folder-closed text-emerald-400";
  }
}

async function clearDoneTasks() {
  const doneTasks = backlogTasks.filter((t) => t.completed);
  if (doneTasks.length === 0) {
    alert("Done Pile is already empty!");
    return;
  }
  if (!confirm(`Are you sure you want to permanently clear ${doneTasks.length} completed task(s) from the Done Pile?`)) {
    return;
  }

  const count = doneTasks.length;
  backlogTasks = backlogTasks.filter((t) => !t.completed);
  await saveBacklogToServer();
  renderBacklog();
  updateDesignerTaskPicker();
  logSessionChange("tasks", `Cleared ${count} completed tasks from Done Pile`);
}

async function restoreTaskToActive(task) {
  task.completed = false;
  await saveBacklogToServer();
  renderBacklog();
  updateDesignerTaskPicker();
  logSessionChange("tasks", `Restored "${task.title}" to Active Tasks`);
}

function renderBacklog() {
  const activeTasks = backlogTasks.filter((t) => !t.completed);
  const doneTasks = backlogTasks.filter((t) => t.completed);

  if (backlogCount) backlogCount.innerText = `${activeTasks.length} active`;
  if (backlogSummaryDone) backlogSummaryDone.innerText = `${doneTasks.length} Done`;
  if (badgeActiveTasksCount) badgeActiveTasksCount.innerText = activeTasks.length;
  if (badgeDoneTasksCount) badgeDoneTasksCount.innerText = doneTasks.length;
  if (doneFolderCountBadge) doneFolderCountBadge.innerText = `${doneTasks.length} completed`;

  // 1. Render Active Tasks in backlogList
  if (backlogList) {
    backlogList.innerHTML = "";
    if (activeTasks.length === 0) {
      if (doneTasks.length > 0) {
        backlogList.innerHTML = `
          <div style="color: #64748b; font-size: 11px; text-align: center; padding: 16px 8px;">
            <i class="fa-solid fa-check-double" style="color: #34d399; margin-right: 5px;"></i>
            All caught up! All tasks are in the <strong>Done Pile</strong> below.
          </div>`;
      } else {
        backlogList.innerHTML = `
          <div style="color: #64748b; font-size: 11px; text-align: center; padding: 16px 8px;">
            No brainstormed tasks yet. Chat with AI or click a prompt pill above!
          </div>`;
      }
    } else {
      // Group active tasks into Main Objective sets so multi-chunk plans take up only 1 compact card!
      const objectiveGroups = [];
      const groupMap = new Map();
      const ungroupedTasks = [];

      activeTasks.forEach((t) => {
        if (t.objective_id) {
          if (!groupMap.has(t.objective_id)) {
            const grp = {
              id: t.objective_id,
              title: t.objective_title || deriveObjectiveTitle([t]),
              tasks: []
            };
            groupMap.set(t.objective_id, grp);
            objectiveGroups.push(grp);
          }
          groupMap.get(t.objective_id).tasks.push(t);
        } else {
          ungroupedTasks.push(t);
        }
      });

      if (ungroupedTasks.length >= 2) {
        objectiveGroups.push({
          id: "obj-active-plan",
          title: deriveObjectiveTitle(ungroupedTasks),
          tasks: ungroupedTasks
        });
      } else if (ungroupedTasks.length === 1) {
        objectiveGroups.push({
          id: ungroupedTasks[0].id,
          title: ungroupedTasks[0].title,
          tasks: ungroupedTasks
        });
      }

      objectiveGroups.forEach((grp) => {
        const steps = grp.tasks;
        const isMultiStep = steps.length > 1;
        const card = document.createElement("div");
        card.className = "task-card";

        if (!isMultiStep) {
          // Single standalone task card
          const t = steps[0];
          const catClass = ["design", "feature", "ux", "polish", "fix"].includes(t.category?.toLowerCase())
            ? t.category.toLowerCase()
            : "feature";

          card.innerHTML = `
            <div class="task-card-top">
              <label class="task-select-wrapper" title="Select task for batch execution" style="display: inline-flex; align-items: center; margin-right: 6px; cursor: pointer;">
                <input type="checkbox" class="chk-task-select" data-task-id="${t.id}" ${selectedTaskIds.has(t.id) ? "checked" : ""}>
              </label>
              <span class="task-tag ${catClass}">${escapeHtml(t.category || "Task")}</span>
              <span class="task-title">${escapeHtml(t.title)}</span>
              <button class="btn-icon-subtle btn-delete-task" title="Delete task"><i class="fa-solid fa-trash-can"></i></button>
            </div>
            <div class="task-desc">${escapeHtml(t.description || "")}</div>
            <div class="task-actions">
              <label style="font-size: 10px; color: #94a3b8; display: flex; align-items: center; gap: 4px; cursor: pointer;" title="File this task directly to the Done Pile">
                <input type="checkbox" class="chk-task-done"> Done
              </label>
              <button class="btn-push-designer" title="Automatically implement this idea into code, save to disk, and reload app">
                <i class="fa-solid fa-bolt"></i> Proceed
              </button>
              <button type="button" class="btn-task-config" title="Configure target file & implementation options">
                <i class="fa-solid fa-gear"></i>
              </button>
            </div>
          `;

          const chkSelect = card.querySelector(".chk-task-select");
          if (chkSelect) {
            chkSelect.addEventListener("change", (e) => {
              if (e.target.checked) selectedTaskIds.add(t.id);
              else selectedTaskIds.delete(t.id);
              updateBatchBarState();
            });
          }
          const chkDone = card.querySelector(".chk-task-done");
          if (chkDone) {
            chkDone.addEventListener("change", async (e) => {
              if (e.target.checked) {
                t.completed = true;
                selectedTaskIds.delete(t.id);
                updateBatchBarState();
                await saveBacklogToServer();
                renderBacklog();
                updateDesignerTaskPicker();
                logSessionChange("tasks", `Filed "${t.title}" to Done Pile`);
              }
            });
          }
          const btnDelete = card.querySelector(".btn-delete-task");
          if (btnDelete) {
            btnDelete.addEventListener("click", async () => {
              selectedTaskIds.delete(t.id);
              const idx = backlogTasks.findIndex((bt) => bt.id === t.id);
              if (idx !== -1) backlogTasks.splice(idx, 1);
              renderBacklog();
              await saveBacklogToServer();
            });
          }
          const btnCfg = card.querySelector(".btn-task-config");
          if (btnCfg) {
            btnCfg.addEventListener("click", () => openImplementationModal(t, card));
          }
          const btnImplement = card.querySelector(".btn-push-designer");
          if (btnImplement) {
            btnImplement.addEventListener("click", () => implementTaskDirectly(t, card));
          }
          backlogList.appendChild(card);
          return;
        }

        // Multi-Step Main Objective Card with Collapsible Outline & Systematic Proceed!
        const allSelected = steps.every((s) => selectedTaskIds.has(s.id));
        const stepPreview = steps.map((s, idx) => `#${idx + 1} ${s.title}`).join("  →  ");

        card.innerHTML = `
          <div class="task-card-top">
            <label class="task-select-wrapper" title="Select all steps in this objective" style="display: inline-flex; align-items: center; margin-right: 6px; cursor: pointer;">
              <input type="checkbox" class="chk-objective-select" ${allSelected ? "checked" : ""}>
            </label>
            <span class="task-tag objective"><i class="fa-solid fa-bullseye"></i> Objective</span>
            <span class="task-title" title="${escapeHtml(grp.title)}">${escapeHtml(grp.title)}</span>
            <span class="objective-steps-badge">${steps.length} steps</span>
            <button class="btn-icon-subtle btn-delete-objective" title="Delete entire objective set"><i class="fa-solid fa-trash-can"></i></button>
          </div>
          <div class="objective-compact-preview" title="Click to toggle step-by-step outline: ${escapeHtml(stepPreview)}">
            <i class="fa-solid fa-route" style="color: #818cf8; margin-right: 4px;"></i>${escapeHtml(stepPreview)}
          </div>
          <div class="task-actions" style="justify-content: space-between; margin-top: 2px;">
            <label style="font-size: 10px; color: #94a3b8; display: flex; align-items: center; gap: 4px; cursor: pointer;" title="File all steps in this objective to the Done Pile">
              <input type="checkbox" class="chk-objective-done"> Done All
            </label>
            <div style="display: flex; align-items: center; gap: 5px;">
              <button type="button" class="btn-toggle-objective-outline" title="Open or close the step-by-step outline to check/uncheck individual chunks">
                <i class="fa-solid fa-list-ol"></i>
                <span>Outline (${steps.length})</span>
                <i class="fa-solid fa-chevron-down outline-chevron" style="font-size: 8px;"></i>
              </button>
              <button type="button" class="btn-series-proceed" title="Run all checked steps in this objective systematically in order">
                <i class="fa-solid fa-bolt"></i>
                <span class="btn-obj-proceed-label">Proceed (${steps.length})</span>
              </button>
            </div>
          </div>
          <div class="backlog-objective-outline hidden"></div>
        `;

        const outlineContainer = card.querySelector(".backlog-objective-outline");
        const btnOutline = card.querySelector(".btn-toggle-objective-outline");
        const outlineChevron = card.querySelector(".outline-chevron");
        const previewEl = card.querySelector(".objective-compact-preview");
        const btnProceed = card.querySelector(".btn-series-proceed");
        const btnProceedLabel = card.querySelector(".btn-obj-proceed-label");
        const chkObjSelect = card.querySelector(".chk-objective-select");
        const chkObjDone = card.querySelector(".chk-objective-done");
        const btnDelObj = card.querySelector(".btn-delete-objective");

        const stepIncluded = new Map(steps.map((s) => [s.id, true]));

        function updateObjectiveProceedLabel() {
          if (!btnProceedLabel) return;
          const activeIncluded = steps.filter((s) => !s.completed && stepIncluded.get(s.id) !== false);
          btnProceedLabel.innerText = `Proceed (${activeIncluded.length})`;
          if (btnProceed) btnProceed.disabled = activeIncluded.length === 0 || isBatchRunning;
        }

        function toggleObjOutline(forceOpen = null) {
          if (!outlineContainer) return;
          const isHidden = outlineContainer.classList.contains("hidden");
          const shouldOpen = forceOpen !== null ? forceOpen : isHidden;
          if (shouldOpen) {
            outlineContainer.classList.remove("hidden");
            if (btnOutline) btnOutline.classList.add("active");
            if (outlineChevron) outlineChevron.className = "fa-solid fa-chevron-up outline-chevron";
          } else {
            outlineContainer.classList.add("hidden");
            if (btnOutline) btnOutline.classList.remove("active");
            if (outlineChevron) outlineChevron.className = "fa-solid fa-chevron-down outline-chevron";
          }
        }

        if (btnOutline) btnOutline.addEventListener("click", () => toggleObjOutline());
        if (previewEl) previewEl.addEventListener("click", () => toggleObjOutline());

        // Populate step-by-step outline items
        steps.forEach((s, idx) => {
          const stepRow = document.createElement("div");
          stepRow.className = "backlog-outline-step";
          const catClass = ["design", "feature", "ux", "polish", "fix"].includes(s.category?.toLowerCase())
            ? s.category.toLowerCase()
            : "feature";

          stepRow.innerHTML = `
            <div style="display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0;">
              <div style="display: flex; align-items: center; gap: 5px; flex-wrap: wrap;">
                <input type="checkbox" class="chk-outline-step-inc" checked title="Include this step when clicking Proceed">
                <span style="font-family: monospace; font-weight: 700; color: #818cf8; font-size: 9.5px;">#${idx + 1}</span>
                <span class="task-tag ${catClass}">${escapeHtml(s.category || "Step")}</span>
                <strong style="color: #f1f5f9; font-size: 11px;">${escapeHtml(s.title)}</strong>
              </div>
              ${s.description ? `<div style="color: #94a3b8; font-size: 10px; padding-left: 18px;">${escapeHtml(s.description)}</div>` : ""}
            </div>
            <div style="display: flex; align-items: center; gap: 4px; flex-shrink: 0;">
              <button type="button" class="btn-push-designer btn-run-single-step" style="font-size: 9.5px; padding: 2px 6px;" title="Run only this step">
                <i class="fa-solid fa-wand-magic-sparkles"></i> Run
              </button>
              <button type="button" class="btn-task-config btn-cfg-single-step" title="Configure target file & options">
                <i class="fa-solid fa-gear"></i>
              </button>
              <button type="button" class="btn-icon-subtle btn-done-single-step" title="Mark this single step Done">
                <i class="fa-solid fa-check"></i>
              </button>
            </div>
          `;

          const chkInc = stepRow.querySelector(".chk-outline-step-inc");
          if (chkInc) {
            chkInc.addEventListener("change", (e) => {
              stepIncluded.set(s.id, Boolean(e.target.checked));
              updateObjectiveProceedLabel();
            });
          }
          const btnRunStep = stepRow.querySelector(".btn-run-single-step");
          if (btnRunStep) {
            btnRunStep.addEventListener("click", () => implementTaskDirectly(s, stepRow));
          }
          const btnCfgStep = stepRow.querySelector(".btn-cfg-single-step");
          if (btnCfgStep) {
            btnCfgStep.addEventListener("click", () => openImplementationModal(s, stepRow));
          }
          const btnDoneStep = stepRow.querySelector(".btn-done-single-step");
          if (btnDoneStep) {
            btnDoneStep.addEventListener("click", async () => {
              s.completed = true;
              selectedTaskIds.delete(s.id);
              await saveBacklogToServer();
              renderBacklog();
              updateDesignerTaskPicker();
            });
          }

          outlineContainer.appendChild(stepRow);
        });

        if (chkObjSelect) {
          chkObjSelect.addEventListener("change", (e) => {
            steps.forEach((s) => {
              if (e.target.checked) selectedTaskIds.add(s.id);
              else selectedTaskIds.delete(s.id);
            });
            updateBatchBarState();
          });
        }

        if (chkObjDone) {
          chkObjDone.addEventListener("change", async (e) => {
            if (e.target.checked) {
              steps.forEach((s) => {
                s.completed = true;
                selectedTaskIds.delete(s.id);
              });
              updateBatchBarState();
              await saveBacklogToServer();
              renderBacklog();
              updateDesignerTaskPicker();
              logSessionChange("tasks", `Filed objective "${grp.title}" (${steps.length} steps) to Done Pile`);
            }
          });
        }

        if (btnDelObj) {
          btnDelObj.addEventListener("click", async () => {
            const idsToRemove = new Set(steps.map((s) => s.id));
            idsToRemove.forEach((id) => selectedTaskIds.delete(id));
            backlogTasks = backlogTasks.filter((bt) => !idsToRemove.has(bt.id));
            renderBacklog();
            await saveBacklogToServer();
          });
        }

        if (btnProceed) {
          btnProceed.addEventListener("click", async () => {
            const chosenSteps = steps.filter((s) => !s.completed && stepIncluded.get(s.id) !== false);
            if (chosenSteps.length === 0) return;
            selectedTaskIds.clear();
            chosenSteps.forEach((s) => selectedTaskIds.add(s.id));
            updateBatchBarState();
            await runSelectedBatch();
          });
        }

        backlogList.appendChild(card);
      });
    }
  }

  // 2. Render Done Tasks in backlogDoneList
  if (backlogDoneList) {
    backlogDoneList.innerHTML = "";
    if (doneTasks.length === 0) {
      backlogDoneList.innerHTML = `
        <div style="color: #64748b; font-size: 10.5px; text-align: center; padding: 12px 0;">
          <i class="fa-solid fa-folder-open" style="color: #10b981; margin-right: 4px;"></i>
          Done Pile is empty. Complete tasks or ideas to file them here!
        </div>`;
    } else {
      doneTasks.forEach((t) => {
        const card = document.createElement("div");
        card.className = "task-card in-done-pile";
        const catClass = ["design", "feature", "ux", "polish"].includes(t.category?.toLowerCase())
          ? t.category.toLowerCase()
          : "feature";

        card.innerHTML = `
          <div class="task-card-top">
            <span class="done-badge-tag"><i class="fa-solid fa-check"></i> Done</span>
            <span class="task-tag ${catClass}">${escapeHtml(t.category || "Task")}</span>
            <span class="task-title" style="flex: 1; margin: 0 4px;">${escapeHtml(t.title)}</span>
            <button class="btn-icon-subtle btn-delete-task" title="Permanently delete from Done Pile"><i class="fa-solid fa-trash-can"></i></button>
          </div>
          ${t.description ? `<div class="task-desc">${escapeHtml(t.description)}</div>` : ''}
          <div class="task-actions" style="justify-content: flex-end; gap: 6px; padding-top: 2px;">
            <button type="button" class="btn-restore-task" title="Restore back to Active Tasks">
              <i class="fa-solid fa-arrow-rotate-left"></i> Restore to Active
            </button>
          </div>
        `;

        // Restore to Active Button
        const btnRestore = card.querySelector(".btn-restore-task");
        if (btnRestore) {
          btnRestore.addEventListener("click", () => {
            restoreTaskToActive(t);
          });
        }

        // Delete permanently from Done Pile
        const btnDelete = card.querySelector(".btn-delete-task");
        if (btnDelete) {
          btnDelete.addEventListener("click", async () => {
            const idx = backlogTasks.findIndex((bt) => bt.id === t.id);
            if (idx !== -1) backlogTasks.splice(idx, 1);
            renderBacklog();
            await saveBacklogToServer();
          });
        }

        backlogDoneList.appendChild(card);
      });
    }
  }

  updateBatchBarState();
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

let customBacklogHeightPx = Number(localStorage.getItem("galactic_backlog_height_px")) || 260;

function toggleBacklogDrawer(forceExpand = null) {
  if (!backlogDrawer) return;
  const isCollapsed = backlogDrawer.classList.contains("collapsed");
  const shouldExpand = (forceExpand !== null) ? forceExpand : isCollapsed;
  if (shouldExpand) {
    backlogDrawer.classList.remove("collapsed");
    const targetH = Math.min(Math.max(customBacklogHeightPx || 260, 140), Math.round(window.innerHeight * 0.75));
    backlogDrawer.style.height = `${targetH}px`;
    backlogDrawer.style.maxHeight = `${targetH}px`;
    if (btnToggleBacklog) btnToggleBacklog.innerHTML = '<i class="fa-solid fa-chevron-up"></i>';
  } else {
    backlogDrawer.classList.add("collapsed");
    backlogDrawer.style.height = "";
    backlogDrawer.style.maxHeight = "";
    if (btnToggleBacklog) btnToggleBacklog.innerHTML = '<i class="fa-solid fa-chevron-down"></i>';
  }
}

function initBacklogDrawerResize() {
  if (!backlogDrawer) return;
  const btnSaveBacklog = document.getElementById("btn-save-backlog");
  if (btnSaveBacklog) {
    btnSaveBacklog.addEventListener("click", (e) => {
      e.stopPropagation();
      saveBacklogToServer(true);
    });
  }
  const handleEl = document.getElementById("backlog-resize-handle");
  const dragTargets = [handleEl, backlogHeader].filter(Boolean);
  if (dragTargets.length === 0) return;

  let isPointerDown = false;
  let isDragging = false;
  let startY = 0;
  let startHeight = 36;

  const onPointerDown = (e) => {
    if (e.button !== undefined && e.button !== 0) return;
    if (e.target.closest("#btn-save-backlog") || e.target.closest("#btn-add-custom-task") || e.target.closest("#btn-toggle-backlog")) return;

    isPointerDown = true;
    isDragging = false;
    startY = e.clientY;
    startHeight = backlogDrawer.getBoundingClientRect().height || 36;

    // If pointer started directly on the resize handle, begin dragging immediately
    if (handleEl && (e.target === handleEl || handleEl.contains(e.target))) {
      isDragging = true;
      backlogDrawer.classList.add("resizing");
      e.preventDefault();
    }

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  };

  const onPointerMove = (e) => {
    if (!isPointerDown) return;
    const deltaY = startY - e.clientY; // positive = dragging UP
    if (!isDragging && Math.abs(deltaY) > 4) {
      isDragging = true;
      backlogDrawer.classList.add("resizing");
      backlogDrawer.dataset.justDragged = "1";
    }
    if (!isDragging) return;

    const maxAllowed = Math.round(window.innerHeight * 0.78);
    const desiredHeight = Math.min(maxAllowed, Math.max(36, Math.round(startHeight + deltaY)));

    if (desiredHeight < 64) {
      backlogDrawer.classList.add("collapsed");
      backlogDrawer.style.height = "";
      backlogDrawer.style.maxHeight = "";
      if (btnToggleBacklog) btnToggleBacklog.innerHTML = '<i class="fa-solid fa-chevron-down"></i>';
    } else {
      backlogDrawer.classList.remove("collapsed");
      backlogDrawer.style.height = `${desiredHeight}px`;
      backlogDrawer.style.maxHeight = `${desiredHeight}px`;
      customBacklogHeightPx = desiredHeight;
      if (btnToggleBacklog) btnToggleBacklog.innerHTML = '<i class="fa-solid fa-chevron-up"></i>';
    }
  };

  const onPointerUp = () => {
    if (!isPointerDown) return;
    isPointerDown = false;
    backlogDrawer.classList.remove("resizing");
    if (isDragging && !backlogDrawer.classList.contains("collapsed") && customBacklogHeightPx >= 100) {
      try {
        localStorage.setItem("galactic_backlog_height_px", String(customBacklogHeightPx));
      } catch (e) {}
    }
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
  };

  dragTargets.forEach((el) => {
    el.addEventListener("pointerdown", onPointerDown);
  });
}

// --- Implementation Control Center & Smart Target File Guessing ---
function guessBestTargetFile(task, fileList = []) {
  if (!fileList || fileList.length === 0) return (task && task.target_file) || activeFilePath || "";
  const paths = fileList.map(f => (typeof f === "object" && f ? f.path : f)).filter(Boolean);
  if (paths.length === 0) return (task && task.target_file) || activeFilePath || "";

  const text = `${task.title || ""} ${task.description || ""} ${task.suggested_prompt || ""} ${task.category || ""}`.toLowerCase();

  // 0. If task already has an explicit target_file from Geppy's backend file-tree analysis, honor it
  if (task && task.target_file) {
    const tfNorm = String(task.target_file).replace(/\\/g, "/").trim();
    const exactMatch = paths.find(p => p.toLowerCase() === tfNorm.toLowerCase());
    if (exactMatch && !(/^index\.html$/i.test(exactMatch) && paths.some(p => /\.(jsx|tsx|js|ts|vue)$/i.test(p)) && !/index\.html|favicon|meta|head|title/i.test(text))) {
      return exactMatch;
    }
  }

  // 1. Check if the task text explicitly names a file path or basename from the project (longest first)
  const sortedByLen = [...paths].sort((a, b) => b.length - a.length);
  for (const p of sortedByLen) {
    if (text.includes(p.toLowerCase())) {
      return p;
    }
  }
  for (const p of sortedByLen) {
    const base = p.split("/").pop().toLowerCase();
    if (base === "index.html" && !text.includes("index.html")) continue;
    const escaped = base.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (new RegExp(`(?<![a-z0-9_/-])${escaped}(?![a-z0-9_])`, "i").test(text)) {
      return p;
    }
  }

  // 2. Match specific module stems (e.g. physics.js, audio.js, levels.js, launcher_service.py)
  if (/physics|friction|damping|velocity|speed|acceleration|ball|bounce|bounciness|collision|gravity|slope|stopping|drag|resistance/i.test(text)) {
    const physFile = paths.find(p => /physics\.(js|ts|jsx|tsx|py)$/i.test(p));
    if (physFile) return physFile;
  }
  if (/audio|sound|music|sfx|beep|mute|volume/i.test(text)) {
    const audioFile = paths.find(p => /audio|sound\.(js|ts|jsx|tsx)$/i.test(p));
    if (audioFile) return audioFile;
  }
  if (/level|course|preset|campaign|hole|par\b/i.test(text)) {
    const lvlFile = paths.find(p => /level|course\.(js|ts|jsx|tsx)$/i.test(p));
    if (lvlFile) return lvlFile;
  }
  for (const p of paths) {
    const base = p.split("/").pop().toLowerCase();
    const stem = base.replace(/\.[^.]+$/, "");
    if (stem.length >= 4 && !["index", "main", "style", "styles", "types", "utils", "config"].includes(stem)) {
      const singular = stem.endsWith("s") ? stem.slice(0, -1) : stem;
      const escapedStem = singular.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      if (new RegExp(`\\b${escapedStem}s?\\b`, "i").test(text)) {
        return p;
      }
    }
  }

  const pickBestHtml = () =>
    paths.find(p => /static\/index\.html$/i.test(p)) ||
    paths.find(p => /src\/index\.html$/i.test(p)) ||
    paths.find(p => /public\/index\.html$/i.test(p)) ||
    paths.find(p => /index\.html$/i.test(p));

  const pickMainAppCode = () =>
    paths.find(p => /client\/src\/App\.(tsx|jsx|js|ts|vue)$/i.test(p)) ||
    paths.find(p => /src\/App\.(tsx|jsx|js|ts|vue)$/i.test(p)) ||
    paths.find(p => /(^|\/)(app|main)\.(tsx|jsx|vue|svelte|js)$/i.test(p)) ||
    paths.find(p => /static\/index\.html$/i.test(p));

  // 3. Icon or Favicon or Head or Metadata -> index.html / public/index.html / manifest.json
  if (/favicon|meta\s+tag|head\s+tag|page\s+title|manifest/i.test(text)) {
    const m = pickBestHtml() || paths.find(p => /manifest\.json$/i.test(p));
    if (m) return m;
  }
  // 4. Pure Styling, CSS, Theme, Color, Font -> CSS files
  if (/stylesheet|css|theme|dark mode|font|gradient/i.test(text) && !/function|state|logic|click|handler|modal|component/i.test(text)) {
    const m = paths.find(p => /\.(css|scss|sass|less)$/i.test(p)) || pickMainAppCode() || pickBestHtml();
    if (m) return m;
  }
  // 5. Backend, API, Route, Database, Endpoint -> Python / Node server files
  if (/\b(endpoint|route|backend|database|sqlite|express|fastapi|server)\b/i.test(text)) {
    const m = paths.find(p => /(main|server|app|api|routes)\.(py|js|ts)$/i.test(p));
    if (m) return m;
  }
  // 6. UI Component, Button, Modal, Drawer, View, Logic -> Main Frontend App code first!
  if (/component|button|modal|drawer|navbar|footer|card|table|view|page|screen|mobile|detect|toggle|state|click|input|slider/i.test(text)) {
    const m = pickMainAppCode() ||
              paths.find(p => /\.(jsx|tsx|vue|svelte|js)$/i.test(p)) ||
              pickBestHtml();
    if (m) return m;
  }
  // 7. If activeFilePath is valid and in the list, keep it (unless it's root index.html when static/index.html or src/App.tsx or js/app.js exists)
  if (activeFilePath && paths.includes(activeFilePath)) {
    if (/^index\.html$/i.test(activeFilePath)) {
      if (paths.some(p => /static\/index\.html$/i.test(p))) {
        return paths.find(p => /static\/index\.html$/i.test(p));
      }
      const mainCode = pickMainAppCode();
      if (mainCode && !/html|header|footer|title|meta|favicon/i.test(text)) {
        return mainCode;
      }
    }
    return activeFilePath;
  }

  // 8. Otherwise preferred default
  const defaultFile = pickMainAppCode() ||
                      pickBestHtml() ||
                      paths.find(p => /(app|main)\.(jsx|tsx|js|py)$/i.test(p)) ||
                      paths[0];
  return defaultFile || "";
}

async function openImplementationModal(task, card = null) {
  currentImplTask = task;
  currentImplCard = card;

  if (!implementationModal) return;

  // Populate Task Info
  if (implModalTitle) implModalTitle.innerText = task.title || "Implementation Task";
  if (implModalDesc) implModalDesc.innerText = task.description || task.suggested_prompt || "Execute this feature/design modification with AI assistance.";
  if (implModalCategory) {
    const cat = (task.category || "feature").toLowerCase();
    implModalCategory.className = `task-tag ${cat}`;
    implModalCategory.innerText = task.category || "Task";
  }
  if (implModalStatusBadge) {
    implModalStatusBadge.className = task.completed ? "impl-badge-done" : "impl-badge-pending";
    implModalStatusBadge.innerText = task.completed ? "Already Completed" : "Pending Implementation";
  }

  // Populate Target File Select
  if (implTargetFileSelect) {
    implTargetFileSelect.innerHTML = '<option value="">Loading files...</option>';
    let files = appFileList || [];
    if (files.length === 0 && activeApp) {
      try {
        const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/files/tree`);
        if (res.ok) {
          const d = await res.json();
          files = d.files || [];
          appFileList = files;
        }
      } catch (e) {}
    }

    implTargetFileSelect.innerHTML = "";
    files.forEach(f => {
      const opt = document.createElement("option");
      opt.value = f.path;
      opt.innerText = f.path;
      implTargetFileSelect.appendChild(opt);
    });

    // Best guessed target file
    const guessed = guessBestTargetFile(task, files);
    if (guessed) {
      implTargetFileSelect.value = guessed;
      if (implSuggestedTag) {
        implSuggestedTag.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Auto-Suggested: <code>${guessed.split("/").pop()}</code>`;
        implSuggestedTag.style.display = "inline-flex";
      }
    } else {
      if (implSuggestedTag) implSuggestedTag.style.display = "none";
    }
  }

  // Reset new file box & tracker
  if (implNewFileBox) implNewFileBox.classList.add("hidden");
  if (implNewFilePath) implNewFilePath.value = "";
  if (implProgressTracker) implProgressTracker.classList.add("hidden");
  if (implFeedbackBanner) implFeedbackBanner.classList.add("hidden");

  // Show modal
  implementationModal.style.display = "flex";
  implementationModal.classList.remove("hidden");
}

function closeImplementationModal() {
  if (implementationModal) {
    implementationModal.style.display = "none";
    implementationModal.classList.add("hidden");
  }
  currentImplTask = null;
  currentImplCard = null;
}

function selectImplMode(mode) {
  if (mode === "review") {
    if (radioImplReview) radioImplReview.checked = true;
    if (modeCardReview) modeCardReview.classList.add("active");
    if (modeCardDirect) modeCardDirect.classList.remove("active");
  } else {
    if (radioImplDirect) radioImplDirect.checked = true;
    if (modeCardDirect) modeCardDirect.classList.add("active");
    if (modeCardReview) modeCardReview.classList.remove("active");
  }
}

function setImplStep(stepNum, state) {
  const el = document.getElementById(`impl-step-${stepNum}`);
  if (!el) return;
  el.classList.remove("active", "done", "error");
  if (state === "active") el.classList.add("active");
  else if (state === "done") el.classList.add("done");
  else if (state === "error") el.classList.add("error");
}

async function executeImplementationFromModal() {
  if (!currentImplTask || !activeApp) return;

  const isNewFile = implNewFileBox && !implNewFileBox.classList.contains("hidden") && implNewFilePath?.value?.trim();
  const targetFile = isNewFile ? implNewFilePath.value.trim() : implTargetFileSelect?.value;

  if (!targetFile) {
    alert("Please select or enter a target file to implement.");
    return;
  }

  const isReviewMode = radioImplReview ? radioImplReview.checked : false;
  const shouldSaveDisk = implChkSaveDisk ? implChkSaveDisk.checked : true;
  const shouldReloadTab = implChkReloadTab ? implChkReloadTab.checked : true;
  const shouldMarkDone = implChkMarkDone ? implChkMarkDone.checked : true;

  const gName = getGeppyName(activeApp);
  const step2Label = document.getElementById("impl-step-2-label");
  if (step2Label) {
    step2Label.innerText = `Synthesizing code with ${gName}...`;
  }

  btnExecuteImplementation.disabled = true;
  btnExecuteImplementation.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Implementing...';

  if (implProgressTracker) implProgressTracker.classList.remove("hidden");
  if (implFeedbackBanner) implFeedbackBanner.classList.add("hidden");

  const taskTitle = currentImplTask.title || "Implementation Task";
  const instruction = currentImplTask.suggested_prompt || currentImplTask.title;

  // Post live conversational action bubble in Central Chat immediately!
  const actionBubble = startActionChatBubble({
    actionType: "implement",
    title: taskTitle,
    instruction: instruction,
    targetFile: targetFile
  });

  // Step 1: Target file verified
  setImplStep(1, "active");
  await new Promise(r => setTimeout(r, 150));
  setImplStep(1, "done");

  // Step 2: Fetch current code or initialize empty if new file
  setImplStep(2, "active");
  let currentCode = "";
  if (!isNewFile) {
    const cacheKey = getFileCacheKey(activeApp.slug, targetFile);
    const cached = editedFilesCache[cacheKey];
    if (targetFile === activeFilePath && codeEditor && codeEditor.value) {
      currentCode = codeEditor.value;
    } else if (cached && typeof cached.latestCode === "string") {
      currentCode = cached.latestCode;
    } else {
      try {
        const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/files/content?file_path=${encodeURIComponent(targetFile)}`);
        if (res.ok) {
          const d = await res.json();
          currentCode = d.content || "";
        }
      } catch (e) {
        console.warn("Could not read existing file content:", e);
      }
    }
  }

  updateActionChatBubbleStep(actionBubble, `${escapeHtml(gName)} is synthesizing updates for <code>${escapeHtml(targetFile)}</code>...`);

  try {
    const res = await fetchAntigravityApi("/api/extension/apply-design", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: activeApp.slug,
        file_path: targetFile,
        current_code: currentCode,
        instruction: instruction
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      setImplStep(2, "done");

      // Stay in the unified Central Chat view; only expand inline Code Drawer if user explicitly asked to Review in Editor
      ensureStudioChatVisible();
      if (isReviewMode) {
        toggleCodeDrawer(true);
      }

      // Load file into editor and preserve pre-edit baseline for Live Preview toggling
      activeFilePath = targetFile;
      if (fileSelect) fileSelect.value = targetFile;
      codeEditor.value = data.modified_code;
      recordEditedFileState(targetFile, currentCode, data.modified_code, isLivePreviewEnabled || shouldSaveDisk);
      isUnsaved = !(isLivePreviewEnabled || shouldSaveDisk);
      if (unsavedIndicator) unsavedIndicator.style.display = isUnsaved ? "inline-block" : "none";

      // Step 3 & 4: Sync according to Live Preview checkbox or modal options
      setImplStep(3, "active");
      updateActionChatBubbleStep(actionBubble, `Saving changes to <code>${escapeHtml(targetFile)}</code> &amp; hot-syncing Live Preview...`);
      if (isLivePreviewEnabled || shouldSaveDisk) {
        await syncLivePreviewToWindow(true, false);
      }
      setImplStep(3, "done");

      setImplStep(4, "active");
      if (shouldReloadTab && !isLivePreviewEnabled && shouldSaveDisk) {
        reloadActiveTabWithBadge(true, activeFilePath, { forceFullReload: false, modifiedCode: data.modified_code });
      }
      await refreshGitStatus();
      setImplStep(4, "done");

      if (implFeedbackBanner) {
        implFeedbackBanner.className = "drop-feedback success";
        implFeedbackBanner.innerHTML = `<i class="fa-solid fa-circle-check"></i> Applied to <code>${escapeHtml(targetFile)}</code>! Summary posted in Central Chat.`;
        implFeedbackBanner.classList.remove("hidden");
      }

      // Mark task completed
      if (shouldMarkDone) {
        currentImplTask.completed = true;
        selectedTaskIds.delete(currentImplTask.id);
        await saveBacklogToServer();
        renderBacklog();
        updateDesignerTaskPicker();
        updateBatchBarState();
      }

      logSessionChange("ai_implementation", `Implemented "${taskTitle}" into ${targetFile}`, targetFile, data.explanation);

      finishActionChatBubble(actionBubble, {
        success: true,
        actionType: "implement",
        title: taskTitle,
        targetFile: data.target_file || targetFile,
        explanation: data.explanation,
        baselineCode: typeof data.baseline_code === "string" ? data.baseline_code : currentCode,
        modifiedCode: data.modified_code,
        toolSteps: data.tool_steps || [],
        modifiedFiles: data.modified_files || [data.target_file || targetFile],
        engine: data.engine || "antigravity_sdk"
      });

      setTimeout(() => {
        closeImplementationModal();
      }, 900);

    } else {
      setImplStep(2, "error");
      finishActionChatBubble(actionBubble, {
        success: false,
        actionType: "implement",
        title: taskTitle,
        targetFile: targetFile,
        toolSteps: data.tool_steps || [],
        engine: data.engine || "antigravity_sdk",
        errorMsg: data.explanation || "API error"
      });
      if (implFeedbackBanner) {
        implFeedbackBanner.className = "drop-feedback error";
        implFeedbackBanner.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Implementation failed: ${escapeHtml(data.explanation || "API error")}`;
        implFeedbackBanner.classList.remove("hidden");
      }
    }
  } catch (err) {
    setImplStep(2, "error");
    finishActionChatBubble(actionBubble, {
      success: false,
      actionType: "implement",
      title: taskTitle,
      targetFile: targetFile,
      errorMsg: String(err)
    });
    if (implFeedbackBanner) {
      implFeedbackBanner.className = "drop-feedback error";
      implFeedbackBanner.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Error: ${escapeHtml(String(err))}`;
      implFeedbackBanner.classList.remove("hidden");
    }
  } finally {
    btnExecuteImplementation.disabled = false;
    btnExecuteImplementation.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> <span>🚀 Execute Implementation</span>';
  }
}

async function implementTaskDirectly(task, card = null, bypassModal = false) {
  if (!activeApp) {
    alert("Please select or detect an active app first.");
    return;
  }

  // If user has "Confirm Target / Options" enabled and not explicitly bypassed, open the Control Center!
  if (!bypassModal && chkAlwaysConfirmTarget && chkAlwaysConfirmTarget.checked) {
    openImplementationModal(task, card);
    return;
  }

  // 1. Stay in the unified Central Chat view (do NOT hide chat by switching away!)
  ensureStudioChatVisible();

  // 2. Determine best target file for this task
  if (!appFileList || appFileList.length === 0) {
    await loadFileTree(activeApp.slug);
  }
  const guessedFile = guessBestTargetFile(task, appFileList) || activeFilePath || (fileSelect && fileSelect.value);
  if (guessedFile && guessedFile !== activeFilePath) {
    if (fileSelect) fileSelect.value = guessedFile;
    await openFile(guessedFile);
  } else if (!activeFilePath && fileSelect && fileSelect.value) {
    await openFile(fileSelect.value);
  }

  if (!activeFilePath) {
    alert("Please select a target file in the File Bar above before implementing.");
    return;
  }

  const instruction = task.suggested_prompt || task.title;
  if (designerAiInput) designerAiInput.value = instruction;

  let pushBtn = card ? (card.querySelector(".btn-push-designer") || card.querySelector(".btn-chat-implement")) : null;
  const originalBtnHtml = pushBtn ? pushBtn.innerHTML : null;
  if (pushBtn) {
    pushBtn.disabled = true;
    pushBtn.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Working in Chat...';
  }

  btnApplyDesignerAi.disabled = true;
  btnApplyDesignerAi.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Implementing...';

  const baselineBeforeEdit = codeEditor.value;

  // 3. Immediately post Geppy's "I'm working on that now!" bubble in Central Chat
  const actionBubble = startActionChatBubble({
    actionType: "implement",
    title: task.title || "Task Implementation",
    instruction: instruction,
    targetFile: activeFilePath
  });

  try {
    const res = await fetchAntigravityApi("/api/extension/apply-design", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: activeApp.slug,
        file_path: activeFilePath,
        current_code: baselineBeforeEdit,
        instruction: instruction,
        save_to_disk: isLivePreviewEnabled
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      const finalTargetFile = data.target_file || activeFilePath;
      const baselineUsed = typeof data.baseline_code === "string" ? data.baseline_code : baselineBeforeEdit;
      if (finalTargetFile !== activeFilePath) {
        activeFilePath = finalTargetFile;
        if (fileSelect) fileSelect.value = finalTargetFile;
      }
      codeEditor.value = data.modified_code;
      recordEditedFileState(finalTargetFile, baselineUsed, data.modified_code, isLivePreviewEnabled);
      isUnsaved = !isLivePreviewEnabled;
      if (unsavedIndicator) unsavedIndicator.style.display = isUnsaved ? "inline-block" : "none";

      updateActionChatBubbleStep(actionBubble, `Saving changes in <code>${escapeHtml(finalTargetFile)}</code> &amp; syncing Live Preview...`);

      // Sync to disk & live window if Live Preview checkbox is checked
      if (isLivePreviewEnabled) {
        await syncLivePreviewToWindow(true, false);
      }

      // Automatically mark task complete in Backlog
      task.completed = true;
      selectedTaskIds.delete(task.id);
      await saveBacklogToServer();
      renderBacklog();
      updateDesignerTaskPicker();
      updateBatchBarState();

      logSessionChange("ai_implementation", `Implemented "${task.title}" in ${finalTargetFile}`, finalTargetFile, data.explanation);

      // Update Central Chat bubble with what happened!
      finishActionChatBubble(actionBubble, {
        success: true,
        actionType: "implement",
        title: task.title || "Task Implementation",
        targetFile: finalTargetFile,
        explanation: data.explanation,
        baselineCode: baselineUsed,
        modifiedCode: data.modified_code,
        toolSteps: data.tool_steps || [],
        modifiedFiles: data.modified_files || [finalTargetFile],
        engine: data.engine || "antigravity_sdk"
      });

      if (pushBtn) {
        pushBtn.innerHTML = '<i class="fa-solid fa-check text-emerald-400"></i> Done!';
        setTimeout(() => {
          if (originalBtnHtml) pushBtn.innerHTML = originalBtnHtml;
          pushBtn.disabled = false;
        }, 2200);
      }
    } else {
      finishActionChatBubble(actionBubble, {
        success: false,
        actionType: "implement",
        title: task.title || "Task Implementation",
        targetFile: activeFilePath,
        toolSteps: data.tool_steps || [],
        engine: data.engine || "antigravity_sdk",
        errorMsg: data.explanation || "Could not generate code"
      });
      if (pushBtn) {
        pushBtn.disabled = false;
        if (originalBtnHtml) pushBtn.innerHTML = originalBtnHtml;
      }
    }
  } catch (e) {
    finishActionChatBubble(actionBubble, {
      success: false,
      actionType: "implement",
      title: task.title || "Task Implementation",
      targetFile: activeFilePath,
      errorMsg: String(e)
    });
    if (pushBtn) {
      pushBtn.disabled = false;
      if (originalBtnHtml) pushBtn.innerHTML = originalBtnHtml;
    }
  } finally {
    btnApplyDesignerAi.disabled = false;
    btnApplyDesignerAi.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> <span>Apply</span>';
  }
}

function pushTaskToDesigner(task) {
  implementTaskDirectly(task);
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

  implementTaskDirectly(task);
}

// --- Backlog Batch Execution Engine ---
function updateBatchBarState() {
  if (!batchSelectedCount) return;
  batchSelectedCount.innerText = `${selectedTaskIds.size} selected`;
  if (btnRunBatchTasks) {
    btnRunBatchTasks.disabled = (selectedTaskIds.size === 0 || isBatchRunning);
    btnRunBatchTasks.innerHTML = `<i class="fa-solid fa-bolt"></i> <span>Run Batch (${selectedTaskIds.size})</span>`;
  }
  if (btnBatchMarkDone) {
    btnBatchMarkDone.disabled = (selectedTaskIds.size === 0 || isBatchRunning);
    btnBatchMarkDone.innerHTML = `<i class="fa-solid fa-folder-arrow-down"></i> <span>File to Done (${selectedTaskIds.size})</span>`;
  }
  if (chkBacklogSelectAll) {
    const uncompleted = backlogTasks.filter((t) => !t.completed);
    chkBacklogSelectAll.checked = (uncompleted.length > 0 && uncompleted.every((t) => selectedTaskIds.has(t.id)));
  }
}

async function markSelectedTasksDone() {
  if (selectedTaskIds.size === 0) return;
  let count = 0;
  backlogTasks.forEach((t) => {
    if (selectedTaskIds.has(t.id)) {
      t.completed = true;
      count++;
    }
  });
  selectedTaskIds.clear();
  updateBatchBarState();
  await saveBacklogToServer();
  renderBacklog();
  updateDesignerTaskPicker();
  logSessionChange("tasks", `Filed ${count} selected tasks to Done Pile`);
}

function toggleSelectAllTasks(selectAll) {
  if (selectAll) {
    backlogTasks.forEach((t) => {
      if (!t.completed) selectedTaskIds.add(t.id);
    });
  } else {
    selectedTaskIds.clear();
  }
  document.querySelectorAll(".chk-task-select").forEach((chk) => {
    const taskId = chk.dataset.taskId;
    chk.checked = selectedTaskIds.has(taskId);
  });
  updateBatchBarState();
}

function runNextBatch(count = 3) {
  if (isBatchRunning) return;
  const uncompleted = backlogTasks.filter((t) => !t.completed);
  if (uncompleted.length === 0) {
    alert("All backlog tasks are already completed! Add new tasks via brainstorming.");
    return;
  }
  const nextTasks = uncompleted.slice(0, count);
  selectedTaskIds.clear();
  nextTasks.forEach((t) => selectedTaskIds.add(t.id));
  document.querySelectorAll(".chk-task-select").forEach((chk) => {
    chk.checked = selectedTaskIds.has(chk.dataset.taskId);
  });
  updateBatchBarState();
  runSelectedBatch();
}

async function runSelectedBatch() {
  if (isBatchRunning) return;
  if (!activeApp) {
    alert("Please select or detect an active app first.");
    return;
  }
  const tasksToRun = backlogTasks.filter((t) => selectedTaskIds.has(t.id));
  if (tasksToRun.length === 0) {
    alert("Please select at least one task to run.");
    return;
  }

  isBatchRunning = true;
  updateBatchBarState();
  if (btnRunNextBatch) btnRunNextBatch.disabled = true;

  // 1. Stay in unified Central Chat view
  ensureStudioChatVisible();

  // 2. Ensure target file is loaded in editor
  if (!activeFilePath) {
    if (fileSelect && fileSelect.options.length > 0 && fileSelect.value) {
      await openFile(fileSelect.value);
    } else {
      await loadFileTree(activeApp.slug);
    }
  }

  if (!activeFilePath) {
    alert("Please select a target file in the File Bar before running batch.");
    isBatchRunning = false;
    updateBatchBarState();
    if (btnRunNextBatch) btnRunNextBatch.disabled = false;
    return;
  }

  if (batchProgressBanner) batchProgressBanner.classList.remove("hidden");
  let completedCount = 0;
  const total = tasksToRun.length;
  const baselineBeforeBatch = codeEditor.value;
  const completedSummaries = [];
  const batchToolSteps = [];
  const batchModifiedFiles = new Set();

  const batchBubble = startActionChatBubble({
    actionType: "batch",
    title: `${total} Selected Task${total === 1 ? "" : "s"}`,
    instruction: tasksToRun.map((t) => t.title).join(" • "),
    targetFile: activeFilePath
  });

  for (let i = 0; i < total; i++) {
    const task = tasksToRun[i];
    const bestFile = guessBestTargetFile(task, appFileList);
    if (bestFile && bestFile !== activeFilePath) {
      if (fileSelect) fileSelect.value = bestFile;
      await openFile(bestFile);
    }
    const pct = Math.round((i / total) * 100);
    if (batchProgressBar) batchProgressBar.style.width = `${pct}%`;
    if (batchProgressPercent) batchProgressPercent.innerText = `${pct}%`;
    if (batchProgressStatus) {
      batchProgressStatus.innerHTML = `<i class="fa-solid fa-spinner animate-spin"></i> [${i + 1}/${total}] Applying "${escapeHtml(task.title)}"...`;
    }
    updateActionChatBubbleStep(
      batchBubble,
      `[${i + 1}/${total}] Antigravity Agent implementing <strong>${escapeHtml(task.title)}</strong> in <code>${escapeHtml(activeFilePath)}</code>...`
    );

    const beforeTaskCode = codeEditor.value;
    const instruction = task.suggested_prompt || task.title;
    try {
      const res = await fetchAntigravityApi("/api/extension/apply-design", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          slug: activeApp.slug,
          file_path: activeFilePath,
          current_code: beforeTaskCode,
          instruction: instruction,
          save_to_disk: true
        })
      });

      const data = await res.json();
      if (Array.isArray(data.tool_steps)) {
        batchToolSteps.push(...data.tool_steps);
      }
      if (Array.isArray(data.modified_files)) {
        data.modified_files.forEach((f) => batchModifiedFiles.add(f));
      }
      if (res.ok && data.success) {
        const finalTargetFile = data.target_file || activeFilePath;
        batchModifiedFiles.add(finalTargetFile);
        const baselineUsed = typeof data.baseline_code === "string" ? data.baseline_code : beforeTaskCode;
        if (finalTargetFile !== activeFilePath) {
          activeFilePath = finalTargetFile;
          if (fileSelect) fileSelect.value = finalTargetFile;
        }
        codeEditor.value = data.modified_code;
        recordEditedFileState(finalTargetFile, baselineUsed, data.modified_code, true);
        isUnsaved = false;
        if (unsavedIndicator) unsavedIndicator.style.display = "none";
        if (!data.saved_to_disk) {
          await saveCurrentFile();
        }

        task.completed = true;
        selectedTaskIds.delete(task.id);
        completedCount++;
        completedSummaries.push(`• **${task.title}** [\`${finalTargetFile}\`]: ${data.explanation || "Applied successfully."}`);
        logSessionChange("ai_implementation", `[Batch] Implemented "${task.title}" in ${finalTargetFile}`, finalTargetFile, data.explanation);
      } else {
        completedSummaries.push(`• ⚠️ **${task.title}**: ${data.explanation || "Skipped / failed."}`);
        console.warn(`[Batch] Failed task "${task.title}":`, data.explanation);
      }
    } catch (err) {
      completedSummaries.push(`• ⚠️ **${task.title}**: ${String(err)}`);
      console.error(`[Batch] Error executing task "${task.title}":`, err);
    }

    await saveBacklogToServer();
    renderBacklog();
  }

  // Finalize
  if (batchProgressBar) batchProgressBar.style.width = "100%";
  if (batchProgressPercent) batchProgressPercent.innerText = "100%";
  if (batchProgressStatus) {
    batchProgressStatus.innerHTML = `<i class="fa-solid fa-circle-check text-emerald-400"></i> Batch finished! (${completedCount}/${total} tasks completed & saved)`;
  }

  finishActionChatBubble(batchBubble, {
    success: completedCount > 0,
    actionType: "batch",
    title: `Batch (${completedCount}/${total} Tasks Completed)`,
    targetFile: activeFilePath,
    explanation: completedSummaries.join("\n"),
    baselineCode: baselineBeforeBatch,
    modifiedCode: codeEditor.value,
    toolSteps: batchToolSteps,
    modifiedFiles: Array.from(batchModifiedFiles),
    engine: "antigravity_sdk",
    errorMsg: completedCount === 0 ? "None of the selected batch tasks could be applied." : ""
  });

  reloadActiveTab();
  await refreshGitStatus();

  setTimeout(() => {
    if (batchProgressBanner) batchProgressBanner.classList.add("hidden");
    isBatchRunning = false;
    updateBatchBarState();
    if (btnRunNextBatch) btnRunNextBatch.disabled = false;
  }, 3500);
}


// --- Asset Lab & App Image Management System ---

async function loadAppImages(slug) {
  if (!slug) return;
  if (appImagesGrid) {
    appImagesGrid.innerHTML = `
      <div class="images-empty-state">
        <i class="fa-solid fa-spinner animate-spin"></i>
        <p>Scanning ${escapeHtml(activeApp?.name || "app")} repository for image assets...</p>
      </div>
    `;
  }

  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${slug}/images`);
    if (res.ok) {
      const data = await res.json();
      activeAppImages = data.images || [];
      if (detectedImagesCount) detectedImagesCount.innerText = data.count || 0;
      if (imagesTotalSize) {
        imagesTotalSize.innerText = data.total_size_bytes < 1024 * 1024
          ? `${(data.total_size_bytes / 1024).toFixed(1)} KB`
          : `${(data.total_size_bytes / (1024 * 1024)).toFixed(1)} MB`;
      }

      // Update folder picker in Asset Lab
      if (extLabTargetFolder && data.folders && data.folders.length > 0) {
        extLabTargetFolder.innerHTML = "";
        data.folders.forEach((f) => {
          const opt = document.createElement("option");
          opt.value = f;
          opt.innerText = f === "." ? "root (/)" : `${f}/`;
          if (f === "assets") opt.selected = true;
          extLabTargetFolder.appendChild(opt);
        });
      }

      renderAppImagesGrid(activeAppImages, slug);
    } else {
      if (appImagesGrid) {
        appImagesGrid.innerHTML = `
          <div class="images-empty-state">
            <i class="fa-solid fa-triangle-exclamation text-amber"></i>
            <p>Could not scan images for this app.</p>
          </div>
        `;
      }
    }
  } catch (err) {
    console.error("Failed to load app images:", err);
    if (appImagesGrid) {
      appImagesGrid.innerHTML = `
        <div class="images-empty-state">
          <i class="fa-solid fa-circle-exclamation text-red-400"></i>
          <p>Error connecting to GitBridge: ${escapeHtml(String(err))}</p>
        </div>
      `;
    }
  }
}

function renderAppImagesGrid(images, slug) {
  if (!appImagesGrid) return;
  appImagesGrid.innerHTML = "";

  if (!images || images.length === 0) {
    appImagesGrid.innerHTML = `
      <div class="images-empty-state">
        <i class="fa-solid fa-photo-film"></i>
        <p>No image files found in this app's folder.</p>
        <span style="font-size: 10.5px; color: #64748b;">Drop or synthesize a new icon or graphic in the <strong>Asset Lab</strong> tab!</span>
      </div>
    `;
    return;
  }

  images.forEach((img) => {
    const card = document.createElement("div");
    card.className = `image-asset-card ${img.is_icon ? "is-app-icon" : ""}`;
    const imgUrl = `${SERVER_URL}${img.url}&t=${Date.now()}`;
    const extClean = (img.extension || "").replace(".", "").toUpperCase();

    card.innerHTML = `
      <div class="image-thumb-box">
        <img src="${imgUrl}" alt="${escapeHtml(img.filename)}" loading="lazy" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' viewBox=\\'0 0 40 40\\"><text y=\\'25\\' x=\\'10\\' font-size=\\'20\\'>🖼️</text></svg>'">
        ${img.is_icon ? '<span class="image-icon-badge" title="Designated App Icon"><i class="fa-solid fa-star"></i> App Icon</span>' : ""}
        <span class="image-format-badge">${escapeHtml(extClean)}</span>
      </div>
      <div class="image-meta-box">
        <div class="image-name" title="${escapeHtml(img.rel_path)}">${escapeHtml(img.filename)}</div>
        <div class="image-details">
          <span>${img.width && img.height ? `${img.width}×${img.height} • ` : ""}${escapeHtml(img.size_formatted)}</span>
          <span class="image-rel-folder" title="${escapeHtml(img.folder || "root")}">${escapeHtml(img.folder ? img.folder + "/" : "/")}</span>
        </div>
        <div class="image-card-actions">
          <button class="btn-image-action btn-view-full" title="Open full resolution in new tab">
            <i class="fa-solid fa-arrow-up-right-from-square"></i> View
          </button>
          <button class="btn-image-action btn-use-ref" title="Use as style reference in Asset Lab">
            <i class="fa-solid fa-flask"></i> In Lab
          </button>
        </div>
      </div>
    `;

    card.querySelector(".btn-view-full").addEventListener("click", () => {
      window.open(imgUrl, "_blank");
    });

    card.querySelector(".btn-use-ref").addEventListener("click", () => {
      switchAssetsSubTab("lab");
      extLabUploadedRefImageUrl = img.url;
      updateExtLabStyleRefPreview(img.filename, img.url);
      if (extLabStyle) {
        extLabStyle.value = `In the visual style of ${img.filename} (${img.rel_path}), transparent PNG output.`;
        extLabStyle.focus();
      }
    });

    appImagesGrid.appendChild(card);
  });
}

async function backupAppImages(slug) {
  if (!slug || !btnBackupAllImages) return;
  const origHtml = btnBackupAllImages.innerHTML;
  btnBackupAllImages.disabled = true;
  btnBackupAllImages.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> <span>Zipping...</span>';

  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${slug}/images/backup`, { method: "POST" });
    const data = await res.json();
    if (res.ok && data.success) {
      const fullUrl = `${SERVER_URL}${data.download_url}`;
      if (typeof chrome !== "undefined" && chrome.downloads && chrome.downloads.download) {
        chrome.downloads.download({ url: fullUrl, filename: data.zip_filename });
      } else {
        window.open(fullUrl, "_blank");
      }
      btnBackupAllImages.innerHTML = '<i class="fa-solid fa-check text-emerald-400"></i> <span>Backed up!</span>';
      setTimeout(() => {
        btnBackupAllImages.disabled = false;
        btnBackupAllImages.innerHTML = origHtml;
      }, 2500);
    } else {
      alert(`Backup failed: ${data.detail || data.message || "Unknown error"}`);
      btnBackupAllImages.disabled = false;
      btnBackupAllImages.innerHTML = origHtml;
    }
  } catch (err) {
    alert(`Backup error: ${err}`);
    btnBackupAllImages.disabled = false;
    btnBackupAllImages.innerHTML = origHtml;
  }
}

function populateExtLabBrandSelect() {
  if (!contextiles || contextiles.length === 0) return;

  // 1. Step 1: Brand / Character Grounding Dropdown
  if (extLabBrandSelect) {
    const currVal = extLabBrandSelect.value;
    extLabBrandSelect.innerHTML = '<option value="">🌟 Auto-Detect Brand / Character Likeness</option>';

    const brandContextiles = contextiles.filter((c) =>
      ["character", "brand_asset"].includes(c.archetype) ||
      ["geppybrand", "captain-geppy"].includes(c.name)
    );

    brandContextiles.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.name;
      const typeLabel = c.archetype === "brand_asset" ? " (BRAND)" : " (CHARACTER)";
      opt.innerText = `${c.title || c.name}${typeLabel}`;
      if (c.name === "geppybrand" && !currVal) {
        opt.selected = true;
      }
      extLabBrandSelect.appendChild(opt);
    });

    if (currVal) extLabBrandSelect.value = currVal;
  }

  // 2. Step 2: Style Contextile Dropdown
  if (extLabStyleContextile) {
    const currStyleVal = extLabStyleContextile.value;
    extLabStyleContextile.innerHTML = '<option value="">🌟 Select Style Contextile (or custom)</option>';

    const styleContextiles = contextiles.filter((c) =>
      ["style", "icon_set", "ui_component", "general"].includes(c.archetype) ||
      ["geppy-hex-icon", "galactic-icons", "70s-baseball-card"].includes(c.name)
    );

    styleContextiles.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.name;
      const icon = c.archetype === "icon_set" ? "🔶 " : (c.archetype === "style" ? "🎨 " : "✨ ");
      opt.innerText = `${icon}${c.title || c.name} (@${c.name})`;
      if (c.name === "geppy-hex-icon" && !currStyleVal) {
        opt.selected = true;
      }
      extLabStyleContextile.appendChild(opt);
    });

    if (currStyleVal) extLabStyleContextile.value = currStyleVal;
  }

  // 3. Step 3: Output Spec Dropdown
  if (extLabOutputPreset) {
    const currOutVal = extLabOutputPreset.value;
    extLabOutputPreset.innerHTML = `
      <option value="png-transparent" selected>✨ Transparent PNG (No Background / Isolated Icon)</option>
      <option value="icon-solid">🖼️ Standard App Icon (1024x1024 Solid / Gradient BG)</option>
      <option value="svg-vector">⚡ Scalable Vector Graphics (SVG Vector)</option>
    `;

    const outputContextiles = contextiles.filter((c) =>
      ["output", "output_spec"].includes(c.archetype)
    );

    outputContextiles.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.name;
      opt.innerText = `🏷️ ${c.title || c.name} (Spec @${c.name})`;
      extLabOutputPreset.appendChild(opt);
    });

    if (currOutVal) extLabOutputPreset.value = currOutVal;
  }

  updateExtLabBrandChip();
  updateExtLabStyleRefPreview();
}

function onShapePresetChanged() {
  if (!extLabShapePreset) return;
  const val = extLabShapePreset.value;

  if (val === "hex-orange-nobg") {
    if (extLabStyle) {
      extLabStyle.value = "Hexagonal icon with bold orange border (#F59E0B), metallic accents, isolated without background, transparent PNG output.";
    }
    if (extLabStyleContextile) {
      const opt = Array.from(extLabStyleContextile.options).find(o => o.value === "geppy-hex-icon");
      if (opt) extLabStyleContextile.value = "geppy-hex-icon";
    }
    if (extLabOutputPreset) {
      extLabOutputPreset.value = "png-transparent";
    }
  } else if (val === "squircle-glass") {
    if (extLabStyle) {
      extLabStyle.value = "Modern Apple iOS 3D glassmorphic squircle, translucent frosted glass, vibrant cyan and amber rim glow, smooth corner bevels.";
    }
    if (extLabStyleContextile) {
      const opt = Array.from(extLabStyleContextile.options).find(o => o.value === "galactic-icons");
      if (opt) extLabStyleContextile.value = "galactic-icons";
    }
    if (extLabOutputPreset) {
      extLabOutputPreset.value = "png-transparent";
    }
  } else if (val === "vault-gold-emerald") {
    if (extLabStyle) {
      extLabStyle.value = "Geometric 3D vault emblem shield with polished golden bevels and glowing emerald mint core, luxury metallic reflections.";
    }
    if (extLabOutputPreset) {
      extLabOutputPreset.value = "png-transparent";
    }
  } else if (val === "isometric-scene") {
    if (extLabStyle) {
      extLabStyle.value = "Dimensional isometric 3D composition with floating translucent glass plates, radiant starlight nodes, cosmic depth.";
    }
  } else if (val === "sticker-diecut") {
    if (extLabStyle) {
      extLabStyle.value = "Die-cut vinyl sticker with clean white contour border rim, high gloss laminate finish, isolated on transparent background.";
    }
    if (extLabOutputPreset) {
      const opt = Array.from(extLabOutputPreset.options).find(o => o.value.includes("diecut") || o.value.includes("sticker"));
      if (opt) extLabOutputPreset.value = opt.value;
      else extLabOutputPreset.value = "png-transparent";
    }
  } else if (val === "trading-card") {
    if (extLabStyle) {
      extLabStyle.value = "Authentic 1970s vintage Topps-style baseball card with aged cardboard margin, arched team banner, and offset litho print texture.";
    }
    if (extLabStyleContextile) {
      const opt = Array.from(extLabStyleContextile.options).find(o => o.value.includes("baseball") || o.value.includes("card"));
      if (opt) extLabStyleContextile.value = opt.value;
    }
    if (extLabOutputPreset) {
      extLabOutputPreset.value = "icon-solid";
    }
  }

  updateExtLabStyleRefPreview();
}

function onStyleContextileChanged() {
  if (!extLabStyleContextile) return;
  const val = extLabStyleContextile.value;
  if (!val) return;

  const ctx = (contextiles || []).find(c => c.name === val);
  if (!ctx) return;

  if (val === "geppy-hex-icon") {
    if (extLabShapePreset) extLabShapePreset.value = "hex-orange-nobg";
    if (extLabOutputPreset) extLabOutputPreset.value = "png-transparent";
    if (extLabStyle) {
      extLabStyle.value = ctx.assembled_prompt || ctx.reference_text || "Hexagonal icon with bold orange border (#F59E0B), metallic accents, isolated without background, transparent PNG output.";
    }
  } else if (val === "galactic-icons") {
    if (extLabShapePreset) extLabShapePreset.value = "squircle-glass";
    if (extLabStyle) {
      extLabStyle.value = ctx.assembled_prompt || ctx.reference_text || "Modern Apple iOS 3D glassmorphic squircle, translucent frosted glass, vibrant cyan and amber rim glow.";
    }
  } else if (val.includes("baseball") || val.includes("card")) {
    if (extLabShapePreset) extLabShapePreset.value = "trading-card";
    if (extLabOutputPreset) extLabOutputPreset.value = "icon-solid";
    if (extLabStyle) {
      extLabStyle.value = ctx.assembled_prompt || ctx.reference_text || "Authentic 1970s vintage baseball card with aged cardboard stock.";
    }
  } else if (ctx.assembled_prompt || ctx.reference_text) {
    if (extLabStyle) {
      extLabStyle.value = ctx.assembled_prompt || ctx.reference_text;
    }
  }

  updateExtLabStyleRefPreview();
}

function updateExtLabBrandChip() {
  if (!extLabBrandSelect || !extLabBrandChip) return;
  const brandVal = extLabBrandSelect.value;
  if (!brandVal) {
    extLabBrandChip.classList.add("hidden");
    return;
  }

  const brandCtx = (contextiles || []).find((c) => c.name === brandVal);
  if (brandCtx) {
    const imgUrl = (brandCtx.reference_images && brandCtx.reference_images[0]) || brandCtx.primary_image_url || brandCtx.reference_image_url;
    if (extLabBrandThumb) {
      if (imgUrl) {
        extLabBrandThumb.src = imgUrl.startsWith("http") ? imgUrl : `${SERVER_URL}${imgUrl}`;
        extLabBrandThumb.classList.remove("hidden");
      } else {
        extLabBrandThumb.classList.add("hidden");
      }
    }
    if (extLabBrandName) {
      extLabBrandName.innerText = brandCtx.title || brandCtx.name || "Brand Mascot";
    }
    extLabBrandChip.classList.remove("hidden");
  } else {
    extLabBrandChip.classList.add("hidden");
  }
}

function updateExtLabStyleRefPreview(filename = null, url = null) {
  if (!extLabRefPreviewBar || !extLabRefDropzone) return;

  const targetUrl = url || extLabUploadedRefImageUrl;
  if (targetUrl) {
    if (extLabRefThumb) {
      extLabRefThumb.src = targetUrl.startsWith("http") || targetUrl.startsWith("blob:") ? targetUrl : `${SERVER_URL}${targetUrl}`;
    }
    if (extLabRefName) {
      extLabRefName.innerText = filename || targetUrl.split("/").pop() || "style-reference.png";
    }
    if (extLabRefStatus) {
      extLabRefStatus.innerText = "Active Style Reference";
    }
    extLabRefPreviewBar.classList.remove("hidden");
    extLabRefDropzone.classList.add("hidden");
    return;
  }

  // Check if style contextile has an image reference
  const styleVal = extLabStyleContextile ? extLabStyleContextile.value : "";
  const styleCtx = (contextiles || []).find((c) => c.name === styleVal);
  const styleImg = styleCtx && ((styleCtx.reference_images && styleCtx.reference_images[0]) || styleCtx.primary_image_url || styleCtx.reference_image_url);

  if (styleImg) {
    if (extLabRefThumb) {
      extLabRefThumb.src = styleImg.startsWith("http") ? styleImg : `${SERVER_URL}${styleImg}`;
    }
    if (extLabRefName) {
      extLabRefName.innerText = `@${styleCtx.name} reference`;
    }
    if (extLabRefStatus) {
      extLabRefStatus.innerText = "Style Contextile Ref";
    }
    extLabRefPreviewBar.classList.remove("hidden");
    extLabRefDropzone.classList.add("hidden");
  } else {
    extLabRefPreviewBar.classList.add("hidden");
    extLabRefDropzone.classList.remove("hidden");
  }
}

async function handleExtLabRefFileUpload(file) {
  if (!file) return;

  if (extLabRefPreviewBar) extLabRefPreviewBar.classList.remove("hidden");
  if (extLabRefDropzone) extLabRefDropzone.classList.add("hidden");
  if (extLabRefName) extLabRefName.innerText = file.name;
  if (extLabRefStatus) extLabRefStatus.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Uploading...';
  if (extLabRefThumb) {
    try {
      extLabRefThumb.src = URL.createObjectURL(file);
    } catch (e) {}
  }

  const formData = new FormData();
  formData.append("files", file);

  try {
    const res = await fetch(`${SERVER_URL}/api/sot/upload-references`, {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (res.ok && data.files && data.files.length > 0) {
      const f = data.files[0];
      extLabUploadedRefImageUrl = f.url;
      if (extLabRefThumb) {
        extLabRefThumb.src = `${SERVER_URL}${f.url}?t=${Date.now()}`;
      }
      if (extLabRefStatus) {
        extLabRefStatus.innerHTML = '<span style="color: #34d399;"><i class="fa-solid fa-check"></i> Style Grounded</span>';
      }
      if (extLabStyle && (!extLabStyle.value || extLabStyle.value.includes("Hexagonal icon with bold orange border"))) {
        extLabStyle.value = `Grounded directly in visual style and materials of ${file.name}, isolated without background, transparent PNG output.`;
      }
    } else {
      if (extLabRefStatus) extLabRefStatus.innerHTML = '<span style="color: #f87171;">Upload failed</span>';
    }
  } catch (err) {
    if (extLabRefStatus) extLabRefStatus.innerHTML = `<span style="color: #f87171;">Error: ${err}</span>`;
  }
}

function useActiveAppIconAsRef() {
  if (!activeApp) {
    alert("Please select or open an application first.");
    return;
  }

  // Look for designated icon in activeAppImages or activeApp.icon_url
  let iconImg = (activeAppImages || []).find((img) => img.is_icon) ||
                (activeAppImages || []).find((img) => (img.filename || "").toLowerCase().includes("icon")) ||
                (activeAppImages || [])[0];

  let targetUrl = null;
  let targetName = null;

  if (iconImg) {
    targetUrl = iconImg.url;
    targetName = iconImg.filename;
  } else if (activeApp.icon_url) {
    targetUrl = activeApp.icon_url;
    targetName = `${activeApp.name} Icon`;
  }

  if (targetUrl) {
    extLabUploadedRefImageUrl = targetUrl;
    updateExtLabStyleRefPreview(targetName, targetUrl);
    if (extLabStyle) {
      extLabStyle.value = `In the visual style and iconography of ${targetName}, transparent PNG output.`;
    }
  } else {
    alert(`No existing icon image found in ${activeApp.name}. Drop an icon image into the upload box to use as reference!`);
  }
}

function removeExtLabRef() {
  extLabUploadedRefImageUrl = null;
  if (extLabRefFile) extLabRefFile.value = "";
  if (extLabRefThumb) extLabRefThumb.src = "";
  updateExtLabStyleRefPreview();
}

async function brainstormExtConcepts() {
  if (!btnExtBrainstormConcepts) return;
  const appSlug = activeApp ? activeApp.slug : null;
  const purpose = extLabPurpose?.value?.trim() || `Official app icon and branding for ${activeApp?.name || "Application"}`;
  const style = extLabStyle?.value?.trim() || "Hexagonal icon with bold orange border, metallic accents, no background, transparent PNG output";
  const brand = extLabBrandSelect?.value || null;
  const styleCtx = extLabStyleContextile?.value || null;
  const outputPreset = extLabOutputPreset?.value || "png-transparent";

  // Gather all unique reference images from direct upload, brand, style contextile, and active app
  const refImages = [];
  if (extLabUploadedRefImageUrl) refImages.push(extLabUploadedRefImageUrl);
  if (brand) {
    const bCtx = (contextiles || []).find((c) => c.name === brand);
    if (bCtx && bCtx.reference_images) refImages.push(...bCtx.reference_images);
    if (bCtx && (bCtx.primary_image_url || bCtx.reference_image_url)) {
      refImages.push(bCtx.primary_image_url || bCtx.reference_image_url);
    }
  }
  if (styleCtx) {
    const sCtx = (contextiles || []).find((c) => c.name === styleCtx);
    if (sCtx && sCtx.reference_images) refImages.push(...sCtx.reference_images);
    if (sCtx && (sCtx.primary_image_url || sCtx.reference_image_url)) {
      refImages.push(sCtx.primary_image_url || sCtx.reference_image_url);
    }
  }
  const uniqueRefImages = Array.from(new Set(refImages.filter(Boolean)));

  btnExtBrainstormConcepts.disabled = true;
  const origHtml = btnExtBrainstormConcepts.innerHTML;
  btnExtBrainstormConcepts.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Brainstorming 3 Concepts...';

  if (extLabConceptsBox) extLabConceptsBox.classList.remove("hidden");
  if (extLabConceptsList) {
    extLabConceptsList.innerHTML = `
      <div style="color: #64748b; font-size: 11px; text-align: center; padding: 16px 0;">
        <i class="fa-solid fa-spinner animate-spin text-amber" style="font-size: 16px; margin-bottom: 6px; display: block;"></i>
        Synthesizing 3 bespoke design concepts with blueprints & SVG previews...
      </div>
    `;
  }

  try {
    const res = await fetch(`${SERVER_URL}/api/asset-lab/brainstorm-concepts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        purpose: purpose,
        style_directive: style,
        app_slug: appSlug,
        brand_contextile: brand,
        style_contextile: styleCtx,
        output_contextile: outputPreset,
        reference_images: uniqueRefImages
      })
    });

    const data = await res.json();
    const concepts = data.concepts || [];
    renderExtBrainstormedConcepts(concepts);
  } catch (err) {
    console.error("Brainstorm error:", err);
    if (extLabConceptsList) {
      extLabConceptsList.innerHTML = `<div style="color: #f87171; font-size: 11px; padding: 8px;">Error generating concepts: ${escapeHtml(String(err))}</div>`;
    }
  } finally {
    btnExtBrainstormConcepts.disabled = false;
    btnExtBrainstormConcepts.innerHTML = origHtml;
  }
}

function renderExtBrainstormedConcepts(concepts) {
  if (!extLabConceptsList) return;
  extLabConceptsList.innerHTML = "";

  if (!concepts || concepts.length === 0) {
    extLabConceptsList.innerHTML = '<div style="color: #64748b; font-size: 11px; text-align: center;">No concepts generated. Try refining your purpose or style!</div>';
    return;
  }

  concepts.forEach((c, idx) => {
    const card = document.createElement("div");
    card.className = "lab-concept-card";

    const paletteHtml = (c.color_palette || []).map((color) => {
      const m = color.match(/#[0-9a-fA-F]{6}/);
      const hex = m ? m[0] : "#818cf8";
      return `<span class="lab-palette-dot" style="background: ${hex};" title="${escapeHtml(color)}"></span>`;
    }).join("");

    const svgPreview = c.svg_preview || c.svg_preview_code || "";

    card.innerHTML = `
      <div class="concept-header">
        <span class="concept-num">#${idx + 1}</span>
        <strong class="concept-title">${escapeHtml(c.title || c.name || `Concept ${idx + 1}`)}</strong>
        <span class="concept-style-tag">${escapeHtml(c.style_tag || c.style_label || "DESIGN")}</span>
      </div>
      <p class="concept-pitch">${escapeHtml(c.pitch || c.description || "")}</p>
      
      ${svgPreview ? `<div class="concept-svg-thumb">${svgPreview}</div>` : ""}

      <div class="concept-palette-row">
        <span style="font-size: 10px; color: #94a3b8; margin-right: 4px;">Palette:</span>
        <div style="display: flex; gap: 4px;">${paletteHtml}</div>
      </div>

      <div class="concept-actions">
        <button class="btn-select-concept primary" title="Load this concept into the Drop-In Station">
          <i class="fa-solid fa-cloud-arrow-down"></i> Drop this Concept
        </button>
        <button class="btn-select-concept secondary" title="Synthesize high-fidelity PNG of this concept">
          <i class="fa-solid fa-wand-magic-sparkles"></i> Synthesize PNG
        </button>
      </div>
    `;

    // Drop this Concept (uses SVG or blueprint)
    card.querySelector(".btn-select-concept.primary").addEventListener("click", () => {
      selectConceptForDrop(c);
    });

    // Synthesize PNG
    card.querySelector(".btn-select-concept.secondary").addEventListener("click", () => {
      instantSynthesizeExtAsset(c.master_prompt || c.blueprint, c.title, c.color_palette);
    });

    extLabConceptsList.appendChild(card);
  });
}

function selectConceptForDrop(concept) {
  const svg = concept.svg_preview || concept.svg_preview_code;
  const title = concept.title || concept.name || "App Concept";
  const cleanName = title.toLowerCase().replace(/[^a-z0-9]/g, "_");

  if (svg) {
    currentSynthesizedAsset = {
      type: "svg",
      content: svg,
      filename: `${cleanName}.svg`,
      title: title,
      colors: concept.color_palette || []
    };

    if (extLabPreviewSvg) {
      extLabPreviewSvg.innerHTML = svg;
      extLabPreviewSvg.classList.remove("hidden");
    }
    if (extLabPreviewImg) {
      extLabPreviewImg.removeAttribute("src");
      extLabPreviewImg.classList.add("hidden");
    }
  } else {
    // If no SVG, trigger instant synthesis
    instantSynthesizeExtAsset(concept.master_prompt || concept.blueprint, title, concept.color_palette);
    return;
  }

  if (extLabAssetTitle) extLabAssetTitle.innerText = title;
  if (extLabFilename) extLabFilename.value = currentSynthesizedAsset.filename;

  // Render palette chips
  if (extLabPaletteChips) {
    extLabPaletteChips.innerHTML = (concept.color_palette || []).map((color) => {
      const m = color.match(/#[0-9a-fA-F]{6}/);
      const hex = m ? m[0] : "#818cf8";
      return `<span class="lab-palette-dot" style="background: ${hex};" title="${escapeHtml(color)}"></span>`;
    }).join("");
  }

  if (extLabDropDock) {
    extLabDropDock.classList.remove("hidden");
    extLabDropDock.scrollIntoView({ behavior: "smooth" });
  }
}

async function instantSynthesizeExtAsset(promptOverride = null, nameOverride = null, paletteOverride = null) {
  if (!btnExtInstantSynthesize) return;
  const appSlug = activeApp ? activeApp.slug : null;
  const title = nameOverride || `Icon for ${activeApp?.name || "App"}`;
  const purpose = extLabPurpose?.value?.trim() || `Official app icon for ${activeApp?.name || "Application"}`;
  const style = extLabStyle?.value?.trim() || "Hexagonal icon with bold orange border, metallic accents, no background, transparent PNG output";
  const outputPreset = extLabOutputPreset?.value || "png-transparent";
  const shapePreset = extLabShapePreset?.value || "hex-orange-nobg";

  const isHex = shapePreset === "hex-orange-nobg" || (style + " " + purpose).toLowerCase().includes("hex");
  const isTransparent = outputPreset === "png-transparent" || (style + " " + purpose).toLowerCase().includes("no background") || (style + " " + purpose).toLowerCase().includes("transparent");
  const targetFormat = isTransparent ? "transparent_png" : "app_icon";

  let masterPrompt = promptOverride;
  if (!masterPrompt) {
    masterPrompt = `${purpose}. Style: ${style}.`;
    if (isHex) masterPrompt += " 6-sided hexagonal app icon silhouette with bold orange border (#F59E0B) and metallic bevels.";
    if (isTransparent) masterPrompt += " Isolated on clean transparent background (no background), transparent PNG output.";
  }

  const ingredientsSummary = [];
  const refImages = [];
  if (extLabUploadedRefImageUrl) refImages.push(extLabUploadedRefImageUrl);

  if (extLabBrandSelect?.value) {
    const brandCtx = (contextiles || []).find(c => c.name === extLabBrandSelect.value);
    if (brandCtx) {
      ingredientsSummary.push({ ...brandCtx, role: "subject" });
    }
  }
  if (extLabStyleContextile?.value) {
    const styleCtx = (contextiles || []).find(c => c.name === extLabStyleContextile.value);
    if (styleCtx) {
      ingredientsSummary.push({ ...styleCtx, role: "style" });
    }
  }
  const uniqueRefImages = Array.from(new Set(refImages.filter(Boolean)));

  const origHtml = btnExtInstantSynthesize.innerHTML;
  btnExtInstantSynthesize.disabled = true;
  btnExtInstantSynthesize.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Synthesizing...';

  try {
    const res = await fetch(`${SERVER_URL}/api/asset-lab/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title,
        master_prompt: masterPrompt,
        target_format: targetFormat,
        aspect_ratio: "1:1",
        color_palette: paletteOverride || (isHex ? ["#F59E0B", "#1E1B4B", "#06B6D4", "#0F172A"] : ["#06B6D4", "#F59E0B", "#1E1B4B"]),
        composition_blueprint: isHex ? "Hexagonal icon with bold orange border and metallic accents" : "Squircle app icon",
        ingredients_summary: ingredientsSummary,
        reference_images: uniqueRefImages,
        app_slug: appSlug
      })
    });

    const data = await res.json();
    if (res.ok && data.file_url) {
      currentSynthesizedAsset = {
        type: "url",
        url: data.file_url,
        filename: data.filename || "icon.png",
        title: data.title || title,
        colors: data.color_palette || []
      };

      if (extLabPreviewSvg) {
        extLabPreviewSvg.innerHTML = "";
        extLabPreviewSvg.classList.add("hidden");
      }
      if (extLabPreviewImg) {
        extLabPreviewImg.src = `${SERVER_URL}${data.file_url}?t=${Date.now()}`;
        extLabPreviewImg.classList.remove("hidden");
      }

      if (extLabAssetTitle) extLabAssetTitle.innerText = data.title || title;
      if (extLabFilename) extLabFilename.value = data.filename || "icon.png";

      if (extLabPaletteChips) {
        extLabPaletteChips.innerHTML = (data.color_palette || []).map((color) => {
          const m = color.match(/#[0-9a-fA-F]{6}/);
          const hex = m ? m[0] : "#818cf8";
          return `<span class="lab-palette-dot" style="background: ${hex};" title="${escapeHtml(color)}"></span>`;
        }).join("");
      }

      if (extLabDropDock) {
        extLabDropDock.classList.remove("hidden");
        extLabDropDock.scrollIntoView({ behavior: "smooth" });
      }
    } else {
      alert(`Synthesis error: ${data.detail || "Could not synthesize visual asset"}`);
    }
  } catch (err) {
    console.error("Synthesize error:", err);
    alert(`Synthesis failed: ${err}`);
  } finally {
    btnExtInstantSynthesize.disabled = false;
    btnExtInstantSynthesize.innerHTML = origHtml;
  }
}

// --- Modal: Save SOT Context Style Handlers ---
function openSaveContextileModal() {
  if (!modalSaveContextile) return;
  uploadedCtxStyleImageUrl = null;
  if (ctxStyleHandle) ctxStyleHandle.value = "geppy-hex-icon";
  if (ctxStyleTitle) ctxStyleTitle.value = "Geppy Hexagonal App Icon (Orange / No Background)";
  if (ctxStyleShape) ctxStyleShape.value = "hexagonal";
  if (ctxStyleAccentPicker) ctxStyleAccentPicker.value = "#F59E0B";
  if (ctxStyleAccentHex) ctxStyleAccentHex.value = "#F59E0B";
  if (ctxStyleBg) ctxStyleBg.value = "transparent";
  if (ctxStyleArchetype) ctxStyleArchetype.value = "icon_set";
  clearUploadedContextileFile();
  updateContextileModalPrompt();
  if (ctxStyleFeedback) ctxStyleFeedback.classList.add("hidden");
  modalSaveContextile.classList.remove("hidden");
  if (ctxStyleHandle) ctxStyleHandle.focus();
}

function closeSaveContextileModal() {
  if (modalSaveContextile) modalSaveContextile.classList.add("hidden");
}

function updateContextileModalPrompt() {
  if (!ctxStylePrompt) return;
  const shape = ctxStyleShape?.value || "hexagonal";
  const accent = ctxStyleAccentHex?.value || "#F59E0B";
  const bg = ctxStyleBg?.value || "transparent";
  const shapeLabel = shape === "hexagonal" ? "Hexagonal 6-sided" : (shape === "squircle" ? "3D glassmorphic squircle" : `${shape}`);
  const bgLabel = bg === "transparent" ? "isolated on clean transparent background (no background), transparent PNG output" : `set on ${bg.replace("_", " ")} background`;

  ctxStylePrompt.value = `${shapeLabel.charAt(0).toUpperCase() + shapeLabel.slice(1)} app icon with bold orange (${accent}) border and metallic accents, modern UI app icon standard, ${bgLabel}.`;
}

async function handleContextileFileUpload(file) {
  if (!file) return;
  if (ctxStyleFilePreview) ctxStyleFilePreview.classList.remove("hidden");
  if (ctxStyleUploadPrompt) ctxStyleUploadPrompt.classList.add("hidden");
  if (ctxStyleFileName) ctxStyleFileName.innerText = file.name;
  if (ctxStyleFileMeta) ctxStyleFileMeta.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Uploading & converting...';

  const formData = new FormData();
  formData.append("files", file);

  try {
    const res = await fetch(`${SERVER_URL}/api/sot/upload-references`, {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (res.ok && data.files && data.files.length > 0) {
      const f = data.files[0];
      uploadedCtxStyleImageUrl = f.url;
      if (ctxStylePreviewImg) {
        ctxStylePreviewImg.src = `${SERVER_URL}${f.url}?t=${Date.now()}`;
      }
      if (ctxStyleFileMeta) {
        ctxStyleFileMeta.innerHTML = `<span style="color: #34d399;"><i class="fa-solid fa-check"></i> ${f.was_converted ? "Converted to PNG" : "Ready"}</span>`;
      }
    } else {
      if (ctxStyleFileMeta) ctxStyleFileMeta.innerHTML = `<span style="color: #f87171;">Upload failed</span>`;
    }
  } catch (err) {
    if (ctxStyleFileMeta) ctxStyleFileMeta.innerHTML = `<span style="color: #f87171;">Error: ${err}</span>`;
  }
}

function clearUploadedContextileFile() {
  uploadedCtxStyleImageUrl = null;
  if (ctxStyleFile) ctxStyleFile.value = "";
  if (ctxStyleFilePreview) ctxStyleFilePreview.classList.add("hidden");
  if (ctxStyleUploadPrompt) ctxStyleUploadPrompt.classList.remove("hidden");
  if (ctxStylePreviewImg) ctxStylePreviewImg.src = "";
}

async function submitSaveContextile() {
  if (!btnSubmitSaveCtx) return;
  const rawHandle = ctxStyleHandle?.value?.trim() || "";
  const cleanHandle = rawHandle.toLowerCase().replace(/[^a-z0-9_\-]/g, "-").replace(/^-+|-+$/g, "");
  const title = ctxStyleTitle?.value?.trim() || cleanHandle;
  const shape = ctxStyleShape?.value || "hexagonal";
  const accent = ctxStyleAccentHex?.value?.trim() || "#F59E0B";
  const bg = ctxStyleBg?.value || "transparent";
  const archetype = ctxStyleArchetype?.value || "icon_set";
  const prompt = ctxStylePrompt?.value?.trim() || "";

  if (!cleanHandle) {
    alert("Please enter a valid handle name (e.g. geppy-hex-icon)");
    return;
  }

  btnSubmitSaveCtx.disabled = true;
  const origHtml = btnSubmitSaveCtx.innerHTML;
  btnSubmitSaveCtx.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Saving to SOT...';

  if (ctxStyleFeedback) {
    ctxStyleFeedback.className = "commit-feedback";
    ctxStyleFeedback.classList.remove("hidden");
    ctxStyleFeedback.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Persisting Context Style into SOT Fleet...';
  }

  const payload = {
    name: cleanHandle,
    title: title,
    archetype: archetype,
    reference_type: uploadedCtxStyleImageUrl ? "hybrid" : "text",
    reference_text: prompt,
    primary_image_url: uploadedCtxStyleImageUrl || null,
    reference_image_url: uploadedCtxStyleImageUrl || null,
    gallery_images: uploadedCtxStyleImageUrl ? [uploadedCtxStyleImageUrl] : [],
    modifiers: {
      shape: [shape === "hexagonal" ? "Hexagonal Silhouette" : shape],
      theme: [accent, bg === "transparent" ? "No Background" : "Dark Background", "Isolated Icon"],
      materials: ["Vibrant Orange Metal", "Dark Obsidian Glass", "Transparent Alpha Channel"],
      output: [bg === "transparent" ? "PNG Transparent" : "PNG Solid", "App Icon"]
    },
    tags: ["context-style", shape, "app-icon", archetype],
    assembled_prompt: prompt,
    app_slug: activeApp ? activeApp.slug : null
  };

  try {
    const res = await fetch(`${SERVER_URL}/api/sot/contextiles`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok && data.name) {
      if (ctxStyleFeedback) {
        ctxStyleFeedback.className = "commit-feedback success";
        ctxStyleFeedback.innerHTML = `<i class="fa-solid fa-circle-check"></i> Saved <strong>@${data.name}</strong> to SOT Fleet!`;
      }
      logSessionChange("context_style_created", `Created SOT Context Style @${data.name} (${data.title})`);

      // Reload contextiles
      await loadContextiles();

      // Automatically select this newly created style in Step 2 dropdown
      if (extLabStyleContextile) {
        extLabStyleContextile.value = data.name;
        onStyleContextileChanged();
      }

      setTimeout(() => {
        closeSaveContextileModal();
        if (ctxStyleFeedback) ctxStyleFeedback.classList.add("hidden");
      }, 1200);
    } else {
      if (ctxStyleFeedback) {
        ctxStyleFeedback.className = "commit-feedback error";
        ctxStyleFeedback.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> Save failed: ${escapeHtml(data.detail || data.message || "Unknown error")}`;
      }
    }
  } catch (err) {
    if (ctxStyleFeedback) {
      ctxStyleFeedback.className = "commit-feedback error";
      ctxStyleFeedback.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Save error: ${escapeHtml(String(err))}`;
    }
  } finally {
    btnSubmitSaveCtx.disabled = false;
    btnSubmitSaveCtx.innerHTML = origHtml;
  }
}

async function dropAssetToApp() {
  if (!activeApp) {
    alert("Please select or detect an active app first.");
    return;
  }
  if (!currentSynthesizedAsset) {
    alert("Please generate or select an asset first.");
    return;
  }

  const targetFolder = (extLabCustomFolder?.value?.trim() || extLabTargetFolder?.value || "assets").trim();
  const targetFilename = (extLabFilename?.value?.trim() || currentSynthesizedAsset.filename || "icon.png").trim();
  const setAppIcon = forceSetIcon !== null ? forceSetIcon : (chkSetAppIcon?.checked ?? true);
  const updateRefs = forceUpdateCode !== null ? forceUpdateCode : (chkUpdateCodeRefs?.checked ?? true);

  if (btnDropAssetToApp) btnDropAssetToApp.disabled = true;
  if (btnDropSaveOnly) btnDropSaveOnly.disabled = true;
  const origHtml = btnDropAssetToApp ? btnDropAssetToApp.innerHTML : "";
  if (btnDropAssetToApp) btnDropAssetToApp.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Processing...';

  if (dropAssetFeedback) {
    dropAssetFeedback.className = "drop-feedback";
    dropAssetFeedback.classList.remove("hidden");
    dropAssetFeedback.innerHTML = `<i class="fa-solid fa-spinner animate-spin"></i> Writing ${escapeHtml(targetFilename)} to ${escapeHtml(targetFolder)}/...`;
  }

  const payload = {
    target_folder: targetFolder,
    target_filename: targetFilename,
    set_as_app_icon: setAppIcon,
    update_code_references: updateRefs
  };

  if (currentSynthesizedAsset.type === "svg") {
    payload.svg_content = currentSynthesizedAsset.content;
  } else if (currentSynthesizedAsset.type === "url") {
    payload.asset_url = currentSynthesizedAsset.url;
  } else if (currentSynthesizedAsset.type === "base64") {
    payload.base64_data = currentSynthesizedAsset.data;
  }

  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/images/drop-asset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (res.ok && data.success) {
      dropAssetFeedback.className = "drop-feedback success";
      const isFileOnly = !setAppIcon && !updateRefs;
      dropAssetFeedback.innerHTML = `
        <div style="font-weight: 700; margin-bottom: 2px;">
          <i class="fa-solid fa-circle-check"></i> ${escapeHtml(data.message)}
        </div>
        <div style="font-size: 10px; opacity: 0.9;">
          📁 Path: <code>${escapeHtml(data.rel_path)}</code> (${(data.size_bytes / 1024).toFixed(1)} KB)<br>
          ${isFileOnly ? "ℹ️ Saved file only. Code references were not modified.<br>" : ""}
          ${data.app_icon_updated ? "🌟 Official GitBridge App Icon Updated!<br>" : ""}
          ${data.refs_updated && data.refs_updated.length > 0 ? `📝 Updated code references in: <code>${data.refs_updated.join(", ")}</code>` : ""}
        </div>
      `;

      logSessionChange("asset_drop", `Dropped ${data.filename} into ${data.rel_path}${data.app_icon_updated ? " (Set as app icon)" : ""}`, data.rel_path);

      // Reload app images & Git status
      await loadAppImages(activeApp.slug);
      await refreshGitStatus();

      // Optionally reload browser tab so the icon immediately reflects
      if (setAppIcon || updateRefs) {
        reloadActiveTab();
      }
    } else {
      dropAssetFeedback.className = "drop-feedback error";
      dropAssetFeedback.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> Drop failed: ${escapeHtml(data.detail || data.message || "Unknown error")}`;
    }
  } catch (err) {
    console.error("Drop asset error:", err);
    dropAssetFeedback.className = "drop-feedback error";
    dropAssetFeedback.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Drop failed: ${escapeHtml(String(err))}`;
  } finally {
    if (btnDropAssetToApp) {
      btnDropAssetToApp.disabled = false;
      btnDropAssetToApp.innerHTML = origHtml;
    }
    if (btnDropSaveOnly) btnDropSaveOnly.disabled = false;
  }
}

// Direct App Image Upload Handlers
function handleAppDirectUploadSelect(file) {
  if (!file) return;
  pendingAppUploadFile = file;
  if (appUploadPromptText) {
    appUploadPromptText.innerHTML = `<strong>Selected:</strong> ${escapeHtml(file.name)} (${(file.size / 1024).toFixed(1)} KB)`;
  }
  if (btnDoAppUpload) btnDoAppUpload.disabled = false;
}

async function executeDirectAppUpload() {
  if (!pendingAppUploadFile || !activeApp) return;

  const targetFolder = appUploadTargetFolder?.value || "assets";
  const setAsIcon = chkAppUploadSetIcon?.checked || false;
  const updateCode = chkAppUploadCodeRefs?.checked || false;

  const origHtml = btnDoAppUpload.innerHTML;
  btnDoAppUpload.disabled = true;
  btnDoAppUpload.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Uploading & Updating...';

  const formData = new FormData();
  formData.append("file", pendingAppUploadFile);
  formData.append("target_folder", targetFolder);
  formData.append("set_as_app_icon", setAsIcon);
  formData.append("update_code_references", updateCode);

  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/images/upload`, {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (res.ok && data.success) {
      if (appUploadFeedback) {
        appUploadFeedback.className = "drop-feedback success";
        appUploadFeedback.innerHTML = `
          <div style="font-weight: 700;"><i class="fa-solid fa-check"></i> ${escapeHtml(data.message)}</div>
          <div style="font-size: 10px;">
            📁 Saved to: <code>${escapeHtml(data.rel_path)}</code><br>
            ${data.app_icon_updated ? "🌟 Official GitBridge Icon updated!<br>" : ""}
            ${data.refs_updated?.length ? `📝 Code updated in: <code>${data.refs_updated.join(", ")}</code>` : ""}
          </div>
        `;
        appUploadFeedback.classList.remove("hidden");
      }
      logSessionChange("asset_upload", `Uploaded ${data.filename} into ${data.rel_path}`, data.rel_path);
      await loadAppImages(activeApp.slug);
      await refreshGitStatus();
      if (setAsIcon || updateCode) {
        reloadActiveTab();
      }
    } else {
      if (appUploadFeedback) {
        appUploadFeedback.className = "drop-feedback error";
        appUploadFeedback.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Upload failed: ${escapeHtml(data.detail || data.message || "Error")}`;
        appUploadFeedback.classList.remove("hidden");
      }
    }
  } catch (err) {
    if (appUploadFeedback) {
      appUploadFeedback.className = "drop-feedback error";
      appUploadFeedback.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Error: ${escapeHtml(String(err))}`;
      appUploadFeedback.classList.remove("hidden");
    }
  } finally {
    btnDoAppUpload.disabled = false;
    btnDoAppUpload.innerHTML = origHtml;
  }
}

// --- Live Designer, Code Editor & Live Window Preview Toggle ---
let isLivePreviewEnabled = true;
let preEditBaselineContent = "";
let latestEditedContent = "";
// Per-file edit cache keyed by `${slug}:${filePath}` -> { originalBaseline, previousStepBaseline, latestCode, savedToDisk }
const editedFilesCache = {};

function getFileCacheKey(slug, filePath) {
  return `${slug || (activeApp && activeApp.slug) || "app"}:${filePath || activeFilePath || ""}`;
}

function recordEditedFileState(filePath, baselineBeforeStep, modifiedCode, savedToDisk = true) {
  if (!activeApp || !filePath) return;
  const key = getFileCacheKey(activeApp.slug, filePath);
  const existing = editedFilesCache[key];
  editedFilesCache[key] = {
    originalBaseline: existing && typeof existing.originalBaseline === "string" ? existing.originalBaseline : baselineBeforeStep,
    previousStepBaseline: baselineBeforeStep,
    latestCode: modifiedCode,
    savedToDisk: Boolean(savedToDisk),
    updatedAt: Date.now()
  };
  preEditBaselineContent = baselineBeforeStep;
  latestEditedContent = modifiedCode;
}

const chkHeaderLivePreview = document.getElementById("chk-header-live-preview");
const lblHeaderLivePreview = document.getElementById("lbl-header-live-preview");
const chkDesignerLivePreview = document.getElementById("chk-designer-live-preview");
const livePreviewStatusPill = document.getElementById("live-preview-status-pill");

function initLivePreviewCheckboxes() {
  const onToggle = async (e) => {
    const checked = Boolean(e.target.checked);
    await onLivePreviewCheckboxChanged(checked);
  };
  if (chkHeaderLivePreview) chkHeaderLivePreview.addEventListener("change", onToggle);
  if (chkDesignerLivePreview) chkDesignerLivePreview.addEventListener("change", onToggle);
}
initLivePreviewCheckboxes();

function updateLivePreviewUiState() {
  if (chkHeaderLivePreview) chkHeaderLivePreview.checked = isLivePreviewEnabled;
  if (chkDesignerLivePreview) chkDesignerLivePreview.checked = isLivePreviewEnabled;

  if (lblHeaderLivePreview) {
    if (isLivePreviewEnabled) {
      lblHeaderLivePreview.style.background = "rgba(16, 185, 129, 0.14)";
      lblHeaderLivePreview.style.borderColor = "rgba(16, 185, 129, 0.4)";
      lblHeaderLivePreview.style.color = "#34d399";
    } else {
      lblHeaderLivePreview.style.background = "rgba(100, 116, 139, 0.16)";
      lblHeaderLivePreview.style.borderColor = "rgba(100, 116, 139, 0.4)";
      lblHeaderLivePreview.style.color = "#94a3b8";
    }
  }

  if (livePreviewStatusPill) {
    if (isLivePreviewEnabled) {
      livePreviewStatusPill.style.background = "rgba(16, 185, 129, 0.15)";
      livePreviewStatusPill.style.color = "#34d399";
      livePreviewStatusPill.style.borderColor = "rgba(16, 185, 129, 0.35)";
      livePreviewStatusPill.innerText = "● Live Preview ON (Saved & Hot-Synced)";
    } else {
      livePreviewStatusPill.style.background = "rgba(148, 163, 184, 0.15)";
      livePreviewStatusPill.style.color = "#cbd5e1";
      livePreviewStatusPill.style.borderColor = "rgba(148, 163, 184, 0.35)";
      livePreviewStatusPill.innerText = "○ Live Preview OFF (Original Shown)";
    }
  }
}

async function onLivePreviewCheckboxChanged(checked) {
  isLivePreviewEnabled = checked;
  updateLivePreviewUiState();
  if (!activeApp) return;

  const key = activeFilePath ? getFileCacheKey(activeApp.slug, activeFilePath) : null;
  const cached = key ? editedFilesCache[key] : null;
  const editedCode = (cached && cached.latestCode) || latestEditedContent || (codeEditor ? codeEditor.value : "");
  const baselineCode = (cached && cached.originalBaseline) || fileOriginalContent || preEditBaselineContent;

  if (codeEditor) {
    if (checked && editedCode) {
      codeEditor.value = editedCode;
    } else if (!checked && baselineCode) {
      codeEditor.value = baselineCode;
    }
  }

  await syncLivePreviewToWindow(checked, false, { isPreviewToggle: true });
}

async function syncLivePreviewToWindow(showEdited = true, lockAsNewBaseline = false, options = {}) {
  if (!activeApp) return false;
  if (!activeFilePath) {
    reloadActiveTabWithBadge(showEdited, "app", options);
    return true;
  }

  const key = getFileCacheKey(activeApp.slug, activeFilePath);
  const cached = editedFilesCache[key];

  // Determine which content to push to disk & the live window:
  // - If showEdited is true -> use latestEditedContent / cached.latestCode / codeEditor.value
  // - If showEdited is false -> revert the live window to originalBaseline (before Geppy's edits)
  if (showEdited && codeEditor && typeof codeEditor.value === "string" && !options.isPreviewToggle) {
    latestEditedContent = codeEditor.value;
    if (cached) cached.latestCode = codeEditor.value;
  }

  const contentToServe = showEdited
    ? ((cached && cached.latestCode) || latestEditedContent || (codeEditor && codeEditor.value))
    : ((cached && cached.originalBaseline) || fileOriginalContent || preEditBaselineContent);

  if (!contentToServe && contentToServe !== "") {
    reloadActiveTabWithBadge(showEdited, activeFilePath, options);
    return false;
  }

  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/files/content`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_path: activeFilePath,
        content: contentToServe,
        is_preview_revert: !showEdited
      })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      if (showEdited) {
        isUnsaved = false;
        if (unsavedIndicator) unsavedIndicator.style.display = "none";
        if (cached) cached.savedToDisk = true;
      }
      if (lockAsNewBaseline) {
        preEditBaselineContent = contentToServe;
        fileOriginalContent = contentToServe;
        latestEditedContent = contentToServe;
        isUnsaved = false;
        if (unsavedIndicator) unsavedIndicator.style.display = "none";
      }
      reloadActiveTabWithBadge(showEdited, activeFilePath, {
        forceFullReload: Boolean(options.forceFullReload),
        isPreviewToggle: Boolean(options.isPreviewToggle),
        modifiedCode: showEdited ? contentToServe : null
      });
      return true;
    }
  } catch (e) {
    console.warn("Live preview sync error:", e);
  }
  return false;
}

function reloadActiveTabWithBadge(isEditedPreview, filePathLabel, options = {}) {
  const lowerPath = String(filePathLabel || "").toLowerCase();
  const isPureCss = lowerPath.endsWith(".css");
  // Always perform a real tab reload for JS/TS/JSX/TSX/HTML/PY/App changes so the browser executes the updated code!
  const shouldFullReload = options.forceFullReload !== undefined
    ? Boolean(options.forceFullReload) || !isPureCss
    : !isPureCss;
  const modifiedCode = options.modifiedCode || (codeEditor ? codeEditor.value : "");

  const injectHotUpdateAndToast = (tabId, didFullReload) => {
    if (!chrome.scripting || !chrome.scripting.executeScript) return;

    // 1. Hot-swap stylesheets in MAIN world when not doing a full reload
    if (!didFullReload) {
      chrome.scripting.executeScript({
        target: { tabId },
        world: "MAIN",
        func: (previewOn, fpath) => {
          try {
            if (!previewOn) return;
            const lower = String(fpath || "").toLowerCase();
            if (lower.endsWith(".css")) {
              document.querySelectorAll('link[rel="stylesheet"]').forEach((link) => {
                const href = (link.getAttribute("href") || "").split("?")[0];
                if (href && !href.startsWith("https://fonts.") && !href.includes("font-awesome")) {
                  link.setAttribute("href", `${href}?t=${Date.now()}`);
                }
              });
            }
          } catch (_) {}
        },
        args: [
          Boolean(isEditedPreview),
          String(filePathLabel || "")
        ]
      }).catch(() => {});
    }

    // 2. Render non-destructive status toast badge in the page
    chrome.scripting.executeScript({
      target: { tabId },
      func: (previewOn, fpath, reloaded) => {
        const old = document.getElementById("geppy-live-preview-toast");
        if (old) old.remove();
        const pill = document.createElement("div");
        pill.id = "geppy-live-preview-toast";
        pill.style.cssText = [
          "position:fixed",
          "bottom:18px",
          "right:18px",
          "z-index:2147483647",
          "padding:8px 14px",
          "border-radius:999px",
          "font-family:system-ui,-apple-system,sans-serif",
          "font-size:12px",
          "font-weight:700",
          "box-shadow:0 10px 25px rgba(0,0,0,0.45)",
          "display:flex",
          "align-items:center",
          "gap:8px",
          "transition:opacity 0.4s ease",
          previewOn
            ? "background:rgba(6,78,59,0.95);color:#6ee7b7;border:1px solid #10b981;"
            : "background:rgba(30,41,59,0.95);color:#cbd5e1;border:1px solid #64748b;"
        ].join(";");

        const labelSpan = document.createElement("span");
        labelSpan.innerHTML = previewOn
          ? (reloaded
              ? `⚡ Live Preview Reloaded <span style="opacity:0.85;font-weight:500;">(${fpath})</span>`
              : `⚡ Live Preview • CSS Synced <span style="opacity:0.85;font-weight:500;">(${fpath})</span>`)
          : `⏪ Live Preview OFF (Original Baseline Shown)`;
        pill.appendChild(labelSpan);

        if (!reloaded) {
          const refreshBtn = document.createElement("button");
          refreshBtn.type = "button";
          refreshBtn.textContent = "↻ Refresh Tab";
          refreshBtn.title = "Click if you want a full browser tab reload.";
          refreshBtn.style.cssText = [
            "background:rgba(16,185,129,0.22)",
            "color:#ecfdf5",
            "border:1px solid rgba(110,231,183,0.45)",
            "border-radius:999px",
            "padding:2px 8px",
            "font-size:10.5px",
            "font-weight:700",
            "cursor:pointer",
            "margin-left:4px"
          ].join(";");
          refreshBtn.addEventListener("click", () => {
            window.location.reload();
          });
          pill.appendChild(refreshBtn);
        }

        document.body.appendChild(pill);
        setTimeout(() => {
          if (pill && pill.parentNode) {
            pill.style.opacity = "0";
            setTimeout(() => pill.remove(), 450);
          }
        }, 4800);
      },
      args: [Boolean(isEditedPreview), String(filePathLabel || "file"), Boolean(didFullReload)]
    }).catch(() => {});
  };

  const handleTab = (tabId) => {
    if (!tabId) return;
    if (shouldFullReload) {
      chrome.tabs.reload(tabId, { bypassCache: true }, () => {
        setTimeout(() => injectHotUpdateAndToast(tabId, true), 750);
      });
    } else {
      injectHotUpdateAndToast(tabId, false);
    }
  };

  if (typeof chrome !== "undefined" && chrome.tabs) {
    // Prefer the tab actually running activeApp's port/slug, otherwise use active tab in currentWindow
    let targetPort = "";
    if (activeApp && activeApp.live_url) {
      try { targetPort = new URL(activeApp.live_url).port; } catch (e) {}
    } else if (activeApp && isGitBridgeApp(activeApp)) {
      targetPort = "8000";
    }

    chrome.tabs.query({ currentWindow: true }, (tabs) => {
      if (!tabs || tabs.length === 0) return;
      let matchedTab = null;
      if (activeApp && activeApp.slug) {
        matchedTab = tabs.find((t) => t.id && tabAppMap[t.id] === activeApp.slug);
      }
      if (!matchedTab && targetPort) {
        matchedTab = tabs.find((t) => {
          if (!t.url) return false;
          try {
            const u = new URL(t.url);
            return ["localhost", "127.0.0.1", "0.0.0.0"].includes(u.hostname) && u.port === String(targetPort);
          } catch (e) {
            return false;
          }
        });
      }
      const chosen = matchedTab || tabs.find((t) => t.active) || tabs[0];
      if (chosen && chosen.id) {
        if (activeTabInstance) activeTabInstance.tabId = chosen.id;
        handleTab(chosen.id);
      }
    });
  }
}

async function loadFileTree(slug) {
  if (!slug) return;
  fileSelect.innerHTML = '<option value="">Loading files...</option>';

  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${slug}/files/tree`);
    if (!res.ok) return;

    const data = await res.json();
    const files = data.files || [];
    appFileList = files;

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

    // Prefer static/index.html or src/App.tsx over root stub index.html
    const preferred =
      files.find((f) => /static\/index\.html$/i.test(f.path)) ||
      files.find((f) => /src\/app\.(tsx|jsx|vue)$/i.test(f.path)) ||
      files.find((f) => /index\.html|app\.(jsx|tsx|vue|js)|main\.py/i.test(f.name)) ||
      files[0];

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

  // Before switching away from the current file, preserve any in-editor changes in editedFilesCache
  if (activeFilePath && codeEditor && isUnsaved) {
    recordEditedFileState(activeFilePath, preEditBaselineContent || fileOriginalContent, codeEditor.value, false);
  }

  activeFilePath = filePath;
  const key = getFileCacheKey(activeApp.slug, filePath);
  const cached = editedFilesCache[key];

  try {
    const res = await fetch(
      `${SERVER_URL}/api/apps/${activeApp.slug}/files/content?file_path=${encodeURIComponent(filePath)}`
    );
    if (!res.ok) return;

    const data = await res.json();
    const diskContent = data.content || "";
    const serverBaseline = typeof data.original_baseline === "string" ? data.original_baseline : diskContent;
    const serverLatest = typeof data.latest_edited === "string" ? data.latest_edited : diskContent;

    if (cached && !cached.savedToDisk && typeof cached.latestCode === "string") {
      fileOriginalContent = cached.originalBaseline || serverBaseline;
      preEditBaselineContent = cached.previousStepBaseline || serverBaseline;
      latestEditedContent = cached.latestCode;
      codeEditor.value = isLivePreviewEnabled ? cached.latestCode : fileOriginalContent;
      isUnsaved = true;
      if (unsavedIndicator) unsavedIndicator.style.display = "inline-block";
    } else {
      fileOriginalContent = (cached && cached.originalBaseline) || serverBaseline;
      preEditBaselineContent = (cached && cached.previousStepBaseline) || serverBaseline;
      latestEditedContent = (cached && cached.latestCode) || serverLatest;
      editedFilesCache[key] = {
        originalBaseline: fileOriginalContent,
        previousStepBaseline: preEditBaselineContent,
        latestCode: latestEditedContent,
        savedToDisk: true,
        updatedAt: Date.now()
      };
      codeEditor.value = isLivePreviewEnabled ? latestEditedContent : fileOriginalContent;
      isUnsaved = false;
      if (unsavedIndicator) unsavedIndicator.style.display = "none";
    }

    // Clear stale suggestions when switching files; only fetch LLM suggestions if the Suggestions Drawer is open
    proactiveSuggestions = [];
    if (proactiveSuggestionsDrawer && !proactiveSuggestionsDrawer.classList.contains("hidden")) {
      fetchProactiveSuggestions(activeApp.slug, filePath, codeEditor.value);
    }
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

async function applySuggestionDirect(sug, btnEl = null) {
  if (!activeApp) return;
  if (!activeFilePath && fileSelect && fileSelect.value) {
    await openFile(fileSelect.value);
  }
  if (!activeFilePath) return;

  const btn = btnEl || (typeof event !== "undefined" && event ? event.currentTarget : null);
  const originalHtml = btn ? btn.innerHTML : null;
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Applying...';
  }

  const baselineBeforeEdit = codeEditor.value;
  const instruction = sug.prompt || sug.title;

  const actionBubble = startActionChatBubble({
    actionType: "suggestion",
    title: sug.title || "Design Suggestion",
    instruction: instruction,
    targetFile: activeFilePath,
    userPromptText: `Apply design suggestion: ${sug.title}`
  });

  try {
    const res = await fetchAntigravityApi("/api/extension/apply-design", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: activeApp.slug,
        file_path: activeFilePath,
        current_code: baselineBeforeEdit,
        instruction: instruction,
        save_to_disk: isLivePreviewEnabled
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      const finalTargetFile = data.target_file || activeFilePath;
      const baselineUsed = typeof data.baseline_code === "string" ? data.baseline_code : baselineBeforeEdit;
      if (finalTargetFile !== activeFilePath) {
        activeFilePath = finalTargetFile;
        if (fileSelect) fileSelect.value = finalTargetFile;
      }
      codeEditor.value = data.modified_code;
      recordEditedFileState(finalTargetFile, baselineUsed, data.modified_code, isLivePreviewEnabled);
      isUnsaved = !isLivePreviewEnabled;
      if (unsavedIndicator) unsavedIndicator.style.display = isUnsaved ? "inline-block" : "none";
      logSessionChange("ai_suggestion", `Applied suggestion "${sug.title}" to ${finalTargetFile}`, finalTargetFile, data.explanation);

      updateActionChatBubbleStep(actionBubble, `Saving <code>${escapeHtml(finalTargetFile)}</code> to disk &amp; syncing Live Preview...`);
      if (isLivePreviewEnabled) {
        await syncLivePreviewToWindow(true, false);
      }

      finishActionChatBubble(actionBubble, {
        success: true,
        actionType: "suggestion",
        title: sug.title || "Design Suggestion",
        targetFile: finalTargetFile,
        explanation: data.explanation,
        baselineCode: baselineUsed,
        modifiedCode: data.modified_code,
        toolSteps: data.tool_steps || [],
        modifiedFiles: data.modified_files || [finalTargetFile],
        engine: data.engine || "antigravity_sdk"
      });
    } else {
      finishActionChatBubble(actionBubble, {
        success: false,
        actionType: "suggestion",
        title: sug.title || "Design Suggestion",
        targetFile: activeFilePath,
        toolSteps: data.tool_steps || [],
        engine: data.engine || "antigravity_sdk",
        errorMsg: data.explanation || "Unknown error"
      });
    }
  } catch (e) {
    finishActionChatBubble(actionBubble, {
      success: false,
      actionType: "suggestion",
      title: sug.title || "Design Suggestion",
      targetFile: activeFilePath,
      errorMsg: String(e)
    });
  } finally {
    if (btn) {
      btn.disabled = false;
      if (originalHtml) btn.innerHTML = originalHtml;
    }
  }
}

async function applyDesignerAiEdit(overrideInstruction = null, actionType = "fix") {
  const instruction = (typeof overrideInstruction === "string" ? overrideInstruction : (designerAiInput ? designerAiInput.value : "")).trim();
  if (!instruction || !activeApp) return;

  ensureStudioChatVisible();

  // Ensure the best target file for this instruction is loaded
  if (!appFileList || appFileList.length === 0) {
    await loadFileTree(activeApp.slug);
  }
  const guessed = guessBestTargetFile({ title: instruction, suggested_prompt: instruction }, appFileList) || activeFilePath || (fileSelect && fileSelect.value);
  if (guessed && guessed !== activeFilePath) {
    if (fileSelect) fileSelect.value = guessed;
    await openFile(guessed);
  }
  if (!activeFilePath) {
    alert("Please select a target file in the File Bar above.");
    return;
  }

  if (btnApplyDesignerAi) {
    btnApplyDesignerAi.disabled = true;
    btnApplyDesignerAi.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Working...';
  }
  if (btnChatDirectEdit) {
    btnChatDirectEdit.disabled = true;
    btnChatDirectEdit.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i>';
  }

  const baselineBeforeEdit = codeEditor.value;
  const shortTitle = instruction.length > 56 ? `${instruction.slice(0, 56)}...` : instruction;

  const actionBubble = startActionChatBubble({
    actionType: actionType,
    title: shortTitle,
    instruction: instruction,
    targetFile: activeFilePath,
    userPromptText: instruction
  });

  try {
    const res = await fetchAntigravityApi("/api/extension/apply-design", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: activeApp.slug,
        file_path: activeFilePath,
        current_code: baselineBeforeEdit,
        instruction: instruction,
        save_to_disk: isLivePreviewEnabled
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      const finalTargetFile = data.target_file || activeFilePath;
      const baselineUsed = typeof data.baseline_code === "string" ? data.baseline_code : baselineBeforeEdit;
      if (finalTargetFile !== activeFilePath) {
        activeFilePath = finalTargetFile;
        if (fileSelect) fileSelect.value = finalTargetFile;
      }
      codeEditor.value = data.modified_code;
      recordEditedFileState(finalTargetFile, baselineUsed, data.modified_code, isLivePreviewEnabled);
      isUnsaved = !isLivePreviewEnabled;
      if (unsavedIndicator) unsavedIndicator.style.display = isUnsaved ? "inline-block" : "none";
      if (designerAiInput) designerAiInput.value = "";
      const changeCategory = actionType === "fix" ? "watchdog_fix" : "ai_edit";
      const cleanLabel = actionType === "fix" ? `Fixed issue in ${finalTargetFile}: "${shortTitle}"` : `Applied AI edit to ${finalTargetFile}: "${shortTitle}"`;
      logSessionChange(changeCategory, cleanLabel, finalTargetFile, data.explanation);

      updateActionChatBubbleStep(actionBubble, `Saving <code>${escapeHtml(finalTargetFile)}</code> to disk &amp; syncing Live Preview...`);
      if (isLivePreviewEnabled) {
        await syncLivePreviewToWindow(true, false);
      }
      await refreshGitStatus();

      finishActionChatBubble(actionBubble, {
        success: true,
        actionType: actionType,
        title: shortTitle,
        targetFile: finalTargetFile,
        explanation: data.explanation,
        baselineCode: baselineUsed,
        modifiedCode: data.modified_code,
        toolSteps: data.tool_steps || [],
        modifiedFiles: data.modified_files || [finalTargetFile],
        engine: data.engine || "antigravity_sdk"
      });
      return true;
    } else {
      finishActionChatBubble(actionBubble, {
        success: false,
        actionType: actionType,
        title: shortTitle,
        targetFile: activeFilePath,
        toolSteps: data.tool_steps || [],
        engine: data.engine || "antigravity_sdk",
        errorMsg: data.explanation || "Could not generate code"
      });
      return false;
    }
  } catch (e) {
    finishActionChatBubble(actionBubble, {
      success: false,
      actionType: actionType,
      title: shortTitle,
      targetFile: activeFilePath,
      errorMsg: String(e)
    });
    return false;
  } finally {
    if (btnApplyDesignerAi) {
      btnApplyDesignerAi.disabled = false;
      btnApplyDesignerAi.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> <span>Apply</span>';
    }
    if (btnChatDirectEdit) {
      btnChatDirectEdit.disabled = false;
      btnChatDirectEdit.innerHTML = '<i class="fa-solid fa-bolt"></i> <span>Edit</span>';
    }
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
      recordEditedFileState(activeFilePath, preEditBaselineContent || fileOriginalContent, codeEditor.value, true);
      if (unsavedIndicator) unsavedIndicator.style.display = "none";
      btnSaveFile.innerHTML = '<i class="fa-solid fa-check"></i> Saved!';
      logSessionChange("manual_save", `Saved manual edits to ${activeFilePath}`, activeFilePath);
      await refreshGitStatus();

      setTimeout(() => {
        btnSaveFile.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> <span>Save</span>';
        btnSaveFile.disabled = false;
      }, 1200);

      reloadActiveTabWithBadge(true, activeFilePath, { modifiedCode: codeEditor.value });
      return true;
    } else {
      alert(`Save failed: ${data.message || data.detail || "Unknown error"}`);
      btnSaveFile.disabled = false;
      return false;
    }
  } catch (e) {
    alert("Save error: " + e);
    btnSaveFile.disabled = false;
    return false;
  }
}

async function revertCurrentFile() {
  if (!isUnsaved || confirm("Revert all unsaved changes to this file?")) {
    codeEditor.value = preEditBaselineContent || fileOriginalContent;
    isUnsaved = false;
    if (unsavedIndicator) unsavedIndicator.style.display = "none";
    await syncLivePreviewToWindow(false, false);
  }
}

function reloadActiveTab() {
  reloadActiveTabWithBadge(isLivePreviewEnabled, activeFilePath || "app", { forceFullReload: true });
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
  // Code blocks with inline contextual toolbar
  html = html.replace(/```([a-z]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    const langLabel = lang ? lang.toUpperCase() : "CODE";
    return `<div class="chat-code-block-wrapper"><div class="chat-code-toolbar"><span><i class="fa-solid fa-code" style="color:#38bdf8;margin-right:4px;"></i>${langLabel}</span><div class="chat-code-toolbar-actions"><button type="button" class="btn-inline-code-action btn-code-copy" title="Copy code snippet"><i class="fa-regular fa-copy"></i> Copy</button><button type="button" class="btn-inline-code-action btn-code-load-drawer" title="Open in </> Code Drawer"><i class="fa-solid fa-code"></i> &lt;/&gt; Code</button></div></div><pre><code>${code}</code></pre></div>`;
  });
  // Images: ![alt](url)
  html = html.replace(/!\[(.*?)\]\((.*?)\)/g, (match, alt, url) => {
    const fullSrc = url.startsWith("http") ? url : `${SERVER_URL}${url}`;
    return `<div class="chat-md-img-box"><img src="${fullSrc}" alt="${alt}" class="chat-md-img" /></div>`;
  });
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

// --- Session Change Log Tracking & Git Sync ---
const CODE_CHANGE_ACTION_TYPES = new Set([
  "ai_implementation",
  "ai_suggestion",
  "ai_edit",
  "watchdog_fix",
  "manual_save",
  "asset_drop",
  "asset_upload"
]);

function saveSessionChangesLog() {
  if (!activeApp) return;
  try {
    localStorage.setItem(`galactic_changelog_${activeApp.slug}`, JSON.stringify(sessionChangesLog.slice(0, 100)));
  } catch (e) {}
}

function logSessionChange(actionType, summary, filePath = null, explanation = null) {
  const isCodeChange = CODE_CHANGE_ACTION_TYPES.has(actionType);
  const cleanExp = explanation
    ? String(explanation).replace(/\s+/g, " ").trim().slice(0, 240)
    : null;

  const item = {
    id: `chg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    date: new Date().toISOString().slice(0, 10),
    actionType,
    summary,
    explanation: cleanExp,
    filePath: filePath || null,
    isCodeChange,
    committed: false,
    commitHash: null,
    timestamp: Date.now()
  };

  sessionChangesLog.unshift(item);
  if (sessionChangesLog.length > 100) sessionChangesLog.pop();
  saveSessionChangesLog();
}

function getPendingCodeChanges() {
  return (sessionChangesLog || []).filter(
    (item) => item && (item.isCodeChange || CODE_CHANGE_ACTION_TYPES.has(item.actionType)) && !item.committed
  );
}

function buildDefaultCommitMessageWithChangelog() {
  const pending = getPendingCodeChanges();
  const gitFiles = (currentGitStatus?.files || []).map((f) => f.path);

  let header = `feat: update ${activeApp ? activeApp.name : "app"}`;
  if (pending.length === 1) {
    const first = pending[0];
    const prefix = first.actionType === "watchdog_fix" ? "fix" : "feat";
    const shortSum = String(first.summary || "").replace(/^(Implemented|Applied suggestion|Applied AI edit to|Fixed issue in)\s+/i, "");
    header = `${prefix}: ${shortSum.slice(0, 62)}`;
  } else if (gitFiles.length > 0) {
    const topFiles = gitFiles.slice(0, 2).map((p) => p.split("/").pop());
    header = `feat: update ${topFiles.join(", ")}${gitFiles.length > 2 ? ` (+${gitFiles.length - 2} more)` : ""}`;
  }

  const bulletLines = [];
  const seen = new Set();

  pending.forEach((item) => {
    const filePrefix = item.filePath ? `[${item.filePath}] ` : "";
    const detailSuffix = item.explanation ? ` — ${item.explanation}` : "";
    const line = `- ${filePrefix}${item.summary}${detailSuffix}`;
    if (!seen.has(line)) {
      seen.add(line);
      bulletLines.push(line);
    }
  });

  if (bulletLines.length === 0 && gitFiles.length > 0) {
    gitFiles.slice(0, 10).forEach((fp) => {
      bulletLines.push(`- Modified ${fp}`);
    });
  }

  if (bulletLines.length > 0) {
    return `${header}\n\nChange Log:\n${bulletLines.join("\n")}`;
  }
  return header;
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
      gitStatusBadge.title = `${count} uncommitted ${count === 1 ? "change" : "changes"} — Click to review & commit`;
      gitStatusBadge.innerHTML = `<i class="fa-solid fa-pen-to-square"></i> <span id="git-status-label">${count}</span>`;
    } else {
      gitStatusBadge.className = "git-badge clean";
      gitStatusBadge.title = "Working tree clean";
      gitStatusBadge.innerHTML = `<i class="fa-solid fa-check"></i> <span id="git-status-label">0</span>`;
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

  // Populate Change Log Tab
  renderModalSessionLog();

  // Always populate Commit Message & Change Log with pending changes if empty or generic
  if (commitMsgInput) {
    commitMsgInput.value = buildDefaultCommitMessageWithChangelog();
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
    row.title = `Click to open ${f.path} in Code Drawer`;

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
      ensureStudioChatVisible();
      toggleCodeDrawer(true);
      if (fileSelect) fileSelect.value = f.path;
      openFile(f.path);
    });

    modalFilesList.appendChild(row);
  });
}

function renderModalSessionLog() {
  const codeChanges = (sessionChangesLog || []).filter(
    (item) => item && (item.isCodeChange || CODE_CHANGE_ACTION_TYPES.has(item.actionType) || item.actionType === "commit")
  );
  const displayList = codeChanges.length > 0 ? codeChanges : sessionChangesLog;
  const pendingCount = getPendingCodeChanges().length;

  if (modalSessionLogCount) {
    modalSessionLogCount.innerText = pendingCount > 0 ? `${pendingCount} new` : String(displayList.length);
  }

  const btnClearCommitted = document.getElementById("btn-clear-committed-log");
  if (btnClearCommitted && !btnClearCommitted.__wired) {
    btnClearCommitted.__wired = true;
    btnClearCommitted.addEventListener("click", () => {
      sessionChangesLog = (sessionChangesLog || []).filter((item) => !item.committed && item.actionType !== "commit");
      saveSessionChangesLog();
      renderModalSessionLog();
    });
  }

  if (!displayList || displayList.length === 0) {
    modalSessionTimeline.innerHTML = '<div style="color: #64748b; font-size: 11px; text-align: center; padding: 14px 0;">No changes recorded for this app yet.</div>';
    return;
  }

  modalSessionTimeline.innerHTML = "";
  displayList.forEach((item) => {
    const el = document.createElement("div");
    el.className = "timeline-item";
    const isCommitted = Boolean(item.committed || item.actionType === "commit");
    el.style.cssText = [
      "display: flex",
      "flex-direction: column",
      "gap: 3px",
      "padding: 6px 8px",
      "border-radius: 6px",
      "margin-bottom: 5px",
      isCommitted
        ? "background: rgba(15, 23, 42, 0.45); border: 1px solid rgba(51, 65, 85, 0.45); opacity: 0.78;"
        : "background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3);"
    ].join(";");

    const statusBadge = isCommitted
      ? `<span style="font-size: 9px; padding: 1px 5px; border-radius: 4px; background: rgba(100, 116, 139, 0.25); color: #94a3b8; font-weight: 700;">✓ Committed${item.commitHash ? ` (${escapeHtml(item.commitHash)})` : ""}</span>`
      : `<span style="font-size: 9px; padding: 1px 5px; border-radius: 4px; background: rgba(16, 185, 129, 0.22); color: #34d399; font-weight: 700;">● Pending Commit</span>`;

    const fileBadge = item.filePath
      ? `<code style="font-size: 9.5px; color: #38bdf8; background: rgba(56, 189, 248, 0.12); padding: 1px 5px; border-radius: 4px;">${escapeHtml(item.filePath)}</code>`
      : "";

    el.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 6px; flex-wrap: wrap;">
        <div style="display: flex; align-items: center; gap: 5px; flex-wrap: wrap;">
          ${statusBadge}
          ${fileBadge}
        </div>
        <span class="timeline-time" style="font-size: 9.5px; color: #64748b;">${escapeHtml(item.time || "")}</span>
      </div>
      <div class="timeline-desc" style="font-size: 11px; color: #f1f5f9; font-weight: 600;">${escapeHtml(item.summary)}</div>
      ${item.explanation ? `<div style="font-size: 10px; color: #94a3b8; line-height: 1.35;">${escapeHtml(item.explanation)}</div>` : ""}
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
    const pending = getPendingCodeChanges();
    const recent = (pending.length > 0 ? pending : sessionChangesLog.slice(0, 8)).map(
      (s) => `${s.filePath ? `[${s.filePath}] ` : ""}${s.summary}${s.explanation ? ` — ${s.explanation}` : ""}`
    );

    const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/generate-commit-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files, recent_actions: recent })
    });

    if (res.ok) {
      const data = await res.json();
      if (data.commit_message) {
        // Combine the AI commit title with the structured Change Log bullets if not already multi-line
        const aiHeader = data.commit_message.trim();
        if (recent.length > 0 && !aiHeader.includes("Change Log:")) {
          const bullets = recent.slice(0, 12).map((line) => `- ${line}`).join("\n");
          commitMsgInput.value = `${aiHeader}\n\nChange Log:\n${bullets}`;
        } else {
          commitMsgInput.value = aiHeader;
        }
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

  const msg = commitMsgInput.value.trim() || buildDefaultCommitMessageWithChangelog();
  const chkWriteChangelog = document.getElementById("chk-write-changelog-md");
  const updateChangelogFile = chkWriteChangelog ? Boolean(chkWriteChangelog.checked) : true;
  const pendingChanges = getPendingCodeChanges();

  btnCommitPcOnly.disabled = true;
  btnDoCommitAndPush.disabled = true;

  commitFeedback.className = "commit-feedback";
  commitFeedback.style.display = "block";
  commitFeedback.innerHTML = `
    <div style="display: flex; align-items: center; gap: 8px; color: #a5b4fc;">
      <i class="fa-solid fa-spinner animate-spin"></i>
      <span>${pushRemote ? "Updating Change Log, committing to local Git, and pushing to GitHub..." : "Updating Change Log and committing to local Git on computer..."}</span>
    </div>
  `;

  try {
    const res = await fetch(`${SERVER_URL}/api/apps/${activeApp.slug}/push-github`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        commit_message: msg,
        push_remote: pushRemote,
        update_changelog_file: updateChangelogFile,
        changelog_entries: pendingChanges.map((c) => ({
          time: c.time,
          action_type: c.actionType,
          file_path: c.filePath,
          summary: c.summary,
          explanation: c.explanation
        }))
      })
    });

    const data = await res.json();

    if (data.success) {
      // Mark all pending changes as committed with the new commit hash!
      const cHash = data.commit_hash || "HEAD";
      sessionChangesLog.forEach((item) => {
        if (!item.committed && (item.isCodeChange || CODE_CHANGE_ACTION_TYPES.has(item.actionType))) {
          item.committed = true;
          item.commitHash = cHash;
        }
      });
      saveSessionChangesLog();

      if (pushRemote && data.pushed_to_github) {
        commitFeedback.className = "commit-feedback success";
        commitFeedback.innerHTML = `
          <div style="font-weight: 700; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
            <i class="fa-solid fa-circle-check"></i>
            <span>Successfully Synced to Computer &amp; GitHub!</span>
          </div>
          <div style="font-size: 10.5px; opacity: 0.95;">
            💻 <strong>Local PC:</strong> Saved to disk &amp; committed (<code>${cHash}</code>)${data.changelog_updated ? " + updated <code>CHANGELOG.md</code>" : ""}<br>
            🐙 <strong>GitHub:</strong> Pushed with Change Log to <code>${data.branch || "main"}</code>
            ${data.github_url ? ` (<a href="${data.github_url}" target="_blank" style="color: #67e8f9; text-decoration: underline;">Open GitHub Repo</a>)` : ""}
          </div>
        `;
      } else {
        // Saved locally, push pending/warning or local-only
        commitFeedback.className = data.warning ? "commit-feedback warning" : "commit-feedback success";
        commitFeedback.innerHTML = `
          <div style="font-weight: 700; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
            <i class="fa-solid fa-hard-drive"></i>
            <span>Changes &amp; Change Log Saved to Computer Disk!</span>
          </div>
          <div style="font-size: 10.5px; opacity: 0.95;">
            💻 Committed to local Git (<code>${cHash}</code>) on branch <code>${data.branch || "main"}</code>${data.changelog_updated ? " + updated <code>CHANGELOG.md</code>" : ""}.<br>
            ${data.warning ? `<span style="color: #fbbf24;">⚠️ GitHub note: ${escapeHtml(data.warning)}</span>` : "Ready to push to GitHub anytime."}
          </div>
        `;
      }

      const firstLine = msg.split("\n")[0];
      logSessionChange("commit", `Committed changes (${cHash}): "${firstLine}"${pushRemote && data.pushed_to_github ? " (Pushed to GitHub)" : ""}`);
      await refreshGitStatus();
      renderModalFilesList();
      renderModalSessionLog();
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

// ============================================================================
// LIVE APP RUNTIME WATCHDOG & PERSISTENT ERROR / FREEZE LOG
// ============================================================================
let runtimeWatchdogEnabled = true;
let consecutiveHeartbeatTimeouts = 0;
let lastKnownTabAction = null;
let latestRuntimeIssue = null;
let watchdogErrorLog = [];

function isFalsePositiveTabHang(issue) {
  if (!issue) return true;
  const title = String(issue.title || "");
  const detail = String(issue.detail || "");
  if (issue.hiddenOrTransition) return true;
  // Passive event-loop drift without an explicit recent button click is almost always browser background-tab timer throttling
  if (
    (issue.type === "ui_freeze" || /UI Main-Thread Hang/i.test(title)) &&
    (!issue.buttonLabel || /App main thread stalled for/i.test(detail))
  ) {
    return true;
  }
  // Background tab heartbeat timeout when no interactive button was just clicked
  if (
    (issue.type === "hard_freeze" || /App Window Frozen/i.test(title)) &&
    !issue.buttonLabel
  ) {
    return true;
  }
  return false;
}

function loadWatchdogLog(slug) {
  watchdogErrorLog = [];
  if (!slug) {
    renderWatchdogLogList();
    return;
  }
  try {
    const raw = localStorage.getItem(`galactic_watchdog_log_${slug}`);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        // Automatically purge false-positive tab-switch / background-throttling hang alerts
        const filtered = parsed.filter((entry) => !isFalsePositiveTabHang(entry));
        watchdogErrorLog = filtered;
        if (filtered.length !== parsed.length) {
          localStorage.setItem(`galactic_watchdog_log_${slug}`, JSON.stringify(filtered.slice(0, 100)));
        }
      }
    }
  } catch (e) {
    console.warn("Could not read watchdog log from storage:", e);
  }
  renderWatchdogLogList();
}

function saveWatchdogLog(slug = activeApp?.slug) {
  if (!slug) return;
  try {
    localStorage.setItem(`galactic_watchdog_log_${slug}`, JSON.stringify(watchdogErrorLog.slice(0, 100)));
  } catch (e) {}
}

function recordWatchdogEvent(issue) {
  if (!issue || isFalsePositiveTabHang(issue)) return null;
  const now = Date.now();
  const title = issue.title || "Runtime Issue Detected";
  const detail = issue.detail || "";

  // Deduplicate identical consecutive events within 4 seconds
  const recentDup = watchdogErrorLog.find(
    (entry) => entry.title === title && entry.detail === detail && now - (entry.timestamp || 0) < 4000
  );
  if (recentDup) {
    recentDup.occurrences = (recentDup.occurrences || 1) + 1;
    recentDup.timestamp = now;
    recentDup.time = new Date(now).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    saveWatchdogLog();
    renderWatchdogLogList();
    return recentDup;
  }

  const entry = {
    id: `wd-${now}-${Math.random().toString(36).slice(2, 6)}`,
    type: issue.type || "runtime_error",
    title,
    detail,
    buttonLabel: issue.buttonLabel || null,
    durationMs: issue.durationMs || null,
    time: new Date(now).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    timestamp: now,
    status: "unresolved",
    occurrences: 1
  };

  watchdogErrorLog.unshift(entry);
  if (watchdogErrorLog.length > 100) {
    watchdogErrorLog.pop();
  }
  saveWatchdogLog();
  renderWatchdogLogList();
  return entry;
}

function updateWatchdogBadgesCount() {
  const countPill = document.getElementById("watchdog-log-count-pill");
  const drawerBadge = document.getElementById("watchdog-drawer-count-badge");
  const unresolvedCount = watchdogErrorLog.filter((e) => e.status !== "fixed").length;
  const totalCount = watchdogErrorLog.length;

  if (countPill) {
    if (totalCount > 0) {
      countPill.style.display = "inline-block";
      countPill.innerText = unresolvedCount > 0 ? String(unresolvedCount) : String(totalCount);
      countPill.style.background = unresolvedCount > 0 ? "rgba(239, 68, 68, 0.35)" : "rgba(16, 185, 129, 0.25)";
      countPill.style.color = unresolvedCount > 0 ? "#fecaca" : "#6ee7b7";
      countPill.style.borderColor = unresolvedCount > 0 ? "rgba(248, 113, 113, 0.7)" : "rgba(16, 185, 129, 0.45)";
    } else {
      countPill.style.display = "none";
    }
  }
  if (drawerBadge) {
    drawerBadge.innerText = `${totalCount} caught (${unresolvedCount} open)`;
  }
}

function toggleWatchdogLogDrawer(forceOpen = null) {
  const drawer = document.getElementById("watchdog-log-drawer");
  if (!drawer) return;
  const isHidden = drawer.classList.contains("hidden");
  const shouldOpen = forceOpen !== null ? forceOpen : isHidden;
  if (shouldOpen) {
    drawer.classList.remove("hidden");
    renderWatchdogLogList();
  } else {
    drawer.classList.add("hidden");
  }
}

async function investigateWatchdogIssue(entry) {
  if (!entry) return;
  entry.status = entry.status === "fixed" ? "fixed" : "investigated";
  saveWatchdogLog();
  renderWatchdogLogList();
  ensureStudioChatVisible();

  const prompt = `Look into this runtime issue caught by the Watchdog in ${activeApp ? activeApp.name : "the app"}:\n` +
    `- **Issue**: ${entry.title}\n` +
    `- **Details**: ${entry.detail}\n` +
    `${entry.buttonLabel ? `- **Triggered By**: Interacting with \`${entry.buttonLabel}\`\n` : ""}` +
    `Please explain what is causing this in \`${activeFilePath || "the codebase"}\` and propose how we should fix it.`;

  await submitBrainstorm(prompt);
}

async function fixWatchdogIssue(entry) {
  if (!entry) return;
  ensureStudioChatVisible();

  // Smart-select the right target file for this Watchdog issue (e.g., frontend UI file for UI freezes/console errors, backend file for HTTP 500 server errors)
  if (activeApp) {
    if (!appFileList || appFileList.length === 0) {
      await loadFileTree(activeApp.slug);
    }
    const paths = (appFileList || []).map((f) => (typeof f === "object" && f ? f.path : f)).filter(Boolean);
    const detailStr = `${entry.title || ""} ${entry.detail || ""} ${entry.buttonLabel || ""}`;

    // 1. Check if the stack trace / error detail explicitly names one of the app's files
    let bestFile = paths.find((p) => {
      const base = p.split("/").pop();
      return base && base.length > 3 && detailStr.toLowerCase().includes(base.toLowerCase());
    });

    // 2. If it's a browser UI freeze or frontend runtime error and activeFilePath is a .py backend file, switch to the primary frontend UI file
    if (!bestFile) {
      if (entry.type === "server_error") {
        bestFile = paths.find((p) => /(main|app|server)\.(py|js|ts)$/i.test(p));
      } else if (!activeFilePath || /\.py$/i.test(activeFilePath)) {
        bestFile =
          paths.find((p) => /static\/index\.html$/i.test(p)) ||
          paths.find((p) => /src\/(App|main)\.(jsx|tsx|js|ts)$/i.test(p)) ||
          paths.find((p) => /index\.html$/i.test(p)) ||
          guessBestTargetFile({ title: entry.title, description: entry.detail, category: "ux" }, appFileList);
      }
    }

    if (bestFile && bestFile !== activeFilePath) {
      if (fileSelect) fileSelect.value = bestFile;
      await openFile(bestFile);
    }
  }

  const fixPrompt =
    `Fix runtime ${entry.type === "hard_freeze" || entry.type === "ui_freeze" ? "UI freeze / main-thread hang" : "error"}: ${entry.title}. ` +
    `Details: ${entry.detail}. ` +
    `${entry.buttonLabel ? `Triggered when interacting with ${entry.buttonLabel}. ` : ""}` +
    `Ensure the handler or async operation is non-blocking, has proper try/catch error handling, and resolves the root cause cleanly.`;

  if (designerAiInput) {
    designerAiInput.value = fixPrompt;
  }
  const ok = await applyDesignerAiEdit(fixPrompt, "fix");

  if (ok) {
    entry.status = "fixed";
    saveWatchdogLog();
    renderWatchdogLogList();
  }
}

function renderWatchdogLogList() {
  updateWatchdogBadgesCount();
  const listEl = document.getElementById("watchdog-log-list");
  if (!listEl) return;

  if (!watchdogErrorLog || watchdogErrorLog.length === 0) {
    listEl.innerHTML = `
      <div style="color: #64748b; font-size: 11px; text-align: center; padding: 14px 6px;">
        <i class="fa-solid fa-circle-check" style="color: #10b981; margin-right: 4px;"></i>
        No runtime freezes, crashes, or errors caught yet for ${escapeHtml(activeApp ? activeApp.name : "this app")}.
      </div>
    `;
    return;
  }

  listEl.innerHTML = "";
  const gName = getGeppyName(activeApp);

  watchdogErrorLog.forEach((entry) => {
    const card = document.createElement("div");
    const isFixed = entry.status === "fixed";
    const isFreeze = entry.type === "hard_freeze" || entry.type === "ui_freeze";

    card.style.cssText = [
      "background: #111827",
      `border: 1px solid ${isFixed ? "rgba(16, 185, 129, 0.35)" : (isFreeze ? "rgba(239, 68, 68, 0.45)" : "rgba(245, 158, 11, 0.4)")}`,
      `border-left: 3px solid ${isFixed ? "#10b981" : (isFreeze ? "#ef4444" : "#f59e0b")}`,
      "border-radius: 7px",
      "padding: 7px 9px",
      "display: flex",
      "flex-direction: column",
      "gap: 5px",
      isFixed ? "opacity: 0.82" : ""
    ].join(";");

    const statusBadge = isFixed
      ? `<span style="background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); padding: 1px 5px; border-radius: 4px; font-size: 9px; font-weight: 700;">✓ Fixed</span>`
      : entry.status === "investigated"
      ? `<span style="background: rgba(99, 102, 241, 0.2); color: #a5b4fc; border: 1px solid rgba(99, 102, 241, 0.4); padding: 1px 5px; border-radius: 4px; font-size: 9px; font-weight: 700;">👀 Reviewed</span>`
      : `<span style="background: rgba(239, 68, 68, 0.2); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.4); padding: 1px 5px; border-radius: 4px; font-size: 9px; font-weight: 700;">● Caught</span>`;

    const occBadge = entry.occurrences && entry.occurrences > 1
      ? `<span style="background: rgba(255,255,255,0.08); color: #cbd5e1; padding: 1px 5px; border-radius: 4px; font-size: 9px;">×${entry.occurrences}</span>`
      : "";

    card.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 6px;">
        <div style="display: flex; align-items: center; gap: 5px; flex-wrap: wrap; min-width: 0;">
          ${statusBadge}
          ${occBadge}
          <strong style="font-size: 11px; color: #f8fafc;">${escapeHtml(entry.title)}</strong>
        </div>
        <div style="display: flex; align-items: center; gap: 6px; flex-shrink: 0;">
          <span style="font-size: 9.5px; color: #64748b; font-family: monospace;">${escapeHtml(entry.time || "")}</span>
          <button type="button" class="btn-wd-delete" style="background: transparent; border: none; color: #64748b; cursor: pointer; font-size: 10px;" title="Remove from log">
            <i class="fa-solid fa-xmark"></i>
          </button>
        </div>
      </div>
      <div style="font-size: 10.5px; color: #cbd5e1; font-family: monospace; word-break: break-word; background: rgba(0,0,0,0.3); padding: 4px 6px; border-radius: 4px;">
        ${escapeHtml(entry.detail || "")}
      </div>
      <div style="display: flex; align-items: center; justify-content: flex-end; gap: 6px; margin-top: 2px;">
        <button type="button" class="btn-wd-investigate" style="padding: 3px 7px; border-radius: 5px; background: rgba(99, 102, 241, 0.2); border: 1px solid rgba(99, 102, 241, 0.45); color: #c7d2fe; font-size: 10px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 4px;" title="Ask ${escapeHtml(gName)} to look into this error and explain what happened in Chat">
          <i class="fa-solid fa-magnifying-glass"></i>
          <span>Look Into It</span>
        </button>
        <button type="button" class="btn-wd-fix" style="padding: 3px 8px; border-radius: 5px; background: linear-gradient(135deg, #ef4444, #d97706); border: none; color: #fff; font-size: 10px; font-weight: 700; cursor: pointer; display: inline-flex; align-items: center; gap: 4px;" title="Have ${escapeHtml(gName)} automatically fix this error in your code">
          <i class="fa-solid fa-wrench"></i>
          <span>Ask ${escapeHtml(gName)} to Fix</span>
        </button>
      </div>
    `;

    const btnInvestigate = card.querySelector(".btn-wd-investigate");
    if (btnInvestigate) {
      btnInvestigate.addEventListener("click", () => {
        investigateWatchdogIssue(entry);
      });
    }

    const btnFix = card.querySelector(".btn-wd-fix");
    if (btnFix) {
      btnFix.addEventListener("click", () => {
        fixWatchdogIssue(entry);
      });
    }

    const btnDel = card.querySelector(".btn-wd-delete");
    if (btnDel) {
      btnDel.addEventListener("click", () => {
        const idx = watchdogErrorLog.findIndex((x) => x.id === entry.id);
        if (idx !== -1) {
          watchdogErrorLog.splice(idx, 1);
          saveWatchdogLog();
          renderWatchdogLogList();
        }
      });
    }

    listEl.appendChild(card);
  });
}

function setRuntimeMonitorBadgeState(state, labelText) {
  const badge = document.getElementById("btn-runtime-monitor-badge");
  const dot = document.getElementById("runtime-monitor-dot");
  const lbl = document.getElementById("runtime-monitor-label");
  const chk = document.getElementById("chk-watchdog-enabled");
  if (chk) chk.checked = runtimeWatchdogEnabled;
  if (!badge || !dot || !lbl) return;

  if (!runtimeWatchdogEnabled) {
    badge.style.background = "rgba(100, 116, 139, 0.16)";
    badge.style.borderColor = "rgba(100, 116, 139, 0.4)";
    badge.style.color = "#94a3b8";
    dot.style.background = "#94a3b8";
    lbl.innerText = "Watchdog OFF";
    updateWatchdogBadgesCount();
    return;
  }

  if (state === "frozen") {
    badge.style.background = "rgba(239, 68, 68, 0.25)";
    badge.style.borderColor = "rgba(248, 113, 113, 0.85)";
    badge.style.color = "#fca5a5";
    dot.style.background = "#ef4444";
    lbl.innerText = labelText || "🚨 FROZEN";
  } else if (state === "warning") {
    badge.style.background = "rgba(245, 158, 11, 0.22)";
    badge.style.borderColor = "rgba(251, 191, 36, 0.75)";
    badge.style.color = "#fde68a";
    dot.style.background = "#f59e0b";
    lbl.innerText = labelText || "⚠️ Issue";
  } else {
    badge.style.background = "rgba(16, 185, 129, 0.14)";
    badge.style.borderColor = "rgba(16, 185, 129, 0.4)";
    badge.style.color = "#34d399";
    dot.style.background = "#34d399";
    lbl.innerText = labelText || "Watchdog ON";
  }
  updateWatchdogBadgesCount();
}

function showRuntimeAlertBanner(issue) {
  if (!issue || isFalsePositiveTabHang(issue)) return;
  const loggedEntry = recordWatchdogEvent(issue);
  if (!loggedEntry) return;
  latestRuntimeIssue = loggedEntry;

  const banner = document.getElementById("runtime-alert-banner");
  const titleEl = document.getElementById("runtime-alert-title");
  const detailEl = document.getElementById("runtime-alert-detail");
  const fixLabel = document.getElementById("btn-fix-runtime-label");
  if (!banner || !titleEl || !detailEl) return;

  const gName = getGeppyName(activeApp);
  if (fixLabel) {
    fixLabel.innerText = `Ask ${gName} to Fix`;
  }

  titleEl.innerText = issue.title || "Runtime Freeze / Error Detected";
  detailEl.innerText = issue.detail || "";
  banner.classList.remove("hidden");

  setRuntimeMonitorBadgeState(
    issue.type === "hard_freeze" || issue.type === "ui_freeze" ? "frozen" : "warning",
    issue.type === "hard_freeze" || issue.type === "ui_freeze" ? "🚨 Freeze!" : "⚠️ Error"
  );
}

function dismissRuntimeAlertBanner() {
  const banner = document.getElementById("runtime-alert-banner");
  if (banner) banner.classList.add("hidden");
  setRuntimeMonitorBadgeState("healthy", "Watchdog ON");
}

async function pollAndInjectRuntimeWatchdog() {
  if (!runtimeWatchdogEnabled) return;
  if (typeof chrome === "undefined" || !chrome.scripting || !chrome.tabs) return;

  // Give a 3-second grace window whenever the user switches tabs so Chrome waking up a background tab never triggers a false hang
  if (typeof lastTabSwitchTimestamp === "number" && Date.now() - lastTabSwitchTimestamp < 3000) {
    consecutiveHeartbeatTimeouts = 0;
    return;
  }

  let targetTabId = activeTabInstance.tabId || activeTabId;
  if (!targetTabId) {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab && tab.id && tab.url && /^https?:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0)/i.test(tab.url)) {
        targetTabId = tab.id;
        activeTabId = tab.id;
      }
    } catch (e) {}
  }
  if (!targetTabId) return;

  // Verify the tab is an ACTIVE, visible, fully-loaded local http(s) page before scripting
  let tabObj = null;
  try {
    tabObj = await chrome.tabs.get(targetTabId);
    if (
      !tabObj ||
      !tabObj.active ||
      tabObj.discarded ||
      tabObj.status !== "complete" ||
      !tabObj.url ||
      !/^https?:\/\//i.test(tabObj.url)
    ) {
      consecutiveHeartbeatTimeouts = 0;
      return;
    }
  } catch (e) {
    consecutiveHeartbeatTimeouts = 0;
    return;
  }

  // Race executeScript against a 1500ms timeout to detect hard main-thread freezes (infinite loops!)
  let timedOut = false;
  const timeoutPromise = new Promise((resolve) => {
    setTimeout(() => {
      timedOut = true;
      resolve({ __timeout: true });
    }, 1500);
  });

  const scriptPromise = chrome.scripting.executeScript({
    target: { tabId: targetTabId },
    func: () => {
      // Install or upgrade in-page watchdog (version 2: tab-visibility & focus aware)
      if (!window.__geppyWatchdog) {
        window.__geppyWatchdog = {
          version: 2,
          installedAt: Date.now(),
          lastAction: null,
          events: [],
          lastTick: performance.now(),
          isHidden: Boolean(document.hidden || document.visibilityState !== "visible"),
          resumeGraceUntil: performance.now() + 3000
        };
      }

      const wd = window.__geppyWatchdog;
      wd.version = 2;
      if (typeof wd.resumeGraceUntil !== "number") {
        wd.resumeGraceUntil = performance.now() + 3000;
      }

      // Wire visibility/focus listeners once so leaving or returning to the tab resets timers and suppresses false hang alerts
      if (!window.__geppyVisibilityWired) {
        window.__geppyVisibilityWired = true;
        const onVisibilityOrFocusChange = () => {
          const hiddenNow = Boolean(
            document.hidden ||
            document.visibilityState !== "visible" ||
            (typeof document.hasFocus === "function" && !document.hasFocus())
          );
          wd.isHidden = hiddenNow;
          wd.lastTick = performance.now();
          // Ignore timer drift for 3.5 seconds after any tab switch, blur, or focus transition
          wd.resumeGraceUntil = performance.now() + 3500;
          if (hiddenNow) {
            wd.lastAction = null;
          }
        };
        document.addEventListener("visibilitychange", onVisibilityOrFocusChange, true);
        window.addEventListener("blur", onVisibilityOrFocusChange, true);
        window.addEventListener("focus", onVisibilityOrFocusChange, true);
        window.addEventListener("pageshow", onVisibilityOrFocusChange, true);
      }

      if (!window.__geppyWatchdogListenersInstalled) {
        window.__geppyWatchdogListenersInstalled = true;

        const describeElement = (el) => {
          if (!el) return "Unknown Element";
          const tag = (el.tagName || "ELEMENT").toLowerCase();
          const id = el.id ? `#${el.id}` : "";
          const text = (el.innerText || el.value || el.getAttribute("aria-label") || el.title || "")
            .trim()
            .replace(/\s+/g, " ")
            .slice(0, 42);
          return `<${tag}${id}>${text ? ` "${text}"` : ""}`;
        };

        const isTabActivelyVisible = () => {
          if (document.hidden || document.visibilityState !== "visible") return false;
          if (typeof document.hasFocus === "function" && !document.hasFocus()) return false;
          if (performance.now() < (wd.resumeGraceUntil || 0)) return false;
          return true;
        };

        // 1. Capture button/interactive clicks BEFORE click handler runs (pointerdown)
        window.addEventListener(
          "pointerdown",
          (ev) => {
            if (document.hidden || document.visibilityState !== "visible") return;
            const btn = ev.target && ev.target.closest
              ? ev.target.closest("button, a, [role='button'], input[type='submit'], input[type='button'], [onclick]")
              : ev.target;
            if (btn) {
              wd.lastAction = {
                label: describeElement(btn),
                timestamp: Date.now(),
                perfStart: performance.now()
              };
            }
          },
          true
        );

        // 2. Post-click main-thread freeze & lag check (only when tab remains visible & focused)
        window.addEventListener(
          "click",
          (ev) => {
            if (!isTabActivelyVisible()) return;
            const btn = ev.target && ev.target.closest
              ? ev.target.closest("button, a, [role='button'], input[type='submit'], input[type='button'], [onclick]")
              : ev.target;
            if (!btn) return;
            const label = describeElement(btn);
            const t0 = performance.now();
            setTimeout(() => {
              // Ignore if user switched tabs or window lost focus during/after the click
              if (!isTabActivelyVisible()) {
                wd.lastTick = performance.now();
                return;
              }
              const elapsed = Math.round(performance.now() - t0);
              // A 60ms timer taking > 900ms while continuously focused means the click handler blocked the main thread
              if (elapsed > 900) {
                wd.events.push({
                  type: "ui_freeze",
                  title: `🥶 Button Freeze Detected (${elapsed}ms)`,
                  detail: `Clicking ${label} froze the main UI thread for ${elapsed}ms.`,
                  buttonLabel: label,
                  durationMs: elapsed,
                  timestamp: Date.now()
                });
              }
            }, 60);
          },
          true
        );

        // 3. Event-loop lag monitor — strictly ignores background tab throttling and only flags post-interaction freezes
        setInterval(() => {
          const now = performance.now();
          if (!isTabActivelyVisible()) {
            wd.lastTick = now;
            return;
          }
          const drift = Math.round(now - wd.lastTick - 500);
          wd.lastTick = now;
          const recentBtn =
            wd.lastAction && Date.now() - wd.lastAction.timestamp < 3500
              ? wd.lastAction.label
              : null;
          // Only report a main-thread hang if the user actively clicked an element and the visible tab stalled for >2000ms
          if (drift > 2000 && recentBtn) {
            wd.events.push({
              type: "ui_freeze",
              title: `🥶 UI Main-Thread Hang (${drift}ms)`,
              detail: `App froze for ${drift}ms right after interacting with ${recentBtn}.`,
              buttonLabel: recentBtn,
              durationMs: drift,
              timestamp: Date.now()
            });
          }
        }, 500);

        // 4. Uncaught Runtime Errors
        window.addEventListener("error", (ev) => {
          const recentBtn =
            wd.lastAction && Date.now() - wd.lastAction.timestamp < 5000
              ? wd.lastAction.label
              : null;
          const msg = ev.message || String(ev.error || "Runtime Error");
          wd.events.push({
            type: "runtime_error",
            title: recentBtn ? `💥 Crash after clicking ${recentBtn}` : "💥 Uncaught JS Error",
            detail: `${msg}${ev.filename ? ` (${ev.filename.split("/").pop()}:${ev.lineno || 0})` : ""}`,
            buttonLabel: recentBtn,
            timestamp: Date.now()
          });
        });

        // 5. Unhandled Promise Rejections
        window.addEventListener("unhandledrejection", (ev) => {
          const recentBtn =
            wd.lastAction && Date.now() - wd.lastAction.timestamp < 6000
              ? wd.lastAction.label
              : null;
          const reason = ev.reason ? (ev.reason.message || String(ev.reason)) : "Unhandled Promise Rejection";
          wd.events.push({
            type: "promise_rejection",
            title: recentBtn ? `⚠️ Failed Action on ${recentBtn}` : "⚠️ Unhandled Async Error",
            detail: reason,
            buttonLabel: recentBtn,
            timestamp: Date.now()
          });
        });

        // 6. Intercept console.error() so caught framework/app errors are also logged!
        if (console && console.error && !window.__geppyConsoleWrapped) {
          window.__geppyConsoleWrapped = true;
          const origConsoleError = console.error.bind(console);
          console.error = (...args) => {
            origConsoleError(...args);
            try {
              const joined = args
                .map((a) => {
                  if (a instanceof Error) return `${a.name}: ${a.message}`;
                  if (typeof a === "object" && a !== null) {
                    try { return JSON.stringify(a).slice(0, 220); } catch (e) { return String(a); }
                  }
                  return String(a);
                })
                .join(" ")
                .trim();
              if (joined && !joined.includes("geppy-live-preview")) {
                const recentBtn =
                  wd.lastAction && Date.now() - wd.lastAction.timestamp < 5000
                    ? wd.lastAction.label
                    : null;
                wd.events.push({
                  type: "console_error",
                  title: recentBtn ? `🛑 Console Error after ${recentBtn}` : "🛑 Console Error Logged",
                  detail: joined.slice(0, 320),
                  buttonLabel: recentBtn,
                  timestamp: Date.now()
                });
              }
            } catch (e) {}
          };
        }

        // 7. Hung or Failed fetch() Monitor
        if (window.fetch && !window.__geppyFetchWrapped) {
          window.__geppyFetchWrapped = true;
          const origFetch = window.fetch.bind(window);
          window.fetch = async (...args) => {
            const urlStr = typeof args[0] === "string" ? args[0] : (args[0]?.url || "API request");
            const recentBtn =
              wd.lastAction && Date.now() - wd.lastAction.timestamp < 3000
                ? wd.lastAction.label
                : null;
            const hangTimer = setTimeout(() => {
              if (recentBtn && !document.hidden && document.visibilityState === "visible") {
                wd.events.push({
                  type: "hung_request",
                  title: `⏳ Hung Action on ${recentBtn}`,
                  detail: `Request to "${urlStr}" has been stuck pending for >8 seconds after clicking ${recentBtn}.`,
                  buttonLabel: recentBtn,
                  timestamp: Date.now()
                });
              }
            }, 8500);

            try {
              const res = await origFetch(...args);
              clearTimeout(hangTimer);
              if (res.status >= 500 && recentBtn) {
                wd.events.push({
                  type: "server_error",
                  title: `🚨 Server Error (${res.status}) on ${recentBtn}`,
                  detail: `${urlStr} returned HTTP ${res.status} after clicking ${recentBtn}.`,
                  buttonLabel: recentBtn,
                  timestamp: Date.now()
                });
              }
              return res;
            } catch (err) {
              clearTimeout(hangTimer);
              if (recentBtn) {
                wd.events.push({
                  type: "network_error",
                  title: `🔌 Network Failure on ${recentBtn}`,
                  detail: `Request to "${urlStr}" failed (${err.message || err}) after clicking ${recentBtn}.`,
                  buttonLabel: recentBtn,
                  timestamp: Date.now()
                });
              }
              throw err;
            }
          };
        }
      }

      // If the tab is currently hidden or within the 3.5s tab-switch grace window, discard any queued ui_freeze events
      const inTransitionOrHidden = Boolean(
        document.hidden ||
        document.visibilityState !== "visible" ||
        performance.now() < (wd.resumeGraceUntil || 0)
      );
      const rawEvents = wd.events.splice(0, wd.events.length);
      const drained = rawEvents.filter((ev) => {
        if (!ev) return false;
        if (ev.type === "ui_freeze") {
          if (inTransitionOrHidden) return false;
          // Drop passive background-timer drift events (from older v1 intervals or non-interactive stalls)
          if (!ev.buttonLabel || /App main thread stalled for/i.test(ev.detail || "")) return false;
        }
        return true;
      });

      return {
        alive: true,
        hidden: Boolean(document.hidden || document.visibilityState !== "visible"),
        lastAction: wd.lastAction,
        events: drained
      };
    }
  }).catch(() => null);

  const raceResult = await Promise.race([scriptPromise, timeoutPromise]);

  if (timedOut || (raceResult && raceResult.__timeout)) {
    // Only count heartbeat timeouts if the user actually clicked an interactive element in the last 6 seconds
    const recentInteractiveClick =
      lastKnownTabAction && Date.now() - (lastKnownTabAction.timestamp || 0) < 6000;
    if (!recentInteractiveClick) {
      consecutiveHeartbeatTimeouts = 0;
      return;
    }
    consecutiveHeartbeatTimeouts += 1;
    if (consecutiveHeartbeatTimeouts >= 2) {
      const actionContext = lastKnownTabAction
        ? ` right after clicking ${lastKnownTabAction.label}`
        : "";
      showRuntimeAlertBanner({
        type: "hard_freeze",
        title: "🚨 App Window Frozen (Main Thread Locked)",
        detail: `The running app tab stopped responding to heartbeats${actionContext}. This is usually caused by an infinite loop or blocking synchronous operation.`,
        buttonLabel: lastKnownTabAction ? lastKnownTabAction.label : null
      });
    }
    return;
  }

  consecutiveHeartbeatTimeouts = 0;
  if (Array.isArray(raceResult) && raceResult[0] && raceResult[0].result) {
    const payload = raceResult[0].result;
    if (payload.hidden) {
      return;
    }
    if (payload.lastAction) {
      lastKnownTabAction = payload.lastAction;
    }
    if (Array.isArray(payload.events) && payload.events.length > 0) {
      const validEvents = payload.events.filter((ev) => !isFalsePositiveTabHang(ev));
      validEvents.forEach((ev) => {
        recordWatchdogEvent(ev);
        logSessionChange("watchdog", `${ev.title}: ${ev.detail}`);
      });
      if (validEvents.length > 0) {
        const latestEv = validEvents[validEvents.length - 1];
        showRuntimeAlertBanner(latestEv);
      }
    }
  }
}

// Wire Runtime Watchdog UI buttons & start 2-second heartbeat loop
(function initRuntimeWatchdogUI() {
  const badgeBtn = document.getElementById("btn-runtime-monitor-badge");
  const dismissBtn = document.getElementById("btn-dismiss-runtime-alert");
  const fixBtn = document.getElementById("btn-fix-runtime-issue");
  const investigateBtn = document.getElementById("btn-investigate-runtime-issue");
  const bannerLogBtn = document.getElementById("btn-banner-open-watchdog-log");
  const recoverBtn = document.getElementById("btn-reload-frozen-tab");
  const chkEnabled = document.getElementById("chk-watchdog-enabled");
  const btnAnalyzeAll = document.getElementById("btn-watchdog-analyze-all");
  const btnClearLog = document.getElementById("btn-watchdog-clear-log");
  const btnCloseLog = document.getElementById("btn-close-watchdog-log");

  // Clicking the Watchdog badge in the header opens/toggles the Watchdog Error Log Drawer!
  if (badgeBtn) {
    badgeBtn.addEventListener("click", () => {
      toggleWatchdogLogDrawer();
    });
  }

  if (chkEnabled) {
    chkEnabled.addEventListener("change", (e) => {
      runtimeWatchdogEnabled = Boolean(e.target.checked);
      setRuntimeMonitorBadgeState("healthy", runtimeWatchdogEnabled ? "Watchdog ON" : "Watchdog OFF");
    });
  }

  if (bannerLogBtn) {
    bannerLogBtn.addEventListener("click", () => {
      toggleWatchdogLogDrawer(true);
    });
  }

  if (btnCloseLog) {
    btnCloseLog.addEventListener("click", () => {
      toggleWatchdogLogDrawer(false);
    });
  }

  if (btnClearLog) {
    btnClearLog.addEventListener("click", () => {
      if (watchdogErrorLog.length === 0) return;
      watchdogErrorLog = [];
      saveWatchdogLog();
      renderWatchdogLogList();
    });
  }

  if (btnAnalyzeAll) {
    btnAnalyzeAll.addEventListener("click", async () => {
      if (!watchdogErrorLog || watchdogErrorLog.length === 0) {
        alert("No caught errors in the Watchdog Log to review yet.");
        return;
      }
      const openItems = watchdogErrorLog.filter((e) => e.status !== "fixed").slice(0, 8);
      const targetItems = openItems.length > 0 ? openItems : watchdogErrorLog.slice(0, 6);
      const summaryLines = targetItems.map(
        (e, i) => `${i + 1}. **[${e.time}] ${e.title}** — \`${e.detail}\`${e.buttonLabel ? ` (after ${e.buttonLabel})` : ""}`
      );
      ensureStudioChatVisible();
      await submitBrainstorm(
        `Review these ${targetItems.length} runtime error(s)/freeze(s) caught by the Watchdog Log in ${activeApp ? activeApp.name : "this app"}:\n` +
        summaryLines.join("\n") +
        `\n\nPlease diagnose the root cause of these issues and let me know which ones we should fix first.`
      );
    });
  }

  if (dismissBtn) {
    dismissBtn.addEventListener("click", () => {
      dismissRuntimeAlertBanner();
    });
  }

  if (recoverBtn) {
    recoverBtn.addEventListener("click", async () => {
      const targetTabId = activeTabInstance.tabId || activeTabId;
      if (targetTabId && chrome.tabs) {
        try {
          await chrome.tabs.reload(targetTabId);
          dismissRuntimeAlertBanner();
        } catch (e) {}
      }
    });
  }

  if (investigateBtn) {
    investigateBtn.addEventListener("click", async () => {
      if (!latestRuntimeIssue) return;
      const issue = latestRuntimeIssue;
      dismissRuntimeAlertBanner();
      await investigateWatchdogIssue(issue);
    });
  }

  if (fixBtn) {
    fixBtn.addEventListener("click", async () => {
      if (!latestRuntimeIssue) return;
      const issue = latestRuntimeIssue;
      dismissRuntimeAlertBanner();
      await fixWatchdogIssue(issue);
    });
  }

  setInterval(pollAndInjectRuntimeWatchdog, 2000);
})();

// ============================================================================
// 1. ANTIGRAVITY ERROR RECEPTION, DIAGNOSIS & IN-CHAT RESPONSE CONTROLLER
// ============================================================================
window._latestAntigravityError = null;
window._replyingToAntigravityErrorId = null;
const _renderedAgErrorIds = new Set();

function renderAntigravityErrorChatCard(errObj, attachToBubble = null) {
  if (!errObj || !chatHistoryEl) return;
  const errId = errObj.id || `ag-err-${Date.now()}`;
  if (_renderedAgErrorIds.has(errId) && !attachToBubble) return;
  _renderedAgErrorIds.add(errId);

  const card = document.createElement("div");
  card.className = "antigravity-error-chat-card";
  card.dataset.errorId = errId;
  card.style.cssText = "margin-top:8px; padding:10px 11px; border-radius:10px; background:linear-gradient(135deg, rgba(88,28,135,0.92), rgba(127,29,29,0.92)); border:1.5px solid rgba(248,113,113,0.75); color:#fef2f2; font-size:11px; box-shadow:0 8px 20px rgba(0,0,0,0.45); display:flex; flex-direction:column; gap:7px;";

  const replies = Array.isArray(errObj.suggested_replies) && errObj.suggested_replies.length > 0
    ? errObj.suggested_replies
    : [
        { label: "🔄 Rotate Model & Retry", reply: "Rotate to the next available Gemini model and retry this instruction.", action: "rotate_and_retry" },
        { label: "✂️ Surgical Patch Retry", reply: "Apply this change using surgical edit_file patches on the exact lines.", action: "retry_surgical" },
        { label: "🔍 Diagnose & Explain", reply: "Diagnose this Antigravity error in detail and propose the cleanest fix.", action: "explain" }
      ];

  const actionButtonsHtml = replies.map((r, idx) => `
    <button type="button" class="btn-ag-card-quick-reply" data-idx="${idx}" style="padding:4px 8px; border-radius:6px; font-size:10px; font-weight:700; background:rgba(15,23,42,0.8); color:#f5d0fe; border:1px solid rgba(216,180,254,0.45); cursor:pointer;">
      ${escapeHtml(r.label || "Retry")}
    </button>
  `).join("");

  card.innerHTML = `
    <div style="display:flex; align-items:center; justify-content:space-between; gap:6px; border-bottom:1px solid rgba(248,113,113,0.3); padding-bottom:5px;">
      <div style="display:flex; align-items:center; gap:6px; font-weight:800; color:#fda4af;">
        <i class="fa-solid fa-atom"></i>
        <span>${escapeHtml(errObj.title || "⚠️ Antigravity Error Diagnostic")}</span>
      </div>
      <span style="font-size:9px; padding:1px 6px; border-radius:999px; background:rgba(0,0,0,0.35); color:#f5d0fe; font-family:monospace;">${escapeHtml(errObj.category || "antigravity")}</span>
    </div>
    <div style="background:rgba(15,23,42,0.7); border-radius:7px; padding:7px 9px; border:1px solid rgba(248,113,113,0.3); display:flex; flex-direction:column; gap:5px;">
      <div>
        <div style="font-size:10px; font-weight:800; color:#fca5a5; text-transform:uppercase; letter-spacing:0.04em;">🔍 What the Error Is:</div>
        <div style="font-size:11px; color:#f8fafc; margin-top:2px; line-height:1.4;">${escapeHtml(errObj.what_is_the_error || errObj.raw_error || "Antigravity encountered an error during execution.")}</div>
      </div>
      <div style="border-top:1px dashed rgba(148,163,184,0.25); padding-top:5px;">
        <div style="font-size:10px; font-weight:800; color:#6ee7b7; text-transform:uppercase; letter-spacing:0.04em;">🛠️ What Needs to Be Done:</div>
        <div style="font-size:11px; color:#e2e8f0; margin-top:2px; line-height:1.4;">${escapeHtml(errObj.what_needs_done || "Send a response or retry instruction to Antigravity below.")}</div>
      </div>
    </div>
    <div style="display:flex; flex-wrap:wrap; gap:5px;">
      ${actionButtonsHtml}
    </div>
    <div style="display:flex; align-items:center; gap:5px; margin-top:2px;">
      <input type="text" class="ag-card-reply-input" placeholder="Respond to Antigravity right here in chat..." style="flex:1; background:rgba(2,6,23,0.9); border:1px solid rgba(216,180,254,0.5); color:#f8fafc; border-radius:6px; padding:5px 8px; font-size:10.5px; outline:none;" />
      <button type="button" class="btn-ag-card-send-reply" style="background:linear-gradient(135deg,#a855f7,#ec4899); color:#fff; border:none; border-radius:6px; padding:5px 9px; font-size:10.5px; font-weight:700; cursor:pointer; white-space:nowrap;">
        <i class="fa-solid fa-paper-plane"></i> Send to Antigravity
      </button>
    </div>
  `;

  card.querySelectorAll(".btn-ag-card-quick-reply").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const idx = Number(btn.getAttribute("data-idx") || 0);
      const chosen = replies[idx] || replies[0];
      if (!chosen) return;
      await sendResponseToAntigravityInChat(chosen.reply, errId, chosen.action || "reply", errObj);
    });
  });

  const replyInput = card.querySelector(".ag-card-reply-input");
  const sendBtn = card.querySelector(".btn-ag-card-send-reply");
  const submitInlineReply = async () => {
    const txt = (replyInput ? replyInput.value : "").trim();
    if (!txt) return;
    if (replyInput) replyInput.value = "";
    await sendResponseToAntigravityInChat(txt, errId, "reply", errObj);
  };
  if (sendBtn) sendBtn.addEventListener("click", submitInlineReply);
  if (replyInput) {
    replyInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        submitInlineReply();
      }
    });
  }

  if (attachToBubble) {
    const bodyEl = attachToBubble.querySelector(".ai-body") || attachToBubble;
    bodyEl.appendChild(card);
  } else {
    const bubble = appendChatBubble("ai", `<p>⚛️ <strong>Antigravity reported an error — here is the diagnosis and what needs to be done:</strong></p>`);
    const bodyEl = bubble.querySelector(".ai-body") || bubble;
    bodyEl.appendChild(card);
  }
  chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
}

window.showAntigravityErrorInGalactic = function (errObj, attachToBubble = null) {
  if (!errObj) return;
  window._latestAntigravityError = errObj;

  // 1. Update top Antigravity Error Banner
  const banner = document.getElementById("antigravity-error-banner");
  const titleEl = document.getElementById("ag-err-banner-title");
  const catEl = document.getElementById("ag-err-banner-cat");
  const whatIsEl = document.getElementById("ag-err-what-is");
  const needsDoneEl = document.getElementById("ag-err-what-needs-done");
  const actionsWrap = document.getElementById("ag-err-suggested-actions");
  const countPill = document.getElementById("galactic-ag-err-count-pill");

  if (countPill) {
    countPill.style.display = "inline-block";
    countPill.textContent = "1";
  }

  if (banner) {
    banner.classList.remove("hidden");
    if (titleEl) titleEl.textContent = errObj.title || "Antigravity Error Received";
    if (catEl) catEl.textContent = (errObj.category || "error").toUpperCase();
    if (whatIsEl) whatIsEl.textContent = errObj.what_is_the_error || errObj.raw_error || "";
    if (needsDoneEl) needsDoneEl.textContent = errObj.what_needs_done || "";

    if (actionsWrap) {
      actionsWrap.innerHTML = "";
      const replies = Array.isArray(errObj.suggested_replies) ? errObj.suggested_replies : [];
      replies.forEach((r) => {
        const b = document.createElement("button");
        b.type = "button";
        b.style.cssText = "padding:3px 7px; border-radius:5px; font-size:9.5px; font-weight:700; background:rgba(15,23,42,0.85); color:#f5d0fe; border:1px solid rgba(216,180,254,0.45); cursor:pointer;";
        b.textContent = r.label || "Retry";
        b.addEventListener("click", () => {
          sendResponseToAntigravityInChat(r.reply, errObj.id, r.action || "reply", errObj);
        });
        actionsWrap.appendChild(b);
      });
    }
  }

  // 2. Also render interactive card in the chat stream so the user can respond right inside chat
  renderAntigravityErrorChatCard(errObj, attachToBubble);

  // 3. Speak error diagnosis if voice mode / TTS is active
  if ((window._galacticVoiceChatActive || window._galacticTtsEnabled) && typeof window.speakGeppyText === "function") {
    window.speakGeppyText(`Heads up! Antigravity reported an issue: ${errObj.what_is_the_error || errObj.title}. ${errObj.what_needs_done || "You can reply to Antigravity right in the chat."}`);
  }
};

async function sendResponseToAntigravityInChat(responseText, errorId = null, action = "reply", errObj = null) {
  const cleanText = (responseText || "").trim();
  if (!cleanText) return;

  ensureStudioChatVisible();
  appendChatBubble("user", `<span style="color:#f0abfc; font-weight:700;">[To Antigravity]</span> ${escapeHtml(cleanText)}`);

  const loadingBubble = appendChatBubble(
    "ai",
    `<i class="fa-solid fa-atom fa-spin" style="color:#c084fc;"></i> Sending your response to Antigravity &amp; executing recovery...`
  );

  try {
    const targetErr = errObj || window._latestAntigravityError || {};
    const res = await fetchAntigravityApi("/api/extension/antigravity/respond", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: activeApp ? activeApp.slug : (targetErr.slug || ""),
        response_text: cleanText,
        error_id: errorId || targetErr.id || null,
        action: action || "reply",
        file_path: activeFilePath || targetErr.file_path || "",
        original_instruction: targetErr.instruction || ""
      })
    });

    const data = await res.json();
    loadingBubble.remove();

    const banner = document.getElementById("antigravity-error-banner");
    if (banner && data.success) banner.classList.add("hidden");
    const countPill = document.getElementById("galactic-ag-err-count-pill");
    if (countPill && data.success) countPill.style.display = "none";

    // If Antigravity modified code during the recovery response, update editor & live preview!
    if (data.modified_code && activeApp) {
      const finalFile = data.target_file || activeFilePath;
      if (finalFile && codeEditor) {
        const prevCode = codeEditor.value;
        activeFilePath = finalFile;
        if (fileSelect) fileSelect.value = finalFile;
        codeEditor.value = data.modified_code;
        recordEditedFileState(finalFile, prevCode, data.modified_code, true);
      }
      reloadActiveTab();
      refreshGitStatus();
    }

    const replyMd = data.reply || data.explanation || "Antigravity processed your response.";
    const aiBubble = appendChatBubble("ai", formatMarkdown(replyMd));
    if (Array.isArray(data.tool_steps) && data.tool_steps.length > 0) {
      attachAntigravityToolTraceToBubble(aiBubble, data.tool_steps, data.engine || "antigravity_sdk", data.modified_files || []);
    }
    if ((window._galacticVoiceChatActive || window._galacticTtsEnabled) && typeof window.speakGeppyText === "function") {
      window.speakGeppyText(replyMd);
    }
  } catch (err) {
    loadingBubble.remove();
    appendChatBubble("ai", `⚠️ Could not reach Antigravity respond endpoint: ${escapeHtml(String(err))}`);
  }
}

async function pollAntigravityErrorsForGalactic() {
  try {
    const slugParam = activeApp && activeApp.slug ? `?slug=${encodeURIComponent(activeApp.slug)}` : "";
    const res = await fetch(`${SERVER_URL}/api/extension/antigravity/errors${slugParam}`);
    if (!res.ok) return;
    const data = await res.json();
    const countPill = document.getElementById("galactic-ag-err-count-pill");
    if (countPill) {
      if (data.open_count > 0) {
        countPill.style.display = "inline-block";
        countPill.textContent = String(data.open_count);
      } else {
        countPill.style.display = "none";
      }
    }
    if (data.latest_error && data.latest_error.status === "open") {
      if (!_renderedAgErrorIds.has(data.latest_error.id)) {
        window.showAntigravityErrorInGalactic(data.latest_error);
      }
    }
  } catch (e) {}
}

// ============================================================================
// 2. LIVE SCREEN STREAMING CONTROLLER (GALACTIC TAB + FULL SCREEN + GITBRIDGE)
// ============================================================================
window._galacticScreenStreamActive = false;
window._latestGalacticStreamFrameB64 = null;
let _galacticStreamInterval = null;
let _galacticDisplayMediaStream = null;
let _galacticDisplayVideoEl = null;

window.captureGalacticTabFrameB64 = async function () {
  // 1. If full screen/window MediaStream is active, grab frame from video element
  if (_galacticDisplayMediaStream && _galacticDisplayVideoEl && _galacticDisplayVideoEl.readyState >= 2) {
    try {
      const canvas = document.createElement("canvas");
      const w = Math.min(1280, _galacticDisplayVideoEl.videoWidth || 1280);
      const h = Math.min(800, _galacticDisplayVideoEl.videoHeight || 720);
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(_galacticDisplayVideoEl, 0, 0, w, h);
      return canvas.toDataURL("image/jpeg", 0.72);
    } catch (e) {}
  }

  // 2. Otherwise capture the active browser tab directly via chrome.tabs.captureVisibleTab (zero permission prompt!)
  if (typeof chrome !== "undefined" && chrome.tabs && chrome.tabs.captureVisibleTab) {
    return new Promise((resolve) => {
      try {
        chrome.tabs.captureVisibleTab(null, { format: "jpeg", quality: 68 }, (dataUrl) => {
          if (chrome.runtime && chrome.runtime.lastError) {
            resolve(null);
            return;
          }
          resolve(dataUrl || null);
        });
      } catch (err) {
        resolve(null);
      }
    });
  }
  return null;
};

async function pushGalacticStreamTick() {
  if (!window._galacticScreenStreamActive) return;
  const frameB64 = await window.captureGalacticTabFrameB64();
  if (frameB64) {
    window._latestGalacticStreamFrameB64 = frameB64;
    const thumbImg = document.getElementById("galactic-stream-thumb-img");
    if (thumbImg) thumbImg.src = frameB64;

    try {
      await fetch(`${SERVER_URL}/api/live-stream/frame`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: "galactic",
          frame_b64: frameB64,
          app_slug: activeApp ? activeApp.slug : "",
          viewport_title: activeApp ? `${activeApp.name} (Galactic Live)` : "Galactic Browser Viewport",
          viewport_url: currentBrowserTabUrl || ""
        })
      });
    } catch (e) {}
  }

  // Also check if GitBridge Web UI is streaming its screen so we can show both thumbnails
  try {
    const stRes = await fetch(`${SERVER_URL}/api/live-stream/status?include_thumbnails=true`);
    if (stRes.ok) {
      const st = await stRes.json();
      const gbStream = st.streams && st.streams.gitbridge;
      const gbWrap = document.getElementById("gitbridge-stream-thumb-wrap");
      const gbImg = document.getElementById("gitbridge-stream-thumb-img");
      const subEl = document.getElementById("galactic-stream-status-sub");
      if (gbStream && gbStream.active && gbStream.frame_b64) {
        if (gbWrap) gbWrap.classList.remove("hidden");
        if (gbImg) gbImg.src = gbStream.frame_b64;
        if (subEl) subEl.textContent = "Streaming BOTH Galactic + GitBridge screens live to Geppy!";
      } else {
        if (gbWrap) gbWrap.classList.add("hidden");
      }
    }
  } catch (e) {}
}

async function startGalacticScreenStream(useFullDisplayMedia = false) {
  if (useFullDisplayMedia && navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia) {
    try {
      _galacticDisplayMediaStream = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: { ideal: 2, max: 5 } },
        audio: false
      });
      _galacticDisplayVideoEl = document.createElement("video");
      _galacticDisplayVideoEl.muted = true;
      _galacticDisplayVideoEl.playsInline = true;
      _galacticDisplayVideoEl.srcObject = _galacticDisplayMediaStream;
      await _galacticDisplayVideoEl.play();
      const track = _galacticDisplayMediaStream.getVideoTracks()[0];
      if (track) {
        track.addEventListener("ended", () => {
          stopGalacticScreenStream();
        });
      }
    } catch (err) {
      console.warn("Full display media cancelled or unavailable, falling back to tab capture:", err);
    }
  }

  window._galacticScreenStreamActive = true;
  const dock = document.getElementById("galactic-stream-preview-dock");
  const btn = document.getElementById("btn-galactic-stream-toggle");
  const lbl = document.getElementById("galactic-stream-btn-label");
  if (dock) dock.classList.remove("hidden");
  if (btn) {
    btn.style.background = "rgba(239, 68, 68, 0.25)";
    btn.style.borderColor = "#f87171";
    btn.style.color = "#fecaca";
  }
  if (lbl) lbl.textContent = "Streaming LIVE";

  await pushGalacticStreamTick();
  if (_galacticStreamInterval) clearInterval(_galacticStreamInterval);
  _galacticStreamInterval = setInterval(pushGalacticStreamTick, 2500);
}

async function stopGalacticScreenStream() {
  window._galacticScreenStreamActive = false;
  if (_galacticStreamInterval) {
    clearInterval(_galacticStreamInterval);
    _galacticStreamInterval = null;
  }
  if (_galacticDisplayMediaStream) {
    _galacticDisplayMediaStream.getTracks().forEach((t) => t.stop());
    _galacticDisplayMediaStream = null;
  }
  _galacticDisplayVideoEl = null;

  const dock = document.getElementById("galactic-stream-preview-dock");
  const btn = document.getElementById("btn-galactic-stream-toggle");
  const lbl = document.getElementById("galactic-stream-btn-label");
  if (dock) dock.classList.add("hidden");
  if (btn) {
    btn.style.background = "rgba(6, 182, 212, 0.15)";
    btn.style.borderColor = "rgba(6, 182, 212, 0.4)";
    btn.style.color = "#67e8f9";
  }
  if (lbl) lbl.textContent = "Stream Screen";

  try {
    await fetch(`${SERVER_URL}/api/live-stream/stop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: "galactic" })
    });
  } catch (e) {}
}

// ============================================================================
// 3. LIVE VOICE CHAT WITH GEPPY + AGENT CREW CONSULTATION CONTROLLER
// ============================================================================
window._galacticVoiceChatActive = false;
window._galacticTtsEnabled = localStorage.getItem("geppy_voice_tts") === "1";
window._galacticConsultCrewEnabled = false;
let _galacticSpeechRecognition = null;

window.speakGeppyText = function (rawText) {
  if (!("speechSynthesis" in window)) return;
  const clean = String(rawText || "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/[#*_`>|~]/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 520);
  if (!clean) return;
  try {
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(clean);
    utter.rate = 1.04;
    utter.pitch = 1.0;
    const voices = window.speechSynthesis.getVoices();
    const preferred = voices.find((v) => /Google US English|Microsoft Guy|Microsoft Aria|Natural|English/i.test(v.name));
    if (preferred) utter.voice = preferred;
    window.speechSynthesis.speak(utter);
  } catch (e) {}
};

function toggleGalacticVoiceChat(forceState = null) {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) {
    alert("Speech recognition is not supported in this browser context.");
    return;
  }

  const nextState = forceState !== null ? forceState : !window._galacticVoiceChatActive;
  const btn = document.getElementById("btn-galactic-voice-toggle");
  const lbl = document.getElementById("galactic-voice-btn-label");

  if (!nextState) {
    window._galacticVoiceChatActive = false;
    if (_galacticSpeechRecognition) {
      try { _galacticSpeechRecognition.stop(); } catch (e) {}
    }
    if (btn) {
      btn.style.background = "rgba(16, 185, 129, 0.15)";
      btn.style.borderColor = "rgba(16, 185, 129, 0.4)";
      btn.style.color = "#6ee7b7";
    }
    if (lbl) lbl.textContent = "Voice Chat";
    return;
  }

  window._galacticVoiceChatActive = true;
  window._galacticTtsEnabled = true;
  localStorage.setItem("geppy_voice_tts", "1");
  updateGalacticTtsButtonUi();

  if (btn) {
    btn.style.background = "rgba(239, 68, 68, 0.28)";
    btn.style.borderColor = "#f87171";
    btn.style.color = "#fecaca";
  }
  if (lbl) lbl.textContent = "🎙️ Listening...";

  if (!_galacticSpeechRecognition) {
    _galacticSpeechRecognition = new SpeechRec();
    _galacticSpeechRecognition.continuous = true;
    _galacticSpeechRecognition.interimResults = true;
    _galacticSpeechRecognition.lang = "en-US";

    _galacticSpeechRecognition.onresult = (event) => {
      let interimTranscript = "";
      let finalTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }
      if (brainstormInput && interimTranscript) {
        brainstormInput.value = interimTranscript;
      }
      if (finalTranscript && finalTranscript.trim()) {
        const spokenMsg = finalTranscript.trim();
        if (brainstormInput) brainstormInput.value = "";
        submitBrainstorm(spokenMsg, {
          voice_mode: true,
          consult_crew: window._galacticConsultCrewEnabled
        });
      }
    };

    _galacticSpeechRecognition.onend = () => {
      if (window._galacticVoiceChatActive) {
        try { _galacticSpeechRecognition.start(); } catch (e) {}
      }
    };
  }

  try {
    _galacticSpeechRecognition.start();
  } catch (e) {}
}

function updateGalacticTtsButtonUi() {
  const ttsBtn = document.getElementById("btn-galactic-tts-toggle");
  if (!ttsBtn) return;
  ttsBtn.textContent = window._galacticTtsEnabled ? "🔊" : "🔇";
  ttsBtn.style.color = window._galacticTtsEnabled ? "#34d399" : "#94a3b8";
  ttsBtn.style.borderColor = window._galacticTtsEnabled ? "rgba(16, 185, 129, 0.45)" : "rgba(148, 163, 184, 0.3)";
}

(function initGalacticLiveCoDesignerControls() {
  const btnStreamToggle = document.getElementById("btn-galactic-stream-toggle");
  const btnStreamFull = document.getElementById("btn-galactic-stream-full-window");
  const btnStreamStop = document.getElementById("btn-galactic-stream-stop");
  const btnVoiceToggle = document.getElementById("btn-galactic-voice-toggle");
  const btnConsultToggle = document.getElementById("btn-galactic-consult-crew-toggle");
  const btnConsultNow = document.getElementById("btn-galactic-consult-now");
  const btnTtsToggle = document.getElementById("btn-galactic-tts-toggle");
  const btnAgErrCheck = document.getElementById("btn-galactic-ag-error-check");
  const btnAgErrDismiss = document.getElementById("btn-ag-err-dismiss");
  const btnAgErrSendReply = document.getElementById("btn-ag-err-send-reply");
  const agErrInlineInput = document.getElementById("ag-err-inline-input");

  updateGalacticTtsButtonUi();

  if (btnStreamToggle) {
    btnStreamToggle.addEventListener("click", () => {
      if (window._galacticScreenStreamActive) {
        stopGalacticScreenStream();
      } else {
        startGalacticScreenStream(false);
      }
    });
  }
  if (btnStreamFull) {
    btnStreamFull.addEventListener("click", () => {
      startGalacticScreenStream(true);
    });
  }
  if (btnStreamStop) {
    btnStreamStop.addEventListener("click", () => {
      stopGalacticScreenStream();
    });
  }
  if (btnVoiceToggle) {
    btnVoiceToggle.addEventListener("click", () => {
      toggleGalacticVoiceChat();
    });
  }
  if (btnConsultToggle) {
    btnConsultToggle.addEventListener("click", () => {
      window._galacticConsultCrewEnabled = !window._galacticConsultCrewEnabled;
      const lbl = document.getElementById("galactic-consult-btn-label");
      if (lbl) lbl.textContent = `Consult Crew: ${window._galacticConsultCrewEnabled ? "ON" : "OFF"}`;
      btnConsultToggle.style.background = window._galacticConsultCrewEnabled
        ? "rgba(245, 158, 11, 0.32)"
        : "rgba(245, 158, 11, 0.16)";
      btnConsultToggle.style.borderColor = window._galacticConsultCrewEnabled
        ? "#f59e0b"
        : "rgba(245, 158, 11, 0.4)";
    });
  }
  if (btnConsultNow) {
    btnConsultNow.addEventListener("click", async () => {
      ensureStudioChatVisible();
      const customPrompt = (brainstormInput && brainstormInput.value.trim())
        ? brainstormInput.value.trim()
        : "Consult with the Agent Crew (@design, @arch, @qa, @strategy) on what we are working on right now and tell me your top recommendations.";
      if (brainstormInput) brainstormInput.value = "";
      await submitBrainstorm(customPrompt, {
        consult_crew: true,
        voice_mode: window._galacticVoiceChatActive || window._galacticTtsEnabled
      });
    });
  }
  if (btnTtsToggle) {
    btnTtsToggle.addEventListener("click", () => {
      window._galacticTtsEnabled = !window._galacticTtsEnabled;
      localStorage.setItem("geppy_voice_tts", window._galacticTtsEnabled ? "1" : "0");
      if (!window._galacticTtsEnabled && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
      updateGalacticTtsButtonUi();
    });
  }
  if (btnAgErrCheck) {
    btnAgErrCheck.addEventListener("click", async () => {
      await pollAntigravityErrorsForGalactic();
      if (window._latestAntigravityError) {
        window.showAntigravityErrorInGalactic(window._latestAntigravityError);
      } else {
        const pasted = prompt("No open Antigravity errors detected automatically. Paste any Antigravity error message here to have Geppy diagnose what the error is, what needs to be done, and open an in-chat reply channel to Antigravity:");
        if (pasted && pasted.trim()) {
          try {
            const r = await fetch(`${SERVER_URL}/api/extension/antigravity/report-error`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                error: pasted.trim(),
                slug: activeApp ? activeApp.slug : "",
                file_path: activeFilePath || ""
              })
            });
            const d = await r.json();
            if (d && d.error) {
              window.showAntigravityErrorInGalactic(d.error);
            }
          } catch (e) {}
        }
      }
    });
  }
  if (btnAgErrDismiss) {
    btnAgErrDismiss.addEventListener("click", async () => {
      const banner = document.getElementById("antigravity-error-banner");
      if (banner) banner.classList.add("hidden");
      try {
        await fetch(`${SERVER_URL}/api/extension/antigravity/errors/clear`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            error_id: window._latestAntigravityError ? window._latestAntigravityError.id : null
          })
        });
      } catch (e) {}
    });
  }
  const submitBannerReply = async () => {
    const txt = (agErrInlineInput ? agErrInlineInput.value : "").trim();
    if (!txt) return;
    if (agErrInlineInput) agErrInlineInput.value = "";
    const errId = window._latestAntigravityError ? window._latestAntigravityError.id : null;
    await sendResponseToAntigravityInChat(txt, errId, "reply", window._latestAntigravityError);
  };
  if (btnAgErrSendReply) {
    btnAgErrSendReply.addEventListener("click", submitBannerReply);
  }
  if (agErrInlineInput) {
    agErrInlineInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        submitBannerReply();
      }
    });
  }

  // Poll Antigravity errors every 4 seconds so any background/SDK Antigravity error immediately surfaces in Galactic
  setInterval(pollAntigravityErrorsForGalactic, 4000);
})();



