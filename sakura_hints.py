from __future__ import annotations

import sys
import traceback
from typing import Callable


def infer_concept_hint(question: dict, *, default_category: str) -> str:
    text = f"{question.get('category', '')} {question.get('chapter', '')} {question.get('ocr_text', '')}".lower()
    rules = [
        (["洛必达", "l'h", "lhopital", "0/0", "∞/∞"], "核心定理：洛必达法则。先确认是否满足 0/0 或 ∞/∞ 型，再分别求分子分母导数。"),
        (["等价", "无穷小", "lim", "极限"], "核心定理：等价无穷小替换与极限四则运算。先判断主导项，再化简为标准极限。"),
        (["泰勒", "麦克劳林"], "核心定理：泰勒展开。优先围绕展开点保留到第一个非零项或题目所需阶数。"),
        (["级数", "收敛", "发散"], "核心定理：级数收敛判别法。先判断是正项级数、交错级数、幂级数还是一般项级数。"),
        (["积分", "原函数", "不定积分"], "核心方法：换元积分或分部积分。先观察复合函数结构与可微因子。"),
        (["微分方程", "通解", "特解"], "核心方法：一阶方程分类。先判断可分离、齐次、线性，或是否需要积分因子。"),
        (["导数", "微分", "求导"], "核心定理：复合函数求导法则。先拆外层函数与内层函数。"),
        (["矩阵", "行列式", "特征值"], "核心定理：矩阵初等变换与特征方程。先明确目标是化简、求秩还是求特征值。"),
    ]
    for keywords, hint in rules:
        if any(keyword in text for keyword in keywords):
            return hint
    return f"核心概念：{question.get('category') or default_category}。先回到该知识点的定义、适用条件和标准题型。"


def infer_key_step_hint(question: dict) -> str:
    text = f"{question.get('category', '')} {question.get('chapter', '')} {question.get('ocr_text', '')}".lower()
    if "洛必达" in text or "0/0" in text or "∞/∞" in text:
        return "关键第一步：把原式整理成分式极限，并验证分子、分母同时趋于 0 或同时趋于无穷，再考虑求导。"
    if "泰勒" in text or "麦克劳林" in text:
        return "关键第一步：选定展开点，写出常用展开式，例如 e^x、sin x、ln(1+x)，并判断需要保留到几阶。"
    if "级数" in text:
        return "关键第一步：先写出通项 a_n，判断是否满足 a_n -> 0；若不满足，可直接判定发散。"
    if "积分" in text:
        return "关键第一步：寻找一个可设为 u 的内层表达式，检查 du 是否能在积分式中配出来。"
    if "微分方程" in text:
        return "关键第一步：把方程整理成 y' = f(x, y) 或标准线性形式 y' + P(x)y = Q(x)。"
    if "导数" in text or "微分" in text:
        return "关键第一步：先标出外层函数，再对内层整体求导，避免漏乘链式法则中的内导数。"
    return "关键第一步：先把已知条件、要求目标和可用公式分三行写出来，再选择最直接的变形入口。"


def full_solution_fallback(question: dict, *, default_category: str) -> str:
    return (
        "Level 3 完整解析：\n"
        f"1. 先识别知识点：{question.get('category', default_category)}。\n"
        "2. 写出题目所需的核心公式。\n"
        "3. 按公式代入并逐步化简。\n\n"
        "当前未配置 AI 接口密钥，因此返回本地简版解析。"
    )


def generate_hint(
    question: dict,
    level: int,
    *,
    llm_enabled: bool,
    call_llm: Callable,
    default_subject: str,
    default_category: str,
    default_chapter: str,
    default_document_kind: str,
) -> str:
    if level == 1:
        return infer_concept_hint(question, default_category=default_category)
    if level == 2:
        return infer_key_step_hint(question)

    fallback = full_solution_fallback(question, default_category=default_category)
    if not llm_enabled:
        return fallback
    try:
        prompt = f"""
你是严谨的数学助教。请为下面题目生成 Level 3 Full Solution。
要求：
- 使用 Markdown + LaTeX。
- 公式用 $$...$$ 或 \\(...\\)。
- 先列关键定理，再给完整步骤，最后给易错点。
- 不要省略关键代数变形。

科目：{question.get('subject', default_subject)}
章节：{question.get('chapter', default_chapter)}
资料类型：{question.get('document_kind', default_document_kind)}
知识点：{question.get('category', default_category)}
元认知错因：{', '.join(question.get('meta_tags') or []) or question.get('mistake_reason') or '未填写'}
题目文字：
{question.get('ocr_text', '')[:4000]}
"""
        return call_llm(prompt, temperature=0.25) or fallback
    except Exception:
        print("LLM hint failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return fallback


def variation_fallback(question: dict, *, default_category: str) -> str:
    return (
        "难度梯度变式：\n"
        f"Base：同属「{question.get('category', default_category)}」，只换数字，不换核心逻辑。\n"
        "Advanced：改变求解目标，例如由求导改为求原函数、由判定改为求参数范围。\n"
        "Pro：跨章节综合，把本题知识点与前置概念组合训练。"
    )


def generate_variations(
    question: dict,
    *,
    llm_enabled: bool,
    call_llm: Callable,
    default_subject: str,
    default_category: str,
    default_chapter: str,
    default_document_kind: str,
) -> str:
    fallback = variation_fallback(question, default_category=default_category)
    if not llm_enabled:
        return fallback + "\n\n当前未配置 AI 接口密钥，因此使用本地简版举一反三。"
    try:
        prompt = f"""
你是学习训练教练。请根据错题生成“难度梯度变式”，使用 Markdown + LaTeX。
科目：{question.get('subject', default_subject)}
章节：{question.get('chapter', default_chapter)}
资料类型：{question.get('document_kind', default_document_kind)}
知识点：{question.get('category', default_category)} / {question.get('subcategory', '')}
错因：{', '.join(question.get('meta_tags') or []) or question.get('mistake_reason') or '未填写'}
备注：{question.get('user_note') or '无'}
原题文字：
{question.get('ocr_text', '')[:3500]}

请输出：
1. 题型迁移规律
2. Base：换数不换逻辑，只给 1 道题
3. Advanced：变换求解目标，只给 1 道题
4. Pro：跨章节综合，只给 1 道题
5. 每道题的训练目标，不给完整答案
"""
        return call_llm(prompt, temperature=0.45) or fallback
    except Exception:
        print("LLM variations failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return fallback
