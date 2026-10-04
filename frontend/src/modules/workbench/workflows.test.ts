/**
 * 업무 판정 — **모르면서 됐다고 하지 않는다**(ADR 0024 · 0058).
 *
 * 이 판정이 틀리면 사람은 안 끝난 일을 끝난 줄 알고 지나간다. 그래서 무는 것은 이렇다.
 *
 *   남은 것이 있으면          「됐다」 하지 않고 **어느 것인지 이름을 댄다**
 *   할 수 없는 일은 재촉 안 함  표로 입력한 시험에 읽기 · 처리를 재촉하지 않는다
 *   진짜 경고만 경고다         출처 설명까지 세면 카드마다 「경고」 가 선다
 *   사용 중지는 초안이 아니다   확정하라고 재촉하지 않는다
 *   사라진 줄은 세지 않는다     그것은 이미 그 줄이 말한다
 *   옛 이름으로도 열린다       서버에 그 이름으로 적힌 작업이 있다
 */

import { readFileSync } from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  FACTS_READ,
  LEGACY_KEYS,
  WORKFLOWS,
  WORKFLOW_GROUPS,
  hasView,
  stepKeyOf,
  workflowOf,
  workflowsIn,
} from '@/modules/workbench/workflows'
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

describe('업무 목록', () => {
  it('업무마다 묶음이 있고, 묶음마다 업무가 있다', () => {
    // **빈 묶음은 홈에 제목만 선다** — 그러면 사람은 그 일을 못 하는 줄 안다.
    const groups = new Set(WORKFLOW_GROUPS.map((one) => one.key))
    for (const flow of WORKFLOWS) expect(groups.has(flow.group)).toBe(true)
    for (const group of WORKFLOW_GROUPS) expect(workflowsIn(group.key).length).toBeGreaterThan(0)
  })

  it('요청받은 네 업무가 있다 (2026-10-04)', () => {
    const titles = WORKFLOWS.map((one) => one.title)
    expect(titles).toContain('물성 카드 하나 만들기')
    expect(titles).toContain('부품표(BOM)로 여러 카드를 한 덱에')
    expect(titles).toContain('시험 데이터 한번에 처리하기')
    expect(titles).toContain('계산된 시험 데이터 한번에 채택하기')
  })

  it('묶음 안에서는 자주 하는 것이 먼저다', () => {
    const cadences = workflowsIn('tests').map((one) => one.cadence)
    expect(cadences.indexOf('매일')).toBeLessThan(cadences.indexOf('자주'))
  })

  it('전용 화면이 있는 업무를 가른다', () => {
    expect(hasView(workflowOf('adopt_many')!)).toBe(true)
    expect(hasView(workflowOf('review_cards')!)).toBe(false)
    // 마지막 단계에 내보내기 띠만 끼운 안내 업무 — 「전용 화면」 이 아니다.
    expect(hasView(workflowOf('bundle_export')!)).toBe(false)
  })

  it('이어 할 업무는 있는 업무다', () => {
    for (const flow of WORKFLOWS) {
      if (flow.next) expect(workflowOf(flow.next), flow.key).toBeDefined()
    }
  })

  it('업무 · 단계 이름이 겹치지 않는다', () => {
    // 겹치면 서버에 적힌 진행이 엉뚱한 단계를 가리킨다.
    expect(new Set(WORKFLOWS.map((one) => one.key)).size).toBe(WORKFLOWS.length)
    for (const flow of WORKFLOWS) {
      expect(new Set(flow.steps.map((one) => one.key)).size, flow.key).toBe(flow.steps.length)
    }
  })
})

