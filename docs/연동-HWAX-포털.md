# HWAX 포털 연동 — MatNexus MCP 도구를 포털 게이트웨이로

> 대상: HWAX 포털 운영자 · MatNexus 운영 · 2026-10-03
> 요약: MatNexus 는 포털의 **사람별 위임(ste 방식)** 계약을 갖췄다 — `POST /api/auth/sso`(+ `/verify` ·
> `/revoke`). TestScope 와 같은 모양이고 **SSO 는 하지 않는다**(ADR 0056). 포털 · 게이트웨이에는 아직
> MatNexus 가 없다 — 아래 2절을 포털 쪽에 더해 주시면 된다.

## 1. MatNexus 가 준비한 것

### 위임 창구 — 포털 요청서(`docs/sso-delegation/ra-request.md`) 계약 그대로

| | 내용 |
|---|---|
| `POST /api/auth/sso` | 헤더 `X-Heax-Gateway-Secret`(MatNexus 전용 공유 비밀) · `X-Heax-User-Email`(필수) · `X-Heax-User-Name`(선택, 퍼센트 인코딩) · `X-Heax-Client`(`gateway`) |
| 응답 200 | `{"success": true, "data": {"access_token": "mnx_pat_…", "token_type": "bearer", "expires_in": 172800, "needs_workspace": false}}` |
| 오류 | 비밀이 비면 **404**(꺼짐) · 비밀 불일치 401 · 이메일 형식 아님 401 · 이메일 없음 400 · 없는 계정 · 승인 대기 · 정지 **403** · 허용 밖 IP 403 |
| `POST /api/auth/sso/verify` | 비밀만 확인 — 204 / 401 |
| `POST /api/auth/sso/revoke` | 그 사람 · 그 client 의 위임 토큰 폐기 — 200 `{"ok": true, "revoked": n}` |

- **계정을 만들지 않는다**(JIT 없음). MatNexus 에서 가입 승인을 받은 사람만 된다 — 없으면 403 과
  「MatNexus 에서 가입 신청을 하고 승인을 받은 뒤」.
- **토큰은 읽기 전용 · 2일**이다. 같은 client 로 다시 받으면 직전 토큰은 폐기된다(게이트웨이 12시간
  캐시와 맞는다). 포털 경유 쓰기는 미리보기(`dry_run`)까지만 된다.
- 사람 찾기는 이메일(대소문자 무시). 함께 오는 소속 헤더(`X-Heax-User-Affiliation` · `X-Heax-Aff-Proof`)는
  읽지 않는다.

### MCP 서버

- 주소 `http://<MatNexus 서버>:8012/mcp`(streamable HTTP). 받은 `Authorization: Bearer <토큰>` 을 백엔드로
  나르기만 한다 — 만능 토큰이 없다.
- 도구 96개. 이름이 다른 앱과 겹치면 게이트웨이가 `matnexus_` 를 붙이는 것을 전제로 스킬
  (`mcp_server/skill/matnexus/SKILL.md`)이 두 이름을 다 허용한다.

## 2. 포털 · 게이트웨이에 필요한 것 — MatNexus 를 서비스로 더하기

TestScope 를 더할 때와 같은 자리들이다(포털 `docs/sso-delegation/server-setup.md` B · B-2). MatNexus 는
**ste 방식만** 쓰면 된다 — 토큰 등록(「외부 연결」 카드)은 없어도 된다.

| # | 어디 | 무엇 |
|---|---|---|
| P1 | 포털 권한표 `backend/config/access.yaml` | `matnexus` 시스템 · 라벨 「MatNexus」 — 쓸 사람에게 권한 |
| P2 | 게이트웨이 백엔드(HWAXMcpGateway `provision.env`) | `MATNEXUS_MCP_URL=http://<MatNexus 서버>:8012/mcp` |
| P3 | 게이트웨이 사람별 위임 | `per_user_sso.matnexus = {sso_url: http://<MatNexus 서버>:8010/api/auth/sso, secret: <MATNEXUS_SSO_SECRET>, client: gateway}` — 프로비저너가 `MATNEXUS_SSO_SECRET` 을 읽게(TestScope 의 `TESTSCOPE_SSO_SECRET` 과 같은 처리, 비우면 위임을 지우는 D-17 규칙까지) |
| P4 | (선택) 앱 목록 타일 `systems.local.yaml` | `matnexus: {url: http://<MatNexus 서버>:8010/}` — 그쪽 주소로 새 탭 |

