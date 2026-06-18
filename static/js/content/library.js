(function () {
  let isBound = false;
  let showStandaloneMockArchive = false;

  function hasActiveLibraryFilter() {
    return Boolean(state.category || state.status || state.documentId || state.subject || state.chapter || (canSearchLibrary() && state.search));
  }

  function canSearchLibrary() {
    return Boolean(state.documentId || state.subject || state.status);
  }

  async function loadQuestions(options = {}) {
    showStandaloneMockArchive = Boolean(options.standaloneMockArchive);
    const loadMockArchive = async () => {
      const data = await api("/api/questions?document_kind=%E6%A8%A1%E6%8B%9F%E5%8D%B7");
      state.mockQuestions = data.questions || [];
    };
    if (state.view === "library" && !hasActiveLibraryFilter() && !showStandaloneMockArchive) {
      state.questions = [];
      state.mockQuestions = [];
      state.stats = {};
      state.subjectStats = {};
      state.categories = [];
      state.chapters = [];
      renderAll();
      return;
    }
    if (state.view === "library" && !hasActiveLibraryFilter() && showStandaloneMockArchive) {
      await loadMockArchive();
      state.questions = [];
      state.stats = {};
      state.subjectStats = {};
      state.categories = [];
      state.chapters = [];
      renderAll();
      return;
    }
    const params = new URLSearchParams();
    if (state.category) params.set("category", state.category);
    if (state.status) params.set("status", state.status);
    if (state.documentId) params.set("document_id", state.documentId);
    if (state.subject) params.set("subject", state.subject);
    if (state.chapter) params.set("chapter", state.chapter);
    if (state.search) params.set("search", state.search);
    const data = await api(`/api/questions?${params}`);
    state.questions = data.questions;
    state.stats = data.stats;
    state.subjectStats = data.subject_stats;
    state.categories = data.categories;
    state.chapters = data.chapters;
    state.subjects = data.subjects;
    state.mockQuestions = state.view === "library" ? state.questions.filter((q) => questionKind(q) === "模拟卷") : [];
    if (state.view === "mockPapers") state.mockQuestions = state.questions.filter((q) => questionKind(q) === "模拟卷");
    renderAll();
  }

  function renderAll() {
    renderQuestionFilters();
    if (window.SakuraDashboard) window.SakuraDashboard.render();
    const regularQuestions = state.questions.filter((q) => questionKind(q) !== "模拟卷");
    const mockQuestions = state.mockQuestions || state.questions.filter((q) => questionKind(q) === "模拟卷");
    $("#questionCountBadge").textContent = `${regularQuestions.length} 题`;
    $("#mockCountBadge").textContent = `${mockQuestions.length} 题`;
    const libraryEmptyText = hasActiveLibraryFilter()
      ? "当前筛选下没有题目。可以换一个科目、资料或清空筛选条件。"
      : "请先选择科目、资料或掌握状态后查看题目。";
    const mockEmptyText = hasActiveLibraryFilter() || showStandaloneMockArchive
      ? "还没有模拟卷题目。先上传整卷 PDF。"
      : "请先选择科目、资料或掌握状态后查看套卷题目。";
    renderQuestionGrid("#questionGrid", regularQuestions, libraryEmptyText);
    renderQuestionGrid("#mockQuestionGrid", mockQuestions, mockEmptyText);
    if (state.view === "mistakes") renderMistakeGrid();
  }

  function renderQuestionFilters() {
    const docs = state.documents.filter((doc) => !state.subject || doc.subject === state.subject);
    const scopedReady = Boolean(state.subject || state.documentId);
    updateSearchBoxState();
    $("#documentFilter").innerHTML = `<option value="">请选择资料</option>${docs
      .map((doc) => `<option value="${escapeAttr(doc.id)}" ${doc.id === state.documentId ? "selected" : ""}>${escapeHtml(documentLabel(doc))}</option>`)
      .join("")}`;
    $("#subjectFilter").innerHTML = `<option value="">请选择科目</option>${state.subjects
      .map((subject) => `<option value="${escapeAttr(subject)}" ${subject === state.subject ? "selected" : ""}>${escapeHtml(subject)}</option>`)
      .join("")}`;
    if (scopedReady) {
      unlockSelect("#categoryFilter");
      unlockSelect("#chapterFilter");
      $("#categoryFilter").innerHTML = `<option value="">全部知识点</option>${state.categories
        .map((category) => `<option value="${escapeAttr(category)}" ${category === state.category ? "selected" : ""}>${escapeHtml(category)}</option>`)
        .join("")}`;
      $("#chapterFilter").innerHTML = `<option value="">全部章节</option>${state.chapters
        .map((chapter) => `<option value="${escapeAttr(chapter)}" ${chapter === state.chapter ? "selected" : ""}>${escapeHtml(chapter)}</option>`)
        .join("")}`;
    } else {
      state.category = "";
      state.chapter = "";
      setSelectLocked("#categoryFilter", "请先选择科目或资料");
      setSelectLocked("#chapterFilter", "请先选择科目或资料");
    }
    const statusEmptyOption = $("#statusFilter option[value='']");
    if (statusEmptyOption) statusEmptyOption.textContent = "请选择掌握状态";
    $("#statusFilter").value = state.status;
  }

  function updateSearchBoxState() {
    const input = $("#searchInput");
    if (!input) return;
    const enabled = state.view === "library" && canSearchLibrary();
    input.disabled = !enabled;
    input.placeholder = enabled ? "在当前范围内搜题号、章节、错因或备注..." : "先选科目或资料后，在当前范围内搜索...";
    if (!enabled && state.search) {
      state.search = "";
      input.value = "";
    }
  }

  function renderQuestionGrid(target, questions, emptyText = "还没有题目。先从左侧上传 PDF，或清空筛选条件。", options = {}) {
    $(target).innerHTML =
      questions.length
        ? questions
            .map(
              (q) => `
          <article class="question-card ${options.selectable ? "selectable-question" : ""}" id="qcard-${escapeAttr(q.id)}">
            ${options.selectable ? `
            <label class="question-select">
              <input type="checkbox" data-select-mistake="${escapeAttr(q.id)}" ${state.selectedMistakes.has(q.id) ? "checked" : ""} />
              <span></span>
            </label>` : ""}
            <div class="thumb" data-open="${escapeAttr(q.id)}">
              <img src="${escapeAttr(q.image_url)}" alt="第 ${escapeAttr(q.page_number)} 页题目" loading="lazy" />
            </div>
            <div class="card-body">
              <div class="meta">
                <span><b class="qno">第${escapeHtml(q.seq_no || q.page_number)}题</b> · ${escapeHtml(q.document_title || q.filename || "做题本")}${q.question_no ? ` · 原题${escapeHtml(q.question_no)}` : ""}</span>
                <span class="tag status ${statusClass(q.status)}">${escapeHtml(q.status)}</span>
              </div>
              <strong>${escapeHtml(q.category)}</strong>
              <span class="tag">${escapeHtml(q.subject || "未分类")} · ${escapeHtml(q.chapter || "未识别章节")}</span>
              <span class="tag kind ${questionKind(q) === "模拟卷" ? "mock" : "paper"}">${escapeHtml(questionKind(q))}</span>
              ${reviewTag(q)}
              <p class="snippet">${escapeHtml(snippet(q.ocr_text))}</p>
              <div class="actions">
                <button data-status="做对" data-id="${escapeAttr(q.id)}">做对</button>
                <button data-status="做错" data-id="${escapeAttr(q.id)}">做错</button>
                <button class="danger" data-delete-question="${escapeAttr(q.id)}">删除</button>
              </div>
            </div>
          </article>`
            )
            .join("")
        : `<p class="empty-note">${escapeHtml(emptyText)}</p>`;
  }

  async function updateQuestion(id, payload) {
    try {
      await api(`/api/questions/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) });
      await refresh();
    } catch (error) {
      // The alert already informs the user; don't re-throw — the callers (e.g. the body click
      // handler in app.js) don't await this, so re-throwing only surfaces an unhandled rejection.
      alert(error.message);
    }
  }

  async function deleteQuestion(id) {
    if (!confirm("确定删除这道题吗？这个操作会移除题目记录和对应页面图片。")) return;
    const result = await api(`/api/questions/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (result.document_deleted && result.document_id) {
      if (state.documentId === result.document_id) {
        state.documentId = "";
        state.category = "";
        state.chapter = "";
      }
      if (state.dashboardDocumentId === result.document_id) {
        state.dashboardDocumentId = "";
      }
    }
    await refresh();
  }

  async function gotoLibraryFilter(filter) {
    state.status = filter.status || "";
    state.category = filter.category || "";
    state.subject = filter.subject || "";
    state.chapter = "";
    state.documentId = "";
    setView("library");
    if ($("#statusFilter")) $("#statusFilter").value = state.status;
    if ($("#subjectFilter")) $("#subjectFilter").value = state.subject;
    if ($("#categoryFilter")) $("#categoryFilter").value = state.category;
    await loadQuestions();
  }

  function locateQuestionByNo(raw) {
    const hint = $("#locateHint");
    const value = String(raw || "").trim().replace(/^0+/, "");
    if (!value) { if (hint) hint.textContent = ""; return; }
    let matches = (state.questions || []).filter((q) => String(q.seq_no || "") === value);
    let byPrinted = false;
    if (!matches.length) {
      matches = (state.questions || []).filter((q) => String(q.question_no || "") === value);
      byPrinted = matches.length > 0;
    }
    if (!matches.length) {
      if (hint) hint.textContent = `当前筛选下没有第 ${value} 题`;
      return;
    }
    const target = matches[0];
    const card = document.getElementById(`qcard-${target.id}`);
    if (card) {
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      card.classList.remove("qcard-flash");
      void card.offsetWidth;
      card.classList.add("qcard-flash");
    }
    if (hint) hint.textContent = byPrinted ? "按原书题号定位" : (matches.length > 1 ? `共 ${matches.length} 题命中，已定位第一题` : "");
  }

  async function showAllQuestions() {
    showStandaloneMockArchive = false;
    state.documentId = "";
    state.subject = "";
    state.category = "";
    state.chapter = "";
    state.status = "";
    state.search = "";
    $("#searchInput").value = "";
    clearTimeout(window.searchTimer);
    setView("library");
    await loadQuestions();
  }

  async function showMockQuestions() {
    state.documentId = "";
    state.subject = "";
    state.category = "";
    state.chapter = "";
    state.status = "";
    state.search = "";
    $("#searchInput").value = "";
    clearTimeout(window.searchTimer);
    setView("library");
    await loadQuestions({ standaloneMockArchive: true });
    $("#mockQuestionGrid").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function bindLibrary() {
    if (isBound) return;
    isBound = true;

    on("#documentFilter", "change", async (event) => {
      showStandaloneMockArchive = false;
      state.documentId = event.target.value;
      const doc = state.documents.find((item) => item.id === state.documentId);
      if (doc) state.subject = doc.subject || state.subject;
      state.category = "";
      state.chapter = "";
      await loadQuestions();
    });

    on("#subjectFilter", "change", async (event) => {
      showStandaloneMockArchive = false;
      state.subject = event.target.value;
      const docs = state.documents.filter((doc) => !state.subject || doc.subject === state.subject);
      if (state.documentId && !docs.some((doc) => doc.id === state.documentId)) {
        state.documentId = "";
      }
      state.category = "";
      state.chapter = "";
      await loadQuestions();
    });

    on("#categoryFilter", "change", async (event) => {
      showStandaloneMockArchive = false;
      state.category = event.target.value;
      state.chapter = "";
      await loadQuestions();
    });

    on("#chapterFilter", "change", async (event) => {
      showStandaloneMockArchive = false;
      state.chapter = event.target.value;
      await loadQuestions();
    });

    on("#statusFilter", "change", async (event) => {
      showStandaloneMockArchive = false;
      state.status = event.target.value;
      await loadQuestions();
    });

    on("#searchInput", "input", async (event) => {
      if (event.target.disabled) return;
      showStandaloneMockArchive = false;
      state.search = event.target.value.trim();
      clearTimeout(window.searchTimer);
      window.searchTimer = setTimeout(loadQuestions, 250);
    });

    on("#questionLocate", "keydown", (event) => {
      if (event.key === "Enter") locateQuestionByNo(event.target.value);
    });

    on("#questionLocate", "input", (event) => {
      clearTimeout(window.locateTimer);
      window.locateTimer = setTimeout(() => locateQuestionByNo(event.target.value), 350);
    });

    on("#showAllQuestions", "click", showAllQuestions);
    on("#showMockQuestions", "click", showMockQuestions);
  }

  window.loadQuestions = loadQuestions;
  window.hasActiveLibraryFilter = hasActiveLibraryFilter;
  window.canSearchLibrary = canSearchLibrary;
  window.renderAll = renderAll;
  window.renderQuestionGrid = renderQuestionGrid;
  window.updateQuestion = updateQuestion;
  window.deleteQuestion = deleteQuestion;
  window.gotoLibraryFilter = gotoLibraryFilter;
  window.updateSearchBoxState = updateSearchBoxState;
  window.SakuraLibrary = {
    load: loadQuestions,
    render: renderAll,
    renderGrid: renderQuestionGrid,
    update: updateQuestion,
    deleteQuestion,
    gotoFilter: gotoLibraryFilter,
    hasActiveFilter: hasActiveLibraryFilter,
    canSearch: canSearchLibrary,
    updateSearchBoxState,
    bind: bindLibrary,
  };

  bindLibrary();
  updateSearchBoxState();
})();
