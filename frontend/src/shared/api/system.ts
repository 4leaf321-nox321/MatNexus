/**
 * 이 설치가 어느 버전인가.
 *
 * **서버가 정본이다.** 화면 번들에 버전을 박아 넣으면 그것은 *빌드된* 버전이지
 * *지금 도는* 서버가 아니다 — 배포가 반쯤 끝났거나 서비스가 안 내려갔다 올라온
 * 상태에서 그 둘이 갈리고, 그때 화면이 거짓말을 한다. 문제가 났을 때 "지금 서버
 * 버전이 뭐냐" 를 못 답하면 원인 찾기가 크게 어려워지는데, 답이 틀린 것은 못
 * 답하는 것보다 나쁘다.
 *
 * 값은 배포 패키지가 들고 온다(`BUILD_INFO.txt`). 개발 중에는 저장소의
 * `frontend/package.json` 이 정본이다 — auto-tag 워크플로도 그것을 본다.
 *
 * `shared` 에 있는 이유: 사이드바가 쓴다. 도메인 모듈이 아니고, 이 파일은
 * 아무 도메인도 import 하지 않는다.
 */

import { api } from '@/shared/api/client'

export interface Health {
  status: string
  /** `v1.73.0` 처럼. 어디서도 못 찾으면 `unknown` — 개발 경로에서 돈다는 뜻이다. */
  version: string
}

/** 어디서도 못 찾았을 때 서버가 주는 값. **화면은 이것을 안 보여 준다.** */
export const UNKNOWN_VERSION = 'unknown'

export const systemApi = {
  health: () => api.get<Health>('/health'),
}
