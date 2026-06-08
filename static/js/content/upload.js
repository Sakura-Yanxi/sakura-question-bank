(function () {
  let isBound = false;

  function bindUploadForm(selector, documentKindValue) {
    const formEl = $(selector);
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
      form.append("document_kind", documentKindValue);
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
