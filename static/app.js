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
  if ($("#textbookList")) await loadTextbooks();
  if ($("#dailyRuleDocument")) await populateDailyRuleFilters();
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

function currentVisibleQuestionIds() {
  const activeView = document.querySelector(".view.active") || document;
  const ids = [...activeView.querySelectorAll("[data-open]")]
    .map((el) => String(el.dataset.open || ""))
    .filter(Boolean);
  return [...new Set(ids)];
}

function detailNeighbor(id, step) {
  const visibleIds = currentVisibleQuestionIds();
  let ids = visibleIds;
  if (!ids.includes(String(id))) {
    const source = state.view === "mistakes" ? state.mistakeQuestions : state.questions;
    ids = (source || []).map((q) => String(q.id));
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
  const ids = visibleIds.includes(String(id))
    ? visibleIds
    : (state.view === "mistakes" ? state.mistakeQuestions : state.questions).map((q) => String(q.id));
  const index = ids.indexOf(String(id));
  return index >= 0 && ids.length ? `${index + 1}/${ids.length}` : "";
}

async function openDetail(id, presetStatus = "") {
  const q = await api(`/api/questions/${id}`);
  const currentStatus = presetStatus || q.status;
  const dialog = $("#detailDialog");
  const prev = detailNeighbor(q.id, -1);
  const next = detailNeighbor(q.id, 1);
  const positionText = detailPositionText(q.id);
  $("#detailContent").innerHTML = `
    <div class="detail">
      <div class="detail-image">
        <div class="crop-toolbar">
          <button class="ghost" id="zoomImage">放大查看</button>
          <button class="ghost" id="enableCrop">裁剪题目边界</button>
          <button id="saveCrop" disabled>保存裁剪</button>
          <span class="detail-position">${positionText}</span>
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
            <h2>${q.category}</h2>
            <p>第 ${q.seq_no || q.page_number} 题 · ${q.document_title || q.filename} · ${q.subject || "其他"} · ${q.difficulty}</p>
          </div>
          <button class="ghost" id="closeDetail">关闭</button>
        </div>
        <label>
          题号（左上角的编号，便于快速定位）
          <input id="detailQuestionNo" value="${q.question_no || ""}" placeholder="例如：03" />
        </label>
        <label>
          章节
          <input id="detailChapter" value="${q.chapter || ""}" placeholder="例如：第3章 多元函数微分学" />
        </label>
        <label>
          状态
          <select id="detailStatus">
            ${["未做", "做对", "做错", "半会", "需复习"].map((s) => `<option ${s === currentStatus ? "selected" : ""}>${s}</option>`).join("")}
          </select>
        </label>
        <div class="memory-panel">
          <strong>复习记忆</strong>
          <span>${q.ever_wrong ? (q.mastered_at ? "已完成多轮复习，标记为已掌握。" : `保持阶段：${q.retention_stage || 1} 天，下次复习：${q.next_review_at || "待安排"}`) : "这道题还没有进入错题复习队列。"}</span>
          <small>created_at: ${q.created_at || "-"} · retention_stage: ${q.retention_stage || 0}</small>
        </div>
        <label>
          元认知错因
          <div class="meta-checks">${metaTagControls(q.meta_tags || [])}</div>
        </label>
        <label>
          我的备注
          <textarea id="userNote" placeholder="记录这题错在哪里，或者下次要注意什么">${q.user_note || ""}</textarea>
        </label>
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
        <article id="analysisBox" class="math-output mathjax-container"></article>
        <article id="variationsBox" class="math-output mathjax-container"></article>
      </div>
    </div>`;
  dialog.showModal();
  renderAiOutput("#analysisBox", q.ai_hint || q.ai_analysis, "先尝试 Level 1 概念提示；仍卡住再逐级展开到完整解析。");
  renderAiOutput("#variationsBox", q.ai_variations, "点击“举一反三”，生成同类变式练习。");
  typesetMath($("#detailContent"));

  $("#closeDetail").onclick = () => dialog.close();
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
    await updateQuestion(q.id, {
      status: $("#detailStatus").value,
      meta_tags: selectedMetaTags(),
      mistake_reason: selectedMetaTags().join("、"),
      user_note: $("#userNote").value,
      chapter: $("#detailChapter").value,
      question_no: $("#detailQuestionNo").value.trim(),
    });
    dialog.close();
  };
  $("#needReview").onclick = async () => {
    await updateQuestion(q.id, { status: "需复习", meta_tags: selectedMetaTags(), mistake_reason: selectedMetaTags().join("、"), user_note: $("#userNote").value });
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
    await api(`/api/questions/${q.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: $("#detailStatus").value,
        meta_tags: selectedMetaTags(),
        mistake_reason: selectedMetaTags().join("、"),
        user_note: $("#userNote").value,
        chapter: $("#detailChapter").value,
      }),
    });
    const data = await api(`/api/questions/${q.id}/analyze`, { method: "POST", body: "{}" });
    const ins = data.insight || {};
    const chip = ins.root_cause
      ? `\n\n— 已写入学习档案：考点「${(ins.knowledge_points || []).join("、")}」· 错因「${ins.root_cause}」`
      : "\n\n— 已写入学习档案。";
    renderAiOutput("#analysisBox", (data.ai_analysis || "") + chip);
    await refresh();
  };
  [1, 2, 3].forEach((level) => {
    $(`#hint${level}`).onclick = async () => {
      renderAiOutput("#analysisBox", level === 3 ? "正在生成完整 LaTeX 解析..." : "正在生成提示...");
      await api(`/api/questions/${q.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          status: $("#detailStatus").value,
          meta_tags: selectedMetaTags(),
          mistake_reason: selectedMetaTags().join("、"),
          user_note: $("#userNote").value,
          chapter: $("#detailChapter").value,
        }),
      });
      const data = await api(`/api/questions/${q.id}/hint`, { method: "POST", body: JSON.stringify({ level }) });
      renderAiOutput("#analysisBox", data.hint);
      await refresh();
    };
  });
  $("#generateVariations").onclick = async () => {
    renderAiOutput("#variationsBox", "正在生成难度梯度变式...");
    await api(`/api/questions/${q.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: $("#detailStatus").value,
        meta_tags: selectedMetaTags(),
        mistake_reason: selectedMetaTags().join("、"),
        user_note: $("#userNote").value,
        chapter: $("#detailChapter").value,
      }),
    });
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

// 题图全屏放大查看：滚轮缩放、拖拽平移、双击复位、Esc/点空白关闭
const lightboxState = { scale: 1, tx: 0, ty: 0, dragging: false, sx: 0, sy: 0 };

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
  // 用 <dialog> 的 showModal 进入浏览器顶层，叠在已打开的详情弹窗之上
  if (!box.open) box.showModal();
}

