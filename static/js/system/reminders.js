// Reminder/check-in/weather helpers for Sakura.
// Loaded before app.js; uses shared global helpers such as $, api and escapeHtml.

const REMIND_DEFAULTS = { morningOn: "1", morningTime: "10:00", nightOn: "1", nightTime: "20:00", weatherOn: "1", weatherTime: "22:30", checkinMode: "wework" };

function normalizeCheckinMode(value) {
  const text = String(value || "").trim().toLowerCase();
  if (text === "button" || text === "local") return "local";
  if (text === "push" || text === "pushplus") return "pushplus";
  if (text === "wework" || text === "wechatwork" || text === "enterprise_wechat") return "wework";
  if (text === "cloud" || text === "link") return "wework";
  return REMIND_DEFAULTS.checkinMode;
}

function checkinModeMeta(value) {
  const mode = normalizeCheckinMode(value);
  const map = {
    wework: {
      label: "企业微信打卡",
      channelText: "企业微信机器人",
      desc: "企业微信机器人消息里会带打卡链接；手机点开后直接记录到服务器。",
      note: "企业微信需要先在下方保存机器人 Webhook。公网地址要能从手机访问。",
    },
    pushplus: {
      label: "PushPlus 打卡",
      channelText: "PushPlus 微信通道",
      desc: "PushPlus 微信消息里会带打卡链接；手机点开后直接记录到服务器。",
      note: "PushPlus 需要先在下方保存 Token，并完成 PushPlus 账号认证。公网地址要能从手机访问。",
    },
    local: {
      label: "本地按钮打卡",
      channelText: "本地按钮",
      desc: "只在当前浏览器点击上方按钮记录打卡，适合本机开发和离线使用。",
      note: "本地按钮不依赖公网地址；但推送消息里的链接不会替你完成本机按钮打卡。",
    },
  };
  return map[mode] || map.wework;
}

function currentCheckinMode() {
  return normalizeCheckinMode($("#checkinMode")?.value || REMIND_DEFAULTS.checkinMode);
}

function notificationDetailText(detail) {
  if (!detail) return "";
  if (Array.isArray(detail)) {
    const firstFailed = detail.find((item) => item && item.ok === false) || detail[0];
    return notificationDetailText(firstFailed);
  }
  if (detail.resp) return notificationDetailText(detail.resp);
  if (detail.code === 905) return "PushPlus 已读到 token，但账号未实名认证。你当前如果用企业微信，请切换到企业微信打卡后再测试。";
  if (detail.errcode !== undefined && detail.errcode !== 0) return detail.errmsg || JSON.stringify(detail);
  return detail.msg || detail.error || detail.detail || JSON.stringify(detail);
}

function normalizeRemindSettings(data = {}) {
  const morningOn = data.morning_on ?? data.morningOn ?? REMIND_DEFAULTS.morningOn;
  const nightOn = data.night_on ?? data.nightOn ?? REMIND_DEFAULTS.nightOn;
  const dayReminderOn = morningOn === "0" && nightOn === "0" ? "0" : "1";
  return {
    morningOn: dayReminderOn,
    morningTime: data.morning_time ?? data.morningTime ?? REMIND_DEFAULTS.morningTime,
    nightOn: dayReminderOn,
    nightTime: data.night_time ?? data.nightTime ?? REMIND_DEFAULTS.nightTime,
    weatherOn: data.weather_on ?? data.weatherOn ?? REMIND_DEFAULTS.weatherOn,
    weatherTime: data.weather_time ?? data.weatherTime ?? REMIND_DEFAULTS.weatherTime,
    checkinMode: normalizeCheckinMode(data.checkin_mode ?? data.checkinMode ?? REMIND_DEFAULTS.checkinMode),
    cron: data.cron || {},
  };
}

function readRemindForm() {
  const dayReminderOn = $("#remindMorningOn").value;
  const s = {
    morningOn: dayReminderOn, morningTime: $("#remindMorningTime").value,
    nightOn: dayReminderOn, nightTime: $("#remindNightTime").value,
    weatherOn: $("#remindWeatherOn")?.value || "1", weatherTime: $("#remindWeatherTime")?.value || "22:30",
    checkinMode: normalizeCheckinMode($("#checkinMode").value),
  };
  return s;
}

