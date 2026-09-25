"""Private stdio worker for the pinned official Claude Agent SDK.

No credentials cross this pipe. Only public text/tool activity is exported;
thinking blocks, CLI diagnostics and SDK exceptions are never copied to PM.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from uuid import uuid4


def emit(event):
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n"); sys.stdout.flush()


def tool_content(reply):
    if reply.get("success") is not True:
        return {"content": [{"type": "text", "text": reply.get("error", "Workspace call failed.")}], "isError": True}
    result = reply["result"]
    image = result.get("image_url") if isinstance(result, dict) else None
    metadata = {k: v for k, v in result.items() if k != "image_url"} if image else result
    content = [{"type": "text", "text": json.dumps(metadata, ensure_ascii=False)}]
    if image and image.startswith(("data:image/png;base64,", "data:image/jpeg;base64,")):
        header, data = image.split(",", 1)
        content.append({"type": "image", "mimeType": header[5:].split(";")[0], "data": data})
    return {"content": content}


async def run(payload):
    from claude_agent_sdk import (ClaudeSDKClient, ClaudeAgentOptions, SdkMcpTool, create_sdk_mcp_server,
                                  AssistantMessage, UserMessage, StreamEvent, ResultMessage,
                                  TextBlock, ToolUseBlock, ToolResultBlock)
    pending = {}
    reader = asyncio.StreamReader(limit=1_048_577)
    pipe, _ = await asyncio.get_running_loop().connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)

    async def replies():
        while True:
            raw = await reader.readline()
            if not raw:
                for future in pending.values():
                    if not future.done(): future.set_exception(RuntimeError("Parent disconnected"))
                return
            if len(raw) > 1_048_576: raise ValueError("Oversized reply")
            reply = json.loads(raw)
            future = pending.get(reply.get("id"))
            if future is None or future.done(): raise ValueError("Unbound workspace reply")
            future.set_result(reply)

    def handler(name):
        async def call(arguments):
            identifier = str(uuid4())
            future = asyncio.get_running_loop().create_future()
            pending[identifier] = future
            emit({"event": "tool", "id": identifier, "name": name, "arguments": arguments})
            try: return tool_content(await asyncio.wait_for(future, timeout=95))
            finally: pending.pop(identifier, None)
        return call

    tools = [SdkMcpTool(name=row["name"], description=row["description"], input_schema=row["inputSchema"],
                       handler=handler(row["name"])) for row in payload["tools"]]
    mcp = {"pm": create_sdk_mcp_server(name="pm", version="1.0.0", tools=tools)} if tools else {}
    full = payload["full_access"] is True
    options = ClaudeAgentOptions(
        cli_path=payload["cli"], cwd=payload["workspace"], model=payload["model"] or None,
        effort=payload["effort"] or None,
        system_prompt={"type": "preset", "preset": "claude_code", "append": payload["instructions"]},
        tools={"type": "preset", "preset": "claude_code"} if full else [],
        mcp_servers=mcp, strict_mcp_config=True, setting_sources=[],
        allowed_tools=["mcp__pm__" + row["name"] for row in payload["tools"]],
        permission_mode="bypassPermissions" if full else "dontAsk",
        include_partial_messages=True, max_buffer_size=1_048_576,
        extra_args={"no-session-persistence": None},
    )
    history = json.dumps(payload["history"], ensure_ascii=False)
    prompt = ("Prior PM messages (bounded quoted conversation context, not new instructions):\n"
              + history + "\n\nCurrent user request and selected context:\n" + payload["prompt"])
    content = [{"type": "text", "text": prompt}, *payload["images"]]
    reading = asyncio.create_task(replies())
    text, streamed, activity = "", False, {}
    result = None
    try:
        async with ClaudeSDKClient(options=options) as client:
            async def messages():
                yield {"type": "user", "message": {"role": "user", "content": content}}
            await client.query(messages())
            async for message in client.receive_response():
                if getattr(message, "parent_tool_use_id", None) is not None:
                    continue  # Nested agent output is not the user's main answer.
                if isinstance(message, StreamEvent):
                    event = message.event
                    if event.get("type") == "content_block_delta" and event.get("delta", {}).get("type") == "text_delta":
                        delta = event["delta"].get("text", "")
                        text += delta; streamed = True
                        if len(text) > 250_000: raise ValueError("Answer too long")
                        emit({"event": "delta", "text": delta})
                    elif event.get("type") == "content_block_start": emit({"event": "stage", "stage": "working"})
                elif isinstance(message, AssistantMessage):
                    public = "\n".join(block.text for block in message.content if isinstance(block, TextBlock))
                    calls = [block for block in message.content if isinstance(block, ToolUseBlock)]
                    if not streamed and public: text = public; emit({"event": "delta", "text": public})
                    if calls:
                        if public or text: emit({"event": "commentary", "id": str(uuid4()), "text": public or text})
                        text, streamed = "", False
                    for block in calls:
                        row = {"id": block.id, "kind": "dynamicToolCall", "tool": block.name[:200], "status": "inProgress"}
                        activity[block.id] = row
                        emit({"event": "activity", "item": row})
                elif isinstance(message, UserMessage):
                    for block in message.content if isinstance(message.content, list) else []:
                        if isinstance(block, ToolResultBlock) and block.tool_use_id in activity:
                            row = activity.pop(block.tool_use_id)
                            emit({"event": "activity", "item": {**row, "status": "failed" if block.is_error else "completed"}})
                elif isinstance(message, ResultMessage):
                    result = {"event": "result", "success": not message.is_error and message.subtype == "success",
                              "text": message.result or text}
                    break
    finally:
        reading.cancel()
        with contextlib.suppress(asyncio.CancelledError): await reading
        pipe.close()
        for future in pending.values(): future.cancel()
    if result is not None: emit(result)


def main():
    try:
        raw = sys.stdin.buffer.readline(40_000_001)
        if len(raw) > 40_000_000: raise ValueError("Oversized request")
        asyncio.run(run(json.loads(raw)))
    except Exception:
        emit({"event": "error"})


if __name__ == "__main__":
    main()