function closeLightbox() {
  const box = $("#imageLightbox");
  if (box.open) box.close();
}

function setupLightbox() {
  const box = $("#imageLightbox");
  if (!box) return;
  const img = $("#lightboxImage");

  $("#lightboxClose").onclick = closeLightbox;
  // 点击图片以外的空白处关闭
  box.addEventListener("click", (e) => { if (e.target === box) closeLightbox(); });
  // <dialog> 的 Esc 会触发 cancel，统一走 close
  box.addEventListener("cancel", (e) => { e.preventDefault(); closeLightbox(); });

  box.addEventListener("wheel", (e) => {
    if (!box.open) return;
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    lightboxState.scale = Math.max(0.5, Math.min(8, lightboxState.scale * factor));
    applyLightboxTransform();
  }, { passive: false });

  img.addEventListener("dblclick", () => {
    Object.assign(lightboxState, { scale: lightboxState.scale > 1 ? 1 : 2, tx: 0, ty: 0 });
    applyLightboxTransform();
  });

  img.addEventListener("pointerdown", (e) => {
    lightboxState.dragging = true;
    lightboxState.sx = e.clientX - lightboxState.tx;
    lightboxState.sy = e.clientY - lightboxState.ty;
    img.setPointerCapture(e.pointerId);
  });
  img.addEventListener("pointermove", (e) => {
    if (!lightboxState.dragging) return;
    lightboxState.tx = e.clientX - lightboxState.sx;
    lightboxState.ty = e.clientY - lightboxState.sy;
    applyLightboxTransform();
  });
  img.addEventListener("pointerup", () => { lightboxState.dragging = false; });
}

// ==========================================================================
// 提醒打卡
// ==========================================================================
// Reminder/check-in/weather helpers live in /static/reminders.js

function updateLlmFields(data) {
  if (!data) return;
  if ($("#llmStatusBadge")) {
    $("#llmStatusBadge").textContent = data.has_key ? `已配置 · ${data.model || ""}` : "未配置 API";
    $("#llmStatusBadge").className = `tag ${data.has_key ? "" : "status wrong"}`;
  }
  if ($("#llmApiKey")) $("#llmApiKey").placeholder = data.masked_key ? `已保存：${data.masked_key}` : "未保存";
  if ($("#llmBaseUrl")) $("#llmBaseUrl").value = data.base_url || "";
  if ($("#llmModel")) $("#llmModel").value = data.model || "";
}

function renderTeacherMemories(memories = []) {
  const node = $("#teacherMemoryList");
  if (!node) return;
  node.innerHTML = memories.length
    ? memories.map((m) => `
      <article class="memory-item">
        <p>${escapeHtml(m.content)}</p>
        <small>${escapeHtml(m.source || "chat")} · ${escapeHtml(m.created_at || "")}</small>
        <button class="ghost" data-delete-ai-memory="${escapeAttr(m.id)}"><i data-lucide="trash-2"></i>删除</button>
      </article>`).join("")
    : `<p class="empty-note">还没有老师记忆。发送对话后，可把有价值的一轮主动导入。</p>`;
  if (window.lucide) lucide.createIcons();
}

function renderMentorExperiences(experiences = []) {
  const node = $("#mentorExperienceList");
  if (!node) return;
  node.innerHTML = experiences.length
    ? experiences.map((item) => `
      <article class="memory-item mentor-item">
        <p><strong>${escapeHtml(item.title || "外部经验")}</strong><br>${escapeHtml(item.content)}</p>
        <small>${escapeHtml(item.subject || "未指定科目")} · 可信度 ${escapeHtml(item.reliability || 3)} · ${(item.tags || []).map(escapeHtml).join(" / ")}${item.source ? ` · ${escapeHtml(item.source)}` : ""}</small>
        <button class="ghost" data-delete-mentor-experience="${escapeAttr(item.id)}"><i data-lucide="trash-2"></i>删除</button>
      </article>`).join("")
    : `<p class="empty-note">还没有外部经验。可以粘贴学长学姐经验、帖子总结或自己的方法论。</p>`;
  if (window.lucide) lucide.createIcons();
}

async function loadMentorExperiences() {
  if (!$("#mentorExperienceList")) return;
  try {
    const data = await api("/api/mentor-experience");
    renderMentorExperiences(data.experiences || []);
  } catch (error) {
    $("#mentorExperienceList").innerHTML = `<p class="empty-note">${escapeHtml(error.message)}</p>`;
  }
}

async function loadAiChatPanel() {
  if (!$("#aiChatInput")) return;
  try {
    const data = await api("/api/ai-chat/memory");
    updateLlmFields(data);
    renderTeacherMemories(data.memories || []);
    await loadMentorExperiences();
  } catch (error) {
    if ($("#aiChatOutput")) $("#aiChatOutput").textContent = error.message;
  }
}

async function saveLlmSettings() {
  const hint = $("#llmSettingsHint");
  if (hint) hint.textContent = "正在保存 API 设置...";
  try {
    const data = await api("/api/llm/settings", {
      method: "POST",
      body: JSON.stringify({
        api_key: $("#llmApiKey")?.value.trim() || "",
        base_url: $("#llmBaseUrl")?.value.trim() || "",
        model: $("#llmModel")?.value.trim() || "",
      }),
    });
    updateLlmFields(data);
    if ($("#llmApiKey")) $("#llmApiKey").value = "";
    if (hint) hint.textContent = data.message || "已保存。";
  } catch (error) {
    if (hint) hint.textContent = error.message;
  }
}

