(function () {
  let isBound = false;

  async function loadDaily() {
    if ($("#dailyRuleList")) await loadDailyRules();
    const data = await api("/api/daily");
    $("#dailyMessage").textContent = `${data.date} · ${data.message}`;
    $("#dailyGrid").innerHTML =
      (data.groups || [])
        .map(
          (group) => `
          <section class="daily-group">
            <div class="daily-group-head">
              <h3>${escapeHtml(group.title)}</h3>
              <span>${group.questions.length} 题</span>
            </div>
            <div class="question-grid mini-grid">
              ${group.questions
                .map(
                  (q) => `
                  <article class="question-card">
                    <div class="thumb" data-open="${escapeAttr(q.id)}">
                      <img src="${q.image_url}" alt="第 ${q.page_number} 页题目" loading="lazy" />
                    </div>
                    <div class="card-body">
                      <div class="meta">
                        <span>${escapeHtml(q.document_title || q.filename || "做题本")} · 第 ${q.page_number} 页</span>
                        <span class="tag status ${statusClass(q.status)}">${escapeHtml(q.status)}</span>
                      </div>
                      <strong>${escapeHtml(q.category)}</strong>
                      <span class="tag">${escapeHtml(q.chapter || "未识别章节")}</span>
                      <span class="tag kind ${questionKind(q) === "模拟卷" ? "mock" : "paper"}">${questionKind(q)}</span>
                      ${q.daily_kind === "foundation" ? '<span class="tag foundation">前置基础</span>' : ""}
                      ${reviewTag(q)}
                      <div class="actions">
                        <button data-status="做对" data-id="${escapeAttr(q.id)}">做对</button>
                        <button data-status="做错" data-id="${escapeAttr(q.id)}">做错</button>
                        <button class="ghost" data-open="${escapeAttr(q.id)}">详情</button>
                      </div>
                    </div>
                  </article>`
                )
                .join("")}
            </div>
          </section>`
        )
        .join("") || "<p>暂无每日练习。先上传做题本或标记错题。</p>";
  }

  function dailyRuleStatusLabel(value) {
    return {
      active_wrong: "当前错题+到期复习",
      due: "只看今天到期复习",
      wrong: "只看做错",
      review: "半会/需复习",
      all_wrong_history: "历史曾错题",
    }[value || "active_wrong"] || "当前错题+到期复习";
  }

  function cleanDailyRulePart(text) {
    return String(text || "")
      .replace(/\s+[·路]\s*(做题本|模拟卷|资料)$/u, "")
      .trim();
  }

  function buildDailyRuleName() {
    const subject = $("#dailyRuleSubject")?.value || "";
    const documentId = $("#dailyRuleDocument")?.value || "";
    const category = $("#dailyRuleCategory")?.value || "";
    const chapter = $("#dailyRuleChapter")?.value || "";
    const status = $("#dailyRuleStatus")?.value || "active_wrong";
    const limit = Math.max(1, Math.min(30, Number($("#dailyRuleLimit")?.value) || 5));
    const parts = [];
    if (subject) parts.push(subject);
    if (documentId) parts.push(cleanDailyRulePart(selectedOptionText("#dailyRuleDocument", "指定资料")));
    if (category) parts.push(category);
    if (chapter) parts.push(chapter);
    parts.push(dailyRuleStatusLabel(status));
    parts.push(`${limit}题`);
    return parts.join(" · ");
  }

  function updateDailyRuleName() {
    const el = $("#dailyRuleName");
    if (el) el.value = buildDailyRuleName();
  }

  async function populateDailyRuleFilters(resetFrom = "") {
    if (!$("#dailyRuleDocument")) return;
    const documentId = $("#dailyRuleDocument").value;
    let subject = $("#dailyRuleSubject").value;
    if (resetFrom === "document") {
      const doc = state.documents.find((item) => item.id === documentId);
      subject = doc?.subject || "";
    }
    const category = ["document", "subject"].includes(resetFrom) ? "" : $("#dailyRuleCategory").value;
    const chapter = ["document", "subject", "category"].includes(resetFrom) ? "" : $("#dailyRuleChapter").value;
    const params = new URLSearchParams();
    if (documentId) params.set("document_id", documentId);
    if (subject) params.set("subject", subject);
    if (category) params.set("category", category);
    if (chapter) params.set("chapter", chapter);
    const data = await api(`/api/daily/rule-options?${params}`);
    const docs = (data.documents || []).map((doc) => ({
      value: doc.id,
      label: documentLabel(doc),
    }));
    const docEl = $("#dailyRuleDocument");
    const keepDoc = docs.some((doc) => String(doc.value) === String(documentId)) ? documentId : "";
    docEl.innerHTML = `<option value="">全部资料</option>${docs
      .map((doc) => `<option value="${escapeAttr(doc.value)}" ${String(doc.value) === String(keepDoc) ? "selected" : ""}>${escapeHtml(doc.label)}</option>`)
      .join("")}`;
    docEl.value = keepDoc;
    subject = setSelectOptions("#dailyRuleSubject", data.subjects, "全部科目", subject);
    const scopedReady = Boolean(keepDoc && subject);
    if (scopedReady) {
      unlockSelect("#dailyRuleCategory");
      unlockSelect("#dailyRuleChapter");
      setSelectOptions("#dailyRuleCategory", data.categories, "全部知识点", category);
      setSelectOptions("#dailyRuleChapter", data.chapters, "全部章节", chapter);
    } else {
      setSelectLocked("#dailyRuleCategory", "请先选择科目和资料");
      setSelectLocked("#dailyRuleChapter", "请先选择科目和资料");
    }
    updateDailyRuleName();
  }

  function resetDailyRuleForm() {
    if ($("#dailyRuleStatus")) $("#dailyRuleStatus").value = "active_wrong";
    if ($("#dailyRuleLimit")) $("#dailyRuleLimit").value = 5;
    if ($("#dailyRuleSubject")) $("#dailyRuleSubject").value = "";
    if ($("#dailyRuleDocument")) $("#dailyRuleDocument").value = "";
    if ($("#dailyRuleCategory")) $("#dailyRuleCategory").value = "";
    if ($("#dailyRuleChapter")) $("#dailyRuleChapter").value = "";
    populateDailyRuleFilters().catch((err) => {
      const hint = $("#dailyRuleHint");
      if (hint) hint.textContent = err.message;
    });
  }

  async function loadDailyRules() {
    if (!$("#dailyRuleList")) return;
    const data = await api("/api/daily/rules");
    state.dailyRules = data.rules || [];
    $("#dailyRuleBadge").textContent = `${state.dailyRules.length} 条规则`;
    $("#dailyRuleList").innerHTML =
      state.dailyRules
        .map(
          (rule) => `
          <article class="daily-rule-item ${rule.enabled ? "" : "disabled"}">
            <div>
              <strong>${escapeHtml(rule.name || "未命名规则")}</strong>
              <p>${escapeHtml(rule.document_title || "全部资料")} · ${escapeHtml(rule.subject || "全部科目")} · ${escapeHtml(rule.category || "全部知识点")} · ${escapeHtml(rule.chapter || "全部章节")}</p>
              <small>${escapeHtml(dailyRuleStatusLabel(rule.status_group))} · 每次 ${rule.limit_count || 5} 题</small>
            </div>
            <div class="daily-rule-actions">
              <label class="switch-lite"><input type="checkbox" data-daily-rule-enabled="${escapeAttr(rule.id)}" ${rule.enabled ? "checked" : ""} /><span>启用</span></label>
              <button class="ghost danger-soft-btn" data-delete-daily-rule="${escapeAttr(rule.id)}"><i data-lucide="trash-2"></i>删除</button>
            </div>
          </article>`
        )
        .join("") || `<p class="empty-note">还没有自定义规则。选择科目、做题本或章节后保存即可。</p>`;
    if (window.lucide) lucide.createIcons();
  }

  async function saveDailyRule() {
    const hint = $("#dailyRuleHint");
    updateDailyRuleName();
    if (hint) hint.textContent = "正在保存规则...";
    const selectedDocument = $("#dailyRuleDocument")?.value || "";
    const selectedSubject = $("#dailyRuleSubject")?.value || "";
    if (!selectedSubject || !selectedDocument) {
      if (hint) hint.textContent = "请先选择科目和资料/做题本，再保存规则。";
      return;
    }
    const payload = {
      name: $("#dailyRuleName")?.value || buildDailyRuleName(),
      document_id: selectedDocument,
      subject: selectedSubject,
      category: $("#dailyRuleCategory")?.value || "",
      chapter: $("#dailyRuleChapter")?.value || "",
      status_group: $("#dailyRuleStatus")?.value || "active_wrong",
      limit_count: Math.max(1, Math.min(30, Number($("#dailyRuleLimit")?.value) || 5)),
      enabled: true,
    };
    await api("/api/daily/rules", { method: "POST", body: JSON.stringify(payload) });
    if (hint) hint.textContent = "规则已保存。";
    await loadDaily();
  }

  async function updateDailyRuleEnabled(id, enabled) {
    await api("/api/daily/rules", { method: "POST", body: JSON.stringify({ id, enabled }) });
    await loadDaily();
  }

  async function deleteDailyRule(id) {
    if (!confirm("确定删除这条每日练习规则吗？")) return;
    await api(`/api/daily/rules/${encodeURIComponent(id)}`, { method: "DELETE" });
    await loadDaily();
  }

  function bindDailyPanel() {
    if (isBound) return;
    isBound = true;
    on("#refreshDaily", "click", loadDaily);
    on("#saveDailyRule", "click", saveDailyRule);
    on("#resetDailyRule", "click", resetDailyRuleForm);
    on("#dailyRuleDocument", "change", async () => {
      await populateDailyRuleFilters("document");
    });
    on("#dailyRuleSubject", "change", async () => {
      await populateDailyRuleFilters("subject");
    });
    on("#dailyRuleCategory", "change", async () => {
      await populateDailyRuleFilters("category");
    });
    on("#dailyRuleChapter", "change", updateDailyRuleName);
    on("#dailyRuleStatus", "change", updateDailyRuleName);
    on("#dailyRuleLimit", "input", updateDailyRuleName);
    on("#dailyRuleList", "change", async (event) => {
      const input = event.target.closest("[data-daily-rule-enabled]");
      if (!input) return;
      await updateDailyRuleEnabled(input.dataset.dailyRuleEnabled, input.checked);
    });
    on("#dailyRuleList", "click", async (event) => {
      const btn = event.target.closest("[data-delete-daily-rule]");
      if (!btn) return;
      await deleteDailyRule(btn.dataset.deleteDailyRule);
    });
  }

  window.SakuraDaily = {
    load: loadDaily,
    populateFilters: populateDailyRuleFilters,
    resetRuleForm: resetDailyRuleForm,
    bind: bindDailyPanel,
  };

  bindDailyPanel();
})();
