(function () {
  const lightboxState = { scale: 1, tx: 0, ty: 0, dragging: false, sx: 0, sy: 0, isBound: false };

  function currentVisibleQuestionIds() {
    const activeView = document.querySelector(".view.active") || document;
    const ids = [...activeView.querySelectorAll("[data-open]")]
      .map((el) => String(el.dataset.open || ""))
      .filter(Boolean);
    return [...new Set(ids)];
  }

  function detailQuestionSource() {
    return state.view === "mistakes" ? state.mistakeQuestions : state.questions;
  }

  function detailNeighbor(id, step) {
    const visibleIds = currentVisibleQuestionIds();
    let ids = visibleIds;
    if (!ids.includes(String(id))) {
      ids = (detailQuestionSource() || []).map((q) => String(q.id));
    }
    const index = ids.indexOf(String(id));
    if (index < 0) return { id: "", index: -1, total: ids.length };
    const nextIndex = index + step;
    return {
      id: ids[nextIndex] || "",
      index,
      total: ids.length,
    };
  }

  function detailPositionText(id) {
    const visibleIds = currentVisibleQuestionIds();
    const sourceIds = (detailQuestionSource() || []).map((q) => String(q.id));
    const ids = visibleIds.includes(String(id)) ? visibleIds : sourceIds;
    const index = ids.indexOf(String(id));
    return index >= 0 && ids.length ? `${index + 1}/${ids.length}` : "";
  }

  function formatReviewNoteDate(value) {
    if (!value) return "未记录日期";
    const normalized = String(value).replace(" ", "T");
    const date = new Date(normalized);
    if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function reviewNoteSourceLabel(source) {
    if (source === "daily") return "每日练习";
    if (source === "legacy") return "旧备注";
    return "题目详情";
  }

  function renderReviewNoteTimeline(notes = []) {
    const list = Array.isArray(notes) ? notes : [];
    if (!list.length) {
      return `<p class="empty-note compact">还没有历史复盘记录。二刷、三刷时写下本次发现，就会按日期留在这里。</p>`;
    }
    return list
      .map((note, index) => {
        const tags = Array.isArray(note.meta_tags) ? note.meta_tags : [];
        const tagHtml = tags.length
          ? `<div class="review-note-tags">${tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div>`
          : "";
        return `
          <details class="review-note-card" ${index === 0 ? "open" : ""}>
            <summary>
              <span class="review-note-date">${escapeHtml(formatReviewNoteDate(note.created_at))}</span>
              <span class="tag status ${statusClass(note.status || "")}">${escapeHtml(note.status || "未标注")}</span>
              <small>${escapeHtml(reviewNoteSourceLabel(note.source || ""))}</small>
            </summary>
            <p>${escapeHtml(note.note || "")}</p>
            ${tagHtml}
          </details>`;
      })
      .join("");
  }

  function readDetailPatch() {
    const tags = selectedMetaTags();
    const note = ($("#userNote")?.value || "").trim();
    const patch = {
      status: $("#detailStatus")?.value || "未做",
      meta_tags: tags,
      mistake_reason: tags.join("、"),
      chapter: $("#detailChapter")?.value || "",
      question_no: $("#detailQuestionNo")?.value?.trim() || "",
    };
    if (note) {
      patch.user_note = note;
      patch.review_note = note;
      patch.append_review_note = true;
      patch.review_note_source = "detail";
    }
    return {
      ...patch,
    };
  }

  function readDetailInsightPatch() {
    const patch = readDetailPatch();
    delete patch.question_no;
    delete patch.user_note;
    delete patch.review_note;
    delete patch.append_review_note;
    delete patch.review_note_source;
    return patch;
  }

  async function persistDetailContext(questionId) {
    await api(`/api/questions/${questionId}`, {
      method: "PATCH",
      body: JSON.stringify(readDetailInsightPatch()),
    });
  }

  function openDetailReading(sourceId, title) {
    const source = document.getElementById(sourceId);
    const layer = $("#detailReadingLayer");
    const content = $("#detailReadingContent");
    const titleNode = $("#detailReadingTitle");
    if (!source || !layer || !content || !titleNode) return;
    titleNode.textContent = title;
    renderAiOutput(content, source.dataset.rawOutput || source.textContent || "", "这里还没有可展开的内容。");
    layer.classList.remove("hidden");
    $("#detailDialog")?.classList.add("reading-mode");
    if (window.lucide) lucide.createIcons();
  }

  function closeDetailReading() {
    $("#detailReadingLayer")?.classList.add("hidden");
    $("#detailDialog")?.classList.remove("reading-mode");
  }

  function isDetailReadingOpen() {
    const layer = $("#detailReadingLayer");
    return Boolean(layer && !layer.classList.contains("hidden"));
  }

  function bindDetailReading() {
    $$("[data-expand-output]").forEach((button) => {
      button.onclick = () => openDetailReading(button.dataset.expandOutput, button.dataset.outputTitle || "解析阅读");
    });
    const close = $("#closeDetailReading");
    if (close) close.onclick = closeDetailReading;
    const layer = $("#detailReadingLayer");
    if (layer) {
      layer.onclick = (event) => {
        if (event.target === layer) closeDetailReading();
      };
    }
  }

  function renderDetail(q, currentStatus, prev, next, positionText) {
    const memoryText = q.ever_wrong
      ? (q.mastered_at ? "已完成多轮复习，标记为已掌握。" : `保持阶段：${q.retention_stage || 1} 天，下次复习：${q.next_review_at || "待安排"}`)
      : "这道题还没有进入错题复习队列。";
    const statuses = ["未做", "做对", "做错", "半会", "需复习"];
    $("#detailContent").innerHTML = `
      <div class="detail">
        <div class="detail-image">
          <div class="crop-toolbar">
            <button class="ghost" id="zoomImage">放大查看</button>
            <button class="ghost" id="enableCrop">裁剪题目边界</button>
            <button id="saveCrop" disabled>保存裁剪</button>
            <span class="detail-position">${escapeHtml(positionText)}</span>
            <button class="ghost detail-nav-btn" id="prevQuestion" ${prev.id ? "" : "disabled"}><i data-lucide="chevron-left"></i>上一题</button>
            <button class="ghost detail-nav-btn next" id="nextQuestion" ${next.id ? "" : "disabled"}>下一题<i data-lucide="chevron-right"></i></button>
          </div>
          <div class="crop-stage" id="cropStage">
            <img id="detailImage" src="${q.image_url}?t=${Date.now()}" alt="题目页面" />
            <div id="cropBox" class="crop-box hidden"></div>
          </div>
        </div>
        <div class="detail-side">
          <div class="panel-head">
            <div>
              <h2>${escapeHtml(q.category)}</h2>
              <p>第 ${escapeHtml(q.seq_no || q.page_number)} 题 · ${escapeHtml(q.document_title || q.filename)} · ${escapeHtml(q.subject || "其他")} · ${escapeHtml(q.difficulty)}</p>
            </div>
            <button class="ghost" id="closeDetail">关闭</button>
          </div>
          <label>
            题号（左上角的编号，便于快速定位）
            <input id="detailQuestionNo" value="${escapeAttr(q.question_no || "")}" placeholder="例如：03" />
          </label>
          <label>
            章节
            <input id="detailChapter" value="${escapeAttr(q.chapter || "")}" placeholder="例如：第3章 多元函数微分学" />
          </label>
          <label>
            状态
            <select id="detailStatus">
              ${statuses.map((s) => `<option value="${escapeAttr(s)}" ${s === currentStatus ? "selected" : ""}>${escapeHtml(s)}</option>`).join("")}
            </select>
          </label>
          <div class="memory-panel">
            <strong>复习记忆</strong>
            <span>${escapeHtml(memoryText)}</span>
            <small>created_at: ${escapeHtml(q.created_at || "-")} · retention_stage: ${escapeHtml(q.retention_stage || 0)}</small>
          </div>
          <label>
            元认知错因
            <div class="meta-checks">${metaTagControls(q.meta_tags || [])}</div>
          </label>
          <label>
            本次复盘补充
            <textarea id="userNote" placeholder="写这一次二刷/三刷的新发现；保存后会追加到下方历史记录，不覆盖旧记录"></textarea>
          </label>
          <section class="review-note-panel">
            <div class="review-note-head">
              <strong>多刷记录</strong>
              <span>${(q.review_notes || []).length || 0} 条</span>
            </div>
            <div class="review-note-timeline">${renderReviewNoteTimeline(q.review_notes || [])}</div>
          </section>
          <div class="detail-actions">
            <button id="saveDetail">保存标注</button>
            <button id="analyzeQuestion" class="ghost">错题分析</button>
            <button id="hint1" class="ghost">Get Hint L1</button>
            <button id="hint2" class="ghost">Get Hint L2</button>
            <button id="hint3" class="ghost">Full Solution</button>
            <button id="generateVariations" class="ghost">举一反三</button>
            <button id="clearAnalysisAnswer" class="ghost">清空解析</button>
            <button id="clearVariationAnswer" class="ghost">清空举一反三</button>
            <button id="needReview" class="ghost">加入复习</button>
            <button id="deleteDetailQuestion" class="danger">删除题目</button>
          </div>
          <section class="detail-output-panel">
            <div class="detail-output-head">
              <div><strong>智能解析</strong><small>Hint / Full Solution / 错题分析</small></div>
              <button class="ghost mini" type="button" data-expand-output="analysisBox" data-output-title="智能解析"><i data-lucide="maximize-2"></i>展开阅读</button>
            </div>
            <article id="analysisBox" class="math-output mathjax-container"></article>
          </section>
          <section class="detail-output-panel">
            <div class="detail-output-head">
              <div><strong>举一反三</strong><small>同类变式练习</small></div>
              <button class="ghost mini" type="button" data-expand-output="variationsBox" data-output-title="举一反三"><i data-lucide="maximize-2"></i>展开阅读</button>
            </div>
            <article id="variationsBox" class="math-output mathjax-container"></article>
          </section>
          <div id="detailReadingLayer" class="detail-reading-layer hidden">
            <section class="detail-reading-panel" role="dialog" aria-modal="true" aria-labelledby="detailReadingTitle">
              <div class="detail-reading-head">
                <div>
                  <strong id="detailReadingTitle">解析阅读</strong>
                  <small>完整阅读模式，关闭后回到当前题目。</small>
                </div>
                <button id="closeDetailReading" class="ghost mini" type="button"><i data-lucide="minimize-2"></i>收起</button>
              </div>
              <article id="detailReadingContent" class="detail-reading-content mathjax-container"></article>
            </section>
          </div>
        </div>
      </div>`;
  }

  async function openDetail(id, presetStatus = "") {
    const q = await api(`/api/questions/${id}`);
    const currentStatus = presetStatus || q.status;
    const dialog = $("#detailDialog");
    dialog.classList.remove("archive-mode");
    dialog.classList.remove("reading-mode");
    const prev = detailNeighbor(q.id, -1);
    const next = detailNeighbor(q.id, 1);
    const positionText = detailPositionText(q.id);
    renderDetail(q, currentStatus, prev, next, positionText);
    dialog.showModal();
    renderAiOutput("#analysisBox", q.ai_hint || q.ai_analysis, "先尝试 Level 1 概念提示；仍卡住再逐级展开到完整解析。");
    renderAiOutput("#variationsBox", q.ai_variations, "点击“举一反三”，生成同类变式练习。");
    typesetMath($("#detailContent"));
    if (window.lucide) lucide.createIcons();
    bindDetailReading();
    dialog.oncancel = (event) => {
      if (!isDetailReadingOpen()) return;
      event.preventDefault();
      closeDetailReading();
    };

    $("#closeDetail").onclick = () => {
      closeDetailReading();
      dialog.close();
    };
    $("#prevQuestion").onclick = () => {
      if (!prev.id) return;
      dialog.close();
      openDetail(prev.id);
    };
    $("#nextQuestion").onclick = () => {
      if (!next.id) return;
      dialog.close();
      openDetail(next.id);
    };
    $("#saveDetail").onclick = async () => {
      await updateQuestion(q.id, readDetailPatch());
      dialog.close();
    };
    $("#needReview").onclick = async () => {
      const patch = readDetailPatch();
      await updateQuestion(q.id, {
        ...patch,
        status: "需复习",
      });
      dialog.close();
    };
    $("#deleteDetailQuestion").onclick = async () => {
      dialog.close();
      await deleteQuestion(q.id);
    };
    $("#clearAnalysisAnswer").onclick = async () => {
      if (!confirm("确定清空这道题已保存的 AI 解析和提示吗？")) return;
      await api(`/api/questions/${q.id}`, {
        method: "PATCH",
        body: JSON.stringify({ ai_analysis: "", ai_hint: "" }),
      });
      renderAiOutput("#analysisBox", "", "解析已清空。可以重新生成 Hint、Full Solution 或错题分析。");
      await refresh();
    };
    $("#clearVariationAnswer").onclick = async () => {
      if (!confirm("确定清空这道题已保存的举一反三吗？")) return;
      await api(`/api/questions/${q.id}`, {
        method: "PATCH",
        body: JSON.stringify({ ai_variations: "" }),
      });
      renderAiOutput("#variationsBox", "", "举一反三已清空。");
      await refresh();
    };
    $("#analyzeQuestion").onclick = async () => {
      renderAiOutput("#analysisBox", "正在生成错题分析并写入学习档案...");
      await persistDetailContext(q.id);
      const data = await api(`/api/questions/${q.id}/analyze`, { method: "POST", body: "{}" });
      const ins = data.insight || {};
      const chip = ins.root_cause
        ? `\n\n- 已写入学习档案：考点「${(ins.knowledge_points || []).join("、")}」· 错因「${ins.root_cause}」`
        : "\n\n- 已写入学习档案。";
      renderAiOutput("#analysisBox", (data.ai_analysis || "") + chip);
      await refresh();
    };
    [1, 2, 3].forEach((level) => {
      $(`#hint${level}`).onclick = async () => {
        renderAiOutput("#analysisBox", level === 3 ? "正在本地识别题干并生成完整解析..." : "正在生成提示...");
        await persistDetailContext(q.id);
        let data = await api(`/api/questions/${q.id}/hint`, { method: "POST", body: JSON.stringify({ level }) });
        if (level === 3 && data.needs_vision_confirm) {
          renderAiOutput("#analysisBox", data.hint);
          const ok = confirm(data.vision_confirm_message || "本地 OCR 没有识别出题干。是否调用视觉 API 识别这张题图？");
          if (ok) {
            renderAiOutput("#analysisBox", "正在调用视觉 API 识别题干并生成完整解析...");
            data = await api(`/api/questions/${q.id}/hint`, {
              method: "POST",
              body: JSON.stringify({ level, allow_vision_ocr: true }),
            });
          }
        }
        renderAiOutput("#analysisBox", data.hint);
        await refresh();
      };
    });
    $("#generateVariations").onclick = async () => {
      renderAiOutput("#variationsBox", "正在生成难度梯度变式...");
      await persistDetailContext(q.id);
      const data = await api(`/api/questions/${q.id}/variations`, { method: "POST", body: "{}" });
      renderAiOutput("#variationsBox", data.ai_variations);
      await refresh();
    };
    setupCropTool(q.id);
    $("#zoomImage").onclick = () => openLightbox($("#detailImage").src, `${q.category} · 第 ${q.page_number} 页`);
  }

  function setupCropTool(questionId) {
    const stage = $("#cropStage");
    const box = $("#cropBox");
    const save = $("#saveCrop");
    let active = false;
    let start = null;
    let crop = null;

    $("#enableCrop").onclick = () => {
      active = !active;
      box.classList.toggle("hidden", !active);
      save.disabled = !active;
    };

    stage.onpointerdown = (event) => {
      if (!active) return;
      const rect = stage.getBoundingClientRect();
      start = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      crop = { x: start.x, y: start.y, w: 1, h: 1 };
      drawCropBox(crop);
    };

    stage.onpointermove = (event) => {
      if (!active || !start) return;
      const rect = stage.getBoundingClientRect();
      const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
      const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top));
      crop = {
        x: Math.min(start.x, x),
        y: Math.min(start.y, y),
        w: Math.abs(x - start.x),
        h: Math.abs(y - start.y),
      };
      drawCropBox(crop);
    };

    stage.onpointerup = () => {
      start = null;
    };

    save.onclick = async () => {
      if (!crop || crop.w < 20 || crop.h < 20) {
        alert("请拖出一个足够大的裁剪区域。");
        return;
      }
      const rect = stage.getBoundingClientRect();
      const normalized = {
        x: crop.x / rect.width,
        y: crop.y / rect.height,
        w: crop.w / rect.width,
        h: crop.h / rect.height,
      };
      const updated = await api(`/api/questions/${questionId}/crop`, {
        method: "POST",
        body: JSON.stringify({ crop: normalized }),
      });
      $("#detailImage").src = `${updated.image_url}?t=${Date.now()}`;
      box.classList.add("hidden");
      save.disabled = true;
      active = false;
      await refresh();
    };
  }

  function drawCropBox(crop) {
    const box = $("#cropBox");
    box.style.left = `${crop.x}px`;
    box.style.top = `${crop.y}px`;
    box.style.width = `${crop.w}px`;
    box.style.height = `${crop.h}px`;
  }

  function applyLightboxTransform() {
    const img = $("#lightboxImage");
    if (img) img.style.transform = `translate(${lightboxState.tx}px, ${lightboxState.ty}px) scale(${lightboxState.scale})`;
  }

  function openLightbox(src, caption = "") {
    const box = $("#imageLightbox");
    $("#lightboxImage").src = src;
    $("#lightboxCaption").textContent = caption;
    Object.assign(lightboxState, { scale: 1, tx: 0, ty: 0, dragging: false });
    applyLightboxTransform();
    if (!box.open) box.showModal();
  }

  function closeLightbox() {
    const box = $("#imageLightbox");
    if (box.open) box.close();
  }

  function setupLightbox() {
    if (lightboxState.isBound) return;
    const box = $("#imageLightbox");
    if (!box) return;
    const img = $("#lightboxImage");
    lightboxState.isBound = true;

    $("#lightboxClose").onclick = closeLightbox;
    box.addEventListener("click", (event) => { if (event.target === box) closeLightbox(); });
    box.addEventListener("cancel", (event) => { event.preventDefault(); closeLightbox(); });

    box.addEventListener("wheel", (event) => {
      if (!box.open) return;
      event.preventDefault();
      const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15;
      lightboxState.scale = Math.max(0.5, Math.min(8, lightboxState.scale * factor));
      applyLightboxTransform();
    }, { passive: false });

    img.addEventListener("dblclick", () => {
      Object.assign(lightboxState, { scale: lightboxState.scale > 1 ? 1 : 2, tx: 0, ty: 0 });
      applyLightboxTransform();
    });

    img.addEventListener("pointerdown", (event) => {
      lightboxState.dragging = true;
      lightboxState.sx = event.clientX - lightboxState.tx;
      lightboxState.sy = event.clientY - lightboxState.ty;
      img.setPointerCapture(event.pointerId);
    });
    img.addEventListener("pointermove", (event) => {
      if (!lightboxState.dragging) return;
      lightboxState.tx = event.clientX - lightboxState.sx;
      lightboxState.ty = event.clientY - lightboxState.sy;
      applyLightboxTransform();
    });
    img.addEventListener("pointerup", () => { lightboxState.dragging = false; });
  }

  window.openDetail = openDetail;
  window.openLightbox = openLightbox;
  window.SakuraQuestionDetail = {
    open: openDetail,
    openLightbox,
    setupLightbox,
  };

  setupLightbox();
})();
