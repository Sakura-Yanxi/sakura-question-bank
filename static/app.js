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
  mistakeCategory: "",
  mistakeChapter: "",
  mistakeStatus: "",
  selectedMistakes: new Set(),
  dailyRules: [],
  textbooks: [],
  textbookId: "",
  textbookPage: 1,
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
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "请求失败");
  return data;
}

async function loadDocuments() {
  const data = await api("/api/documents");
  state.documents = data.documents;
  state.subjects = data.subjects;
  renderDocumentFilters();
  renderDocuments();
}

async function loadQuestions() {
  if (state.view === "library" && !hasActiveLibraryFilter()) {
    state.questions = [];
    state.stats = {};
    state.subjectStats = {};
    state.categories = [];
    state.chapters = [];
    renderAll();
    return;
  }
  const params = new URLSearchParams();
  if (state.category) params.set("category", state.category);
  if (state.status) params.set("status", state.status);
  if (state.documentId) params.set("document_id", state.documentId);
  if (state.subject) params.set("subject", state.subject);
  if (state.chapter) params.set("chapter", state.chapter);
  if (state.search) params.set("search", state.search);
  const data = await api(`/api/questions?${params}`);
  state.questions = data.questions;
  state.stats = data.stats;
  state.subjectStats = data.subject_stats;
  state.categories = data.categories;
  state.chapters = data.chapters;
  state.subjects = data.subjects;
  renderAll();
}

async function loadMistakes() {
  if (!hasActiveMistakeFilter()) {
    state.mistakeQuestions = [];
    state.mistakeCategories = [];
    state.mistakeChapters = [];
    state.mistakeSubjects = [];
    state.selectedMistakes.clear();
    renderMistakeFilters();
    renderMistakeGrid();
    return;
  }
  const params = new URLSearchParams();
  if (state.mistakeCategory) params.set("category", state.mistakeCategory);
  if (state.mistakeDocumentId) params.set("document_id", state.mistakeDocumentId);
  if (state.mistakeSubject) params.set("subject", state.mistakeSubject);
  if (state.mistakeChapter) params.set("chapter", state.mistakeChapter);
  const data = await api(`/api/questions?${params}`);
  state.mistakeQuestions = data.questions.filter(isActiveMistake).filter((q) => {
    if (state.mistakeStatus === "做错") return q.status === "做错";
    if (state.mistakeStatus === "review") return ["需复习", "半会"].includes(q.status) || (q.ever_wrong && !q.mastered_at);
    return true;
  });
  state.mistakeCategories = data.categories;
  state.mistakeChapters = data.chapters;
  state.mistakeSubjects = data.subjects;
  const visibleIds = new Set(state.mistakeQuestions.map((q) => q.id));
  state.selectedMistakes = new Set([...state.selectedMistakes].filter((id) => visibleIds.has(id)));
  renderMistakeFilters();
  renderMistakeGrid();
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
  return Boolean(state.category || state.status || state.documentId || state.subject || state.chapter || (canSearchLibrary() && state.search));
}

function canSearchLibrary() {
  return Boolean(state.documentId || state.subject || state.status);
}

function hasActiveMistakeFilter() {
  return Boolean(state.mistakeDocumentId || state.mistakeSubject || state.mistakeCategory || state.mistakeChapter);
}

async function loadDashboardData() {
  const docs = dashboardDocuments().filter((doc) => !state.dashboardSubject || doc.subject === state.dashboardSubject);
  if (state.dashboardDocumentId && !docs.some((doc) => doc.id === state.dashboardDocumentId)) {
    state.dashboardDocumentId = "";
  }
  const params = new URLSearchParams();
  if (state.dashboardSubject) params.set("subject", state.dashboardSubject);
  if (state.dashboardDocumentId) params.set("document_id", state.dashboardDocumentId);
  const data = await api(`/api/questions?${params}`);
  state.dashboardQuestions = data.questions;
  state.dashboardStats = data.stats;
  state.dashboardSubjectStats = data.subject_stats;
  renderDashboardFilters();
  renderDashboard();
}

function renderAll() {
  renderQuestionFilters();
  renderDashboard();
  const regularQuestions = state.questions.filter((q) => questionKind(q) !== "模拟卷");
  const mockQuestions = state.questions.filter((q) => questionKind(q) === "模拟卷");
  $("#questionCountBadge").textContent = `${regularQuestions.length} 题`;
  $("#mockCountBadge").textContent = `${mockQuestions.length} 题`;
  const libraryEmptyText = hasActiveLibraryFilter()
    ? "当前筛选下没有题目。可以换一个科目、资料或清空筛选条件。"
    : "请先选择科目、资料或掌握状态后查看题目。";
  renderQuestionGrid("#questionGrid", regularQuestions, libraryEmptyText);
  renderQuestionGrid("#mockQuestionGrid", mockQuestions, "还没有模拟卷题目。先上传整卷 PDF。");
  if (state.view === "mistakes") renderMistakeGrid();
}

