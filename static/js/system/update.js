// In-app version notice and release status panel.
// Notify-only: the app links to the release page and never rewrites running code.
(function () {
  const DISMISS_KEY = "sakura_update_dismissed";

  async function fetchVersion(force = false) {
    const suffix = force ? "?force=1" : "";
    return api(`/api/version${suffix}`);
  }

  function formatReleaseStatus(info) {
    if (!info?.configured) {
      return {
        label: "未配置仓库",
        text: "在 .env 设置 SAKURA_UPDATE_REPO=用户名/仓库名 后即可检查 GitHub Release。",
        tone: "muted",
      };
    }
    if (!info.checked) {
      return {
        label: "暂未连通",
        text: "当前没有拿到 GitHub 最新 Release，可能是网络、限流、私有仓库或还没有发布 Release。",
        tone: "warning",
      };
    }
    if (info.update_available) {
      return {
        label: "发现新版本",
        text: `最新版本 ${info.latest} 已发布，当前运行版本是 ${info.current}。`,
        tone: "success",
      };
    }
    return {
      label: "已经是最新版",
      text: `当前版本 ${info.current} 与 GitHub 最新 Release 一致。`,
      tone: "ok",
    };
  }

  function renderVersionPanel(info, message = "") {
    const card = document.getElementById("versionStatusCard");
    if (!card) return;

    const status = formatReleaseStatus(info);
    const releaseHref = info?.url || info?.releases_url || "";
    const repoText = info?.repo || "未配置";
    const notes = info?.notes ? String(info.notes).trim().slice(0, 260) : "";
    const checkedText = info?.published_at ? `最新发布时间：${info.published_at}` : "检查缓存约 6 小时，可手动刷新。";

    card.innerHTML = `
      <div class="version-status-head">
        <span class="version-status-badge ${escapeAttr(status.tone)}">${escapeHtml(status.label)}</span>
        <span class="version-status-repo">${escapeHtml(repoText)}</span>
      </div>
      <div class="version-status-grid">
        <div><span>当前版本</span><strong>${escapeHtml(info?.current || "-")}</strong></div>
        <div><span>最新 Release</span><strong>${escapeHtml(info?.latest || "-")}</strong></div>
        <div><span>更新方式</span><strong>update.bat / update.sh</strong></div>
      </div>
      <p>${escapeHtml(status.text)}</p>
      ${notes ? `<p class="version-release-notes">${escapeHtml(notes)}</p>` : ""}
      <div class="version-actions">
        <button id="checkVersionNow" class="ghost" type="button"><i data-lucide="refresh-cw"></i>重新检查</button>
        ${releaseHref ? `<a class="ghost version-link" href="${escapeAttr(releaseHref)}" target="_blank" rel="noopener"><i data-lucide="external-link"></i>打开 Release</a>` : ""}
        <span>${escapeHtml(message || checkedText)}</span>
      </div>`;

    const button = document.getElementById("checkVersionNow");
    if (button) {
      button.addEventListener("click", async () => {
        button.disabled = true;
        button.innerHTML = `<i data-lucide="loader-2"></i>检查中`;
        if (window.lucide) window.lucide.createIcons();
        try {
          const fresh = await fetchVersion(true);
          renderVersionPanel(fresh, "已手动刷新版本状态。");
          showUpdateBanner(fresh);
        } catch (error) {
          renderVersionPanel(info, `检查失败：${error.message || error}`);
        }
      });
    }
    if (window.lucide) window.lucide.createIcons();
  }

  function showUpdateBanner(info) {
    const banner = document.getElementById("updateBanner");
    if (!banner || !info || !info.update_available || !info.url) return;
    if (localStorage.getItem(DISMISS_KEY) === info.latest) return;

    banner.innerHTML = `
      <span class="update-banner-text">发现新版本 <strong>${escapeHtml(info.latest)}</strong>，当前为 ${escapeHtml(info.current || "")}，建议更新。</span>
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

  async function loadVersionStatus() {
    let info;
    try {
      info = await fetchVersion(false);
    } catch (error) {
      renderVersionPanel(
        { configured: true, checked: false, current: "-", latest: "-", repo: "" },
        `检查失败：${error.message || error}`,
      );
      return;
    }
    showUpdateBanner(info);
    renderVersionPanel(info);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadVersionStatus);
  } else {
    loadVersionStatus();
  }
})();