async function sendAiChat() {
  const input = $("#aiChatInput");
  const output = $("#aiChatOutput");
  const message = input?.value.trim();
  if (!message) return;
  renderAiOutput(output, "正在请求 AI 老师...");
  try {
    const data = await api("/api/ai-chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    lastAiChatAnswer = data.answer || "";
    updateLlmFields(data);
    const strategyName = data.teacher_strategy?.name || "";
    const intentText = data.teacher_intent ? `意图：${data.teacher_intent}` : "";
    const strategyText = strategyName ? `策略：${strategyName}` : "";
    const prefix = [intentText, strategyText].filter(Boolean).join(" · ");
    renderAiOutput(output, `${prefix ? `【${prefix}】\n\n` : ""}${lastAiChatAnswer || "AI 没有返回内容。"}`);
  } catch (error) {
    renderAiOutput(output, error.message);
  }
}

async function saveAiMemory(content, source = "chat") {
  const text = (content || "").trim();
  if (!text) return;
  await api("/api/ai-chat/memory", {
    method: "POST",
    body: JSON.stringify({ content: text, source }),
  });
  await loadAiChatPanel();
}

async function saveMentorExperience() {
  const content = $("#mentorExperienceContent")?.value.trim() || "";
  if (!content) return;
  await api("/api/mentor-experience", {
    method: "POST",
    body: JSON.stringify({
      title: $("#mentorExperienceTitle")?.value.trim() || "",
      subject: $("#mentorExperienceSubject")?.value.trim() || "",
      tags: $("#mentorExperienceTags")?.value.trim() || "",
      reliability: $("#mentorExperienceReliability")?.value || "3",
      source: $("#mentorExperienceSource")?.value.trim() || "",
      content,
    }),
  });
  ["#mentorExperienceTitle", "#mentorExperienceSubject", "#mentorExperienceTags", "#mentorExperienceContent", "#mentorExperienceSource"].forEach((sel) => {
    if ($(sel)) $(sel).value = "";
  });
  await loadMentorExperiences();
}

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

async function loadReflectionPreview() {
  const period = $("#reflectionPeriod").value;
  const data = await api(`/api/reflection?period=${period}`);
  renderReflectionSummary(data);
}

function renderReflectionSummary(data) {
  const total = Number(data.total || 0);
  if (!total) {
    $("#reflectionSummary").innerHTML = '<p class="empty-note">本周期还没有做题记录。先开始做题，再来做周期反思复盘。</p>';
    $("#reflectionSubjectSummary").innerHTML = '<p class="empty-note">导入题目不会计入统计，只有做对、做错、半会或需复习后才会进入这里。</p>';
    $("#reflectionOutput").textContent = "本周期暂无可复盘内容。";
    return;
  }
  $("#reflectionSummary").innerHTML = `
    <div class="summary-pill"><span>周期</span><strong>${data.period === "month" ? "本月" : "本周"}</strong></div>
    <div class="summary-pill"><span>完成/复盘</span><strong>${data.total}</strong></div>
    <div class="summary-pill"><span>做对</span><strong>${data.correct}</strong></div>
    <div class="summary-pill"><span>做错</span><strong>${data.wrong}</strong></div>
    <div class="summary-pill"><span>需复习</span><strong>${data.review}</strong></div>`;
  $("#reflectionSubjectSummary").innerHTML =
    (data.subjects || [])
      .map((item) => {
        const done = item.total || 0;
        const correctRate = done ? Math.round(((item.correct || 0) / done) * 100) : 0;
        return `
        <article class="subject-reflection-card">
          <div>
            <span>科目</span>
            <strong>${item.subject}</strong>
          </div>
          <div class="subject-reflection-grid">
            <span>做题 ${item.total || 0}</span>
            <span>做对 ${item.correct || 0}</span>
            <span>做错 ${item.wrong || 0}</span>
            <span>需复习 ${item.review || 0}</span>
          </div>
          <div class="mini-rate"><span style="width: ${correctRate}%"></span></div>
          <small>正确率 ${correctRate}%</small>
        </article>`;
      })
      .join("") || `<p class="empty-note">本周期还没有已标记的做题记录。导入题目不会计入这里，只有标记做对、做错、半会或需复习后才会统计。</p>`;
}

async function generateReflection() {
  const period = $("#reflectionPeriod").value;
  $("#reflectionOutput").textContent = "正在生成总结与反思...";
  const data = await api("/api/reflection", {
    method: "POST",
    body: JSON.stringify({ period }),
  });
  renderReflectionSummary(data.summary);
  $("#reflectionOutput").textContent = data.reflection;
}

async function loadDaily() {
  if ($("#dailyRuleList")) await loadDailyRules();
  const data = await api("/api/daily");
  $("#dailyMessage").textContent = `${data.date} · ${data.message}`;
  $("#dailyGrid").innerHTML =
    (data.groups || [])
      .map(
        (group) => `
        <section class="daily-group">
          <div class="daily-group-head">
            <h3>${group.title}</h3>
            <span>${group.questions.length} 题</span>
          </div>
          <div class="question-grid mini-grid">
            ${group.questions
              .map(
                (q) => `
                <article class="question-card">
                  <div class="thumb" data-open="${q.id}">
                    <img src="${q.image_url}" alt="第 ${q.page_number} 页题目" loading="lazy" />
                  </div>
                  <div class="card-body">
                    <div class="meta">
                      <span>${q.document_title || q.filename || "做题本"} · 第 ${q.page_number} 页</span>
                      <span class="tag status ${statusClass(q.status)}">${q.status}</span>
                    </div>
                    <strong>${q.category}</strong>
                    <span class="tag">${q.chapter || "未识别章节"}</span>
                    <span class="tag kind ${questionKind(q) === "模拟卷" ? "mock" : "paper"}">${questionKind(q)}</span>
                    ${q.daily_kind === "foundation" ? '<span class="tag foundation">前置基础</span>' : ""}
                    ${reviewTag(q)}
                    <div class="actions">
                      <button data-status="做对" data-id="${q.id}">做对</button>
                      <button data-status="做错" data-id="${q.id}">做错</button>
                      <button class="ghost" data-open="${q.id}">详情</button>
                    </div>
                  </div>
                </article>`
              )
              .join("")}
          </div>
        </section>`
      )
      .join("") || "<p>暂无每日练习。先上传做题本或标记错题。</p>";
}

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

function dailyRuleStatusLabel(value) {
  return {
    active_wrong: "当前错题+到期复习",
    due: "只看今天到期复习",
    wrong: "只看做错",
    review: "半会/需复习",
    all_wrong_history: "历史曾错题",
  }[value || "active_wrong"] || "当前错题+到期复习";
}

function selectedOptionText(selector, fallback) {
  const el = $(selector);
  if (!el) return fallback;
  return el.selectedOptions?.[0]?.textContent?.trim() || fallback;
}

function cleanDailyRulePart(text) {
  return String(text || "")
    .replace(/\s+[·路]\s*(做题本|模拟卷|资料)$/u, "")
    .trim();
}

function buildDailyRuleName() {
  const subject = $("#dailyRuleSubject")?.value || "";
  const documentId = $("#dailyRuleDocument")?.value || "";
  const category = $("#dailyRuleCategory")?.value || "";
  const chapter = $("#dailyRuleChapter")?.value || "";
  const status = $("#dailyRuleStatus")?.value || "active_wrong";
  const limit = Math.max(1, Math.min(30, Number($("#dailyRuleLimit")?.value) || 5));
  const parts = [];
  if (subject) parts.push(subject);
  if (documentId) parts.push(cleanDailyRulePart(selectedOptionText("#dailyRuleDocument", "指定资料")));
  if (category) parts.push(category);
  if (chapter) parts.push(chapter);
  parts.push(dailyRuleStatusLabel(status));
  parts.push(`${limit}题`);
  return parts.join(" · ");
}

function updateDailyRuleName() {
  const el = $("#dailyRuleName");
  if (el) el.value = buildDailyRuleName();
}

async function populateDailyRuleFilters(resetFrom = "") {
  if (!$("#dailyRuleDocument")) return;
  const documentId = $("#dailyRuleDocument").value;
  let subject = $("#dailyRuleSubject").value;
  if (resetFrom === "document") {
    const doc = state.documents.find((item) => item.id === documentId);
    subject = doc?.subject || "";
  }
  const category = ["document", "subject"].includes(resetFrom) ? "" : $("#dailyRuleCategory").value;
  const chapter = ["document", "subject", "category"].includes(resetFrom) ? "" : $("#dailyRuleChapter").value;
  const params = new URLSearchParams();
  if (documentId) params.set("document_id", documentId);
  if (subject) params.set("subject", subject);
  if (category) params.set("category", category);
  if (chapter) params.set("chapter", chapter);
  const data = await api(`/api/daily/rule-options?${params}`);
  const docs = (data.documents || []).map((doc) => ({
    value: doc.id,
    label: documentLabel(doc),
  }));
  const docEl = $("#dailyRuleDocument");
  const keepDoc = docs.some((doc) => String(doc.value) === String(documentId)) ? documentId : "";
  docEl.innerHTML = `<option value="">全部资料</option>${docs
    .map((doc) => `<option value="${escapeAttr(doc.value)}" ${String(doc.value) === String(keepDoc) ? "selected" : ""}>${escapeHtml(doc.label)}</option>`)
    .join("")}`;
  docEl.value = keepDoc;
  subject = setSelectOptions("#dailyRuleSubject", data.subjects, "全部科目", subject);
  const scopedReady = Boolean(keepDoc && subject);
  if (scopedReady) {
    unlockSelect("#dailyRuleCategory");
    unlockSelect("#dailyRuleChapter");
    setSelectOptions("#dailyRuleCategory", data.categories, "全部知识点", category);
    setSelectOptions("#dailyRuleChapter", data.chapters, "全部章节", chapter);
  } else {
    setSelectLocked("#dailyRuleCategory", "请先选择科目和资料");
    setSelectLocked("#dailyRuleChapter", "请先选择科目和资料");
  }
  updateDailyRuleName();
}

function resetDailyRuleForm() {
  if ($("#dailyRuleStatus")) $("#dailyRuleStatus").value = "active_wrong";
  if ($("#dailyRuleLimit")) $("#dailyRuleLimit").value = 5;
  if ($("#dailyRuleSubject")) $("#dailyRuleSubject").value = "";
  if ($("#dailyRuleDocument")) $("#dailyRuleDocument").value = "";
  if ($("#dailyRuleCategory")) $("#dailyRuleCategory").value = "";
  if ($("#dailyRuleChapter")) $("#dailyRuleChapter").value = "";
  populateDailyRuleFilters().catch((err) => {
    const hint = $("#dailyRuleHint");
    if (hint) hint.textContent = err.message;
  });
}

async function loadDailyRules() {
  if (!$("#dailyRuleList")) return;
  const data = await api("/api/daily/rules");
  state.dailyRules = data.rules || [];
  $("#dailyRuleBadge").textContent = `${state.dailyRules.length} 条规则`;
  $("#dailyRuleList").innerHTML =
    state.dailyRules
      .map(
        (rule) => `
        <article class="daily-rule-item ${rule.enabled ? "" : "disabled"}">
          <div>
            <strong>${escapeHtml(rule.name || "未命名规则")}</strong>
            <p>${escapeHtml(rule.document_title || "全部资料")} · ${escapeHtml(rule.subject || "全部科目")} · ${escapeHtml(rule.category || "全部知识点")} · ${escapeHtml(rule.chapter || "全部章节")}</p>
            <small>${escapeHtml(dailyRuleStatusLabel(rule.status_group))} · 每次 ${rule.limit_count || 5} 题</small>
          </div>
          <div class="daily-rule-actions">
            <label class="switch-lite"><input type="checkbox" data-daily-rule-enabled="${escapeAttr(rule.id)}" ${rule.enabled ? "checked" : ""} /><span>启用</span></label>
            <button class="ghost danger-soft-btn" data-delete-daily-rule="${escapeAttr(rule.id)}"><i data-lucide="trash-2"></i>删除</button>
          </div>
        </article>`
      )
      .join("") || `<p class="empty-note">还没有自定义规则。选择科目、做题本或章节后保存即可。</p>`;
  if (window.lucide) lucide.createIcons();
}

async function saveDailyRule() {
  const hint = $("#dailyRuleHint");
  updateDailyRuleName();
  if (hint) hint.textContent = "正在保存规则...";
  const selectedDocument = $("#dailyRuleDocument")?.value || "";
  const selectedSubject = $("#dailyRuleSubject")?.value || "";
  if (!selectedSubject || !selectedDocument) {
    if (hint) hint.textContent = "请先选择科目和资料/做题本，再保存规则。";
    return;
  }
  const payload = {
    name: $("#dailyRuleName")?.value || buildDailyRuleName(),
    document_id: selectedDocument,
    subject: selectedSubject,
    category: $("#dailyRuleCategory")?.value || "",
    chapter: $("#dailyRuleChapter")?.value || "",
    status_group: $("#dailyRuleStatus")?.value || "active_wrong",
    limit_count: Math.max(1, Math.min(30, Number($("#dailyRuleLimit")?.value) || 5)),
    enabled: true,
  };
  await api("/api/daily/rules", { method: "POST", body: JSON.stringify(payload) });
  if (hint) hint.textContent = "规则已保存。";
  await loadDaily();
}

async function updateDailyRuleEnabled(id, enabled) {
  await api("/api/daily/rules", { method: "POST", body: JSON.stringify({ id, enabled }) });
  await loadDaily();
}

async function deleteDailyRule(id) {
  if (!confirm("确定删除这条每日练习规则吗？")) return;
  await api(`/api/daily/rules/${encodeURIComponent(id)}`, { method: "DELETE" });
  await loadDaily();
}

function updateBackupMode() {
  const mode = $("#backupMode")?.value || "full";
  const start = $("#backupStartDate");
  const end = $("#backupEndDate");
  const includeAssets = $("#backupIncludeAssets");
  const rangeMode = mode === "range";
  if (start) start.disabled = !rangeMode;
  if (end) end.disabled = !rangeMode;
  if (includeAssets) {
    includeAssets.disabled = mode === "light";
    includeAssets.checked = mode === "full" ? true : mode === "light" ? false : includeAssets.checked;
  }
  const hint = $("#migrationHint");
  if (!hint) return;
  if (mode === "full") {
    hint.textContent = "完整迁移会包含原 PDF 和题图，文件可能超过 1GB。";
  } else if (mode === "light") {
    hint.textContent = "轻量迁移只包含数据库、标注、错题状态、AI 记忆和规则，不包含原 PDF/题图。";
  } else {
    hint.textContent = "范围迁移会按日期裁剪数据库；可选择是否带上关联 PDF 和题图。";
  }
}

function exportBackup() {
  const hint = $("#migrationHint");
  const mode = $("#backupMode")?.value || "full";
  const startDate = $("#backupStartDate")?.value || "";
  const endDate = $("#backupEndDate")?.value || "";
  const includeAssets = $("#backupIncludeAssets")?.checked ? "1" : "0";
  if (mode === "range" && (!startDate || !endDate)) {
    if (hint) hint.textContent = "范围迁移需要同时选择开始日期和结束日期。";
    return;
  }
  const params = new URLSearchParams();
  params.set("mode", mode);
  params.set("include_assets", includeAssets);
  if (mode === "range") {
    params.set("start_date", startDate);
    params.set("end_date", endDate);
  }
  if (hint) {
    hint.textContent = mode === "full"
      ? "正在准备完整迁移包，数据较大时需要等一会。"
      : mode === "light"
        ? "正在准备轻量迁移包，通常会快很多。"
        : "正在准备范围迁移包，请稍等。";
  }
  window.location.href = `/api/backup/export?${params.toString()}`;
}

async function waitBackupImport(jobId) {
  const hint = $("#migrationHint");
  for (let i = 0; i < 600; i += 1) {
    const job = await api(`/api/backup/import-status?id=${encodeURIComponent(jobId)}`);
    if (hint) {
      const sizeText = job.size ? ` (${Math.round(job.size / 1024 / 1024)} MB)` : "";
      hint.textContent = `Import ${job.status}${sizeText}: ${job.message || ""}`;
    }
    if (job.status === "done") {
      if (hint) hint.textContent = `Import completed. Backup: ${(job.result && job.result.backup_path) || "migration_backups"}`;
      await refresh();
      await loadDaily();
      return;
    }
    if (job.status === "failed") {
      throw new Error(job.error || job.message || "Import failed.");
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error("Import is still running. Please check again later.");
}

async function importBackup(file) {
  if (!file) return;
  if (!confirm("确定导入这个迁移包吗？当前本地数据会先备份，然后替换为导入数据。")) return;
  const hint = $("#migrationHint");
  if (hint) hint.textContent = "正在导入迁移包...";
  const form = new FormData();
  form.append("backup", file);
  const data = await api("/api/backup/import", { method: "POST", body: form });
  if (data.job_id) {
    await waitBackupImport(data.job_id);
    return;
  }
  if (hint) hint.textContent = `导入完成，旧数据已备份到：${data.backup_path || "migration_backups"}`;
  await refresh();
  await loadDaily();
}

// ==========================================================================
// 学习档案
// ==========================================================================
const ROOT_CAUSE_LABELS = ["概念缺失", "计算失误", "方法不会", "审题偏差"];
const BAND_CLASS = { "已掌握": "mastered", "巩固中": "good", "不稳": "review", "薄弱": "wrong", "未触及": "" };
const TREND_ICON = { up: "↑", down: "↓", flat: "→", new: "✦", untouched: "·" };

function coachSettingsFromUI() {
  return {
    daily_minutes: Number($("#coachDailyMinutes").value) || 60,
    exam_date: $("#coachExamDate").value || "2026-12-20",
    cadence: $("#coachCadence").value,
    focus_subject: $("#coachFocusSubject").value.trim(),
  };
}

function applyCoachSettings(settings) {
  if (!settings) return;
  $("#coachDailyMinutes").value = settings.daily_minutes ?? 60;
  $("#coachExamDate").value = settings.exam_date || "2026-12-20";
  $("#coachCadence").value = settings.cadence || "immediate";
  $("#coachFocusSubject").value = settings.focus_subject || "";
}

async function loadCoach() {
  const hint = $("#coachHint");
  try {
    const data = await api("/api/coach");
    state.coach = data;
    applyCoachSettings(data.settings);
    const v = data.profile_summary?.version || 0;
    setCoachMemoryBadge(v, data.insight_count || 0);
    if (!data.has_key) hint.textContent = "未配置 AI 接口密钥，将只使用本地统计与规则计划。";
    else if (data.needs_refresh) hint.textContent = "有新的错题证据尚未并入档案，建议先「更新学习档案」。";
    else hint.textContent = "";

    if (data.cached_plan) {
      renderCoachPlan(data.cached_plan);
    } else if (data.profile_summary) {
      $("#coachEmpty").classList.add("hidden");
      $("#coachBody").classList.remove("hidden");
      $("#coachNarrative").textContent = "档案已就绪，点「生成复习计划」开始。";
    } else {
      $("#coachBody").classList.add("hidden");
      $("#coachEmpty").classList.remove("hidden");
    }
  } catch (error) {
    hint.textContent = error.message;
  }
}

async function saveCoachSettings() {
  try {
    await api("/api/coach/settings", { method: "POST", body: JSON.stringify(coachSettingsFromUI()) });
  } catch (error) {
    $("#coachHint").textContent = error.message;
  }
}

async function refreshProfile() {
  const hint = $("#coachHint");
  hint.textContent = "正在更新学习档案...";
  try {
    await saveCoachSettings();
    const data = await api("/api/profile/refresh", { method: "POST", body: JSON.stringify({ want_ai: state.coach?.has_key ?? false }) });
    hint.textContent = `学习档案已更新到 v${data.version}（${data.profile.evidence_count} 条证据）。`;
    await loadCoach();
  } catch (error) {
    hint.textContent = error.message;
  }
}

async function generatePlan(wantAi = false) {
  const hint = $("#coachHint");
  hint.textContent = wantAi ? "正在调用 AI 解读学习档案..." : "正在生成本地复习计划...";
  try {
    await saveCoachSettings();
    const plan = await api("/api/coach", { method: "POST", body: JSON.stringify({ want_ai: wantAi }) });
    renderCoachPlan(plan);
    hint.textContent = "";
    await refreshCoachBadge();
  } catch (error) {
    hint.textContent = error.message;
  }
}

async function refreshCoachBadge() {
  try {
    const data = await api("/api/coach");
    state.coach = data;
    const v = data.profile_summary?.version || 0;
    setCoachMemoryBadge(v, data.insight_count || 0);
  } catch (_) {}
}

async function clearProfile() {
  if (!confirm("确定清除当前建议吗？只会清空学习档案页当前生成的复习计划和摘要，不会删除做题记录、错题证据或档案版本。")) return;
  const hint = $("#coachHint");
  hint.textContent = "正在清除当前建议...";
  try {
    await api("/api/coach/plan", { method: "DELETE" });
    $("#coachBody").classList.add("hidden");
    $("#coachEmpty").classList.remove("hidden");
    $("#coachNarrative").textContent = "点击上方「生成复习计划」；配置 API 后可点「AI 解读档案」。";
    hint.textContent = "已清除当前建议，做题记录和学习档案都已保留。";
    await loadCoach();
  } catch (error) {
    hint.textContent = error.message;
  }
}

function renderCoachPlan(plan) {
  if (!plan || !plan.has_profile) {
    $("#coachBody").classList.add("hidden");
    $("#coachEmpty").classList.remove("hidden");
    return;
  }
  $("#coachEmpty").classList.add("hidden");
  $("#coachBody").classList.remove("hidden");

  const diag = plan.diagnosis || {};
  $("#coachHeadline").textContent = diag.headline || diag.velocity || "已建立学习档案。";

  $("#coachProfileStats").innerHTML = `
    <div class="summary-pill"><span>档案版本</span><strong>v${plan.profile_version}</strong></div>
    <div class="summary-pill"><span>已分析错题</span><strong>${plan.evidence_count}</strong></div>
    <div class="summary-pill"><span>距考试</span><strong>${plan.days_left} 天</strong></div>
    <div class="summary-pill"><span>每日预算</span><strong>${plan.daily_minutes} 分</strong></div>`;

  const modes = diag.error_mode_profile || {};
  const maxMode = Math.max(1, ...ROOT_CAUSE_LABELS.map((m) => modes[m] || 0));
  $("#coachErrorModes").innerHTML =
    `<h4>错因分布</h4>` +
    ROOT_CAUSE_LABELS.map((m) => `
      <div class="stat-row">
        <span>${m}</span>
        <div class="bar"><span style="width:${((modes[m] || 0) / maxMode) * 100}%"></span></div>
        <span>${modes[m] || 0}</span>
      </div>`).join("");

  const misc = diag.recurring_misconceptions || [];
  $("#coachMisconceptions").innerHTML = misc.length
    ? `<h4>反复出现的误区</h4>` + misc.slice(0, 5).map((m) => `<div class="misc-item"><span class="misc-count">${m.count}×</span>${escapeHtml(m.text)}</div>`).join("")
    : "";

  const pred = plan.predictions || {};
  $("#coachPredictions").innerHTML = `
    <div class="predict-ring" style="--p:${Math.round((pred.coverage || 0) * 100)}">
      <div class="predict-ring-inner">
        <strong>${Math.round((pred.coverage || 0) * 100)}%</strong>
        <small>薄弱点覆盖</small>
      </div>
    </div>
    <div class="predict-lines">
      <p><span>当前平均掌握度</span><b>${Math.round((pred.current_avg_mastery || 0) * 100)}%</b></p>
      <p><span>剩余练习容量</span><b>${pred.capacity_total || 0} 题</b></p>
      <p><span>薄弱点覆盖率</span><b>${Math.round((pred.coverage || 0) * 100)}%</b></p>
      <p class="predict-outlook">${escapeHtml(pred.outlook || "")}</p>
      <small>${escapeHtml(pred.note || "")}</small>
    </div>`;

  $("#coachGaps").innerHTML = (plan.gaps || []).map((g) => `
    <div class="gap-row">
      <div class="gap-main">
        <div class="gap-title">
          <strong>${escapeHtml(g.name)}</strong>
          <span class="tag band ${BAND_CLASS[g.band] || ""}">${g.band} ${TREND_ICON[g.trend] || ""}</span>
        </div>
        <p class="gap-reason">${escapeHtml(g.reason)}</p>
        <p class="gap-prescription"><i data-lucide="lightbulb"></i>${escapeHtml(g.prescription)}</p>
        ${g.note ? `<p class="gap-note">${escapeHtml(g.note)}</p>` : ""}
      </div>
      <button class="ghost gap-go" data-go-category="${escapeAttr(g.name)}" data-go-subject="${escapeAttr(g.subject || "")}">去练</button>
    </div>`).join("") || `<p class="empty-note">暂无已暴露的薄弱点，继续做题积累证据。</p>`;

  $("#coachPhases").innerHTML = (plan.phases || []).map((p, i) => `
    <div class="phase-card">
      <div class="phase-index">${i + 1}</div>
      <div class="phase-info">
        <div class="phase-head"><strong>${escapeHtml(p.name)}</strong><span>${escapeHtml(p.span)} · ${p.days} 天</span></div>
        <p>${escapeHtml(p.focus)}</p>
        <span class="tag">约 ${p.daily_questions} 题/天</span>
      </div>
    </div>`).join("");

  $("#coachToday").innerHTML = (plan.today || []).map((a) => `
    <div class="today-item today-${a.kind}">
      <span class="today-check"><i data-lucide="circle"></i></span>
      <div class="today-info"><strong>${escapeHtml(a.label)}</strong><p>${escapeHtml(a.detail)}</p></div>
      <button class="ghost today-go" data-go-filter='${escapeAttr(JSON.stringify(a.filter || {}))}'>去做</button>
    </div>`).join("") || `<p class="empty-note">今天没有安排任务，先去更新档案或导入新题。</p>`;

  const src = $("#coachNarrativeSource");
  src.textContent = plan.narrative_source === "ai" ? "AI 解读" : "本地摘要";
  src.className = `tag ${plan.narrative_source === "ai" ? "kind mock" : ""}`;
  $("#coachNarrative").textContent = plan.narrative || "";
  typesetMath($("#coachNarrative"));
  if (window.lucide) lucide.createIcons();
}

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
  if (view === "daily") loadDaily();
  if (view === "chapterStats") loadChapterStats();
  if (view === "reflection") { loadReflectionPreview(); loadReflectionHistory(); }
  if (view === "coach") loadCoach();
  if (view === "aiChat") loadAiChatPanel();
  if (view === "remind") { loadRemind(); loadWeatherSettings(); }
  if (view === "mistakes") loadMistakes();
  if (view === "textbook") loadTextbooks();
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

bindTextbookUploadForm();

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

if ($("#textbookList")) {
  $("#textbookList").addEventListener("click", async (event) => {
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
}

if ($("#loadTextbookPage")) {
  $("#loadTextbookPage").addEventListener("click", async () => {
    state.textbookChat = [];
    await loadTextbookPage();
    renderTextbookChat();
  });
}

if ($("#textbookPageInput")) {
  $("#textbookPageInput").addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
      state.textbookChat = [];
      await loadTextbookPage();
      renderTextbookChat();
    }
  });
}

if ($("#textbookParagraphs")) {
  $("#textbookParagraphs").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-textbook-paragraph]");
    if (!btn) return;
    state.textbookParagraph = Number(btn.dataset.textbookParagraph) || 0;
    $$(".textbook-paragraph").forEach((node) => node.classList.toggle("active", node === btn));
    updateTextbookChatBadge();
  });
}

