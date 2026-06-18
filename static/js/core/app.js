const state = {
  questions: [],
  dashboardQuestions: [],
  dashboardStats: [],
  dashboardSubjectStats: [],
  documents: [],
  stats: [],
  subjectStats: [],
  categories: [],
  chapters: [],
  subjects: [],
  view: "dashboard",
  category: "",
  status: "",
  documentId: "",
  subject: "",
  chapter: "",
  dashboardSubject: "",
  dashboardDocumentId: "",
  search: "",
  coach: null,
  mistakeQuestions: [],
  mistakeCategories: [],
  mistakeChapters: [],
  mistakeSubjects: [],
  mistakeDocumentId: "",
  mistakeSubject: "",
  mistakeSubjectAuto: false,
  mistakeCategory: "",
  mistakeChapter: "",
  mistakeChaptersSelected: [],
  mistakeStatus: "",
  selectedMistakes: new Set(),
  dailyRules: [],
  textbooks: [],
  textbookId: "",
  textbookPage: 1,
  textbookPdfPage: 1,
  textbookParagraph: 0,
  textbookChat: [],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const META_TAGS = ["计算失误", "公式遗忘", "逻辑死角", "题意理解偏差"];

document.body.dataset.view = state.view;

function on(selector, eventName, handler) {
  const element = $(selector);
  if (element) element.addEventListener(eventName, handler);
}

function onEach(selectors, eventName, handler) {
  selectors.forEach((selector) => on(selector, eventName, handler));
}

function typesetMath(root = document.body) {
  if (window.MathJax?.typesetPromise) {
    if (window.MathJax.typesetClear) window.MathJax.typesetClear([root]);
    window.MathJax.typesetPromise([root]).catch(() => {});
  }
}

function markdownLineToHtml(line) {
  let text = escapeHtml(line.trim());
  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  if (!text) return "";
  if (/^---+$/.test(text)) return "<hr />";
  const heading = text.match(/^(#{1,4})\s+(.+)$/);
  if (heading) {
    const level = Math.min(4, heading[1].length + 2);
    return `<h${level}>${heading[2]}</h${level}>`;
  }
  if (/^[-*]\s+/.test(text)) return `<li>${text.replace(/^[-*]\s+/, "")}</li>`;
  if (/^\d+\.\s+/.test(text)) return `<li>${text.replace(/^\d+\.\s+/, "")}</li>`;
  return `<p>${text}</p>`;
}

function normalizeLatexText(text) {
  return String(text || "");
}

function markdownToHtml(text) {
  const source = normalizeLatexText(text);
  const mathBlocks = [];
  const protectedSource = source.replace(/(\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\])/g, (block) => {
    const token = `@@MATH_BLOCK_${mathBlocks.length}@@`;
    mathBlocks.push(block);
    return token;
  });
  const lines = protectedSource.split(/\r?\n/);
  const html = [];
  let list = [];
  const flushList = () => {
    if (!list.length) return;
    html.push(`<ul>${list.join("")}</ul>`);
    list = [];
  };
  for (const line of lines) {
    const mathToken = line.trim().match(/^@@MATH_BLOCK_(\d+)@@$/);
    if (mathToken) {
      flushList();
      html.push(`<div class="math-block">${escapeHtml(mathBlocks[Number(mathToken[1])] || "")}</div>`);
      continue;
    }
    const rendered = markdownLineToHtml(line);
    if (!rendered) {
      flushList();
      continue;
    }
    if (rendered.startsWith("<li>")) {
      list.push(rendered);
    } else {
      flushList();
      html.push(rendered);
    }
  }
  flushList();
  return html.join("").replace(/@@MATH_BLOCK_(\d+)@@/g, (_, index) => {
    return `<span class="math-inline-block">${escapeHtml(mathBlocks[Number(index)] || "")}</span>`;
  });
}

function renderAiOutput(selector, text, placeholder = "") {
  const node = typeof selector === "string" ? $(selector) : selector;
  if (!node) return;
  const raw = String(text || placeholder || "");
  node.dataset.rawOutput = raw;
  node.innerHTML = markdownToHtml(raw);
  node.classList.add("mathjax-container");
  typesetMath(node);
}

function statusClass(status) {
  if (status === "做错") return "wrong";
  if (status === "需复习" || status === "半会") return "review";
  return "";
}

function reviewTag(q) {
  if (!q.ever_wrong) return "";
  if (q.mastered_at) return `<span class="tag memory mastered">已掌握</span>`;
  if (q.next_review_at) return `<span class="tag memory">${q.retention_stage || q.review_stage || 0}天 · ${q.next_review_at}</span>`;
  return `<span class="tag memory">曾错题</span>`;
}

function isActiveMistake(q) {
  return ["做错", "需复习", "半会"].includes(q.status) || (q.ever_wrong && !q.mastered_at);
}

function selectedMetaTags() {
  return $$(".meta-check input:checked").map((input) => input.value);
}

function metaTagControls(selected = []) {
  return META_TAGS.map(
    (tag) => `
      <label class="meta-check">
        <input type="checkbox" value="${tag}" ${selected.includes(tag) ? "checked" : ""} />
        <span>${tag}</span>
      </label>`
  ).join("");
}

function documentLabel(doc) {
  const title = doc.title || doc.filename || "做题本";
  const kind = doc.document_kind || "做题本";
  return `${title} · ${kind}`;
}

function documentKind(doc) {
  return doc.document_kind || "做题本";
}

function questionKind(question) {
  return question.document_kind || "做题本";
}

function snippet(text) {
  const clean = (text || "这页 PDF 没有可提取文字，可直接查看题图并手动标注。").replace(/\s+/g, " ").trim();
  return clean.length > 86 ? `${clean.slice(0, 86)}...` : clean;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  // Read as text first: a non-2xx response may be an HTML 500 page, a proxy 502, an auth
  // redirect, or an empty body — calling res.json() on those throws an opaque SyntaxError
  // and hides the real server error from the caller.
  const raw = await res.text();
  let data = {};
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch (err) {
      if (!res.ok) throw new Error(`请求失败（${res.status} ${res.statusText || ""}）`.trim());
      throw new Error("服务器返回了无法解析的响应。");
    }
  }
  if (!res.ok) throw new Error(data.error || `请求失败（${res.status} ${res.statusText || ""}）`.trim());
  return data;
}

async function loadDocuments() {
  const data = await api("/api/documents");
  state.documents = data.documents;
  state.subjects = data.subjects;
  renderDocumentFilters();
  if (window.SakuraDocuments) window.SakuraDocuments.render();
  else if (window.renderDocuments) window.renderDocuments();
}

async function loadQuestions() {
  if (window.SakuraLibrary) await window.SakuraLibrary.load();
}

async function refresh() {
  await loadDocuments();
  if ($("#textbookList") && window.SakuraTextbook) await window.SakuraTextbook.load();
  if ($("#dailyRuleDocument") && window.SakuraDaily) await window.SakuraDaily.populateFilters();
  await loadDashboardData();
  if (state.view === "library" || state.view === "mockPapers") await loadQuestions();
  if (state.view === "mistakes") await loadMistakes();
}

function hasActiveLibraryFilter() {
  if (window.SakuraLibrary) return window.SakuraLibrary.hasActiveFilter();
  return Boolean(state.category || state.status || state.documentId || state.subject || state.chapter || (canSearchLibrary() && state.search));
}

function canSearchLibrary() {
  if (window.SakuraLibrary) return window.SakuraLibrary.canSearch();
  return Boolean(state.documentId || state.subject || state.status);
}

async function loadDashboardData() {
  if (window.SakuraDashboard) await window.SakuraDashboard.load();
}

async function loadMistakes() {
  if (window.SakuraMistakes) await window.SakuraMistakes.load();
}

function hasActiveMistakeFilter() {
  if (window.SakuraMistakes) return window.SakuraMistakes.hasActiveFilter();
  return Boolean(
    state.mistakeDocumentId ||
      state.mistakeSubject ||
      state.mistakeCategory ||
      state.mistakeChapter ||
      (Array.isArray(state.mistakeChaptersSelected) && state.mistakeChaptersSelected.length)
  );
}

function renderAll() {
  if (window.SakuraLibrary) window.SakuraLibrary.render();
}

function renderDocumentFilters() {
  $("#subjectSuggestions").innerHTML = state.subjects.map((subject) => `<option value="${escapeAttr(subject)}"></option>`).join("");
  const chapterDocs = state.documents.filter((doc) => documentKind(doc) !== "模拟卷");
  $("#statsDocumentSelect").innerHTML = chapterDocs
    .map((doc) => `<option value="${escapeAttr(doc.id)}">${escapeHtml(documentLabel(doc))}</option>`)
    .join("");
}

// Dashboard filters, cards and distribution stats live in /static/js/content/dashboard.js

// Library filters, search, locate controls and question grids live in /static/js/content/library.js

function updateSearchBoxState() {
  if (window.SakuraLibrary) window.SakuraLibrary.updateSearchBoxState();
}

function renderMistakeGrid() {
  if (window.SakuraMistakes) window.SakuraMistakes.renderGrid();
}

function renderMistakeSelectionHint() {
  if (window.SakuraMistakes) window.SakuraMistakes.renderSelectionHint();
}

// Profile and teacher-memory archive dialogs live in /static/js/review/archives.js

// Mistake filters, focused wrong/review toggles and mistake grid live in /static/js/review/mistakes.js

// Document card rendering and management actions live in /static/js/content/documents.js

// Textbook intensive-reading helpers live in /static/js/content/textbook.js

function renderQuestionGrid(target, questions, emptyText = "还没有题目。先从左侧上传 PDF，或清空筛选条件。", options = {}) {
  if (window.SakuraLibrary) window.SakuraLibrary.renderGrid(target, questions, emptyText, options);
}

async function updateQuestion(id, payload) {
  if (window.SakuraLibrary) await window.SakuraLibrary.update(id, payload);
}

async function deleteQuestion(id) {
  if (window.SakuraLibrary) await window.SakuraLibrary.deleteQuestion(id);
}

// Question detail, crop tool and image lightbox live in /static/js/content/question_detail.js

// ==========================================================================
// 提醒打卡
// ==========================================================================
// Reminder/check-in/weather helpers live in /static/js/system/reminders.js
// AI chat/settings/memory helpers live in /static/js/ai/ai_chat.js

// Chapter statistics and wrong-reason radar chart live in /static/js/review/chapter_stats.js

// Reflection summary/history helpers live in /static/js/review/reflection.js

// Daily practice and custom-rule helpers live in /static/js/review/daily.js

function setSelectOptions(selector, values, allLabel, current = "") {
  const el = $(selector);
  if (!el) return "";
  const safeValues = (values || []).filter((value) => value !== null && value !== undefined && String(value).trim() !== "");
  const hasCurrent = current && safeValues.some((value) => String(value) === String(current));
  const nextValue = hasCurrent ? current : "";
  el.innerHTML = `<option value="">${escapeHtml(allLabel)}</option>${safeValues
    .map((value) => `<option value="${escapeAttr(value)}" ${String(value) === String(nextValue) ? "selected" : ""}>${escapeHtml(value)}</option>`)
    .join("")}`;
  el.value = nextValue;
  return nextValue;
}

function setSelectLocked(selector, label) {
  const el = $(selector);
  if (!el) return;
  el.innerHTML = `<option value="">${escapeHtml(label)}</option>`;
  el.value = "";
  el.disabled = true;
}

function unlockSelect(selector) {
  const el = $(selector);
  if (el) el.disabled = false;
}

function selectedOptionText(selector, fallback) {
  const el = $(selector);
  if (!el) return fallback;
  return el.selectedOptions?.[0]?.textContent?.trim() || fallback;
}

// Daily practice rule form/rendering lives in /static/js/review/daily.js

// Backup/migration helpers live in /static/js/system/backup.js

// Learning profile / AI coach helpers live in /static/js/ai/coach.js

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function escapeAttr(text) {
  return escapeHtml(text).replace(/'/g, "&#39;");
}

async function gotoLibraryFilter(filter) {
  if (window.SakuraLibrary) await window.SakuraLibrary.gotoFilter(filter);
}

function setView(view) {
  state.view = view;
  document.body.dataset.view = view;
  $$(".view").forEach((node) => node.classList.toggle("active", node.id === view));
  $$(".nav-btn").forEach((node) => node.classList.toggle("active", node.dataset.view === view));
  const titles = {
    dashboard: ["学习总览", "按科目、做题本和知识点追踪练习情况。"],
    documents: ["做题本", "上传和维护章节练习、专项题册等做题本资料。"],
    mockPapers: ["模拟卷", "上传和维护整套试卷，模拟卷与做题本同级管理。"],
    textbook: ["教材精读", "上传教材 PDF，按页/段落让 AI 逐句解释并沉淀记忆。"],
    chapterStats: ["章节统计", "用章节正确率看清每套做题本里的薄弱部分。"],
    library: ["总题库", "按做题本、科目、知识点和状态检索题目。"],
    mistakes: ["错题本", "集中处理做错、半会和需要复习的题目。"],
    reflection: ["总结反思", "按周或月复盘重难点、错题和后续规划。"],
    daily: ["每日练习", "优先从薄弱项和最近错题里安排练习。"],
    coach: ["学习档案", "基于真实做题记录生成统计、薄弱点证据和复习计划。"],
    aiChat: ["AI 学习教练", "测试 API、维护老师记忆，并把有效对话沉淀到学习档案。"],
    remind: ["提醒打卡", "云端/本地打卡、微信提醒设置与定时教程。"],
  };
  $("#viewTitle").textContent = titles[view][0];
  $("#viewSubtitle").textContent = titles[view][1];
  if (view === "daily" && window.SakuraDaily) window.SakuraDaily.load();
  if (view === "chapterStats" && window.SakuraChapterStats) window.SakuraChapterStats.load();
  if (view === "reflection" && window.SakuraReflection) window.SakuraReflection.load();
  if (view === "coach" && window.SakuraCoach) window.SakuraCoach.load();
  if (view === "aiChat" && window.loadAiChatPanel) window.loadAiChatPanel();
  if (view === "remind") { loadRemind(); loadWeatherSettings(); }
  if (view === "mistakes") loadMistakes();
  if (view === "textbook" && window.SakuraTextbook) window.SakuraTextbook.load();
  if (view === "library" || view === "mockPapers") loadQuestions();
  updateSearchBoxState();
}

// Book/mock upload form bindings live in /static/js/content/upload.js
// Library filters, search, locate controls and question grids live in /static/js/content/library.js
// Dashboard filter bindings live in /static/js/content/dashboard.js
// Mistake filter bindings live in /static/js/review/mistakes.js

// 回到顶部悬浮按钮
(function setupBackToTop() {
  const btn = $("#backToTop");
  const scroller = $(".main-content-wrapper");
  if (!btn || !scroller) return;
  scroller.addEventListener("scroll", () => {
    btn.classList.toggle("hidden", scroller.scrollTop < 320);
  });
  btn.addEventListener("click", () => scroller.scrollTo({ top: 0, behavior: "smooth" }));
})();

// Learning profile / coach bindings live in /static/js/ai/coach.js

// Reminder, notification, weather, and security bindings live in /static/js/system/reminders.js
if (window.SakuraReminderControls) window.SakuraReminderControls.bind();

// Mistake PDF export and selection bindings live in /static/js/review/mistake_export.js

// Daily practice bindings live in /static/js/review/daily.js
// Backup/migration bindings live in /static/js/system/backup.js

document.body.addEventListener("click", async (event) => {
  const nav = event.target.closest(".nav-btn");
  if (nav) setView(nav.dataset.view);

  const open = event.target.closest("[data-open]");
  if (open && window.openDetail) window.openDetail(open.dataset.open);

  const status = event.target.closest("[data-status]");
  if (status) {
    if (status.dataset.status === "做错") {
      if (window.openDetail) await window.openDetail(status.dataset.id, "做错");
      return;
    }
    await updateQuestion(status.dataset.id, { status: status.dataset.status });
  }

  const deleteQuestionBtn = event.target.closest("[data-delete-question]");
  if (deleteQuestionBtn) {
    await deleteQuestion(deleteQuestionBtn.dataset.deleteQuestion);
  }

  const deleteDocBtn = event.target.closest("[data-delete-doc]");
  if (deleteDocBtn) {
    if (window.SakuraDocuments) await window.SakuraDocuments.deleteDocument(deleteDocBtn.dataset.deleteDoc);
  }

  const editDocBtn = event.target.closest("[data-edit-doc]");
  if (editDocBtn) {
    if (window.SakuraDocuments) await window.SakuraDocuments.edit(editDocBtn.dataset.editDoc);
  }

  const viewDocBtn = event.target.closest("[data-view-doc]");
  if (viewDocBtn) {
    state.documentId = viewDocBtn.dataset.viewDoc;
    state.status = "";
    setView("library");
  }

  const statsDocBtn = event.target.closest("[data-stats-doc]");
  if (statsDocBtn) {
    setView("chapterStats");
    if (window.SakuraChapterStats) await window.SakuraChapterStats.load(statsDocBtn.dataset.statsDoc);
  }

  const rescanDocBtn = event.target.closest("[data-rescan-doc]");
  if (rescanDocBtn) {
    if (window.SakuraDocuments) await window.SakuraDocuments.rescan(rescanDocBtn.dataset.rescanDoc);
  }
});

loadCountdown();
loadQuote();
refresh();
if (window.SakuraQuestionDetail) window.SakuraQuestionDetail.setupLightbox();
if ($("#detailDialog")) {
  $("#detailDialog").addEventListener("close", () => {
    $("#detailDialog").classList.remove("archive-mode");
  });
}

async function loadCountdown() {
  try {
    const data = await api("/api/countdown");
    const el = document.getElementById("countdownText");
    if (el) el.innerHTML = data.today_formatted + " " + data.weekday + " · 距考研还有 <strong>" + data.days_left + "</strong> 天";
  } catch (e) {
    const el = document.getElementById("countdownText");
    if (el) el.textContent = "加载日期失败";
  }
}

async function loadQuote() {
  try {
    const data = await api("/api/quote");
    const el = document.getElementById("quoteText");
    if (el) el.textContent = data.quote;
  } catch (e) {
    const el = document.getElementById("quoteText");
    if (el) el.textContent = "You are more than what you have become.";
  }
}
