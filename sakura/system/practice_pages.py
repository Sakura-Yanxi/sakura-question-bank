from __future__ import annotations

import json


PRACTICE_TITLE = "Sakura \u5feb\u901f\u56de\u586b"
LOADING_TEXT = "\u6b63\u5728\u8bfb\u53d6\u672c\u6b21\u63a8\u9001..."
INVALID_BATCH_HTML = "\u8fd9\u4e2a\u6279\u6b21\u4e0d\u5b58\u5728\u6216\u5df2\u5931\u6548\u3002<br><a href=\"/\">\u56de\u5230\u505a\u9898\u96c6</a>"
EMPTY_BATCH_HTML = "\u672c\u6b21\u63a8\u9001\u6ca1\u6709\u9898\u76ee\u3002<br><a href=\"/\">\u56de\u5230\u505a\u9898\u96c6</a>"
DONE_TITLE = "\u4eca\u65e5\u6253\u5361\u6210\u529f"
DONE_MESSAGE = (
    "\u505a\u5f97\u5f88\u597d\u3002\u4eca\u5929\u7684\u590d\u4e60\u95ed\u73af\u5df2\u7ecf\u5b8c\u6210\uff0c"
    "\u9519\u9898\u6ca1\u6709\u88ab\u6d6a\u8d39\u3002<br>"
    "\u4fdd\u6301\u8fd9\u4e2a\u8282\u594f\uff0c\u540e\u9762\u4f1a\u8d8a\u6765\u8d8a\u7a33\u3002"
)


