# bin — 배포 패키지에 동봉하는 바이너리

폐쇄망 서버는 zip 하나만 받는다. 여기 있는 것은 그 zip 에 그대로 들어간다
(`scripts/ci/package_deploy.ps1`).

| 파일 | 무엇 | 버전 | 출처 | 라이선스 |
| --- | --- | --- | --- | --- |
| `nssm.exe` | Windows 서비스 래퍼 — `service.ps1` 이 python.exe 를 서비스로 등록할 때 쓴다 | 2.24 (win64) | https://nssm.cc/release/nssm-2.24.zip → `win64/nssm.exe` | 퍼블릭 도메인 |

`nssm.exe` SHA-256: `f689ee9af94b00e9e3f0bb072b34caaf207f32dcb4f5782fc9ca351df9a06c97`

바꿀 때는 위 표의 버전·해시를 함께 고친다. 콘솔 없이(파이프로) `nssm.exe` 를 부르면
출력이 안 나오고 멈춘 것처럼 보인다 — NSSM 이 `WriteConsole` 로만 쓰기 때문이다.
PowerShell 창에서 직접 부르면 정상이다.
