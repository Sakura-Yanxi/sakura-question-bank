(function () {
  let isBound = false;

  async function loadChapterStats(documentId) {
    const explicitDoc = documentId ? state.documents.find((doc) => doc.id === documentId) : null;
    if (explicitDoc && documentKind(explicitDoc) === "模拟卷") {
      $("#chapterStatsGrid").innerHTML = "<p>章节统计仅支持做题本，模拟卷请到题库或模拟卷页面查看。</p>";
      return;
    }
    const id =
      documentId ||
      $("#statsDocumentSelect").value ||
      state.documents.find((doc) => documentKind(doc) !== "模拟卷")?.id;
    if (!id) {
      $("#chapterStatsGrid").innerHTML = "<p>还没有做题本。先上传 PDF。</p>";
      return;
    }
    $("#statsDocumentSelect").value = id;
    const data = await api(`/api/documents/${id}/chapter-stats`);
    $("#chapterStatsGrid").innerHTML =
      `<article class="chapter-card radar-card">
        <h3>错因雷达图</h3>
        ${renderRadar(data.meta_tags || [])}
      </article>` +
      data.chapters
        .map((chapter) => {
          const deg = Math.round((chapter.correct_rate / 100) * 360);
          return `
          <article class="chapter-card">
            <h3>${escapeHtml(chapter.chapter)}</h3>
            <div class="pie" data-label="${chapter.correct_rate}%" style="background: conic-gradient(var(--accent) 0deg ${deg}deg, var(--accent-2) ${deg}deg 360deg)"></div>
            <div class="legend">
              <span>共 ${chapter.total} 题</span>
              <span>做对 ${chapter.correct || 0} · 做错 ${chapter.wrong || 0}</span>
              <span>需复习 ${chapter.review || 0} · 未做 ${chapter.todo || 0}</span>
            </div>
          </article>`;
        })
        .join("") || "<p>这套做题本还没有章节数据。</p>";
    typesetMath($("#chapterStatsGrid"));
  }

  function renderRadar(items) {
    const size = 260;
    const center = size / 2;
    const radius = 80;
    const source = items.length ? items : [{ tag: "暂无错因", count: 0, ratio: 0 }];
    const points = source.map((item, index) => {
      const angle = -Math.PI / 2 + (index * 2 * Math.PI) / source.length;
      const value = item.ratio || 0;
      let anchor = "middle";
      if (Math.cos(angle) < -0.1) anchor = "end";
      if (Math.cos(angle) > 0.1) anchor = "start";
      let dy = "0.3em";
      if (Math.sin(angle) < -0.1) dy = "-0.5em";
      if (Math.sin(angle) > 0.1) dy = "1em";
      return {
        ...item,
        x: center + Math.cos(angle) * radius * value,
        y: center + Math.sin(angle) * radius * value,
        ax: center + Math.cos(angle) * radius,
        ay: center + Math.sin(angle) * radius,
        lx: center + Math.cos(angle) * (radius + 15),
        ly: center + Math.sin(angle) * (radius + 15),
        anchor,
        dy,
      };
    });
    const polygon = points.map((p) => `${p.x},${p.y}`).join(" ");
    return `
      <svg class="radar" viewBox="0 0 ${size} ${size}" role="img" aria-label="错因雷达图">
        <polygon class="radar-grid" points="${points.map((p) => `${p.ax},${p.ay}`).join(" ")}"></polygon>
        ${points.map((p) => `<line class="radar-axis" x1="${center}" y1="${center}" x2="${p.ax}" y2="${p.ay}"></line>`).join("")}
        <polygon class="radar-area" points="${polygon}"></polygon>
        ${points.map((p) => `<text x="${p.lx}" y="${p.ly}" text-anchor="${p.anchor}" dy="${p.dy}">${escapeHtml(p.tag)} ${p.count}</text>`).join("")}
      </svg>`;
  }

  function bindChapterStats() {
    if (isBound) return;
    isBound = true;
    on("#statsDocumentSelect", "change", async (event) => {
      await loadChapterStats(event.target.value);
    });
  }

  window.SakuraChapterStats = {
    load: loadChapterStats,
    renderRadar,
    bind: bindChapterStats,
  };

  bindChapterStats();
})();
