# 听涛阁 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal**: 构建一个多 agent 辩论/头脑风暴系统（听涛阁），通过 Claude Code CLI 驱动 3 个子 agent 相互反驳与交叉探讨，帮助用户逼近客观真实。

**架构**：Python FastAPI 后端提供 HTTP + SSE 服务，内嵌 Claude Code CLI 子进程通信，原生 HTML/CSS/JS 前端。用户通过浏览器发起讨论，后端调度 agent 轮转，SSE 实时推送讨论内容。

**Tech Stack**：Python 3.10+, FastAPI, uvicorn, Claude Code CLI, 原生 HTML5/CSS3/JS (ES6)

---

## 文件结构

```
听涛阁/
├── main.py                 # FastAPI 应用入口，路由注册，启动入口
├── requirements.txt        # 依赖：fastapi, uvicorn
├── backend/
│   ├── __init__.py
│   ├── agent_manager.py    # Agent 调度器（轮转、上下文、模式切换）
│   ├── roles.py            # 角色人格预设库（8个角色）
│   └── claude_client.py    # Claude Code CLI 子进程通信
├── static/
│   └── index.html          # 单页应用（内嵌 CSS + JS）
└── data/                   # 讨论记录存档目录
```

### 各文件职责

| 文件 | 职责 |
|------|------|
| `main.py` | FastAPI 应用创建、路由（/start、/stream、/interject、/end、/report）、静态文件挂载、SSE 端点 |
| `backend/roles.py` | 定义角色人格数据结构，预设角色库，角色-模式匹配逻辑 |
| `backend/claude_client.py` | 封装 subprocess 调用 Claude Code CLI，流式读取 stdout，超时处理 |
| `backend/agent_manager.py` | 讨论会话状态管理，轮转调度，上下文构建，模式自动切换检测 |
| `static/index.html` | 前端界面，内嵌完整 CSS 样式和 JS 逻辑（SSE 连接、流式渲染、交互控制） |

---

### Task 1: 项目骨架与依赖

**Files:**
- Create: `听涛阁/main.py`
- Create: `听涛阁/requirements.txt`
- Create: `听涛阁/backend/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
fastapi>=0.110.0
uvicorn>=0.29.0
```

- [ ] **Step 2: Create backend/__init__.py** (empty file)

- [ ] **Step 3: Create main.py — FastAPI 应用骨架**

```python
import os
import uuid
import json
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="听涛阁")

# 静态文件
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join(static_dir, "index.html"))

# 讨论会话存储
sessions: dict = {}

class StartRequest(BaseModel):
    topic: str
    mode: str = "debate"  # debate | brainstorm | mixed
    roles: list[str] | None = None
    rounds: int = 3

class InterjectRequest(BaseModel):
    session_id: str
    message: str

class EndRequest(BaseModel):
    session_id: str

@app.post("/api/start")
async def start_discussion(req: StartRequest):
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "id": session_id,
        "topic": req.topic,
        "mode": req.mode,
        "rounds": req.rounds,
        "status": "pending",
        "history": [],
        "queue": asyncio.Queue(),
    }
    return {"session_id": session_id, "status": "started"}

@app.get("/api/stream/{session_id}")
async def stream_discussion(session_id: str):
    from fastapi.responses import StreamingResponse
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return StreamingResponse(
        event_stream(session),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

async def event_stream(session):
    try:
        while True:
            event_data = await asyncio.wait_for(session["queue"].get(), timeout=300)
            yield f"data: {json.dumps(event_data)}\n\n"
            if event_data.get("type") == "done":
                break
    except asyncio.TimeoutError:
        yield f"data: {json.dumps({'type': 'error', 'message': '讨论超时'})}\n\n"

@app.post("/api/interject")
async def interject(req: InterjectRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    await session["queue"].put({
        "type": "user_interjection",
        "agent_id": "user",
        "agent_name": "你",
        "message": req.message,
    })
    return {"status": "ok"}

@app.post("/api/end")
async def end_discussion(req: EndRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session["status"] = "ending"
    await session["queue"].put({"type": "done"})
    return {"status": "ended"}

@app.get("/api/report/{session_id}")
async def get_report(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    report_path = os.path.join("data", f"{session_id}-report.md")
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            return {"report": f.read()}
    return {"report": "报告尚未生成，请等待讨论结束"}

if __name__ == "__main__":
    import uvicorn
    os.makedirs("data", exist_ok=True)
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

---

### Task 2: 角色系统

**Files:**
- Create: `听涛阁/backend/roles.py`

- [ ] **Step 1: Define 角色数据结构和预设库**

```python
from typing import Protocol

