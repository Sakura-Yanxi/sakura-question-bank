(function () {
  let isBound = false;
  let scanTimers = [];
  let textbookLoadRequestSeq = 0;
  let textbookAiRequestSeq = 0;
  let textbookVisionRequestSeq = 0;
  let textbookAiBusy = false;
  let textbookMemoryBusy = false;
  let textbookVisionBusy = false;

  const TEXTBOOK_SCAN_STATUS = {
    reading: (pageNumber) => `正在读取第 ${pageNumber} 页...`,
    rendering: (pageNumber) => `正在渲染第 ${pageNumber} 页截图...`,
    ocr: "若本页无文本层，正在 OCR 扫描当前页...",
    done: (pageNumber, count) => `第 ${pageNumber} 页已读取；仅保留当前页临时结果，识别出 ${count} 段。`,
  };

  const TEXTBOOK_DELETE_STATUS = {
    pageRemovedTitle: "当前页已删除。",
    pageRemovedBody: (pageNumber) => `已自动切换到第 ${pageNumber} 页。点击「读取/OCR」或「视觉读取」开始加载这一页。`,
    pageRemovedHint: (deletedPage, nextPage) => `已删除第 ${deletedPage} 页，当前切换到第 ${nextPage} 页，尚未读取。`,
  };

  function pageLabel(pageLike = {}) {
    return Number(pageLike.pdf_page_number || pageLike.page_number || state.textbookPage || 1);
  }

  function currentPdfPage(pageLike = {}) {
    return pageLabel(pageLike);
  }

  function textbookPageBoundaries(book = selectedTextbook()) {
    const fallbackMax = Math.max(1, Number(book?.page_count || state.textbookPage || 1));
    const min = 1;
    const max = fallbackMax;
    return { min, max };
  }

  function textbookPageMeta(book, page) {
    const pdf = currentPdfPage(page);
    const display = Number(page?.display_page || 0);
    const totalPdf = Number(book?.page_count || pdf || 1);
    const segments = [`${book.title} · PDF ${pdf}/${totalPdf}`];
    if (display && display !== pdf) segments.push(`教材第 ${display} 页`);
    if (Array.isArray(page?.paragraphs)) segments.push(`${page.paragraphs.length} 段`);
    return segments.join(" · ");
  }

  const QUESTION_DOCUMENT_PATTERN = /(模拟卷|模拟考试|模考试卷|模考|真题卷?|试卷|套卷|试题|押题|冲刺卷|预测卷|自测卷|练习卷|测试卷|考试卷|卷子)/i;
  const GENERIC_QUESTION_VOLUME_PATTERN = /[\w\u4e00-\u9fff]{1,24}卷/i;
  const TEXTBOOK_VOLUME_PATTERN = /(上卷|中卷|下卷|第一卷|第二卷|第三卷|第四卷|第五卷)/;

  function looksLikeQuestionDocument(book) {
    if (book && Object.prototype.hasOwnProperty.call(book, "question_like")) {
      return Boolean(book.question_like);
    }
    return looksLikeQuestionDocumentName(book?.filename || "", book?.title || "");
  }

  function looksLikeQuestionDocumentName(filename = "", title = "") {
    const text = `${title || ""} ${filename || ""}`;
    if (QUESTION_DOCUMENT_PATTERN.test(text)) return true;
    if (TEXTBOOK_VOLUME_PATTERN.test(text)) return false;
    return GENERIC_QUESTION_VOLUME_PATTERN.test(text);
  }

  function textbookImportGuardMessage() {
    return "该文件名疑似为试卷/真题卷/模拟卷，请到「全真模拟卷」模块导入；教材精读只处理教材、讲义和参考书。";
  }

  function clearTextbookScanTimers() {
    scanTimers.forEach((timer) => clearTimeout(timer));
    scanTimers = [];
  }

  function setTextbookLoadButtonDisabled(disabled) {
    const loadButton = $("#loadTextbookPage");
    if (loadButton) loadButton.disabled = disabled;
  }

  function setTextbookChatButtonsDisabled(disabled) {
    ["#askTextbookAi", "#explainSelectedParagraph"].forEach((selector) => {
      const button = $(selector);
      if (button) button.disabled = disabled;
    });
  }

  function setTextbookMemoryButtonDisabled(disabled) {
    const button = $("#saveTextbookMemory");
    if (button) button.disabled = disabled;
  }

  function setTextbookVisionButtonDisabled(disabled) {
    const button = $("#readTextbookVision");
    if (button) button.disabled = disabled;
  }

  function cancelPendingTextbookAiResponse() {
    textbookAiRequestSeq += 1;
    textbookAiBusy = false;
    setTextbookChatButtonsDisabled(false);
  }

  function cancelPendingTextbookVisionResponse() {
    textbookVisionRequestSeq += 1;
    textbookVisionBusy = false;
    setTextbookVisionButtonDisabled(false);
  }

  function resetTextbookScanStatus() {
    clearTextbookScanTimers();
    const box = $("#textbookScanStatus");
    if (!box) return;
    box.classList.add("hidden");
    box.classList.remove("active");
    if ($("#textbookScanLabel")) $("#textbookScanLabel").textContent = "正在读取当前页...";
    if ($("#textbookScanPercent")) $("#textbookScanPercent").textContent = "0%";
    if ($("#textbookScanBar")) $("#textbookScanBar").style.setProperty("--scan-progress", "4%");
  }

  function cancelPendingTextbookRead() {
    textbookLoadRequestSeq += 1;
    resetTextbookScanStatus();
    setTextbookLoadButtonDisabled(false);
  }

  function setTextbookScanStatus(label, progress = 0, active = false) {
    const box = $("#textbookScanStatus");
    if (!box) return;
    box.classList.remove("hidden");
    box.classList.toggle("active", active);
    if ($("#textbookScanLabel")) $("#textbookScanLabel").textContent = label;
    if ($("#textbookScanPercent")) $("#textbookScanPercent").textContent = `${Math.max(0, Math.min(100, progress))}%`;
    if ($("#textbookScanBar")) $("#textbookScanBar").style.setProperty("--scan-progress", `${Math.max(4, Math.min(100, progress))}%`);
  }

  function finishTextbookScanStatus(label) {
    clearTextbookScanTimers();
    setTextbookScanStatus(label, 100, false);
  }

  function startTextbookScanStatus(pageNumber, requestId) {
    clearTextbookScanTimers();
    setTextbookScanStatus(TEXTBOOK_SCAN_STATUS.reading(pageNumber), 18, true);
    scanTimers.push(setTimeout(() => {
      if (requestId === textbookLoadRequestSeq) setTextbookScanStatus(TEXTBOOK_SCAN_STATUS.rendering(pageNumber), 42, true);
    }, 450));
    scanTimers.push(setTimeout(() => {
      if (requestId === textbookLoadRequestSeq) setTextbookScanStatus(TEXTBOOK_SCAN_STATUS.ocr, 72, true);
    }, 1200));
  }

  function renderSelectedParagraphContent() {
    const detail = $("#textbookParagraphDetail");
    if (!detail) return;
    const paragraphs = state.textbookParagraphs || [];
    const index = Number(state.textbookParagraph || 0);
    const text = index > 0 ? paragraphs[index - 1] || "" : "";
    detail.classList.toggle("hidden", !text);
    if ($("#textbookParagraphDetailTitle")) $("#textbookParagraphDetailTitle").textContent = `第 ${index} 段完整内容`;
    if ($("#textbookParagraphDetailText")) $("#textbookParagraphDetailText").textContent = text;
  }

  async function loadTextbooks() {
    const data = await api("/api/textbooks");
    state.textbooks = data.textbooks || [];
    const current = state.textbooks.find((book) => book.id === state.textbookId);
    if (current && looksLikeQuestionDocument(current)) {
      state.textbookId = "";
      state.textbookPage = 1;
      state.textbookPdfPage = 1;
      state.textbookParagraph = 0;
      state.textbookChat = [];
      syncTextbookPageInput(1);
      renderTextbooks();
      showTextbookEmptyState("请选择教材。", "检测到当前资料像模拟卷/真题，请到「全真模拟卷」导入，它会按题号切分成题目。");
      renderTextbookChat();
      return;
    }
    renderTextbooks();
    if (!state.textbookId && state.textbooks.length) {
      const firstReadable = state.textbooks.find((book) => !looksLikeQuestionDocument(book));
      if (!firstReadable) {
        showTextbookEmptyState("没有可精读的教材。", "教材库里都是试卷类 PDF。请到「全真模拟卷」导入，或删除这些误导入记录。");
        renderTextbookChat();
        return;
      }
      state.textbookId = firstReadable.id;
      state.textbookPage = Number(firstReadable.first_page || 1);
      state.textbookPdfPage = 0;
      state.textbookParagraph = 0;
      state.textbookChat = [];
      syncTextbookPageInput(state.textbookPage);
      showTextbookEmptyState("页码已就绪，等待读取。", `当前选中 PDF 第 ${state.textbookPage} 页。点击「读取/OCR」或「视觉读取」开始加载这一页。`);
      renderTextbookChat();
    }
  }

  function renderTextbooks() {
    const node = $("#textbookList");
    if (!node) return;
    node.innerHTML =
      state.textbooks
        .map((book) => {
          const questionLike = looksLikeQuestionDocument(book);
          return `
          <article class="document-card ${book.id === state.textbookId ? "selected-doc" : ""} ${questionLike ? "question-doc-card" : ""}">
            <div>
              <h3>${escapeHtml(book.title || book.filename)}</h3>
              <p>${escapeHtml(book.subject || "未分类")} · PDF ${book.page_count || 0} 页 · 可用 ${book.saved_pages || 0} 页</p>
              <span class="tag kind ${questionLike ? "mock" : "paper"}">${questionLike ? "疑似试卷" : "教材"}</span>
              ${questionLike ? `<p class="textbook-routing-note">请走全真模拟卷导入，才能按题号切分成题目。</p>` : ""}
              <p>${escapeHtml(book.filename || "")}</p>
            </div>
            <div class="doc-actions">
              ${questionLike
                ? `<button class="ghost" data-go-mock-upload>去模拟卷</button>`
                : `<button data-open-textbook="${escapeAttr(book.id)}">精读</button>`}
              <button class="danger" data-delete-textbook="${escapeAttr(book.id)}">删除</button>
            </div>
          </article>`;
        })
        .join("") || `<p class="empty-note">还没有教材。先在上方上传 PDF。</p>`;
  }

  function selectedTextbook() {
    return state.textbooks.find((book) => book.id === state.textbookId);
  }

  function syncTextbookPageInput(pageNumber = state.textbookPage || 1) {
    const input = $("#textbookPageInput");
    if (input) input.value = pageNumber;
  }

  function currentRequestedTextbookPage() {
    const input = $("#textbookPageInput");
    const raw = input ? String(input.value || "").trim() : "";
    return clampTextbookPage(raw || state.textbookPage || 1);
  }

  function currentSelectedParagraphText() {
    const index = Number(state.textbookParagraph || 0);
    if (index <= 0) return "";
    return String((state.textbookParagraphs || [])[index - 1] || "").trim();
  }

  function requireLoadedTextbookPage(actionLabel = "继续操作") {
    const requestedPage = currentRequestedTextbookPage();
    if (state.textbookPdfPage && requestedPage === Number(state.textbookPdfPage)) {
      return true;
    }
    cancelPendingTextbookAiResponse();
    cancelPendingTextbookVisionResponse();
    state.textbookPage = requestedPage;
    state.textbookPdfPage = 0;
    state.textbookParagraph = 0;
    state.textbookParagraphs = [];
    state.textbookChat = [];
    syncTextbookPageInput(requestedPage);
    showTextbookEmptyState(
      "页码已切换，等待读取。",
      `当前输入为 PDF 第 ${requestedPage} 页。请先点击「读取/OCR」或「视觉读取」，再${actionLabel}。`
    );
    renderTextbookChat();
    if ($("#textbookHint")) $("#textbookHint").textContent = `请先读取 PDF 第 ${requestedPage} 页，再${actionLabel}。`;
    return false;
  }

  function applyRequestedTextbookPage(options = {}) {
    const { clearParagraph = false, clearChat = false } = options;
    const pageNumber = currentRequestedTextbookPage();
    const changed = Number(state.textbookPage || 1) !== pageNumber;
    state.textbookPage = pageNumber;
    syncTextbookPageInput(pageNumber);
    if (changed && clearParagraph) {
      state.textbookParagraph = 0;
      state.textbookParagraphs = [];
      renderSelectedParagraphContent();
    }
    if (changed && clearChat) {
      state.textbookChat = [];
    }
    updateTextbookChatBadge();
    return { pageNumber, changed };
  }

  function clampTextbookPage(pageNumber) {
    const { min, max } = textbookPageBoundaries();
    return Math.min(max, Math.max(min, Number(pageNumber || min)));
  }

  async function goTextbookPage(delta) {
    if (!state.textbookId) return;
    const nextPage = clampTextbookPage(Number(currentRequestedTextbookPage()) + delta);
    const changed = Number(state.textbookPage || 1) !== nextPage;
    state.textbookPage = nextPage;
    syncTextbookPageInput(nextPage);
    if (changed) {
      cancelPendingTextbookAiResponse();
      cancelPendingTextbookVisionResponse();
      state.textbookParagraph = 0;
      state.textbookParagraphs = [];
      state.textbookChat = [];
      state.textbookPdfPage = 0;
      showTextbookEmptyState("页码已切换，等待读取。", `当前已切到第 ${nextPage} 页。点击「读取/OCR」或「视觉读取」开始加载这一页。`);
      if ($("#textbookHint")) $("#textbookHint").textContent = `已切换到第 ${nextPage} 页，尚未读取。`;
    } else {
      updateTextbookChatBadge();
    }
    renderTextbookChat();
  }

  function showTextbookEmptyState(meta, note, options = {}) {
    const { cancelPendingRead = true, resetScan = true } = options;
    if (cancelPendingRead) {
      cancelPendingTextbookRead();
    } else if (resetScan) {
      resetTextbookScanStatus();
    }
    if ($("#textbookPageMeta")) $("#textbookPageMeta").textContent = meta;
    if ($("#textbookParagraphs")) $("#textbookParagraphs").innerHTML = `<p class="empty-note">${escapeHtml(note)}</p>`;
    state.textbookParagraphs = [];
    state.textbookPdfPage = 0;
    const img = $("#textbookPageImage");
    if (img) {
      img.classList.add("hidden");
      img.removeAttribute("src");
    }
    renderSelectedParagraphContent();
    updateTextbookChatBadge();
  }

  async function loadTextbookPage() {
    if (!state.textbookId) return;
    cancelPendingTextbookAiResponse();
    cancelPendingTextbookVisionResponse();
    const pageNumber = applyRequestedTextbookPage({ clearParagraph: true }).pageNumber;
    const requestId = textbookLoadRequestSeq + 1;
    textbookLoadRequestSeq = requestId;
    setTextbookLoadButtonDisabled(true);
    startTextbookScanStatus(pageNumber, requestId);
    let data;
    try {
      data = await api(`/api/textbooks/${encodeURIComponent(state.textbookId)}/pages/${pageNumber}`);
    } catch (error) {
      if (requestId !== textbookLoadRequestSeq) return;
      // The page may not exist (deleted) or the textbook may be empty — degrade to a clear
      // empty state instead of throwing an unhandled error.
      state.textbookParagraph = 0;
      renderTextbooks();
      showTextbookEmptyState(
        "这一页不存在，或本教材已无页面。",
        "本教材没有可用页面。可在左侧列表点「删除」移除它，或换一本教材 / 换一个页码。",
        { cancelPendingRead: false, resetScan: false }
      );
      finishTextbookScanStatus(`第 ${pageNumber} 页读取失败：${error.message}`);
      syncTextbookPageInput(pageNumber);
      setTextbookLoadButtonDisabled(false);
      return;
    }
    if (requestId !== textbookLoadRequestSeq) return;
    state.textbookPage = pageLabel(data.page);
    state.textbookPdfPage = currentPdfPage(data.page);
    state.textbookParagraph = 0;
    syncTextbookPageInput(state.textbookPage);
    renderTextbooks();
    renderTextbookPage(data.textbook, data.page);
    finishTextbookScanStatus(TEXTBOOK_SCAN_STATUS.done(state.textbookPage, (data.page.paragraphs || []).length));
    setTextbookLoadButtonDisabled(false);
  }

  function renderTextbookPage(book, page) {
    state.textbookParagraphs = page.paragraphs || [];
    $("#textbookPageMeta").textContent = textbookPageMeta(book, page);
    $("#textbookPageImage").src = `${page.image_url}?t=${Date.now()}`;
    $("#textbookPageImage").classList.toggle("hidden", !page.image_url);
    $("#textbookPageImage").dataset.caption = textbookPageMeta(book, page);
    $("#textbookParagraphs").innerHTML =
      (page.paragraphs || [])
        .map(
          (paragraph, index) => `
          <button class="textbook-paragraph ${state.textbookParagraph === index + 1 ? "active" : ""}" data-textbook-paragraph="${index + 1}">
            <span class="textbook-paragraph-index">第 ${index + 1} 段</span>
            <span class="textbook-paragraph-preview">${escapeHtml(paragraph)}</span>
          </button>`
        )
        .join("") || `<p class="empty-note">这一页没有可提取文字。可以直接根据页图向 AI 提问，但效果取决于文本层质量。</p>`;
    renderSelectedParagraphContent();
    updateTextbookChatBadge();
  }

  function updateTextbookChatBadge() {
    const book = selectedTextbook();
    const text = book ? `${book.title} · 第 ${state.textbookPage} 页${state.textbookParagraph ? ` · 第 ${state.textbookParagraph} 段` : ""}` : "未选择教材";
    $("#textbookChatBadge").textContent = text;
  }

  function renderTextbookChat() {
    const node = $("#textbookChatLog");
    if (!node) return;
    node.innerHTML =
      state.textbookChat
        .map((item) => `<article class="textbook-chat-msg ${item.role}"><strong>${item.role === "user" ? "我" : "AI 老师"}</strong><div>${markdownToHtml(item.content)}</div></article>`)
        .join("") || `<p class="empty-note">选择教材页和段落后，可以让 AI 逐句解释、补例子或联系错题。</p>`;
    typesetMath(node);
    node.scrollTop = node.scrollHeight;
  }

  async function askTextbookAi(message = "", options = {}) {
    const { selectedOnly = false } = options;
    const hint = $("#textbookHint");
    if (textbookAiBusy) return;
    const content = (message || $("#textbookQuestion")?.value || "").trim();
    if (!state.textbookId) {
      if (hint) hint.textContent = "请先选择教材。";
      return;
    }
    if (!content) {
      if (hint) hint.textContent = "请输入要问的问题。";
      return;
    }
    if (!requireLoadedTextbookPage(selectedOnly ? "解释选中段落" : "向 AI 提问")) {
      return;
    }
    const textbookId = state.textbookId;
    const pageNumber = state.textbookPage;
    const paragraphIndex = state.textbookParagraph;
    const selectedParagraphText = currentSelectedParagraphText();
    if (selectedOnly && !selectedParagraphText) {
      if (hint) hint.textContent = "请先在左侧选择一个已经识别出的段落。";
      return;
    }
    const historyBeforeQuestion = state.textbookChat.slice();
    state.textbookChat.push({ role: "user", content });
    renderTextbookChat();
    if ($("#textbookQuestion")) $("#textbookQuestion").value = "";
    if (hint) hint.textContent = selectedOnly ? "AI 正在解释选中段落..." : "AI 正在精读当前页...";
    const requestId = textbookAiRequestSeq + 1;
    textbookAiRequestSeq = requestId;
    textbookAiBusy = true;
    setTextbookChatButtonsDisabled(true);
    try {
      const data = await api("/api/textbooks/chat", {
        method: "POST",
        body: JSON.stringify({
          textbook_id: textbookId,
          page_number: pageNumber,
          paragraph_index: paragraphIndex,
          selected_paragraph_text: selectedParagraphText,
          message: content,
          history: historyBeforeQuestion,
        }),
      });
      if (
        requestId !== textbookAiRequestSeq ||
        textbookId !== state.textbookId ||
        Number(pageNumber) !== Number(state.textbookPage)
      ) {
        return;
      }
      state.textbookChat.push({ role: "assistant", content: data.answer || "" });
      renderTextbookChat();
      if (hint) hint.textContent = data.has_key ? "已完成。可以继续追问，或压缩导入记忆。" : "未配置 API，已返回本地提示。";
    } catch (error) {
      if (requestId === textbookAiRequestSeq && hint) hint.textContent = `AI 精读失败：${error.message}`;
    } finally {
      if (requestId === textbookAiRequestSeq) {
        textbookAiBusy = false;
        setTextbookChatButtonsDisabled(false);
      }
    }
  }

  async function readTextbookPageWithVision() {
    const hint = $("#textbookHint");
    if (textbookVisionBusy) return;
    if (!state.textbookId) {
      if (hint) hint.textContent = "请先选择教材并读取当前页。";
      return;
    }
    cancelPendingTextbookAiResponse();
    cancelPendingTextbookRead();
    const { pageNumber, changed } = applyRequestedTextbookPage({ clearParagraph: true, clearChat: true });
    if (changed) {
      showTextbookEmptyState("页码已切换，等待视觉读取。", `当前已切到第 ${pageNumber} 页，正在准备页面截图。`);
      renderTextbookChat();
    }
    const textbookId = state.textbookId;
    const displayPage = state.textbookPage;
    const content = ($("#textbookQuestion")?.value || "").trim();
    const historyBeforeQuestion = state.textbookChat.slice();
    const requestId = textbookVisionRequestSeq + 1;
    textbookVisionRequestSeq = requestId;
    textbookVisionBusy = true;
    setTextbookVisionButtonDisabled(true);
    state.textbookParagraph = 0;
    renderSelectedParagraphContent();
    updateTextbookChatBadge();
    if (hint) hint.textContent = "正在调用视觉模型读取当前页图片...";
    state.textbookChat.push({
      role: "user",
      content: content || `请用视觉模型阅读第 ${displayPage} 页，解释本页正文、图表和公式。`,
    });
    renderTextbookChat();
    try {
      const data = await api("/api/textbooks/vision", {
        method: "POST",
        body: JSON.stringify({
          textbook_id: textbookId,
          page_number: pageNumber,
          paragraph_index: 0,
          message: content,
          history: historyBeforeQuestion,
        }),
      });
      if (
        requestId !== textbookVisionRequestSeq ||
        textbookId !== state.textbookId ||
        Number(pageNumber) !== Number(state.textbookPage)
      ) {
        return;
      }
      if (data && data.textbook && data.page) {
        state.textbookPage = pageLabel(data.page);
        state.textbookPdfPage = currentPdfPage(data.page);
        state.textbookParagraph = 0;
        syncTextbookPageInput(state.textbookPage);
        renderTextbooks();
        renderTextbookPage(data.textbook, data.page);
      }
      state.textbookChat.push({ role: "assistant", content: data.answer || "" });
      renderTextbookChat();
      if (hint) {
        hint.textContent = data.has_vision
          ? "视觉读取完成。"
          : (String(data.answer || "").startsWith("视觉模型读取失败") ? data.answer : "未配置视觉模型，已返回配置提示。");
      }
    } catch (error) {
      if (requestId === textbookVisionRequestSeq && hint) hint.textContent = error.message;
    } finally {
      if (requestId === textbookVisionRequestSeq) {
        textbookVisionBusy = false;
        setTextbookVisionButtonDisabled(false);
      }
    }
  }

  async function saveTextbookMemory() {
    const hint = $("#textbookHint");
    if (textbookMemoryBusy) return;
    if (!state.textbookId || !state.textbookChat.length) {
      if (hint) hint.textContent = "先完成一轮教材精读对话，再导入记忆。";
      return;
    }
    if (!requireLoadedTextbookPage("导入记忆")) {
      return;
    }
    if (hint) hint.textContent = "正在压缩对话并写入老师记忆...";
    textbookMemoryBusy = true;
    setTextbookMemoryButtonDisabled(true);
    try {
      const data = await api("/api/textbooks/memory", {
        method: "POST",
        body: JSON.stringify({
          textbook_id: state.textbookId,
          page_number: state.textbookPage,
          paragraph_index: state.textbookParagraph,
          selected_paragraph_text: currentSelectedParagraphText(),
          history: state.textbookChat,
        }),
      });
      if (hint) hint.textContent = `已导入老师记忆：${data.memory.content.slice(0, 48)}...`;
    } catch (error) {
      if (hint) hint.textContent = `导入记忆失败：${error.message}`;
    } finally {
      textbookMemoryBusy = false;
      setTextbookMemoryButtonDisabled(false);
    }
  }

  async function deleteTextbook(id) {
    const book = state.textbooks.find((item) => item.id === id);
    const name = book ? book.title || book.filename : "这本教材";
    if (!confirm(`确定删除「${name}」吗？这会删除教材 PDF、页图和精读对话记录。`)) return;
    if (state.textbookId === id) {
      cancelPendingTextbookRead();
      cancelPendingTextbookAiResponse();
      cancelPendingTextbookVisionResponse();
    }
    await api(`/api/textbooks/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (state.textbookId === id) {
      state.textbookId = "";
      state.textbookPage = 1;
      state.textbookPdfPage = 1;
      state.textbookParagraph = 0;
      state.textbookChat = [];
      syncTextbookPageInput(1);
    }
    await loadTextbooks();
    renderTextbookChat();
  }

  async function deleteTextbookPage() {
    const hint = $("#textbookHint");
    if (!state.textbookId) {
      if (hint) hint.textContent = "请先选择教材。";
      return;
    }
    const requestedPage = currentRequestedTextbookPage();
    if (!state.textbookPdfPage || requestedPage !== Number(state.textbookPdfPage)) {
      state.textbookPage = requestedPage;
      state.textbookPdfPage = 0;
      state.textbookParagraph = 0;
      state.textbookParagraphs = [];
      syncTextbookPageInput(requestedPage);
      showTextbookEmptyState("页码已切换，等待读取。", `当前输入为 PDF 第 ${requestedPage} 页。请先点击“读取/OCR”或“视觉读取”，确认页面后再删除。`);
      renderTextbookChat();
      if (hint) hint.textContent = `请先读取 PDF 第 ${requestedPage} 页，再删除该页。`;
      return;
    }
    const pageNumber = requestedPage;
    const pdfPageNumber = requestedPage;
    const pageText = `PDF 第 ${pdfPageNumber || pageNumber} 页`;
    const book = selectedTextbook();
    const isLastPage = book && Number(book.saved_pages) <= 1;
    const message = isLastPage
      ? `${pageText}是本教材最后一页，删除后整本教材将被移除。确定删除吗？`
      : `确定删除${pageText}吗？这会删除该页的扫描图、提取文字和本页对话记录，其他页码保持不变。`;
    if (!confirm(message)) return;
    cancelPendingTextbookRead();
    cancelPendingTextbookAiResponse();
    cancelPendingTextbookVisionResponse();

    const bookId = state.textbookId;
    try {
      const data = await api(
        `/api/textbooks/${encodeURIComponent(bookId)}/pages/${pageNumber}`,
        { method: "DELETE" }
      );
      state.textbookChat = [];

      if (data && data.saved_pages === 0) {
        // The textbook is now empty and can't be re-filled, so don't leave a zombie record —
        // remove the whole textbook and reset the reader.
        await api(`/api/textbooks/${encodeURIComponent(bookId)}`, { method: "DELETE" });
        state.textbookId = "";
        state.textbookPage = 1;
        state.textbookPdfPage = 1;
        state.textbookParagraph = 0;
        syncTextbookPageInput(1);
        showTextbookEmptyState("先选择一本教材。", "先在左侧选择教材，再读取页面。");
        await loadTextbooks();
        renderTextbookChat();
        if (hint) hint.textContent = "已删除最后一页，本教材已无内容，已为你移除整本教材。";
        return;
      }

      await loadTextbooks();
      if (data && data.next_page) {
        state.textbookPage = Number(data.next_page);
        state.textbookPdfPage = 0;
        state.textbookParagraph = 0;
        state.textbookParagraphs = [];
        syncTextbookPageInput(state.textbookPage);
        showTextbookEmptyState(TEXTBOOK_DELETE_STATUS.pageRemovedTitle, TEXTBOOK_DELETE_STATUS.pageRemovedBody(state.textbookPage));
        renderTextbookChat();
        if (hint) hint.textContent = TEXTBOOK_DELETE_STATUS.pageRemovedHint(pageNumber, state.textbookPage);
        return;
      }
      renderTextbookChat();
      if (hint) hint.textContent = `已删除第 ${pageNumber} 页。`;
    } catch (error) {
      // e.g. the page was already gone (404) — refresh and report instead of crashing.
      await loadTextbooks();
      if (hint) hint.textContent = `删除失败：${error.message}`;
    }
  }

  function bindTextbookUploadForm() {
    const formEl = $("#textbookUploadForm");
    if (!formEl) return;
    formEl.addEventListener("submit", async (event) => {
      event.preventDefault();
      const fileInput = formEl.querySelector('[name="file"]');
      const status = formEl.querySelector(".upload-status");
      const file = fileInput.files[0];
      if (!file) return;
      const title = formEl.querySelector('[name="title"]').value;
      if (looksLikeQuestionDocumentName(file.name, title)) {
        status.textContent = textbookImportGuardMessage();
        return;
      }
      const form = new FormData();
      form.append("file", file);
      form.append("title", title);
      form.append("subject", formEl.querySelector('[name="subject"]').value);
      status.textContent = "正在导入教材并按页建立索引...";
      try {
        const data = await api("/api/textbooks/upload", { method: "POST", body: form });
        status.textContent = `已导入「${data.title}」共 ${data.page_count} 页。`;
        formEl.reset();
        cancelPendingTextbookRead();
        cancelPendingTextbookAiResponse();
        cancelPendingTextbookVisionResponse();
        state.textbookId = data.textbook_id;
        state.textbookPage = 1;
        state.textbookPdfPage = 1;
        state.textbookParagraph = 0;
        state.textbookChat = [];
        await loadTextbooks();
        const book = state.textbooks.find((item) => item.id === state.textbookId);
        state.textbookPage = Number(book?.first_page || 1);
        state.textbookPdfPage = 0;
        syncTextbookPageInput(state.textbookPage);
        showTextbookEmptyState("页码已就绪，等待读取。", `当前选中 PDF 第 ${state.textbookPage} 页。点击「读取/OCR」或「视觉读取」开始加载这一页。`);
      } catch (error) {
        status.textContent = error.message;
      }
    });
  }

  function bindTextbookPanel() {
    if (isBound) return;
    isBound = true;
    bindTextbookUploadForm();
    on("#textbookList", "click", async (event) => {
      const goMock = event.target.closest("[data-go-mock-upload]");
      if (goMock) {
        setView("mockPapers");
        return;
      }
      const open = event.target.closest("[data-open-textbook]");
      if (open) {
        cancelPendingTextbookRead();
        cancelPendingTextbookAiResponse();
        cancelPendingTextbookVisionResponse();
        state.textbookId = open.dataset.openTextbook;
        const book = state.textbooks.find((item) => item.id === state.textbookId);
        state.textbookPage = Number(book?.first_page || 1);
        state.textbookPdfPage = 0;
        state.textbookParagraph = 0;
        state.textbookChat = [];
        syncTextbookPageInput(state.textbookPage);
        showTextbookEmptyState("页码已就绪，等待读取。", `当前选中 PDF 第 ${state.textbookPage} 页。点击「读取/OCR」或「视觉读取」开始加载这一页。`);
        renderTextbookChat();
        return;
      }
      const del = event.target.closest("[data-delete-textbook]");
      if (del) await deleteTextbook(del.dataset.deleteTextbook);
    });
    on("#loadTextbookPage", "click", async () => {
      applyRequestedTextbookPage({ clearParagraph: true, clearChat: true });
      state.textbookChat = [];
      await loadTextbookPage();
      renderTextbookChat();
    });
    on("#readTextbookVision", "click", readTextbookPageWithVision);
    on("#prevTextbookPage", "click", () => goTextbookPage(-1));
    on("#nextTextbookPage", "click", () => goTextbookPage(1));
    on("#deleteTextbookPage", "click", deleteTextbookPage);
    on("#textbookPageInput", "keydown", async (event) => {
      if (event.key === "Enter") {
        applyRequestedTextbookPage({ clearParagraph: true, clearChat: true });
        state.textbookChat = [];
        await loadTextbookPage();
        renderTextbookChat();
      }
    });
    on("#textbookParagraphs", "click", (event) => {
      const btn = event.target.closest("[data-textbook-paragraph]");
      if (!btn) return;
      state.textbookParagraph = Number(btn.dataset.textbookParagraph) || 0;
      $$(".textbook-paragraph").forEach((node) => node.classList.toggle("active", node === btn));
      renderSelectedParagraphContent();
      updateTextbookChatBadge();
    });
    on("#copyTextbookParagraph", "click", async () => {
      const text = $("#textbookParagraphDetailText")?.textContent || "";
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        if ($("#textbookHint")) $("#textbookHint").textContent = "已复制当前段落。";
      } catch (error) {
        if ($("#textbookHint")) $("#textbookHint").textContent = "当前浏览器不允许自动复制，可以手动选中文本复制。";
      }
    });
    on("#textbookPageImage", "dblclick", () => {
      const img = $("#textbookPageImage");
      if (!img || img.classList.contains("hidden") || !img.src) return;
      if (window.openLightbox) window.openLightbox(img.src, img.dataset.caption || "教材页截图");
    });
    on("#askTextbookAi", "click", () => askTextbookAi());
    on("#explainSelectedParagraph", "click", () => {
      if (!state.textbookParagraph) {
        if ($("#textbookHint")) $("#textbookHint").textContent = "请先在左侧选择一个段落。";
        return;
      }
      const msg = `请逐句解释第 ${state.textbookPage} 页第 ${state.textbookParagraph} 段，说明关键概念、公式来源和容易误解的地方。`;
      askTextbookAi(msg, { selectedOnly: true });
    });
    on("#saveTextbookMemory", "click", saveTextbookMemory);
    on("#clearTextbookChat", "click", () => {
      cancelPendingTextbookAiResponse();
      cancelPendingTextbookVisionResponse();
      state.textbookChat = [];
      renderTextbookChat();
      if ($("#textbookHint")) $("#textbookHint").textContent = "当前页面对话已清空。";
    });
  }

  window.SakuraTextbook = {
    load: loadTextbooks,
    renderChat: renderTextbookChat,
    loadPage: loadTextbookPage,
    bind: bindTextbookPanel,
  };

  bindTextbookPanel();
})();
