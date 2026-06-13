from __future__ import annotations

import base64
import json
import re
from pathlib import Path


def image_to_data_url(image_path: str) -> str:
    """Read a rendered page image and return a data: URL for OpenAI-compatible vision input.
    Returns '' if the file is missing so callers can degrade gracefully."""
    if not image_path:
        return ""
    path = Path(image_path)
    if not path.exists() or not path.is_file():
        return ""
    suffix = path.suffix.lower()
    mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


AI_TEACHER_PROTOCOL = """
你是 Sakura 做题集的 AI 学习教练，不是聊天陪练，也不是只给答案的解析器。
你的回答必须遵守这个教学协议：
1. 先判断用户意图：API 测试、知识讲解、错题复盘、计划制定、情绪/节奏调整。
2. 若涉及学习建议，必须优先使用“本地上下文”里的真实证据；没有证据时明确说“当前证据不足”，不要编造做题记录。
3. 默认采用启发式教学：先给概念抓手，再给关键一步，最后才给完整解法；用户明确要求完整答案时可以直接完整展开。
4. 每次回答至少落到一个可执行动作：今天做什么、做几道、看哪个知识点、如何检查是否掌握。
5. 遇到错题原因，要区分：计算失误、公式遗忘、逻辑死角、题意理解偏差，并给对应纠偏动作。
6. “外部经验库”只能作为参考，不等同于用户自己的证据；如果引用，必须说清楚“这是经验参考，需结合你的错题验证”。
7. 不要长篇鸡汤；语言要像认真负责的老师，清楚、具体、能执行。
推荐输出结构：
- 判断：你现在的问题属于什么类型
- 依据：引用本地上下文中的薄弱点/错题/记忆；没有就说明证据不足
- 教学：概念提示 → 关键步骤 → 必要时完整说明
- 行动：下一步 1-3 个任务
""".strip()


TEACHER_INTENTS = {
    "api_test": "API 测试",
    "concept_explain": "知识讲解",
    "wrong_review": "错题复盘",
    "plan": "计划制定",
    "motivation": "节奏调整",
    "memory_update": "记忆更新",
}


TEACHER_STRATEGIES = {
    "scaffold": {
        "name": "启发式引导",
        "rule": "先给概念抓手，再给关键一步，最后询问是否展开完整解法。",
    },
    "diagnose": {
        "name": "证据诊断",
        "rule": "先引用本地证据，再指出主要矛盾和一个优先级最高的纠偏动作。",
    },
    "drill": {
        "name": "变式训练",
        "rule": "给 Base / Advanced / Pro 三层变式，但每层只保留一个训练目标。",
    },
    "schedule": {
        "name": "复习调度",
        "rule": "把建议转成今日任务、到期复习和薄弱点攻坚，不写空泛计划。",
    },
    "memory": {
        "name": "记忆压缩",
        "rule": "把用户偏好、长期误区和学习策略压缩成可复用老师记忆。",
    },
}


