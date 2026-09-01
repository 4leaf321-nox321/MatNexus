/**
 * 워크플로 정의 — **데이터다**(ADR 0024).
 *
 * 새 시나리오가 파일 하나여야 한다. 화면이 목록을 적어 두면 시나리오를 더할 때 두 곳을
 * 고치게 되고, 그때 한 곳을 빠뜨린다 — 형식 프로파일·덱 정의·레지스트리에서 이 저장소가
 * 반복해 내린 판단이다.
 *
 * ## 정의는 프론트에 산다
 *
 * 단계는 결국 화면이다. 서버가 그것을 알면 화면을 고칠 때마다 서버도 고쳐야 하고, 그때
 * 마이그레이션이 붙는다(ADR 0025). 서버는 `workflow_key` 문자열과 진행(`steps`)만 담아
 * 둔다.
 *
 * ## 단계는 **진행자**다
 *
 * 각 단계는 이미 있는 화면·API 로 데려가거나 그것을 끼운다. **도메인을 새로 갖지
 * 않는다.** 판정(`done`)도 되도록 공용 규칙을 쓴다 — 여기서 새로 쓰면 도메인이 바뀌어도
 * 말없이 옛 규칙을 쓰게 되고, 그러면 「다음」 이 열려 있는데 실제로는 안 끝난 상태가
 * 된다(ADR 0024 「지켜야 유지되는 것」).
 */

import type { BasketItem } from '@/shared/api/basket'
import { withJosa } from '@/shared/korean'
import { masterCurveGap } from '@/shared/masterCurveGap'

/** 담을 수 있는 것. 서버의 `ITEM_KINDS` 와 같은 말이다. */
export type ItemKind = 'test_run' | 'material' | 'card'

/**
 * 단계 판정 — **안내지 잠금이 아니다.**
 *
 * 「다음」 은 언제나 눌린다. 워크벤치는 진행자이지 문지기가 아니고(ADR 0024), 사람이
 * 화면 밖에서 이미 한 일을 여기가 못 보는 경우가 늘 있다 — 그때 막으면 도구가 일을
 * 막는 것이 된다. 대신 **무엇이 남았는지 이름으로** 말한다.
 */
export interface StepCheck {
  ok: boolean
  /** 한 줄. 「2건이 아직 안 겹쳤습니다」 처럼 남은 일을 세어 말한다. */
  say: string
  /**
   * 아직인 것들. **이름만이 아니라 그 줄 자체를 준다** — 화면이 링크를 건다.
   * 「2건 남음」 만 읽고 목록을 뒤지게 두면 단계를 읽는 값이 없다.
   */
  blocking?: BasketItem[]
  /** 여기서 할 일이 있는 자리. 담긴 것에 따라 달라지는 주소(그 재료·그 시험). */
  go?: { href: string; label: string }
}

/** 담는 자리 — **담는 단추가 사는 목록 화면**. 종류마다 하나뿐이다. */
export const COLLECT_AT: Record<ItemKind, string> = {
  test_run: '/tests',
  material: '/materials',
  card: '/cards',
}

/** 담긴 것으로 판정한다. `null` 은 「이 단계는 판정하지 않는다」 — 모르면 침묵한다. */
export type StepJudge = (items: BasketItem[]) => StepCheck | null

export interface WorkflowStep {
  key: string
  title: string
  /** 이 단계에서 무엇을 하나. 한 줄로. */
  what: string
  /** 이 단계가 담는 것. 없으면 담지 않는 단계(고르기만·내보내기만). */
  collects?: ItemKind
  /** 어디서 하나. **담는 단추도 거기 있다** — 여기서 담지 않는다. */
  where?: string
  /** 그 자리의 이름. 「그 화면으로」 만 적으면 어디로 가는지 모른 채 누른다. */
  whereLabel?: string
  /**
   * 이 단계가 끝났나. **담긴 것의 사실(`facts`)로만 본다** — 서버가 세어 준 숫자다
   * (`ItemOut.facts`). 여기서 도메인 API 를 따로 부르면 워크벤치가 남의 도메인을
   * 알게 되고, 그 방향은 되돌리기 어렵다.
   */
  judge?: StepJudge
}

export interface Workflow {
  key: string
  title: string
  /** 언제 쓰나. 고르는 자리에서 이것만 읽고 고를 수 있어야 한다. */
  when: string
  /** 얼마나 자주 하는 일인가. 목록의 차례를 이걸로 정한다. */
  cadence: '매일' | '자주' | '프로젝트마다' | '이따금'
  steps: WorkflowStep[]
}

