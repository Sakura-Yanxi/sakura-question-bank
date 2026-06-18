const fs = require("fs");
const vm = require("vm");

URL.createObjectURL = () => "blob:test";
URL.revokeObjectURL = () => {};

const elements = new Map();

function element(id) {
  if (!elements.has(id)) {
    elements.set(id, {
      id,
      value: "",
      textContent: "",
      innerHTML: "",
      disabled: false,
      classList: { add() {}, remove() {}, toggle() {} },
      addEventListener() {},
    });
  }
  return elements.get(id);
}

function chaptersFromPicker() {
  const html = element("mistakeChapterFilter").innerHTML;
  return [...html.matchAll(/<option value="([^"]+)"/g)]
    .map((match) => match[1])
    .filter(Boolean);
}

function activeChaptersFromPicker() {
  return [...context.state.mistakeChaptersSelected];
}

const apiCalls = [];
const downloads = [];
const appendedElements = [];
let pendingDownload = null;
const questions = [
  { id: "a".repeat(32), chapter: "第一章", status: "做错" },
  { id: "b".repeat(32), chapter: "第二章", status: "半会" },
  { id: "c".repeat(32), chapter: "第三章", status: "做错" },
  { id: "d".repeat(32), chapter: "第三章", status: "做对", ever_wrong: true, mastered_at: "" },
  { id: "e".repeat(32), chapter: "第三章", status: "做错", ever_wrong: true, mastered_at: "" },
];

const context = {
  console,
  state: {
    documents: [{ id: "doc1", title: "同一本练习册", subject: "高数" }],
    subjects: ["高数"],
    mistakeQuestions: [],
    mistakeCategories: [],
    mistakeChapters: [],
    mistakeSubjects: [],
    mistakeDocumentId: "doc1",
    mistakeSubject: "高数",
    mistakeCategory: "",
    mistakeChapter: "",
    mistakeChaptersSelected: [],
    mistakeStatus: "",
    selectedMistakes: new Set(),
    view: "mistakes",
  },
  window: {},
  document: {
    querySelector(selector) {
      return selector.startsWith("#") ? element(selector.slice(1)) : null;
    },
    getElementById(id) {
      return appendedElements.find((node) => node.id === id) || null;
    },
    createElement(tagName) {
      return {
        tagName: String(tagName || "").toUpperCase(),
        click() {},
        remove() {},
        style: {},
        set href(value) {
          this._href = value;
        },
        get href() {
          return this._href;
        },
        set src(value) {
          this._src = value;
        },
        get src() {
          return this._src;
        },
      };
    },
    body: {
      appendChild(node) {
        appendedElements.push(node);
      },
    },
  },
  navigator: { userAgent: "node", platform: "Win32", maxTouchPoints: 0 },
  URL,
  URLSearchParams,
  fetch: async (url) => {
    downloads.push(url);
    if (pendingDownload) await pendingDownload;
    return {
      ok: true,
      headers: { get: () => 'attachment; filename="mistakes.pdf"' },
      blob: async () => Buffer.from("pdf"),
    };
  },
  alert(message) {
    throw new Error(`unexpected alert: ${message}`);
  },
  confirm() {
    return true;
  },
  api: async (url) => {
    apiCalls.push(url);
    const parsed = new URL(url, "http://localhost");
    const selected = parsed.searchParams.getAll("chapter");
    const filtered = selected.length ? questions.filter((q) => selected.includes(q.chapter)) : questions;
    return {
      questions: filtered,
      categories: ["极限"],
      chapters: ["第一章", "第二章", "第三章"],
      subjects: ["高数"],
    };
  },
  on(selector, eventName, handler) {
    element(selector.slice(1)).handler = handler;
  },
  escapeAttr(value) {
    return String(value).replaceAll('"', "&quot;");
  },
  escapeHtml(value) {
    return String(value);
  },
  documentLabel(doc) {
    return doc.title;
  },
  unlockSelect(selector) {
    element(selector.slice(1)).disabled = false;
  },
  setSelectLocked(selector, label) {
    const el = element(selector.slice(1));
    el.innerHTML = `<option value="">${label}</option>`;
    el.value = "";
    el.disabled = true;
  },
  setSelectOptions(selector, values, _allLabel, current = "") {
    element(selector.slice(1)).options = values;
    return values.includes(current) ? current : "";
  },
  isActiveMistake(q) {
    return ["做错", "半会", "需复习"].includes(q.status) || (q.ever_wrong && !q.mastered_at);
  },
  renderQuestionGrid() {},
  questionKind() {
    return "练习册";
  },
  hasActiveMistakeFilter: undefined,
  renderMistakeGrid: undefined,
  renderMistakeSelectionHint: undefined,
  setTimeout(callback) {
    callback();
  },
};

context.$ = context.document.querySelector.bind(context.document);
context.window = context;
vm.createContext(context);

vm.runInContext(fs.readFileSync("static/js/review/mistakes.js", "utf8"), context);
vm.runInContext(fs.readFileSync("static/js/review/mistake_export.js", "utf8"), context);

