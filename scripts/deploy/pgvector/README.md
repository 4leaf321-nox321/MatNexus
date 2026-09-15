# pgvector — 배포 패키지에 동봉하는 빌드 산출물

폐쇄망 서버는 zip 하나만 받는다. 전에는 이 폴더가 `build/`(gitignore)에만 있어서 서버
이전 때 **사람이 따로 날라야** 했다(2026-09-15 이전 절차의 유일한 손 반입물). DLL 은
PostgreSQL **메이저 판**과 Windows x64 에만 묶이지 기계에는 안 묶이므로, 판별 폴더로
저장소에 두고 zip 에 담는다. `install_pgvector.ps1` 은 `-FromDir` 를 안 주면 옆의
`pgvector\pg<판>` 을 쓴다.

| 폴더 | pgvector | PostgreSQL | 빌드 | 파일 |
| --- | --- | --- | --- | --- |
| `pg17/` | v0.8.0 | 17 (x64) | 2026-09-08, `build_pgvector.ps1` (VS Build Tools + PG17 헤더) | vector.dll · vector.control · vector--*.sql 35개 · build-info.json |

`pg17/vector.dll` SHA-256: `43b6045bd554378306706f45de4a5a3981f2131056fd3da1fad8604e1f8a02f7`

다른 판(예: 18)이 필요하면 개발 PC 에서 `build_pgvector.ps1 -PgRoot 'C:\Program Files\PostgreSQL\18'`
로 뽑아 `pg18/` 로 넣고 위 표에 적는다. 판이 다른 서버에 넣으면 `install_pgvector.ps1` 이
`build-info.json` 의 `postgres_major` 를 보고 멈춘다.