def call_llm(
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.3,
) -> str:
    """Call an OpenAI-compatible chat endpoint."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        result = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
    except Exception as exc:
        raise RuntimeError(normalize_llm_error(exc)) from exc
    return result.choices[0].message.content or ""


def normalize_llm_error(exc: Exception) -> str:
    """Map provider errors to clearer user-facing Chinese messages."""
    body = getattr(exc, "body", None)
    code = ""
    err_type = ""
    message = ""
    if isinstance(body, dict):
        code = str(body.get("code") or "")
        err_type = str(body.get("type") or "")
        message = str(body.get("message") or "")
    raw = str(exc)
    haystack = " ".join([raw, code, err_type, message]).lower()
    if "insufficient_balance" in haystack or "insufficient account balance" in haystack or "402" == code:
        return (
            "当前视觉模型供应商账户余额不足（402）。"
            "请到对应平台充值或确认该模型已开通计费，然后再重试。"
        )
    if "invalid_api_key" in haystack or "incorrect api key" in haystack or "401" == code:
        return "API Key 无效或已失效，请检查 AI 设置中的 Key 是否填写正确。"
    if "model_not_found" in haystack or "404" == code:
        return "模型名称不存在或当前账号无权限调用，请检查模型名和供应商权限。"
    if "rate limit" in haystack or "429" == code:
        return "调用过于频繁，供应商已限流。请稍等片刻后再试。"
    return raw or "AI 调用失败，请稍后重试。"


def extract_json_block(raw: str) -> dict:
    """Extract a fenced JSON object first, then fall back to the first object."""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S)
    if fence:
        return json.loads(fence.group(1))
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        raise ValueError("AI 返回内容不是 JSON")
    return json.loads(match.group(0))


def infer_teacher_intent(message: str) -> str:
    text = (message or "").lower()
    if any(k in text for k in ["今天", "明天", "每日", "复习", "计划", "安排", "进度", "考试", "时间", "任务"]):
        return "plan"
    if any(k in text for k in ["api", "key", "密钥", "能用", "测试", "deepseek"]):
        return "api_test"
    if any(k in text for k in ["错题", "错因", "为什么错", "复盘", "不会", "半会"]):
        return "wrong_review"
    if any(k in text for k in ["记住", "记忆", "偏好", "以后", "导入"]):
        return "memory_update"
    if any(k in text for k in ["烦", "焦虑", "不想", "坚持", "动力", "累", "崩"]):
        return "motivation"
    return "concept_explain"


def choose_teacher_strategy(intent: str, context: dict) -> dict:
    if intent == "wrong_review":
        key = "diagnose"
    elif intent == "plan":
        key = "schedule"
    elif intent == "memory_update":
        key = "memory"
    elif intent == "api_test":
        key = "diagnose"
    else:
        key = "scaffold"
    strategy = dict(TEACHER_STRATEGIES[key])
    strategy["key"] = key
    if context.get("top_gaps") and intent in {"concept_explain", "wrong_review"}:
        strategy["must_reference_gap"] = context["top_gaps"][0].get("name", "")
    return strategy


def build_teacher_turn_instruction(intent: str, strategy: dict) -> str:
    return f"""
本轮意图：{TEACHER_INTENTS.get(intent, intent)}
本轮教学策略：{strategy.get('name')}。
策略规则：{strategy.get('rule')}
执行要求：
1. 开头用一句话说明你判断到的意图。
2. 如果本地上下文里有相关证据，必须引用 1-3 条；如果没有，明确说证据不足。
3. 对知识问题默认不要一上来全解，先用启发式引导；用户要求 full solution 时再完整展开。
4. 对计划问题必须给出具体题量、筛选条件或复习对象。
5. 结尾必须给“下一步动作”，最多 3 条。
""".strip()


def build_teacher_chat_turn(message: str, context: dict, *, call_llm_messages) -> dict:
    intent = infer_teacher_intent(message)
    strategy = choose_teacher_strategy(intent, context)
    turn_instruction = build_teacher_turn_instruction(intent, strategy)
    answer = call_llm_messages(
        [
            {"role": "system", "content": AI_TEACHER_PROTOCOL},
            {"role": "system", "content": turn_instruction},
            {"role": "system", "content": "Local context:\n" + json.dumps(context, ensure_ascii=False)},
            {"role": "user", "content": message},
        ],
        temperature=0.35,
    )
    memory_candidate = build_memory_candidate(message, answer, intent, strategy, context)
    return {
        "answer": answer,
        "intent": intent,
        "strategy": strategy,
        "memory_candidate": memory_candidate,
    }


def build_memory_candidate(user_message: str, answer: str, intent: str, strategy: dict, context: dict) -> str:
    if intent not in {"wrong_review", "plan", "memory_update", "motivation"}:
        return ""
    profile = context.get("profile", {})
    parts = [
        f"意图：{TEACHER_INTENTS.get(intent, intent)}",
        f"策略：{strategy.get('name', '')}",
    ]
    if profile.get("headline"):
        parts.append(f"档案判断：{profile.get('headline')}")
    if context.get("top_gaps"):
        parts.append("当前优先薄弱点：" + "、".join(g.get("name", "") for g in context["top_gaps"][:3] if g.get("name")))
    concise_user = re.sub(r"\s+", " ", user_message).strip()[:120]
    concise_answer = re.sub(r"\s+", " ", answer).strip()[:180]
    parts.append(f"用户本轮问题：{concise_user}")
    parts.append(f"老师本轮建议：{concise_answer}")
    return "；".join(parts)[:900]