if ($("#textbookPageImage")) {
  $("#textbookPageImage").addEventListener("dblclick", () => {
    const img = $("#textbookPageImage");
    if (!img || img.classList.contains("hidden") || !img.src) return;
    openLightbox(img.src, img.dataset.caption || "教材页截图");
  });
}

if ($("#askTextbookAi")) $("#askTextbookAi").addEventListener("click", () => askTextbookAi());
if ($("#explainSelectedParagraph")) {
  $("#explainSelectedParagraph").addEventListener("click", () => {
    const msg = state.textbookParagraph
      ? `请逐句解释第 ${state.textbookPage} 页第 ${state.textbookParagraph} 段，说明关键概念、公式来源和容易误解的地方。`
      : `请解释第 ${state.textbookPage} 页的核心内容，并指出我应该重点理解什么。`;
    askTextbookAi(msg);
  });
}
if ($("#saveTextbookMemory")) $("#saveTextbookMemory").addEventListener("click", saveTextbookMemory);
if ($("#clearTextbookChat")) {
  $("#clearTextbookChat").addEventListener("click", () => {
    state.textbookChat = [];
    renderTextbookChat();
    if ($("#textbookHint")) $("#textbookHint").textContent = "当前页面对话已清空。";
  });
}

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

$("#reflectionPeriod").addEventListener("change", loadReflectionPreview);
$("#generateReflection").addEventListener("click", generateReflection);

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

