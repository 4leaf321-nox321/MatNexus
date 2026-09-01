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
    material_id: null,
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

  it('카드는 담아 달라고 하지 않고 근거로 센다', () => {
    // **다 한 일을 바구니에 도로 담아 신고하게 만들지 않는다.** 카드가 어느
    // 시험에서 나왔는지 스스로 들고 있어서 서버가 세어 준다.
    expect(
      judge('viscoelastic_set', 'card', [item({ facts: { prony_fits: 1, cards: 0 } })])
    ).toMatchObject({ ok: false })
    expect(
      judge('viscoelastic_set', 'card', [item({ facts: { prony_fits: 1, cards: 2 } })])
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

describe('해석 물성 — 무엇이 비었나', () => {
  const material = (label: string, cards: number, published = 0) =>
    item({
      kind: 'material',
      label,
      material_id: label,
      facts: { cards, published_cards: published },
    })

  it('카드가 없는 재료의 이름을 댄다', () => {
    // **이 판정이 이 시나리오의 산출물이다** — 「해석에 넘기기 전에 뭐가 비었나」.
    // 지금까지는 재료를 하나씩 열어 봐야 알 수 있었다.
    const check = judge('analysis_deck', 'survey', [
      material('EPDM-70', 2, 2),
      material('PP-GF30', 0),
    ])
    expect(check).toMatchObject({ ok: false })
    expect(check!.say).toContain('1건에 카드가 없습니다')
    expect(names(check)).toEqual(['PP-GF30'])
  })

  it('초안뿐인 재료는 따로 말한다', () => {
    // 만들 것이 아니라 **확정할 것**이다 — 같은 말로 세면 할 일이 뒤섞인다.
    const check = judge('analysis_deck', 'survey', [
      material('EPDM-70', 2, 2),
      material('PP-GF30', 1, 0),
    ])
    expect(check!.say).toContain('초안뿐입니다')
    expect(names(check)).toEqual(['PP-GF30'])
    // 카드는 있으므로 이 단계는 끝났다. 확정은 다음 사람(부서 관리자)의 일이다.
    expect(check!.ok).toBe(true)
  })

  it('다 갖췄으면 됐다고 한다', () => {
    const check = judge('analysis_deck', 'survey', [material('EPDM-70', 2, 1)])
    expect(check).toMatchObject({ ok: true })
  })
})

describe('해석 물성 — 빠뜨린 재료', () => {
  it('재료는 셋인데 카드가 한 재료 것뿐이면 짚어 준다', () => {
    // **담았다는 사실만으로 「다 골랐다」 고 하면 누락이 안 보인다.** 해석에 재료
    // 하나가 빠지면 그 부품만 딴 물성으로 돈다.
    const check = judge('analysis_deck', 'collect', [
      item({ kind: 'material', label: 'EPDM-70', material_id: 'm1', facts: { cards: 1 } }),
      item({ kind: 'material', label: 'PP-GF30', material_id: 'm2', facts: { cards: 1 } }),
      item({ kind: 'card', label: '점탄성', material_id: 'm1', facts: { published: 1 } }),
    ])
    expect(check).toMatchObject({ ok: false })
    expect(names(check)).toEqual(['PP-GF30'])
  })

  it('재료마다 카드가 담겼으면 넘어간다', () => {
    const check = judge('analysis_deck', 'collect', [
      item({ kind: 'material', label: 'EPDM-70', material_id: 'm1', facts: { cards: 1 } }),
      item({ kind: 'card', label: '점탄성', material_id: 'm1', facts: { published: 1 } }),
    ])
    expect(check).toMatchObject({ ok: true })
  })
})

describe('오늘 들어온 것 — 앞 단계가 말한 것을 두 번 말하지 않는다', () => {
  const run = (label: string, facts: Record<string, number>) => item({ label, facts })

  it('안 읽힌 시험을 먼저 골라낸다', () => {
    // **읽기가 실패한 시험에 레시피를 걸면** 「처리했는데 값이 안 나온다」 로 한
    // 바퀴를 더 돈다.
    const check = judge('daily_intake', 'read', [
      run('오늘-1', { parsed: 1 }),
      run('오늘-2', { parsed: 0 }),
    ])
    expect(check).toMatchObject({ ok: false })
    expect(names(check)).toEqual(['오늘-2'])
  })

  it('처리 단계는 읽힌 것만 센다', () => {
    // 안 읽힌 시험까지 「처리 전」 으로 세우면 **같은 시험을 두 단계가 동시에
    // 가리킨다** — 사람은 어느 쪽을 봐야 하는지 모른다.
    const check = judge('daily_intake', 'process', [
      run('오늘-1', { parsed: 1, results: 1 }),
      run('안읽힘', { parsed: 0, results: 0 }),
    ])
    expect(check).toMatchObject({ ok: true })
    expect(names(check)).toEqual([])
  })

  it('처리 안 된 것의 이름을 댄다', () => {
    const check = judge('daily_intake', 'process', [
      run('오늘-1', { parsed: 1, results: 1 }),
      run('오늘-2', { parsed: 1, results: 0 }),
    ])
    expect(names(check)).toEqual(['오늘-2'])
  })

  it('채택 단계는 처리된 것만 센다', () => {
    // 처리 결과가 없으면 **채택할 것 자체가 없다.**
    const check = judge('daily_intake', 'adopt', [
      run('오늘-1', { parsed: 1, results: 1, adopted: 1 }),
      run('처리전', { parsed: 1, results: 0, adopted: 0 }),
    ])
    expect(check).toMatchObject({ ok: true })
  })

  it('채택 안 한 시험의 이름을 댄다', () => {
    const check = judge('daily_intake', 'adopt', [
      run('오늘-1', { results: 1, adopted: 1 }),
      run('오늘-2', { results: 1, adopted: 0 }),
    ])
    expect(check).toMatchObject({ ok: false })
    expect(names(check)).toEqual(['오늘-2'])
  })
})

describe('새 장비 파일 — 읽혔다고 매핑이 된 것은 아니다', () => {
  it('안 읽혔으면 표 규칙부터 보라고 한다', () => {
    const check = judge('new_instrument', 'verify', [
      item({ label: '시험-1', facts: { parsed: 0, channels: 0 } }),
    ])
    expect(check).toMatchObject({ ok: false })
    expect(check!.say).toContain('표를 고르는 규칙')
  })

  it('읽혔는데 채널이 0이면 열 매핑을 보라고 한다', () => {
    // **열 이름이 하나도 안 맞아도 파일은 읽힌다** — 그러고 표가 비어 있다.
    // 이 둘을 같은 말로 안내하면 사람이 엉뚱한 화면을 고친다.
    const check = judge('new_instrument', 'verify', [
      item({ label: '시험-1', facts: { parsed: 1, channels: 0 } }),
    ])
    expect(check).toMatchObject({ ok: false })
    expect(check!.say).toContain('열 매핑')
    expect(names(check)).toEqual(['시험-1'])
  })

  it('채널이 잡혔으면 몇 개인지 적는다', () => {
    const check = judge('new_instrument', 'verify', [
      item({ label: '시험-1', facts: { parsed: 1, channels: 8 } }),
    ])
    expect(check).toMatchObject({ ok: true })
    expect(check!.say).toContain('8개')
  })
})

describe('확정 전 근거 훑기 — 근거의 두께', () => {
  const card = (label: string, facts: Record<string, number>) =>
    item({ kind: 'card', label, facts })

  it('표본이 하나인 카드를 짚어 준다', () => {
    // **표본 하나로 만든 카드는 만들 수는 있어도 그대로 확정하면 안 된다.**
    const check = judge('review_cards', 'read', [
      card('인장 MD', { samples: 5 }),
      card('인장 TD', { samples: 1 }),
    ])
    expect(check!.say).toContain('표본이 하나')
    expect(names(check)).toEqual(['인장 TD'])
  })

  it('경고가 붙은 카드도 짚어 준다', () => {
    const check = judge('review_cards', 'read', [card('점탄성', { samples: 4, notes: 2 })])
    expect(check!.say).toContain('경고')
    expect(names(check)).toEqual(['점탄성'])
  })

  it('둘 다인 카드를 두 번 세지 않는다', () => {
    const check = judge('review_cards', 'read', [card('점탄성', { samples: 1, notes: 1 })])
    expect(names(check)).toEqual(['점탄성'])
  })

  it('확정하러 갈 자리를 준다 — 카드 목록에는 그 단추가 없다', () => {
    // **막다른 길을 만들지 않는다.** 확정은 재료 화면의 물성 패널에서 누른다.
    // 눌러야 할 것이 없는 화면에 도착하면 사람은 기능이 없다고 결론 낸다.
    const check = judge('review_cards', 'decide', [
      item({ kind: 'card', label: '인장 TD', material_id: 'm7', facts: { published: 0 } }),
    ])
    // 확정 단추는 재료 화면의 **「CAE 카드」 탭**에 있다 — 탭까지 적어야 그리로 열린다.
    expect(check!.go).toMatchObject({ href: '/materials/m7?tab=cards' })
  })

  it('막지는 않는다 — 읽었는지는 화면이 알 수 없다', () => {
    const check = judge('review_cards', 'read', [card('인장 TD', { samples: 1 })])
    expect(check!.ok).toBe(true)
  })
})

describe('다른 시나리오도 같은 사실로 본다', () => {

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