def render_practice_page(batch_id: str) -> str:
    batch_json = json.dumps(batch_id)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{PRACTICE_TITLE}</title>
  <style>
    :root {{ --pink:#ec4899; --green:#10b981; --red:#ef4444; --amber:#f59e0b; --ink:#172033; --muted:#718096; --line:#eadde7; --bg:#fff7fb; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; color:var(--ink); background:linear-gradient(180deg,#fff 0%,var(--bg) 100%); }}
    header {{ position:sticky; top:0; z-index:3; padding:14px 16px; background:rgba(255,255,255,.94); backdrop-filter:blur(14px); border-bottom:1px solid var(--line); }}
    h1 {{ margin:0; font-size:20px; }}
    .sub {{ margin-top:6px; color:var(--muted); font-size:13px; line-height:1.5; }}
    .progress {{ margin-top:10px; height:8px; background:#f3e8ef; border-radius:999px; overflow:hidden; }}
    .bar {{ height:100%; width:0%; background:linear-gradient(90deg,var(--pink),#f472b6); transition:.2s; }}
    main {{ padding:14px; max-width:760px; margin:0 auto; }}
    .card {{ background:#fff; border:1px solid var(--line); border-radius:18px; margin:0 0 14px; overflow:hidden; box-shadow:0 10px 28px rgba(236,72,153,.08); }}
    .qhead {{ display:flex; justify-content:space-between; gap:10px; padding:12px 14px; border-bottom:1px solid #f3e8ef; }}
    .qhead strong {{ font-size:16px; line-height:1.45; }}
    .qhead span {{ color:var(--muted); font-size:12px; line-height:1.45; text-align:right; }}
    .image-wrap {{ padding:10px; background:#fbfafc; }}
    img {{ width:100%; display:block; border-radius:12px; border:1px solid #eee; background:#fff; }}
    .meta {{ padding:0 14px 10px; display:flex; flex-wrap:wrap; gap:8px; }}
    .tag {{ border-radius:999px; padding:5px 9px; font-size:12px; background:#f8eaf2; color:#9d174d; }}
    textarea {{ width:calc(100% - 28px); margin:0 14px 12px; min-height:64px; resize:vertical; border:1px solid var(--line); border-radius:12px; padding:10px; font:inherit; }}
    .actions {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; padding:0 14px 14px; }}
    button {{ border:0; border-radius:13px; padding:12px 8px; font-weight:800; color:#fff; font-size:15px; }}
    button:disabled {{ opacity:.6; }}
    .ok {{ background:var(--green); }} .bad {{ background:var(--red); }} .half {{ background:var(--amber); }}
    .done {{ outline:3px solid rgba(16,185,129,.25); }}
    .empty {{ padding:40px 18px; text-align:center; color:var(--muted); line-height:1.7; }}
    .toast {{ position:fixed; left:16px; right:16px; bottom:18px; padding:12px 14px; background:#172033; color:#fff; border-radius:14px; opacity:0; transform:translateY(12px); transition:.2s; text-align:center; z-index:5; }}
    .toast.show {{ opacity:1; transform:translateY(0); }}
    a {{ color:var(--pink); font-weight:800; text-decoration:none; }}
  </style>
</head>
<body>
  <header>
    <h1>{PRACTICE_TITLE}</h1>
    <div class="sub" id="summary">{LOADING_TEXT}</div>
    <div class="progress"><div class="bar" id="bar"></div></div>
  </header>
  <main id="list"></main>
  <div class="toast" id="toast"></div>
  <script>
    const batchId = {batch_json};
    const list = document.getElementById("list");
    const summary = document.getElementById("summary");
    const bar = document.getElementById("bar");
    const toast = document.getElementById("toast");
    const STATUS_RIGHT = "\\u505a\\u5bf9";
    const STATUS_WRONG = "\\u505a\\u9519";
    const STATUS_HALF = "\\u534a\\u4f1a";
    let state = null;

    function esc(s) {{
      return String(s ?? "").replace(/[&<>"']/g, c => ({{ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }}[c]));
    }}

    function praise(status, remaining) {{
      if (remaining === 0) return "\\u4eca\\u5929\\u8fd9\\u7ec4\\u9519\\u9898\\u6536\\u5de5\\u4e86\\u3002\\u5f88\\u7a33\\uff0c\\u771f\\u6b63\\u6709\\u5728\\u628a\\u6f0f\\u6d1e\\u8865\\u4e0a\\u3002";
      if (status === STATUS_RIGHT) return "\\u6f02\\u4eae\\uff0c\\u8fd9\\u9898\\u5df2\\u7ecf\\u88ab\\u4f60\\u62ff\\u56de\\u6765\\u4e86\\u3002";
      if (status === STATUS_HALF) return "\\u80fd\\u6807\\u51fa\\u534a\\u4f1a\\u5c31\\u4e0d\\u4e8f\\uff0c\\u4e0b\\u4e00\\u8f6e\\u4f1a\\u66f4\\u51c6\\u3002";
      return "\\u53d1\\u73b0\\u95ee\\u9898\\u5c31\\u662f\\u8fdb\\u6b65\\u7684\\u5165\\u53e3\\uff0c\\u5df2\\u7ecf\\u5e2e\\u4f60\\u8bb0\\u4e0b\\u6765\\u4e86\\u3002";
    }}

    function showToast(text) {{
      toast.textContent = text;
      toast.classList.add("show");
      setTimeout(() => toast.classList.remove("show"), 2400);
    }}

    async function load() {{
      const res = await fetch(`/api/practice/${{batchId}}`);
      if (!res.ok) {{
        list.innerHTML = '<div class="empty">{INVALID_BATCH_HTML}</div>';
        return;
      }}
      state = await res.json();
      render();
    }}

    function render() {{
      const b = state.batch;
      const qs = state.questions || [];
      const done = Number(b.done_count || 0);
      const total = Number(b.question_count || 0);
      summary.textContent = `${{b.day}} \\u00b7 \\u5df2\\u56de\\u586b ${{done}}/${{total}} \\u9053`;
      bar.style.width = total ? `${{Math.round(done / total * 100)}}%` : "0%";
      list.innerHTML = qs.map(q => `
        <article class="card ${{q.quick_status ? "done" : ""}}" id="q-${{q.id}}">
          <div class="qhead">
            <strong>\\u7b2c ${{q.batch_position}} \\u9898 \\u00b7 ${{esc(q.category || "\\u5f85\\u5f52\\u7c7b")}}</strong>
            <span>${{esc(q.subject || "")}}<br>${{esc(q.document_title || q.filename || "")}}</span>
          </div>
          <div class="image-wrap"><img src="${{q.image_url}}" alt="\\u9898\\u76ee\\u56fe" loading="lazy"></div>
          <div class="meta">
            <span class="tag">\\u5f53\\u524d\\uff1a${{esc(q.status || "\\u672a\\u505a")}}</span>
            <span class="tag">${{esc(q.chapter || "\\u672a\\u8bc6\\u522b\\u7ae0\\u8282")}}</span>
            ${{q.quick_status ? `<span class="tag">\\u5df2\\u56de\\u586b\\uff1a${{esc(q.quick_status)}}</span>` : ""}}
          </div>
          <textarea data-note="${{q.id}}" placeholder="\\u53ef\\u9009\\uff1a\\u4e00\\u53e5\\u8bdd\\u5907\\u6ce8\\uff0c\\u7535\\u8111\\u7aef\\u4e4b\\u540e\\u53ef\\u8be6\\u7ec6\\u590d\\u76d8">${{esc(q.quick_note || "")}}</textarea>
          <div class="actions">
            <button class="ok" data-id="${{q.id}}" data-status="${{STATUS_RIGHT}}">\\u505a\\u5bf9</button>
            <button class="bad" data-id="${{q.id}}" data-status="${{STATUS_WRONG}}">\\u505a\\u9519</button>
            <button class="half" data-id="${{q.id}}" data-status="${{STATUS_HALF}}">\\u534a\\u4f1a</button>
          </div>
        </article>`).join("") || '<div class="empty">{EMPTY_BATCH_HTML}</div>';
    }}

    list.addEventListener("click", async (event) => {{
      const btn = event.target.closest("button[data-id]");
      if (!btn) return;
      btn.disabled = true;
      const id = btn.dataset.id;
      const noteEl = document.querySelector(`[data-note="${{id}}"]`);
      const note = noteEl ? noteEl.value : "";
      try {{
        const res = await fetch(`/api/practice/${{batchId}}/questions/${{id}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ status: btn.dataset.status, note }})
        }});
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "\\u4fdd\\u5b58\\u5931\\u8d25");
        const remaining = Math.max(0, (state?.batch?.question_count || 0) - (state?.batch?.done_count || 0) - 1);
        showToast(praise(btn.dataset.status, remaining));
        await load();
      }} catch (e) {{
        showToast(e.message);
      }} finally {{
        btn.disabled = false;
      }}
    }});

    load();
  </script>
</body>
</html>"""


def render_today_done_page(app_public_url: str) -> str:
    home_url = app_public_url.rstrip("/") or "/"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{DONE_TITLE}</title>
  <style>
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background:linear-gradient(135deg,#FBF1F6,#FCE7F1); color:#20242E; }}
    .card {{ width:min(92vw,420px); background:#fff; padding:38px 34px; border-radius:22px; text-align:center; box-shadow:0 12px 40px -16px rgba(236,72,153,.4); }}
    .big {{ width:58px; height:58px; margin:0 auto; display:grid; place-items:center; border-radius:18px; background:#fce7f3; color:#db2777; font-size:34px; font-weight:900; }}
    .t {{ font-size:21px; font-weight:900; margin:16px 0 8px; }}
    .s {{ color:#6B7280; font-size:14px; line-height:1.75; }}
    a {{ display:inline-flex; margin-top:18px; color:#DB2777; text-decoration:none; font-weight:800; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="big">&#10003;</div>
    <div class="t">{DONE_TITLE}</div>
    <div class="s">{DONE_MESSAGE}</div>
    <a href="{home_url}">\u56de\u5230\u505a\u9898\u96c6</a>
  </div>
</body>
</html>"""
