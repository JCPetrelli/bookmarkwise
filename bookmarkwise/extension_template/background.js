// Clicking the toolbar icon opens the apply page. Nothing runs on its own.
chrome.action.onClicked.addListener(() => {
  chrome.tabs.create({ url: chrome.runtime.getURL("apply.html") });
});
