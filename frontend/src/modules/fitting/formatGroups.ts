/**
 * 형식을 **솔버로 묶는다** — 「ANSYS (선형)」 · 「ANSYS (탄소성)」 은 한 솔버의 두 모델이다.
 *
 * 솔버 × 물성 모델로 형식이 서른 개 가까이 되면서(2026-09-27) 한 줄로 늘어놓은 목록은
 * 고를 것을 찾는 데 시간이 든다. 이름의 괄호 앞이 솔버다 — 서버가 그 꼴로 짓는다
 * (`tests/unit/test_export_solvers.py` 가 지킨다). 정의로 붙인 형식은 그 꼴이 아닐 수
 * 있는데, 그때는 이름 전체가 한 묶음이 된다 — 틀리게 묶는 것보다 따로 서는 편이 낫다.
 */

export interface FormatLike {
  key: string
  label: string
}

/** 괄호 앞 — 「LS-DYNA (속도 의존)」 → 「LS-DYNA」. 괄호가 없으면 이름 전체. */
export function solverOf(label: string): string {
  const open = label.indexOf(' (')
  return open > 0 ? label.slice(0, open) : label
}

/** 솔버마다 한 묶음. **묶음 차례는 서버가 준 차례**(처음 나온 자리)다. */
export function groupBySolver<T extends FormatLike>(
  formats: T[]
): { solver: string; items: T[] }[] {
  const groups = new Map<string, T[]>()
  for (const format of formats) {
    const solver = solverOf(format.label)
    const items = groups.get(solver)
    if (items) items.push(format)
    else groups.set(solver, [format])
  }
  return [...groups.entries()].map(([solver, items]) => ({ solver, items }))
}