function renderDocumentFilters() {
  $("#subjectSuggestions").innerHTML = state.subjects.map((subject) => `<option value="${subject}"></option>`).join("");
  const chapterDocs = state.documents.filter((doc) => documentKind(doc) !== "模拟卷");
  $("#statsDocumentSelect").innerHTML = chapterDocs
    .map((doc) => `<option value="${doc.id}">${documentLabel(doc)}</option>`)
    .join("");
}

function firstUploadDocuments() {
  const sorted = [...state.documents].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
  const seen = new Set();
  return sorted.filter((doc) => {
    const key = `${doc.subject}::${doc.document_kind || "做题本"}::${doc.title || doc.filename}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function dashboardDocuments() {
  return firstUploadDocuments().filter((doc) => documentKind(doc) !== "模拟卷");
}

function renderDashboardFilters() {
  $("#dashboardSubjectFilter").innerHTML = `<option value="">请选择科目</option>${state.subjects
    .map((subject) => `<option ${subject === state.dashboardSubject ? "selected" : ""}>${subject}</option>`)
    .join("")}`;
  const docs = dashboardDocuments().filter((doc) => !state.dashboardSubject || doc.subject === state.dashboardSubject);
  $("#dashboardDocumentFilter").innerHTML = `<option value="">请选择做题本</option>${docs
    .map((doc) => `<option value="${doc.id}" ${doc.id === state.dashboardDocumentId ? "selected" : ""}>${documentLabel(doc)}</option>`)
    .join("")}`;
}

function renderQuestionFilters() {
  const docs = state.documents.filter((doc) => !state.subject || doc.subject === state.subject);
  const scopedReady = Boolean(state.subject || state.documentId);
  updateSearchBoxState();
  $("#documentFilter").innerHTML = `<option value="">请选择资料</option>${docs
    .map((doc) => `<option value="${doc.id}" ${doc.id === state.documentId ? "selected" : ""}>${documentLabel(doc)}</option>`)
    .join("")}`;
  $("#subjectFilter").innerHTML = `<option value="">请选择科目</option>${state.subjects
    .map((subject) => `<option ${subject === state.subject ? "selected" : ""}>${subject}</option>`)
    .join("")}`;
  if (scopedReady) {
    unlockSelect("#categoryFilter");
    unlockSelect("#chapterFilter");
    $("#categoryFilter").innerHTML = `<option value="">全部知识点</option>${state.categories
      .map((category) => `<option ${category === state.category ? "selected" : ""}>${category}</option>`)
      .join("")}`;
    $("#chapterFilter").innerHTML = `<option value="">全部章节</option>${state.chapters
      .map((chapter) => `<option ${chapter === state.chapter ? "selected" : ""}>${chapter}</option>`)
      .join("")}`;
  } else {
    state.category = "";
    state.chapter = "";
    setSelectLocked("#categoryFilter", "请先选择科目或资料");
    setSelectLocked("#chapterFilter", "请先选择科目或资料");
  }
  const statusEmptyOption = $("#statusFilter option[value='']");
  if (statusEmptyOption) statusEmptyOption.textContent = "请选择掌握状态";
  $("#statusFilter").value = state.status;
}

function updateSearchBoxState() {
  const input = $("#searchInput");
  if (!input) return;
  const enabled = state.view === "library" && canSearchLibrary();
  input.disabled = !enabled;
  input.placeholder = enabled ? "在当前范围内搜题号、章节、错因或备注..." : "先选科目或资料后，在当前范围内搜索...";
  if (!enabled && state.search) {
    state.search = "";
    input.value = "";
  }
}

function setCoachMemoryBadge(version = 0, evidenceCount = 0) {
  const badge = $("#coachMemoryBadge");
  if (!badge) return;
  badge.textContent = evidenceCount ? `已建档 · ${evidenceCount} 条证据` : "未建档";
  badge.title = version ? `内部档案版本：v${version}` : "";
}

function openSimpleDialog(title, subtitle, bodyHtml) {
  const dialog = $("#detailDialog");
  dialog.classList.add("archive-mode");
  $("#detailContent").innerHTML = `
    <div class="archive-dialog">
      <div class="archive-dialog-head">
        <div>
          <h2>${escapeHtml(title)}</h2>
          <p>${escapeHtml(subtitle || "")}</p>
        </div>
      </div>
      ${bodyHtml}
    </div>`;
  if (!dialog.open) dialog.showModal();
  if (window.lucide) lucide.createIcons();
}

async function openProfileArchive() {
  openSimpleDialog("学习档案存档", "正在读取历史档案快照...", `<p class="empty-note">请稍等。</p>`);
  try {
    const data = await api("/api/profile/history");
    const profiles = data.profiles || [];
    const body = profiles.length
      ? `<div class="archive-list">${profiles.map((profile) => {
          const mastery = Math.round(Number(profile.avg_mastery || 0) * 100);
          const source = profile.source === "ai" ? "AI润色" : "本地统计";
          return `
            <article class="archive-item">
              <div class="archive-item-head">
                <strong>v${profile.version} · ${source}</strong>
                <span>${escapeHtml(profile.created_at || "")}</span>
              </div>
              <p>${escapeHtml(profile.headline || "本地统计档案")}</p>
              ${profile.pattern_summary ? `<small>${escapeHtml(profile.pattern_summary)}</small>` : ""}
              <div class="archive-meta">
                <span>${profile.evidence_count || 0} 条证据</span>
                <span>${profile.knowledge_count || 0} 个知识点</span>
                <span>平均掌握 ${mastery}%</span>
              </div>
            </article>`;
        }).join("")}</div>`
      : `<p class="empty-note">还没有历史档案。先点击「更新学习档案」。</p>`;
    openSimpleDialog("学习档案存档", "每次更新学习档案都会生成一个可追溯快照。", body);
  } catch (error) {
    openSimpleDialog("学习档案存档", "读取失败", `<p class="empty-note">${escapeHtml(error.message)}</p>`);
  }
}

async function openTeacherMemoryArchive() {
  openSimpleDialog("老师记忆", "正在读取主动导入的长期记忆...", `<p class="empty-note">请稍等。</p>`);
  try {
    const data = await api("/api/ai-chat/memory");
    const memories = data.memories || [];
    const body = `
      ${memories.length
        ? `<div class="archive-list memory-archive-list">${memories.map((memory) => `
            <article class="archive-item">
              <div class="archive-item-head">
                <strong>${escapeHtml(memory.source || "memory")}</strong>
                <span>${escapeHtml(memory.created_at || "")}</span>
              </div>
              <p>${escapeHtml(memory.content || "")}</p>
            </article>`).join("")}</div>`
        : `<p class="empty-note">还没有主动导入的老师记忆。可以在 AI 学习教练或教材精读里导入。</p>`}
      <div class="archive-actions">
        <button id="goAiMemoryPanel" class="ghost"><i data-lucide="messages-square"></i>去维护记忆</button>
      </div>`;
    openSimpleDialog("老师记忆", "这些内容会作为 AI 老师了解你的长期上下文。", body);
    const go = $("#goAiMemoryPanel");
    if (go) {
      go.onclick = () => {
        $("#detailDialog").close();
        setView("aiChat");
      };
    }
  } catch (error) {
    openSimpleDialog("老师记忆", "读取失败", `<p class="empty-note">${escapeHtml(error.message)}</p>`);
  }
}

function renderMistakeFilters() {
  const docs = state.documents.filter((doc) => !state.mistakeSubject || doc.subject === state.mistakeSubject);
  const doc = docs.find((item) => item.id === state.mistakeDocumentId);
  if (state.mistakeDocumentId && !doc) state.mistakeDocumentId = "";
  if (doc?.subject && !state.mistakeSubject) state.mistakeSubject = doc.subject;
  const subjects = state.mistakeSubjects.length ? state.mistakeSubjects : state.subjects;
  const scopedReady = Boolean(state.mistakeSubject && state.mistakeDocumentId);
  $("#mistakeDocumentFilter").innerHTML = `<option value="">请选择资料</option>${docs
    .map((doc) => `<option value="${doc.id}" ${doc.id === state.mistakeDocumentId ? "selected" : ""}>${documentLabel(doc)}</option>`)
    .join("")}`;
  $("#mistakeSubjectFilter").innerHTML = `<option value="">请选择科目</option>${subjects
    .map((subject) => `<option ${subject === state.mistakeSubject ? "selected" : ""}>${subject}</option>`)
    .join("")}`;
  if (scopedReady) {
    unlockSelect("#mistakeCategoryFilter");
    unlockSelect("#mistakeChapterFilter");
    $("#mistakeCategoryFilter").innerHTML = `<option value="">全部知识点</option>${state.mistakeCategories
      .map((category) => `<option ${category === state.mistakeCategory ? "selected" : ""}>${category}</option>`)
      .join("")}`;
    $("#mistakeChapterFilter").innerHTML = `<option value="">全部章节</option>${state.mistakeChapters
      .map((chapter) => `<option ${chapter === state.mistakeChapter ? "selected" : ""}>${chapter}</option>`)
      .join("")}`;
  } else {
    state.mistakeCategory = "";
    state.mistakeChapter = "";
    setSelectLocked("#mistakeCategoryFilter", "请先选择科目和资料");
    setSelectLocked("#mistakeChapterFilter", "请先选择科目和资料");
  }
}

function renderMistakeGrid() {
  $("#mistakeCountBadge").textContent = `${state.mistakeQuestions.length} 题`;
  const emptyText = hasActiveMistakeFilter()
    ? "当前筛选范围没有错题。"
    : "请先选择科目或资料，再按知识点、章节或错题状态导出。";
  renderQuestionGrid("#mistakeGrid", state.mistakeQuestions, emptyText, { selectable: true });
  renderMistakeSelectionHint();
}

function renderMistakeSelectionHint() {
  const selected = state.selectedMistakes.size;
  const total = state.mistakeQuestions.length;
  $("#focusWrong").classList.toggle("filter-active", state.mistakeStatus === "做错");
  $("#focusReview").classList.toggle("filter-active", state.mistakeStatus === "review");
  if (!hasActiveMistakeFilter()) {
    $("#mistakeSelectHint").textContent = "先选择科目或资料后再导出";
    return;
  }
  $("#mistakeSelectHint").textContent = selected ? `已选择 ${selected}/${total} 题` : `未勾选时导出当前 ${total} 道错题`;
}

function renderDashboard() {
  const dashboardReady = Boolean(state.dashboardSubject && state.dashboardDocumentId);
  const source = dashboardReady ? state.dashboardQuestions : [];
  const stats = dashboardReady ? state.dashboardStats : [];
  const total = source.length;
  const done = source.filter((q) => q.status && q.status !== "未做").length;
  const progress = total ? Math.round((done / total) * 100) : 0;
  const wrong = source.filter((q) => q.status === "做错").length;
  const review = source.filter((q) => ["需复习", "半会"].includes(q.status)).length;
  const weak = [...stats].sort((a, b) => (b.wrong || 0) - (a.wrong || 0))[0];

  $("#totalCount").textContent = total;
  if ($("#doneCount")) $("#doneCount").textContent = done;
  if ($("#progressRate")) $("#progressRate").textContent = `${progress}%`;
  if ($("#wrongCount")) $("#wrongCount").textContent = wrong;
  if ($("#reviewCount")) $("#reviewCount").textContent = review;
  if ($("#weakCategory")) {
    $("#weakCategory").textContent = dashboardReady ? (weak && weak.wrong ? weak.category : "暂无") : "请选择科目";
  }

  renderStats("#statsList", stats, "category", "选择科目和做题本后会显示对应知识点分布。");
  renderStats(
    "#subjectStatsList",
    dashboardReady ? state.dashboardSubjectStats : [],
    "subject",
    "选择科目和做题本后会显示科目分布。"
  );
}

function renderStats(target, stats, labelKey, emptyText) {
  const max = Math.max(...stats.map((item) => item.total), 1);
  $(target).innerHTML =
    stats
      .map(
        (item) => `
        <div class="stat-row">
          <strong>${item[labelKey]}</strong>
          <div class="bar"><span style="width: ${(item.total / max) * 100}%"></span></div>
          <span>${item.total} 题</span>
        </div>`
      )
      .join("") || `<p>${emptyText}</p>`;
}

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
      .join("") || `<p class="empty-note">${emptyText}</p>`;
}

function documentCard(doc) {
  const kind = documentKind(doc);
  const rescanLabel = kind === "模拟卷" ? "重扫整卷" : "重扫章节";
  return `
        <article class="document-card">
          <div>
            <h3>${doc.title || doc.filename}</h3>
            <p>${doc.subject} · ${kind} · ${doc.question_count || 0} 题 · 错题 ${doc.wrong_count || 0} · 需复习 ${doc.review_count || 0}</p>
            <span class="tag kind ${kind === "模拟卷" ? "mock" : "paper"}">${kind}</span>
            <p>${doc.filename}</p>
          </div>
          <div class="doc-actions">
            <button data-view-doc="${doc.id}">查看</button>
            <button class="ghost" data-edit-doc="${doc.id}">编辑</button>
            <button class="ghost" data-stats-doc="${doc.id}">统计</button>
            <button class="ghost" data-rescan-doc="${doc.id}">${rescanLabel}</button>
            <button class="danger" data-delete-doc="${doc.id}">删除</button>
          </div>
        </article>`;
}

// Textbook intensive-reading helpers live in /static/textbook.js

async function editDocument(id) {
  const doc = state.documents.find((item) => item.id === id);
  if (!doc) return;
  const kind = documentKind(doc);
  const dialog = $("#detailDialog");
  $("#detailContent").innerHTML = `
    <form class="document-editor" id="documentEditForm">
      <div class="panel-head">
        <div>
          <h2>编辑${kind}</h2>
          <p>只修改显示名称和科目，不会影响已导入题目、错题和复习记录。</p>
        </div>
        <button type="button" class="ghost" id="closeDocumentEdit">关闭</button>
      </div>
      <label>
        资料名称
        <input id="editDocumentTitle" value="${doc.title || doc.filename || ""}" maxlength="120" required />
      </label>
      <label>
        科目/分类
        <input id="editDocumentSubject" value="${doc.subject || "未分类"}" maxlength="60" list="subjectSuggestions" />
      </label>
      <label>
        资料类型
        <select id="editDocumentKind">
          <option value="做题本" ${doc.document_kind !== "模拟卷" ? "selected" : ""}>做题本</option>
          <option value="模拟卷" ${doc.document_kind === "模拟卷" ? "selected" : ""}>模拟卷</option>
        </select>
      </label>
      <p class="edit-file-name">原始文件：${doc.filename}</p>
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
      await api(`/api/documents/${id}`, {
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

function renderQuestionGrid(target, questions, emptyText = "还没有题目。先从左侧上传 PDF，或清空筛选条件。", options = {}) {
  $(target).innerHTML =
    questions.length
      ? questions
          .map(
            (q) => `
        <article class="question-card ${options.selectable ? "selectable-question" : ""}" id="qcard-${q.id}">
          ${options.selectable ? `
          <label class="question-select">
            <input type="checkbox" data-select-mistake="${q.id}" ${state.selectedMistakes.has(q.id) ? "checked" : ""} />
            <span></span>
          </label>` : ""}
          <div class="thumb" data-open="${q.id}">
            <img src="${q.image_url}" alt="第 ${q.page_number} 页题目" loading="lazy" />
          </div>
          <div class="card-body">
            <div class="meta">
              <span><b class="qno">第${q.seq_no || q.page_number}题</b> · ${q.document_title || q.filename || "做题本"}${q.question_no ? ` · 原题${q.question_no}` : ""}</span>
              <span class="tag status ${statusClass(q.status)}">${q.status}</span>
            </div>
            <strong>${q.category}</strong>
            <span class="tag">${q.subject || "未分类"} · ${q.chapter || "未识别章节"}</span>
            <span class="tag kind ${questionKind(q) === "模拟卷" ? "mock" : "paper"}">${questionKind(q)}</span>
            ${reviewTag(q)}
            <p class="snippet">${snippet(q.ocr_text)}</p>
            <div class="actions">
              <button data-status="做对" data-id="${q.id}">做对</button>
              <button data-status="做错" data-id="${q.id}">做错</button>
              <button class="danger" data-delete-question="${q.id}">删除</button>
            </div>
          </div>
        </article>`
          )
          .join("")
      : `<p class="empty-note">${emptyText}</p>`;
}

async function updateQuestion(id, payload) {
  try {
    await api(`/api/questions/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
    await refresh();
  } catch (error) {
    alert(error.message);
    throw error;
  }
}

async function deleteQuestion(id) {
  if (!confirm("确定删除这道题吗？这个操作会移除题目记录和对应页面图片。")) return;
  const result = await api(`/api/questions/${id}`, { method: "DELETE" });
  if (result.document_deleted && result.document_id) {
    if (state.documentId === result.document_id) {
      state.documentId = "";
      state.category = "";
      state.chapter = "";
    }
    if (state.dashboardDocumentId === result.document_id) {
      state.dashboardDocumentId = "";
    }
  }
  await refresh();
}

async function deleteDocument(id) {
  const doc = state.documents.find((item) => item.id === id);
  const name = doc ? doc.title || doc.filename : "这套做题本";
  const kind = doc ? documentKind(doc) : "做题本";
  if (!confirm(`确定删除「${name}」吗？这会删除整套${kind}、题目记录和页面图片。`)) return;
  await api(`/api/documents/${id}`, { method: "DELETE" });
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
  const result = await api(`/api/documents/${id}/rescan-chapters`, { method: "POST", body: "{}" });
  alert(`已重扫 ${result.pages} 页，更新 ${result.updated} 条题目记录。`);
  await refresh();
}

// Question detail, crop tool and image lightbox live in /static/question_detail.js

// ==========================================================================
// 提醒打卡
// ==========================================================================
// Reminder/check-in/weather helpers live in /static/reminders.js
// AI chat/settings/memory helpers live in /static/ai_chat.js

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
          <h3>${chapter.chapter}</h3>
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
  const size = 260; // 适当放动画布，给文字留出呼吸空间
  const center = size / 2;
  const radius = 80;
  const points = items.map((item, index) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / items.length;
    const value = item.ratio || 0;
    
    // 🌸 动态文字排版算法：根据角度决定向外推的方向
    let anchor = "middle";
    if (Math.cos(angle) < -0.1) anchor = "end";   // 左半边的字靠右对齐（向左推）
    if (Math.cos(angle) > 0.1) anchor = "start";  // 右半边的字靠左对齐（向右推）

    let dy = "0.3em";
    if (Math.sin(angle) < -0.1) dy = "-0.5em"; // 顶部的字往上推
    if (Math.sin(angle) > 0.1) dy = "1em";     // 底部的字往下推

    return {
      ...item,
      x: center + Math.cos(angle) * radius * value,
      y: center + Math.sin(angle) * radius * value,
      ax: center + Math.cos(angle) * radius,
      ay: center + Math.sin(angle) * radius,
      lx: center + Math.cos(angle) * (radius + 15), // 距离顶点的缓冲距离
      ly: center + Math.sin(angle) * (radius + 15),
      anchor, dy
    };
  });
  const polygon = points.map((p) => `${p.x},${p.y}`).join(" ");
  return `
    <svg class="radar" viewBox="0 0 ${size} ${size}" role="img" aria-label="错因雷达图">
      <polygon class="radar-grid" points="${points.map((p) => `${p.ax},${p.ay}`).join(" ")}"></polygon>
      ${points.map((p) => `<line class="radar-axis" x1="${center}" y1="${center}" x2="${p.ax}" y2="${p.ay}"></line>`).join("")}
      <polygon class="radar-area" points="${polygon}"></polygon>
      ${points.map((p) => `<text x="${p.lx}" y="${p.ly}" text-anchor="${p.anchor}" dy="${p.dy}">${p.tag} ${p.count}</text>`).join("")}
    </svg>`;
}

// Reflection summary/history helpers live in /static/reflection.js

// Daily practice and custom-rule helpers live in /static/daily.js

function setSelectOptions(selector, values, allLabel, current = "") {
  const el = $(selector);
  if (!el) return "";
  const safeValues = (values || []).filter((value) => value !== null && value !== undefined && String(value).trim() !== "");
  const hasCurrent = current && safeValues.some((value) => String(value) === String(current));
  const nextValue = hasCurrent ? current : "";
  el.innerHTML = `<option value="">${allLabel}</option>${safeValues
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

// Daily practice rule form/rendering lives in /static/daily.js

// Backup/migration helpers live in /static/backup.js

// Learning profile / AI coach helpers live in /static/coach.js

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function escapeAttr(text) {
  return escapeHtml(text).replace(/'/g, "&#39;");
}

async function gotoLibraryFilter(filter) {
  state.status = filter.status || "";
  state.category = filter.category || "";
  state.subject = filter.subject || "";
  state.chapter = "";
  state.documentId = "";
  setView("library");
  // 同步下拉框显示
  if ($("#statusFilter")) $("#statusFilter").value = state.status;
  if ($("#subjectFilter")) $("#subjectFilter").value = state.subject;
  if ($("#categoryFilter")) $("#categoryFilter").value = state.category;
  await loadQuestions();
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
  if (view === "chapterStats") loadChapterStats();
  if (view === "reflection" && window.SakuraReflection) window.SakuraReflection.load();
  if (view === "coach" && window.SakuraCoach) window.SakuraCoach.load();
  if (view === "aiChat" && window.loadAiChatPanel) window.loadAiChatPanel();
  if (view === "remind") { loadRemind(); loadWeatherSettings(); }
  if (view === "mistakes") loadMistakes();
  if (view === "textbook" && window.SakuraTextbook) window.SakuraTextbook.load();
  if (view === "library" || view === "mockPapers") loadQuestions();
  updateSearchBoxState();
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

bindUploadForm("#bookUploadForm", "做题本");
bindUploadForm("#mockUploadForm", "模拟卷");

$("#documentFilter").addEventListener("change", async (event) => {
  state.documentId = event.target.value;
  const doc = state.documents.find((item) => item.id === state.documentId);
  if (doc) state.subject = doc.subject || state.subject;
  state.category = "";
  state.chapter = "";
  await loadQuestions();
});

$("#dashboardSubjectFilter").addEventListener("change", async (event) => {
  state.dashboardSubject = event.target.value;
  const docs = dashboardDocuments().filter((doc) => !state.dashboardSubject || doc.subject === state.dashboardSubject);
  if (state.dashboardDocumentId && !docs.some((doc) => doc.id === state.dashboardDocumentId)) {
    state.dashboardDocumentId = "";
  }
  await loadDashboardData();
});

$("#dashboardDocumentFilter").addEventListener("change", async (event) => {
  state.dashboardDocumentId = event.target.value;
  await loadDashboardData();
});

$("#subjectFilter").addEventListener("change", async (event) => {
  state.subject = event.target.value;
  const docs = state.documents.filter((doc) => !state.subject || doc.subject === state.subject);
  if (state.documentId && !docs.some((doc) => doc.id === state.documentId)) {
    state.documentId = "";
  }
  state.category = "";
  state.chapter = "";
  await loadQuestions();
});

$("#categoryFilter").addEventListener("change", async (event) => {
  state.category = event.target.value;
  state.chapter = "";
  await loadQuestions();
});

$("#chapterFilter").addEventListener("change", async (event) => {
  state.chapter = event.target.value;
  await loadQuestions();
});

$("#mistakeDocumentFilter").addEventListener("change", async (event) => {
  state.mistakeDocumentId = event.target.value;
  const doc = state.documents.find((item) => item.id === state.mistakeDocumentId);
  if (doc) state.mistakeSubject = doc.subject || state.mistakeSubject;
  state.mistakeCategory = "";
  state.mistakeChapter = "";
  await loadMistakes();
});

$("#mistakeSubjectFilter").addEventListener("change", async (event) => {
  state.mistakeSubject = event.target.value;
  const docs = state.documents.filter((doc) => !state.mistakeSubject || doc.subject === state.mistakeSubject);
  if (state.mistakeDocumentId && !docs.some((doc) => doc.id === state.mistakeDocumentId)) {
    state.mistakeDocumentId = "";
  }
  state.mistakeCategory = "";
  state.mistakeChapter = "";
  await loadMistakes();
});

$("#mistakeCategoryFilter").addEventListener("change", async (event) => {
  state.mistakeCategory = event.target.value;
  state.mistakeChapter = "";
  await loadMistakes();
});

$("#mistakeChapterFilter").addEventListener("change", async (event) => {
  state.mistakeChapter = event.target.value;
  await loadMistakes();
});

$("#statsDocumentSelect").addEventListener("change", async (event) => {
  await loadChapterStats(event.target.value);
});

$("#statusFilter").addEventListener("change", async (event) => {
  state.status = event.target.value;
  await loadQuestions();
});

$("#searchInput").addEventListener("input", async (event) => {
  if (event.target.disabled) return;
  state.search = event.target.value.trim();
  clearTimeout(window.searchTimer);
  window.searchTimer = setTimeout(loadQuestions, 250);
});

function locateQuestionByNo(raw) {
  const hint = $("#locateHint");
  const value = String(raw || "").trim().replace(/^0+/, "");
  if (!value) { if (hint) hint.textContent = ""; return; }
  // 先按每本序号定位，再按手填的原书题号
  let matches = (state.questions || []).filter((q) => String(q.seq_no || "") === value);
  let byPrinted = false;
  if (!matches.length) {
    matches = (state.questions || []).filter((q) => String(q.question_no || "") === value);
    byPrinted = matches.length > 0;
  }
  if (!matches.length) {
    if (hint) hint.textContent = `当前筛选下没有第 ${value} 题`;
    return;
  }
  const target = matches[0];
  const card = document.getElementById(`qcard-${target.id}`);
  if (card) {
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.classList.remove("qcard-flash");
    void card.offsetWidth; // 重置动画
    card.classList.add("qcard-flash");
  }
  if (hint) hint.textContent = byPrinted ? `按原书题号定位` : (matches.length > 1 ? `共 ${matches.length} 题命中，已定位第一题` : "");
}

$("#questionLocate").addEventListener("keydown", (event) => {
  if (event.key === "Enter") locateQuestionByNo(event.target.value);
});
$("#questionLocate").addEventListener("input", (event) => {
  clearTimeout(window.locateTimer);
  window.locateTimer = setTimeout(() => locateQuestionByNo(event.target.value), 350);
});

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

$("#focusWrong").addEventListener("click", async () => {
  state.mistakeStatus = state.mistakeStatus === "做错" ? "" : "做错";
  await loadMistakes();
});

// Learning profile / coach bindings live in /static/coach.js

// 提醒打卡
on("#checkinBtn", "click", doCheckin);
on("#testMorningBtn", "click", () => testPush("morning"));
on("#testNightBtn", "click", () => testPush("night"));
on("#saveRemindSettings", "click", saveRemindSettings);
onEach(["#remindMorningOn", "#remindMorningTime", "#remindNightTime", "#remindWeatherOn", "#remindWeatherTime", "#checkinMode"], "change", () => {
  renderRemindGuide(readRemindForm(), "设置已修改，点击保存提醒设置后生效。");
});
on("#saveNotifySettings", "click", saveNotificationSettings);
on("#testEmailBtn", "click", testEmailNotification);
on("#saveWeatherCity", "click", saveWeatherCity);
on("#previewWeather", "click", previewWeather);
on("#sendWeatherPreview", "click", previewWeatherPush);
on("#testWeatherPush", "click", testWeatherPush);

$("#focusReview").addEventListener("click", async () => {
  state.mistakeStatus = state.mistakeStatus === "review" ? "" : "review";
  await loadMistakes();
});

async function exportMistakesPDF({ useFilters = false } = {}) {
  const selectedIds = state.view === "mistakes" ? [...state.selectedMistakes] : [];
  if (state.view === "mistakes") {
    if (!selectedIds.length && !hasActiveMistakeFilter()) {
      alert("请先选择科目或资料，再导出对应错题。");
      return;
    }
    if (!selectedIds.length && state.mistakeQuestions.length > 120 && !confirm(`将导出当前筛选下 ${state.mistakeQuestions.length} 道错题，PDF 可能较大。确定继续吗？`)) return;
  } else if (useFilters) {
    const total = (state.questions || []).filter((q) => questionKind(q) !== "模拟卷").length;
    const hasFilter = Boolean(state.documentId || state.subject || state.category || state.chapter || state.status || state.search);
    if (!hasFilter && total > 120 && !confirm(`当前没有筛选条件，将导出 ${total} 道题，PDF 可能较大。确定继续吗？`)) return;
  }
  const params = new URLSearchParams();
  params.set("mistakes_only", "1");
  if (selectedIds.length) {
    params.set("ids", selectedIds.join(","));
  } else if (state.view === "mistakes") {
    if (state.mistakeDocumentId) params.set("document_id", state.mistakeDocumentId);
    if (state.mistakeSubject) params.set("subject", state.mistakeSubject);
    if (state.mistakeCategory) params.set("category", state.mistakeCategory);
    if (state.mistakeChapter) params.set("chapter", state.mistakeChapter);
    if (state.mistakeStatus === "做错") params.set("status", "做错");
    if (state.mistakeStatus === "review") params.set("status_group", "review");
  } else if (useFilters) {
    params.set("mistakes_only", "0");
    if (state.documentId) params.set("document_id", state.documentId);
    if (state.subject) params.set("subject", state.subject);
    if (state.category) params.set("category", state.category);
    if (state.chapter) params.set("chapter", state.chapter);
    if (state.status) params.set("status", state.status);
    if (state.search) params.set("search", state.search);
  }
  try {
    const res = await fetch(`/api/export/mistakes?${params.toString()}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "导出失败，请稍后再试。");
      return;
    }
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const name = (cd.match(/filename="(.+?)"/) || [])[1] || "mistakes.pdf";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  } catch (e) {
    alert("导出失败：" + e.message);
  }
}

$("#exportMistakes").addEventListener("click", () => exportMistakesPDF({ useFilters: false }));
$("#exportLibrary").addEventListener("click", () => exportMistakesPDF({ useFilters: true }));

$("#selectAllMistakes").addEventListener("click", () => {
  state.mistakeQuestions.forEach((q) => state.selectedMistakes.add(q.id));
  renderMistakeGrid();
});

$("#clearMistakeSelection").addEventListener("click", () => {
  state.selectedMistakes.clear();
  renderMistakeGrid();
});

$("#mistakeGrid").addEventListener("change", (event) => {
  const input = event.target.closest("[data-select-mistake]");
  if (!input) return;
  if (input.checked) state.selectedMistakes.add(input.dataset.selectMistake);
  else state.selectedMistakes.delete(input.dataset.selectMistake);
  renderMistakeSelectionHint();
});

$("#showAllQuestions").addEventListener("click", async () => {
  state.documentId = "";
  state.subject = "";
  state.category = "";
  state.chapter = "";
  state.status = "";
  state.search = "";
  $("#searchInput").value = "";
  clearTimeout(window.searchTimer);
  setView("library");
  await loadQuestions();
});

$("#showMockQuestions").addEventListener("click", async () => {
  state.documentId = "";
  state.subject = "";
  state.category = "";
  state.chapter = "";
  state.status = "";
  state.search = "";
  $("#searchInput").value = "";
  clearTimeout(window.searchTimer);
  setView("library");
  await loadQuestions();
  $("#mockQuestionGrid").scrollIntoView({ behavior: "smooth", block: "start" });
});

// Daily practice bindings live in /static/daily.js
// Backup/migration bindings live in /static/backup.js

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
    await deleteDocument(deleteDocBtn.dataset.deleteDoc);
  }

  const editDocBtn = event.target.closest("[data-edit-doc]");
  if (editDocBtn) {
    await editDocument(editDocBtn.dataset.editDoc);
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
    await loadChapterStats(statsDocBtn.dataset.statsDoc);
  }

  const rescanDocBtn = event.target.closest("[data-rescan-doc]");
  if (rescanDocBtn) {
    await rescanDocument(rescanDocBtn.dataset.rescanDoc);
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
