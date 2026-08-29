/**
 * 양옆 영역 — **껍데기가 자리를 내주고, 화면이 채운다.**
 *
 * 왼쪽 사이드바와 같은 층이다. 본문(`main`)은 `max-w-[1600px]` 로 가운데
 * 정렬되는데, 그 안에 사이드바를 넣으면 **본문과 함께 가운데로 딸려 들어가고**
 * 화면 끝에는 여백만 남는다. 그래서 껍데기 층에 둔다.
 *
 * ## 내용은 화면이, 자리와 여닫기는 껍데기가
 *
 * 처리 화면의 변수 목록은 **지금 켠 단계**에 따라 달라지고, 그 상태는
 * `ProcessingPanel` 안에 산다. 껍데기로 끌어올리면 껍데기가 처리 도메인을 알게
 * 되고, 그때부터 그 모듈을 떼어 낼 수 없다 — 그래서 내용은 포털로 화면이 넣는다.
 *
 * 반대로 **여닫는 상태는 껍데기가 갖는다.** 처음에는 접힌 사이드바를 화면
 * 끝에 흐린 세로 띠로 뒀는데 아무도 못 봤다. 여는 단추는 **왼쪽 사이드바
 * 토글 옆**, 상단 바에 있어야 한다 — 껍데기를 여닫는 단추는 다 거기 있다.
 * 그러려면 `Header` 가 그 상태를 볼 수 있어야 한다.
 *
 * 화면이 바뀌면(탭을 옮기면) 등록이 걷히고 상단 바의 단추도 같이 사라진다 —
 * 없는 패널을 여는 단추가 남아 있으면 눌러도 아무 일이 안 일어난다.
 *
 * ## 왜 공장인가
 *
 * 오른쪽만 있다가 왼쪽이 필요해졌다(재료 상세에서 다른 재료로 건너뛰기).
 * 기계는 똑같고 **다른 것은 자리와 기본 상태뿐**이다.
 *
 *     오른쪽   기본 닫힘   늘 펴 두면 본문이 그만큼 좁아진다
 *     왼쪽     기본 열림   목록을 보려고 여는 것인데 닫혀 있으면 뜻이 없다
 *
 * `side` 를 프롭으로 넘기지 않고 공장으로 만든 이유: 그러면 `RightPanel` 을 쓰는
 * 모든 자리가 `side="right"` 를 적어야 하고, 빠뜨리면 반대쪽에 뜬다.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import type { ReactNode } from 'react'

export interface SidePanelState {
  /** 지금 화면이 이 영역을 쓰는가. 쓰면 그 이름(상단 바 단추에 뜬다). */
  label: string | null
  open: boolean
  toggle: () => void
  register: (label: string | null) => void
}

function createSidePanel(hostId: string, defaultOpen: boolean) {
  const Ctx = createContext<SidePanelState | null>(null)

  function Provider({ children }: { children: ReactNode }) {
    const [label, setLabel] = useState<string | null>(null)
    const [open, setOpen] = useState(defaultOpen)

    const register = useCallback((next: string | null) => {
      setLabel(next)
      // **패널이 사라지면 기본값으로 되돌린다.** 다음 화면에서 갑자기 빈 칸이
      // 열려 있으면 그것이 무엇인지 알 방법이 없고(오른쪽), 반대로 왼쪽은 다음
      // 재료 상세에서 다시 열려 있어야 한다 — 들어갈 때마다 열게 하면 뜻이 없다.
      if (next === null) setOpen(defaultOpen)
    }, [])

    const value = useMemo(
      () => ({ label, open, toggle: () => setOpen((value) => !value), register }),
      [label, open, register]
    )
    return <Ctx.Provider value={value}>{children}</Ctx.Provider>
  }

  /** 상단 바가 쓴다. 패널이 없으면 `label` 이 `null` 이라 단추를 감춘다. */
  function use(): SidePanelState {
    const value = useContext(Ctx)
    if (!value) throw new Error(`${hostId} 제공자 안에서만 쓸 수 있습니다.`)
    return value
  }

  /** 껍데기가 그리는 빈 자리. 아무 화면도 안 쓰면 폭이 0 이다. */
  function Host() {
    return <div id={hostId} className="shrink-0" />
  }

  /**
   * 그 자리에 내용을 넣는다. 폭·테두리·스크롤은 **넣는 쪽이 정한다** — 화면마다
   * 필요한 폭이 다르고, 껍데기가 그것까지 알 이유가 없다.
   *
   * `label` 은 상단 바 단추에 뜨는 이름이다.
   */
  function Panel({
    label,
    rail,
    children,
  }: {
    label: string
    /** 접혔을 때 그 자리에 남는 것. **없으면 아무것도 안 남는다** — 그러면 다시
     *  펴는 길이 상단 바 단추뿐이고, 패널에서 멀어 아무도 못 찾는다. */
    rail?: ReactNode
    children: ReactNode
  }) {
    const { open, register } = use()
    // 껍데기가 먼저 그려져 있어야 찾을 수 있다. 첫 렌더에는 없으므로 효과에서 잡는다.
    const [host, setHost] = useState<HTMLElement | null>(null)
    useEffect(() => setHost(document.getElementById(hostId)), [])

    useEffect(() => {
      register(label)
      return () => register(null)
    }, [label, register])

    const shown = open ? children : rail
    return host && shown ? createPortal(shown, host) : null
  }

  return { Provider, Host, Panel, use }
}

const right = createSidePanel('app-right-panel', false)
export const RightPanelProvider = right.Provider
export const RightPanelHost = right.Host
export const RightPanel = right.Panel
export const useRightPanel = right.use

const left = createSidePanel('app-left-panel', true)
export const LeftPanelProvider = left.Provider
export const LeftPanelHost = left.Host
export const LeftPanel = left.Panel
export const useLeftPanel = left.use
