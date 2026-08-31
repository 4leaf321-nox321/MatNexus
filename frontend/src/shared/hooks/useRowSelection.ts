/**
 * 표에서 줄을 고른다 — **Shift 로 범위, Ctrl 로 하나씩.**
 *
 * ## 왜 훅인가
 *
 * 고르는 표가 아홉 곳이다(재료·시편·시험·묶음·휴지통·기준정보 둘·커넥터·규격
 * 카탈로그). 각자 `useState<Set<string>>` 과 체크박스 `onChange` 를 손으로 적고
 * 있었고, 범위 선택을 붙이려면 **아홉 번 같은 것을 적어야** 했다. 그러면 한
 * 곳만 고쳐지고, 사람은 어떤 표에서는 Shift 가 되고 어떤 표에서는 안 되는 것을
 * 겪는다 — 그 차이를 설명할 수 있는 사람이 없다.
 *
 * ## Shift 가 하는 일
 *
 * 마지막으로 누른 줄(닻)부터 지금 누른 줄까지를 **켠다.** 끄지 않는다 —
 * 파일 탐색기·메일함이 그렇고, 사람이 그것을 기대한다.
 *
 * **닻은 「마지막으로 누른 줄」 이지 「마지막으로 켠 줄」 이 아니다.** 껐던 줄에서
 * Shift 를 눌러도 거기서부터 이어진다.
 *
 * ## Ctrl 은 따로 안 다룬다
 *
 * 체크박스는 원래 한 번에 하나씩 토글한다 — Ctrl 을 눌러도 같다. 그래서 Ctrl 을
 * 위한 코드가 따로 없고, **누른 채로 눌러도 평소와 같이 동작한다.** 없는 규칙을
 * 만들어 두면 다음 사람이 그것을 지키려다 헷갈린다.
 *
 * ## 목록이 바뀌면 사라진 줄을 버린다
 *
 * 거르기를 바꾸면 안 보이는 줄이 선택에 남는다. 그대로 두면 **사람이 본 수와
 * 실제로 손대는 수가 어긋나고**, 그때 누른 「예」 는 다른 것에 대한 대답이 된다.
 */

import { useCallback, useMemo, useRef, useState } from 'react'

export interface RowSelection {
  /** 지금 보이는 줄 중에서 고른 것. **안 보이는 줄은 안 들어 있다.** */
  picked: Set<string>
  /** 고른 줄의 id — 화면이 그대로 API 에 넘긴다. 목록 차례를 지킨다. */
  chosen: string[]
  /** 한 줄을 켜거나 끈다. `event` 를 주면 Shift 범위가 먹는다. */
  toggle: (id: string, event?: { shiftKey?: boolean }) => void
  /** 이 쪽 전부 켜기/끄기. */
  setAll: (on: boolean) => void
  /** 비운다. 거르기를 바꾸거나 일을 끝냈을 때. */
  clear: () => void
  /** 머리 칸의 상태 — 전부 켜졌나. */
  allOn: boolean
  /** 일부만 켜졌나(머리 칸의 `indeterminate`). */
  someOn: boolean
}

export function useRowSelection(ids: string[]): RowSelection {
  const [raw, setRaw] = useState<Set<string>>(new Set())
  const anchor = useRef<string | null>(null)

  // **보이는 것만 센다.** 거르기로 사라진 줄이 남아 있으면 수가 어긋난다.
  const picked = useMemo(() => new Set(ids.filter((id) => raw.has(id))), [ids, raw])
  const chosen = useMemo(() => ids.filter((id) => raw.has(id)), [ids, raw])

  const toggle = useCallback(
    (id: string, event?: { shiftKey?: boolean }) => {
      // **닻을 밖에서 붙잡는다.** `setRaw` 의 업데이터는 나중에 도는데, 그 사이
      // 아래에서 닻이 이미 이번 줄로 바뀐다 — 안에서 읽으면 범위가 늘 한 줄이
      // 되고, Shift 가 그냥 토글처럼 보인다.
      const from = anchor.current
      const start = from === null ? -1 : ids.indexOf(from)
      const end = ids.indexOf(id)
      setRaw((current) => {
        const next = new Set(current)

        // 닻이 목록에서 사라졌으면(거르기가 바뀌었다) 평소처럼 하나만 다룬다.
        if (event?.shiftKey && start !== -1 && end !== -1) {
          const [a, b] = start <= end ? [start, end] : [end, start]
          for (const one of ids.slice(a, b + 1)) next.add(one)
          return next
        }
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
      })
      anchor.current = id
    },
    [ids]
  )

  const setAll = useCallback(
    (on: boolean) => {
      setRaw((current) => {
        const next = new Set(current)
        for (const id of ids) {
          if (on) next.add(id)
          else next.delete(id)
        }
        return next
      })
      // **닻을 지운다.** 전부 고른 뒤의 Shift 가 어디서부터인지 아무도 모른다.
      anchor.current = null
    },
    [ids]
  )

  const clear = useCallback(() => {
    setRaw(new Set())
    anchor.current = null
  }, [])

  return {
    picked,
    chosen,
    toggle,
    setAll,
    clear,
    allOn: ids.length > 0 && picked.size === ids.length,
    someOn: picked.size > 0 && picked.size < ids.length,
  }
}