async function selectChapter(chapter) {
  const picker = element("mistakeChapterFilter");
  picker.value = chapter;
  await picker.handler({ target: picker });
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

(async () => {
  await context.SakuraMistakes.load();
  await selectChapter("第一章");
  await selectChapter("第二章");
  context.state.selectedMistakes.add("a".repeat(32));
  await selectChapter("第三章");
  context.state.selectedMistakes.add("c".repeat(32));
  await context.SakuraMistakeExport.exportPdf();

  const active = activeChaptersFromPicker();
  const chapters = chaptersFromPicker();
  const exportUrl = downloads.at(-1) || "";
  const exported = new URL(exportUrl, "http://localhost");
  const exportedChapters = exported.searchParams.getAll("chapter");
  const exportedIds = exported.searchParams.get("ids") || "";

  if (chapters.join(",") !== "第一章,第二章,第三章") {
    throw new Error(`chapter picker lost options: ${chapters.join(",")}`);
  }
  if (apiCalls.length !== 4) {
    throw new Error(`expected one question request per load, got ${apiCalls.length}`);
  }
  if (active.join(",") !== "第一章,第二章,第三章") {
    throw new Error(`chapter picker lost selected chapters: ${active.join(",")}`);
  }
  if (exportedChapters.length !== 0) {
    throw new Error(`checked export should prefer selected ids, got chapters=${exportedChapters.join(",")}`);
  }
  if (exportedIds !== `${"a".repeat(32)},${"c".repeat(32)}`) {
    throw new Error(`selected ids from multiple chapters were not preserved: ${exportedIds}`);
  }

  await selectChapter("第三章");
  const afterDeselect = activeChaptersFromPicker();
  if (afterDeselect.join(",") !== "第一章,第二章") {
    throw new Error(`deselecting a chapter should keep the other chapters: ${afterDeselect.join(",")}`);
  }
  if (context.state.selectedMistakes.has("c".repeat(32))) {
    throw new Error("deselecting a chapter should remove checked questions from that chapter");
  }
  await selectChapter("第三章");
  context.state.selectedMistakes.add("c".repeat(32));

  await selectChapter("");
  if (activeChaptersFromPicker().length !== 0) {
    throw new Error("choosing all chapters should clear explicit chapter selections");
  }
  if (context.state.selectedMistakes.size !== 0) {
    throw new Error("choosing all chapters should clear old checked questions");
  }
  await selectChapter("第一章");
  await selectChapter("第二章");
  await selectChapter("第三章");

  context.state.selectedMistakes.clear();
  await context.SakuraMistakeExport.exportPdf();
  const filteredExport = new URL(downloads.at(-1), "http://localhost");
  const filterChapters = filteredExport.searchParams.getAll("chapter");
  if (filterChapters.join(",") !== "第一章,第二章,第三章") {
    throw new Error(`filter export lost chapters: ${filterChapters.join(",")}`);
  }

  context.state.mistakeStatus = "做错";
  await context.SakuraMistakes.load();
  const lastQuestionUrl = new URL(apiCalls.at(-1), "http://localhost");
  if (lastQuestionUrl.searchParams.get("status") !== "做错") {
    throw new Error("wrong-only mistake filter should be sent to /api/questions");
  }

  context.state.mistakeStatus = "review";
  await context.SakuraMistakes.load();
  const reviewQuestionUrl = new URL(apiCalls.at(-1), "http://localhost");
  if (reviewQuestionUrl.searchParams.get("status_group") !== "review") {
    throw new Error("review mistake filter should be sent to /api/questions");
  }
  const reviewIds = context.state.mistakeQuestions.map((q) => q.id).join(",");
  if (reviewIds !== `${"b".repeat(32)},${"d".repeat(32)}`) {
    throw new Error(`review filter should keep review/ever-wrong items but exclude current wrong items: ${reviewIds}`);
  }
  context.state.selectedMistakes.clear();
  await context.SakuraMistakeExport.exportPdf();
  const reviewExport = new URL(downloads.at(-1), "http://localhost");
  if (reviewExport.searchParams.get("status_group") !== "review") {
    throw new Error("review export should keep status_group=review");
  }
  context.state.mistakeStatus = "";
  context.state.mistakeChaptersSelected = ["第一章", "第二章", "第三章"];

  pendingDownload = deferred();
  const firstExport = context.SakuraMistakeExport.exportPdf();
  const secondExport = context.SakuraMistakeExport.exportPdf();
  if (!element("exportMistakes").disabled || !element("exportLibrary").disabled) {
    throw new Error("export buttons should be disabled during export");
  }
  if (downloads.length !== 4) {
    throw new Error(`double click should not start two exports, got ${downloads.length} downloads`);
  }
  pendingDownload.resolve();
  await firstExport;
  await secondExport;
  pendingDownload = null;
  if (element("exportMistakes").disabled || element("exportLibrary").disabled) {
    throw new Error("export buttons should be re-enabled after export");
  }

  context.navigator.userAgent = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)";
  context.navigator.platform = "iPad";
  context.state.selectedMistakes.clear();
  const beforeIpadDownloads = downloads.length;
  await context.SakuraMistakeExport.exportPdf();
  if (downloads.length !== beforeIpadDownloads) {
    throw new Error("iPad iframe fallback should not fetch the PDF before triggering download");
  }
  const frame = context.document.getElementById("sakuraDownloadFrame");
  if (!frame || !frame.src) {
    throw new Error("iPad export should fall back to a hidden download iframe");
  }
  const ipadExport = new URL(frame.src, "http://localhost");
  if (ipadExport.searchParams.get("download") !== "1") {
    throw new Error("iPad iframe export should keep download=1");
  }
  if (ipadExport.searchParams.getAll("chapter").join(",") !== "第一章,第二章,第三章") {
    throw new Error(`iPad iframe export lost selected chapters: ${ipadExport.searchParams.getAll("chapter").join(",")}`);
  }

  console.log("mistake export frontend check passed");
})();
