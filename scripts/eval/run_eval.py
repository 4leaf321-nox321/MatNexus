"""AI 가 MatNexus 를 얼마나 잘 찾나 — **물음 세트를 실제 AI 세션으로 돌리고 도구 자취를
채점한다.**

온톨로지를 고치고 나아졌는지 확인하는 방법이 전에는 「AI 세션을 띄워 transcript 를 사람이
읽는 것」 뿐이었다(한 번에 10분). 같은 그래프에서 37번과 16번이 갈렸던 판단이 아무 데도
안 남았다([계획] 온톨로지 §8-③). 여기서 그것을 숫자로 남긴다.

## 채점 — 답 글자를 맞춰 보지 않는다

표현이 조금만 달라도 틀렸다고 나온다. 대신 **도구 자취**를 본다 — 객관적이고, 온톨로지를
고쳤을 때 정확히 그것이 움직인다:

    calls          도구를 몇 번 불렀나 (상한 max_calls 를 넘으면 헤맨 것)
    map_first      첫 두 호출 안에 지도(get_ontology·get_guide)를 봤나
    empty_calls    빈손으로 돌아온 호출 수 (hits/items 가 비었거나 total 0)
    tools_any      기대한 도구 중 하나는 불렀나
    tools_forbidden 부르면 안 되는 도구(쓰기)를 안 불렀나
    must_mention   답에 반드시 있어야 할 것(묶음마다 하나라도)이 다 있나

한계를 알고 쓴다: 부를 때마다 실제 AI 세션 값이 든다 — **CI 에 넣지 않는다.** 같은 물음도
12번이 되고 20번이 되므로 합격선이 아니라 **추세**로 본다. 결과는 `scripts/eval/results/`
에 남고 직전 실행과 나란히 비교된다.

## 어떻게 돌리나

    개발 백엔드(8011)가 떠 있어야 한다. 이 스크립트가 MCP 서버를 자식으로 띄웠다 내린다.

    cd scripts\\eval
    $env:MATNEXUS_PAT = 'mnx_pat_...'          # 화면 → 내 계정 → 토큰 (끝나고 폐기)
    ..\\..\\backend\\.venv\\Scripts\\python.exe run_eval.py             # 전부
    ..\\..\\backend\\.venv\\Scripts\\python.exe run_eval.py --only deck  # 한 갈래만
    ..\\..\\backend\\.venv\\Scripts\\python.exe run_eval.py --ids deck-01,search-03

`claude`(Claude Code CLI)가 PATH 에 있어야 한다. 물음은 `questions.json`, 개발 DB 의 재료
이름을 쓴다 — 자료가 바뀌면 물음도 고친다.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
MCP_DIR = REPO / "mcp_server"
RESULTS = HERE / "results"
QUESTIONS = HERE / "questions.json"

API_BASE = os.environ.get("MATNEXUS_API_BASE", "http://127.0.0.1:8011/api")
MCP_PORT = int(os.environ.get("MATNEXUS_EVAL_MCP_PORT", "8019"))
#: 물음 하나에 허용하는 시간. 덱을 뽑고 되읽는 물음이 2분을 넘기기도 한다.
QUESTION_TIMEOUT = int(os.environ.get("MATNEXUS_EVAL_TIMEOUT", "300"))
MAX_TURNS = int(os.environ.get("MATNEXUS_EVAL_MAX_TURNS", "14"))

MAP_TOOLS = {"mcp__matnexus__get_ontology", "mcp__matnexus__get_guide"}
#: 빈손 판정 — 결과 JSON 에 이런 모양이 있으면 그 호출은 아무것도 못 찾은 것이다.
EMPTY_MARKERS = ('"hits": []', '"items": []', '"total": 0', '"candidates": []', '"edges": []')

SYSTEM = (
    "너는 MatNexus(재료 물성 플랫폼)의 MCP 도구만으로 답한다. 파일·셸은 쓰지 않는다. "
    "먼저 get_ontology 나 get_guide 로 지도를 보고 길을 정한다. 모르면 지어내지 말고 없다고 "
    "말한다. 단위·등급·출처를 함께 말한다. 답은 한국어로, 짧게."
)


@dataclass
class Trace:
    id: str
    category: str
    prompt: str
    calls: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    error: str | None = None
    seconds: float = 0.0
    cost_usd: float | None = None

    # 채점
    map_first: bool = False
    empty_calls: int = 0
    over_budget: bool = False
    tools_any_ok: bool | None = None
    forbidden_hit: list[str] = field(default_factory=list)
    missing_mentions: list[list[str]] = field(default_factory=list)
    passed: bool = False


def _wait_port(port: int, server: subprocess.Popen[Any]) -> None:
    for _ in range(80):
        with socket.socket() as sock:
            sock.settimeout(0.3)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        if server.poll() is not None:
            raise SystemExit("MCP 서버가 떴다가 죽었다 — results/mcp-server.log 를 보라")
        time.sleep(0.5)
    raise SystemExit("MCP 서버가 안 떴다")


def start_mcp(token: str) -> tuple[subprocess.Popen[Any], Path]:
    """probe.py 와 같은 방식 — 자식으로 띄우고, 출력은 파일로(PIPE 를 안 읽으면 서버가
    멈춘다)."""
    python = MCP_DIR / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        raise SystemExit(
            f"MCP 가상환경이 없다: {python} — mcp_server\\run_mcp.ps1 을 한 번 돌려라"
        )
    env = dict(os.environ)
    env["MATNEXUS_API_BASE"] = API_BASE
    env["MATNEXUS_MCP_PORT"] = str(MCP_PORT)
    env["MATNEXUS_MCP_HOST"] = "127.0.0.1"
    env["PYTHONIOENCODING"] = "utf-8"
    RESULTS.mkdir(exist_ok=True)
    log = (RESULTS / "mcp-server.log").open("w", encoding="utf-8")
    server = subprocess.Popen(
        [str(python), "server.py"],
        cwd=str(MCP_DIR),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    _wait_port(MCP_PORT, server)
    config = RESULTS / "mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "matnexus": {
                        "type": "http",
                        "url": f"http://127.0.0.1:{MCP_PORT}/mcp",
                        "headers": {"Authorization": f"Bearer {token}"},
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return server, config


def ask(question: dict[str, Any], config: Path, model: str | None) -> Trace:
    trace = Trace(id=question["id"], category=question["category"], prompt=question["prompt"])
    claude = shutil.which("claude") or shutil.which("claude.cmd")
    if claude is None:
        raise SystemExit("claude CLI 가 PATH 에 없다")
    cmd = [
        claude,
        "-p",
        question["prompt"],
        "--output-format",
        "stream-json",
        "--verbose",
        "--mcp-config",
        str(config),
        "--strict-mcp-config",
        "--allowed-tools",
        "mcp__matnexus",
        "--max-turns",
        str(MAX_TURNS),
        "--append-system-prompt",
        SYSTEM,
    ]
    if model:
        cmd += ["--model", model]
    started = time.time()
    try:
        done = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=QUESTION_TIMEOUT,
            cwd=str(HERE),
        )
    except subprocess.TimeoutExpired:
        trace.error = f"시간 초과({QUESTION_TIMEOUT}s)"
        trace.seconds = time.time() - started
        return trace
    trace.seconds = time.time() - started
    if done.returncode != 0 and not done.stdout.strip():
        trace.error = (done.stderr or "").strip()[-400:] or f"exit {done.returncode}"
        return trace

    pending: dict[str, dict[str, Any]] = {}
    for line in done.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        # **이벤트 모양을 믿지 않는다**(2026-09-18). `message` 가 문자열로 오는 줄이
        # 있어서 `.get` 에서 터졌고, **16번째 문항에서 25분짜리 실행이 통째로
        # 날아갔다.** 스트림 형식은 우리 것이 아니라 CLI 의 것이라 늘 바뀔 수 있다 —
        # 모르는 줄은 세지 않고 넘어가는 편이 맞다.
        message = event.get("message")
        message = message if isinstance(message, dict) else {}
        content = message.get("content")
        content = content if isinstance(content, list) else []
        if kind == "assistant":
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    call = {
                        "name": block.get("name"),
                        "input": block.get("input"),
                        "empty": False,
                    }
                    pending[block.get("id", "")] = call
                    trace.calls.append(call)
        elif kind == "user":
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    found = pending.get(block.get("tool_use_id", ""))
                    if found is None:
                        continue
                    call = found
                    body = block.get("content")
                    text = (
                        body
                        if isinstance(body, str)
                        else "".join(
                            part.get("text", "") for part in body if isinstance(part, dict)
                        )
                        if isinstance(body, list)
                        else ""
                    )
                    call["empty"] = any(marker in text for marker in EMPTY_MARKERS)
                    call["is_error"] = bool(block.get("is_error"))
        elif kind == "result":
            trace.answer = str(event.get("result") or "")
            trace.cost_usd = event.get("total_cost_usd")
            if event.get("is_error"):
                trace.error = trace.answer[-400:]
    return trace


def score(trace: Trace, question: dict[str, Any]) -> None:
    # **MCP 도구만 센다.** Claude Code 가 도구 목록을 읽는 `ToolSearch` 같은 내부 호출은
    # 우리 온톨로지와 무관하다 — 세면 지도를 보기도 전에 「헤맸다」 가 된다.
    trace.calls = [one for one in trace.calls if str(one["name"]).startswith("mcp__")]
    names = [str(one["name"]) for one in trace.calls]
    trace.map_first = any(name in MAP_TOOLS for name in names[:2])
    trace.empty_calls = sum(1 for one in trace.calls if one.get("empty"))
    trace.over_budget = len(names) > int(question.get("max_calls", 99))
    wanted = question.get("tools_any")
    trace.tools_any_ok = None if not wanted else any(name in wanted for name in names)
    trace.forbidden_hit = [
        name
        for name in names
        if name in set(question.get("tools_forbidden", []))
        # dry_run 미리보기는 쓰기가 아니다.
        and not any(
            one["name"] == name and (one.get("input") or {}).get("dry_run", True)
            for one in trace.calls
        )
    ]
    answer = trace.answer
    trace.missing_mentions = [
        group
        for group in question.get("must_mention", [])
        if not any(word in answer for word in group)
    ]
    trace.passed = (
        trace.error is None
        and not trace.over_budget
        and trace.tools_any_ok is not False
        and not trace.forbidden_hit
        and not trace.missing_mentions
    )


def summarize(traces: list[Trace]) -> dict[str, Any]:
    by_category: dict[str, dict[str, Any]] = {}
    for one in traces:
        slot = by_category.setdefault(
            one.category, {"n": 0, "passed": 0, "calls": 0, "empty": 0, "map_first": 0}
        )
        slot["n"] += 1
        slot["passed"] += int(one.passed)
        slot["calls"] += len(one.calls)
        slot["empty"] += one.empty_calls
        slot["map_first"] += int(one.map_first)
    total_calls = sum(len(one.calls) for one in traces)
    return {
        "n": len(traces),
        "passed": sum(int(one.passed) for one in traces),
        "calls": total_calls,
        "calls_per_question": round(total_calls / max(1, len(traces)), 2),
        "empty_calls": sum(one.empty_calls for one in traces),
        "map_first": sum(int(one.map_first) for one in traces),
        "errors": sum(1 for one in traces if one.error),
        "seconds": round(sum(one.seconds for one in traces), 1),
        "cost_usd": round(sum(one.cost_usd or 0.0 for one in traces), 4),
        "by_category": by_category,
    }


def previous_summary() -> dict[str, Any] | None:
    runs = sorted(RESULTS.glob("run-*.json"))
    if not runs:
        return None
    loaded = json.loads(runs[-1].read_text(encoding="utf-8"))
    summary = loaded.get("summary")
    return dict(summary) if isinstance(summary, dict) else None


def write_report(
    traces: list[Trace], summary: dict[str, Any], before: dict[str, Any] | None
) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=str(REPO)
    ).stdout.strip()
    payload = {
        "at": stamp,
        "git": head,
        "summary": summary,
        "traces": [asdict(one) for one in traces],
    }
    out = RESULTS / f"run-{stamp}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# 기준선 {stamp} · {head}", ""]

    def row(label: str, key: str) -> str:
        now = summary[key]
        was = before.get(key) if before else None
        delta = "" if was is None else f" (지난번 {was})"
        return f"| {label} | {now}{delta} |"

    lines += ["| 항목 | 값 |", "| --- | --- |"]
    lines += [
        row("물음", "n"),
        row("통과", "passed"),
        row("도구 호출(합)", "calls"),
        row("물음당 호출", "calls_per_question"),
        row("빈손 호출", "empty_calls"),
        row("지도부터 본 물음", "map_first"),
        row("오류", "errors"),
        row("걸린 시간(s)", "seconds"),
        row("비용(USD)", "cost_usd"),
        "",
        "| 갈래 | 통과/전체 | 호출 | 빈손 | 지도부터 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, slot in summary["by_category"].items():
        lines.append(
            f"| {name} | {slot['passed']}/{slot['n']} | {slot['calls']} | {slot['empty']} | "
            f"{slot['map_first']} |"
        )
    lines += ["", "| 물음 | 결과 | 호출 | 자취 | 빠진 말 |", "| --- | --- | --- | --- | --- |"]
    for one in traces:
        verdict = "오류" if one.error else ("통과" if one.passed else "미달")
        marks = []
        if one.over_budget:
            marks.append("호출 초과")
        if one.tools_any_ok is False:
            marks.append("기대 도구 안 씀")
        if one.forbidden_hit:
            marks.append("금지 도구: " + ",".join(one.forbidden_hit))
        names = " → ".join(str(c["name"]).removeprefix("mcp__matnexus__") for c in one.calls)
        missing = " / ".join("·".join(group) for group in one.missing_mentions)
        lines.append(
            f"| {one.id} | {verdict}{(' — ' + ', '.join(marks)) if marks else ''} | "
            f"{len(one.calls)} | {names} | {missing} |"
        )
    (RESULTS / f"run-{stamp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RESULTS / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--only", help="갈래 이름(카드·값 찾기·…) 또는 id 접두어(deck·search·…)"
    )
    parser.add_argument("--ids", help="쉼표로 나눈 물음 id")
    parser.add_argument("--model", help="claude --model 에 넘길 값")
    args = parser.parse_args()

    token = os.environ.get("MATNEXUS_PAT")
    if not token:
        print("MATNEXUS_PAT 이 없습니다 — 화면 → 내 계정 → 토큰에서 발급하세요(끝나고 폐기).")
        return 2
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    if args.ids:
        wanted = {one.strip() for one in args.ids.split(",")}
        questions = [one for one in questions if one["id"] in wanted]
    if args.only:
        questions = [
            one
            for one in questions
            if one["category"] == args.only or one["id"].startswith(args.only)
        ]
    if not questions:
        print("고른 물음이 없습니다.")
        return 2

    before = previous_summary()
    server, config = start_mcp(token)
    traces: list[Trace] = []
    try:
        for index, question in enumerate(questions, start=1):
            print(f"[{index}/{len(questions)}] {question['id']} …", end=" ", flush=True)
            # **한 문항이 터져도 실행을 안 버린다.** 30문항이 25분이라, 16번에서
            # 죽으면 앞의 15개도 함께 날아간다(실측 2026-09-18). 못 읽은 문항은
            # 오류로 적고 다음으로 간다 — 표에 그대로 남아 눈에 띈다.
            try:
                trace = ask(question, config, args.model)
            except Exception as exc:  # 무엇이 터지든 다음 문항은 돈다
                trace = Trace(
                    id=question["id"],
                    category=question["category"],
                    prompt=str(question.get("prompt", "")),
                )
                trace.error = f"[{type(exc).__name__}] {exc}"[:400]
            score(trace, question)
            traces.append(trace)
            state = "오류" if trace.error else ("통과" if trace.passed else "미달")
            print(f"{state} · 호출 {len(trace.calls)} · {trace.seconds:.0f}s")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    summary = summarize(traces)
    out = write_report(traces, summary, before)
    print()
    print(
        f"=== 물음 {summary['n']} · 통과 {summary['passed']} · 호출 {summary['calls']}"
        f"(물음당 {summary['calls_per_question']}) · 빈손 {summary['empty_calls']} · "
        f"지도부터 {summary['map_first']} · 오류 {summary['errors']} ==="
    )
    if before:
        print(
            f"    지난번: 통과 {before['passed']}/{before['n']} · 호출 {before['calls']} · "
            f"빈손 {before['empty_calls']} · 지도부터 {before['map_first']}"
        )
    print(f"    {out}  ·  {RESULTS / 'latest.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
