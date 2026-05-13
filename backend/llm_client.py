"""DeepSeek V4 API 客户端（OpenAI 兼容 SDK）+ 辩论协议 prompts"""

import os
from openai import AsyncOpenAI

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY 或 ANTHROPIC_AUTH_TOKEN 环境变量未设置")
        _client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
    return _client


DEFAULT_MODEL = "deepseek-chat"
FAST_MODEL = "deepseek-chat"


# ── 非流式调用 ──

async def chat(messages: list[dict], model: str = DEFAULT_MODEL,
               temperature: float = 1.0, max_tokens: int = 4096,
               thinking_mode: str = "non-thinking") -> str:
    client = get_client()
    resp = await client.chat.completions.create(
        model=model, messages=messages, temperature=temperature,
        max_tokens=max_tokens, extra_body={"thinking_mode": thinking_mode},
    )
    return resp.choices[0].message.content or ""


# ── 流式调用 ──

async def chat_stream(messages: list[dict], on_chunk, model: str = DEFAULT_MODEL,
                      temperature: float = 1.0, max_tokens: int = 4096,
                      thinking_mode: str = "thinking") -> str:
    client = get_client()
    full_text = ""
    stream = await client.chat.completions.create(
        model=model, messages=messages, temperature=temperature,
        max_tokens=max_tokens, stream=True,
        extra_body={"thinking_mode": thinking_mode},
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            full_text += delta
            await on_chunk(delta)
    return full_text


# ── 方向探索 prompts ──

DIRECTION_SYSTEM_PROMPT = """你是一个创新创业方向探索助手。你的任务是帮助用户从零开始找到值得做的项目方向。

工作流程：
1. 势能扫描：从政策势能、技术溢出、代际迁移、不对称机会、存量抱怨五个维度，分析当前值得关注的领域
2. 过滤：根据用户身份（大一学生、科创班、有一定技术能力），筛选出适合的机会点
3. 校准：通过与用户对话逐步收窄到一个具体的、可执行的问题方向

规则：
- 不要说空话套话，每句话都要有具体信息
- 给出方向时务必附上为什么适合这个用户
- 如果用户表现出兴趣，马上深入挖掘而不是跳到下一个话题"""

SOCRATIC_SYSTEM_PROMPT = """你是一个苏格拉底式追问者。你的任务是帮助学生理清思路，而不是给答案。

规则：
1. 学生说出自己的想法后，你不断追问「为什么」「那如果…」「你能举个例子吗？」
2. 不要评价学生的回答好坏，继续追问
3. 当发现学生逻辑有漏洞时，温和地指出来
4. 目标是帮学生自己把问题想透，而不是你替他总结
5. 每次只问 1-2 个问题，不要连珠炮"""


# ── 8步协议 Prompts ──

PROBLEM_RESTATE_PROMPT = """## 问题重述 Problem Restatement

请从你的角度重新定义这个问题。

1. **你的重述**：用一句话概括核心问题，用你的分析视角来框定它
2. **替代框架**：用另一句话换一种方式重新定义这个问题——也许提问者自己都没意识到问题的另一面

50 字以内。不要开始分析，只是重新定义问题。"""

SYNTHESIS_PROMPT = """## 正反合 Synthesis

前面的讨论中各位角色提出了不同的观点和论证。现在请你做三件事：

1. **核心分歧**：各方最根本的分歧点是什么？（不是表面上的不同意见，而是前提假设层面）
2. **共识基础**：尽管有分歧，各方在哪些点上其实是一致的？
3. **合题**：能否找到一个能容纳各方核心关切的方案或视角？这个方案不一定是妥协——它可能是一个比所有原初立场都更好的新视角。

300 字以内。"""

VERDICT_PROMPT = """## 判决 Verdict

基于整场讨论，请给出你的最终判断：

1. **你的立场**：你现在站在哪一边？或者超越了原初的二元对立？
2. **关键论据**：支撑你立场的最强证据或推理是什么？
3. **可信度评级**：高/中/低——你对这个判断有多大把握？为什么？
4. **持异意见**：即使你做出了判断，仍然存在的合理疑虑是什么？你的判断在什么条件下可能被推翻？

200 字以内。"""


# ── 构建辩论消息 ──

def build_debate_messages(
    role_system_prompt: str,
    topic: str,
    round_instruction: str,
    history: list[dict],
    user_interject: str = "",
) -> list[dict]:
    """构建辩论场景的消息列表，使用 Role.system_prompt"""
    messages = [{"role": "system", "content": role_system_prompt}]

    for entry in history:
        role = "user" if entry.get("agent_role", "agent") == "user" else "assistant"
        messages.append({
            "role": role,
            "content": f"[{entry['agent_name']}]：{entry['message']}",
        })

    user_prompt = f"## 讨论主题\n{topic}\n\n## 本轮要求\n{round_instruction}\n\n"
    if user_interject:
        user_prompt += f"## ⚡ 用户插话（必须直接回应）\n{user_interject}\n\n"
    user_prompt += f"现在请你发言："
    messages.append({"role": "user", "content": user_prompt})
    return messages