// 学习档案按钮接线
$("#refreshProfileBtn").addEventListener("click", refreshProfile);
$("#generatePlanBtn").addEventListener("click", () => generatePlan(false));
$("#coachNarrativeBtn").addEventListener("click", () => generatePlan(true));
$("#clearProfileBtn").addEventListener("click", clearProfile);
$("#coachMemoryBadge").addEventListener("click", openProfileArchive);
$("#coachMemoryBadge").addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    openProfileArchive();
  }
});
$("#viewTeacherMemoryBtn").addEventListener("click", openTeacherMemoryArchive);
["#coachDailyMinutes", "#coachExamDate", "#coachCadence", "#coachFocusSubject"].forEach((sel) => {
  $(sel).addEventListener("change", saveCoachSettings);
});
$("#coachGaps").addEventListener("click", (event) => {
  const btn = event.target.closest(".gap-go");
  if (!btn) return;
  gotoLibraryFilter({ category: btn.dataset.goCategory, subject: btn.dataset.goSubject });
});
$("#coachToday").addEventListener("click", (event) => {
  const btn = event.target.closest(".today-go");
  if (!btn) return;
  let filter = {};
  try { filter = JSON.parse(btn.dataset.goFilter || "{}"); } catch (_) {}
  if (filter.kind === "模拟卷") { setView("mockPapers"); return; }
  gotoLibraryFilter(filter);
});

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

