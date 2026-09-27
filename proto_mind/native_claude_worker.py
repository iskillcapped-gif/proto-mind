"""Private stdio worker for the pinned official Claude Agent SDK.

No credentials cross this pipe. Only public text/tool activity is exported;
thinking blocks, CLI diagnostics and SDK exceptions are never copied to PM.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from uuid import UUID, uuid4
from proto_mind.native_claude_protocol import (MAX_UPDATE_LINE, UsageMeter, WorkspaceReplies, WorkspaceReplyError, error_code,
                                              tool_finished, tool_row)


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
                                  AssistantMessage, UserMessage, StreamEvent, ResultMessage, SystemMessage,
                                  TextBlock, ToolUseBlock, ToolResultBlock)
    replies = WorkspaceReplies(emit)
    reader = asyncio.StreamReader(limit=MAX_UPDATE_LINE + 1)
    pipe, _ = await asyncio.get_running_loop().connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)

    def handler(name):
        async def call(arguments):
            return tool_content(await replies.call(name, arguments))
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
        # Claude Code prints each tool result as one JSON line, including images read
        # with Read; a 1 MiB cap ended a turn at a 1.25 MB screenshot.
        include_partial_messages=True, max_buffer_size=64 * 1024 * 1024,
        resume=payload.get("session_id") if payload.get("resume") else None,
        resume_session_at=payload.get("resume_at") if payload.get("resume") else None,
        session_id=payload.get("session_id") if not payload.get("resume") else None,
        # Echoed user messages show when an operator update enters the conversation.
        extra_args={"replay-user-messages": None, **({} if payload.get("session_id") else {"no-session-persistence": None})},
    )
    history = json.dumps(payload["history"], ensure_ascii=False)
    prompt = (("Prior PM messages (quoted bootstrap context, not new instructions):\n" + history + "\n\n")
              if not payload.get("resume") else "") + "Current user request and selected context:\n" + payload["prompt"]
    content = [{"type": "text", "text": prompt}, *payload["images"]]
    meter = UsageMeter()
    live = {"client": None, "finished": False, "pending": set()}

    async def steer(update):
        # Claude Code adds a user message that arrives during a turn before the
        # model's next request. If the model has already answered, it runs the
        # message as the next turn of the session, and this turn waits for it.
        identifier, blocks, status = update.get("id"), update.get("content"), "rejected"
        try: valid = isinstance(identifier, str) and str(UUID(identifier)) == identifier
        except ValueError: valid = False
        if valid and live["client"] is not None and not live["finished"] and isinstance(blocks, list) and 0 < len(blocks) <= 4:
            live["pending"].add(identifier)
            status = "unknown"
            try:
                async def one():
                    yield {"type": "user", "uuid": identifier, "message": {"role": "user", "content": blocks}}
                await live["client"].query(one())
                status = "accepted"
            except Exception:
                pass  # Possibly written; never resent.
        emit({"event": "update_ack", "id": identifier if valid else "", "status": status})

    async def receive():
        text, streamed, activity, failure, outcome, waiting, leaf = "", False, {}, None, None, False, None
        compaction = None
        async with ClaudeSDKClient(options=options) as client:
            async def messages():
                yield {"type": "user", "message": {"role": "user", "content": content}}
            await client.query(messages())
            live["client"] = client
            # Only now may PM write updates: the prompt is already in Claude Code's
            # input, and nothing but the first line was sent before asyncio read stdin.
            emit({"event": "steering_ready"})
            stream = client.receive_messages().__aiter__()
            while True:
                try:
                    # A late update's turn starts right after the answer; bound that wait.
                    message = await (asyncio.wait_for(stream.__anext__(), 60) if waiting else stream.__anext__())
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    live["finished"] = True
                    return {**outcome, "undelivered_updates": sorted(live["pending"])}
                if isinstance(message, AssistantMessage) or isinstance(message, StreamEvent) and getattr(message, "parent_tool_use_id", None) is None:
                    meter.observe(message)
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
                    leaf = getattr(message, "uuid", None) or leaf  # This answer's transcript entry.
                    failure = error_code(message, failure)
                    if getattr(message, "error", None) is not None: continue
                    public = "\n".join(block.text for block in message.content if isinstance(block, TextBlock))
                    calls = [block for block in message.content if isinstance(block, ToolUseBlock)]
                    if not streamed and public: text = public; emit({"event": "delta", "text": public})
                    if calls:
                        if public or text: emit({"event": "commentary", "id": str(uuid4()), "text": public or text})
                        text, streamed = "", False
                    for block in calls:
                        row = tool_row(block.id, block.name, getattr(block, "input", None))
                        activity[block.id] = (row, time.monotonic())
                        emit({"event": "activity", "item": row})
                elif isinstance(message, UserMessage):
                    if getattr(message, "uuid", None) in live["pending"]:
                        live["pending"].discard(message.uuid); waiting = False
                        emit({"event": "update_delivered", "id": message.uuid})
                    results = [block for block in (message.content if isinstance(message.content, list) else [])
                               if isinstance(block, ToolResultBlock) and block.tool_use_id in activity]
                    # The structured result belongs to the message's only tool result.
                    structured = getattr(message, "tool_use_result", None) if len(results) == 1 else None
                    for block in results:
                        row, started = activity.pop(block.tool_use_id)
                        emit({"event": "activity", "item": tool_finished(row, getattr(block, "content", None), block.is_error,
                                                                        (time.monotonic() - started) * 1000, structured)})
                elif isinstance(message, ResultMessage):
                    outcome = {"event": "result", "success": not message.is_error and message.subtype == "success"
                               and getattr(message, "terminal_reason", None) not in {"aborted_streaming", "aborted_tools"},
                               "text": message.result or text, "session_id": getattr(message, "session_id", None),
                               "error_code": error_code(message, failure), "usage": meter.summary(), "leaf": leaf}
                    if live["pending"] and outcome["success"]:
                        # This answer stays visible as progress; the update's turn answers last.
                        if outcome["text"]: emit({"event": "commentary", "id": str(uuid4()), "text": outcome["text"]})
                        text, streamed, waiting = "", False, True
                        continue
                    live["finished"] = True
                    if live["pending"]: outcome["undelivered_updates"] = sorted(live["pending"])
                    return outcome
                elif isinstance(message, SystemMessage):
                    # Claude Code compacts a long session by itself, and a summary can take a
                    # minute or two. Its status repeats while it works; one row covers it.
                    data = message.data if isinstance(message.data, dict) else {}
                    if message.subtype == "status" and data.get("status") == "compacting" and compaction is None:
                        compaction = str(uuid4())
                        emit({"event": "compaction", "id": compaction, "status": "inProgress"})
                    elif message.subtype == "compact_boundary":
                        metadata = data.get("compact_metadata") if isinstance(data.get("compact_metadata"), dict) else {}
                        emit({"event": "compaction", "id": compaction or str(uuid4()), "status": "completed",
                              **{key: metadata[key] for key in ("pre_tokens", "post_tokens", "duration_ms")
                                 if type(metadata.get(key)) is int and 0 <= metadata[key] < 10**10}})
                        compaction = None
        live["finished"] = True
        return None

    reading = asyncio.create_task(replies.read(reader, on_update=steer))
    receiving = asyncio.create_task(receive())
    try:
        done, _ = await asyncio.wait({reading, receiving}, return_when=asyncio.FIRST_COMPLETED)
        if reading in done: raise WorkspaceReplyError("Workspace connection closed")
        result = await receiving
        if result is not None: emit(result)
    finally:
        reading.cancel(); receiving.cancel()
        await asyncio.gather(reading, receiving, return_exceptions=True)
        pipe.close()
        replies.close()


def main():
    try:
        raw = sys.stdin.buffer.readline(40_000_001)
        if len(raw) > 40_000_000: raise ValueError("Oversized request")
        asyncio.run(run(json.loads(raw)))
    except Exception as error:
        emit({"event": "error", "error_code": "workspace_connection" if isinstance(error, WorkspaceReplyError) else "unknown"})


if __name__ == "__main__":
    main()
