/**
 * 조합된 이름 하나 — **값이 없는 칸을 흐리게 그린다.**
 *
 * ## 왜 지우지 않는가
 *
 * 이름은 `Grade_Details_두께` 로 조합되고, 값이 없는 칸은 `-` 로 남는다
 * (`matcore/naming.py`). 그 `-` 를 빼면 **칸 수가 값에 따라 달라진다** —
 * `SECC_1.0` 이 「Details 가 1.0」 인지 「두께가 1.0」 인지 알 수 없다. 옛 앱이
 * 정확히 그렇게 했고, 두께를 나중에 채우는 순간 이름이 바뀌어 하위 데이터가
 * 통째로 끊어졌다(ADR 0004).
 *
 * 실측(2026-08-31, 개발 DB): 재료 111개 중 **75개가 가운데 빈 칸**을 갖는다
 * (Details 없음). 지울 수 없는 쪽이 대부분이다.
 *
 * ## 그래서 무게만 뺀다
 *
 * 글자는 그대로 둔다. 화면에서 감추면 **보이는 이름과 저장된 이름이 갈라지고**,
 * 검색은 저장된 이름으로 걸리므로 보이는 대로 쳐서는 안 찾힌다. 복사해도 진짜
 * 이름이 그대로 나온다.
 *
 * ## 시험에서 주의할 것
 *
 * 칸마다 span 이 생기므로 **`getByText('SECC_-_1.0')` 는 안 걸린다** — RTL 의
 * 기본 대조가 직계 텍스트만 보기 때문이다. 통째로 찾으려면 함수 대조를 쓴다:
 * 링크·버튼 안이면 **접근 이름으로 찾는 것이 가장 낫다** —
 * `getByRole('link', { name })`. 조각이 합쳐져 온다.
 */

import { Fragment } from 'react'

/** 값이 없는 칸. `matcore/naming.py` 의 `PLACEHOLDER` 와 같아야 한다. */
export const NAME_PLACEHOLDER = '-'

/** 칸을 나누는 글자. 계층 경계 `__` 는 빈 조각으로 갈라진다. */
const FIELD_SEP = '_'

/**
 * 값이 `-` 하나인 칸은 **언제나 빈 칸이다.**
 *
 * `sanitize` 가 값의 앞뒤 `-` 를 떼고 이어진 것을 하나로 줄이므로, 사람이 친
 * 값이 `-` 하나로 남는 경우가 없다.
 */
function isBlank(part: string): boolean {
  return part === NAME_PLACEHOLDER
}

export function RecordName({ name, className }: { name: string; className?: string }) {
  const parts = name.split(FIELD_SEP)
  return (
    <span className={className}>
      {parts.map((part, index) => (
        <Fragment key={index}>
          {index > 0 && FIELD_SEP}
          {isBlank(part) ? (
            <span className="opacity-40" title="값이 없는 칸">
              {part}
            </span>
          ) : (
            part
          )}
        </Fragment>
      ))}
    </span>
  )
}
