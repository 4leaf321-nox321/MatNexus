# 평가 세트 — AI 가 MatNexus 를 얼마나 잘 찾나

온톨로지·MCP 안내를 고치고 「나아졌나」 를 **숫자로** 보는 도구다(2026-09-16, [계획] 온톨로지
고도화 0단계). 물음 30개를 실제 Claude 세션(`claude -p`)이 MCP 로 답하게 하고, **답 글자가
아니라 도구 자취**를 채점한다 — 몇 번 불렀나 · 지도를 봤나 · 빈손 호출이 몇이나 · 기대한
도구를 썼나 · 쓰면 안 되는 도구를 안 썼나 · 답에 반드시 있어야 할 것이 있나.

## 돌리기

개발 백엔드(8011)가 떠 있어야 한다. MCP 서버는 이 스크립트가 자식으로 띄웠다 내린다.
`claude`(Claude Code CLI)가 PATH 에 있어야 한다.

```powershell
cd scripts\eval
$env:MATNEXUS_PAT = 'mnx_pat_...'      # 화면 → 내 계정 → 토큰. 끝나고 폐기한다.
..\..\backend\.venv\Scripts\python.exe run_eval.py               # 전부 (20~30분)
..\..\backend\.venv\Scripts\python.exe run_eval.py --only 카드    # 한 갈래
..\..\backend\.venv\Scripts\python.exe run_eval.py --ids deck-01,search-03
```

결과는 `results/run-<시각>.json`(자취 전부)과 `results/run-<시각>.md`(표), `results/latest.md`.
직전 실행과 나란히 비교해 준다. **CI 에 넣지 않는다** — 세션마다 값이 들고, 같은 물음도
12번이 되고 20번이 되므로 합격선이 아니라 **추세**로 본다.

## 물음 — `questions.json`

| 갈래 | 무엇을 보나 |
| --- | --- |
| 카드 | 「이 재료로 이 형식이 나오나」 → `deck_readiness` 를 먼저 보나 · MID·솔버를 넘기나 |
| 값 찾기 | 조건·등급·세계를 인자로 넘기나 · 단위 없는 물음에 짐작하지 않나 |
| 커버리지 | 「뭐가 있나」 에 `property_coverage` 한 번으로 답하나 |
| 관계 | 레시피·의뢰·시편으로 `related`/`find_path` 를 걷나 |
| 이름 해소 | 별칭·모르는 이름을 `resolve_property` 로 푸나 |
| 판단 | 단위계 함정 · 추정값을 실측처럼 옮기기 · 외삽 · 없는 재료 — **거절·경고를 말하나** |

물음은 **개발 DB 의 실제 이름**(SCATTER_DP600_1.0 · EXAMPLE-MIX_예제_- …)을 쓴다. 자료가
바뀌면 물음도 고친다. 판단 물음의 `tools_forbidden` 은 `dry_run` 이 아닌 쓰기 호출만 잡는다.

## 채점 필드

| 필드 | 뜻 |
| --- | --- |
| `calls` | MCP 도구 호출 수(`ToolSearch` 같은 CLI 내부 호출은 안 센다). `max_calls` 를 넘으면 헤맨 것 |
| `map_first` | 첫 두 호출 안에 `get_ontology`·`get_guide` 를 봤나 |
| `empty_calls` | 결과가 빈 호출(`hits: []`·`items: []`·`total: 0`·`candidates: []`·`edges: []`) |
| `tools_any_ok` | 기대한 도구 중 하나를 불렀나 |
| `forbidden_hit` | 쓰면 안 되는 도구를 불렀나 |
| `missing_mentions` | 답에 빠진 「반드시 있어야 할 것」 묶음 |
| `passed` | 오류 없음 · 호출 상한 안 · 기대 도구 씀 · 금지 도구 안 씀 · 빠진 말 없음 |

## 한계

- 실제 AI 세션이라 **돈이 들고 느리다**(물음당 20~90초). 전체는 릴리스 전 한 번.
- `must_mention` 은 느슨한 문자열 포함이다 — 통과가 「답이 맞다」 는 아니다. 미달·오류 줄의
  자취를 사람이 읽는 것이 이 도구의 진짜 출력이다.
- 개발 DB 상대로만 돈다(사내 정책상 개발 PC 에서 개발 DB 는 됨, 2026-09-16 확인).