/**
 * 발굴한 시나리오(ADR 0024). **여기 있는 것이 곧 화면의 목록**이다.
 *
 * 단계는 「어디서 하나」(`where`)로 데려가고, 「끝났나」(`judge`)를 담긴 것의 사실로
 * 말한다. 판정을 안 붙인 단계는 침묵한다 — **모르면서 됐다고 하지 않는다.**
 */
/** 살아 있는 것만 본다. **사라진 줄은 세지 않는다** — 그것은 이미 그 줄이 말한다. */
function live(items: BasketItem[], kind: ItemKind): BasketItem[] {
  return items.filter((one) => one.kind === kind && !one.missing)
}

function fact(item: BasketItem, key: string): number {
  return (item.facts as Record<string, number> | undefined)?.[key] ?? 0
}

/** 「담긴 게 있나」 — 여러 단계가 같은 말을 한다. */
function collected(items: BasketItem[], kind: ItemKind, noun: string): StepCheck {
  const found = live(items, kind)
  return {
    ok: found.length > 0,
    say:
      found.length > 0
        ? `${withJosa(noun, '을/를')} ${found.length}건 담았습니다.`
        : `아직 담은 ${withJosa(noun, '이/가')} 없습니다.`,
  }
}

/** 아직 안 한 것들. 세기만 하면 어느 것인지 찾으러 다녀야 한다. */
function pendingOf(rows: BasketItem[], done: (item: BasketItem) => boolean): BasketItem[] {
  return rows.filter((one) => !done(one))
}

/** 담긴 것이 딸린 재료. **글로벌 피팅은 재료 화면에 있다**(ADR 0020). */
function materialHref(items: BasketItem[]): string | null {
  const owner = items.find((one) => !one.missing && one.material_id)?.material_id
  return owner ? `/materials/${owner}` : null
}

