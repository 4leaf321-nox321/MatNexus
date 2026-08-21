/**
 * 오른쪽 영역 — **껍데기가 자리를 내주고, 화면이 채운다.**
 *
 * 왼쪽 사이드바와 같은 층이다. 본문(`main`)은 `mx-auto max-w-7xl` 로 가운데
 * 정렬되는데, 그 안에 사이드바를 넣으면 **본문과 함께 가운데로 딸려 들어가고**
 * 화면 오른쪽 끝에는 여백만 남는다. 그래서 껍데기 층에 둔다.
 *
 * ## 내용은 화면이, 자리와 여닫기는 껍데기가
 *
 * 처리 화면의 변수 목록은 **지금 켠 단계**에 따라 달라지고, 그 상태는
 * `ProcessingPanel` 안에 산다. 껍데기로 끌어올리면 껍데기가 처리 도메인을 알게
 * 되고, 그때부터 그 모듈을 떼어 낼 수 없다 — 그래서 내용은 포털로 화면이 넣는다.
 *
 * 반대로 **여닫는 상태는 껍데기가 갖는다.** 처음에는 접힌 사이드바를 화면
 * 오른쪽 끝에 흐린 세로 띠로 뒀는데 아무도 못 봤다. 여는 단추는 **왼쪽 사이드바
 * 토글 옆**, 상단 바에 있어야 한다 — 껍데기를 여닫는 단추는 다 거기 있다.
 * 그러려면 `Header` 가 그 상태를 볼 수 있어야 한다.
 *
 * 화면이 바뀌면(탭을 옮기면) 등록이 걷히고 상단 바의 단추도 같이 사라진다 —
 * 없는 패널을 여는 단추가 남아 있으면 눌러도 아무 일이 안 일어난다.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import type { ReactNode } from 'react'

const HOST_ID = 'app-right-panel'

interface RightPanelState {
  /** 지금 화면이 오른쪽 영역을 쓰는가. 쓰면 그 이름(상단 바 단추에 뜬다). */
  label: string | null
  open: boolean
  toggle: () => void
  register: (label: string | null) => void
}

const Ctx = createContext<RightPanelState | null>(null)

export function RightPanelProvider({ children }: { children: ReactNode }) {
  const [label, setLabel] = useState<string | null>(null)
  // **기본은 닫힘.** 늘 펴 두면 본문이 그만큼 좁아진다.
  const [open, setOpen] = useState(false)

  const register = useCallback((next: string | null) => {
    setLabel(next)
    // 패널이 사라지면 열려 있던 상태도 거둔다 — 다음 화면에서 갑자기 빈 칸이
    // 열려 있으면 그것이 무엇인지 알 방법이 없다.
    if (next === null) setOpen(false)
  }, [])

  const value = useMemo(
    () => ({ label, open, toggle: () => setOpen((value) => !value), register }),
    [label, open, register]
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

/** 상단 바가 쓴다. 패널이 없으면 `label` 이 `null` 이라 단추를 감춘다. */
export function useRightPanel(): RightPanelState {
  const value = useContext(Ctx)
  if (!value) throw new Error('RightPanelProvider 안에서만 쓸 수 있습니다.')
  return value
}

/** 껍데기가 그리는 빈 자리. 아무 화면도 안 쓰면 폭이 0 이다. */
export function RightPanelHost() {
  return <div id={HOST_ID} className="shrink-0" />
}

/**
 * 그 자리에 내용을 넣는다. 폭·테두리·스크롤은 **넣는 쪽이 정한다** — 화면마다
 * 필요한 폭이 다르고, 껍데기가 그것까지 알 이유가 없다.
 *
 * `label` 은 상단 바 단추에 뜨는 이름이다.
 */
export function RightPanel({ label, children }: { label: string; children: ReactNode }) {
  const { open, register } = useRightPanel()
  // 껍데기가 먼저 그려져 있어야 찾을 수 있다. 첫 렌더에는 없으므로 효과에서 잡는다.
  const [host, setHost] = useState<HTMLElement | null>(null)
  useEffect(() => setHost(document.getElementById(HOST_ID)), [])

  useEffect(() => {
    register(label)
    return () => register(null)
  }, [label, register])

  return host && open ? createPortal(children, host) : null
}