on("#sendAiChat", "click", sendAiChat);
on("#saveLlmSettings", "click", saveLlmSettings);
on("#refreshAiMemory", "click", loadAiChatPanel);
on("#refreshMentorExperience", "click", loadMentorExperiences);
on("#saveMentorExperience", "click", saveMentorExperience);
on("#saveAiChatMemory", "click", async () => {
  const message = $("#aiChatInput")?.value.trim() || "";
  const content = lastAiChatAnswer ? `用户问题：${message}\nAI 回答：${lastAiChatAnswer}` : message;
  await saveAiMemory(content, "chat");
  if ($("#aiChatOutput")) $("#aiChatOutput").textContent = "已导入老师记忆。";
});
on("#saveManualAiMemory", "click", async () => {
  await saveAiMemory($("#manualAiMemory")?.value || "", "manual");
  if ($("#manualAiMemory")) $("#manualAiMemory").value = "";
});
on("#clearAiChat", "click", () => {
  lastAiChatAnswer = "";
  if ($("#aiChatInput")) $("#aiChatInput").value = "";
  if ($("#aiChatOutput")) $("#aiChatOutput").textContent = "已清空。";
});
on("#teacherMemoryList", "click", async (event) => {
  const btn = event.target.closest("[data-delete-ai-memory]");
  if (!btn) return;
  await api(`/api/ai-chat/memory/${encodeURIComponent(btn.dataset.deleteAiMemory)}`, { method: "DELETE" });
  await loadAiChatPanel();
});
on("#mentorExperienceList", "click", async (event) => {
  const btn = event.target.closest("[data-delete-mentor-experience]");
  if (!btn) return;
  await api(`/api/mentor-experience/${encodeURIComponent(btn.dataset.deleteMentorExperience)}`, { method: "DELETE" });
  await loadMentorExperiences();
});

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

