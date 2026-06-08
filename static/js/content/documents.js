(function () {
  function renderDocuments() {
    const books = state.documents.filter((doc) => documentKind(doc) !== "模拟卷");
    const mocks = state.documents.filter((doc) => documentKind(doc) === "模拟卷");
    renderDocumentGrid("#documentGrid", books, "还没有做题本。先在上方导入章节练习 PDF。");
    renderDocumentGrid("#mockDocumentGrid", mocks, "还没有模拟卷。先在上方导入整卷 PDF。");
  }

  function renderDocumentGrid(target, docs, emptyText) {
    const node = $(target);
    if (!node) return;
    node.innerHTML =
      docs
        .map((doc) => documentCard(doc))
        .join("") || `<p class="empty-note">${escapeHtml(emptyText)}</p>`;
  }

  function documentCard(doc) {
    const kind = documentKind(doc);
    const rescanLabel = kind === "模拟卷" ? "重扫整卷" : "重扫章节";
    const title = doc.title || doc.filename || "未命名资料";
    const subject = doc.subject || "未分类";
    const id = doc.id || "";
    return `
        <article class="document-card">
          <div>
            <h3>${escapeHtml(title)}</h3>
            <p>${escapeHtml(subject)} · ${escapeHtml(kind)} · ${doc.question_count || 0} 题 · 错题 ${doc.wrong_count || 0} · 需复习 ${doc.review_count || 0}</p>
            <span class="tag kind ${kind === "模拟卷" ? "mock" : "paper"}">${escapeHtml(kind)}</span>
            <p>${escapeHtml(doc.filename || "")}</p>
          </div>
          <div class="doc-actions">
            <button data-view-doc="${escapeAttr(id)}">查看</button>
            <button class="ghost" data-edit-doc="${escapeAttr(id)}">编辑</button>
            <button class="ghost" data-stats-doc="${escapeAttr(id)}">统计</button>
            <button class="ghost" data-rescan-doc="${escapeAttr(id)}">${rescanLabel}</button>
            <button class="danger" data-delete-doc="${escapeAttr(id)}">删除</button>
          </div>
        </article>`;
  }

  async function editDocument(id) {
    const doc = state.documents.find((item) => item.id === id);
    if (!doc) return;
    const kind = documentKind(doc);
    const dialog = $("#detailDialog");
    dialog.classList.remove("archive-mode");
    $("#detailContent").innerHTML = `
      <form class="document-editor" id="documentEditForm">
        <div class="panel-head">
          <div>
            <h2>编辑${escapeHtml(kind)}</h2>
            <p>只修改显示名称和科目，不会影响已导入题目、错题和复习记录。</p>
          </div>
          <button type="button" class="ghost" id="closeDocumentEdit">关闭</button>
        </div>
        <label>
          资料名称
          <input id="editDocumentTitle" value="${escapeAttr(doc.title || doc.filename || "")}" maxlength="120" required />
        </label>
        <label>
          科目/分类
          <input id="editDocumentSubject" value="${escapeAttr(doc.subject || "未分类")}" maxlength="60" list="subjectSuggestions" />
        </label>
        <label>
          资料类型
          <select id="editDocumentKind">
            <option value="做题本" ${doc.document_kind !== "模拟卷" ? "selected" : ""}>做题本</option>
            <option value="模拟卷" ${doc.document_kind === "模拟卷" ? "selected" : ""}>模拟卷</option>
          </select>
        </label>
        <p class="edit-file-name">原始文件：${escapeHtml(doc.filename || "")}</p>
        <div class="detail-actions">
          <button type="submit">保存修改</button>
          <button type="button" class="ghost" id="cancelDocumentEdit">取消</button>
        </div>
      </form>`;
    dialog.showModal();
    $("#closeDocumentEdit").onclick = () => dialog.close();
    $("#cancelDocumentEdit").onclick = () => dialog.close();
    $("#documentEditForm").onsubmit = async (event) => {
      event.preventDefault();
      try {
        await api(`/api/documents/${encodeURIComponent(id)}`, {
          method: "PATCH",
          body: JSON.stringify({
            title: $("#editDocumentTitle").value.trim(),
            subject: $("#editDocumentSubject").value.trim() || "未分类",
            document_kind: $("#editDocumentKind").value,
          }),
        });
        dialog.close();
        await refresh();
      } catch (error) {
        alert(error.message);
      }
    };
  }

  async function deleteDocument(id) {
    const doc = state.documents.find((item) => item.id === id);
    const name = doc ? doc.title || doc.filename : "这套做题本";
    const kind = doc ? documentKind(doc) : "做题本";
    if (!confirm(`确定删除「${name}」吗？这会删除整套${kind}、题目记录和页面图片。`)) return;
    await api(`/api/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (state.documentId === id) {
      state.documentId = "";
      state.category = "";
      state.chapter = "";
    }
    if (state.dashboardDocumentId === id) state.dashboardDocumentId = "";
    await refresh();
  }

  async function rescanDocument(id) {
    const doc = state.documents.find((item) => item.id === id);
    const name = doc ? doc.title || doc.filename : "这套做题本";
    const kind = doc ? documentKind(doc) : "做题本";
    const scanLabel = kind === "模拟卷" ? "整卷" : "章节";
    if (!confirm(`重新扫描「${name}」的页眉/右上角${scanLabel}吗？这不会调用 AI，也不会消耗 token。`)) return;
    const result = await api(`/api/documents/${encodeURIComponent(id)}/rescan-chapters`, { method: "POST", body: "{}" });
    alert(`已重扫 ${result.pages} 页，更新 ${result.updated} 条题目记录。`);
    await refresh();
  }

  window.renderDocuments = renderDocuments;
  window.SakuraDocuments = {
    render: renderDocuments,
    edit: editDocument,
    deleteDocument,
    rescan: rescanDocument,
  };

  renderDocuments();
})();