function applyRemindSettings(s) {
  $("#remindMorningOn").value = s.morningOn;
  $("#remindMorningTime").value = s.morningTime;
  $("#remindNightTime").value = s.nightTime;
  if ($("#remindWeatherOn")) $("#remindWeatherOn").value = s.weatherOn;
  if ($("#remindWeatherTime")) $("#remindWeatherTime").value = s.weatherTime;
  $("#checkinMode").value = s.checkinMode;
}

async function saveRemindSettings() {
  const s = readRemindForm();
  renderRemindGuide(s, "正在同步服务器定时任务...");
  try {
    const data = await api("/api/reminder/settings", {
      method: "POST",
      body: JSON.stringify({
        morning_on: s.morningOn,
        morning_time: s.morningTime,
        night_on: s.nightOn,
        night_time: s.nightTime,
        weather_on: s.weatherOn,
        weather_time: s.weatherTime,
        checkin_mode: s.checkinMode,
      }),
    });
    const saved = normalizeRemindSettings(data);
    applyRemindSettings(saved);
    renderRemindGuide(saved, data.message || saved.cron?.message || "服务器定时任务已同步。");
  } catch (error) {
    renderRemindGuide(s, `保存失败：${error.message}`);
  }
}

async function loadRemind() {
  let s = { ...REMIND_DEFAULTS };
  try {
    s = normalizeRemindSettings(await api("/api/reminder/settings"));
  } catch (_) {
    try {
      s = normalizeRemindSettings(JSON.parse(localStorage.getItem("remindSettings") || "{}"));
    } catch (__) {}
  }
  applyRemindSettings(s);
  renderRemindGuide(s);
  // 今日打卡状态
  try {
    const st = await api("/api/today/status");
    setCheckinUI(st.checked_in);
  } catch (_) {}
  $("#pushConfigBadge").textContent = "点测试按钮检测";
  $("#pushConfigBadge").className = "tag";
  await loadNotificationSettings();
  await loadSecuritySettings();
}

function setCheckinUI(done) {
  const badge = $("#checkinBadge");
  const btn = $("#checkinBtn");
  if (done) {
    badge.textContent = "今日已打卡 ✅";
    badge.className = "section-count checkin-done";
    btn.disabled = true;
    $("#checkinHint").textContent = "今天已完成，晚上不会被念了 😌";
  } else {
    badge.textContent = "未打卡";
    badge.className = "section-count";
    btn.disabled = false;
  }
}

function renderRemindGuide(s, statusText = "") {
  const mode = normalizeCheckinMode(s.checkinMode);
  const morning = s.morningTime.split(":");
  const night = s.nightTime.split(":");
  const weather = (s.weatherTime || "22:30").split(":");
  const modeInfo = checkinModeMeta(mode);
  const guide = `
    ${statusText ? `<p class="remind-note"><b>同步状态：</b>${escapeHtml(statusText)}</p>` : ""}
    <p class="remind-note"><b>当前打卡入口：</b>${modeInfo.label}。${modeInfo.desc}</p>
    <p>早间提醒：${s.morningOn === "1" ? `每天 ${s.morningTime}` : "已关闭"}；晚间检查：${s.nightOn === "1" ? `每天 ${s.nightTime}` : "已关闭"}；天气推送：${s.weatherOn === "1" ? `每天 ${s.weatherTime}` : "已关闭"}。</p>
    <p><b>服务器定时</b>：保存后服务器会自动重写 Sakura 专属 crontab，不需要手动进服务器改。</p>
    <pre class="remind-code"># 当前将同步到服务器
${s.morningOn === "1" ? `${morning[1] || "00"} ${morning[0] || "10"} * * * notify_daily.py --morning` : "# 早间提醒已关闭"}
${s.nightOn === "1" ? `${night[1] || "00"} ${night[0] || "20"} * * * notify_daily.py --night` : "# 晚间检查已关闭"}
${s.weatherOn === "1" ? `${weather[1] || "30"} ${weather[0] || "22"} * * * notify_daily.py --weather` : "# 天气推送已关闭"}</pre>
    <p><b>配置提示</b>：${modeInfo.note}</p>
  `;
  $("#remindGuide").innerHTML = guide;
}

async function doCheckin() {
  try {
    await fetch("/api/today/done");
    setCheckinUI(true);
  } catch (e) {
    $("#checkinHint").textContent = "打卡失败：" + e.message;
  }
}

