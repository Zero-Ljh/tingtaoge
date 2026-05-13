"""听涛阁 — FastAPI 应用入口（重构版）"""

import os
import uuid
import asyncio
import json
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.agent_manager import AgentManager
from backend.roles import list_modes, get_roles_for_mode
from backend.llm_client import chat

app = FastAPI(title="听涛阁")

# 挂载静态文件
root_dir = os.path.dirname(__file__)
static_dir = os.path.join(root_dir, "static")
os.makedirs(static_dir, exist_ok=True)

# 新前端目录（Vite build 输出）
dist_dir = os.path.join(root_dir, "frontend", "dist")
if os.path.isdir(dist_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_dir, "assets")), name="assets")


# 讨论会话存储
sessions: dict[str, dict] = {}


# ── 请求模型 ──

class StartRequest(BaseModel):
    topic: str
    mode: str = "debate"
    roles: list[str] | None = None
    rounds: int = 3
    extra: dict | None = None


class InterjectRequest(BaseModel):
    session_id: str
    message: str


class EndRequest(BaseModel):
    session_id: str


class QuestionSuggestRequest(BaseModel):
    session_id: str


# ── API 路由 ──

@app.get("/")
async def root():
    """优先返回新前端，其次回退到旧版"""
    index_path = os.path.join(dist_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/api/modes")
async def get_modes():
    """返回所有可用模式"""
    return {"modes": list_modes()}


@app.get("/api/roles")
async def get_roles(mode: str | None = None):
    """返回角色列表，可选按模式过滤"""
    if mode:
        roles = get_roles_for_mode(mode)
        return {
            "mode": mode,
            "roles": [
                {"id": r.role_id, "name": r.name, "personality": r.personality,
                 "stance": r.stance, "color": r.color, "emoji": r.emoji}
                for r in roles
            ],
        }
    from .roles import ROLE_LIBRARY
    return {
        "roles": [
            {"id": r.role_id, "name": r.name, "personality": r.personality,
             "stance": r.stance, "color": r.color, "emoji": r.emoji}
            for r in ROLE_LIBRARY.values()
        ],
    }


@app.post("/api/start")
async def start_discussion(req: StartRequest):
    if not req.topic.strip():
        raise HTTPException(400, "主题不能为空")

    valid_modes = set(list_modes().keys())
    valid_modes.add("debate")
    if req.mode not in valid_modes:
        raise HTTPException(400, f"无效模式：{req.mode}，可选：{', '.join(sorted(valid_modes))}")
    if req.rounds < 1 or req.rounds > 10:
        raise HTTPException(400, "轮次范围 1-10")

    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    user_event = asyncio.Event()
    user_input_container: list = []
    continue_event = asyncio.Event()

    session = {
        "id": session_id,
        "topic": req.topic,
        "mode": req.mode,
        "rounds": req.rounds,
        "status": "running",
        "history": [],
        "queue": queue,
        "manager": None,
        "user_event": user_event,
        "user_input": user_input_container,
        "continue_event": continue_event,
    }
    sessions[session_id] = session

    manager = AgentManager(
        session_id=session_id,
        topic=req.topic,
        mode=req.mode,
        role_ids=req.roles,
        rounds=req.rounds,
        queue=queue,
        user_event=user_event,
        user_input_container=user_input_container,
        continue_event=continue_event,
        extra=req.extra or {},
    )
    session["manager"] = manager
    asyncio.create_task(manager.run())

    agents_info = [
        {"id": f"agent_{i}", "name": a.name, "color": a.color, "emoji": a.emoji}
        for i, a in enumerate(manager.agents)
    ] if manager.agents else []

    return {
        "session_id": session_id,
        "agents": agents_info,
        "mode": req.mode,
        "status": "started",
    }


@app.get("/api/stream/{session_id}")
async def stream_discussion(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "讨论不存在")

    async def event_gen():
        try:
            while True:
                data = await asyncio.wait_for(session["queue"].get(), timeout=600)
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                if data.get("type") in ("done", "error"):
                    break
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'message': '连接超时'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/interject")
async def interject(req: InterjectRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "讨论不存在")
    if session["status"] != "running":
        raise HTTPException(400, "讨论已结束")

    session["user_input"].append(req.message)
    session["user_event"].set()

    await session["queue"].put({
        "type": "user_interjection",
        "agent_id": "user",
        "agent_name": "你",
        "message": req.message,
    })
    return {"status": "ok"}


@app.post("/api/continue/{session_id}")
async def continue_discussion(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "讨论不存在")
    session["continue_event"].set()
    return {"status": "continued"}


@app.post("/api/question-suggest")
async def question_suggest(req: QuestionSuggestRequest):
    """『这题我不会问』— 生成 3 个提问示例"""
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "讨论不存在")

    manager = session.get("manager")
    if manager:
        asyncio.create_task(manager.run_question_suggestion())
        return {"status": "started"}

    # 没有 manager（异常情况），直出
    prompt = (
        f"## 主题\n{session['topic']}\n\n"
        f"用户不知道该怎么提问。请从 3 个完全不同的角度各生成一个提问示例。"
    )
    asyncio.create_task(_direct_suggestion(session_id, session["queue"], prompt))
    return {"status": "started"}


