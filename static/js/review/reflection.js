(function () {
  let isBound = false;

  async function loadReflectionPreview() {
    const period = $("#reflectionPeriod")?.value || "week";
    const data = await api(`/api/reflection?period=${period}`);
    renderReflectionSummary(data);
  }

  function renderReflectionSummary(data) {
    const total = Number(data.total || 0);
    if (!total) {
      $("#reflectionSummary").innerHTML = '<p class="empty-note">本周期还没有做题记录。先开始做题，再来做周期反思复盘。</p>';
      $("#reflectionSubjectSummary").innerHTML = '<p class="empty-note">导入题目不会计入统计，只有做对、做错、半会或需复习后才会进入这里。</p>';
      renderAiOutput("#reflectionOutput", "本周期暂无可复盘内容。");
      return;
    }
    $("#reflectionSummary").innerHTML = `
      <div class="summary-pill"><span>周期</span><strong>${data.period === "month" ? "本月" : "本周"}</strong></div>
      <div class="summary-pill"><span>完成/复盘</span><strong>${data.total}</strong></div>
      <div class="summary-pill"><span>做对</span><strong>${data.correct}</strong></div>
      <div class="summary-pill"><span>做错</span><strong>${data.wrong}</strong></div>
      <div class="summary-pill"><span>需复习</span><strong>${data.review}</strong></div>`;
    $("#reflectionSubjectSummary").innerHTML =
      (data.subjects || [])
        .map((item) => {
          const done = item.total || 0;
          const correctRate = done ? Math.round(((item.correct || 0) / done) * 100) : 0;
          return `
          <article class="subject-reflection-card">
            <div>
              <span>科目</span>
              <strong>${escapeHtml(item.subject)}</strong>
            </div>
            <div class="subject-reflection-grid">
              <span>做题 ${item.total || 0}</span>
              <span>做对 ${item.correct || 0}</span>
              <span>做错 ${item.wrong || 0}</span>
              <span>需复习 ${item.review || 0}</span>
            </div>
            <div class="mini-rate"><span style="width: ${correctRate}%"></span></div>
            <small>正确率 ${correctRate}%</small>
          </article>`;
        })
        .join("") || `<p class="empty-note">本周期还没有已标记的做题记录。导入题目不会计入这里，只有标记做对、做错、半会或需复习后才会统计。</p>`;
  }

  async function generateReflection() {
    const period = $("#reflectionPeriod")?.value || "week";
    renderAiOutput("#reflectionOutput", "正在生成总结与反思...");
    const data = await api("/api/reflection", {
      method: "POST",
      body: JSON.stringify({ period }),
    });
    renderReflectionSummary(data.summary);
    renderAiOutput("#reflectionOutput", data.reflection || "没有生成到反思内容。");
    await loadReflectionHistory();
  }

  async function loadReflectionHistory() {
    try {
      const data = await api("/api/reflections");
      const list = data.reflections || [];
      if (!list.length) {
        $("#historyList").innerHTML = '<p class="empty-note">暂无历史反思记录。</p>';
        return;
      }
      $("#historyList").innerHTML = list.map((ref) => {
        const periodLabel = ref.period === "week" ? "周" : "月";
        const dateLabel = `${ref.period_start} ~ ${ref.period_end}`;
        const preview = (ref.reflection_text || "").slice(0, 120);
        return `
          <div class="history-item">
            <div class="history-meta">
              <strong>${periodLabel}总结</strong>
              <span>${escapeHtml(dateLabel)}</span>
              <small>${escapeHtml((ref.created_at || "").slice(0, 16))}</small>
            </div>
            <p class="history-preview">${escapeHtml(preview)}${preview.length >= 120 ? "..." : ""}</p>
            <div class="history-actions">
              <button class="ghost" data-download-reflection="${escapeAttr(ref.id)}">下载 TXT</button>
              <button class="danger" data-delete-reflection="${escapeAttr(ref.id)}">删除</button>
            </div>
          </div>`;
      }).join("");
    } catch (e) {
      $("#historyList").innerHTML = '<p class="empty-note">加载历史失败。</p>';
    }
  }

  function downloadReflection(refId) {
    const a = document.createElement("a");
    a.href = `/api/reflections/${encodeURIComponent(refId)}/download`;
    a.download = "";
    a.click();
  }

  async function deleteReflection(refId) {
    if (!confirm("确定删除这条历史记录吗？")) return;
    await api(`/api/reflections/${encodeURIComponent(refId)}`, { method: "DELETE" });
    await loadReflectionHistory();
  }

  async function loadReflectionPanel() {
    await loadReflectionPreview();
    await loadReflectionHistory();
  }

  function bindReflectionPanel() {
    if (isBound) return;
    isBound = true;
    on("#reflectionPeriod", "change", loadReflectionPreview);
    on("#generateReflection", "click", generateReflection);
    on("#loadReflectionHistory", "click", loadReflectionHistory);
    on("#historyList", "click", async (event) => {
      const downloadBtn = event.target.closest("[data-download-reflection]");
      if (downloadBtn) {
        downloadReflection(downloadBtn.dataset.downloadReflection);
        return;
      }
      const deleteBtn = event.target.closest("[data-delete-reflection]");
      if (deleteBtn) await deleteReflection(deleteBtn.dataset.deleteReflection);
    });
  }

  window.SakuraReflection = {
    load: loadReflectionPanel,
    preview: loadReflectionPreview,
    history: loadReflectionHistory,
    generate: generateReflection,
    bind: bindReflectionPanel,
  };

  bindReflectionPanel();
})();
