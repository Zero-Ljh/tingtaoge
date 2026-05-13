"""Claude Code CLI 子进程通信模块（Windows 兼容）"""

import asyncio
import shutil
import sys


def _find_claude() -> tuple[str, list[str]]:
    """
    找到 claude 命令的可用路径和启动参数。
    返回 (executable, args_prefix)
    """
    path = shutil.which("claude") or shutil.which("claude.cmd") or shutil.which("claude.CMD")
    if not path:
        return "claude", []

    if sys.platform == "win32" and (path.lower().endswith(".cmd") or path.lower().endswith(".bat")):
        return "cmd.exe", ["/c", path]

    return path, []


_CLAUDE_EXE, _CLAUDE_PREFIX = _find_claude()


async def _run_claude(prompt: str, timeout: int, stream_callback=None) -> str:
    """
    通过管道将 prompt 传给 claude -p，读取输出。
    使用 stdin 传 prompt（兼容 Windows 的 .CMD 包装）。
    """
    full_args = _CLAUDE_PREFIX + ["-p"] if _CLAUDE_PREFIX else ["-p"]
    prompt_bytes = (prompt + "\n").encode("utf-8")

    try:
        process = await asyncio.create_subprocess_exec(
            _CLAUDE_EXE, *full_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return "[错误：未找到 `claude` 命令]"
    except Exception as e:
        return f"[启动失败：{e}]"

    if stream_callback:
        # 流式：边读 stdout 边回调
        output_parts: list[str] = []
        try:
            # 写 prompt 到 stdin
            process.stdin.write(prompt_bytes)
            await process.stdin.drain()
            process.stdin.close()

            while True:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=timeout)
                if not line:
                    break
                text = line.decode(errors="replace")
                output_parts.append(text)
                await stream_callback(text)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            await stream_callback("[超时]")
            return "[超时]"

        await process.wait()
        return "".join(output_parts).strip()
    else:
        # 非流式：一次性通信
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=prompt_bytes), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return "[超时]"

        if process.returncode != 0:
            err = stderr.decode(errors="replace").strip() if stderr else ""
            if err:
                return f"[调用失败：{err}]"

        result = stdout.decode(errors="replace").strip() if stdout else ""
        return result if result else "(无输出)"


async def call_claude(prompt: str, timeout: int = 120) -> str:
    return await _run_claude(prompt, timeout)


async def call_claude_stream(prompt: str, on_chunk, timeout: int = 120) -> str:
    return await _run_claude(prompt, timeout, stream_callback=on_chunk)
