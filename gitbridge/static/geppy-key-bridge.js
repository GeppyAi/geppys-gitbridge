/**
 * Geppy's GitBridge Universal Central Key & AI Bridge
 * 
 * Drop-in client library for any application inside Geppy's App Universe.
 * Provides instant access to the central Gemini API key and AI execution.
 * 
 * Usage:
 *   <script src="http://127.0.0.1:8000/static/geppy-key-bridge.js"></script>
 *   <script>
 *     window.addEventListener('geppy:key-ready', (e) => {
 *       console.log('Central Gemini Key Ready:', e.detail.masked_key);
 *     });
 *     // or async:
 *     const apiKey = await window.getGeppyApiKey();
 *   </script>
 */

(function () {
  const GITBRIDGE_HOST = 'http://127.0.0.1:8000';
  window.GEPPY_BRIDGE_URL = GITBRIDGE_HOST;

  let _cachedKey = null;
  let _keyFetchPromise = null;

  /**
   * Fetch the Central Gemini API Key from GitBridge Vault.
   * Returns a Promise resolving to the raw API key string.
   */
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
        if (data.gemini_api_key) {
          _cachedKey = data.gemini_api_key;
          window.GEMINI_API_KEY = _cachedKey;
          window.GOOGLE_API_KEY = _cachedKey;
          window.GEPPY_CENTRAL_KEY = _cachedKey;
          window.GEPPY_ACTIVE_MODEL = data.active_model || 'gemini-2.5-flash';

          // Broadcast custom event
          try {
            window.dispatchEvent(new CustomEvent('geppy:key-ready', { detail: data }));
          } catch (e) {}

          return _cachedKey;
        }
        throw new Error('No API key in GitBridge response');
      })
      .catch(err => {
        console.warn('[GeppyKeyBridge] Could not retrieve Central Gemini Key from GitBridge:', err.message);
        return null;
      })
      .finally(() => {
        _keyFetchPromise = null;
      });

    return _keyFetchPromise;
  };

  /**
   * Test the Central Gemini API connection through GitBridge.
   */
  window.testGeppyGemini = async function () {
    try {
      const res = await fetch(`${GITBRIDGE_HOST}/api/keys/test`, { method: 'POST' });
      return await res.json();
    } catch (err) {
      return { success: false, error: err.message };
    }
  };

  /**
   * Convenience helper to generate content via Gemini through GitBridge.
   */
  window.callGeppyGemini = async function ({ prompt, systemInstruction = '', model = 'gemini-2.5-flash' }) {
    try {
      const res = await fetch(`${GITBRIDGE_HOST}/api/keys/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, system_instruction: systemInstruction, model })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      console.error('[GeppyKeyBridge] Gemini generation error:', err);
      throw err;
    }
  };

  // Auto-initialize on load
  if (typeof window !== 'undefined') {
    window.getGeppyApiKey();
  }
})();
