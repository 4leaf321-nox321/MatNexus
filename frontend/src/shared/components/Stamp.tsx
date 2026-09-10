/**
 * 표 칸에 적는 등록 일시.
 *
 * **날짜만으로는 모자란다.** 같은 날 여러 번 올리는 일이 흔하고(이관·배치 등록),
 * 그때 날짜만 보이면 어느 것이 나중 것인지 표만 봐서는 모른다.
 *
 * `CreatedOn` 과 자리가 다르다 — 그쪽은 **제목 옆**이라 길어지면 이름이 밀려서
 * 날짜만 적고, 여기는 **제 열**이라 시각까지 들어간다.
 *
 * ## 값이므로 흐리게 그리지 않는다
 *
 * 전에는 `text-muted-foreground text-xs` 였다. 제 열에 선 값인데 혼자 작고
 * 흐려서, 한 줄 안에서 글자 크기가 세 가지로 보이는 원인 중 하나였다
 * (2026-09-10 지적). **흐리게 하는 것은 값이 아닌 것뿐이다** — 여기서는 「없음」
 * 하나다.
 */

import { stamp, stampFull } from '@/shared/lib/datetime'

export function Stamp({ at }: { at?: string | null }) {
  if (!at) return <span className="text-muted-foreground">—</span>
  return (
    <span
      className="whitespace-nowrap tabular-nums"
      title={stampFull(at)}
    >
      {stamp(at)}
    </span>
  )
}
