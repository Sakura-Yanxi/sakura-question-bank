(function () {
  let isBound = false;
  const DAILY_COLLAPSE_STORAGE_KEY = "sakura.daily.collapsedSections";

  function dailyCollapsedState() {
    try {
      return JSON.parse(localStorage.getItem(DAILY_COLLAPSE_STORAGE_KEY) || "{}") || {};
    } catch {
      return {};
    }
  }

  function isDailySectionCollapsed(key) {
    return Boolean(dailyCollapsedState()[key]);
  }

  function setDailySectionCollapsed(key, collapsed) {
    const state = dailyCollapsedState();
    state[key] = Boolean(collapsed);
    try {
      localStorage.setItem(DAILY_COLLAPSE_STORAGE_KEY, JSON.stringify(state));
    } catch {
      // Ignore storage failures; the current toggle still updates the page.
    }
  }

  function updateDailySectionCollapsed(section, collapsed) {
    if (!section) return;
    section.classList.toggle("collapsed", collapsed);
    const btn = section.querySelector("[data-daily-collapse]");
    if (btn) {
      btn.setAttribute("aria-expanded", String(!collapsed));
      const icon = btn.querySelector("i");
      if (icon) icon.setAttribute("data-lucide", collapsed ? "chevron-right" : "chevron-down");
    }
    if (window.lucide) lucide.createIcons();
  }

  function dailyQuestionCard(q) {
    const kind = questionKind(q);
    const quickStatus = q.quick_status || "";
    return `
      <article class="question-card">
        <div class="thumb" data-open="${escapeAttr(q.id)}">
          <img src="${escapeAttr(q.image_url)}" alt="第 ${q.page_number} 页题目" loading="lazy" />
        </div>
        <div class="card-body">
          <div class="meta">
            <span>${escapeHtml(q.document_title || q.filename || "做题本")} · 第 ${q.page_number} 页</span>
            <span class="tag status ${statusClass(q.status)}">${escapeHtml(q.status)}</span>
          </div>
          <strong>${escapeHtml(q.category || "未识别知识点")}</strong>
          <span class="tag">${escapeHtml(q.chapter || "未识别章节")}</span>
          <span class="tag kind ${kind === "模拟卷" ? "mock" : "paper"}">${escapeHtml(kind)}</span>
          ${q.daily_kind === "foundation" ? '<span class="tag foundation">前置基础</span>' : ""}
          ${q.batch_position ? `<span class="tag pushed">推送 #${escapeHtml(q.batch_position)}</span>` : ""}
          ${quickStatus ? `<span class="tag status ${statusClass(quickStatus)}">已回填：${escapeHtml(quickStatus)}</span>` : ""}
          ${reviewTag(q)}
          <div class="actions">
            <button data-status="做对" data-id="${escapeAttr(q.id)}">做对</button>
            <button data-status="做错" data-id="${escapeAttr(q.id)}">做错</button>
            <button class="ghost" data-open="${escapeAttr(q.id)}">详情</button>
          </div>
        </div>
      </article>`;
  }

  function dailyQuestionGrid(questions, emptyText) {
    if (!questions.length) return `<p class="empty-note">${escapeHtml(emptyText)}</p>`;
    return `<div class="question-grid mini-grid">${questions.map(dailyQuestionCard).join("")}</div>`;
  }

  function renderDailyGroups(groups) {
    if (!groups.length) return `<p class="empty-note">暂无艾宾浩斯练习。先上传做题本，或把题目标记为做错、半会、需复习。</p>`;
    return groups
      .map((group) => {
        const questions = group.questions || [];
        return `
          <section class="daily-group">
            <div class="daily-group-head">
              <h3>${escapeHtml(group.title)}</h3>
              <span>${questions.length} 题</span>
            </div>
            ${dailyQuestionGrid(questions, "这组暂时没有题目。")}
          </section>`;
      })
      .join("");
  }

  function renderPushBatch(batchPayload) {
    if (!batchPayload || !batchPayload.batch) {
      return `<p class="empty-note">今天还没有生成过推送批次。到“提醒打卡”里测试每日推送，或等待定时推送后这里会自动出现。</p>`;
    }
    const batch = batchPayload.batch;
    const questions = batchPayload.questions || [];
    const doneCount = Number(batch.done_count || 0);
    const total = Number(batch.question_count || questions.length || 0);
    const dayLabel = batchPayload.is_today ? "今日推送" : `最近一次有题目的推送 · ${batch.day || "未记录日期"}`;
    return `
      <div class="daily-batch-meta">
        <div>
          <strong>${escapeHtml(dayLabel)}</strong>
          <span>${escapeHtml(batch.created_at || "")} · 已回填 ${doneCount}/${total}</span>
        </div>
        <a class="ghost daily-practice-link" href="/practice/${escapeAttr(batch.id)}" target="_blank" rel="noopener">
          <i data-lucide="external-link"></i>打开回填页
        </a>
      </div>
      ${dailyQuestionGrid(questions, "这个推送批次没有题目。")}`;
  }

  function dailySection({ key, title, subtitle, count, body }) {
    const collapsed = isDailySectionCollapsed(key);
    const bodyId = `daily-section-body-${key}`;
    return `
      <section class="daily-collapsible ${collapsed ? "collapsed" : ""}" data-daily-section="${escapeAttr(key)}">
        <div class="daily-section-head">
          <div>
            <h3>${escapeHtml(title)}</h3>
            <p>${escapeHtml(subtitle || "")}</p>
          </div>
          <div class="daily-section-tools">
            <span>${count} 题</span>
            <button class="ghost daily-collapse-btn" type="button" data-daily-collapse="${escapeAttr(key)}" aria-expanded="${String(!collapsed)}" aria-controls="${bodyId}" title="折叠/展开">
              <i data-lucide="${collapsed ? "chevron-right" : "chevron-down"}"></i>
            </button>
          </div>
        </div>
        <div id="${bodyId}" class="daily-section-body">
          ${body}
        </div>
      </section>`;
  }

  async function loadDaily() {
    if ($("#dailyRuleList")) await loadDailyRules();
    const data = await api("/api/daily");
    const groups = data.groups || [];
    const pushQuestions = data.latest_push_batch?.questions || [];
    $("#dailyMessage").textContent = `${data.date} · ${data.message}`;
    $("#dailyGrid").innerHTML = [
      dailySection({
        key: "ebbinghaus",
        title: "艾宾浩斯 / 当前练习队列",
        subtitle: "按到期复习、自定义每日规则和薄弱章节生成。",
        count: groups.reduce((sum, group) => sum + (group.questions || []).length, 0),
        body: renderDailyGroups(groups),
      }),
      dailySection({
        key: "pushed",
        title: data.latest_push_batch?.is_today ? "今日已推送错题" : "最近推送错题",
        subtitle: "优先显示今天的推送；今天没有题目时，自动显示最近一次有题目的推送。",
        count: pushQuestions.length,
        body: renderPushBatch(data.latest_push_batch),
      }),
    ].join("");
    if (window.lucide) lucide.createIcons();
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
    on("#dailyGrid", "click", (event) => {
      const btn = event.target.closest("[data-daily-collapse]");
      if (!btn) return;
      const key = btn.dataset.dailyCollapse;
      const collapsed = btn.getAttribute("aria-expanded") === "true";
      setDailySectionCollapsed(key, collapsed);
      updateDailySectionCollapsed(btn.closest("[data-daily-section]"), collapsed);
    });
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
