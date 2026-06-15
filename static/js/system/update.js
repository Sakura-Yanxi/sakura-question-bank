// In-app version notice, release status panel, and guarded one-click updater.
(function () {
  const DISMISS_KEY = "sakura_update_dismissed";

  async function fetchVersion(force = false) {
    const suffix = force ? "?force=1" : "";
    return api(`/api/version${suffix}`);
  }

  function canAutoUpdate(info) {
    return Boolean(info?.auto_update?.supported);
  }

  function updateModeText(info) {
    if (canAutoUpdate(info)) {
      return info.auto_update.mode === "git" ? "一键更新（Git）" : "一键更新（Release zip）";
    }
    return info?.auto_update?.label || "手动下载覆盖";
  }

  function formatReleaseStatus(info) {
    if (info?.restart_scheduled) {
      return {
        label: "正在重启",
        text: "更新文件已写入，服务器正在自动重启 Sakura 服务；请等待几秒后刷新页面。",
        tone: "warning",
      };
    }
    if (info?.restart_required) {
      return {
        label: "等待重启",
        text: "更新文件已写入本地，关闭并重新启动 Sakura 服务后，新版本才会正式生效。",
        tone: "warning",
      };
    }
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
        <div><span>更新方式</span><strong>${escapeHtml(updateModeText(info))}</strong></div>
      </div>
      <p>${escapeHtml(status.text)}</p>
      ${info?.auto_update?.description ? `<p>${escapeHtml(info.auto_update.description)}</p>` : ""}
      ${notes ? `<p class="version-release-notes">${escapeHtml(notes)}</p>` : ""}
      <div class="version-actions">
        <button id="checkVersionNow" class="ghost" type="button"><i data-lucide="refresh-cw"></i>重新检查</button>
        ${info?.update_available && canAutoUpdate(info) ? `<button id="applyVersionUpdate" type="button"><i data-lucide="download"></i>一键更新</button>` : ""}
        ${releaseHref ? `<a class="ghost version-link" href="${escapeAttr(releaseHref)}" target="_blank" rel="noopener"><i data-lucide="external-link"></i>手动下载</a>` : ""}
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
    const updateButton = document.getElementById("applyVersionUpdate");
    if (updateButton) {
      updateButton.addEventListener("click", () => applyUpdate(info, updateButton));
    }
    if (window.lucide) window.lucide.createIcons();
  }

  async function applyUpdate(info, button) {
    const ok = window.confirm(
      "将自动更新代码文件，保留 data/、.env 和 .venv。Release zip 模式会先备份旧代码，更新完成后需要重启 Sakura 服务才会生效。现在继续吗？",
    );
    if (!ok) return;
    const original = button?.innerHTML;
    if (button) {
      button.disabled = true;
      button.innerHTML = `<i data-lucide="loader-2"></i>更新中`;
      if (window.lucide) window.lucide.createIcons();
    }
    try {
      const result = await api("/api/version/update", { method: "POST", body: JSON.stringify({}) });
      const stepText = (result.steps || [])
        .map((step) => `${step.ok ? "OK" : "FAIL"} ${step.name}`)
        .join("；");
      const nextInfo = {
        ...info,
        auto_update: result.auto_update || info.auto_update,
        latest: result.info?.latest || info.latest,
        restart_scheduled: Boolean(result.restart_scheduled),
        restart_required: Boolean(result.restart_required),
        update_available: result.restart_required ? false : info.update_available,
      };
      renderVersionPanel(nextInfo, `${result.message || "更新完成。"}${stepText ? ` ${stepText}` : ""}`);
      const banner = document.getElementById("updateBanner");
      if (banner) {
        const doneText = result.restart_scheduled
          ? "更新已完成，服务器正在自动重启；请等待几秒后刷新页面。"
          : "更新已完成，请关闭并重新启动 Sakura 服务后生效。";
        banner.innerHTML = `<span class="update-banner-text">${escapeHtml(doneText)}</span>`;
        banner.classList.remove("hidden");
      }
    } catch (error) {
      renderVersionPanel(info, `更新失败：${error.message || error}`);
      if (button) {
        button.disabled = false;
        button.innerHTML = original || "一键更新";
        if (window.lucide) window.lucide.createIcons();
      }
    }
  }

  function showUpdateBanner(info) {
    const banner = document.getElementById("updateBanner");
    if (!banner) return;
    if (!info || !info.update_available || !info.url) {
      banner.classList.add("hidden");
      return;
    }
    if (localStorage.getItem(DISMISS_KEY) === info.latest) return;

    const auto = canAutoUpdate(info);
    banner.innerHTML = `
      <span class="update-banner-text">发现新版本 <strong>${escapeHtml(info.latest)}</strong>，当前为 ${escapeHtml(info.current || "")}，建议更新。</span>
      ${
        auto
          ? `<button class="update-banner-link" id="updateBannerApply" type="button">一键更新</button>`
          : `<a class="update-banner-link" href="${escapeAttr(info.url)}" target="_blank" rel="noopener">下载新版</a>`
      }
      <button class="update-banner-close" type="button" aria-label="关闭">×</button>`;
    banner.classList.remove("hidden");
    const updateBtn = banner.querySelector("#updateBannerApply");
    if (updateBtn) {
      updateBtn.addEventListener("click", () => applyUpdate(info, updateBtn));
    }
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