describe('옛 이름으로 적힌 작업 (ADR 0058)', () => {
  it('옛 업무 이름은 지금 업무로 열린다', () => {
    // **서버에 그 이름으로 적힌 작업이 있다** — 지우면 「모르는 워크플로」 로 선다.
    expect(workflowOf('daily_intake')?.key).toBe('process_many')
    expect(workflowOf('viscoelastic_set')?.key).toBe('card_one')
    expect(workflowOf('analysis_deck')?.key).toBe('bundle_export')
    for (const current of Object.values(LEGACY_KEYS)) expect(workflowOf(current)).toBeDefined()
  })

  it('옛 단계 이름은 지금 단계로 옮긴다', () => {
    // 합친 단계로 옮기지 않으면 이어 하던 작업이 1단계로 되돌아간다.
    const card = workflowOf('card_one')!
    expect(stepKeyOf(card, 'master')).toBe('ready')
    expect(stepKeyOf(card, 'fit')).toBe('make')
    const bom = workflowOf('bom_deck')!
    expect(stepKeyOf(bom, 'match')).toBe('deck')
    // 지금 이름은 그대로, 모르는 이름도 그대로 — 그때 화면이 「바뀌었습니다」 를 말한다.
    expect(stepKeyOf(card, 'make')).toBe('make')
    expect(stepKeyOf(card, '없는단계')).toBe('없는단계')
  })

  it('옛 「오늘 들어온 것」 의 단계는 그대로 있다', () => {
    const steps = workflowOf('daily_intake')!.steps.map((one) => one.key)
    expect(steps).toEqual(['pick', 'read', 'process', 'adopt'])
  })
})

describe('사실의 이름 — 서버와 한 벌', () => {
  it('판정이 읽는 이름은 전부 표에 있다', () => {
    // **없는 키를 읽으면 0이 되고, 0은 「아직 안 했다」 로 읽힌다** — 영원히 안 끝나는 단계.
    // 서버 쪽은 `test_workbench_links.py` 가 이 표와 `FACT_KEYS` 를 대 본다.
    const source = readFileSync(
      path.resolve(process.cwd(), 'src/modules/workbench/workflows.ts'),
      'utf-8'
    )
    const read = new Set([...source.matchAll(/fact\([^,]+, '([a-z_]+)'\)/g)].map((one) => one[1]))
    const known = new Set(Object.values(FACTS_READ).flat())
    expect(read.size).toBeGreaterThan(0)
    for (const key of read) expect(known.has(key), key).toBe(true)
  })
})

describe('시험 데이터 — 읽기 · 처리 · 채택', () => {
  const run = (label: string, facts: Record<string, number>) => item({ label, facts })

  it('안 읽힌 시험을 먼저 골라내고, 형식 정의로 데려간다', () => {
    // **읽기가 실패한 시험에 레시피를 걸면** 「처리했는데 값이 안 나온다」 로 한
    // 바퀴를 더 돈다.
    const check = judge('process_many', 'read', [
      run('오늘-1', { parsed: 1 }),
      run('오늘-2', { parsed: 0 }),
    ])
    expect(check).toMatchObject({ ok: false })
    expect(names(check)).toEqual(['오늘-2'])
    expect(check!.go?.href).toBe('/settings/formats')
  })

  it('표로 입력한 시험은 안 읽힌 것이 아니다', () => {
    // 읽을 파일이 없다 — 「안 읽힘」 으로 세면 할 수 없는 일을 재촉한다(2026-10-04).
    const check = judge('intake_many', 'read', [
      run('표', { parsed: 0, imported: 1 }),
      run('곡선', { parsed: 1 }),
    ])
    expect(check).toMatchObject({ ok: true })
  })

  it('처리 단계는 곡선이 있는 것만 센다', () => {
    // 안 읽힌 시험까지 「처리 전」 으로 세우면 **같은 시험을 두 단계가 동시에 가리킨다.**
    // 표로 입력한 시험은 처리할 곡선이 없다.
    const check = judge('process_many', 'process', [
      run('오늘-1', { parsed: 1, results: 1 }),
      run('안읽힘', { parsed: 0, results: 0 }),
      run('표', { imported: 1, results: 0 }),
    ])
    expect(check).toMatchObject({ ok: true })
    expect(names(check)).toEqual([])
  })

  it('처리 안 된 것의 이름을 댄다', () => {
    const check = judge('process_many', 'process', [
      run('오늘-1', { parsed: 1, results: 1 }),
      run('오늘-2', { parsed: 1, results: 0 }),
    ])
    expect(names(check)).toEqual(['오늘-2'])
  })

  it('채택 단계는 처리된 것만 센다 — 두 업무가 같은 판정이다', () => {
    // 처리 결과가 없으면 **채택할 것 자체가 없다.**
    for (const flow of ['process_many', 'adopt_many']) {
      const check = judge(flow, 'adopt', [
        run('오늘-1', { parsed: 1, results: 1, adopted: 1 }),
        run('오늘-2', { parsed: 1, results: 2, adopted: 0 }),
        run('처리전', { parsed: 1, results: 0, adopted: 0 }),
      ])
      expect(check, flow).toMatchObject({ ok: false })
      expect(names(check), flow).toEqual(['오늘-2'])
    }
  })

  it('채택하러 담았는데 결과가 없는 것은 처리 업무로 보낸다', () => {
    const check = judge('adopt_many', 'pick', [
      run('결과있음', { results: 1 }),
      run('결과없음', { results: 0 }),
    ])
    expect(check!.ok).toBe(true)
    expect(names(check)).toEqual(['결과없음'])
    expect(check!.say).toContain('한번에 처리하기')
  })

  it('사라진 줄은 세지 않는다', () => {
    const check = judge('process_many', 'read', [
      run('오늘-1', { parsed: 1 }),
      item({ label: '사라졌습니다', missing: true, facts: {} }),
    ])
    expect(check).toMatchObject({ ok: true })
  })

  it('담은 시험이 없으면 침묵한다', () => {
    expect(judge('process_many', 'process', [])).toBeNull()
    expect(judge('adopt_many', 'adopt', [])).toBeNull()
  })
})