if ($("#refreshDaily")) $("#refreshDaily").addEventListener("click", loadDaily);
if ($("#saveDailyRule")) $("#saveDailyRule").addEventListener("click", saveDailyRule);
if ($("#resetDailyRule")) $("#resetDailyRule").addEventListener("click", resetDailyRuleForm);
if ($("#dailyRuleDocument")) {
  $("#dailyRuleDocument").addEventListener("change", async () => {
    await populateDailyRuleFilters("document");
  });
}
if ($("#dailyRuleSubject")) {
  $("#dailyRuleSubject").addEventListener("change", async () => {
    await populateDailyRuleFilters("subject");
  });
}
if ($("#dailyRuleCategory")) {
  $("#dailyRuleCategory").addEventListener("change", async () => {
    await populateDailyRuleFilters("category");
  });
}
if ($("#dailyRuleChapter")) {
  $("#dailyRuleChapter").addEventListener("change", updateDailyRuleName);
}
if ($("#dailyRuleStatus")) $("#dailyRuleStatus").addEventListener("change", updateDailyRuleName);
if ($("#dailyRuleLimit")) $("#dailyRuleLimit").addEventListener("input", updateDailyRuleName);
if ($("#dailyRuleList")) {
  $("#dailyRuleList").addEventListener("change", async (event) => {
    const input = event.target.closest("[data-daily-rule-enabled]");
    if (!input) return;
    await updateDailyRuleEnabled(input.dataset.dailyRuleEnabled, input.checked);
  });
  $("#dailyRuleList").addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-delete-daily-rule]");
    if (!btn) return;
    await deleteDailyRule(btn.dataset.deleteDailyRule);
  });
}
if ($("#backupMode")) $("#backupMode").addEventListener("change", updateBackupMode);
if ($("#backupIncludeAssets")) $("#backupIncludeAssets").addEventListener("change", updateBackupMode);
if ($("#exportBackup")) $("#exportBackup").addEventListener("click", exportBackup);
updateBackupMode();
if ($("#importBackupFile")) {
  $("#importBackupFile").addEventListener("change", async (event) => {
    await importBackup(event.target.files?.[0]);
    event.target.value = "";
  });
}

