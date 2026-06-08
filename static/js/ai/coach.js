(function () {
  const ROOT_CAUSE_LABELS = ["概念缺失", "计算失误", "方法不会", "审题偏差"];
  const BAND_CLASS = { "已掌握": "mastered", "巩固中": "good", "不稳": "review", "薄弱": "wrong", "未触及": "" };
  const TREND_ICON = { up: "↑", down: "↓", flat: "→", new: "✦", untouched: "·" };
  let isBound = false;

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
            <span class="tag band ${BAND_CLASS[g.band] || ""}">${escapeHtml(g.band)} ${TREND_ICON[g.trend] || ""}</span>
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
      <div class="today-item today-${escapeAttr(a.kind)}">
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

  function bindCoachPanel() {
    if (isBound) return;
    isBound = true;
    on("#refreshProfileBtn", "click", refreshProfile);
    on("#generatePlanBtn", "click", () => generatePlan(false));
    on("#coachNarrativeBtn", "click", () => generatePlan(true));
    on("#clearProfileBtn", "click", clearProfile);
    on("#coachMemoryBadge", "click", openProfileArchive);
    on("#coachMemoryBadge", "keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openProfileArchive();
      }
    });
    on("#viewTeacherMemoryBtn", "click", openTeacherMemoryArchive);
    ["#coachDailyMinutes", "#coachExamDate", "#coachCadence", "#coachFocusSubject"].forEach((sel) => {
      on(sel, "change", saveCoachSettings);
    });
    on("#coachGaps", "click", (event) => {
      const btn = event.target.closest(".gap-go");
      if (!btn) return;
      gotoLibraryFilter({ category: btn.dataset.goCategory, subject: btn.dataset.goSubject });
    });
    on("#coachToday", "click", (event) => {
      const btn = event.target.closest(".today-go");
      if (!btn) return;
      let filter = {};
      try { filter = JSON.parse(btn.dataset.goFilter || "{}"); } catch (_) {}
      if (filter.kind === "模拟卷") { setView("mockPapers"); return; }
      gotoLibraryFilter(filter);
    });
  }

  window.SakuraCoach = {
    load: loadCoach,
    refreshProfile,
    generatePlan,
    refreshBadge: refreshCoachBadge,
    bind: bindCoachPanel,
  };

  bindCoachPanel();
})();
