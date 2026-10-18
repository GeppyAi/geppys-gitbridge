// Geppy's GitBridge - Background Service Worker
chrome.runtime.onInstalled.addListener(() => {
  if (chrome.sidePanel && chrome.sidePanel.setPanelBehavior) {
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
      .catch((error) => console.error("Error setting side panel behavior:", error));
  }
});

// Broadcast active tab updates to the side panel for instant app auto-detection
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    if (tab && tab.url) {
      chrome.runtime.sendMessage({ type: "TAB_CHANGED", url: tab.url, tabId: tab.id }).catch(() => {});
    }
  } catch (e) {
    // Ignore errors for internal chrome:// tabs
  }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url) {
    chrome.runtime.sendMessage({ type: "TAB_CHANGED", url: changeInfo.url, tabId: tabId }).catch(() => {});
  }
});