document.body.addEventListener("click", async (event) => {
  const nav = event.target.closest(".nav-btn");
  if (nav) setView(nav.dataset.view);

  const open = event.target.closest("[data-open]");
  if (open) openDetail(open.dataset.open);

  const status = event.target.closest("[data-status]");
  if (status) {
    if (status.dataset.status === "做错") {
      await openDetail(status.dataset.id, "做错");
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
setupLightbox();
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

async function loadReflectionHistory() {
  try {
    const data = await api("/api/reflections");
    const list = data.reflections || [];
    if (!list.length) {
      $("#historyList").innerHTML = '<p class="empty-note">' + "暂无历史反思记录。" + '</p>';
      return;
    }
    $("#historyList").innerHTML = list.map((ref) => {
      const periodLabel = ref.period === "week" ? "周" : "月";
      const dateLabel = ref.period_start + " ~ " + ref.period_end;
      const preview = (ref.reflection_text || "").slice(0, 120);
      return '<div class="history-item">' +
        '<div class="history-meta">' +
        '<strong>' + periodLabel + '总结</strong>' +
        '<span>' + dateLabel + '</span>' +
        '<small>' + ref.created_at.slice(0, 16) + '</small>' +
        '</div>' +
        '<p class="history-preview">' + preview + (preview.length >= 120 ? "..." : "") + '</p>' +
        '<div class="history-actions">' +
        '<button class="ghost" onclick="downloadReflection(\'' + ref.id + '\')">下载 TXT</button>' +
        '<button class="danger" onclick="deleteReflection(\'' + ref.id + '\')">删除</button>' +
        '</div>' +
        '</div>';
    }).join("");
  } catch (e) {
    $("#historyList").innerHTML = '<p class="empty-note">' + "加载历史失败。" + '</p>';
  }
}
function downloadReflection(refId) {
  const a = document.createElement("a");
  a.href = `/api/reflections/${refId}/download`;
  a.download = "";
  a.click();
}

async function deleteReflection(refId) {
  if (!confirm("确定删除这条历史记录吗？")) return;
  await api(`/api/reflections/${refId}`, { method: "DELETE" });
  await loadReflectionHistory();
}

$("#loadReflectionHistory").addEventListener("click", loadReflectionHistory);
