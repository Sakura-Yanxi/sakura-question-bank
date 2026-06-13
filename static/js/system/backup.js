// Backup and data-migration UI helpers for Sakura.
// Loaded after app.js so shared helpers ($, api, refresh) are available.
// Daily-queue refresh goes through window.SakuraDaily.load() (daily.js).

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
      await window.SakuraDaily?.load();
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
  await window.SakuraDaily?.load();
}

// Migration panel bindings

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
