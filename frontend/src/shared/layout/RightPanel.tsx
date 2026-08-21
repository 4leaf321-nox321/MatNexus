/**
 * 오른쪽 영역 — **껍데기가 자리를 내주고, 화면이 채운다.**
 *
 * 왼쪽 사이드바와 같은 층이다. 본문(`main`)은 `mx-auto max-w-7xl` 로 가운데
 * 정렬되는데, 그 안에 사이드바를 넣으면 **본문과 함께 가운데로 딸려 들어가고**
 * 화면 오른쪽 끝에는 여백만 남는다. 그래서 껍데기 층에 둔다.
 *
 * ## 왜 포털인가
 *
 * 내용은 화면이 안다. 처리 화면의 변수 목록은 **지금 켠 단계**에 따라 달라지고,
 * 그 상태는 `ProcessingPanel` 안에 산다. 껍데기로 끌어올리면 껍데기가 처리
 * 도메인을 알게 되고, 그때부터 그 모듈을 떼어 낼 수 없다.
 *
 * 그래서 **자리만 껍데기가 내준다.** 빈 자리는 폭이 0 이라(`shrink-0` 플렉스
 * 항목) 아무 화면도 안 쓰면 없는 것과 같다. 폭은 넣는 쪽이 정한다.
 *
 * 화면이 바뀌면(탭을 옮기면) 그 컴포넌트가 사라지면서 포털도 같이 걷힌다 —
 * 남아 있는 사이드바를 따로 치울 일이 없다.
 */

import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import type { ReactNode } from 'react'

const HOST_ID = 'app-right-panel'

/** 껍데기가 그리는 빈 자리. `AppShell` 이 왼쪽 사이드바와 나란히 둔다. */
export function RightPanelHost() {
  return <div id={HOST_ID} className="shrink-0" />
}

/**
 * 그 자리에 내용을 넣는다. 폭·테두리·스크롤은 **넣는 쪽이 정한다** — 화면마다
 * 필요한 폭이 다르고, 껍데기가 그것까지 알 이유가 없다.
 */
export function RightPanel({ children }: { children: ReactNode }) {
  // 껍데기가 먼저 그려져 있어야 찾을 수 있다. 첫 렌더에는 없으므로 효과에서 잡는다.
  const [host, setHost] = useState<HTMLElement | null>(null)
  useEffect(() => setHost(document.getElementById(HOST_ID)), [])
  return host ? createPortal(children, host) : null
}
