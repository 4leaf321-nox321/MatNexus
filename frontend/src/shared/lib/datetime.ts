/**
 * 표에 적는 시각 — **날짜만으로는 모자란 자리가 있다.**
 *
 * 같은 날 여러 번 올리는 일이 흔하다. 이관은 한 번에 안 끝나고(이름 규칙을 고쳐
 * 다시 돌린다), 시험은 배치로 들어온다 — 그때 날짜만 보이면 **어느 것이 나중
 * 것인지 표만 봐서는 모른다.**
 *
 * ## `toLocaleString` 을 그대로 안 쓴다
 *
 * `2026. 8. 28. 오전 9:59:00` 은 표 칸에 너무 넓다. 열이 여덟인 표에서 이 한
 * 칸이 이름보다 넓어진다.
 *
 * `2026-08-28 09:59` 로 적는다 — 자리 수가 늘 같아서 **줄이 세로로 정렬되고**,
 * 24시로 적어 오전·오후를 읽는 단계가 없다. 초는 `title` 에 넣는다: 표에서
 * 초까지 볼 일은 드물지만, 같은 분에 둘이 들어온 것을 가릴 때는 필요하다.
 *
 * ## 한 곳에 둔다
 *
 * 전에는 화면마다 `when()` 을 따로 적었다(변경 이력·휴지통). 두 벌이 되면 한쪽만
 * 고쳐지고, 그때 같은 표에서 시각 모양이 갈린다.
 */

/** `2026-08-28 09:59`. 못 읽는 값이면 그대로 돌려준다. */
export function stamp(value: string | null | undefined): string {
  if (!value) return ''
  const at = new Date(value)
  if (Number.isNaN(at.getTime())) return value
  const pad = (one: number) => String(one).padStart(2, '0')
  return (
    `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())} ` +
    `${pad(at.getHours())}:${pad(at.getMinutes())}`
  )
}

/** 마우스를 올렸을 때 보이는 것. **초까지** — 같은 분에 둘이 들어왔을 때 가른다. */
export function stampFull(value: string | null | undefined): string | undefined {
  if (!value) return undefined
  const at = new Date(value)
  return Number.isNaN(at.getTime()) ? undefined : at.toLocaleString('ko-KR')
}