export const WORKFLOWS: Workflow[] = [
  {
    key: 'daily_intake',
    title: '오늘 들어온 것 처리하기',
    when: '장비에서 올라온 파일을 시편에 붙이고, 처리해서 채택까지.',
    cadence: '매일',
    steps: [
      {
        key: 'pick',
        title: '파일 고르기',
        what: '커넥터 수집함에서 담습니다.',
        collects: 'test_run',
        where: '/settings/connectors',
        judge: (items) => collected(items, 'test_run', '시험'),
      },
      {
        key: 'attach',
        title: '시편에 붙이기',
        what: '어느 시편의 것인지 사람이 정합니다(ADR 0021).',
        where: '/tests',
        whereLabel: '시험 목록으로',
      },
      {
        key: 'process',
        title: '처리',
        what: '레시피를 걸어 한 번에 돌립니다.',
        where: '/tests',
        whereLabel: '시험 목록으로',
      },
      {
        key: 'adopt',
        title: '채택',
        what: '시험마다 값 하나를 고릅니다 — 그것이 재료 통계로 갑니다.',
        where: '/tests',
        whereLabel: '시험 목록으로',
        judge: (items) => {
          const runs = live(items, 'test_run')
          if (runs.length === 0) return null
          const left = pendingOf(runs, (one) => fact(one, 'adopted') > 0)
          return {
            ok: left.length === 0,
            say:
              left.length === 0
                ? `담은 ${runs.length}건 모두 채택했습니다.`
                : `${left.length}건이 아직 채택 전입니다.`,
            blocking: left,
          }
        },
      },
    ],
  },
  {
    key: 'viscoelastic_set',
    title: 'DMA 한 벌로 점탄성 계수 내기',
    when: '시편 여럿의 DMA 를 겹쳐 Prony 계수 한 벌을 만들고 카드까지.',
    cadence: '자주',
    steps: [
      {
        key: 'pick',
        title: '시험 고르기',
        what: '그 재료의 DMA 시험을 담습니다.',
        collects: 'test_run',
        where: '/tests',
        whereLabel: '시험 목록으로',
        judge: (items) => {
          const runs = live(items, 'test_run')
          if (runs.length === 0) return { ok: false, say: '아직 담은 시험이 없습니다.' }
          // **둘부터가 「한 벌」 이다.** 한 건이면 그 시험 화면에서 하는 편이 빠르다.
          return {
            ok: runs.length >= 2,
            say:
              runs.length >= 2
                ? `시험 ${runs.length}건을 담았습니다.`
                : '아직 1건입니다. 글로벌 피팅은 시편 여럿을 한 번에 적합할 때 값이 있습니다.',
          }
        },
      },
      {
        key: 'master',
        title: '마스터커브 갖추기',
        what: '시험 상세의 「점탄성」 탭에서 겹칩니다. 장비가 만든 것은 가져오면 됩니다.',
        where: '/tests',
        whereLabel: '시험 목록으로',
        judge: (items) => {
          const runs = live(items, 'test_run')
          if (runs.length === 0) return null
          // **세는 규칙은 재료 화면과 한 벌이다**(`shared/masterCurveGap`). 각자 세면
          // 두 화면이 같은 시험을 놓고 다른 말을 한다.
          const gap = masterCurveGap(
            runs.map((one) => ({
              test_type_key: '',
              master_curve_count: fact(one, 'master_curves'),
              temperature_step_count:
                fact(one, 'temperature_steps') < 0 ? null : fact(one, 'temperature_steps'),
            })),
            []
          )
          const left = runs.filter(
            (one) => fact(one, 'master_curves') === 0 && fact(one, 'temperature_steps') >= 2
          )
          const say: string[] = []
          if (gap.pending > 0) say.push(`${gap.pending}건이 아직 안 겹쳤습니다.`)
          // **할 수 없는 일을 남은 일로 세지 않는다** — 온도 한 단은 겹칠 것이 없다.
          if (gap.cannot > 0) {
            say.push(
              `${gap.cannot}건은 온도가 한 단이라 겹칠 수 없습니다 — 장비가 만든 커브를 가져오거나 바구니에서 빼세요.`
            )
          }
          if (gap.unknown > 0) say.push(`${gap.unknown}건은 온도 단 수를 아직 안 세어 봤습니다.`)
          if (gap.ready === 0 && say.length === 0) say.push('담은 시험에 마스터커브가 없습니다.')
          return {
            ok: gap.ready > 0 && gap.pending === 0,
            say: say.length > 0 ? say.join(' ') : `${gap.ready}건에 마스터커브가 있습니다.`,
            blocking: left,
          }
        },
      },
      {
        key: 'fit',
        title: '글로벌 피팅',
        what: '담은 시편을 한 번에 적합해 계수 한 벌을 냅니다.',
        judge: (items) => {
          const runs = live(items, 'test_run')
          if (runs.length === 0) return null
          const fitted = runs.filter((one) => fact(one, 'prony_fits') > 0)
          const href = materialHref(runs)
          return {
            ok: fitted.length > 0,
            say:
              fitted.length > 0
                ? `${fitted.length}건에 맞춘 계수가 있습니다.`
                : '아직 맞춘 계수가 없습니다. 재료 화면의 「묶음」 에서 한 번에 적합합니다.',
            go: href ? { href, label: '이 시험의 재료로' } : undefined,
          }
        },
      },
      {
        key: 'card',
        title: '카드 만들기',
        what: '맞춘 계수에서 물성 카드를 만듭니다 — 시험 상세의 「점탄성」 탭, 또는 재료의 묶음에서.',
        where: '/cards',
        whereLabel: '카드 목록으로',
        // **담아 달라고 하지 않는다.** 카드가 자기 근거로 어느 시험에서 나왔는지를
        // 들고 있어서(`source.test_run_ids`) 서버가 세어 준다. 다 한 일을 바구니에
        // 도로 담아 신고하게 만들면, 담기가 「모아 두는 일」 이 아니라 절차가 된다.
        judge: (items) => {
          const runs = live(items, 'test_run')
          if (runs.length === 0) return null
          const made = runs.reduce((sum, one) => sum + fact(one, 'cards'), 0)
          return {
            ok: made > 0,
            say:
              made > 0
                ? `담은 시험에서 나온 카드가 ${made}장 있습니다.`
                : '아직 이 시험들로 만든 카드가 없습니다.',
          }
        },
      },
    ],
  },
  {
    key: 'analysis_deck',
    title: '해석에 쓸 물성 갖추기',
    when: '제품군에 쓰이는 재료의 카드를 모아 한 덱 묶음으로 내보냅니다.',
    cadence: '프로젝트마다',
    steps: [
      {
        key: 'scope',
        title: '무엇에 쓰나',
        what: '적용 제품·파트로 재료를 찾습니다.',
        collects: 'material',
        where: '/materials',
        whereLabel: '재료 목록으로',
        judge: (items) => collected(items, 'material', '재료'),
      },
      {
        key: 'survey',
        title: '무엇이 있나',
        what: '재료마다 카드가 있는지, 초안인지 확정인지 봅니다.',
        // **이 시나리오의 산출물이 이 판정이다** — 「해석에 넘기기 전에 뭐가 비었나」.
        // 지금까지는 재료를 하나씩 열어 봐야 알 수 있었다.
        judge: (items) => {
          const found = live(items, 'material')
          if (found.length === 0) return null
          const empty = pendingOf(found, (one) => fact(one, 'cards') > 0)
          const draftOnly = found.filter(
            (one) => fact(one, 'cards') > 0 && fact(one, 'published_cards') === 0
          )
          const say: string[] = []
          if (empty.length > 0) say.push(`${empty.length}건에 카드가 없습니다.`)
          if (draftOnly.length > 0) say.push(`${draftOnly.length}건은 초안뿐입니다.`)
          return {
            ok: empty.length === 0,
            say: say.length > 0 ? say.join(' ') : `담은 재료 ${found.length}건 모두 카드가 있습니다.`,
            // 카드가 아예 없는 것이 먼저다 — 초안뿐인 것은 만들 것이 아니라 확정할 것이다.
            blocking: [...empty, ...draftOnly],
          }
        },
      },
      {
        key: 'collect',
        title: '골라 담기',
        what: '해석에 쓸 카드를 담습니다.',
        collects: 'card',
        where: '/cards',
        whereLabel: '카드 목록으로',
        judge: (items) => {
          const check = collected(items, 'card', '카드')
          // 담은 재료 수와 견준다. **재료가 셋인데 카드가 하나면 빠뜨린 것이다** —
          // 카드를 담았다는 사실만으로 「다 골랐다」 고 하면 그 누락이 안 보인다.
          const owners = new Set(live(items, 'card').map((one) => one.material_id))
          const materials = live(items, 'material')
          if (check.ok && materials.length > owners.size) {
            return {
              ok: false,
              say: `${check.say} 담은 재료 ${materials.length}건 중 ${owners.size}건의 카드만 담겼습니다.`,
              blocking: materials.filter((one) => !owners.has(one.material_id)),
            }
          }
          return check
        },
      },
      {
        key: 'export',
        title: '묶음 내보내기',
        what: 'manifest·체크섬과 함께 한 번에 받습니다.',
        where: '/cards',
        judge: (items) => {
          const cards = live(items, 'card')
          if (cards.length === 0) return null
          const draft = pendingOf(cards, (one) => fact(one, 'published') > 0)
          return {
            ok: draft.length === 0,
            // **막지 않는다.** 초안도 내보내진다 — 다만 해석에 쓰기 전에 알아야 한다.
            say:
              draft.length === 0
                ? `담은 카드 ${cards.length}건이 모두 확정입니다.`
                : `${draft.length}건이 초안입니다. 내보낼 수는 있지만 해석에 쓰기 전에 확정하세요.`,
            blocking: draft,
          }
        },
      },
    ],
  },
  {
    key: 'new_instrument',
    title: '새 장비 파일 붙이기',
    when: '새 장비의 출력 파일을 읽게 만듭니다.',
    cadence: '이따금',
    steps: [
      { key: 'sample', title: '예제 파일', what: '한 벌 올려 구조를 읽습니다.', where: '/settings/formats' },
      { key: 'tables', title: '표 고르기', what: '측정과 처리결과를 가릅니다.', where: '/settings/formats' },
      { key: 'columns', title: '열 매핑', what: '이 열이 무슨 채널인지 정합니다.', where: '/settings/formats' },
      { key: 'verify', title: '무엇이 열리나 확인', what: '점탄성 탭·처리 단계가 뜨는지 그 자리에서 봅니다.', where: '/settings/formats' },
    ],
  },
  {
    key: 'review_cards',
    title: '확정 전 근거 훑기',
    when: '초안 카드의 근거를 보고 확정하거나 반려합니다.',
    cadence: '이따금',
    steps: [
      {
        key: 'pick',
        title: '초안 고르기',
        what: '확정 대기 카드를 담습니다.',
        collects: 'card',
        where: '/cards',
        judge: (items) => collected(items, 'card', '카드'),
      },
      {
        key: 'read',
        title: '근거 보기',
        what: '어느 시험·표본 수·경고를 봅니다.',
        where: '/cards',
        whereLabel: '카드 목록으로',
      },
      {
        key: 'decide',
        title: '확정 또는 반려',
        what: '부서 관리자가 누릅니다 — 워크벤치가 대신 누르지 않습니다.',
        where: '/cards',
        whereLabel: '카드 목록으로',
        judge: (items) => {
          const cards = live(items, 'card')
          if (cards.length === 0) return null
          const left = pendingOf(cards, (one) => fact(one, 'published') > 0)
          return {
            ok: left.length === 0,
            say:
              left.length === 0
                ? `담은 ${cards.length}건이 모두 확정됐습니다.`
                : `${left.length}건이 아직 초안입니다.`,
            blocking: left,
          }
        },
      },
    ],
  },
]

export function workflowOf(key: string): Workflow | undefined {
  return WORKFLOWS.find((one) => one.key === key)
}
