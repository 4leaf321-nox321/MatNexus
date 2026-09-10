/**
 * 표에서 **화살표로 줄 사이를 옮겨 다닌다.**
 *
 * ## 왜 필요한가 (2026-09-11 요청)
 *
 * 목록을 훑는 일은 마우스로 하기에 성가시다 — 재료 20건을 하나씩 열어 보려면
 * 열고, 뒤로 가고, 다음 줄을 눈으로 다시 찾아 눌러야 한다. **키보드로는 아예
 * 안 됐다**: Tab 은 줄이 아니라 그 안의 링크·체크상자를 하나씩 지나가므로,
 * 다음 재료로 가려면 한 줄에 두세 번을 눌러야 했다.
 *
 * ## 어떻게 도나 — 줄 하나만 Tab 순서에 남긴다
 *
 * 표 전체를 Tab 으로 지나갈 수 있어야 하지만, 줄이 200개면 200번을 눌러야 한다.
 * 그래서 **지금 있는 줄만 `tabIndex=0`** 이고 나머지는 `-1` 이다(roving tabindex).
 * Tab 한 번이면 표를 지나가고, 표 안에서는 화살표로 다닌다 — 파일 탐색기·메일함이
 * 그렇게 돌고, 사람이 그것을 기대한다.
 *
 *     ↑ ↓        앞뒤 줄
 *     Home End   맨 처음·맨 끝
 *     Enter      그 줄의 첫 링크를 연다
 *
 * ## 왜 DOM 을 직접 만지나
 *
 * 줄마다 ref 를 들고 배열로 모으는 방법도 있는데, 그러면 **거르기·정렬로 줄이
 * 갈릴 때마다 그 배열이 어긋난다** — 지운 줄의 ref 가 남아 「다음 줄」 이 사라진
 * 자리를 가리킨다. 형제 줄은 브라우저가 이미 알고 있으므로 그것을 묻는다.
 *
 * ## 스크롤이 먼저 튀지 않게 (2026-09-11 지적)
 *
 * 줄에 포커스를 주면 브라우저가 **그 줄을 화면 가운데로 끌어온다.** 한 줄씩
 * 내려가는데 화면이 크게 출렁이므로, 사람 눈에는 「화살표가 스크롤부터 한다」
 * 로 보인다. 그래서 브라우저의 스크롤을 끄고(`preventScroll`) **필요한 만큼만**
 * 우리가 옮긴다(`block: 'nearest'`) — 이미 보이는 줄이면 화면이 가만히 있는다.
 *
 * 그리고 **누른 줄에 포커스를 준다.** 표 안을 클릭하고 화살표를 눌렀는데
 * 포커스가 표 밖에 있으면 그 화살표는 페이지를 스크롤한다 — 눌러서 고른 줄이
 * 있는데 화살표가 안 먹는 것으로 보인다.
 *
 * ## Enter 가 링크를 누르는 이유
 *
 * 줄은 링크가 아니라 상자다. 그래서 Enter 를 안 다루면 **포커스는 줄에 있는데
 * 열 방법이 없다** — 화살표로 옮겨 다니다가 마우스를 다시 잡아야 한다. 줄의 첫
 * 링크가 그 줄의 주된 손잡이라(이름 열), 그것을 누른다.
 */

import { useCallback, useState } from 'react'
import type { KeyboardEvent, MouseEvent } from 'react'

/** 줄에 붙일 것들. `<TableRow {...focus.rowProps(id)}>` 로 편다. */
export interface RowProps {
  tabIndex: number
  'data-row': string
  onFocus: () => void
  onMouseDown: (event: MouseEvent<HTMLElement>) => void
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => void
}

export interface RowFocus {
  rowProps: (id: string) => RowProps
  /** 지금 Tab 순서에 있는 줄. 표가 바뀌면 첫 줄로 돌아간다. */
  at: string | null
}

/** 줄에 주는 눈에 보이는 표시. **없으면 어디 있는지 모른 채 화살표만 누른다.** */
export const ROW_FOCUS_STYLE =
  'focus-visible:ring-primary/60 focus-visible:ring-2 focus-visible:ring-inset focus-visible:outline-none'

