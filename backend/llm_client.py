"""DeepSeek V4 API 客户端（OpenAI 兼容 SDK）"""

import os
import asyncio
from openai import AsyncOpenAI

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY 或 ANTHROPIC_AUTH_TOKEN 环境变量未设置")
        _client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
        )
    return _client


# ── 模型选择 ──

DEFAULT_MODEL = "deepseek-v4-pro"
FAST_MODEL = "deepseek-v4-flash"


# ── 角色系统 prompts ──

DEBATE_SYSTEM_PROMPT_TEMPLATE = """你是一个讨论角色，名叫「{name}」。

## 你的性格
{personality}

## 你的立场
{stance}

## 你的发言规则
1. 你正在参与一场围绕给定主题的多角色讨论
2. 每次发言时，你需要回应对手/上一位发言者的核心观点
3. 指出你同意什么、不同意什么，并用逻辑和论据支撑
4. 你可以用问句结尾引导进一步讨论
5. 发言长度：200-500 字，要有实质性内容
6. 你的目的是帮用户把问题想透，而不是为了「赢」
7. 如果对方有道理，大方承认"""

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


async def chat(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    temperature: float = 1.0,
    max_tokens: int = 4096,
    thinking_mode: str = "thinking",
) -> str:
    """非流式调用 DeepSeek V4 Chat Completions"""
    client = get_client()
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={"thinking_mode": thinking_mode},
    )
    return resp.choices[0].message.content or ""


async def chat_stream(
    messages: list[dict],
    on_chunk,
    model: str = DEFAULT_MODEL,
    temperature: float = 1.0,
    max_tokens: int = 4096,
    thinking_mode: str = "thinking",
) -> str:
    """流式调用 DeepSeek V4 Chat Completions，on_chunk(chunk: str) 逐段回调"""
    client = get_client()
    full_text = ""
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        extra_body={"thinking_mode": thinking_mode},
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            full_text += delta
            await on_chunk(delta)
    return full_text


def build_debate_messages(
    role_name: str,
    personality: str,
    stance: str,
    topic: str,
    mode_instructions: str,
    history: list[dict],
    user_interject: str = "",
) -> list[dict]:
    """构建辩论场景的消息列表"""
    system = DEBATE_SYSTEM_PROMPT_TEMPLATE.format(
        name=role_name, personality=personality, stance=stance
    )
    messages = [{"role": "system", "content": system}]

    # 把 history 压缩后加入
    for entry in history:
        role = "user" if entry.get("agent_role", "agent") == "user" else "assistant"
        messages.append({
            "role": role,
            "content": f"[{entry['agent_name']}]：{entry['message']}",
        })

    user_prompt = (
        f"## 主题\n{topic}\n\n"
        f"## 模式规则\n{mode_instructions}\n\n"
    )
    if user_interject:
        user_prompt += (
            f"## ⚡ 用户插话（必须直接回应，不得忽略）\n"
            f"{user_interject}\n\n"
        )
    user_prompt += f"现在请你以「{role_name}」的身份发言："
    messages.append({"role": "user", "content": user_prompt})
    return messages
