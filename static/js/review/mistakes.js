(function () {
  let isBound = false;
  let loadSerial = 0;

  function hasActiveMistakeFilter() {
    return Boolean(state.mistakeDocumentId || state.mistakeSubject || state.mistakeCategory || selectedMistakeChapters().length);
  }

  function currentSelectValue(selector, fallback = "") {
    const el = $(selector);
    return el ? el.value : fallback;
  }

  function setControlValue(selector, value = "") {
    const el = $(selector);
    if (el) el.value = value;
  }

  function selectedMistakeChapters() {
    if (Array.isArray(state.mistakeChaptersSelected)) return state.mistakeChaptersSelected.filter(Boolean);
    return state.mistakeChapter ? [state.mistakeChapter] : [];
  }

  function setSelectedMistakeChapters(chapters = []) {
    state.mistakeChaptersSelected = [...new Set((chapters || []).filter(Boolean))];
    state.mistakeChapter = state.mistakeChaptersSelected[0] || "";
  }

  function syncMistakeFiltersFromControls() {
    state.mistakeDocumentId = currentSelectValue("#mistakeDocumentFilter", state.mistakeDocumentId);
    state.mistakeSubject = currentSelectValue("#mistakeSubjectFilter", state.mistakeSubject);
    state.mistakeCategory = currentSelectValue("#mistakeCategoryFilter", state.mistakeCategory);
  }

  function resetMistakeSelection() {
    state.selectedMistakes.clear();
  }

  function removeSelectedMistakesFromChapter(chapter) {
    if (!chapter || !state.selectedMistakes.size) return;
    state.mistakeQuestions
      .filter((q) => q.chapter === chapter)
      .forEach((q) => state.selectedMistakes.delete(q.id));
  }

  function buildMistakeQueryParams({ includeChapters = true } = {}) {
    const params = new URLSearchParams();
    if (state.mistakeCategory) params.set("category", state.mistakeCategory);
    if (state.mistakeDocumentId) params.set("document_id", state.mistakeDocumentId);
    if (state.mistakeSubject) params.set("subject", state.mistakeSubject);
    if (includeChapters) selectedMistakeChapters().forEach((chapter) => params.append("chapter", chapter));
    if (state.mistakeStatus === "做错") params.set("status", "做错");
    if (state.mistakeStatus === "review") params.set("status_group", "review");
    return params;
  }

  async function loadMistakes() {
    const serial = ++loadSerial;
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
    const params = buildMistakeQueryParams();
    const data = await api(`/api/questions?${params}`);
    if (serial !== loadSerial) return;
    state.mistakeQuestions = data.questions.filter(isVisibleMistake);
    state.mistakeCategories = data.categories;
    state.mistakeChapters = data.chapters;
    state.mistakeSubjects = data.subjects;
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
    const documentFilter = $("#mistakeDocumentFilter");
    const subjectFilter = $("#mistakeSubjectFilter");
    documentFilter.innerHTML = `<option value="">请选择资料</option>${docs
      .map((doc) => `<option value="${escapeAttr(doc.id)}" ${doc.id === state.mistakeDocumentId ? "selected" : ""}>${escapeHtml(documentLabel(doc))}</option>`)
      .join("")}`;
    documentFilter.value = state.mistakeDocumentId || "";
    subjectFilter.innerHTML = `<option value="">请选择科目</option>${subjects
      .map((subject) => `<option value="${escapeAttr(subject)}" ${subject === state.mistakeSubject ? "selected" : ""}>${escapeHtml(subject)}</option>`)
      .join("")}`;
    subjectFilter.value = state.mistakeSubject || "";
    if (scopedReady) {
      unlockSelect("#mistakeCategoryFilter");
      state.mistakeCategory = setSelectOptions("#mistakeCategoryFilter", state.mistakeCategories, "全部知识点", state.mistakeCategory);
      renderMistakeChapterPicker();
    } else {
      state.mistakeCategory = "";
      setSelectedMistakeChapters();
      setSelectLocked("#mistakeCategoryFilter", "请先选择科目和资料");
      renderMistakeChapterPicker(true);
    }
  }

  function renderMistakeChapterPicker(locked = false) {
    const picker = $("#mistakeChapterFilter");
    if (!picker) return;
    if (locked) {
      setSelectLocked("#mistakeChapterFilter", "请先选择科目和资料");
      return;
    }
    unlockSelect("#mistakeChapterFilter");
    const chapters = (state.mistakeChapters || []).filter(Boolean);
    state.mistakeChaptersSelected = selectedMistakeChapters().filter((chapter) => chapters.includes(chapter));
    const selected = new Set(state.mistakeChaptersSelected);
    const label = selected.size ? `已选 ${selected.size} 个章节，点此清空` : "全部章节";
    picker.innerHTML = `<option value="">${escapeHtml(label)}</option>${chapters
      .map((chapter) => {
        const marker = selected.has(chapter) ? "✓ " : "";
        return `<option value="${escapeAttr(chapter)}">${marker}${escapeHtml(chapter)}</option>`;
      })
      .join("")}`;
    picker.value = "";
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
    const visibleSelected = state.mistakeQuestions.filter((q) => state.selectedMistakes.has(q.id)).length;
    $("#focusWrong").classList.toggle("filter-active", state.mistakeStatus === "做错");
    $("#focusReview").classList.toggle("filter-active", state.mistakeStatus === "review");
    if (!hasActiveMistakeFilter()) {
      $("#mistakeSelectHint").textContent = "先选择科目或资料后再导出";
      return;
    }
    const chapterCount = selectedMistakeChapters().length;
    const chapterText = chapterCount ? `已选 ${chapterCount} 个章节，` : "";
    $("#mistakeSelectHint").textContent = selected
      ? `${chapterText}已勾选 ${selected} 道，其中当前显示 ${visibleSelected}/${total} 道`
      : `${chapterText}未勾选时导出当前 ${total} 道错题`;
  }

  function isVisibleMistake(q) {
    if (!isActiveMistake(q)) return false;
    if (state.mistakeStatus === "review") return ["需复习", "半会"].includes(q.status) || (q.ever_wrong && !q.mastered_at && q.status !== "做错");
    return true;
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
      setSelectedMistakeChapters();
      setControlValue("#mistakeCategoryFilter");
      resetMistakeSelection();
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
      setSelectedMistakeChapters();
      setControlValue("#mistakeCategoryFilter");
      resetMistakeSelection();
      await loadMistakes();
    });

    on("#mistakeCategoryFilter", "change", async (event) => {
      state.mistakeCategory = event.target.value;
      setSelectedMistakeChapters();
      resetMistakeSelection();
      await loadMistakes();
    });

    on("#mistakeChapterFilter", "change", async (event) => {
      const chapter = event.target.value;
      if (!chapter) {
        setSelectedMistakeChapters();
        resetMistakeSelection();
      } else {
        const selected = new Set(selectedMistakeChapters());
        if (selected.has(chapter)) {
          selected.delete(chapter);
          removeSelectedMistakesFromChapter(chapter);
        } else {
          selected.add(chapter);
        }
        setSelectedMistakeChapters([...selected]);
      }
      await loadMistakes();
    });

    on("#focusWrong", "click", async () => {
      state.mistakeStatus = state.mistakeStatus === "做错" ? "" : "做错";
      resetMistakeSelection();
      await loadMistakes();
    });

    on("#focusReview", "click", async () => {
      state.mistakeStatus = state.mistakeStatus === "review" ? "" : "review";
      resetMistakeSelection();
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
    syncFiltersFromControls: syncMistakeFiltersFromControls,
    selectedChapters: selectedMistakeChapters,
    resetSelection: resetMistakeSelection,
    bind: bindMistakes,
  };

  bindMistakes();
  renderMistakeFilters();
  renderMistakeGrid();
})();