describe('물성 카드 하나 만들기', () => {
  const material = (label: string, cards = 0, published = 0) =>
    item({ kind: 'material', label, material_id: label, facts: { cards, published_cards: published } })

  it('재료를 하나 고르면 됐다고 한다', () => {
    expect(judge('card_one', 'material', [material('EPDM-70')])).toMatchObject({ ok: true })
    expect(judge('card_one', 'material', [])).toMatchObject({ ok: false })
  })

  it('여럿이면 첫 재료로 한다고 말하고, 묶음 업무를 권한다', () => {
    const check = judge('card_one', 'material', [material('EPDM-70'), material('PP-GF30')])
    expect(check!.say).toContain('EPDM-70')
    expect(check!.say).toContain('한 묶음으로 내보내기')
  })

  it('옛 점탄성 작업은 담은 시험의 재료로 한다', () => {
    // 그 작업은 시험을 담았다 — 재료를 다시 고르게 하지 않는다.
    const check = judge('card_one', 'material', [item({ material_id: 'm1', facts: {} })])
    expect(check).toMatchObject({ ok: true })
  })

  it('카드가 생기면 끝나고, 초안이면 확정할 자리를 말한다', () => {
    expect(judge('card_one', 'make', [material('EPDM-70', 0)])).toMatchObject({ ok: false })
    const check = judge('card_one', 'make', [material('EPDM-70', 2, 1)])
    expect(check).toMatchObject({ ok: true })
    expect(check!.say).toContain('1장이 초안')
    expect(check!.say).toContain('카드 확정 전 검토하기')
  })
})