function move(from: HTMLElement, to: 'next' | 'prev' | 'first' | 'last'): string | null {
  const row = from.closest<HTMLElement>('[data-row]')
  const body = row?.parentElement
  if (!row || !body) return null
  const rows = Array.from(body.querySelectorAll<HTMLElement>(':scope > [data-row]'))
  const here = rows.indexOf(row)
  if (here < 0) return null
  const target =
    to === 'next'
      ? rows[here + 1]
      : to === 'prev'
        ? rows[here - 1]
        : to === 'first'
          ? rows[0]
          : rows[rows.length - 1]
  if (!target) return null
  // **브라우저에 스크롤을 맡기지 않는다.** 맡기면 줄을 화면 가운데로 끌어와
  // 한 줄 내려갈 때마다 화면이 출렁인다.
  target.focus({ preventScroll: true })
  target.scrollIntoView({ block: 'nearest' })
  return target.dataset.row ?? null
}

export interface RowFocusOptions {
  /**
   * 아직 아무 줄도 안 짚었을 때 **Tab 이 닿을 줄.** 「지금 보고 있는 것」 이
   * 있는 목록(재료 상세의 왼쪽 목록)에서 그 줄을 준다 — 안 주면 Tab 이 늘 첫
   * 줄로 가고, 50번째 재료를 보는 중에도 처음부터 내려와야 한다.
   */
  preferred?: string | null
  /**
   * 화살표로 **옮겨 간 줄**. 주면 옮기는 것이 곧 고르는 것이 된다.
   *
   * **아무 목록에나 주면 안 된다.** 줄을 고르는 일이 그 화면 안에서 끝나는
   * 목록에만 준다(재료 상세의 왼쪽 목록처럼) — 줄이 다른 화면으로 가는 링크인
   * 목록에서는 화살표 한 번에 목록을 떠나 버린다.
   *
   * 마우스로 누른 것과 Tab 으로 들어온 것에는 안 부른다. 그 둘은 사람이 이미
   * 「거기로 간다」 를 뜻했거나(클릭), 아직 아무것도 안 고른 것이다(Tab).
   */
  onMove?: (id: string) => void
}

/**
 * @param ids 지금 보이는 줄. 거르기·정렬로 바뀌면 그대로 따라간다.
 */
export function useRowFocus(ids: string[], options: RowFocusOptions = {}): RowFocus {
  const { preferred, onMove } = options
  const [at, setAt] = useState<string | null>(null)
  // 고른 줄이 거르기로 사라졌으면 짚어 준 줄, 그것도 없으면 첫 줄이 Tab 순서를
  // 든다 — 아무 줄도 `0` 이 아니면 **표를 Tab 으로 아예 못 들어간다.**
  const fallback = preferred && ids.includes(preferred) ? preferred : (ids[0] ?? null)
  const here = at && ids.includes(at) ? at : fallback

  const rowProps = useCallback(
    (id: string): RowProps => ({
      tabIndex: id === here ? 0 : -1,
      'data-row': id,
      onFocus: () => setAt(id),
      // 누른 줄이 곧 지금 줄이다. 안 주면 클릭한 뒤 누른 화살표가 페이지를
      // 스크롤한다 — 고른 줄이 있는데 화살표가 안 먹는 것으로 보인다.
      onMouseDown: (event) => {
        const node = event.target as HTMLElement
        if (node.closest('a, button, input, select, textarea, label')) return
        event.currentTarget.focus({ preventScroll: true })
      },
      onKeyDown: (event) => {
        const node = event.target as HTMLElement
        // **글자를 치는 중이면 손대지 않는다.** 줄 안에 입력 칸이 있는 표가
        // 있고, 거기서 화살표는 글자 사이를 옮기는 것이다.
        if (node.closest('input, textarea, select')) return
        const how =
          event.key === 'ArrowDown'
            ? 'next'
            : event.key === 'ArrowUp'
              ? 'prev'
              : event.key === 'Home'
                ? 'first'
                : event.key === 'End'
                  ? 'last'
                  : null
        if (how) {
          event.preventDefault()
          const moved = move(event.currentTarget, how)
          if (moved && onMove) onMove(moved)
          return
        }
        // 줄 자체에 포커스가 있을 때만 연다. 안쪽 단추 위에서 누른 Enter 는
        // 그 단추의 것이다.
        if (event.key === 'Enter' && node === event.currentTarget) {
          const link = event.currentTarget.querySelector<HTMLAnchorElement>('a[href]')
          if (link) {
            event.preventDefault()
            link.click()
          }
        }
      },
    }),
    [here, onMove]
  )

  return { rowProps, at: here }
}
