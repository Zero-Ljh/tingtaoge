"""Agent 调度器 — 管理多模式、多角色的讨论编排"""

import asyncio
import os
from datetime import datetime

from .roles import get_roles_for_mode
from .llm_client import (
    chat_stream, chat, build_debate_messages,
    DIRECTION_SYSTEM_PROMPT, SOCRATIC_SYSTEM_PROMPT,
)


class AgentManager:
    """管理一次讨论会话的全部调度"""

    def __init__(self, session_id: str, topic: str, mode: str,
                 role_ids: list[str] | None, rounds: int, queue: asyncio.Queue,
                 user_event: asyncio.Event = None, user_input_container: list = None,
                 continue_event: asyncio.Event = None, extra: dict = None):
        self.session_id = session_id
        self.topic = topic
        self.mode = mode
        self.rounds = rounds
        self.queue = queue
        self.agents = get_roles_for_mode(mode, role_ids)
        self.history: list[dict] = []
        self.extra = extra or {}
        self.user_event = user_event or asyncio.Event()
        self.user_input_container = user_input_container or []
        self.continue_event = continue_event or asyncio.Event()
        self.continue_event.set()

    # ── 入口 ──

    async def run(self):
        try:
            await self._announce_start()

            if self.mode == "direction_explore":
                await self._run_direction_explore()
            elif self.mode == "socratic":
                await self._run_socratic()
            elif self.mode == "brainstorm":
                await self._run_brainstorm()
            elif self.mode in ("debate", "critique", "compare",
                               "bp_polish", "business_model", "risk_explore",
                               "track_compare", "pain_find"):
                await self._run_debate_generic()
            elif self.mode in ("mock_defense", "roadshow", "contest_prep"):
                await self._run_defense()
            else:
                await self._run_debate_generic()

            await self._generate_report()
        except Exception as e:
            await self._emit("error", message=f"讨论异常：{str(e)}")
            raise
        finally:
            await self._emit("done")

    # ── 通用辅助 ──

    async def _emit(self, type_: str, **kwargs):
        await self.queue.put({"type": type_, **kwargs})

    async def _pause(self, message="📖 继续往下看？", timeout=120):
        self.continue_event.clear()
        await self._emit("pause", message=message)
        try:
            await asyncio.wait_for(self.continue_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    def _mode_instructions(self) -> str:
        instructions = {
            "debate": ("每次发言要回应对手的核心观点，指出同意什么、不同意什么。"
                       "用逻辑和论据说话。目的是帮用户把问题想透，不是「赢」。"),
            "brainstorm": "天马行空地打开思路，在别人想法上做联想和拓展。数量比质量重要。",
            "critique": "从你的角度挑刺，指出问题、盲区、可改进之处。要有建设性。",
            "compare": "逐条对比两个观点，高亮分歧点。指出各自的适用场景和局限。",
            "bp_polish": "逐章审视商业计划书，从你的角度找出漏洞和优化空间。",
            "business_model": "评估商业模式的可行性、可持续性、竞争优势。",
            "risk_explore": "从你的专业角度找出潜在风险，越全面越好。",
            "track_compare": "评估两个方向的优劣、风险、资源需求。",
            "pain_find": "从你的角度分析这个方向的真实痛点是否成立。",
        }
        return instructions.get(self.mode, "")

    # ── 标准辩论式多轮模式 ──

    async def _run_debate_generic(self):
        for r in range(1, self.rounds + 1):
            await self._emit("round_start", round=r, total=self.rounds)

            for idx, agent in enumerate(self.agents):
                await self._agent_speak(idx)
                if idx < len(self.agents) - 1:
                    await self._pause()

            await self._ask_user()

    # ── 头脑风暴 ──

    async def _run_brainstorm(self):
        phases = ["发散", "聚焦", "深化"]
        for r in range(1, self.rounds + 1):
            phase = phases[r - 1] if r <= len(phases) else "深化"
            await self._emit("round_start", round=r, total=self.rounds, phase=phase)

            for idx, agent in enumerate(self.agents):
                await self._agent_speak(idx, extra_context=f"## 当前阶段：{phase}")
                if idx < len(self.agents) - 1:
                    await self._pause()

            # 每轮结束后收束
            if self.rounds > 1 and r < self.rounds:
                await self._converge_ideas()

            await self._ask_user()

    # ── 苏格拉底式追问 ──

    async def _run_socratic(self):
        await self._emit("status", message="🧠 苏格拉底模式：说说你的想法，我会一直追问")
        messages = [
            {"role": "system", "content": SOCRATIC_SYSTEM_PROMPT},
            {"role": "user", "content": f"## 主题\n{self.topic}\n\n请说说你对这个问题的看法。"},
        ]

        for r in range(1, self.rounds + 1):
            await self._emit("round_start", round=r, total=self.rounds)

            # AI 追问
            full = ""
            async def push_chunk(chunk):
                nonlocal full
                if chunk.strip():
                    full += chunk
                    await self._emit("agent_chunk", agent_id="socratic",
                                     agent_name="苏格拉底", color="#1a5276",
                                     chunk=chunk)
            await self._emit("agent_start", agent_id="socratic",
                             agent_name="苏格拉底", color="#1a5276")
            await chat_stream(messages, push_chunk,
                              temperature=0.8, max_tokens=2048)
            await self._emit("agent_end", agent_id="socratic",
                             agent_name="苏格拉底", color="#1a5276",
                             message=full)
            messages.append({"role": "assistant", "content": full})
            self.history.append({
                "agent_id": "socratic", "agent_name": "苏格拉底",
                "message": full, "timestamp": datetime.now().isoformat(),
            })

            # 等学生回答
            await self._ask_user(final=(r == self.rounds))
            if self.history and self.history[-1]["agent_id"] == "user":
                messages.append({"role": "user", "content": self.history[-1]["message"]})

    # ── 方向探索模式（势能扫描→过滤→校准） ──

    async def _run_direction_explore(self):
        steps = [
            ("势能扫描",
             "从政策势能、技术溢出、代际迁移、不对称机会、存量抱怨五个维度，"
             "分析当前值得关注的领域。每个维度给出 2-3 个具体方向，附上简要理由。"),
            ("过滤匹配",
             "根据用户身份（大一学生、科创班、有一定技术能力），"
             "从上一步中筛选出最适合的机会点。说明为什么适合、需要什么能力、大概怎么做。"),
            ("兴趣校准",
             "用户选择一个感兴趣的方向后，深入挖掘这个方向里的真实问题和切入点。"
             "逐步收窄到具体可执行的问题定义。"),
        ]

        agent = self.agents[0] if self.agents else None
        messages = [{"role": "system", "content": DIRECTION_SYSTEM_PROMPT}]
        messages.append({"role": "user", "content": f"用户身份：大一学生，科创班，有一定技术能力。\n\n请开始方向探索。"})

        for i, (step_name, instruction) in enumerate(steps):
            await self._emit("round_start", round=i + 1, total=len(steps),
                             phase=step_name)
            await self._emit("status", message=f"🔍 正在{step_name}...")

            messages.append({"role": "user", "content": f"## 当前步骤：{step_name}\n{instruction}"})

            full = ""
            async def push_chunk(chunk):
                nonlocal full
                if chunk.strip():
                    full += chunk
                    await self._emit("agent_chunk", agent_id="direction_guide",
                                     agent_name="方向探索", color="#1a5276",
                                     chunk=chunk)

            await self._emit("agent_start", agent_id="direction_guide",
                             agent_name="方向探索", color="#1a5276")
            await chat_stream(messages, push_chunk,
                              temperature=0.9, max_tokens=4096)
            await self._emit("agent_end", agent_id="direction_guide",
                             agent_name="方向探索", color="#1a5276",
                             message=full)

            messages.append({"role": "assistant", "content": full})
            self.history.append({
                "agent_id": "direction_guide", "agent_name": "方向探索",
                "message": full, "timestamp": datetime.now().isoformat(),
                "step": step_name,
            })

            await self._ask_user(final=(i == len(steps) - 1))
            if self.history and self.history[-1]["agent_id"] == "user":
                messages.append({"role": "user", "content": self.history[-1]["message"]})

    # ── 答辩/路演模拟（高强度轮转） ──

    async def _run_defense(self):
        label = {"mock_defense": "模拟答辩", "roadshow": "路演模拟", "contest_prep": "比赛备战"}.get(self.mode, "答辩")

        await self._emit("status", message=f"🎤 {label}开始！准备好迎接追问")

        for r in range(1, self.rounds + 1):
            await self._emit("round_start", round=r, total=self.rounds)

            for idx, agent in enumerate(self.agents):
                await self._agent_speak(idx)
                # 每个角色问完就给学生回应机会
                await self._ask_user(final=(r == self.rounds and idx == len(self.agents) - 1))

    # ── "这题我不会问" ──

    async def run_question_suggestion(self):
        """由前端触发：展示 3 个不同角度的提问示例"""
        await self._emit("status", message="💡 正在生成提问示例...")
        prompt = (
            f"## 主题\n{self.topic}\n\n"
            f"用户不知道该怎么提问。请从 3 个完全不同的角度各生成一个提问示例，"
            f"每个示例包含：角度名称、为什么要从这个角度问、具体的提问话术。\n\n"
            f"格式：\n"
            f"### 角度1：[名称]\n"
            f"- 为什么从这个角度问：[理由]\n"
            f"- 可以这样问：「[具体问题]」\n"
        )
        result = await chat(
            [{"role": "user", "content": prompt}],
            temperature=0.9, max_tokens=2048,
        )
        await self._emit("question_suggestions", suggestions=result)

    # ── 核心：让某个角色发言 ──

    async def _agent_speak(self, idx: int, extra_context: str = ""):
        agent = self.agents[idx]
        if not agent:
            return

        # 检查用户插话积压
        pending = ""
        if self.user_input_container:
            msgs = list(self.user_input_container)
            self.user_input_container.clear()
            pending = (
                "\n\n## ⚡ 用户插话了（必须直接回应）\n"
                + "\n---\n".join(f"「{m}」" for m in msgs)
            )

        mode_inst = self._mode_instructions()
        messages = build_debate_messages(
            role_name=agent.name,
            personality=agent.personality,
            stance=agent.stance,
            topic=self.topic,
            mode_instructions=mode_inst + ("\n" + extra_context if extra_context else ""),
            history=self.history[-8:] if self.history else [],
            user_interject=pending,
        )

        await self._emit("agent_start", agent_id=f"agent_{idx}",
                         agent_name=agent.name, color=agent.color, emoji=agent.emoji)

        full = ""
        async def push_chunk(chunk):
            nonlocal full
            if chunk.strip():
                full += chunk
                await self._emit("agent_chunk", agent_id=f"agent_{idx}",
                                 agent_name=agent.name, color=agent.color,
                                 chunk=chunk)

        await chat_stream(messages, push_chunk, temperature=0.9, max_tokens=4096)

        self.history.append({
            "agent_id": f"agent_{idx}", "agent_name": agent.name,
            "message": full, "timestamp": datetime.now().isoformat(),
            "agent_role": "agent",
        })

        await self._emit("agent_end", agent_id=f"agent_{idx}",
                         agent_name=agent.name, color=agent.color,
                         emoji=agent.emoji, message=full)

    # ── 收束：头脑风暴定期聚类 ──

    async def _converge_ideas(self):
        await self._emit("status", message="🔍 正在筛选总结想法...")
        recent = self.history[-3:]
        if not recent:
            return
        ideas_text = "\n".join(f"[{e['agent_name']}]：{e['message'][:800]}" for e in recent)
        prompt = (
            f"以下是一场头脑风暴的最新想法。请做三件事：\n\n"
            f"## 想法\n{ideas_text}\n\n"
            f"1. 用 2-3 句话总结核心内容\n"
            f"2. 筛选最有潜力的 1-2 个方向\n"
            f"3. 提出进一步深化的方向\n\n简洁的 3-5 句话即可。"
        )
        summary = await chat([{"role": "user", "content": prompt}],
                             temperature=0.7, max_tokens=1024)
        if summary:
            await self._emit("converge", summary=summary)

    # ── 询问用户 ──

    async def _ask_user(self, final: bool = False):
        self.user_event.clear()
        self.user_input_container.clear()
        label = "讨论即将结束" if final else f"第 {self.current_history_round()} 步"
        await self._emit("user_turn",
                         message=f"👤 {label}，你怎么看？",
                         final=final)
        try:
            await asyncio.wait_for(self.user_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            await self._emit("user_turn_timeout", message="⏭ 等待超时，继续")
            return

        user_msg = self.user_input_container[0] if self.user_input_container else ""
        if not user_msg.strip():
            return
        self.history.append({
            "agent_id": "user", "agent_name": "你",
            "message": user_msg, "timestamp": datetime.now().isoformat(),
            "agent_role": "user",
        })

    def current_history_round(self):
        agents_in_history = [e for e in self.history if e.get("agent_role") == "agent"]
        if not self.agents:
            return 0
        return len(agents_in_history) // len(self.agents) + 1

    # ── 报告生成 ──

    async def _generate_report(self):
        await self._emit("status", message="📝 讨论结束，正在生成摘要...")

        agents_desc = "\n".join(f"- {a.name}：{a.stance}" for a in self.agents) if self.agents else "- 方向探索向导"
        history_text = "\n".join(
            f"[{e['agent_name']}]：{e['message']}"
            for e in self.history if e.get("agent_role") != "user"
        )
        user_text = "\n".join(
            f"[你]：{e['message']}"
            for e in self.history if e.get("agent_role") == "user"
        )

        prompt = (
            f"请根据以下讨论记录，生成结构化总结报告。\n\n"
            f"## 主题\n{self.topic}\n"
            f"## 模式\n{self.mode}\n"
            f"## 参与角色\n{agents_desc}\n\n"
            f"## 讨论记录\n{history_text or '(无)'}\n\n"
            f"## 用户参与\n{user_text or '(无)'}\n\n"
            f"## 报告结构\n"
            f"1. 讨论摘要（200字内）\n"
            f"2. 各方观点速览（每人核心立场 + 主要论据）\n"
            f"3. 核心分歧点\n"
            f"4. 共识点\n"
            f"5. 参考建议"
        )

        report_text = await chat([{"role": "user", "content": prompt}],
                                 temperature=0.7, max_tokens=4096)

        os.makedirs("data", exist_ok=True)

        # 保存原始记录
        transcript = ""
        for e in self.history:
            name = e["agent_name"]
            ts = e.get("timestamp", "")[:16] if e.get("timestamp") else ""
            transcript += f"\n### **{name}** {ts}\n\n{e['message']}\n\n---\n"

        transcript_path = os.path.join("data", f"{self.session_id}-transcript.md")
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(f"# 原始记录：{self.topic}\n\n")
            f.write(f"- 日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"- 模式：{self.mode}\n")
            roles_str = ", ".join(a.name for a in self.agents) if self.agents else "方向探索"
            f.write(f"- 角色：{roles_str}\n\n")
            f.write(transcript)

        # 保存总结报告
        report_path = os.path.join("data", f"{self.session_id}-report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# 讨论报告：{self.topic}\n\n")
            f.write(f"- 日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"- 模式：{self.mode}\n")
            f.write(f"- 角色：{roles_str}\n\n")
            f.write(report_text)

        await self._emit("report", report=report_text,
                         transcript=transcript, session_id=self.session_id)

    async def _announce_start(self):
        agents_info = [
            {"id": f"agent_{i}", "name": a.name, "color": a.color, "emoji": a.emoji}
            for i, a in enumerate(self.agents)
        ] if self.agents else []
        await self._emit("status",
                         message=f"🏯 {'方向探索' if self.mode == 'direction_explore' else '讨论'}开始！模式：{self.mode}",
                         agents=agents_info)
