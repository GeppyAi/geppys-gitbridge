/**
 * Geppy's GitBridge Universal Central Key, Update & GeppyBug Reporting Bridge
 *
 * Drop-in client library & floating HUD widget for any application inside Geppy's App Universe.
 * Provides:
 *   1. Instant access to the central Gemini API key & AI generation (`window.getGeppyApiKey()`, `window.callGeppyGemini()`).
 *   2. Automatic runtime & console error capture (`window.GEPPY_CAPTURED_ERRORS`).
 *   3. Universal floating dock with the official `GeppyBug.png` "Report Bug" badge and "Update App" button.
 *   4. Interactive Bug Reporting & Update modals connected directly to GitBridge, Captain Geppy, and Antigravity.
 *
 * Usage:
 *   <script src="http://127.0.0.1:8000/static/geppy-key-bridge.js" defer></script>
 */

(function () {
  if (window.__GEPPY_BRIDGE_INITIALIZED__) return;
  window.__GEPPY_BRIDGE_INITIALIZED__ = true;

  const GITBRIDGE_HOST = 'http://127.0.0.1:8000';
  window.GEPPY_BRIDGE_URL = GITBRIDGE_HOST;
  const BUG_ICON_URL = `${GITBRIDGE_HOST}/static/assets/geppy_bug.png`;
  const GITBRIDGE_ICON_URL = `${GITBRIDGE_HOST}/static/assets/gitbridge_icon_64.png`;

  let _cachedKey = null;
  let _keyFetchPromise = null;
  let _detectedApp = null;
  const _capturedErrors = [];
  window.GEPPY_CAPTURED_ERRORS = _capturedErrors;

  // --- 1. Automatic Runtime & Console Error Capture ---
  function recordCapturedError(msg, source) {
    if (!msg) return;
    const clean = `[${new Date().toLocaleTimeString()}] (${source || 'runtime'}) ${String(msg).slice(0, 350)}`;
    if (!_capturedErrors.includes(clean)) {
      _capturedErrors.unshift(clean);
      if (_capturedErrors.length > 25) _capturedErrors.pop();
      updateBugBadgeCount();
    }
  }

  window.addEventListener('error', (event) => {
    const errText = event.message || (event.error && event.error.message) || '';
    if (errText) {
      recordCapturedError(`${errText} @ ${event.filename || ''}:${event.lineno || 0}`, 'window.onerror');
    }
  });

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason ? (event.reason.message || String(event.reason)) : 'Unhandled Promise Rejection';
    recordCapturedError(reason, 'unhandledrejection');
  });

  const _origConsoleError = console.error;
  console.error = function (...args) {
    try {
      const joined = args.map(a => (typeof a === 'object' ? (a && a.message ? a.message : JSON.stringify(a)) : String(a))).join(' ');
      if (joined && !joined.includes('[GeppyKeyBridge]')) {
        recordCapturedError(joined, 'console.error');
      }
    } catch (e) {}
    return _origConsoleError.apply(console, args);
  };

  // --- 2. Central Gemini API Key & AI Helpers ---
  window.getGeppyApiKey = function (forceRefresh = false) {
    if (_cachedKey && !forceRefresh) {
      return Promise.resolve(_cachedKey);
    }
    if (_keyFetchPromise && !forceRefresh) {
      return _keyFetchPromise;
    }

    _keyFetchPromise = fetch(`${GITBRIDGE_HOST}/api/keys/gemini`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' }
    })
      .then(res => {
        if (!res.ok) throw new Error(`GitBridge returned HTTP ${res.status}`);
        return res.json();
      })
      .then(data => {
        if (data && data.gemini_api_key) {
          _cachedKey = data.gemini_api_key;
          window.GEMINI_API_KEY = _cachedKey;
          window.GOOGLE_API_KEY = _cachedKey;
          window.GEPPY_CENTRAL_KEY = _cachedKey;
          window.GEPPY_ACTIVE_MODEL = data.active_model || 'gemini-2.5-flash';

          try {
            window.dispatchEvent(new CustomEvent('geppy:key-ready', { detail: data }));
          } catch (e) {}

          return _cachedKey;
        }
        throw new Error('No API key in GitBridge response');
      })
      .catch(err => {
        console.warn('[GeppyKeyBridge] Could not retrieve Central Gemini Key from GitBridge:', err ? err.message : err);
        return null;
      })
      .finally(() => {
        _keyFetchPromise = null;
      });

    return _keyFetchPromise;
  };

  window.testGeppyGemini = async function () {
    try {
      const res = await fetch(`${GITBRIDGE_HOST}/api/keys/test`, { method: 'POST' });
      return await res.json();
    } catch (err) {
      return { success: false, error: err ? err.message : 'Network error' };
    }
  };

  window.callGeppyGemini = async function ({ prompt, systemInstruction = '', model = 'gemini-2.5-flash' }) {
    try {
      const res = await fetch(`${GITBRIDGE_HOST}/api/keys/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, system_instruction: systemInstruction, model })
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      console.error('[GeppyKeyBridge] Gemini generation error:', err ? err.message : err);
      throw err;
    }
  };

  // --- 3. Auto-Detect Current App in GitBridge ---
  async function detectCurrentGeppyApp() {
    if (_detectedApp) return _detectedApp;
    try {
      const pageUrl = window.location.href;
      const res = await fetch(`${GITBRIDGE_HOST}/api/extension/detect-app?url=${encodeURIComponent(pageUrl)}`);
      if (res.ok) {
        const data = await res.json();
        if (data && data.app) {
          _detectedApp = data.app;
          return _detectedApp;
        }
      }
    } catch (e) {}
    return {
      slug: window.currentAppSlug || '',
      name: document.title || window.location.hostname || 'Current App'
    };
  }

  // --- 4. Programmatic Bug Report & Update Functions ---
  window.reportGeppyBug = async function (options = {}) {
    const appInfo = await detectCurrentGeppyApp();
    const payload = {
      app_slug: options.app_slug || options.slug || (window.currentAppSlug || appInfo.slug || ''),
      app_name: options.app_name || appInfo.name || document.title,
      url: window.location.href,
      title: options.title || '',
      description: options.description || '',
      severity: options.severity || 'high',
      file_path: options.file_path || '',
      console_errors: options.console_errors || _capturedErrors.slice(0, 12),
      user_agent: navigator.userAgent,
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      auto_fix: Boolean(options.auto_fix),
      log_to_health_card: options.log_to_health_card !== false,
      create_github_issue: Boolean(options.create_github_issue)
    };

    const res = await fetch(`${GITBRIDGE_HOST}/api/bugs/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    return await res.json();
  };

  window.triggerGeppyAppUpdate = async function (options = {}) {
    const appInfo = await detectCurrentGeppyApp();
    const slug = options.app_slug || options.slug || (window.currentAppSlug || appInfo.slug || '');
    const payload = {
      app_slug: slug,
      url: window.location.href,
      mode: options.mode || 'sync_all',
      instruction: options.instruction || '',
      commit_message: options.commit_message || ''
    };
    const endpoint = slug ? `${GITBRIDGE_HOST}/api/apps/${encodeURIComponent(slug)}/update` : `${GITBRIDGE_HOST}/api/universal/update`;
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    return await res.json();
  };

  function updateBugBadgeCount() {
    const badge = document.getElementById('geppy-universal-bug-count');
    if (!badge) return;
    if (_capturedErrors.length > 0) {
      badge.textContent = String(_capturedErrors.length);
      badge.style.display = 'inline-flex';
    } else {
      badge.style.display = 'none';
    }
  }

  // --- 5. Universal Floating Dock & Modals (GeppyBug.png + Update Button) ---
  function injectUniversalBugAndUpdateWidget() {
    // Do not inject inside Chrome extension sidepanel (sidepanel has its own header buttons)
    if (window.location.protocol === 'chrome-extension:') return;
    if (document.getElementById('geppy-universal-bridge-dock')) return;

    const styleEl = document.createElement('style');
    styleEl.id = 'geppy-universal-bridge-styles';
    styleEl.textContent = `
      #geppy-universal-bridge-dock {
        position: fixed;
        bottom: 16px;
        right: 16px;
        z-index: 2147483000;
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 10px;
        border-radius: 999px;
        background: rgba(9, 13, 22, 0.92);
        border: 1.5px solid rgba(245, 158, 11, 0.45);
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.65), 0 0 16px rgba(245, 158, 11, 0.18);
        backdrop-filter: blur(12px);
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
        transition: transform 0.2s ease, border-color 0.2s ease;
        user-select: none;
      }
      #geppy-universal-bridge-dock:hover {
        border-color: rgba(245, 158, 11, 0.85);
      }
      #geppy-universal-bridge-dock.minimized .geppy-dock-expandable {
        display: none !important;
      }
      .geppy-dock-bug-btn {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        background: linear-gradient(135deg, rgba(234, 88, 12, 0.28), rgba(154, 52, 18, 0.42));
        border: 1px solid rgba(251, 146, 60, 0.65);
        color: #ffedd5;
        padding: 4px 11px 4px 5px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 800;
        letter-spacing: 0.02em;
        cursor: pointer;
        transition: all 0.18s ease;
        position: relative;
      }
      .geppy-dock-bug-btn:hover {
        background: linear-gradient(135deg, rgba(249, 115, 22, 0.48), rgba(194, 65, 12, 0.65));
        transform: translateY(-1px) scale(1.03);
        box-shadow: 0 4px 14px rgba(249, 115, 22, 0.4);
      }
      .geppy-dock-bug-btn img {
        width: 32px;
        height: 32px;
        object-fit: contain;
        filter: drop-shadow(0 2px 6px rgba(0,0,0,0.6));
        transition: transform 0.2s ease;
      }
      .geppy-dock-bug-btn:hover img {
        transform: rotate(-6deg) scale(1.1);
      }
      #geppy-universal-bug-count {
        display: none;
        align-items: center;
        justify-content: center;
        min-width: 18px;
        height: 18px;
        padding: 0 5px;
        border-radius: 999px;
        background: #ef4444;
        color: #ffffff;
        font-size: 10px;
        font-weight: 900;
        border: 1.5px solid #090d16;
        box-shadow: 0 2px 6px rgba(239, 68, 68, 0.6);
      }
      .geppy-dock-update-btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: linear-gradient(135deg, rgba(79, 70, 229, 0.35), rgba(6, 182, 212, 0.35));
        border: 1px solid rgba(56, 189, 248, 0.6);
        color: #e0f2fe;
        padding: 6px 12px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 800;
        letter-spacing: 0.02em;
        cursor: pointer;
        transition: all 0.18s ease;
      }
      .geppy-dock-update-btn:hover {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.6), rgba(14, 165, 233, 0.6));
        transform: translateY(-1px) scale(1.03);
        box-shadow: 0 4px 14px rgba(56, 189, 248, 0.35);
      }
      .geppy-dock-collapse-btn {
        background: transparent;
        border: none;
        color: #94a3b8;
        cursor: pointer;
        padding: 4px;
        font-size: 11px;
        line-height: 1;
        border-radius: 999px;
      }
      .geppy-dock-collapse-btn:hover {
        color: #f8fafc;
        background: rgba(255,255,255,0.08);
      }
      #geppy-universal-modal-backdrop {
        position: fixed;
        inset: 0;
        z-index: 2147483600;
        background: rgba(2, 6, 23, 0.78);
        backdrop-filter: blur(6px);
        display: none;
        align-items: center;
        justify-content: center;
        padding: 16px;
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
      }
      #geppy-universal-modal-backdrop.open {
        display: flex;
      }
      .geppy-universal-modal-card {
        width: 100%;
        max-width: 540px;
        background: #0f172a;
        border: 1.5px solid rgba(245, 158, 11, 0.5);
        border-radius: 20px;
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.85);
        color: #f8fafc;
        overflow: hidden;
        animation: geppyModalPop 0.18s ease-out;
      }
      @keyframes geppyModalPop {
        from { opacity: 0; transform: scale(0.95) translateY(8px); }
        to { opacity: 1; transform: scale(1) translateY(0); }
      }
      .geppy-modal-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 14px 18px;
        background: linear-gradient(90deg, rgba(15, 23, 42, 0.98), rgba(30, 27, 75, 0.85));
        border-bottom: 1px solid rgba(51, 65, 85, 0.8);
      }
      .geppy-modal-body {
        padding: 18px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        max-height: 78vh;
        overflow-y: auto;
      }
      .geppy-modal-input, .geppy-modal-textarea, .geppy-modal-select {
        width: 100%;
        box-sizing: border-box;
        background: #020617;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 9px 12px;
        color: #f8fafc;
        font-size: 13px;
        font-family: inherit;
      }
      .geppy-modal-input:focus, .geppy-modal-textarea:focus, .geppy-modal-select:focus {
        outline: none;
        border-color: #f59e0b;
      }
      .geppy-modal-btn-primary {
        background: linear-gradient(135deg, #ea580c, #d97706);
        color: #ffffff;
        border: none;
        padding: 10px 16px;
        border-radius: 10px;
        font-weight: 800;
        font-size: 13px;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        transition: opacity 0.15s ease;
      }
      .geppy-modal-btn-primary:hover {
        opacity: 0.92;
      }
      .geppy-modal-btn-secondary {
        background: #1e293b;
        color: #e2e8f0;
        border: 1px solid #475569;
        padding: 9px 14px;
        border-radius: 10px;
        font-weight: 700;
        font-size: 12px;
        cursor: pointer;
      }
      .geppy-modal-btn-secondary:hover {
        background: #334155;
      }
    `;
    document.head.appendChild(styleEl);

    const dock = document.createElement('div');
    dock.id = 'geppy-universal-bridge-dock';
    dock.innerHTML = `
      <button type="button" class="geppy-dock-bug-btn" id="geppy-btn-open-bug-modal" title="Report a Bug to GitBridge, Captain Geppy & Antigravity">
        <img src="${BUG_ICON_URL}" alt="Report Bug" />
        <span class="geppy-dock-expandable">Report Bug</span>
        <span id="geppy-universal-bug-count">0</span>
      </button>
      <button type="button" class="geppy-dock-update-btn geppy-dock-expandable" id="geppy-btn-open-update-modal" title="Update App — Sync Central Key, Pull/Push GitHub, or Run AI Update">
        <span>🔄 Update</span>
      </button>
      <button type="button" class="geppy-dock-collapse-btn" id="geppy-btn-toggle-dock-min" title="Minimize / Expand Geppy Bridge Dock">
        ▾
      </button>
    `;
    document.body.appendChild(dock);

    const backdrop = document.createElement('div');
    backdrop.id = 'geppy-universal-modal-backdrop';
    backdrop.innerHTML = `<div class="geppy-universal-modal-card" id="geppy-universal-modal-content"></div>`;
    document.body.appendChild(backdrop);

    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) closeGeppyUniversalModal();
    });

    document.getElementById('geppy-btn-open-bug-modal').addEventListener('click', () => {
      openGeppyBugModal();
    });

    document.getElementById('geppy-btn-open-update-modal').addEventListener('click', () => {
      openGeppyUpdateModal();
    });

    const minBtn = document.getElementById('geppy-btn-toggle-dock-min');
    minBtn.addEventListener('click', () => {
      dock.classList.toggle('minimized');
      minBtn.textContent = dock.classList.contains('minimized') ? '▴' : '▾';
    });

    updateBugBadgeCount();
  }

  window.closeGeppyUniversalModal = function () {
    const backdrop = document.getElementById('geppy-universal-modal-backdrop');
    if (backdrop) backdrop.classList.remove('open');
  };

  window.openGeppyBugModal = async function (prefill = {}) {
    let backdrop = document.getElementById('geppy-universal-modal-backdrop');
    if (!backdrop) {
      injectUniversalBugAndUpdateWidget();
      backdrop = document.getElementById('geppy-universal-modal-backdrop');
    }
    const card = document.getElementById('geppy-universal-modal-content');
    const appInfo = await detectCurrentGeppyApp();
    const activeSlug = prefill.app_slug || prefill.slug || window.currentAppSlug || appInfo.slug || 'geppys-gitbridge';
    const activeName = prefill.app_name || appInfo.name || document.title || activeSlug;
    const defaultErrors = (prefill.console_errors || _capturedErrors).join('\n');

    card.innerHTML = `
      <div class="geppy-modal-header">
        <div style="display:flex;align-items:center;gap:10px;">
          <img src="${BUG_ICON_URL}" alt="GeppyBug" style="width:42px;height:42px;object-fit:contain;filter:drop-shadow(0 2px 8px rgba(249,115,22,0.5));" />
          <div>
            <div style="font-size:15px;font-weight:800;color:#fff;display:flex;align-items:center;gap:6px;">
              <span>Report Bug to GitBridge</span>
              <span style="font-size:10px;padding:2px 7px;border-radius:999px;background:rgba(249,115,22,0.2);color:#fdba74;border:1px solid rgba(249,115,22,0.4);">${activeName}</span>
            </div>
            <div style="font-size:11px;color:#94a3b8;">Logs to App Backlog, Health Card, Captain Geppy &amp; Antigravity Auto-Fix</div>
          </div>
        </div>
        <button type="button" onclick="window.closeGeppyUniversalModal()" style="background:transparent;border:none;color:#94a3b8;font-size:18px;cursor:pointer;">✕</button>
      </div>
      <div class="geppy-modal-body">
        <div style="display:grid;grid-template-columns:1fr 140px;gap:10px;">
          <div>
            <label style="font-size:11px;font-weight:700;color:#cbd5e1;display:block;margin-bottom:4px;">Bug Title / Summary *</label>
            <input type="text" id="geppy-bug-title-input" class="geppy-modal-input" placeholder="e.g. Clicking Save button freezes or throws undefined error" value="${(prefill.title || '').replace(/"/g, '&quot;')}" />
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;color:#cbd5e1;display:block;margin-bottom:4px;">Severity</label>
            <select id="geppy-bug-severity-select" class="geppy-modal-select">
              <option value="critical">🚨 Critical</option>
              <option value="high" selected>🔥 High</option>
              <option value="medium">⚠️ Medium</option>
              <option value="low">💡 Low / UI Polish</option>
            </select>
          </div>
        </div>

        <div>
          <label style="font-size:11px;font-weight:700;color:#cbd5e1;display:block;margin-bottom:4px;">What happened &amp; steps to reproduce</label>
          <textarea id="geppy-bug-desc-input" class="geppy-modal-textarea" rows="3" placeholder="Describe the bug, expected behavior, or component affected...">${prefill.description || ''}</textarea>
        </div>

        <div>
          <label style="font-size:11px;font-weight:700;color:#fca5a5;display:flex;justify-content:space-between;margin-bottom:4px;">
            <span>Captured Console / Runtime Errors (${_capturedErrors.length} auto-detected)</span>
            <span style="font-weight:400;color:#94a3b8;">Editable</span>
          </label>
          <textarea id="geppy-bug-errors-input" class="geppy-modal-textarea" rows="2" style="font-family:monospace;font-size:11px;color:#fecaca;" placeholder="Paste any console stack trace or error message here...">${defaultErrors}</textarea>
        </div>

        <div style="display:flex;flex-wrap:wrap;gap:12px;padding:8px 10px;background:#020617;border-radius:10px;border:1px solid #1e293b;font-size:11.5px;color:#cbd5e1;">
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
            <input type="checkbox" id="geppy-bug-chk-autofix" checked style="accent-color:#f97316;" />
            <span>⚡ <strong>Send to Antigravity / AI to Auto-Patch Code Now</strong></span>
          </label>
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
            <input type="checkbox" id="geppy-bug-chk-health" checked style="accent-color:#10b981;" />
            <span>📋 Log to Health Card &amp; BUGS.md</span>
          </label>
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
            <input type="checkbox" id="geppy-bug-chk-github" style="accent-color:#6366f1;" />
            <span>🐙 Create GitHub Issue</span>
          </label>
        </div>

        <div id="geppy-bug-modal-feedback" style="display:none;padding:10px 12px;border-radius:10px;font-size:12px;line-height:1.4;"></div>

        <div style="display:flex;align-items:center;justify-content:flex-end;gap:8px;padding-top:4px;">
          <button type="button" class="geppy-modal-btn-secondary" onclick="window.closeGeppyUniversalModal()">Cancel</button>
          <button type="button" class="geppy-modal-btn-primary" id="geppy-btn-submit-bug-report">
            <img src="${BUG_ICON_URL}" alt="" style="width:20px;height:20px;object-fit:contain;" />
            <span>Submit Bug Report</span>
          </button>
        </div>
      </div>
    `;

    backdrop.classList.add('open');

    const submitBtn = document.getElementById('geppy-btn-submit-bug-report');
    submitBtn.addEventListener('click', async () => {
      const title = document.getElementById('geppy-bug-title-input').value.trim();
      const desc = document.getElementById('geppy-bug-desc-input').value.trim();
      const severity = document.getElementById('geppy-bug-severity-select').value;
      const errLines = document.getElementById('geppy-bug-errors-input').value.split('\n').map(s => s.trim()).filter(Boolean);
      const autoFix = document.getElementById('geppy-bug-chk-autofix').checked;
      const logHealth = document.getElementById('geppy-bug-chk-health').checked;
      const ghIssue = document.getElementById('geppy-bug-chk-github').checked;
      const fb = document.getElementById('geppy-bug-modal-feedback');

      if (!title && !desc && errLines.length === 0) {
        fb.style.display = 'block';
        fb.style.background = 'rgba(127, 29, 29, 0.5)';
        fb.style.border = '1px solid #ef4444';
        fb.style.color = '#fecaca';
        fb.textContent = 'Please enter a bug title or description.';
        return;
      }

      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span>⏳ Diagnosing${autoFix ? ' & Patching via Antigravity...' : '...'}</span>`;
      fb.style.display = 'block';
      fb.style.background = 'rgba(30, 41, 59, 0.8)';
      fb.style.border = '1px solid #475569';
      fb.style.color = '#e2e8f0';
      fb.textContent = autoFix
        ? 'Logging bug to GitBridge and invoking Captain Geppy / Antigravity to patch the code...'
        : 'Logging bug to GitBridge Backlog, Health Card, and Watchdog...';

      try {
        const res = await window.reportGeppyBug({
          app_slug: activeSlug,
          app_name: activeName,
          title: title || desc.slice(0, 60),
          description: desc || title,
          severity,
          console_errors: errLines,
          auto_fix: autoFix,
          log_to_health_card: logHealth,
          create_github_issue: ghIssue
        });

        if (res && res.success) {
          fb.style.background = 'rgba(6, 78, 59, 0.65)';
          fb.style.border = '1px solid #10b981';
          fb.style.color = '#d1fae5';
          const fixNote = res.bug && res.bug.auto_fix_result && res.bug.auto_fix_result.applied
            ? `<div style="margin-top:6px;font-weight:700;color:#6ee7b7;">✅ Auto-Fix Applied to <code>${res.bug.auto_fix_result.file_path}</code>: ${res.bug.auto_fix_result.explanation}</div>`
            : `<div style="margin-top:6px;color:#fcd34d;">📋 Diagnosis: ${res.bug ? res.bug.diagnosis_summary : 'Queued in Backlog'}</div>`;
          fb.innerHTML = `<div><strong>${res.message}</strong></div>${fixNote}`;
          submitBtn.innerHTML = `<span>✅ Reported!</span>`;
          if (typeof window.fetchCatalog === 'function') window.fetchCatalog();
        } else {
          throw new Error((res && (res.detail || res.message)) || 'Failed to submit bug report');
        }
      } catch (err) {
        fb.style.background = 'rgba(127, 29, 29, 0.6)';
        fb.style.border = '1px solid #ef4444';
        fb.style.color = '#fecaca';
        fb.textContent = 'Error: ' + (err ? err.message : String(err));
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<img src="${BUG_ICON_URL}" alt="" style="width:20px;height:20px;object-fit:contain;" /><span>Retry Submit</span>`;
      }
    });
  };

  window.openGeppyUpdateModal = async function (prefill = {}) {
    let backdrop = document.getElementById('geppy-universal-modal-backdrop');
    if (!backdrop) {
      injectUniversalBugAndUpdateWidget();
      backdrop = document.getElementById('geppy-universal-modal-backdrop');
    }
    const card = document.getElementById('geppy-universal-modal-content');
    const appInfo = await detectCurrentGeppyApp();
    const activeSlug = prefill.app_slug || prefill.slug || window.currentAppSlug || appInfo.slug || 'geppys-gitbridge';
    const activeName = prefill.app_name || appInfo.name || document.title || activeSlug;

    card.innerHTML = `
      <div class="geppy-modal-header">
        <div style="display:flex;align-items:center;gap:10px;">
          <img src="${GITBRIDGE_ICON_URL}" onerror="this.src='${BUG_ICON_URL}'" alt="GitBridge Update" style="width:38px;height:38px;object-fit:contain;" />
          <div>
            <div style="font-size:15px;font-weight:800;color:#fff;display:flex;align-items:center;gap:6px;">
              <span>🔄 Update App via GitBridge</span>
              <span style="font-size:10px;padding:2px 7px;border-radius:999px;background:rgba(56,189,248,0.2);color:#7dd3fc;border:1px solid rgba(56,189,248,0.4);">${activeName}</span>
            </div>
            <div style="font-size:11px;color:#94a3b8;">Sync Central Key, Pull/Push GitHub, or Apply an AI Feature Update</div>
          </div>
        </div>
        <button type="button" onclick="window.closeGeppyUniversalModal()" style="background:transparent;border:none;color:#94a3b8;font-size:18px;cursor:pointer;">✕</button>
      </div>
      <div class="geppy-modal-body">
        <div>
          <label style="font-size:11px;font-weight:700;color:#cbd5e1;display:block;margin-bottom:4px;">Update Action Mode</label>
          <select id="geppy-update-mode-select" class="geppy-modal-select">
            <option value="sync_all" selected>⚡ Full Sync &amp; Update (Sync Central Gemini Key + Pull Latest + Inject Bridge)</option>
            <option value="ai_update">🤖 AI Code Update (Instruct Captain Geppy / Antigravity to update this app)</option>
            <option value="push">🐙 Commit &amp; Push Local Updates to GitHub</option>
            <option value="pull">⬇️ Pull Latest Changes from GitHub</option>
          </select>
        </div>

        <div id="geppy-update-ai-box">
          <label style="font-size:11px;font-weight:700;color:#cbd5e1;display:block;margin-bottom:4px;">Optional AI Update Instruction or Git Commit Message</label>
          <textarea id="geppy-update-instruction-input" class="geppy-modal-textarea" rows="3" placeholder="Optional: Describe any feature or UI update you want Captain Geppy to apply right now, or enter a commit message when pushing to GitHub...">${prefill.instruction || ''}</textarea>
        </div>

        <div id="geppy-update-modal-feedback" style="display:none;padding:10px 12px;border-radius:10px;font-size:12px;line-height:1.4;"></div>

        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding-top:4px;">
          <button type="button" class="geppy-modal-btn-secondary" onclick="window.location.reload()" title="Reload current page with fresh assets">↻ Reload Page</button>
          <div style="display:flex;align-items:center;gap:8px;">
            <button type="button" class="geppy-modal-btn-secondary" onclick="window.closeGeppyUniversalModal()">Close</button>
            <button type="button" class="geppy-modal-btn-primary" id="geppy-btn-run-update" style="background:linear-gradient(135deg,#4f46e5,#0891b2);">
              <span>🔄 Run Update Now</span>
            </button>
          </div>
        </div>
      </div>
    `;

    backdrop.classList.add('open');

    const runBtn = document.getElementById('geppy-btn-run-update');
    runBtn.addEventListener('click', async () => {
      const mode = document.getElementById('geppy-update-mode-select').value;
      const textVal = document.getElementById('geppy-update-instruction-input').value.trim();
      const fb = document.getElementById('geppy-update-modal-feedback');

      runBtn.disabled = true;
      runBtn.innerHTML = `<span>⏳ Updating ${activeName}...</span>`;
      fb.style.display = 'block';
      fb.style.background = 'rgba(30, 41, 59, 0.8)';
      fb.style.border = '1px solid #475569';
      fb.style.color = '#e2e8f0';
      fb.textContent = 'Running GitBridge update pipeline...';

      try {
        const res = await window.triggerGeppyAppUpdate({
          app_slug: activeSlug,
          mode,
          instruction: mode === 'ai_update' ? textVal : '',
          commit_message: mode === 'push' ? textVal : ''
        });

        if (res && res.success) {
          fb.style.background = 'rgba(6, 78, 59, 0.65)';
          fb.style.border = '1px solid #10b981';
          fb.style.color = '#d1fae5';
          const stepsHtml = (res.steps_completed || []).map(s => `<li>✅ ${s}</li>`).join('');
          fb.innerHTML = `<div><strong>${res.message}</strong></div>${stepsHtml ? `<ul style="margin:6px 0 0 16px;padding:0;">${stepsHtml}</ul>` : ''}`;
          runBtn.innerHTML = `<span>✅ Updated!</span>`;
          runBtn.disabled = false;
          if (typeof window.fetchCatalog === 'function') window.fetchCatalog();
        } else {
          throw new Error((res && (res.detail || res.message)) || 'Update failed');
        }
      } catch (err) {
        fb.style.background = 'rgba(127, 29, 29, 0.6)';
        fb.style.border = '1px solid #ef4444';
        fb.style.color = '#fecaca';
        fb.textContent = 'Update error: ' + (err ? err.message : String(err));
        runBtn.disabled = false;
        runBtn.innerHTML = `<span>🔄 Retry Update</span>`;
      }
    });
  };

  // Auto-initialize on load
  if (typeof window !== 'undefined') {
    window.getGeppyApiKey();
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', injectUniversalBugAndUpdateWidget);
    } else {
      injectUniversalBugAndUpdateWidget();
    }
  }
})();