async def _direct_suggestion(session_id: str, queue: asyncio.Queue, prompt: str):
    result = await chat([{"role": "user", "content": prompt}],
                        temperature=0.9, max_tokens=2048)
    await queue.put({
        "type": "question_suggestions",
        "suggestions": result,
    })


@app.post("/api/end")
async def end_discussion(req: EndRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "讨论不存在")
    session["status"] = "ending"
    await session["queue"].put({"type": "done"})
    return {"status": "ended", "message": "讨论已结束"}


# ── 报告 & 导出 ──

@app.get("/api/report/{session_id}")
async def get_report(session_id: str):
    report_path = os.path.join(root_dir, "data", f"{session_id}-report.md")
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            return {"report": f.read()}
    return {"report": None, "message": "报告尚未生成"}


@app.get("/api/transcript/{session_id}")
async def get_transcript(session_id: str):
    transcript_path = os.path.join(root_dir, "data", f"{session_id}-transcript.md")
    if os.path.exists(transcript_path):
        with open(transcript_path, "r", encoding="utf-8") as f:
            return {"transcript": f.read()}
    return {"transcript": None}


@app.get("/api/export/{session_id}")
async def export_html(session_id: str):
    """导出为 HTML，按课程作业格式排版"""
    session = sessions.get(session_id)
    report_path = os.path.join(root_dir, "data", f"{session_id}-report.md")
    transcript_path = os.path.join(root_dir, "data", f"{session_id}-transcript.md")

    topic = session["topic"] if session else "讨论记录"
    mode = session["mode"] if session else "unknown"

    report_text = ""
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            report_text = f.read()

    transcript_text = ""
    if os.path.exists(transcript_path):
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript_text = f.read()

    html = _build_export_html(topic, mode, report_text, transcript_text)
    return StreamingResponse(
        iter([html]),
        media_type="text/html",
        headers={"Content-Disposition": f"attachment; filename=\"{session_id}-report.html\""},
    )


def _build_export_html(topic: str, mode: str, report: str, transcript: str) -> str:
    """构建排版干净的 HTML 导出"""
    report_html = _md_to_html(report) if report else "<p>暂无报告</p>"
    transcript_html = _md_to_html(transcript) if transcript else "<p>暂无记录</p>"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{topic} — 讨论报告</title>
