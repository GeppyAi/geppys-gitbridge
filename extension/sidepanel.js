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
let isChatImageMode = false;
const backlogCount = document.getElementById("backlog-count");
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

// Central API Key Vault elements
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

// Unrecognized Tab Bar & Registration Modal Elements
let lastDetectedUnrecognized = null;
let activeTabInstance = { tabId: null, url: null, port: null, slug: null };
const unrecognizedAppBar = document.getElementById("unrecognized-app-bar");
const unrecognizedUrlLabel = document.getElementById("unrecognized-url-label");
const btnReassociateTab = document.getElementById("btn-reassociate-tab");
const reassociateBtnText = document.getElementById("reassociate-btn-text");
const btnShowAddAppModal = document.getElementById("btn-show-add-app-modal");
const btnHeaderAddApp = document.getElementById("btn-header-add-app");

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
  await checkServerConnection();
  await checkCentralKeyStatus();

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
  if (btnChatModeImage) btnChatModeImage.addEventListener("click", () => toggleChatImageMode());
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

// --- Mode Switcher ---
function switchMode(mode) {
  currentMode = mode;
  if (mode === "brainstorm") {
    btnModeBrainstorm.classList.add("active");
    btnModeDesigner.classList.remove("active");
    if (btnModeAssets) btnModeAssets.classList.remove("active");
    viewBrainstorm.classList.remove("hidden");
    viewDesigner.classList.add("hidden");
    if (viewAssets) viewAssets.classList.add("hidden");
  } else if (mode === "designer") {
    btnModeDesigner.classList.add("active");
    btnModeBrainstorm.classList.remove("active");
    if (btnModeAssets) btnModeAssets.classList.remove("active");
    viewDesigner.classList.remove("hidden");
    viewBrainstorm.classList.add("hidden");
    if (viewAssets) viewAssets.classList.add("hidden");

    // Ensure file tree is loaded for current app
    if (activeApp && (!fileSelect.options || fileSelect.options.length <= 1)) {
      loadFileTree(activeApp.slug);
    }
    // Sync backlog picker dropdown in designer
    updateDesignerTaskPicker();
  } else if (mode === "assets") {
    if (btnModeAssets) btnModeAssets.classList.add("active");
    btnModeBrainstorm.classList.remove("active");
    btnModeDesigner.classList.remove("active");
    if (viewAssets) viewAssets.classList.remove("hidden");
    viewBrainstorm.classList.add("hidden");
    viewDesigner.classList.add("hidden");

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

// --- Central API Key Vault Handlers ---
async function checkCentralKeyStatus() {
  if (!centralKeyLabel) return;
  try {
    const res = await fetch(`${SERVER_URL}/api/keys/status`);
    if (res.ok) {
      const data = await res.json();
      if (data.configured) {
        if (btnCentralKeyVault) {
          btnCentralKeyVault.className = "key-vault-badge active";
          btnCentralKeyVault.title = `Central Vault Active (${data.masked_key}) - Click for options`;
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
          btnCentralKeyVault.className = "key-vault-badge missing";
          btnCentralKeyVault.title = "No Gemini API Key found in Central Vault - Click to configure";
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
    if (btnCentralKeyVault) btnCentralKeyVault.className = "key-vault-badge missing";
    if (centralKeyLabel) centralKeyLabel.innerText = "Key: Offline";
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
  viewAllChip.addEventListener("click", () => openSotFleetModal());
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

// --- Active Tab App Detection & Instance Tracking ---
let tabAppMap = {};   // tabId -> appSlug
let hostAppMap = {};  // hostname:port -> appSlug

async function detectActiveTabApp() {
  if (typeof chrome === "undefined" || !chrome.tabs) return;

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.url) {
      activeTabId = tab.id;
      await detectAppFromUrl(tab.url, tab.id);
    }
  } catch (e) {
    console.warn("Could not query active tab:", e);
  }
}

async function detectAppFromUrl(url, explicitTabId = null) {
  if (!url) return;
  const currentTabId = explicitTabId || activeTabId;
  if (currentTabId) activeTabId = currentTabId;

  let parsedHost = null;
  let isLocal = false;
  try {
    const parsedTab = new URL(url);
    parsedHost = parsedTab.host;
    isLocal = ["localhost", "127.0.0.1", "0.0.0.0"].includes(parsedTab.hostname);
  } catch (e) {}

  // 1. Check if tabId or host was already mapped to a specific app
  if (currentTabId && tabAppMap[currentTabId]) {
    const mappedSlug = tabAppMap[currentTabId];
    const targetApp = apps.find((a) => a.slug === mappedSlug);
    if (targetApp) {
      if (unrecognizedAppBar) unrecognizedAppBar.classList.add("hidden");
      lastDetectedUnrecognized = null;
      activeTabInstance.tabId = currentTabId;
      activeTabInstance.url = url;
      activeTabInstance.slug = targetApp.slug;
      if (!activeApp || activeApp.slug !== targetApp.slug) {
        await setActiveApp(targetApp);
      }
      return;
    }
  }

  if (parsedHost && hostAppMap[parsedHost]) {
    const mappedSlug = hostAppMap[parsedHost];
    const targetApp = apps.find((a) => a.slug === mappedSlug);
    if (targetApp) {
      if (unrecognizedAppBar) unrecognizedAppBar.classList.add("hidden");
      lastDetectedUnrecognized = null;
      activeTabInstance.tabId = currentTabId;
      activeTabInstance.url = url;
      activeTabInstance.slug = targetApp.slug;
      if (currentTabId) tabAppMap[currentTabId] = targetApp.slug;
      if (!activeApp || activeApp.slug !== targetApp.slug) {
        await setActiveApp(targetApp);
      }
      return;
    }
  }

  // 2. Is this tab URL or tabId already known to be our active app instance?
  if (activeApp) {
    let isSameAppInstance = false;
    try {
      if (activeApp.live_url) {
        const parsedLive = new URL(activeApp.live_url);
        if (parsedHost && parsedHost === parsedLive.host) {
          isSameAppInstance = true;
        } else if (isLocal && parsedLive.port) {
          const u = new URL(url);
          if (u.port === parsedLive.port) isSameAppInstance = true;
        }
      }

      if (activeTabInstance.tabId && activeTabInstance.tabId === currentTabId && activeTabInstance.slug === activeApp.slug && isLocal) {
        isSameAppInstance = true;
      }
    } catch (e) {}

    if (isSameAppInstance) {
      if (unrecognizedAppBar) unrecognizedAppBar.classList.add("hidden");
      lastDetectedUnrecognized = null;
      activeTabInstance.tabId = currentTabId;
      activeTabInstance.url = url;
      activeTabInstance.slug = activeApp.slug;
      if (currentTabId) tabAppMap[currentTabId] = activeApp.slug;
      if (parsedHost) hostAppMap[parsedHost] = activeApp.slug;
      return;
    }
  }

  // 3. Query backend detect-app
  try {
    const res = await fetch(`${SERVER_URL}/api/extension/detect-app?url=${encodeURIComponent(url)}`);
    if (res.ok) {
      const data = await res.json();
      if (data.matched && data.app) {
        if (unrecognizedAppBar) unrecognizedAppBar.classList.add("hidden");
        lastDetectedUnrecognized = null;
        activeTabInstance.tabId = currentTabId;
        activeTabInstance.url = url;
        activeTabInstance.slug = data.app.slug;
        if (currentTabId) tabAppMap[currentTabId] = data.app.slug;
        if (parsedHost) hostAppMap[parsedHost] = data.app.slug;
        await setActiveApp(data.app);
        return;
      } else {
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
}

async function onAppSelected(slug) {
  if (!slug) return;
  const app = apps.find((a) => a.slug === slug);
  if (app) await setActiveApp(app);
}

async function setActiveApp(app) {
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
    if (activeTabId) tabAppMap[activeTabId] = app.slug;
    return;
  }

  // 1. If switching away from another app, save its chat history first!
  if (activeApp && activeApp.slug) {
    await saveAppChatHistory(activeApp.slug, chatHistory);
  }

  activeApp = app;
  appSelect.value = app.slug;

  // Track active app instance & mappings
  activeTabInstance.slug = app.slug;
  if (app.live_url) {
    activeTabInstance.url = app.live_url;
    try {
      const u = new URL(app.live_url);
      activeTabInstance.port = u.port || "80";
      hostAppMap[u.host] = app.slug;
    } catch (e) {}
  }
  if (activeTabId) {
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
  } else {
    appLiveBadge.style.display = "none";
  }

  // 2. Load dedicated Chat History for this specific app
  await loadAppChatHistory(app.slug);

  // 3. Load backlog
  await loadBacklog(app.slug);

  // 4. Load file tree for designer
  await loadFileTree(app.slug);

  // 5. Load Git status & Session Changelog
  loadSessionLog(app.slug);
  await refreshGitStatus();

  // 6. If in Asset Lab mode, load app images
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

function renderChatHistoryForActiveApp() {
  if (!chatHistoryEl) return;
  chatHistoryEl.innerHTML = "";

  const appName = activeApp ? activeApp.name : "Active Application";

  // Captain Geppy Welcome Banner personalized for this app
  const welcomeBubble = document.createElement("div");
  welcomeBubble.className = "chat-bubble ai";
  welcomeBubble.innerHTML = `
    <div class="captain-badge">
      <span class="captain-avatar"><img src="icons/icon48.png" alt="Captain Geppy" class="captain-avatar-img" /></span>
      <div>
        <strong style="color: #818cf8;">Captain Geppy</strong>
        <span class="captain-sub">Galactic Commander &bull; ${escapeHtml(appName)}</span>
      </div>
    </div>
    <div class="ai-body">
      <p>Greetings, Commander! Welcome aboard <strong>Geppy's Galactic</strong> for <strong>${escapeHtml(appName)}</strong>.</p>
      <p>I am Captain Geppy, your pilot for <em>${escapeHtml(appName)}</em>. Click the ideation pills above or ask me for visual makeovers, UX polish, and killer features tailored specifically to this project!</p>
      <p>🛸 <strong>Source of Truth:</strong> Click <strong>SOT Fleet</strong> above or type <code>@contextile_name</code> to anchor ideas in your saved standards.</p>
    </div>
  `;
  chatHistoryEl.appendChild(welcomeBubble);

  // Render each conversation turn for this app
  chatHistory.forEach((msg) => {
    if (msg.sender === "user") {
      appendChatBubble("user", escapeHtml(msg.text));
    } else {
      const bubble = appendChatBubble("ai", formatMarkdown(msg.text));
      if (msg.extracted_tasks && msg.extracted_tasks.length > 0) {
        attachIdeasDockToBubble(bubble, msg.extracted_tasks);
      }
      if (msg.image_data) {
        attachImageCardToBubble(bubble, msg.image_data);
      }
    }
  });

  chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
}

function attachIdeasDockToBubble(aiBubble, extractedTasks) {
  if (!aiBubble || !extractedTasks || extractedTasks.length === 0) return;
  const targetContainer = aiBubble.querySelector(".ai-body") || aiBubble;

  // Avoid duplicate docks
  if (targetContainer.querySelector(".chat-ideas-box")) return;

  const ideasDock = document.createElement("div");
  ideasDock.className = "chat-ideas-box";
  ideasDock.innerHTML = `
    <div class="chat-ideas-header">
      <i class="fa-solid fa-list-check" style="color: #818cf8;"></i>
      <span>Proposed Ideas (${extractedTasks.length})</span>
      <span class="chat-ideas-sub">Select or click to implement directly</span>
    </div>
    <div class="chat-ideas-list"></div>
  `;
  const listEl = ideasDock.querySelector(".chat-ideas-list");

  extractedTasks.forEach((t) => {
    // Check if task exists in backlogTasks to mirror completion status
    const existingTask = backlogTasks.find((bt) => bt.id === t.id || bt.title === t.title);
    const isCompleted = existingTask ? existingTask.completed : (t.completed || false);
    const taskObj = existingTask || {
      id: t.id || `task-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
      title: t.title,
      category: t.category || "feature",
      description: t.description || "",
      suggested_prompt: t.suggested_prompt || t.title,
      completed: isCompleted
    };

    const ideaCard = document.createElement("div");
    const catClass = ["design", "feature", "ux", "polish"].includes(taskObj.category?.toLowerCase())
      ? taskObj.category.toLowerCase()
      : "feature";

    function updateChatCardUi() {
      if (taskObj.completed) {
        ideaCard.className = "chat-idea-card completed";
        ideaCard.innerHTML = `
          <div class="chat-idea-info">
            <div style="display: flex; align-items: center; gap: 5px; flex-wrap: wrap;">
              <span class="chat-idea-done-badge"><i class="fa-solid fa-check"></i> In Done Pile</span>
              <span class="task-tag ${catClass}">${escapeHtml(taskObj.category || "Task")}</span>
              <strong>${escapeHtml(taskObj.title)}</strong>
            </div>
            <div class="chat-idea-desc">${escapeHtml(taskObj.description || "")}</div>
          </div>
          <div class="chat-idea-actions">
            <button type="button" class="btn-chat-view-done" title="Open and view this task in the Done Pile">
              <i class="fa-solid fa-folder-closed"></i> View in Done
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
            await saveBacklogToServer();
            renderBacklog();
            updateDesignerTaskPicker();
            updateChatCardUi();
          });
        }
      } else {
        ideaCard.className = "chat-idea-card";
        ideaCard.innerHTML = `
          <div class="chat-idea-info">
            <div style="display: flex; align-items: center; gap: 4px;">
              <span class="task-tag ${catClass}">${escapeHtml(taskObj.category || "Task")}</span>
              <strong>${escapeHtml(taskObj.title)}</strong>
            </div>
            <div class="chat-idea-desc">${escapeHtml(taskObj.description || "")}</div>
          </div>
          <div class="chat-idea-actions">
            <label class="chat-idea-done-label" title="File this idea directly to Done Pile">
              <input type="checkbox" class="chk-chat-done"> Done
            </label>
            <button type="button" class="btn-chat-implement" title="Automatically implement this idea into code, save to disk, and reload app">
              <i class="fa-solid fa-wand-magic-sparkles"></i>
              <span>Implement Now</span>
            </button>
            <button type="button" class="btn-task-config btn-chat-config" title="Configure target file & implementation options">
              <i class="fa-solid fa-gear"></i>
            </button>
          </div>
        `;
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
          });
        }
      }
    }

    updateChatCardUi();
    listEl.appendChild(ideaCard);
  });

  targetContainer.appendChild(ideasDock);
}

function toggleChatImageMode(forceVal = null) {
  if (forceVal !== null) isChatImageMode = forceVal;
  else isChatImageMode = !isChatImageMode;

  if (btnChatModeImage) {
    btnChatModeImage.classList.toggle("active", isChatImageMode);
  }
  if (brainstormInput) {
    if (isChatImageMode) {
      brainstormInput.placeholder = "🎨 Describe image or icon to generate (e.g. Captain Geppy on Mars, Hex badge)...";
      brainstormInput.focus();
    } else {
      brainstormInput.placeholder = "Ask Captain Geppy or type /image to generate visuals...";
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
          if (newTab) {
            activeTabId = newTab.id;
            activeTabInstance.tabId = newTab.id;
            activeTabInstance.url = data.target;
            activeTabInstance.slug = activeApp.slug;
            try {
              const u = new URL(data.target);
              activeTabInstance.port = u.port || "80";
            } catch (e) {}
          }
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
          if (newTab) {
            activeTabId = newTab.id;
            activeTabInstance.tabId = newTab.id;
            activeTabInstance.url = data.target;
            activeTabInstance.slug = activeApp.slug;
            try {
              const u = new URL(data.target);
              activeTabInstance.port = u.port || "80";
            } catch (e) {}
          }
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
  chatHistory.push({ sender: "user", text: prompt, timestamp: Date.now() });
  if (activeApp && activeApp.slug) {
    saveAppChatHistory(activeApp.slug, chatHistory);
  }

  logSessionChange("brainstorm", `Chat with Captain Geppy: "${prompt.substring(0, 45)}${prompt.length > 45 ? "..." : ""}"`);

  const isImgReq = isChatImageMode ||
    prompt.startsWith("/image") || prompt.startsWith("/img") || prompt.startsWith("/icon") || prompt.startsWith("/draw") || prompt.startsWith("/pic") ||
    /\b(generate|create|make|draw|synthesize|design)\s+(an?\s+)?(app\s+)?(image|icon|logo|badge|mascot|graphic|sticker|artwork)\b/i.test(prompt);

  const loadingText = isImgReq
    ? '<i class="fa-solid fa-spinner animate-spin text-amber"></i> Captain Geppy is synthesizing your visual asset...'
    : '<i class="fa-solid fa-spinner animate-spin"></i> Captain Geppy is navigating the Galactic stars...';

  const loadingBubble = appendChatBubble("ai", loadingText);

  btnSendBrainstorm.disabled = true;

  try {
    const res = await fetch(`${SERVER_URL}/api/extension/brainstorm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug: activeApp ? activeApp.slug : "",
        message: prompt,
        history: chatHistory,
        file_path: activeFilePath,
        is_image: isImgReq
      })
    });

    const data = await res.json();
    loadingBubble.remove();

    if (res.ok) {
      const aiBubble = appendChatBubble("ai", formatMarkdown(data.text));
      chatHistory.push({
        sender: "ai",
        text: data.text,
        is_image: data.is_image || false,
        image_data: data.image_data || null,
        extracted_tasks: data.extracted_tasks || [],
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

      // Automatically incorporate newly extracted ideas into backlog & chat dock!
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

        attachIdeasDockToBubble(aiBubble, data.extracted_tasks);
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

function appendChatBubble(sender, htmlContent) {
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${sender}`;
  if (sender === "ai") {
    bubble.innerHTML = `
      <div class="captain-badge">
        <span class="captain-avatar"><img src="icons/icon48.png" alt="Captain Geppy" class="captain-avatar-img" /></span>
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
      activeTasks.forEach((t) => {
        const card = document.createElement("div");
        card.className = "task-card";
        const catClass = ["design", "feature", "ux", "polish"].includes(t.category?.toLowerCase())
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
              <i class="fa-solid fa-wand-magic-sparkles"></i> Implement Now
            </button>
            <button type="button" class="btn-task-config" title="Configure target file & implementation options">
              <i class="fa-solid fa-gear"></i>
            </button>
          </div>
        `;

        // Batch Select Checkbox
        const chkSelect = card.querySelector(".chk-task-select");
        if (chkSelect) {
          chkSelect.addEventListener("change", (e) => {
            if (e.target.checked) {
              selectedTaskIds.add(t.id);
            } else {
              selectedTaskIds.delete(t.id);
            }
            updateBatchBarState();
          });
        }

        // Done Checkbox (Files directly to Done Pile)
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

        // Delete Button
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

        // Configure Button (Gear)
        const btnCfg = card.querySelector(".btn-task-config");
        if (btnCfg) {
          btnCfg.addEventListener("click", () => {
            openImplementationModal(t, card);
          });
        }

        // Implement Now Button
        const btnImplement = card.querySelector(".btn-push-designer");
        if (btnImplement) {
          btnImplement.addEventListener("click", () => {
            implementTaskDirectly(t, card);
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

function toggleBacklogDrawer(forceExpand = null) {
  if (!backlogDrawer) return;
  const isCollapsed = (backlogDrawer.style.maxHeight === "38px");
  const shouldExpand = (forceExpand !== null) ? forceExpand : isCollapsed;
  if (shouldExpand) {
    backlogDrawer.style.maxHeight = "45%";
    if (btnToggleBacklog) btnToggleBacklog.innerHTML = '<i class="fa-solid fa-chevron-up"></i>';
  } else {
    backlogDrawer.style.maxHeight = "38px";
    if (btnToggleBacklog) btnToggleBacklog.innerHTML = '<i class="fa-solid fa-chevron-down"></i>';
  }
}

// --- Implementation Control Center & Smart Target File Guessing ---
function guessBestTargetFile(task, fileList = []) {
  if (!fileList || fileList.length === 0) return activeFilePath || "";
  const paths = fileList.map(f => (typeof f === "object" && f ? f.path : f)).filter(Boolean);
  const text = `${task.title || ""} ${task.description || ""} ${task.suggested_prompt || ""} ${task.category || ""}`.toLowerCase();

  // 1. Icon or Favicon or Head or Metadata -> index.html / public/index.html / manifest.json
  if (/icon|favicon|meta|head|title|header|manifest/i.test(text)) {
    const m = paths.find(p => /index\.html$/i.test(p)) || paths.find(p => /manifest\.json$/i.test(p));
    if (m) return m;
  }
  // 2. Styling, CSS, Theme, Color, Font -> CSS files
  if (/style|css|theme|color|dark mode|font|gradient|background|border/i.test(text)) {
    const m = paths.find(p => /\.(css|scss|sass|less)$/i.test(p));
    if (m) return m;
  }
  // 3. Backend, API, Route, Database, Endpoint -> Python / Node server files
  if (/api|endpoint|route|backend|database|query|db|server|controller|handler/i.test(text)) {
    const m = paths.find(p => /(main|app|server|api|routes)\.(py|js|ts)$/i.test(p));
    if (m) return m;
  }
  // 4. UI Component, Button, Modal, Drawer, View -> Frontend components or App.jsx/index.html
  if (/component|button|modal|drawer|navbar|footer|card|table|view|page|screen/i.test(text)) {
    const m = paths.find(p => /(app|index|home|main)\.(jsx|tsx|vue|svelte|html)$/i.test(p)) ||
              paths.find(p => /\.(jsx|tsx|vue|svelte)$/i.test(p));
    if (m) return m;
  }
  // 5. If activeFilePath is valid and in the list, keep it
  if (activeFilePath && paths.includes(activeFilePath)) return activeFilePath;

  // 6. Otherwise preferred default
  const defaultFile = paths.find(p => /index\.html$/i.test(p)) ||
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

  const isReviewMode = radioImplReview ? radioImplReview.checked : true;
  const shouldSaveDisk = implChkSaveDisk ? implChkSaveDisk.checked : true;
  const shouldReloadTab = implChkReloadTab ? implChkReloadTab.checked : true;
  const shouldMarkDone = implChkMarkDone ? implChkMarkDone.checked : true;

  btnExecuteImplementation.disabled = true;
  btnExecuteImplementation.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Implementing...';

  if (implProgressTracker) implProgressTracker.classList.remove("hidden");
  if (implFeedbackBanner) implFeedbackBanner.classList.add("hidden");

  // Step 1: Target file verified
  setImplStep(1, "active");
  await new Promise(r => setTimeout(r, 150));
  setImplStep(1, "done");

  // Step 2: Fetch current code or initialize empty if new file
  setImplStep(2, "active");
  let currentCode = "";
  if (!isNewFile) {
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

  const instruction = currentImplTask.suggested_prompt || currentImplTask.title;

  try {
    const res = await fetch(`${SERVER_URL}/api/extension/apply-design`, {
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

      // Switch to designer view
      switchMode("designer");

      // Load file into editor
      activeFilePath = targetFile;
      if (fileSelect) fileSelect.value = targetFile;
      codeEditor.value = data.modified_code;
      isUnsaved = true;
      unsavedIndicator.style.display = "inline-block";

      if (isReviewMode && !shouldSaveDisk) {
        // Review mode without auto-save: Leave in editor for user review
        setImplStep(3, "done");
        setImplStep(4, "done");
        if (implFeedbackBanner) {
          implFeedbackBanner.className = "drop-feedback success";
          implFeedbackBanner.innerHTML = `<i class="fa-solid fa-check"></i> Code generated and loaded into Designer! Review changes and click [Save].`;
          implFeedbackBanner.classList.remove("hidden");
        }
      } else {
        // Step 3: Save to disk
        setImplStep(3, "active");
        if (shouldSaveDisk) {
          await saveCurrentFile();
          setImplStep(3, "done");
        }

        // Step 4: Live reload
        setImplStep(4, "active");
        if (shouldReloadTab) {
          reloadActiveTab();
          await refreshGitStatus();
        }
        setImplStep(4, "done");

        if (implFeedbackBanner) {
          implFeedbackBanner.className = "drop-feedback success";
          implFeedbackBanner.innerHTML = `<i class="fa-solid fa-circle-check"></i> Successfully updated <code>${escapeHtml(targetFile)}</code> on disk and reloaded live app!`;
          implFeedbackBanner.classList.remove("hidden");
        }
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

      logSessionChange("ai_implementation", `Implemented "${currentImplTask.title}" into ${targetFile}`, targetFile);

      setTimeout(() => {
        closeImplementationModal();
      }, 1400);

    } else {
      setImplStep(2, "error");
      if (implFeedbackBanner) {
        implFeedbackBanner.className = "drop-feedback error";
        implFeedbackBanner.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Implementation failed: ${escapeHtml(data.explanation || "API error")}`;
        implFeedbackBanner.classList.remove("hidden");
      }
    }
  } catch (err) {
    setImplStep(2, "error");
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

  // 1. Switch immediately to Designer view
  switchMode("designer");

  // 2. Ensure target file is determined (smart guess or activeFilePath)
  if (!activeFilePath) {
    if (fileSelect && fileSelect.options.length > 0 && fileSelect.value) {
      await openFile(fileSelect.value);
    } else {
      await loadFileTree(activeApp.slug);
      const guessed = guessBestTargetFile(task, appFileList);
      if (guessed) await openFile(guessed);
    }
  }

  if (!activeFilePath) {
    alert("Please select a target file in the Designer before implementing.");
    return;
  }

  const instruction = task.suggested_prompt || task.title;
  designerAiInput.value = instruction;

  let pushBtn = card ? card.querySelector(".btn-push-designer") : null;
  const originalBtnHtml = pushBtn ? pushBtn.innerHTML : null;
  if (pushBtn) {
    pushBtn.disabled = true;
    pushBtn.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Implementing...';
  }

  btnApplyDesignerAi.disabled = true;
  btnApplyDesignerAi.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i> Implementing...';

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

      // Automatically persist modified code to PC disk and reload browser tab
      await saveCurrentFile();

      // Automatically mark task complete in Backlog
      task.completed = true;
      selectedTaskIds.delete(task.id);
      await saveBacklogToServer();
      renderBacklog();
      updateDesignerTaskPicker();
      updateBatchBarState();

      logSessionChange("ai_implementation", `Implemented "${task.title}" to ${activeFilePath}`, activeFilePath);

      if (pushBtn) {
        pushBtn.innerHTML = '<i class="fa-solid fa-check text-emerald-400"></i> Done & Implemented!';
        setTimeout(() => {
          if (originalBtnHtml) pushBtn.innerHTML = originalBtnHtml;
          pushBtn.disabled = false;
        }, 2200);
      }
    } else {
      alert(`Implementation failed: ${data.explanation || "Could not generate code"}`);
      if (pushBtn) {
        pushBtn.disabled = false;
        if (originalBtnHtml) pushBtn.innerHTML = originalBtnHtml;
      }
    }
  } catch (e) {
    alert("Error implementing idea: " + e);
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

  // 1. Switch to designer view
  switchMode("designer");

  // 2. Ensure target file is loaded in editor
  if (!activeFilePath) {
    if (fileSelect && fileSelect.options.length > 0 && fileSelect.value) {
      await openFile(fileSelect.value);
    } else {
      await loadFileTree(activeApp.slug);
    }
  }

  if (!activeFilePath) {
    alert("Please select a target file in the Designer before running batch.");
    isBatchRunning = false;
    updateBatchBarState();
    if (btnRunNextBatch) btnRunNextBatch.disabled = false;
    return;
  }

  if (batchProgressBanner) batchProgressBanner.classList.remove("hidden");
  let completedCount = 0;
  const total = tasksToRun.length;

  for (let i = 0; i < total; i++) {
    const task = tasksToRun[i];
    const pct = Math.round((i / total) * 100);
    if (batchProgressBar) batchProgressBar.style.width = `${pct}%`;
    if (batchProgressPercent) batchProgressPercent.innerText = `${pct}%`;
    if (batchProgressStatus) {
      batchProgressStatus.innerHTML = `<i class="fa-solid fa-spinner animate-spin"></i> [${i + 1}/${total}] Applying "${escapeHtml(task.title)}"...`;
    }

    const instruction = task.suggested_prompt || task.title;
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
        await saveCurrentFile();

        task.completed = true;
        selectedTaskIds.delete(task.id);
        completedCount++;
        logSessionChange("ai_implementation", `[Batch] Implemented "${task.title}" into ${activeFilePath}`, activeFilePath);
      } else {
        console.warn(`[Batch] Failed task "${task.title}":`, data.explanation);
      }
    } catch (err) {
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

// --- Live Designer & Code Editor ---
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

function revertCurrentFile() {
  if (!isUnsaved || confirm("Revert all unsaved changes to this file?")) {
    codeEditor.value = fileOriginalContent;
    isUnsaved = false;
    unsavedIndicator.style.display = "none";
  }
}

function reloadActiveTab() {
  if (typeof chrome !== "undefined" && chrome.tabs) {
    if (activeTabInstance && activeTabInstance.tabId) {
      chrome.tabs.get(activeTabInstance.tabId, (tab) => {
        if (!chrome.runtime.lastError && tab) {
          chrome.tabs.reload(activeTabInstance.tabId);
        } else {
          chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs && tabs[0]) {
              activeTabInstance.tabId = tabs[0].id;
              chrome.tabs.reload(tabs[0].id);
            }
          });
        }
      });
    } else {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs && tabs[0]) {
          activeTabInstance.tabId = tabs[0].id;
          chrome.tabs.reload(tabs[0].id);
        }
      });
    }
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
