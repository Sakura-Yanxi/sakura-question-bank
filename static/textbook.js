(function () {
  let isBound = false;

  async function loadTextbooks() {
    const data = await api("/api/textbooks");
    state.textbooks = data.textbooks || [];
    renderTextbooks();
    if (!state.textbookId && state.textbooks.length) {
      state.textbookId = state.textbooks[0].id;
      state.textbookPage = 1;
      await loadTextbookPage();
    }
  }

  function renderTextbooks() {
    const node = $("#textbookList");
    if (!node) return;
    node.innerHTML =
      state.textbooks
        .map(
          (book) => `
          <article class="document-card ${book.id === state.textbookId ? "selected-doc" : ""}">
            <div>
              <h3>${escapeHtml(book.title || book.filename)}</h3>
              <p>${escapeHtml(book.subject || "未分类")} · ${book.page_count || 0} 页 · 已索引 ${book.saved_pages || 0} 页</p>
              <span class="tag kind paper">教材</span>
              <p>${escapeHtml(book.filename || "")}</p>
            </div>
            <div class="doc-actions">
              <button data-open-textbook="${escapeAttr(book.id)}">精读</button>
              <button class="danger" data-delete-textbook="${escapeAttr(book.id)}">删除</button>
            </div>
          </article>`
        )
        .join("") || `<p class="empty-note">还没有教材。先在上方上传 PDF。</p>`;
  }

  function selectedTextbook() {
    return state.textbooks.find((book) => book.id === state.textbookId);
  }

  async function loadTextbookPage() {
    if (!state.textbookId) return;
    const pageNumber = Math.max(1, Number($("#textbookPageInput")?.value || state.textbookPage || 1));
    const data = await api(`/api/textbooks/${encodeURIComponent(state.textbookId)}/pages/${pageNumber}`);
    state.textbookPage = data.page.page_number;
    state.textbookParagraph = 0;
    if ($("#textbookPageInput")) $("#textbookPageInput").value = state.textbookPage;
    renderTextbooks();
    renderTextbookPage(data.textbook, data.page);
  }

  function renderTextbookPage(book, page) {
    $("#textbookPageMeta").textContent = `${book.title} · 第 ${page.page_number}/${book.page_count} 页 · ${page.paragraphs.length} 段`;
    $("#textbookPageImage").src = `${page.image_url}?t=${Date.now()}`;
    $("#textbookPageImage").classList.toggle("hidden", !page.image_url);
    $("#textbookPageImage").dataset.caption = `${book.title} · 第 ${page.page_number}/${book.page_count} 页`;
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

  async function askTextbookAi(message = "") {
    const hint = $("#textbookHint");
    const content = (message || $("#textbookQuestion")?.value || "").trim();
    if (!state.textbookId) {
      if (hint) hint.textContent = "请先选择教材。";
      return;
    }
    if (!content) {
      if (hint) hint.textContent = "请输入要问的问题。";
      return;
    }
    state.textbookChat.push({ role: "user", content });
    renderTextbookChat();
    if ($("#textbookQuestion")) $("#textbookQuestion").value = "";
    if (hint) hint.textContent = "AI 正在精读当前页...";
    const data = await api("/api/textbooks/chat", {
      method: "POST",
      body: JSON.stringify({
        textbook_id: state.textbookId,
        page_number: state.textbookPage,
        paragraph_index: state.textbookParagraph,
        message: content,
        history: state.textbookChat,
      }),
    });
    state.textbookChat.push({ role: "assistant", content: data.answer || "" });
    renderTextbookChat();
    if (hint) hint.textContent = data.has_key ? "已完成。可以继续追问，或压缩导入记忆。" : "未配置 API，已返回本地提示。";
  }

  async function saveTextbookMemory() {
    const hint = $("#textbookHint");
    if (!state.textbookId || !state.textbookChat.length) {
      if (hint) hint.textContent = "先完成一轮教材精读对话，再导入记忆。";
      return;
    }
    if (hint) hint.textContent = "正在压缩对话并写入老师记忆...";
    const data = await api("/api/textbooks/memory", {
      method: "POST",
      body: JSON.stringify({
        textbook_id: state.textbookId,
        page_number: state.textbookPage,
        paragraph_index: state.textbookParagraph,
        history: state.textbookChat,
      }),
    });
    if (hint) hint.textContent = `已导入老师记忆：${data.memory.content.slice(0, 48)}...`;
  }

  async function deleteTextbook(id) {
    const book = state.textbooks.find((item) => item.id === id);
    const name = book ? book.title || book.filename : "这本教材";
    if (!confirm(`确定删除「${name}」吗？这会删除教材 PDF、页图和精读对话记录。`)) return;
    await api(`/api/textbooks/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (state.textbookId === id) {
      state.textbookId = "";
      state.textbookChat = [];
    }
    await loadTextbooks();
    renderTextbookChat();
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
      const form = new FormData();
      form.append("file", file);
      form.append("title", formEl.querySelector('[name="title"]').value);
      form.append("subject", formEl.querySelector('[name="subject"]').value);
      status.textContent = "正在导入教材并按页建立索引...";
      try {
        const data = await api("/api/textbooks/upload", { method: "POST", body: form });
        status.textContent = `已导入「${data.title}」共 ${data.page_count} 页。`;
        formEl.reset();
        state.textbookId = data.textbook_id;
        state.textbookPage = 1;
        state.textbookChat = [];
        await loadTextbooks();
        await loadTextbookPage();
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
      const open = event.target.closest("[data-open-textbook]");
      if (open) {
        state.textbookId = open.dataset.openTextbook;
        state.textbookPage = 1;
        state.textbookParagraph = 0;
        state.textbookChat = [];
        if ($("#textbookPageInput")) $("#textbookPageInput").value = 1;
        await loadTextbookPage();
        renderTextbookChat();
        return;
      }
      const del = event.target.closest("[data-delete-textbook]");
      if (del) await deleteTextbook(del.dataset.deleteTextbook);
    });
    on("#loadTextbookPage", "click", async () => {
      state.textbookChat = [];
      await loadTextbookPage();
      renderTextbookChat();
    });
    on("#textbookPageInput", "keydown", async (event) => {
      if (event.key === "Enter") {
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
      updateTextbookChatBadge();
    });
    on("#textbookPageImage", "dblclick", () => {
      const img = $("#textbookPageImage");
      if (!img || img.classList.contains("hidden") || !img.src) return;
      if (window.openLightbox) window.openLightbox(img.src, img.dataset.caption || "教材页截图");
    });
    on("#askTextbookAi", "click", () => askTextbookAi());
    on("#explainSelectedParagraph", "click", () => {
      const msg = state.textbookParagraph
        ? `请逐句解释第 ${state.textbookPage} 页第 ${state.textbookParagraph} 段，说明关键概念、公式来源和容易误解的地方。`
        : `请解释第 ${state.textbookPage} 页的核心内容，并指出我应该重点理解什么。`;
      askTextbookAi(msg);
    });
    on("#saveTextbookMemory", "click", saveTextbookMemory);
    on("#clearTextbookChat", "click", () => {
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
