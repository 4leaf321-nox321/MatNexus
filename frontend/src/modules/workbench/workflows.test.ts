/**
 * 단계 판정 — **모르면서 됐다고 하지 않는다.**
 *
 * 이 판정이 틀리면 사람은 안 끝난 일을 끝난 줄 알고 지나간다. 그래서 무는 것이 넷이다.
 *
 *   안 겹친 시험이 있으면      「됐다」 하지 않고 **어느 것인지 이름을 댄다**
 *   온도 한 단은 남은 일이 아니다  겹칠 수 없는 것을 재촉하면 그 줄을 다시 안 읽는다
 *   모르는 것은 세지 않는다     안 세어 본 시험을 「할 수 있다」 로 밀지 않는다
 *   사라진 줄은 세지 않는다     그것은 이미 그 줄이 말한다
 */

import { describe, expect, it } from 'vitest'

import { workflowOf } from '@/modules/workbench/workflows'
import type { StepCheck } from '@/modules/workbench/workflows'
import type { BasketItem } from '@/shared/api/basket'

function item(over: Partial<BasketItem> & { facts?: Record<string, number> }): BasketItem {
  return {
    id: crypto.randomUUID(),
    kind: 'test_run',
    target_id: crypto.randomUUID(),
    label: '시편 A',
    detail: null,
    facts: {},
    missing: false,
    note: null,
    added_at: '2026-09-01T00:00:00Z',
    ...over,
  } as BasketItem
}

/** 남은 것들의 이름. **줄 자체를 돌려주므로** 화면이 링크를 걸 수 있다. */
function names(check: StepCheck | null): string[] {
  return (check?.blocking ?? []).map((one) => one.label)
}

function judge(flowKey: string, stepKey: string, items: BasketItem[]) {
  const step = workflowOf(flowKey)!.steps.find((one) => one.key === stepKey)!
  return step.judge?.(items) ?? null
}

const swept = (label: string, curves: number) =>
  item({ label, facts: { master_curves: curves, temperature_steps: 5 } })

describe('점탄성 — 마스터커브 갖추기', () => {
  it('안 겹친 것이 있으면 이름을 댄다', () => {
    // 세기만 하면 「2건」 을 들고 어느 것인지 찾으러 다녀야 한다.
    const check = judge('viscoelastic_set', 'master', [
      swept('시편 A', 1),
      swept('시편 B', 0),
      swept('시편 C', 0),
    ])
    expect(check).toMatchObject({ ok: false })
    expect(check!.say).toContain('2건')
    expect(names(check)).toEqual(['시편 B', '시편 C'])
  })

  it('다 갖췄으면 됐다고 한다', () => {
    const check = judge('viscoelastic_set', 'master', [swept('시편 A', 1), swept('시편 B', 2)])
    expect(check).toMatchObject({ ok: true })
    expect(names(check)).toEqual([])
  })

  it('온도가 한 단인 것은 남은 일로 세지 않는다', () => {
    // 변형률 스윕은 겹칠 것이 없다. 재촉하면 **할 수 없는 일**을 가리키게 된다.
    const check = judge('viscoelastic_set', 'master', [
      swept('시편 A', 1),
      item({ label: '변형률 스윕', facts: { master_curves: 0, temperature_steps: 1 } }),
    ])
    expect(names(check)).toEqual([])
    expect(check!.say).toContain('겹칠 수 없습니다')
    // **여기서 더 할 수 있는 일이 없으므로 이 단계는 끝난 것이다.** 말은 해 주되
    // 「아직 남았다」 로 세우면 영원히 안 끝나는 단계가 된다.
    expect(check!.ok).toBe(true)
  })

  it('안 세어 본 것은 따로 말한다', () => {
    // `-1` 은 「모른다」 다 — 0으로 읽으면 없는 일을 만들거나 진짜 남은 일을 숨긴다.
    const check = judge('viscoelastic_set', 'master', [
      swept('시편 A', 1),
      item({ label: '옛 시험', facts: { master_curves: 0, temperature_steps: -1 } }),
    ])
    expect(check!.say).toContain('안 세어 봤습니다')
    expect(names(check)).toEqual([])
  })

  it('사라진 줄은 세지 않는다', () => {
    const check = judge('viscoelastic_set', 'master', [
      swept('시편 A', 1),
      item({ label: '사라졌습니다', missing: true, facts: {} }),
    ])
    expect(check).toMatchObject({ ok: true })
  })

  it('담은 시험이 없으면 침묵한다', () => {
    expect(judge('viscoelastic_set', 'master', [])).toBeNull()
  })
})

describe('점탄성 — 나머지 단계', () => {
  it('한 건만 담으면 아직이라고 한다', () => {
    // **둘부터가 「한 벌」 이다.** 한 건이면 그 시험 화면에서 하는 편이 빠르다.
    expect(judge('viscoelastic_set', 'pick', [swept('시편 A', 0)])).toMatchObject({ ok: false })
    expect(
      judge('viscoelastic_set', 'pick', [swept('시편 A', 0), swept('시편 B', 0)])
    ).toMatchObject({ ok: true })
  })

  it('맞춘 계수가 하나라도 있어야 피팅이 끝난다', () => {
    expect(
      judge('viscoelastic_set', 'fit', [item({ facts: { master_curves: 1, prony_fits: 0 } })])
    ).toMatchObject({ ok: false })
    expect(
      judge('viscoelastic_set', 'fit', [item({ facts: { master_curves: 1, prony_fits: 1 } })])
    ).toMatchObject({ ok: true })
  })
})

describe('다른 시나리오도 같은 사실로 본다', () => {
  it('채택 안 한 시험의 이름을 댄다', () => {
    const check = judge('daily_intake', 'adopt', [
      item({ label: '오늘-1', facts: { adopted: 1 } }),
      item({ label: '오늘-2', facts: { adopted: 0 } }),
    ])
    expect(check).toMatchObject({ ok: false })
    expect(names(check)).toEqual(['오늘-2'])
  })

  it('초안이 섞인 묶음은 말해 주되 막지 않는다', () => {
    const check = judge('analysis_deck', 'export', [
      item({ kind: 'card', label: '인장 MD', facts: { published: 1 } }),
      item({ kind: 'card', label: '점탄성', facts: { published: 0 } }),
    ])
    expect(check).toMatchObject({ ok: false })
    expect(names(check)).toEqual(['점탄성'])
    expect(check!.say).toContain('내보낼 수는 있지만')
  })
})
