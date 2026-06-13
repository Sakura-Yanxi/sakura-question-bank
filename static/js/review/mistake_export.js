(function () {
  let isBound = false;

  async function exportMistakesPDF({ useFilters = false } = {}) {
    const selectedIds = state.view === "mistakes" ? [...state.selectedMistakes] : [];
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
    if (selectedIds.length) {
      params.set("ids", selectedIds.join(","));
    } else if (state.view === "mistakes") {
      if (state.mistakeDocumentId) params.set("document_id", state.mistakeDocumentId);
      if (state.mistakeSubject) params.set("subject", state.mistakeSubject);
      if (state.mistakeCategory) params.set("category", state.mistakeCategory);
      if (state.mistakeChapter) params.set("chapter", state.mistakeChapter);
      if (state.mistakeStatus === "做错") params.set("status", "做错");
      if (state.mistakeStatus === "review") params.set("status_group", "review");
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
      const res = await fetch(`/api/export/mistakes?${params.toString()}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(err.error || "导出失败，请稍后再试。");
        return;
      }
      const blob = await res.blob();
      const cd = res.headers.get("Content-Disposition") || "";
      const name = (cd.match(/filename="(.+?)"/) || [])[1] || "mistakes.pdf";
      const a = document.createElement("a");
      const url = URL.createObjectURL(blob);
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Defer revoke: revoking in the same tick can cancel the in-flight download in some browsers.
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      alert("导出失败：" + error.message);
    }
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
