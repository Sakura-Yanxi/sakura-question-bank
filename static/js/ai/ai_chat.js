(function () {
  let lastAiChatAnswer = "";
  let isBound = false;

  function updateLlmFields(data) {
    if (!data) return;
    if ($("#llmStatusBadge")) {
      $("#llmStatusBadge").textContent = data.has_key ? `已配置 · ${data.model || ""}` : "未配置 API";
      $("#llmStatusBadge").className = `tag ${data.has_key ? "" : "status wrong"}`;
    }
    if ($("#llmApiKey")) $("#llmApiKey").placeholder = data.masked_key ? `已保存：${data.masked_key}` : "未保存";
    if ($("#llmBaseUrl")) $("#llmBaseUrl").value = data.base_url || "";
    if ($("#llmModel")) $("#llmModel").value = data.model || "";
  }

  function renderTeacherMemories(memories = []) {
    const node = $("#teacherMemoryList");
    if (!node) return;
    node.innerHTML = memories.length
      ? memories.map((m) => `
        <article class="memory-item">
          <p>${escapeHtml(m.content)}</p>
          <small>${escapeHtml(m.source || "chat")} · ${escapeHtml(m.created_at || "")}</small>
          <button class="ghost" data-delete-ai-memory="${escapeAttr(m.id)}"><i data-lucide="trash-2"></i>删除</button>
        </article>`).join("")
      : `<p class="empty-note">还没有老师记忆。发送对话后，可把有价值的一轮主动导入。</p>`;
    if (window.lucide) lucide.createIcons();
  }

  function renderMentorExperiences(experiences = []) {
    const node = $("#mentorExperienceList");
    if (!node) return;
    node.innerHTML = experiences.length
      ? experiences.map((item) => `
        <article class="memory-item mentor-item">
          <p><strong>${escapeHtml(item.title || "外部经验")}</strong><br>${escapeHtml(item.content)}</p>
          <small>${escapeHtml(item.subject || "未指定科目")} · 可信度 ${escapeHtml(item.reliability || 3)} · ${(item.tags || []).map(escapeHtml).join(" / ")}${item.source ? ` · ${escapeHtml(item.source)}` : ""}</small>
          <button class="ghost" data-delete-mentor-experience="${escapeAttr(item.id)}"><i data-lucide="trash-2"></i>删除</button>
        </article>`).join("")
      : `<p class="empty-note">还没有外部经验。可以粘贴学长学姐经验、帖子总结或自己的方法论。</p>`;
    if (window.lucide) lucide.createIcons();
  }

  async function loadMentorExperiences() {
    if (!$("#mentorExperienceList")) return;
    try {
      const data = await api("/api/mentor-experience");
      renderMentorExperiences(data.experiences || []);
    } catch (error) {
      $("#mentorExperienceList").innerHTML = `<p class="empty-note">${escapeHtml(error.message)}</p>`;
    }
  }

  async function loadAiChatPanel() {
    if (!$("#aiChatInput")) return;
    try {
      const data = await api("/api/ai-chat/memory");
      updateLlmFields(data);
      renderTeacherMemories(data.memories || []);
      await loadMentorExperiences();
    } catch (error) {
      if ($("#aiChatOutput")) $("#aiChatOutput").textContent = error.message;
    }
  }

  async function saveLlmSettings() {
    const hint = $("#llmSettingsHint");
    if (hint) hint.textContent = "正在保存 API 设置...";
    try {
      const data = await api("/api/llm/settings", {
        method: "POST",
        body: JSON.stringify({
          api_key: $("#llmApiKey")?.value.trim() || "",
          base_url: $("#llmBaseUrl")?.value.trim() || "",
          model: $("#llmModel")?.value.trim() || "",
        }),
      });
      updateLlmFields(data);
      if ($("#llmApiKey")) $("#llmApiKey").value = "";
      if (hint) hint.textContent = data.message || "已保存。";
    } catch (error) {
      if (hint) hint.textContent = error.message;
    }
  }

  async function sendAiChat() {
    const input = $("#aiChatInput");
    const output = $("#aiChatOutput");
    const message = input?.value.trim();
    if (!message) return;
    renderAiOutput(output, "正在请求 AI 老师...");
    try {
      const data = await api("/api/ai-chat", {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      lastAiChatAnswer = data.answer || "";
      updateLlmFields(data);
      const strategyName = data.teacher_strategy?.name || "";
      const intentText = data.teacher_intent ? `意图：${data.teacher_intent}` : "";
      const strategyText = strategyName ? `策略：${strategyName}` : "";
      const prefix = [intentText, strategyText].filter(Boolean).join(" · ");
      renderAiOutput(output, `${prefix ? `【${prefix}】\n\n` : ""}${lastAiChatAnswer || "AI 没有返回内容。"}`);
    } catch (error) {
      renderAiOutput(output, error.message);
    }
  }

  async function saveAiMemory(content, source = "chat") {
    const text = (content || "").trim();
    if (!text) return;
    await api("/api/ai-chat/memory", {
      method: "POST",
      body: JSON.stringify({ content: text, source }),
    });
    await loadAiChatPanel();
  }

  async function saveMentorExperience() {
    const content = $("#mentorExperienceContent")?.value.trim() || "";
    if (!content) return;
    await api("/api/mentor-experience", {
      method: "POST",
      body: JSON.stringify({
        title: $("#mentorExperienceTitle")?.value.trim() || "",
        subject: $("#mentorExperienceSubject")?.value.trim() || "",
        tags: $("#mentorExperienceTags")?.value.trim() || "",
        reliability: $("#mentorExperienceReliability")?.value || "3",
        source: $("#mentorExperienceSource")?.value.trim() || "",
        content,
      }),
    });
    ["#mentorExperienceTitle", "#mentorExperienceSubject", "#mentorExperienceTags", "#mentorExperienceContent", "#mentorExperienceSource"].forEach((sel) => {
      if ($(sel)) $(sel).value = "";
    });
    await loadMentorExperiences();
  }

  function bindAiChatPanel() {
    if (isBound) return;
    isBound = true;
    on("#sendAiChat", "click", sendAiChat);
    on("#saveLlmSettings", "click", saveLlmSettings);
    on("#refreshAiMemory", "click", loadAiChatPanel);
    on("#refreshMentorExperience", "click", loadMentorExperiences);
    on("#saveMentorExperience", "click", saveMentorExperience);
    on("#saveAiChatMemory", "click", async () => {
      const message = $("#aiChatInput")?.value.trim() || "";
      const content = lastAiChatAnswer ? `用户问题：${message}\nAI 回答：${lastAiChatAnswer}` : message;
      await saveAiMemory(content, "chat");
      if ($("#aiChatOutput")) $("#aiChatOutput").textContent = "已导入老师记忆。";
    });
    on("#saveManualAiMemory", "click", async () => {
      await saveAiMemory($("#manualAiMemory")?.value || "", "manual");
      if ($("#manualAiMemory")) $("#manualAiMemory").value = "";
    });
    on("#clearAiChat", "click", () => {
      lastAiChatAnswer = "";
      if ($("#aiChatInput")) $("#aiChatInput").value = "";
      if ($("#aiChatOutput")) $("#aiChatOutput").textContent = "已清空。";
    });
    on("#teacherMemoryList", "click", async (event) => {
      const btn = event.target.closest("[data-delete-ai-memory]");
      if (!btn) return;
      await api(`/api/ai-chat/memory/${encodeURIComponent(btn.dataset.deleteAiMemory)}`, { method: "DELETE" });
      await loadAiChatPanel();
    });
    on("#mentorExperienceList", "click", async (event) => {
      const btn = event.target.closest("[data-delete-mentor-experience]");
      if (!btn) return;
      await api(`/api/mentor-experience/${encodeURIComponent(btn.dataset.deleteMentorExperience)}`, { method: "DELETE" });
      await loadMentorExperiences();
    });
  }

  window.loadAiChatPanel = loadAiChatPanel;
  window.SakuraAiChat = {
    load: loadAiChatPanel,
    bind: bindAiChatPanel,
  };

  bindAiChatPanel();
})();
