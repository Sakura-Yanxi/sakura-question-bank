(function () {
  let isBound = false;
  let isExporting = false;

  function isIOSLikeDevice() {
    const ua = navigator.userAgent || "";
    return /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  }

  function currentSelectValue(selector, fallback = "") {
    const el = $(selector);
    return el ? el.value : fallback;
  }

  function syncMistakeFiltersForExport() {
    if (window.SakuraMistakes?.syncFiltersFromControls) {
      window.SakuraMistakes.syncFiltersFromControls();
      return;
    }
    state.mistakeDocumentId = currentSelectValue("#mistakeDocumentFilter", state.mistakeDocumentId);
    state.mistakeSubject = currentSelectValue("#mistakeSubjectFilter", state.mistakeSubject);
    state.mistakeCategory = currentSelectValue("#mistakeCategoryFilter", state.mistakeCategory);
  }

  function selectedMistakeChaptersForExport() {
    if (window.SakuraMistakes?.selectedChapters) return window.SakuraMistakes.selectedChapters();
    if (Array.isArray(state.mistakeChaptersSelected)) return state.mistakeChaptersSelected.filter(Boolean);
    return state.mistakeChapter ? [state.mistakeChapter] : [];
  }

  function visibleMistakeIds() {
    return (state.mistakeQuestions || []).map((q) => q.id).filter(Boolean);
  }

  function selectedMistakeIdsForExport() {
    if (state.view === "mistakes") return [...state.selectedMistakes].filter(Boolean);
    const visible = new Set(visibleMistakeIds());
    return [...state.selectedMistakes].filter((id) => visible.has(id));
  }

  function applyMistakeFilters(params) {
    syncMistakeFiltersForExport();
    if (state.mistakeDocumentId) params.set("document_id", state.mistakeDocumentId);
    if (state.mistakeSubject) params.set("subject", state.mistakeSubject);
    if (state.mistakeCategory) params.set("category", state.mistakeCategory);
    selectedMistakeChaptersForExport().forEach((chapter) => params.append("chapter", chapter));
    if (state.mistakeStatus === "做错") params.set("status", "做错");
    if (state.mistakeStatus === "review") params.set("status_group", "review");
  }

  function filenameFromDisposition(header) {
    const utf8 = (header.match(/filename\*=UTF-8''([^;]+)/i) || [])[1];
    if (utf8) {
      try {
        return decodeURIComponent(utf8);
      } catch (_error) {
        return utf8;
      }
    }
    return (header.match(/filename="(.+?)"/) || [])[1] || "mistakes.pdf";
  }

  function triggerServerDownload(url) {
    let frame = document.getElementById("sakuraDownloadFrame");
    if (!frame) {
      frame = document.createElement("iframe");
      frame.id = "sakuraDownloadFrame";
      frame.name = "sakuraDownloadFrame";
      frame.style.display = "none";
      document.body.appendChild(frame);
    }
    frame.src = url;
  }

  function canAttemptPdfShare() {
    if (!isIOSLikeDevice() || typeof File === "undefined" || !navigator.share) return false;
    if (!navigator.canShare) return true;
    try {
      const probe = new File([""], "mistakes.pdf", { type: "application/pdf" });
      return navigator.canShare({ files: [probe] });
    } catch (_error) {
      return false;
    }
  }

  async function trySharePdf(blob, name) {
    if (!canAttemptPdfShare()) return false;
    const file = new File([blob], name, { type: "application/pdf" });
    if (navigator.canShare && !navigator.canShare({ files: [file] })) return false;
    try {
      await navigator.share({ files: [file], title: name });
      return true;
    } catch (error) {
      return error?.name === "AbortError";
    }
  }

  function downloadBlob(blob, name) {
    const a = document.createElement("a");
    const url = URL.createObjectURL(blob);
    a.href = url;
    a.download = name;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    // Defer revoke: revoking in the same tick can cancel the in-flight download in some browsers.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function downloadPdf(url) {
    if (isIOSLikeDevice() && !canAttemptPdfShare()) {
      triggerServerDownload(url);
      return;
    }
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "导出失败，请稍后再试。");
      return;
    }
    const blob = await res.blob();
    const name = filenameFromDisposition(res.headers.get("Content-Disposition") || "");
    if (await trySharePdf(blob, name)) return;
    if (isIOSLikeDevice()) {
      triggerServerDownload(url);
      return;
    }
    downloadBlob(blob, name);
  }

  async function exportMistakesPDF({ useFilters = false } = {}) {
    if (isExporting) return;
    if (state.view === "mistakes") syncMistakeFiltersForExport();
    const selectedIds = state.view === "mistakes" ? selectedMistakeIdsForExport() : [];
    if (state.view === "mistakes") {
      if (!selectedIds.length && !hasActiveMistakeFilter()) {
        alert("请先选择科目或资料，再导出对应错题。");
        return;
      }
      if (!selectedIds.length && state.mistakeQuestions.length > 120 && !confirm(`将导出当前筛选下 ${state.mistakeQuestions.length} 道错题，PDF 可能较大。确定继续吗？`)) return;
    } else if (useFilters) {
      const total = (state.questions || []).filter((q) => questionKind(q) !== "模拟卷").length;
      const hasFilter = Boolean(state.documentId || state.subject || state.category || state.chapter || state.status || state.search);
      if (!hasFilter && total > 120 && !confirm(`当前没有筛选条件，将导出 ${total} 道题，PDF 可能较大。确定继续吗？`)) return;
    }
    const params = new URLSearchParams();
    params.set("mistakes_only", "1");
    params.set("download", "1");
    if (selectedIds.length) {
      params.set("ids", selectedIds.join(","));
    } else if (state.view === "mistakes") {
      applyMistakeFilters(params);
    } else if (useFilters) {
      params.set("mistakes_only", "0");
      if (state.documentId) params.set("document_id", state.documentId);
      if (state.subject) params.set("subject", state.subject);
      if (state.category) params.set("category", state.category);
      if (state.chapter) params.set("chapter", state.chapter);
      if (state.status) params.set("status", state.status);
      if (state.search) params.set("search", state.search);
    }
    try {
      isExporting = true;
      setExportBusy(true);
      await downloadPdf(`/api/export/mistakes?${params.toString()}`);
    } catch (error) {
      alert("导出失败：" + error.message);
    } finally {
      isExporting = false;
      setExportBusy(false);
    }
  }

  function setExportBusy(busy) {
    ["#exportMistakes", "#exportLibrary"].forEach((selector) => {
      const button = $(selector);
      if (!button) return;
      button.disabled = busy;
      button.classList.toggle("is-loading", busy);
    });
  }

  function bindMistakeExport() {
    if (isBound) return;
    isBound = true;
    on("#exportMistakes", "click", () => exportMistakesPDF({ useFilters: false }));
    on("#exportLibrary", "click", () => exportMistakesPDF({ useFilters: true }));
    on("#selectAllMistakes", "click", () => {
      state.mistakeQuestions.forEach((q) => state.selectedMistakes.add(q.id));
      renderMistakeGrid();
    });
    on("#clearMistakeSelection", "click", () => {
      state.selectedMistakes.clear();
      renderMistakeGrid();
    });
    on("#mistakeGrid", "change", (event) => {
      const input = event.target.closest("[data-select-mistake]");
      if (!input) return;
      if (input.checked) state.selectedMistakes.add(input.dataset.selectMistake);
      else state.selectedMistakes.delete(input.dataset.selectMistake);
      renderMistakeSelectionHint();
    });
  }

  window.SakuraMistakeExport = {
    exportPdf: exportMistakesPDF,
    bind: bindMistakeExport,
  };

  bindMistakeExport();
})();
