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
    function subjectOptions(subjects = [], selected = "") {
      const normalized = Array.from(new Set(["未分科", ...subjects.map((item) => String(item || "").trim()).filter(Boolean)]));
      return [
        `<option value="">全部学科</option>`,
        ...normalized.map((subject) => `<option value="${escapeAttr(subject)}"${subject === selected ? " selected" : ""}>${escapeHtml(subject)}</option>`),
      ].join("");
    }

    function renderMemoryItems(memories = []) {
      const list = $("#teacherMemoryArchiveList");
      if (!list) return;
      list.innerHTML = memories.length
        ? memories.map((memory) => `
            <article class="archive-item teacher-memory-archive-item">
              <div class="archive-item-head">
                <strong>${escapeHtml(memory.subject || "未分科")}</strong>
                <span>${escapeHtml(memory.created_at || "")}</span>
              </div>
              <p>${escapeHtml(memory.content || "")}</p>
              <div class="archive-meta">
                <span>${escapeHtml(memory.source || "memory")}</span>
                <button class="ghost danger-ghost" data-delete-ai-memory="${escapeAttr(memory.id)}"><i data-lucide="trash-2"></i>删除</button>
              </div>
            </article>`).join("")
        : `<p class="empty-note">没有匹配的老师记忆。可以换一个学科或关键词，也可以在 AI 学习教练里导入。</p>`;
      if (window.lucide) lucide.createIcons();
    }

    async function refreshArchiveMemories() {
      const subject = $("#teacherMemoryArchiveSubject")?.value || "";
      const q = $("#teacherMemoryArchiveSearch")?.value.trim() || "";
      const params = new URLSearchParams({ limit: "120" });
      if (subject) params.set("subject", subject);
      if (q) params.set("q", q);
      const data = await api(`/api/ai-chat/memory?${params.toString()}`);
      renderMemoryItems(data.memories || []);
      const select = $("#teacherMemoryArchiveSubject");
      if (select) select.innerHTML = subjectOptions(data.subjects || [], subject);
      return data;
    }

    openSimpleDialog("老师记忆", "正在读取主动导入的长期记忆...", `<p class="empty-note">请稍等。</p>`);
    try {
      const data = await api("/api/ai-chat/memory?limit=120");
      const body = `
        <div class="memory-archive-toolbar">
          <label class="coach-field">
            <span>学科</span>
            <select id="teacherMemoryArchiveSubject">${subjectOptions(data.subjects || [])}</select>
          </label>
          <label class="coach-field">
            <span>自由搜索</span>
            <input id="teacherMemoryArchiveSearch" type="search" placeholder="搜索记忆内容、来源或学科" />
          </label>
          <label class="coach-field">
            <span>新建学科</span>
            <input id="teacherMemoryArchiveNewSubject" type="text" placeholder="例如：408 机组" />
          </label>
          <button id="createTeacherMemorySubject" class="ghost"><i data-lucide="plus"></i>创建</button>
        </div>
        <div id="teacherMemoryArchiveList" class="archive-list memory-archive-list"></div>
        <div class="archive-actions">
          <button id="goAiMemoryPanel" class="ghost"><i data-lucide="messages-square"></i>去导入记忆</button>
        </div>`;
      openSimpleDialog("老师记忆", "按学科查看长期记忆，也可以直接搜索关键词。", body);
      renderMemoryItems(data.memories || []);
      const go = $("#goAiMemoryPanel");
      if (go) {
        go.onclick = () => {
          $("#detailDialog").close();
          setView("aiChat");
        };
      }
      $("#teacherMemoryArchiveSubject").onchange = refreshArchiveMemories;
      $("#teacherMemoryArchiveSearch").oninput = () => {
        clearTimeout(window.__teacherMemorySearchTimer);
        window.__teacherMemorySearchTimer = setTimeout(refreshArchiveMemories, 220);
      };
      $("#createTeacherMemorySubject").onclick = async () => {
        const input = $("#teacherMemoryArchiveNewSubject");
        const subject = input?.value.trim() || "";
        if (!subject) return;
        const created = await api("/api/ai-chat/memory-subjects", {
          method: "POST",
          body: JSON.stringify({ subject }),
        });
        if (input) input.value = "";
        const select = $("#teacherMemoryArchiveSubject");
        if (select) {
          select.innerHTML = subjectOptions(created.subjects || [], created.subject);
          select.value = created.subject;
        }
        await refreshArchiveMemories();
      };
      $("#teacherMemoryArchiveList").onclick = async (event) => {
        const btn = event.target.closest("[data-delete-ai-memory]");
        if (!btn) return;
        await api(`/api/ai-chat/memory/${encodeURIComponent(btn.dataset.deleteAiMemory)}`, { method: "DELETE" });
        await refreshArchiveMemories();
      };
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
