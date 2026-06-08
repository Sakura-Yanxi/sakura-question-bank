(function () {
  function setCoachMemoryBadge(version = 0, evidenceCount = 0) {
    const badge = $("#coachMemoryBadge");
    if (!badge) return;
    badge.textContent = evidenceCount ? `已建档 · ${evidenceCount} 条证据` : "未建档";
    badge.title = version ? `内部档案版本：v${version}` : "";
  }

  function openSimpleDialog(title, subtitle, bodyHtml) {
    const dialog = $("#detailDialog");
    dialog.classList.add("archive-mode");
    $("#detailContent").innerHTML = `
      <div class="archive-dialog">
        <div class="archive-dialog-head">
          <div>
            <h2>${escapeHtml(title)}</h2>
            <p>${escapeHtml(subtitle || "")}</p>
          </div>
        </div>
        ${bodyHtml}
      </div>`;
    if (!dialog.open) dialog.showModal();
    if (window.lucide) lucide.createIcons();
  }

  async function openProfileArchive() {
    openSimpleDialog("学习档案存档", "正在读取历史档案快照...", `<p class="empty-note">请稍等。</p>`);
    try {
      const data = await api("/api/profile/history");
      const profiles = data.profiles || [];
      const body = profiles.length
        ? `<div class="archive-list">${profiles.map((profile) => {
            const mastery = Math.round(Number(profile.avg_mastery || 0) * 100);
            const source = profile.source === "ai" ? "AI润色" : "本地统计";
            return `
              <article class="archive-item">
                <div class="archive-item-head">
                  <strong>v${profile.version} · ${source}</strong>
                  <span>${escapeHtml(profile.created_at || "")}</span>
                </div>
                <p>${escapeHtml(profile.headline || "本地统计档案")}</p>
                ${profile.pattern_summary ? `<small>${escapeHtml(profile.pattern_summary)}</small>` : ""}
                <div class="archive-meta">
                  <span>${profile.evidence_count || 0} 条证据</span>
                  <span>${profile.knowledge_count || 0} 个知识点</span>
                  <span>平均掌握 ${mastery}%</span>
                </div>
              </article>`;
          }).join("")}</div>`
        : `<p class="empty-note">还没有历史档案。先点击「更新学习档案」。</p>`;
      openSimpleDialog("学习档案存档", "每次更新学习档案都会生成一个可追溯快照。", body);
    } catch (error) {
      openSimpleDialog("学习档案存档", "读取失败", `<p class="empty-note">${escapeHtml(error.message)}</p>`);
    }
  }

  async function openTeacherMemoryArchive() {
    openSimpleDialog("老师记忆", "正在读取主动导入的长期记忆...", `<p class="empty-note">请稍等。</p>`);
    try {
      const data = await api("/api/ai-chat/memory");
      const memories = data.memories || [];
      const body = `
        ${memories.length
          ? `<div class="archive-list memory-archive-list">${memories.map((memory) => `
              <article class="archive-item">
                <div class="archive-item-head">
                  <strong>${escapeHtml(memory.source || "memory")}</strong>
                  <span>${escapeHtml(memory.created_at || "")}</span>
                </div>
                <p>${escapeHtml(memory.content || "")}</p>
              </article>`).join("")}</div>`
          : `<p class="empty-note">还没有主动导入的老师记忆。可以在 AI 学习教练或教材精读里导入。</p>`}
        <div class="archive-actions">
          <button id="goAiMemoryPanel" class="ghost"><i data-lucide="messages-square"></i>去维护记忆</button>
        </div>`;
      openSimpleDialog("老师记忆", "这些内容会作为 AI 老师了解你的长期上下文。", body);
      const go = $("#goAiMemoryPanel");
      if (go) {
        go.onclick = () => {
          $("#detailDialog").close();
          setView("aiChat");
        };
      }
    } catch (error) {
      openSimpleDialog("老师记忆", "读取失败", `<p class="empty-note">${escapeHtml(error.message)}</p>`);
    }
  }

  window.setCoachMemoryBadge = setCoachMemoryBadge;
  window.openSimpleDialog = openSimpleDialog;
  window.openProfileArchive = openProfileArchive;
  window.openTeacherMemoryArchive = openTeacherMemoryArchive;
  window.SakuraArchives = {
    setCoachMemoryBadge,
    openSimpleDialog,
    openProfileArchive,
    openTeacherMemoryArchive,
  };
})();
