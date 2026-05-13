"""Agent 调度器 — 8步辩论协议 + 多模式编排"""

import asyncio
import os
from datetime import datetime

from .roles import get_roles_for_mode
from .llm_client import (
    chat_stream, chat, build_debate_messages,
    PROBLEM_RESTATE_PROMPT, SYNTHESIS_PROMPT, VERDICT_PROMPT,
    DIRECTION_SYSTEM_PROMPT, SOCRATIC_SYSTEM_PROMPT,
)


class AgentManager:
    """管理一次讨论会话的全部调度，核心是 8 步辩论协议"""

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
            await self._emit("status", message=f"🏯 讨论开始！模式：{self.mode}",
                             agents=[{"id": f"agent_{i}", "name": a.name,
                                      "color": a.color, "emoji": a.emoji}
                                     for i, a in enumerate(self.agents)])

            if self.mode == "direction_explore":
                await self._run_direction_explore()
            elif self.mode == "socratic":
                await self._run_socratic()
            elif self.mode in ("brainstorm", "critique", "risk_explore"):
                await self._run_round_robin()
            else:
                await self._run_debate_protocol()

            await self._generate_report()
        except Exception as e:
            await self._emit("error", message=f"讨论异常：{str(e)}")
            raise
        finally:
            await self._emit("done")

    # ── 辅助 ──

    async def _emit(self, type_: str, **kwargs):
        await self.queue.put({"type": type_, **kwargs})

    async def _pause(self, message="📖 继续往下看？", timeout=120):
        self.continue_event.clear()
        await self._emit("pause", message=message)
        try:
            await asyncio.wait_for(self.continue_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    def _get_round_instruction(self, round_num: int, total: int) -> str:
        """生成每轮的指令"""
        if total == 1:
            return "这是唯一一轮辩论。请完整阐述你的立场：核心观点、主要论据和关键例子。200-500字。"
        if round_num == 1:
            return "第一轮：阐述立场。请阐明你的核心观点和主要论据。200-500字。"
        if round_num == total:
            return f"最后一轮：总结陈词。基于前面的讨论，重申或修正你的立场，回应对手的关键质疑。200-500字。"
        return f"第{round_num}轮：回应与深化。回应对手的核心观点，指出同意什么、不同意什么。200-500字。"

    # ── 8步辩论协议 ──

    async def _run_debate_protocol(self):
        """核心辩论流程：Step 1-3: 开题 → Step 4-5: R1 辩论 → Step 6: 正反合 → Step 7-8: 判决"""
        n_agents = len(self.agents)
        if n_agents == 0:
            await self._emit("error", message="没有可用角色")
            return

        # ── Step 1-3: 各角色开题（问题重述 + 立场阐述） ──
        await self._emit("round_start", round=1, total=self.rounds or 3, phase="开题：问题重述与立场阐述")

        for idx, agent in enumerate(self.agents):
            await self._agent_speak(idx, extra_instruction=PROBLEM_RESTATE_PROMPT)
            if idx < n_agents - 1:
                await self._pause(f"📖 看完{agent.name}的重述了吗？")

        # 用户参与
        await self._ask_user("第1轮结束")

        # ── Step 4-5: 各角色辩论（如果 rounds >= 2） ──
        if self.rounds >= 2:
            for r in range(2, self.rounds + 1):
                is_last = (r == self.rounds)
                phase = "辩论交锋：回应与反驳" if not is_last else f"第{r}轮：总结陈词"
                await self._emit("round_start", round=r, total=self.rounds or 3, phase=phase)

                for idx, agent in enumerate(self.agents):
                    instruction = self._get_round_instruction(r, self.rounds)
                    await self._agent_speak(idx, extra_instruction=instruction)
                    if idx < n_agents - 1:
                        await self._pause()

                if is_last:
                    # Step 6: 正反合 Synthesis
                    await self._run_synthesis()
                else:
                    await self._ask_user(f"第{r}轮结束")
        else:
            # 只有一轮时也做正反合
            await self._run_synthesis()

        # Step 7-8: 最终判决 + 导出
        await self._run_verdict()

    # ── 正反合 Synthesis ──

    async def _run_synthesis(self):
        await self._emit("status", message="🤝 正在整合各方观点...")

        # 让每个角色做一次 synthesis
        for idx, agent in enumerate(self.agents):
            self.continue_event.set()
            self.continue_event.clear()

            messages = build_debate_messages(
                role_system_prompt=agent.system_prompt,
                topic=self.topic,
                round_instruction=SYNTHESIS_PROMPT,
                history=self.history[-6:] if self.history else [],
            )

            await self._emit("agent_start", agent_id=f"agent_{idx}",
                             agent_name=agent.name, color=agent.color, emoji=agent.emoji,
                             synthesis=True)

            full = ""
            async def push_chunk(chunk):
                nonlocal full
                if chunk.strip():
                    full += chunk
                    await self._emit("agent_chunk", agent_id=f"agent_{idx}",
                                     agent_name=agent.name, color=agent.color,
                                     chunk=chunk, synthesis=True)

            await chat_stream(messages, push_chunk, temperature=0.8, max_tokens=2048)

            self.history.append({
                "agent_id": f"agent_{idx}", "agent_name": agent.name,
                "message": f"[正反合] {full}", "timestamp": datetime.now().isoformat(),
                "agent_role": "agent",
            })

            await self._emit("agent_end", agent_id=f"agent_{idx}",
                             agent_name=agent.name, color=agent.color,
                             emoji=agent.emoji, message=full, synthesis=True)

            if idx < len(self.agents) - 1:
                await self._pause()

        await self._ask_user("正反合结束")

    # ── 最终判决 Verdict ──

    async def _run_verdict(self):
        await self._emit("status", message="⚖️ 正在生成最终判决...")

        for idx, agent in enumerate(self.agents):
            messages = build_debate_messages(
                role_system_prompt=agent.system_prompt,
                topic=self.topic,
                round_instruction=VERDICT_PROMPT,
                history=self.history[-8:] if self.history else [],
            )

            await self._emit("agent_start", agent_id=f"agent_{idx}",
                             agent_name=agent.name, color=agent.color, emoji=agent.emoji,
                             verdict=True)

            full = ""
            async def push_chunk(chunk):
                nonlocal full
                if chunk.strip():
                    full += chunk
                    await self._emit("agent_chunk", agent_id=f"agent_{idx}",
                                     agent_name=agent.name, color=agent.color,
                                     chunk=chunk, verdict=True)

            await chat_stream(messages, push_chunk, temperature=0.8, max_tokens=2048)

            self.history.append({
                "agent_id": f"agent_{idx}", "agent_name": agent.name,
                "message": f"[判决] {full}", "timestamp": datetime.now().isoformat(),
                "agent_role": "agent",
            })

            await self._emit("agent_end", agent_id=f"agent_{idx}",
                             agent_name=agent.name, color=agent.color,
                             emoji=agent.emoji, message=full, verdict=True)

            if idx < len(self.agents) - 1:
                await self._pause()

    # ── 轮转式模式（头脑风暴/批评/风险勘探等） ──

    async def _run_round_robin(self):
        for r in range(1, self.rounds + 1):
            phase = {1: "发散", 2: "聚焦", 3: "深化"}.get(r, "深化")
            await self._emit("round_start", round=r, total=self.rounds, phase=phase)

            for idx, agent in enumerate(self.agents):
                await self._agent_speak(idx, extra_instruction=f"## 当前阶段：{phase}")
                if idx < len(self.agents) - 1:
                    await self._pause()

            await self._ask_user(f"第{r}轮结束")

    # ── 苏格拉底式追问 ──

    async def _run_socratic(self):
        await self._emit("status", message="🧠 苏格拉底模式：说说你的想法，我会一直追问")
        messages = [
            {"role": "system", "content": SOCRATIC_SYSTEM_PROMPT},
            {"role": "user", "content": f"## 主题\n{self.topic}\n\n请说说你对这个问题的看法。"},
        ]

        for r in range(1, self.rounds + 1):
            await self._emit("round_start", round=r, total=self.rounds)

            full = ""
            async def push_chunk(chunk):
                nonlocal full
                if chunk.strip():
                    full += chunk
                    await self._emit("agent_chunk", agent_id="socratic",
                                     agent_name="苏格拉底", color="#1a5276", chunk=chunk)

            await self._emit("agent_start", agent_id="socratic",
                             agent_name="苏格拉底", color="#1a5276")
            await chat_stream(messages, push_chunk, temperature=0.8, max_tokens=2048)
            await self._emit("agent_end", agent_id="socratic",
                             agent_name="苏格拉底", color="#1a5276", message=full)
            messages.append({"role": "assistant", "content": full})
            self.history.append({
                "agent_id": "socratic", "agent_name": "苏格拉底",
                "message": full, "timestamp": datetime.now().isoformat(),
            })

            await self._ask_user(final=(r == self.rounds))
            if self.history and self.history[-1]["agent_id"] == "user":
                messages.append({"role": "user", "content": self.history[-1]["message"]})

    # ── 方向探索（势能扫描→过滤→校准） ──

    async def _run_direction_explore(self):
        steps = [
            ("势能扫描", "从政策势能、技术溢出、代际迁移、不对称机会、存量抱怨五个维度分析当前值得关注的领域。每个维度给出 2-3 个具体方向。"),
            ("过滤匹配", "根据用户身份（大一学生、科创班、有一定技术能力），从上一步中筛选出最适合的机会点。说明为什么适合。"),
            ("兴趣校准", "用户选择一个感兴趣的方向后，深入挖掘问题空间，收窄到具体可执行的问题定义。"),
        ]

        messages = [{"role": "system", "content": DIRECTION_SYSTEM_PROMPT}]
        messages.append({"role": "user", "content": f"用户：大一科创班学生，有一定技术能力。\n\n请开始方向探索。"})

        for i, (step_name, instruction) in enumerate(steps):
            await self._emit("round_start", round=i + 1, total=len(steps), phase=step_name)
            await self._emit("status", message=f"🔍 正在{step_name}...")
            messages.append({"role": "user", "content": f"## 步骤：{step_name}\n{instruction}"})

            full = ""
            async def push_chunk(chunk):
                nonlocal full
                if chunk.strip():
                    full += chunk
                    await self._emit("agent_chunk", agent_id="direction_guide",
                                     agent_name="方向探索", color="#1a5276", chunk=chunk)

            await self._emit("agent_start", agent_id="direction_guide",
                             agent_name="方向探索", color="#1a5276")
            await chat_stream(messages, push_chunk, temperature=0.9, max_tokens=4096)
            await self._emit("agent_end", agent_id="direction_guide",
                             agent_name="方向探索", color="#1a5276", message=full)

            messages.append({"role": "assistant", "content": full})
            self.history.append({
                "agent_id": "direction_guide", "agent_name": "方向探索",
                "message": full, "timestamp": datetime.now().isoformat(), "step": step_name,
            })

            await self._ask_user(final=(i == len(steps) - 1))
            if self.history and self.history[-1]["agent_id"] == "user":
                messages.append({"role": "user", "content": self.history[-1]["message"]})

    # ── "这题我不会问" ──

    async def run_question_suggestion(self):
        await self._emit("status", message="💡 正在生成提问示例...")
        prompt = (
            f"## 主题\n{self.topic}\n\n"
            f"用户不知道该怎么提问。请从 3 个完全不同的角度各生成一个提问示例，"
            f"每个包含：角度名称、为什么要从这个角度问、具体提问话术。"
        )
        result = await chat([{"role": "user", "content": prompt}], temperature=0.9, max_tokens=2048)
        await self._emit("question_suggestions", suggestions=result)

    # ── 核心：角色发言 ──

    async def _agent_speak(self, idx: int, extra_instruction: str = ""):
        agent = self.agents[idx]
        if not agent:
            return

        pending = ""
        if self.user_input_container:
            msgs = list(self.user_input_container)
            self.user_input_container.clear()
            pending = "\n\n## ⚡ 用户插话了（必须直接回应）\n" + "\n---\n".join(f"「{m}」" for m in msgs)

        instruction = extra_instruction or self._get_round_instruction(1, self.rounds)
        messages = build_debate_messages(
            role_system_prompt=agent.system_prompt,
            topic=self.topic,
            round_instruction=instruction,
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
                                 agent_name=agent.name, color=agent.color, chunk=chunk)

        await chat_stream(messages, push_chunk, temperature=0.9, max_tokens=4096)

        self.history.append({
            "agent_id": f"agent_{idx}", "agent_name": agent.name,
            "message": full, "timestamp": datetime.now().isoformat(), "agent_role": "agent",
        })

        await self._emit("agent_end", agent_id=f"agent_{idx}",
                         agent_name=agent.name, color=agent.color,
                         emoji=agent.emoji, message=full)

    # ── 用户交互 ──

    async def _ask_user(self, label: str = "", final: bool = False):
        self.user_event.clear()
        self.user_input_container.clear()
        await self._emit("user_turn", message=f"👤 {label}，你怎么看？", final=final)
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
            "message": user_msg, "timestamp": datetime.now().isoformat(), "agent_role": "user",
        })

    # ── 报告生成 ──

    async def _generate_report(self):
        await self._emit("status", message="📝 讨论结束，正在生成报告...")

        agents_desc = "\n".join(f"- {a.name}：{a.identity[:60]}…" for a in self.agents) if self.agents else ""
        debate_text = "\n".join(f"[{e['agent_name']}]：{e['message']}" for e in self.history)
        user_text = "\n".join(f"[你]：{e['message']}" for e in self.history if e.get("agent_role") == "user")

        prompt = (
            f"请根据以下讨论记录生成结构化报告。\n\n## 主题\n{self.topic}\n## 模式\n{self.mode}\n"
            f"## 参与角色\n{agents_desc}\n\n## 讨论记录\n{debate_text or '（无）'}\n\n"
            f"## 用户参与\n{user_text or '（无）'}\n\n## 报告结构\n"
            f"1. 讨论摘要（200字内）\n2. 各方观点速览\n3. 核心分歧点\n4. 共识点\n5. 参考建议"
        )
        report_text = await chat([{"role": "user", "content": prompt}], temperature=0.7, max_tokens=4096)

        os.makedirs("data", exist_ok=True)

        # 保存原始记录
        transcript = "\n".join(
            f"### **{e['agent_name']}** {e.get('timestamp','')[:16]}\n\n{e['message']}\n\n---"
            for e in self.history
        )
        roles_str = ", ".join(a.name for a in self.agents) if self.agents else "方向探索"
        t_path = os.path.join("data", f"{self.session_id}-transcript.md")
        with open(t_path, "w", encoding="utf-8") as f:
            f.write(f"# 原始记录：{self.topic}\n\n- 日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n- 模式：{self.mode}\n- 角色：{roles_str}\n\n{transcript}")

        r_path = os.path.join("data", f"{self.session_id}-report.md")
        with open(r_path, "w", encoding="utf-8") as f:
            f.write(f"# 讨论报告：{self.topic}\n\n- 日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n- 模式：{self.mode}\n- 角色：{roles_str}\n\n{report_text}")

        await self._emit("report", report=report_text, transcript=transcript, session_id=self.session_id)
