(function () {
  let isBound = false;

  function firstUploadDocuments() {
    const sorted = [...state.documents].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
    const seen = new Set();
    return sorted.filter((doc) => {
      const key = `${doc.subject}::${doc.document_kind || "做题本"}::${doc.title || doc.filename}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function dashboardDocuments() {
    return firstUploadDocuments().filter((doc) => documentKind(doc) !== "模拟卷");
  }

  async function loadDashboardData() {
    const docs = dashboardDocuments().filter((doc) => !state.dashboardSubject || doc.subject === state.dashboardSubject);
    if (state.dashboardDocumentId && !docs.some((doc) => doc.id === state.dashboardDocumentId)) {
      state.dashboardDocumentId = "";
    }
    const params = new URLSearchParams();
    if (state.dashboardSubject) params.set("subject", state.dashboardSubject);
    if (state.dashboardDocumentId) params.set("document_id", state.dashboardDocumentId);
    const data = await api(`/api/questions?${params}`);
    state.dashboardQuestions = data.questions;
    state.dashboardStats = data.stats;
    state.dashboardSubjectStats = data.subject_stats;
    renderDashboardFilters();
    renderDashboard();
  }

  function renderDashboardFilters() {
    const subjectFilter = $("#dashboardSubjectFilter");
    const documentFilter = $("#dashboardDocumentFilter");
    if (!subjectFilter || !documentFilter) return;
    subjectFilter.innerHTML = `<option value="">请选择科目</option>${state.subjects
      .map((subject) => `<option ${subject === state.dashboardSubject ? "selected" : ""}>${escapeHtml(subject)}</option>`)
      .join("")}`;
    const docs = dashboardDocuments().filter((doc) => !state.dashboardSubject || doc.subject === state.dashboardSubject);
    documentFilter.innerHTML = `<option value="">请选择做题本</option>${docs
      .map((doc) => `<option value="${escapeAttr(doc.id)}" ${doc.id === state.dashboardDocumentId ? "selected" : ""}>${escapeHtml(documentLabel(doc))}</option>`)
      .join("")}`;
  }

  function renderDashboard() {
    const dashboardReady = Boolean(state.dashboardSubject && state.dashboardDocumentId);
    const source = dashboardReady ? state.dashboardQuestions : [];
    const stats = dashboardReady ? state.dashboardStats : [];
    const total = source.length;
    const done = source.filter((q) => q.status && q.status !== "未做").length;
    const progress = total ? Math.round((done / total) * 100) : 0;
    const wrong = source.filter((q) => q.status === "做错").length;
    const review = source.filter((q) => ["需复习", "半会"].includes(q.status)).length;
    const weak = [...stats].sort((a, b) => (b.wrong || 0) - (a.wrong || 0))[0];

    $("#totalCount").textContent = total;
    if ($("#doneCount")) $("#doneCount").textContent = done;
    if ($("#progressRate")) $("#progressRate").textContent = `${progress}%`;
    if ($("#wrongCount")) $("#wrongCount").textContent = wrong;
    if ($("#reviewCount")) $("#reviewCount").textContent = review;
    if ($("#weakCategory")) {
      $("#weakCategory").textContent = dashboardReady ? (weak && weak.wrong ? weak.category : "暂无") : "请选择科目";
    }

    renderStats("#statsList", stats, "category", "选择科目和做题本后会显示对应知识点分布。");
    renderStats(
      "#subjectStatsList",
      dashboardReady ? state.dashboardSubjectStats : [],
      "subject",
      "选择科目和做题本后会显示科目分布。"
    );
  }

  function renderStats(target, stats, labelKey, emptyText) {
    const node = $(target);
    if (!node) return;
    const max = Math.max(...stats.map((item) => item.total), 1);
    node.innerHTML =
      stats
        .map(
          (item) => `
        <div class="stat-row">
          <strong>${escapeHtml(item[labelKey])}</strong>
          <div class="bar"><span style="width: ${(item.total / max) * 100}%"></span></div>
          <span>${item.total} 题</span>
        </div>`
        )
        .join("") || `<p>${escapeHtml(emptyText)}</p>`;
  }

  function bindDashboard() {
    if (isBound) return;
    isBound = true;
    on("#dashboardSubjectFilter", "change", async (event) => {
      state.dashboardSubject = event.target.value;
      const docs = dashboardDocuments().filter((doc) => !state.dashboardSubject || doc.subject === state.dashboardSubject);
      if (state.dashboardDocumentId && !docs.some((doc) => doc.id === state.dashboardDocumentId)) {
        state.dashboardDocumentId = "";
      }
      await loadDashboardData();
    });
    on("#dashboardDocumentFilter", "change", async (event) => {
      state.dashboardDocumentId = event.target.value;
      await loadDashboardData();
    });
  }

  window.loadDashboardData = loadDashboardData;
  window.SakuraDashboard = {
    load: loadDashboardData,
    render: renderDashboard,
    renderFilters: renderDashboardFilters,
    documents: dashboardDocuments,
    bind: bindDashboard,
  };

  bindDashboard();
  renderDashboardFilters();
  renderDashboard();
})();