class AgentRole:
    """单个 agent 角色的定义"""
    def __init__(self, role_id: str, name: str, personality: str, stance: str, color: str):
        self.role_id = role_id
        self.name = name
        self.personality = personality  # 角色人格描述
        self.stance = stance            # 立场/视角
        self.color = color              # UI 标识色

# 预设角色库
ROLE_LIBRARY = {
    "optimist": AgentRole(
        "optimist", "技术乐观派",
        "你是一个对新事物充满热情的技术乐观主义者。你总是能看到事物的积极面和发展潜力，善于发现创新带来的机遇。",
        "支持技术发展，认为进步能解决大部分问题",
        "#00b4d8"  # 青
    ),
    "skeptic": AgentRole(
        "skeptic", "怀疑论者",
        "你是一个谨慎的怀疑论者。你习惯质疑表面的结论，喜欢指出逻辑漏洞、潜在风险和未被考虑的因素。你的质疑不是为反对而反对，而是为了帮助大家想得更周全。",
        "保持批判态度，指出问题比给出答案更重要",
        "#f77f00"  # 橙
    ),
    "ethicist": AgentRole(
        "ethicist", "伦理学者",
        "你是一个关注伦理和社会影响的思考者。你关心公平、正义、隐私、人权等价值维度，善于从道德和社会层面分析问题。",
        "关注伦理维度，确保决策不忽视人的价值",
        "#7b2cbf"  # 紫
    ),
    "pragmatist": AgentRole(
        "pragmatist", "实用主义者",
        "你是一个务实的实用主义者。你关心什么在实际中能行得通，关注成本、可行性、效率和可操作性。你讨厌空谈理论，注重落地效果。",
        "关注实际可行性，理论要能落地才有意义",
        "#2d6a4f"  # 绿
    ),
    "idealist": AgentRole(
        "idealist", "理想主义者",
        "你是一个有远见的理想主义者。你关注长期愿景和最高目标，不被眼前的困难束缚。你善于描绘宏伟蓝图，激励人们追求卓越。",
        "坚持最高标准，追求理想而非妥协",
        "#e0a800"  # 金
    ),
    "realist": AgentRole(
        "realist", "现实主义者",
        "你是一个冷静的现实主义者。你关注事实和数据，不被情绪和愿景左右。你善于做最坏的打算，习惯基于现有条件做判断。",
        "基于事实和现状做判断，不抱幻想",
        "#9c6644"  # 棕
    ),
    "innovator": AgentRole(
        "innovator", "跨界创新者",
        "你是一个喜欢跨界思考的创新者。你善于把不同领域的知识联系起来，提出意想不到的解决方案。你相信最好的创意往往来自边界之外。",
        "打破思维定式，用跨领域视角带来新思路",
        "#e3646b"  # 粉
    ),
    "analyst": AgentRole(
        "analyst", "数据分析师",
        "你是一个严谨的数据分析师。你要求任何观点都要有数据或事实支撑，善于发现论证中的逻辑瑕疵，关注统计意义和因果关系。",
        "用数据和逻辑说话，拒绝空洞的观点",
        "#457b9d"  # 蓝
    ),
}

# 不同模式的默认角色组合
MODE_ROLES = {
    "debate": {
        "description": "默认选取立场对立的角色",
        "default": ["optimist", "skeptic", "ethicist"],
    },
    "brainstorm": {
        "description": "默认选取视角互补的角色",
        "default": ["innovator", "pragmatist", "ethicist"],
    },
    "mixed": {
        "description": "默认选取多样化的角色组合",
        "default": ["optimist", "skeptic", "realist"],
    },
}

def get_role(role_id: str) -> AgentRole | None:
    return ROLE_LIBRARY.get(role_id)

def get_roles_for_mode(mode: str, custom_roles: list[str] | None = None) -> list[AgentRole]:
    role_ids = custom_roles or MODE_ROLES.get(mode, {}).get("default", [])
    roles = []
    for rid in role_ids:
        role = get_role(rid)
        if role:
            roles.append(role)
    return roles

def get_roles_mode_roles(mode: str) -> list[str]:
    return MODE_ROLES.get(mode, {}).get("default", [])