<style>
  @media print {{ @page {{ margin: 2cm; }} }}
  body {{ font-family: -apple-system, "Noto Sans SC", "Microsoft YaHei", sans-serif;
         max-width: 800px; margin: 0 auto; padding: 2rem 1.5rem;
         line-height: 1.8; color: #1a1a2e; background: #fff; }}
  h1 {{ font-size: 1.6rem; border-bottom: 2px solid #1a5276; padding-bottom: .5rem; margin-bottom: 2rem; }}
  h2 {{ font-size: 1.2rem; color: #1a5276; margin-top: 2rem; }}
  h3 {{ font-size: 1.05rem; color: #2d6a4f; }}
  hr {{ border: none; border-top: 1px solid #eee; margin: 2rem 0; }}
  blockquote {{ border-left: 3px solid #1a5276; margin: 1rem 0; padding: .5rem 1rem; background: #f8f9fa; }}
  code {{ background: #f0f0f0; padding: .15rem .4rem; border-radius: 3px; font-size: .9em; }}
  pre {{ background: #f5f5f5; padding: 1rem; border-radius: 6px; overflow-x: auto; }}
  .meta {{ color: #666; font-size: .9rem; margin-bottom: 2rem; }}
  .section {{ margin-bottom: 2rem; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #1a1a2e; color: #e0e0e0; }}
    h2 {{ color: #7fb3d8; }} h3 {{ color: #6abf8a; }}
    blockquote {{ background: #16213e; border-left-color: #7fb3d8; }}
    code, pre {{ background: #0f3460; }}
    .meta {{ color: #999; }}
    hr {{ border-top-color: #333; }}
  }}
</style>
</head>
<body>
<h1>{topic}</h1>
<div class="meta">
  <p>模式：{mode} | 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</div>
<div class="section">
  <h2>讨论报告</h2>
  {report_html}
</div>
<hr>
<div class="section">
  <h2>完整讨论记录</h2>
  {transcript_html}
</div>
</body>
</html>"""


def _md_to_html(md: str) -> str:
    """极简 markdown → HTML 转换"""
    import re
    lines = md.split("\n")
    html_parts = []
    in_list = False
    for line in lines:
        # 标题
        m = re.match(r"^###?\s+(.+)$", line)
        if m:
            level = 3 if line.startswith("###") else 2
            html_parts.append(f"<h{level}>{m.group(1)}</h{level}>")
            continue
        # 无序列表
        if line.startswith("- "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{line[2:]}</li>")
            continue
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
        # 空行
        if not line.strip():
            html_parts.append("")
            continue
        html_parts.append(f"<p>{line}</p>")
    if in_list:
        html_parts.append("</ul>")
    return "\n".join(html_parts)


@app.get("/api/history")
async def list_history():
    """扫描 data/ 目录，列出所有讨论记录"""
    import glob, re
    data_dir = os.path.join(root_dir, "data")
    report_files = glob.glob(os.path.join(data_dir, "*-report.md"))
    entries = []
    for fpath in sorted(report_files, reverse=True):
        fname = os.path.basename(fpath)
        sid = fname.replace("-report.md", "")
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                header = f.read(800)
            topic = ""
            date = ""
            mode = ""
            roles = ""
            for line in header.split("\n"):
                if line.startswith("# 讨论报告：") or line.startswith("# 原始记录"):
                    topic = line.split("：", 1)[-1] if "：" in line else ""
                elif line.startswith("- 日期"):
                    date = line.split("：", 1)[-1] if "：" in line else ""
                elif line.startswith("- 模式"):
                    mode = line.split("：", 1)[-1] if "：" in line else ""
                elif line.startswith("- 角色"):
                    roles = line.split("：", 1)[-1] if "：" in line else ""
            entries.append({
                "session_id": sid,
                "topic": topic.strip(),
                "date": date.strip(),
                "mode": mode.strip(),
                "roles": roles.strip(),
                "has_report": True,
            })
        except:
            continue
    return {"entries": entries}


@app.get("/api/status/{session_id}")
async def get_status(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "讨论不存在")
    return {
        "session_id": session_id,
        "status": session["status"],
        "mode": session["mode"],
        "topic": session["topic"],
    }


if __name__ == "__main__":
    import uvicorn
    os.makedirs("data", exist_ok=True)
    print("[听涛阁] 启动：http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