⚠ **비밀은 MatNexus 쪽이 켠 뒤에 넣는다.** 포털 쪽에 `MATNEXUS_SSO_SECRET` 이 생기는 순간 게이트웨이가
MatNexus 를 위임으로만 부른다 — MatNexus 쪽 창구가 아직 꺼져 있으면 MatNexus 도구 전부가 거부된다.

## 3. 켜는 순서

| # | 어디 | 무엇 | 누가 |
|---|---|---|---|
| 1 | 포털 운영자 | `openssl rand -hex 32` 로 비밀 하나 — **MatNexus 전용**(다른 서비스와 묶지 않는다). 메신저 평문 말고 안전한 경로로 MatNexus 운영에 전달 | 포털 운영자 |
| 2 | MatNexus `backend\.env` | `HEAX_SSO_SECRET=<비밀>` · `HEAX_SSO_ALLOWED_IPS=<게이트웨이 박스 IP>` → 재기동 | MatNexus 운영 |
| 3 | MatNexus `backend\.env` | MCP 를 게이트웨이에 연다 — `MCP_HOST=0.0.0.0` · `MCP_ALLOWED_HOSTS=<게이트웨이가 부르는 주소:8012>`(포트까지 글자 그대로) · 방화벽 TCP 8012 인바운드 → MCP 서비스 재기동 | MatNexus 운영 |
| 4 | MatNexus | 확인: `curl -X POST -H "X-Heax-Gateway-Secret: <비밀>" http://<MatNexus>:8010/api/auth/sso/verify` → **204**(틀리면 401, 안 켰으면 404) | MatNexus 운영 |
| 5 | 포털 · 게이트웨이 | 2절 P1~P3 + `MATNEXUS_SSO_SECRET=<같은 비밀>` → `./infra/scripts/update-all.sh` | 포털 운영자 |
| 6 | MatNexus `backend\.env` | (선택) `HWAX_PORTAL_URL=https://hwax.sec.samsung.net` · `MCP_PUBLIC_URL=http://<MatNexus>:8012/mcp` — 「내 계정 → 토큰」 의 안내가 포털 길과 정확한 주소를 보인다 | MatNexus 운영 |

확인: ① 포털 Claude Code 에서 MatNexus 도구(`get_guide` · `search_materials` 등)가 **등록 없이** 결과를
낸다. ② MatNexus 「내 계정 → 토큰」 에 「HWAX 포털 게이트웨이 (gateway)」 가 읽기 전용으로 선다 — 이틀마다
바뀌고 직전 것은 폐기로 남는다. ③ 변경 이력에 「HWAX 포털이 토큰을 받아 감」(누구 명의로 · 어느 IP 에서).
④ MatNexus 에 계정이 없는 포털 사용자는 「MatNexus 에서 가입 신청을 하고 승인을 받은 뒤」 로 거부된다.
⑤ 「관리 → 사용 현황」 의 MCP 호출에 포털 경유 호출이 그 사람 몫으로 잡힌다.

되돌리기: 포털 쪽 `MATNEXUS_SSO_SECRET` 을 비우고 update-all — 게이트웨이 위임이 지워진다. MatNexus 쪽
비밀은 그다음에 빼도 되고 둬도 된다(비면 창구가 404 로 닫힐 뿐이다). 사람이 끊고 싶으면 「내 계정 →
토큰」 에서 그 토큰을 폐기한다 — 게이트웨이의 다음 호출이 401 을 받고 한 번 다시 받아 간다. 영영 끊으려면
포털에서 MatNexus 권한을 뺀다.
