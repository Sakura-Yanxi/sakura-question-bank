(function () {
  let isBound = false;

  function hasActiveMistakeFilter() {
    return Boolean(state.mistakeDocumentId || state.mistakeSubject || state.mistakeCategory || state.mistakeChapter);
  }

  async function loadMistakes() {
    if (!hasActiveMistakeFilter()) {
      state.mistakeQuestions = [];
      state.mistakeCategories = [];
      state.mistakeChapters = [];
      state.mistakeSubjects = [];
      state.selectedMistakes.clear();
      renderMistakeFilters();
      renderMistakeGrid();
      return;
    }
    const params = new URLSearchParams();
    if (state.mistakeCategory) params.set("category", state.mistakeCategory);
    if (state.mistakeDocumentId) params.set("document_id", state.mistakeDocumentId);
    if (state.mistakeSubject) params.set("subject", state.mistakeSubject);
    if (state.mistakeChapter) params.set("chapter", state.mistakeChapter);
    const data = await api(`/api/questions?${params}`);
    state.mistakeQuestions = data.questions.filter(isActiveMistake).filter((q) => {
      if (state.mistakeStatus === "做错") return q.status === "做错";
      if (state.mistakeStatus === "review") return ["需复习", "半会"].includes(q.status) || (q.ever_wrong && !q.mastered_at);
      return true;
    });
    state.mistakeCategories = data.categories;
    state.mistakeChapters = data.chapters;
    state.mistakeSubjects = data.subjects;
    const visibleIds = new Set(state.mistakeQuestions.map((q) => q.id));
    state.selectedMistakes = new Set([...state.selectedMistakes].filter((id) => visibleIds.has(id)));
    renderMistakeFilters();
    renderMistakeGrid();
  }

  function renderMistakeFilters() {
    const doc = state.documents.find((item) => item.id === state.mistakeDocumentId);
    if (state.mistakeDocumentId && !doc) {
      state.mistakeDocumentId = "";
      if (state.mistakeSubjectAuto) {
        state.mistakeSubject = "";
        state.mistakeSubjectAuto = false;
      }
    }
    if (doc?.subject && !state.mistakeSubject) {
      state.mistakeSubject = doc.subject;
      state.mistakeSubjectAuto = true;
    }
    const docs = state.documents.filter((item) => !state.mistakeSubject || state.mistakeSubjectAuto || item.subject === state.mistakeSubject);
    const subjects = state.mistakeSubjects.length ? state.mistakeSubjects : state.subjects;
    const scopedReady = Boolean(state.mistakeSubject && state.mistakeDocumentId);
    $("#mistakeDocumentFilter").innerHTML = `<option value="">请选择资料</option>${docs
      .map((doc) => `<option value="${escapeAttr(doc.id)}" ${doc.id === state.mistakeDocumentId ? "selected" : ""}>${escapeHtml(documentLabel(doc))}</option>`)
      .join("")}`;
    $("#mistakeSubjectFilter").innerHTML = `<option value="">请选择科目</option>${subjects
      .map((subject) => `<option value="${escapeAttr(subject)}" ${subject === state.mistakeSubject ? "selected" : ""}>${escapeHtml(subject)}</option>`)
      .join("")}`;
    if (scopedReady) {
      unlockSelect("#mistakeCategoryFilter");
      unlockSelect("#mistakeChapterFilter");
      $("#mistakeCategoryFilter").innerHTML = `<option value="">全部知识点</option>${state.mistakeCategories
        .map((category) => `<option value="${escapeAttr(category)}" ${category === state.mistakeCategory ? "selected" : ""}>${escapeHtml(category)}</option>`)
        .join("")}`;
      $("#mistakeChapterFilter").innerHTML = `<option value="">全部章节</option>${state.mistakeChapters
        .map((chapter) => `<option value="${escapeAttr(chapter)}" ${chapter === state.mistakeChapter ? "selected" : ""}>${escapeHtml(chapter)}</option>`)
        .join("")}`;
    } else {
      state.mistakeCategory = "";
      state.mistakeChapter = "";
      setSelectLocked("#mistakeCategoryFilter", "请先选择科目和资料");
      setSelectLocked("#mistakeChapterFilter", "请先选择科目和资料");
    }
  }

  function renderMistakeGrid() {
    $("#mistakeCountBadge").textContent = `${state.mistakeQuestions.length} 题`;
    const emptyText = hasActiveMistakeFilter()
      ? "当前筛选范围没有错题。"
      : "请先选择科目或资料，再按知识点、章节或错题状态导出。";
    renderQuestionGrid("#mistakeGrid", state.mistakeQuestions, emptyText, { selectable: true });
    renderMistakeSelectionHint();
  }

  function renderMistakeSelectionHint() {
    const selected = state.selectedMistakes.size;
    const total = state.mistakeQuestions.length;
    $("#focusWrong").classList.toggle("filter-active", state.mistakeStatus === "做错");
    $("#focusReview").classList.toggle("filter-active", state.mistakeStatus === "review");
    if (!hasActiveMistakeFilter()) {
      $("#mistakeSelectHint").textContent = "先选择科目或资料后再导出";
      return;
    }
    $("#mistakeSelectHint").textContent = selected ? `已选择 ${selected}/${total} 题` : `未勾选时导出当前 ${total} 道错题`;
  }

  function bindMistakes() {
    if (isBound) return;
    isBound = true;
    on("#mistakeDocumentFilter", "change", async (event) => {
      state.mistakeDocumentId = event.target.value;
      const doc = state.documents.find((item) => item.id === state.mistakeDocumentId);
      if (doc) {
        state.mistakeSubject = doc.subject || "";
        state.mistakeSubjectAuto = true;
      } else if (state.mistakeSubjectAuto) {
        state.mistakeSubject = "";
        state.mistakeSubjectAuto = false;
      }
      state.mistakeCategory = "";
      state.mistakeChapter = "";
      await loadMistakes();
    });

    on("#mistakeSubjectFilter", "change", async (event) => {
      state.mistakeSubject = event.target.value;
      state.mistakeSubjectAuto = false;
      const docs = state.documents.filter((doc) => !state.mistakeSubject || doc.subject === state.mistakeSubject);
      if (state.mistakeDocumentId && !docs.some((doc) => doc.id === state.mistakeDocumentId)) {
        state.mistakeDocumentId = "";
      }
      state.mistakeCategory = "";
      state.mistakeChapter = "";
      await loadMistakes();
    });

    on("#mistakeCategoryFilter", "change", async (event) => {
      state.mistakeCategory = event.target.value;
      state.mistakeChapter = "";
      await loadMistakes();
    });

    on("#mistakeChapterFilter", "change", async (event) => {
      state.mistakeChapter = event.target.value;
      await loadMistakes();
    });

    on("#focusWrong", "click", async () => {
      state.mistakeStatus = state.mistakeStatus === "做错" ? "" : "做错";
      await loadMistakes();
    });

    on("#focusReview", "click", async () => {
      state.mistakeStatus = state.mistakeStatus === "review" ? "" : "review";
      await loadMistakes();
    });
  }

  window.loadMistakes = loadMistakes;
  window.hasActiveMistakeFilter = hasActiveMistakeFilter;
  window.renderMistakeGrid = renderMistakeGrid;
  window.renderMistakeSelectionHint = renderMistakeSelectionHint;
  window.SakuraMistakes = {
    load: loadMistakes,
    hasActiveFilter: hasActiveMistakeFilter,
    renderFilters: renderMistakeFilters,
    renderGrid: renderMistakeGrid,
    renderSelectionHint: renderMistakeSelectionHint,
    bind: bindMistakes,
  };

  bindMistakes();
  renderMistakeFilters();
  renderMistakeGrid();
})();
