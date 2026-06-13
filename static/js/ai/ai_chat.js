(function () {
  let lastAiChatAnswer = "";
  let isBound = false;
  let memorySubjects = ["未分科"];
  let memorySettings = {
    compression_prompt: "",
    default_compression_prompt: "",
    is_custom: false,
  };

  function updateLlmFields(data) {
    if (!data) return;
    if ($("#llmStatusBadge")) {
      $("#llmStatusBadge").textContent = data.has_key ? `已配置 · ${data.model || ""}` : "未配置 API";
      $("#llmStatusBadge").className = `tag ${data.has_key ? "" : "status wrong"}`;
    }
    if ($("#llmApiKey")) $("#llmApiKey").placeholder = data.masked_key ? `已保存：${data.masked_key}` : "未保存";
    if ($("#llmBaseUrl")) $("#llmBaseUrl").value = data.base_url || "";
    if ($("#llmModel")) $("#llmModel").value = data.model || "";
    if ($("#llmVisionModel")) $("#llmVisionModel").value = data.vision_model || "";
    if ($("#llmVisionApiKey")) $("#llmVisionApiKey").placeholder = data.vision_masked_key ? `已保存：${data.vision_masked_key}` : "留空=复用上面的 Key";
    if ($("#llmVisionBaseUrl")) $("#llmVisionBaseUrl").value = data.vision_base_url || "";
  }

  function renderTeacherMemories(memories = []) {
    const node = $("#teacherMemoryList");
    if (!node) return;
    node.innerHTML = memories.length
      ? memories.map((m) => `
        <article class="memory-item">
          <p>${escapeHtml(m.content)}</p>
          <small><span class="subject-chip">${escapeHtml(m.subject || "未分科")}</span> · ${escapeHtml(m.source || "chat")} · ${escapeHtml(m.created_at || "")}</small>
          <button class="ghost" data-delete-ai-memory="${escapeAttr(m.id)}"><i data-lucide="trash-2"></i>删除</button>
        </article>`).join("")
      : `<p class="empty-note">还没有老师记忆。发送对话后，可把有价值的一轮主动导入。</p>`;
    if (window.lucide) lucide.createIcons();
  }

  function updateMemorySubjects(subjects = []) {
    const next = subjects.map((item) => String(item || "").trim()).filter(Boolean);
    memorySubjects = Array.from(new Set(["未分科", ...next]));
    return memorySubjects;
  }

  function updateMemorySettings(settings = {}) {
    memorySettings = {
      ...memorySettings,
      ...settings,
    };
    return memorySettings;
  }

  async function loadTeacherMemorySubjects() {
    const data = await api("/api/ai-chat/memory-subjects");
    return updateMemorySubjects(data.subjects || []);
  }

  async function loadTeacherMemorySettings() {
    const data = await api("/api/ai-chat/memory-settings");
    return updateMemorySettings(data);
  }

  function subjectSelectOptions(selected = "") {
    const active = selected || memorySubjects[0] || "未分科";
    return memorySubjects.map((subject) => `
      <option value="${escapeAttr(subject)}"${subject === active ? " selected" : ""}>${escapeHtml(subject)}</option>
    `).join("");
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
      updateMemorySubjects(data.subjects || []);
      updateMemorySettings(data.memory_settings || {});
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
          vision_model: $("#llmVisionModel")?.value.trim() || "",
          vision_api_key: $("#llmVisionApiKey")?.value.trim() || "",
          vision_base_url: $("#llmVisionBaseUrl")?.value.trim() || "",
        }),
      });
      updateLlmFields(data);
      if ($("#llmApiKey")) $("#llmApiKey").value = "";
      if ($("#llmVisionApiKey")) $("#llmVisionApiKey").value = "";
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

  async function openMemorySubjectDialog({ content, source }) {
    const text = (content || "").trim();
    if (!text) return null;
    try {
      await loadTeacherMemorySubjects();
      await loadTeacherMemorySettings();
    } catch (error) {
      memorySubjects = memorySubjects.length ? memorySubjects : ["未分科"];
    }
    const dialog = $("#detailDialog");
    const preview = text.length > 260 ? `${text.slice(0, 260)}...` : text;
    let resolved = false;
    return new Promise((resolve) => {
      const finish = (value) => {
        if (resolved) return;
        resolved = true;
        dialog.removeEventListener("close", onClose);
        resolve(value);
      };
      const onClose = () => finish(null);
      dialog.classList.add("archive-mode");
      $("#detailContent").innerHTML = `
        <div class="archive-dialog memory-subject-dialog">
          <div class="archive-dialog-head">
            <div>
              <h2>导入老师记忆</h2>
              <p>先选择学科，再把原始内容压缩成长期可复用的老师记忆。摘要可以手动修改。</p>
            </div>
          </div>
          <div class="memory-subject-form">
            <label class="coach-field">
              <span>选择已有学科</span>
              <select id="memoryImportSubject">${subjectSelectOptions()}</select>
            </label>
            <label class="coach-field">
              <span>新建学科（可选）</span>
              <input id="memoryImportNewSubject" type="text" placeholder="例如：408 机组 / 高等数学 / 英语阅读" />
            </label>
            <label class="coach-field memory-wide-field">
              <span>本次额外压缩要求（可选）</span>
              <input id="memoryCompressionInstruction" type="text" placeholder="例如：更关注我的错因；只保留后续教学策略；语气更严格一点" />
            </label>
            <details class="memory-compression-settings memory-wide-field">
              <summary><i data-lucide="sliders-horizontal"></i> 自定义记忆压缩模板</summary>
              <textarea id="memoryCompressionPrompt" rows="8">${escapeHtml(memorySettings.compression_prompt || "")}</textarea>
              <div class="memory-compression-actions">
                <button id="saveMemoryCompressionPrompt" type="button" class="ghost"><i data-lucide="save"></i>保存模板</button>
                <button id="resetMemoryCompressionPrompt" type="button" class="ghost"><i data-lucide="rotate-ccw"></i>恢复默认</button>
                <span id="memoryCompressionPromptHint" class="coach-hint">${memorySettings.is_custom ? "当前使用自定义模板" : "当前使用默认模板"}</span>
              </div>
            </details>
            <div class="memory-preview-box">
              <strong>原始内容预览</strong>
              <p>${escapeHtml(preview)}</p>
              <small>来源：${escapeHtml(source || "chat")}</small>
            </div>
            <label class="coach-field memory-wide-field">
              <span>压缩后的老师记忆（可编辑）</span>
              <textarea id="memoryCompressedContent" rows="5" placeholder="点击“智能归纳”生成；如果直接保存，会先自动归纳。"></textarea>
            </label>
          </div>
          <div class="archive-actions">
            <button id="cancelMemoryImport" class="ghost"><i data-lucide="x"></i>取消</button>
            <button id="runMemoryCompress" class="ghost"><i data-lucide="wand-sparkles"></i>智能归纳</button>
            <button id="confirmMemoryImport"><i data-lucide="brain-circuit"></i>保存归纳记忆</button>
          </div>
        </div>`;
      dialog.addEventListener("close", onClose, { once: true });
      if (!dialog.open) dialog.showModal();
      if (window.lucide) lucide.createIcons();
      const currentSubject = () => {
        const created = $("#memoryImportNewSubject")?.value.trim() || "";
        const selected = $("#memoryImportSubject")?.value || "未分科";
        return created || selected;
      };
      const runCompression = async () => {
        const target = $("#memoryCompressedContent");
        if (target) target.value = "正在归纳压缩...";
        try {
          const data = await api("/api/ai-chat/memory/compress", {
            method: "POST",
            body: JSON.stringify({
              content: text,
              source,
              subject: currentSubject(),
              instruction: $("#memoryCompressionInstruction")?.value.trim() || "",
            }),
          });
          updateMemorySettings(data.memory_settings || {});
          if (target) target.value = data.summary || "";
          return data.summary || "";
        } catch (error) {
          if (target) target.value = error.message;
          throw error;
        }
      };
      $("#cancelMemoryImport").onclick = () => {
        finish(null);
        dialog.close();
      };
      $("#runMemoryCompress").onclick = async () => {
        await runCompression();
      };
      $("#saveMemoryCompressionPrompt").onclick = async () => {
        const hint = $("#memoryCompressionPromptHint");
        if (hint) hint.textContent = "正在保存模板...";
        const data = await api("/api/ai-chat/memory-settings", {
          method: "POST",
          body: JSON.stringify({ compression_prompt: $("#memoryCompressionPrompt")?.value || "" }),
        });
        updateMemorySettings(data);
        if (hint) hint.textContent = "已保存自定义压缩模板。";
      };
      $("#resetMemoryCompressionPrompt").onclick = async () => {
        const data = await api("/api/ai-chat/memory-settings", {
          method: "POST",
          body: JSON.stringify({ reset: true }),
        });
        updateMemorySettings(data);
        if ($("#memoryCompressionPrompt")) $("#memoryCompressionPrompt").value = data.compression_prompt || "";
        if ($("#memoryCompressionPromptHint")) $("#memoryCompressionPromptHint").textContent = "已恢复默认模板。";
      };
      $("#confirmMemoryImport").onclick = async () => {
        let summary = $("#memoryCompressedContent")?.value.trim() || "";
        if (!summary || summary === "正在归纳压缩...") {
          summary = await runCompression();
        }
        if (!summary) return;
        finish({ subject: currentSubject(), content: summary });
        dialog.close();
      };
    });
  }

  async function saveAiMemory(content, source = "chat", subject = "") {
    const text = (content || "").trim();
    if (!text) return;
    const saved = await api("/api/ai-chat/memory", {
      method: "POST",
      body: JSON.stringify({ content: text, source, subject }),
    });
    if (saved.memory?.subject) {
      updateMemorySubjects([saved.memory.subject, ...memorySubjects]);
    }
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
      const result = await openMemorySubjectDialog({ content, source: "chat" });
      if (!result) return;
      await saveAiMemory(result.content, "chat", result.subject);
      if ($("#aiChatOutput")) $("#aiChatOutput").textContent = "已导入老师记忆。";
    });
    on("#saveManualAiMemory", "click", async () => {
      const content = $("#manualAiMemory")?.value || "";
      const result = await openMemorySubjectDialog({ content, source: "manual" });
      if (!result) return;
      await saveAiMemory(result.content, "manual", result.subject);
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
  window.loadTeacherMemorySubjects = loadTeacherMemorySubjects;
  window.loadTeacherMemorySettings = loadTeacherMemorySettings;
  window.SakuraAiChat = {
    load: loadAiChatPanel,
    bind: bindAiChatPanel,
    loadTeacherMemorySubjects,
    loadTeacherMemorySettings,
  };

  bindAiChatPanel();
})();
