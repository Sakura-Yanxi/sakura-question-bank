// In-app "new version available" notice. Notify-only: it links to the download page and never
// touches running code. Loaded after app.js, so `api` / `escapeHtml` / `escapeAttr` are available.
(function () {
  const DISMISS_KEY = "sakura_update_dismissed";

  async function checkForUpdate() {
    const banner = document.getElementById("updateBanner");
    if (!banner) return;
    let info;
    try {
      info = await api("/api/version");
    } catch (error) {
      // The update check must never disrupt the app — stay silent on any failure.
      return;
    }
    if (!info || !info.update_available || !info.url) return;
    // Respect a per-version dismissal so we don't nag after the user has seen it.
    if (localStorage.getItem(DISMISS_KEY) === info.latest) return;

    banner.innerHTML = `
      <span class="update-banner-text">🎉 有新版本 <strong>${escapeHtml(info.latest)}</strong>（当前 ${escapeHtml(info.current || "")}），建议更新。</span>
      <a class="update-banner-link" href="${escapeAttr(info.url)}" target="_blank" rel="noopener">前往下载</a>
      <button class="update-banner-close" type="button" aria-label="关闭">×</button>`;
    banner.classList.remove("hidden");
    const closeBtn = banner.querySelector(".update-banner-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        try {
          localStorage.setItem(DISMISS_KEY, info.latest);
        } catch (error) {
          /* ignore storage failures */
        }
        banner.classList.add("hidden");
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", checkForUpdate);
  } else {
    checkForUpdate();
  }
})();