```

---

### Task 3: Claude CLI 通信模块

**Files:**
- Create: `听涛阁/backend/claude_client.py`

- [ ] **Step 1: 实现 Claude CLI 子进程调用**

```python
import subprocess
import asyncio
import shlex

async def call_claude(prompt: str, timeout: int = 60) -> str:
    """
    调用 Claude Code CLI，传入 prompt，返回输出文本。
    通过 subprocess 启动 claude -p 命令。
    """
    try:
        process = await asyncio.create_subprocess_exec(
            "claude", "-p", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return "[超时] 该 agent 思考时间过长，已跳过。"

        if process.returncode != 0:
            error_msg = stderr.decode().strip() if stderr else "未知错误"
            return f"[错误] agent 调用失败：{error_msg}"

        return stdout.decode().strip() if stdout else "(无输出)"

    except FileNotFoundError:
        return "[错误] 未找到 Claude Code CLI，请确保已安装 `claude` 命令。"
    except Exception as e:
        return f"[错误] CLI 调用异常：{str(e)}"


async def call_claude_stream(prompt: str, callback, timeout: int = 60):
    """
    流式调用 Claude CLI，逐步将输出传给 callback 函数。
    callback 函数签名：callback(chunk: str)
    """
    try:
        process = await asyncio.create_subprocess_exec(
            "claude", "-p", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        full_output = []
        try:
            while True:
                line = await asyncio.wait_for(
                    process.stdout.readline(), timeout=timeout
                )
                if not line:
                    break
                chunk = line.decode(errors="replace")
                full_output.append(chunk)
                if callback:
                    await callback(chunk)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            await callback("[超时]")
            return "[超时]"

        await process.wait()
        return "".join(full_output).strip()

    except FileNotFoundError:
        msg = "[错误] 未找到 Claude Code CLI"
        if callback:
            await callback(msg)
        return msg
    except Exception as e:
        msg = f"[错误] {str(e)}"
        if callback:
            await callback(msg)
        return msg
```

---

### Task 4: Agent 调度器

**Files:**
- Create: `听涛阁/backend/agent_manager.py`

- [ ] **Step 1: 实现 Agent 调度器核心逻辑**

```python
import asyncio
import json
from .roles import get_role, get_roles_for_mode
from .claude_client import call_claude

class AgentManager:
    """管理多 agent 讨论的调度器"""

    def __init__(self, session_id: str, topic: str, mode: str,
                 role_ids: list[str] | None, rounds: int, queue: asyncio.Queue):
        self.session_id = session_id
        self.topic = topic
        self.mode = mode
        self.rounds = rounds
        self.queue = queue
        self.agents = get_roles_for_mode(mode, role_ids)
        self.history = []
        self.current_round = 0
        self.last_speaker_idx = -1
        self.in_debate_mode = (mode == "debate")
        self.brainstorm_phase = "发散"  # 发散 → 交叉 → 整合

    def _build_system_prompt(self, agent_idx: int, reply_to: str | None = None) -> str:
        """构建 agent 的系统提示词"""
        agent = self.agents[agent_idx]
        mode_desc = {
            "debate": """这是辩论模式。规则：
1. 你前面的人已经发表了观点，你必须直接回应他/她的核心论据
2. 指出你同意什么、不同意什么，并给出理由
3. 你的最终目标是让真理越辩越明，不是"赢"""",
            "brainstorm": f"""这是头脑风暴模式（当前阶段：{self.brainstorm_phase}）。规则：
1. 从你独特的视角出发，提出有价值的见解
2. 你可以补充、扩展、质疑前一个人的观点
3. 目的是覆盖全面的视角，不是分出胜负""",
            "mixed": """这是混合模式。当前可能处于自由讨论阶段也可能处于深度交锋阶段。
请自然地回应前面的观点，如果不同意就直说，如果同意就补充新角度。
自动在发散和交锋之间切换。""",
        }

        context_parts = [
            f"## 你的角色\n你是「{agent.name}」。{agent.personality}",
            f"你的立场：{agent.stance}",
            "",
            f"## 讨论主题\n{self.topic}",
            "",
            f"## 模式说明\n{mode_desc.get(self.mode, '')}",
        ]

        if self.history:
            context_parts.append("\n## 到目前为止的讨论记录")
            for entry in self.history[-6:]:  # 最近6条
                speaker = entry["agent_name"]
                msg = entry["message"][:300]  # 截断避免 token 过长
                context_parts.append(f"\n[{speaker}]：{msg}")

        if reply_to:
            context_parts.append(f"""
## 你需要直接回应的前一位发言
[{reply_to["agent_name"]}] 说：
{reply_to["message"][:500]}

请直接回应以上观点。你可以：
- 同意并补充
- 部分同意但提出不同角度
- 不同意并说明理由
- 指出其中的逻辑问题""")

        context_parts.append(f"""
## 你的发言要求
- 长度：200-400 字，简洁有力
- 必须有实质性内容，不能只是附和
- 如果是辩论模式，必须直接回应对手的观点
- 如果是头脑风暴模式，提出你独特的视角
- 结束时可以用一个问句引出下一轮讨论

现在请开始你的发言：""")

        return "\n".join(context_parts)

    async def run(self):
        """运行完整讨论流程"""
        try:
            await self.queue.put({
                "type": "status",
                "message": f"讨论开始！模式：{self.mode}，共 {self.rounds} 轮",
                "agents": [
                    {"id": f"agent_{i}", "name": a.name, "color": a.color}
                    for i, a in enumerate(self.agents)
                ]
            })

            for round_num in range(1, self.rounds + 1):
                self.current_round = round_num
                await self.queue.put({
                    "type": "round_start",
                    "round": round_num,
                    "total": self.rounds,
                })

                if self.mode == "debate":
                    await self._run_debate_round(round_num)
                elif self.mode == "brainstorm":
                    await self._run_brainstorm_round(round_num)
                else:  # mixed
                    await self._run_mixed_round(round_num)

            # 讨论结束，生成报告
            await self._generate_report()

        except Exception as e:
            await self.queue.put({
                "type": "error",
                "message": f"讨论异常：{str(e)}"
            })
        finally:
            await self.queue.put({"type": "done"})

    async def _speak(self, agent_idx: int, reply_to: str | None = None):
        """让指定 agent 发言"""
        agent = self.agents[agent_idx]
        prompt = self._build_system_prompt(agent_idx, reply_to)

        await self.queue.put({
            "type": "agent_start",
            "agent_id": f"agent_{agent_idx}",
            "agent_name": agent.name,
            "color": agent.color,
        })

        def make_callback(aidx=agent_idx, aname=agent.name, acolor=agent.color):
            async def callback(chunk):
                if chunk.strip():
                    await self.queue.put({
                        "type": "agent_chunk",
                        "agent_id": f"agent_{aidx}",
                        "agent_name": aname,
                        "color": acolor,
                        "chunk": chunk,
                    })
            return callback

        full_message = await call_claude(prompt, timeout=90)

        agent_entry = {
            "agent_id": f"agent_{agent_idx}",
            "agent_name": agent.name,
            "message": full_message,
        }
        self.history.append(agent_entry)

        await self.queue.put({
            "type": "agent_end",
            "agent_id": f"agent_{agent_idx}",
            "agent_name": agent.name,
            "color": agent.color,
            "message": full_message,
        })

        return agent_entry

    async def _run_debate_round(self, round_num: int):
        """辩论模式的一轮：正方 → 反方 → 裁判"""
        order = [0, 1, 2]  # A, B, C
        if round_num % 2 == 0:
            order = [1, 0, 2]  # 偶数轮换反方先发言

        for i, agent_idx in enumerate(order):
            reply_to = self.history[-1] if self.history else None
            await self._speak(agent_idx, reply_to)

    async def _run_brainstorm_round(self, round_num: int):
        """头脑风暴模式的一轮"""
        if round_num <= 1:
            self.brainstorm_phase = "发散"
        elif round_num == 2:
            self.brainstorm_phase = "交叉"
        else:
            self.brainstorm_phase = "整合"

        # 首轮正向，次轮反向，促进交叉
        if round_num % 2 == 1:
            order = [0, 1, 2]
        else:
            order = [2, 1, 0]

        for agent_idx in order:
            reply_to = self.history[-1] if self.history else None
            await self._speak(agent_idx, reply_to)

    async def _run_mixed_round(self, round_num: int):
        """混合模式的一轮"""
        # 首轮像头脑风暴自由发言，之后检测对立点自动切换
        if round_num == 1:
            order = [0, 1, 2]
        else:
            # 检测是否应该进入辩论模式
            should_debate = self._detect_conflict()
            if should_debate:
                # 进入辩论模式：持对立观点的两个 agent 交锋
                order = [0, 1, 0, 1]  # 更多交锋
                await self.queue.put({
                    "type": "status",
                    "message": "检测到观点分歧，自动切换为深度交锋模式",
                })
            else:
                order = [2, 0, 1] if round_num % 2 == 0 else [0, 1, 2]

        for agent_idx in order:
            reply_to = self.history[-1] if self.history else None
            await self._speak(agent_idx, reply_to)

    def _detect_conflict(self) -> bool:
        """检测历史中是否有明显的观点对立"""
        conflict_keywords = ["我不同意", "恰恰相反", "你的观点有问题",
                           "不敢苟同", "我持保留意见", "这说不通",
                           "但你没考虑到", "我反对", "恰恰相反"]
        for entry in self.history[-3:]:
            msg = entry.get("message", "")
            if any(kw in msg for kw in conflict_keywords):
                return True
        return False

    async def _generate_report(self):
        """生成讨论总结报告"""
        await self.queue.put({
            "type": "status",
            "message": "讨论结束，正在生成报告..."
        })

        # 构建总结 prompt
        report_prompt = f"""请根据以下多 agent 讨论记录，生成一份结构化的总结报告。

## 讨论主题
{self.topic}

## 讨论模式
{self.mode}

## 参与角色
{chr(10).join(f"- {a.name}：{a.stance}" for a in self.agents)}

## 讨论记录
{chr(10).join(f"[{e['agent_name']}]：{e['message']}" for e in self.history)}

## 报告要求
请按以下结构生成 Markdown 报告：
1. 讨论摘要（200字以内概述）
2. 各角色观点（每人核心立场、主要论据、最终态度）
3. 核心分歧（列出哪些点上有不同看法，谁支持谁反对）
4. 共识点（有哪些点大家一致认可）
5. 参考建议（给提问者的具体建议）
"""
        report = await call_claude(report_prompt, timeout=120)

        # 保存报告
        import os
        report_path = os.path.join("data", f"{self.session_id}-report.md")
        os.makedirs("data", exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# 讨论报告：{self.topic}\n\n")
            f.write(f"- 日期：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"- 模式：{self.mode}\n")
            f.write(f"- 参与角色：{', '.join(a.name for a in self.agents)}\n\n")
            f.write(report)

        await self.queue.put({
            "type": "report",
            "report": report,
            "session_id": self.session_id,
        })
```

Wait, the `__import__('datetime')` is ugly. Let me fix that.

Also, I realize this plan is getting very long. Let me simplify. The user is in a hurry, so let me make the plan practical and then start building directly. Actually given that the user is waiting and wants to USE this system for homework, maybe I should just build it inline rather than writing a full plan document first.

Hmm but the writing-plans skill says I need to write the plan first. Let me write it efficiently and then invoke subagent-driven-development to execute it.

Actually, thinking about this more practically: the user is waiting. The writing-plans skill is meant for complex cross-cutting features. This is a relatively contained project. Let me write the plan quickly and then just execute it directly since each task is small.

Let me simplify my plan and just write it.<｜end▁of▁thinking｜>

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="Write">
<｜｜DSML｜｜parameter name="content" string="true"># 听涛阁 — 实施计划

**Goal**：Python FastAPI + 原生 HTML/CSS 构建多 agent 辩论/头脑风暴系统，通过 Claude Code CLI 驱动 3 个子 agent

**Tech Stack**：Python 3.10+, FastAPI, uvicorn, Claude Code CLI, 原生 HTML5/CSS3/JS

---

## 文件结构

```
听涛阁/
├── main.py                 # FastAPI 入口 + 路由
├── requirements.txt        # fastapi, uvicorn
├── backend/
│   ├── __init__.py
│   ├── agent_manager.py    # Agent 调度器
│   ├── roles.py            # 角色人格库
│   └── claude_client.py    # Claude CLI 通信
├── static/
│   └── index.html          # 单页应用（内嵌 CSS + JS）
└── data/                   # 讨论记录
```

---

### Task 1: 项目骨架

**Files:**
- Create: `听涛阁/requirements.txt`
- Create: `听涛阁/backend/__init__.py`

- [ ] **Step: 创建 requirements.txt**

```
fastapi>=0.110.0
uvicorn>=0.29.0
```

- [ ] **Step: 创建空的 backend/__init__.py**
- [ ] **Step: 创建 data/ 目录**

---