describe('카드 확정 전 검토 — 근거의 두께', () => {
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

  it('경고는 진짜 경고만 센다', () => {
    // 출처 설명까지 세던 동안에는 카드 42장이 전부 경고 카드였다(2026-10-04) — 서버가 이제
    // 경고만 센다(`warnings`). 화면은 그 숫자만 본다.
    const check = judge('review_cards', 'read', [
      card('점탄성', { samples: 4, warnings: 2 }),
      card('인장', { samples: 4, warnings: 0 }),
    ])
    expect(check!.say).toContain('1장에 경고')
    expect(names(check)).toEqual(['점탄성'])
  })

  it('코멘트가 붙은 카드도 짚어 준다', () => {
    // 근거 시험이 다른 재료로 옮겨졌다는 말이 거기 붙는다.
    const check = judge('review_cards', 'read', [card('인장', { samples: 4, remarks: 1 })])
    expect(check!.say).toContain('코멘트')
    expect(names(check)).toEqual(['인장'])
  })

  it('둘 다인 카드를 두 번 세지 않는다', () => {
    const check = judge('review_cards', 'read', [card('점탄성', { samples: 1, warnings: 1 })])
    expect(names(check)).toEqual(['점탄성'])
  })

  it('사용 중지는 초안으로 세지 않는다', () => {
    // **쓰지 말라는 카드를 확정하라고 재촉하지 않는다.**
    const check = judge('review_cards', 'decide', [
      card('옛것', { published: 0, deprecated: 1 }),
      card('새것', { published: 0 }),
    ])
    expect(names(check)).toEqual(['새것'])
    const pick = judge('review_cards', 'pick', [card('옛것', { deprecated: 1 })])
    expect(pick!.say).toContain('사용 중지')
  })

  it('확정하러 갈 자리를 준다 — 카드 목록에는 그 단추가 없다', () => {
    // **막다른 길을 만들지 않는다.** 확정은 재료 화면의 「CAE 카드」 탭에서 누른다.
    const check = judge('review_cards', 'decide', [
      item({ kind: 'card', label: '인장 TD', material_id: 'm7', facts: { published: 0 } }),
    ])
    expect(check!.go).toMatchObject({ href: '/materials/m7?tab=cards' })
  })

  it('막지는 않는다 — 읽었는지는 화면이 알 수 없다', () => {
    const check = judge('review_cards', 'read', [card('인장 TD', { samples: 1 })])
    expect(check!.ok).toBe(true)
  })
})

describe('여러 카드를 한 묶음으로 — 무엇이 비었나', () => {
  const material = (label: string, cards: number, published = 0) =>
    item({ kind: 'material', label, material_id: label, facts: { cards, published_cards: published } })

  it('카드가 없는 재료의 이름을 대고, 카드 만들기 업무를 말한다', () => {
    const check = judge('bundle_export', 'survey', [material('EPDM-70', 2, 2), material('PP-GF30', 0)])
    expect(check).toMatchObject({ ok: false })
    expect(check!.say).toContain('1건에 카드가 없습니다')
    expect(check!.say).toContain('물성 카드 하나 만들기')
    expect(names(check)).toEqual(['PP-GF30'])
  })

  it('초안뿐인 재료는 따로 말한다', () => {
    // 만들 것이 아니라 **확정할 것**이다 — 같은 말로 세면 할 일이 뒤섞인다.
    const check = judge('bundle_export', 'survey', [material('EPDM-70', 2, 2), material('PP-GF30', 1, 0)])
    expect(check!.say).toContain('초안뿐입니다')
    expect(check!.ok).toBe(true)
  })

  it('재료는 셋인데 카드가 한 재료 것뿐이면 짚어 준다', () => {
    // **담았다는 사실만으로 「다 골랐다」 고 하면 누락이 안 보인다.**
    const check = judge('bundle_export', 'collect', [
      item({ kind: 'material', label: 'EPDM-70', material_id: 'm1', facts: { cards: 1 } }),
      item({ kind: 'material', label: 'PP-GF30', material_id: 'm2', facts: { cards: 1 } }),
      item({ kind: 'card', label: '점탄성', material_id: 'm1', facts: { published: 1 } }),
    ])
    expect(check).toMatchObject({ ok: false })
    expect(names(check)).toEqual(['PP-GF30'])
  })

  it('초안이 섞인 묶음은 말해 주되 막지 않는다', () => {
    const check = judge('bundle_export', 'export', [
      item({ kind: 'card', label: '인장 MD', facts: { published: 1 } }),
      item({ kind: 'card', label: '점탄성', facts: { published: 0 } }),
    ])
    expect(check).toMatchObject({ ok: false })
    expect(names(check)).toEqual(['점탄성'])
    expect(check!.say).toContain('내보낼 수는 있지만')
  })

  it('사용 중지 카드가 섞이면 빼라고 한다', () => {
    const check = judge('bundle_export', 'export', [
      item({ kind: 'card', label: '옛것', facts: { published: 0, deprecated: 1 } }),
    ])
    expect(check!.say).toContain('사용 중지')
    expect(check!.say).not.toContain('초안')
    expect(names(check)).toEqual(['옛것'])
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
    const check = judge('new_instrument', 'verify', [
      item({ label: '시험-1', facts: { parsed: 1, channels: 0 } }),
    ])
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
