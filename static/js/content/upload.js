(function () {
  let isBound = false;

  function workbookPresets() {
    return window.SakuraWorkbookPresets;
  }

  function chooseBookPreset(file) {
    return new Promise((resolve) => {
      const existing = document.querySelector(".workbook-preset-dialog");
      if (existing) existing.remove();

      const presets = workbookPresets().all();
      const recommended = workbookPresets().recommendedForFilename(file?.name || "");
      const dialog = document.createElement("dialog");
      dialog.className = "workbook-preset-dialog";
      dialog.innerHTML = `
        <form method="dialog" class="workbook-preset-panel">
          <div class="workbook-preset-head">
            <div>
              <h3>选择做题本来源</h3>
              <p>${escapeHtml(file?.name || "当前 PDF")}</p>
            </div>
            <button type="button" class="ghost icon-only workbook-preset-close" title="关闭"><i data-lucide="x"></i></button>
          </div>
          <div class="workbook-preset-options">
            ${presets.map((preset) => `
              <button type="button" class="workbook-preset-option ${preset.value === recommended.value ? "recommended" : ""}" data-preset="${escapeAttr(preset.value)}">
                <strong>${escapeHtml(preset.label)}</strong>
                <span>${escapeHtml(preset.hint)}</span>
              </button>
            `).join("")}
          </div>
        </form>`;

      document.body.appendChild(dialog);
      window.lucide?.createIcons?.();

      let settled = false;
      function finish(value) {
        if (settled) return;
        settled = true;
        dialog.close();
        dialog.remove();
        resolve(value);
      }

      dialog.querySelector(".workbook-preset-close").addEventListener("click", () => finish(""));
      dialog.querySelectorAll("[data-preset]").forEach((button) => {
        button.addEventListener("click", () => finish(button.dataset.preset || ""));
      });
      dialog.addEventListener("cancel", (event) => {
        event.preventDefault();
        finish("");
      });
      dialog.showModal();
    });
  }

  function bindUploadForm(selector, documentKindValue) {
    const formEl = $(selector);
    if (!formEl) return;
    formEl.addEventListener("submit", async (event) => {
      event.preventDefault();
      const fileInput = formEl.querySelector('[name="file"]');
      const status = formEl.querySelector(".upload-status");
      const file = fileInput.files[0];
      if (!file) return;

      let chapterRule = "";
      if (documentKindValue === "做题本") {
        chapterRule = await chooseBookPreset(file);
        if (!chapterRule) {
          status.textContent = "已取消导入。";
          return;
        }
      }

      const form = new FormData();
      form.append("file", file);
      form.append("title", formEl.querySelector('[name="title"]').value);
      form.append("subject", formEl.querySelector('[name="subject"]').value);
      form.append("document_kind", documentKindValue);
      if (chapterRule) form.append("chapter_rule", chapterRule);
      form.append("start_page", formEl.querySelector('[name="start_page"]').value);
      form.append("end_page", formEl.querySelector('[name="end_page"]').value);
      const splitInput = formEl.querySelector('[name="split_questions"]');
      if (splitInput) form.append("split_questions", splitInput.checked ? "1" : "0");
      status.textContent = splitInput?.checked
        ? `正在导入${documentKindValue}，会尝试按题号自动切分...`
        : `正在导入${documentKindValue}，每页会生成一道题...`;
      try {
        const data = await api("/api/upload", { method: "POST", body: form });
        status.textContent = `已导入「${data.title}」共 ${data.page_count} 道题。`;
        formEl.reset();
        await refresh();
      } catch (error) {
        status.textContent = error.message;
      }
    });
  }

  function bindUploadForms() {
    if (isBound) return;
    isBound = true;
    bindUploadForm("#bookUploadForm", "做题本");
    bindUploadForm("#mockUploadForm", "模拟卷");
  }

  window.SakuraUpload = {
    bind: bindUploadForms,
  };

  bindUploadForms();
})();