async function testPush(kind) {
  const hint = $("#pushTestHint");
  const mode = currentCheckinMode();
  const modeInfo = checkinModeMeta(mode);
  hint.textContent = `正在发送${modeInfo.label}测试推送…`;
  try {
    const res = await fetch(`/api/push/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ checkin_mode: mode }),
    });
    const r = await res.json();
    if (r.configured === false) {
      hint.textContent = mode === "wework"
        ? "未配置企业微信机器人 Webhook：请在下方推送通道配置里保存企业微信机器人。"
        : mode === "pushplus"
          ? "未配置 PushPlus Token：请在下方推送通道配置里保存 PushPlus Token。"
          : "未配置推送通道：请先配置企业微信、PushPlus 或邮箱 SMTP。";
      $("#pushConfigBadge").textContent = "未配置推送";
      $("#pushConfigBadge").className = "tag status wrong";
    } else if (r.ok) {
      hint.textContent = `已发送，请到${modeInfo.channelText}查看。`;
      $("#pushConfigBadge").textContent = "推送已配置";
      $("#pushConfigBadge").className = "tag status";
    } else {
      hint.textContent = "发送失败：" + notificationDetailText(r.detail || r);
    }
  } catch (e) {
    hint.textContent = "请求失败：" + e.message;
  }
}

function emailSecureFromData(data = {}) {
  if (String(data.email_use_ssl || "0") === "1") return "ssl";
  if (String(data.email_use_starttls || "0") === "1") return "starttls";
  return "none";
}

function emailSecurePayload() {
  const secure = $("#emailSecure")?.value || "ssl";
  return {
    email_use_ssl: secure === "ssl" ? "1" : "0",
    email_use_starttls: secure === "starttls" ? "1" : "0",
  };
}

async function loadNotificationSettings() {
  if (!$("#notifySettingsBadge")) return;
  try {
    const data = await api("/api/notification/settings");
    const configured = data.has_wework || data.has_pushplus || data.has_email;
    $("#notifySettingsBadge").textContent = configured ? "推送已配置" : "未配置推送";
    $("#notifySettingsBadge").className = `tag ${configured ? "" : "status wrong"}`;
    if ($("#pushConfigBadge")) {
      $("#pushConfigBadge").textContent = configured ? "推送已配置" : "未配置推送";
      $("#pushConfigBadge").className = `tag ${configured ? "status" : "status wrong"}`;
    }
    if ($("#notifyAppPublicUrl")) {
      $("#notifyAppPublicUrl").value = "";
      $("#notifyAppPublicUrl").placeholder = data.masked_app_public_url ? `已保存：${data.masked_app_public_url}` : "例如：https://your-domain.example";
    }
    if ($("#weworkWebhook")) $("#weworkWebhook").placeholder = data.masked_wework ? `已保存：${data.masked_wework}` : "未保存";
    if ($("#pushplusToken")) $("#pushplusToken").placeholder = data.masked_pushplus ? `已保存：${data.masked_pushplus}` : "未保存";
    if ($("#emailEnabled")) $("#emailEnabled").value = String(data.email_enabled || "0") === "1" ? "1" : "0";
    if ($("#emailHost")) {
      $("#emailHost").value = data.email_host || "";
      $("#emailHost").placeholder = data.email_host ? `已保存：${data.email_host}` : "smtp.qq.com";
    }
    if ($("#emailPort")) {
      $("#emailPort").value = data.email_port || "";
      $("#emailPort").placeholder = data.email_port ? `已保存：${data.email_port}` : "465";
    }
    if ($("#emailSecure")) $("#emailSecure").value = emailSecureFromData(data);
    if ($("#emailUser")) {
      $("#emailUser").value = "";
      $("#emailUser").placeholder = data.masked_email_user ? `已保存：${data.masked_email_user}` : "your@qq.com";
    }
    if ($("#emailPassword")) {
      $("#emailPassword").value = "";
      $("#emailPassword").placeholder = data.has_email_password ? "已保存：授权码已配置" : "邮箱授权码，不是登录密码";
    }
    if ($("#emailTo")) {
      $("#emailTo").value = "";
      $("#emailTo").placeholder = data.masked_email_to ? `已保存：${data.masked_email_to}` : "多个邮箱用逗号分隔";
    }
    if ($("#emailFromName")) {
      $("#emailFromName").value = data.email_from_name || "";
      $("#emailFromName").placeholder = data.email_from_name ? `已保存：${data.email_from_name}` : "Sakura 做题集";
    }
    if ($("#notifySettingsHint")) {
      const channels = [
        data.has_wework ? "企业微信机器人" : "",
        data.has_pushplus ? "PushPlus" : "",
        data.has_email ? "邮箱" : "",
      ].filter(Boolean).join("、");
      $("#notifySettingsHint").textContent = channels
        ? `当前已保存：${channels}。只用企业微信时，第一块保持已保存即可；空着保存不会清空原值。`
        : "还没有推送通道；推荐先填写第一块的公网地址和企业微信机器人 Webhook。";
    }
  } catch (error) {
    $("#notifySettingsBadge").textContent = "配置读取失败";
    $("#notifySettingsBadge").className = "tag status wrong";
    if ($("#notifySettingsHint")) $("#notifySettingsHint").textContent = error.message;
  }
}

function securityEventLabel(type) {
  const map = {
    login_failed: "登录失败",
    login_locked: "触发锁定",
    login_blocked: "锁定拦截",
    login_success: "登录成功",
    password_updated: "密码更新",
  };
  return map[type] || type || "安全事件";
}

function renderSecurityEvents(events = []) {
  const box = $("#securityRecentEvents");
  if (!box) return;
  if (!events.length) {
    box.innerHTML = `<p class="empty-note compact">暂无安全事件记录。</p>`;
    return;
  }
  box.innerHTML = events.slice(0, 6).map((event) => {
    const detail = event.detail || {};
    const ua = detail.user_agent ? ` · ${escapeHtml(String(detail.user_agent).slice(0, 80))}` : "";
    return `
      <div class="security-event">
        <span>${escapeHtml(securityEventLabel(event.event_type))}</span>
        <strong>${escapeHtml(event.ip || "unknown")}</strong>
        <small>${escapeHtml(event.created_at || "")}${ua}</small>
      </div>`;
  }).join("");
}

async function loadSecuritySettings() {
  if (!$("#securitySettingsBadge")) return;
  try {
    const data = await api("/api/security/settings");
    $("#securitySettingsBadge").textContent = data.password_configured ? "访问密码已启用" : "尚未启用访问密码";
    $("#securitySettingsBadge").className = data.password_configured ? "security-ok" : "security-warn";
    const policy = data.policy || {};
    $("#securityPolicyText").textContent = `至少 ${policy.min_length || 12} 位，必须包含 ${(policy.requires || ["字母", "数字", "特殊字符"]).join("、")}；失败锁定：${(policy.lock_steps || []).join(" → ")}。`;
    renderSecurityEvents(data.recent_events || []);
  } catch (error) {
    $("#securitySettingsBadge").textContent = "安全设置读取失败";
    $("#securitySettingsBadge").className = "security-warn";
    if ($("#securitySettingsHint")) $("#securitySettingsHint").textContent = error.message;
  }
}

async function saveSecuritySettings() {
  const hint = $("#securitySettingsHint");
  const password = $("#adminPassword")?.value || "";
  const confirm = $("#adminPasswordConfirm")?.value || "";
  if (hint) hint.textContent = "正在保存访问密码...";
  if (password !== confirm) {
    if (hint) hint.textContent = "两次输入的密码不一致。";
    return;
  }
  try {
    const data = await api("/api/security/settings", {
      method: "POST",
      body: JSON.stringify({
        admin_password: password,
        admin_password_confirm: confirm,
      }),
    });
    if ($("#adminPassword")) $("#adminPassword").value = "";
    if ($("#adminPasswordConfirm")) $("#adminPasswordConfirm").value = "";
    if (hint) hint.textContent = data.message || "访问密码已保存。";
    setTimeout(() => {
      window.location.href = "/login";
    }, 1200);
  } catch (error) {
    if (hint) hint.textContent = error.message;
  }
}

async function saveNotificationSettings() {
  const hint = $("#notifySettingsHint");
  if (hint) hint.textContent = "正在保存推送配置...";
  try {
    const data = await api("/api/notification/settings", {
      method: "POST",
      body: JSON.stringify({
        app_public_url: $("#notifyAppPublicUrl")?.value.trim() || "",
        wework_webhook: $("#weworkWebhook")?.value.trim() || "",
        pushplus_token: $("#pushplusToken")?.value.trim() || "",
        email_enabled: $("#emailEnabled")?.value || "",
        email_host: $("#emailHost")?.value.trim() || "",
        email_port: $("#emailPort")?.value.trim() || "",
        ...emailSecurePayload(),
        email_user: $("#emailUser")?.value.trim() || "",
        email_password: $("#emailPassword")?.value.trim() || "",
        email_to: $("#emailTo")?.value.trim() || "",
        email_from_name: $("#emailFromName")?.value.trim() || "",
      }),
    });
    if ($("#weworkWebhook")) $("#weworkWebhook").value = "";
    if ($("#pushplusToken")) $("#pushplusToken").value = "";
    if ($("#notifyAppPublicUrl")) $("#notifyAppPublicUrl").value = "";
    if ($("#emailUser")) $("#emailUser").value = "";
    if ($("#emailPassword")) $("#emailPassword").value = "";
    if ($("#emailTo")) $("#emailTo").value = "";
    await loadNotificationSettings();
    if (hint) hint.textContent = data.message || "已保存推送配置。";
  } catch (error) {
    if (hint) hint.textContent = error.message;
  }
}

// ==========================================================================
// 天气推送设置
// ==========================================================================
async function testEmailNotification() {
  const hint = $("#notifySettingsHint");
  if (hint) hint.textContent = "正在发送测试邮件...";
  try {
    const data = await api("/api/notification/test-email", {
      method: "POST",
      body: "{}",
    });
    if (hint) hint.textContent = data.ok ? "测试邮件已发送，请检查收件箱或垃圾邮件。" : "测试邮件发送失败。";
    await loadNotificationSettings();
  } catch (error) {
    if (hint) hint.textContent = `测试邮件发送失败：${error.message}`;
  }
}

async function loadWeatherSettings() {
  if (!$("#weatherCity")) return;
  try {
    const data = await api("/api/weather/settings");
    $("#weatherCity").value = data.city || data.default_city || "";
  } catch (_) {}
}

async function saveWeatherCity() {
  const city = $("#weatherCity")?.value.trim();
  if (!city) return;
  const box = $("#weatherPreviewBox");
  box.textContent = "正在保存城市...";
  try {
    const data = await api("/api/weather/settings", {
      method: "POST",
      body: JSON.stringify({ city }),
    });
    box.textContent = `已保存城市：${data.city}`;
  } catch (error) {
    box.textContent = error.message;
  }
}

function weatherInfoText(info) {
  if (!info) return "没有天气数据。";
  return [
    `${info.city || ""} → ${info.resolved_city || ""}`,
    `日期：${info.date || "-"}`,
    `天气：${info.weather_text || "-"}`,
    `气温：${info.temp_min ?? "-"}℃ ~ ${info.temp_max ?? "-"}℃`,
    `降水概率：${info.rain_probability ?? "-"}%`,
    `最大风速：${info.wind_max ?? "-"} km/h`,
    `来源：${info.source || "open-meteo"}`,
  ].join("\n");
}

async function previewWeather() {
  const city = $("#weatherCity")?.value.trim();
  const box = $("#weatherPreviewBox");
  box.textContent = "正在查询明天天气...";
  try {
    const data = await api(`/api/weather/preview?city=${encodeURIComponent(city || "")}`);
    box.textContent = weatherInfoText(data.weather);
  } catch (error) {
    box.textContent = error.message;
  }
}

async function previewWeatherPush() {
  const city = $("#weatherCity")?.value.trim();
  const box = $("#weatherPreviewBox");
  box.textContent = "正在生成推送预览...";
  try {
    const data = await api("/api/weather/reminder", {
      method: "POST",
      body: JSON.stringify({ city }),
    });
    box.textContent = `${data.title}\n\n${data.content}`;
  } catch (error) {
    box.textContent = error.message;
  }
}

async function testWeatherPush() {
  const city = $("#weatherCity")?.value.trim();
  const box = $("#weatherPreviewBox");
  const mode = currentCheckinMode();
  const modeInfo = checkinModeMeta(mode);
  box.textContent = `正在发送${modeInfo.label}天气测试推送...`;
  try {
    const data = await api("/api/push/weather", {
      method: "POST",
      body: JSON.stringify({ city, checkin_mode: mode }),
    });
    if (data.ok) {
      box.textContent = `已发送天气推送：${data.title}\n\n请到${modeInfo.channelText}查看。`;
      if ($("#pushConfigBadge")) {
        $("#pushConfigBadge").textContent = "推送已配置";
        $("#pushConfigBadge").className = "tag status";
      }
    } else {
      box.textContent = "发送失败：" + notificationDetailText(data.detail || data);
    }
  } catch (error) {
    box.textContent = error.message;
  }
}

// ==========================================================================
// AI 对话测试台 / API 设置
// ==========================================================================
let lastAiChatAnswer = "";
