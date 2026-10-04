/**
 * 업무 정의 — **데이터다**(ADR 0024 · 0058).
 *
 * 새 업무가 정의 하나여야 한다. 화면이 목록을 적어 두면 업무를 더할 때 두 곳을 고치게
 * 되고, 그때 한 곳을 빠뜨린다 — 형식 프로파일·덱 정의·레지스트리에서 이 저장소가 반복해
 * 내린 판단이다.
 *
 * ## 사례가 아니라 업무다 (2026-10-04, ADR 0058)
 *
 * 처음 여섯은 「DMA 한 벌로 점탄성 계수 내기」 처럼 **사례**였다. 기능이 늘 때마다 사례가
 * 하나씩 붙어야 했고, 실제로는 한 달 동안 아무것도 안 붙었다 — 그 사이 늘어난 기능 서른여
 * 개가 워크벤치에서 안 보였다. 지금은 **하는 일의 단위**다: 「시험 데이터 한번에 처리하기」 ·
 * 「물성 카드 하나 만들기」. 비슷한 업무는 묶음(`group`)으로 모여 홈에 선다.
 *
 * ## 정의는 프론트에 산다
 *
 * 단계는 결국 화면이다. 서버가 그것을 알면 화면을 고칠 때마다 서버도 고쳐야 하고, 그때
 * 마이그레이션이 붙는다(ADR 0025). 서버는 `workflow_key` 문자열과 진행(`steps`)만 담아
 * 둔다 — 그래서 이름을 바꿀 때는 옛 이름을 별칭으로 남긴다(`LEGACY_KEYS`).
 *
 * ## 단계는 진행자다 — 전용 화면도 도메인 모듈의 것이다
 *
 * 단계는 이미 있는 화면으로 데려가거나(`where`), **도메인 모듈의 화면을 그 자리에 끼운다**
 * (`view`). 끼우는 화면은 처리 · 시험 · 카드 모듈에 살고, 워크벤치는 담긴 것을 건네기만
 * 한다(`views.tsx`). 판정(`judge`)도 담긴 것의 사실(서버가 센 숫자)로만 한다 — 여기서 새로
 * 쓰면 도메인이 바뀌어도 말없이 옛 규칙을 쓰게 되고, 그러면 「다음」 이 열려 있는데 실제로는
 * 안 끝난 상태가 된다(ADR 0024 「지켜야 유지되는 것」).
 */

import type { BasketItem } from '@/shared/api/basket'
import { withJosa } from '@/shared/korean'

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

/**
 * 담으러 가는 자리.
 *
 * **`?collect=` 를 달고 간다.** 그 목록 화면은 평소에는 담기 창을 안 띄우고
 * 단추만 두는데(줄마다 뜨면 목록을 훑는 일을 방해한다), **워크벤치에서 담으러
 * 온 사람은 그 단추를 또 찾을 이유가 없다** — 고르는 순간 창이 뜬다.
 */
export const COLLECT_AT: Record<ItemKind, string> = {
  test_run: '/tests?collect=test_run',
  material: '/materials?collect=material',
  card: '/cards?collect=card',
}

/** 담긴 것으로 판정한다. `null` 은 「이 단계는 판정하지 않는다」 — 모르면 침묵한다. */
export type StepJudge = (items: BasketItem[]) => StepCheck | null

/**
 * 단계에 끼우는 **전용 화면**(ADR 0058). 화면은 도메인 모듈에 살고 `views.tsx` 가
 * 담긴 것을 건넨다 — 여기는 어느 화면인지와 그 화면의 처음 거르기만 적는다.
 *
 *     runs        시험 목록에서 바로 골라 담기(처리 상태로 처음 거른다)
 *     batch       담은 시험에 같은 처리 단계 — 미리보기 전/후 · 저장 · 되돌리기
 *     adopt       채택 검토대 — 결과를 겹쳐 보고 견주어 한 번에 채택
 *     material    카드를 만들 재료 하나 고르기
 *     readiness   그 재료로 무엇이 나오나 — 비었으면 어디서 채우나
 *     cards       그 재료의 CAE 카드 패널(탄소성 · 점탄성 · 열 · 기본 정보)
 *     bom         부품표(BOM) 혼합 덱
 *     bundle      담은 카드를 한 묶음으로 내보내기
 */
export type StepView =
  | { kind: 'runs'; processing?: 'none' | 'results' | 'adopted' }
  | { kind: 'batch' }
  | { kind: 'adopt' }
  | { kind: 'material' }
  | { kind: 'readiness' }
  | { kind: 'cards' }
  | { kind: 'bom' }
  | { kind: 'bundle' }

export interface WorkflowStep {
  key: string
  title: string
  /** 이 단계에서 무엇을 하나. 한 줄로. */
  what: string
  /** 이 단계가 담는 것. 없으면 담지 않는 단계(고르기만·내보내기만). */
  collects?: ItemKind
  /** 어디서 하나. **담는 단추도 거기 있다** — 전용 화면이 없는 단계의 길이다. */
  where?: string
  /** 그 자리의 이름. 「그 화면으로」 만 적으면 어디로 가는지 모른 채 누른다. */
  whereLabel?: string
  /** 이 단계에 끼우는 전용 화면. 있으면 화면을 오가지 않고 여기서 한다. */
  view?: StepView
  /**
   * 이 단계가 끝났나. **담긴 것의 사실(`facts`)로만 본다** — 서버가 세어 준 숫자다
   * (`ItemOut.facts`). 여기서 도메인 API 를 따로 부르면 워크벤치가 남의 도메인을
   * 알게 되고, 그 방향은 되돌리기 어렵다.
   */
  judge?: StepJudge
}

/** 업무의 묶음 — 홈에서 이 차례로 선다. 새 묶음은 여기 한 줄이다. */
export type WorkflowGroup = 'tests' | 'cards' | 'decks' | 'setup'

export const WORKFLOW_GROUPS: { key: WorkflowGroup; title: string; what: string }[] = [
  {
    key: 'tests',
    title: '시험 데이터',
    what: '여러 시험을 한 번에 올리고 · 처리하고 · 채택합니다.',
  },
  {
    key: 'cards',
    title: '물성 카드',
    what: '재료의 값으로 해석용 카드를 만들고, 근거를 보고 확정합니다.',
  },
  {
    key: 'decks',
    title: '해석 덱',
    what: '여러 재료의 카드를 덱 한 파일 · 한 묶음으로 냅니다.',
  },
  {
    key: 'setup',
    title: '장비 · 형식',
    what: '새 장비가 낸 파일을 읽게 만듭니다.',
  },
]

export interface Workflow {
  key: string
  group: WorkflowGroup
  title: string
  /** 언제 쓰나. 고르는 자리에서 이것만 읽고 고를 수 있어야 한다. */
  when: string
  /** 얼마나 자주 하는 일인가. 묶음 안의 차례를 이걸로 정한다. */
  cadence: '매일' | '자주' | '프로젝트마다' | '이따금'
  steps: WorkflowStep[]
  /**
   * 끝나면 이어 할 업무. 마지막 단계에 「담은 것 그대로 ○○ 시작」 이 선다 — 올린 시험을
   * 처리로 넘길 때 다시 고르게 하면 고른 것이 그 자리에서 버려진다.
   */
  next?: string
  /**
   * 옛 단계 이름 → 지금 단계. 업무를 고쳐 단계가 합쳐졌을 때 **이어 하던 작업이 1단계로
   * 되돌아가지 않게** 한다. 여기 없는 옛 이름은 「단계 구성이 바뀌었습니다」 로 말한다.
   */
  formerly?: Record<string, string>
}

/**
 * 옛 업무 이름 → 지금 이름. **서버에 이미 그 이름으로 적힌 작업이 있다**(ADR 0025 —
 * 정의는 화면에 있고 서버는 문자열만 든다). 지우면 그 작업들이 「모르는 워크플로」 로 선다.
 */
export const LEGACY_KEYS: Record<string, string> = {
  daily_intake: 'process_many',
  viscoelastic_set: 'card_one',
  analysis_deck: 'bundle_export',
}

/** 살아 있는 것만 본다. **사라진 줄은 세지 않는다** — 그것은 이미 그 줄이 말한다. */
function live(items: BasketItem[], kind: ItemKind): BasketItem[] {
  return items.filter((one) => one.kind === kind && !one.missing)
}

function fact(item: BasketItem, key: string): number {
  return (item.facts as Record<string, number> | undefined)?.[key] ?? 0
}

/**
 * 판정이 읽는 사실의 이름. **서버의 `FACT_KEYS` 와 같아야 한다** — 어긋나면 없는 키를
 * 읽어 0을 얻고, 0은 「아직 안 했다」 로 읽혀 영원히 안 끝나는 단계가 된다.
 * `workflows.test.ts` 가 이 표와 판정이 실제로 읽는 이름을 대 본다.
 */
export const FACTS_READ: Record<ItemKind, string[]> = {
  test_run: [
    'master_curves',
    'prony_fits',
    'cards',
    'adopted',
    'parsed',
    'imported',
    'results',
    'channels',
    'temperature_steps',
  ],
  material: ['cards', 'published_cards'],
  card: ['published', 'deprecated', 'samples', 'warnings', 'remarks'],
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

/**
 * 담긴 것이 딸린 재료의 **그 탭**.
 *
 * 탭까지 적는 이유: 재료 화면은 탭이 셋이고(시료·시편 / 물성 / CAE 카드) 주소에 안
 * 담으면 늘 첫 탭이 열린다. 「그 재료의 CAE 카드로」 라고 해 놓고 시료 목록에
 * 떨어뜨리면 그 안내는 없느니만 못하다.
 */
function materialHref(items: BasketItem[], tab: 'properties' | 'cards'): string | null {
  const owner = items.find((one) => !one.missing && one.material_id)?.material_id
  return owner ? `/materials/${owner}?tab=${tab}` : null
}

/**
 * **읽을 수 있는 시험** — 읽혔거나 표로 입력한 것.
 *
 * 표로 입력한 시험은 읽을 파일이 없다(값만 있다). 「안 읽힘」 으로 세면 할 수 없는 일을
 * 재촉하게 된다 — 2026-10-04 점검에서 그렇게 서 있었다.
 */
const readable = (one: BasketItem) => fact(one, 'parsed') > 0 || fact(one, 'imported') > 0

/** 읽기 확인 — 등록 · 처리 두 업무가 같은 말을 한다. */
function readJudge(items: BasketItem[]): StepCheck | null {
  const runs = live(items, 'test_run')
  if (runs.length === 0) return null
  // **실패한 것을 먼저 골라낸다.** 안 읽힌 시험을 그대로 두고 레시피를
  // 걸면, 「처리했는데 값이 안 나온다」 로 한 바퀴를 더 돈다.
  const failed = pendingOf(runs, readable)
  return {
    ok: failed.length === 0,
    say:
      failed.length === 0
        ? `담은 ${runs.length}건이 모두 읽혔습니다.`
        : `${failed.length}건이 아직 안 읽혔거나 실패했습니다 — 열이 안 맞거나 형식이 다르면 읽기가 실패합니다. 그 시험은 빼거나, 형식 정의를 고친 뒤 다시 읽히세요.`,
    blocking: failed,
    go: failed.length > 0 ? { href: '/settings/formats', label: '형식 정의로' } : undefined,
  }
}

/** 처리 — 읽힌 것 가운데 결과가 없는 것. */
function processJudge(items: BasketItem[]): StepCheck | null {
  // **곡선이 있는 것만 센다.** 안 읽힌 시험은 앞 단계가 이미 말했고, 표로 입력한
  // 시험은 처리할 곡선이 없다.
  const runs = live(items, 'test_run').filter((one) => fact(one, 'parsed') > 0)
  if (runs.length === 0) return null
  const left = pendingOf(runs, (one) => fact(one, 'results') > 0)
  return {
    ok: left.length === 0,
    say:
      left.length === 0
        ? `읽힌 ${runs.length}건이 모두 처리됐습니다.`
        : `${left.length}건이 아직 처리 전입니다.`,
    blocking: left,
  }
}

/** 채택 — 처리된 것 가운데 아직 채택 안 한 것. */
function adoptJudge(items: BasketItem[]): StepCheck | null {
  // **처리된 것만 센다.** 처리 결과가 없으면 채택할 것 자체가 없다 —
  // 그 시험을 「채택 안 했다」 로 세우면 앞 단계와 같은 말을 두 번 하게 되고,
  // 사람은 어느 쪽을 봐야 하는지 모른다.
  const runs = live(items, 'test_run').filter((one) => fact(one, 'results') > 0)
  if (runs.length === 0) return null
  const left = pendingOf(runs, (one) => fact(one, 'adopted') > 0)
  return {
    ok: left.length === 0,
    say:
      left.length === 0
        ? `처리된 ${runs.length}건 모두 채택했습니다.`
        : `${left.length}건이 아직 채택 전입니다.`,
    blocking: left,
  }
}

/**
 * 업무 목록(ADR 0058). **여기 있는 것이 곧 홈의 목록**이다.
 *
 * 단계는 「어디서 하나」(`where`)로 데려가거나 전용 화면(`view`)을 끼우고, 「끝났나」
 * (`judge`)를 담긴 것의 사실로 말한다. 판정을 안 붙인 단계는 침묵한다 — **모르면서
 * 됐다고 하지 않는다.**
 */
export const WORKFLOWS: Workflow[] = [
  // --- 시험 데이터 -----------------------------------------------------------
  {
    key: 'intake_many',
    group: 'tests',
    title: '시험 데이터 한번에 등록하기',
    when: '파일 여럿을 한 번에 올리고, 다 읽혔는지 확인합니다. 안 읽힌 것은 형식 정의에서 고칩니다.',
    cadence: '매일',
    next: 'process_many',
    steps: [
      {
        key: 'upload',
        title: '파일 올리기',
        what: '여러 파일을 한 번에 올립니다 — 파일 이름에서 재료 · 시편을 읽어 줄을 채웁니다. 커넥터가 물어 온 파일은 시편에 붙이면 시험 목록에 섭니다(ADR 0021).',
        where: '/tests/upload',
        whereLabel: '일괄 등록 화면으로',
      },
      {
        key: 'pick',
        title: '올린 것 담기',
        what: '방금 올린 시험을 담습니다 — 아래 목록은 최근에 올린 것이 위에 섭니다.',
        collects: 'test_run',
        view: { kind: 'runs' },
        judge: (items) => collected(items, 'test_run', '시험'),
      },
      {
        key: 'read',
        title: '읽혔나 보기',
        what: '열이 안 맞거나 형식이 다르면 읽기가 실패합니다 — 그 시험은 뒤 단계가 다 헛돕니다.',
        judge: readJudge,
      },
    ],
  },
  {
    key: 'process_many',
    group: 'tests',
    title: '시험 데이터 한번에 처리하기',
    when: '같은 처리 단계를 여러 시험에 겁니다 — 저장 전에 전/후를 견주고, 저장한 뒤에는 그 자리에서 겹쳐 보고 채택까지.',
    cadence: '매일',
    steps: [
      {
        key: 'pick',
        title: '처리할 시험 담기',
        what: '아직 처리 안 한 시험이 먼저 섭니다. 재료 · 시험 종류로 좁혀 골라 담습니다.',
        collects: 'test_run',
        view: { kind: 'runs', processing: 'none' },
        judge: (items) => collected(items, 'test_run', '시험'),
      },
      {
        key: 'read',
        title: '읽혔나 보기',
        what: '안 읽힌 시험은 처리해도 값이 안 나옵니다 — 먼저 빼거나 형식을 고칩니다.',
        judge: readJudge,
      },
      {
        key: 'process',
        title: '한 번에 처리',
        what: '레시피(또는 시험 하나에서 맞춘 단계)를 담은 시험 전부에 미리 돌려 전/후를 견준 뒤 저장합니다. 잘못 걸었으면 되돌립니다.',
        view: { kind: 'batch' },
        judge: processJudge,
      },
      {
        key: 'adopt',
        title: '한 번에 채택',
        what: '시험마다 결과 하나를 골라 겹쳐 보고, 튀는 것을 확인한 뒤 한 번에 채택합니다 — 채택한 값이 재료 통계로 갑니다.',
        view: { kind: 'adopt' },
        judge: adoptJudge,
      },
    ],
  },
  {
    key: 'adopt_many',
    group: 'tests',
    title: '계산된 시험 데이터 한번에 채택하기',
    when: '처리는 됐는데 채택 안 한 시험을 모아, 처리 전/후 곡선과 값을 견주며 한 번에 채택합니다.',
    cadence: '자주',
    steps: [
      {
        key: 'pick',
        title: '채택할 시험 담기',
        what: '결과는 있는데 채택 안 한 시험이 먼저 섭니다. 이미 채택한 것도 다시 견줄 수 있습니다.',
        collects: 'test_run',
        view: { kind: 'runs', processing: 'results' },
        judge: (items) => {
          const check = collected(items, 'test_run', '시험')
          const bare = live(items, 'test_run').filter((one) => fact(one, 'results') === 0)
          if (!check.ok || bare.length === 0) return check
          // 결과가 없으면 채택할 것이 없다 — **처리하기 업무로 보낼 것**이다.
          return {
            ok: true,
            say: `${check.say} ${bare.length}건은 처리 결과가 없어 채택할 것이 없습니다 — 「시험 데이터 한번에 처리하기」 의 일입니다.`,
            blocking: bare,
          }
        },
      },
      {
        key: 'adopt',
        title: '견주어 채택',
        what: '시험마다 결과 하나를 골라 겹쳐 보고, 중앙값에서 멀리 간 것을 확인한 뒤 한 번에 채택합니다. 되돌리기는 이전 채택으로 돌려놓습니다.',
        view: { kind: 'adopt' },
        judge: adoptJudge,
      },
    ],
  },

  // --- 물성 카드 -------------------------------------------------------------
  {
    key: 'card_one',
    group: 'cards',
    title: '물성 카드 하나 만들기',
    when: '재료 하나를 골라, 그 재료로 무엇이 나오는지 보고 해석용 카드(탄소성 · 점탄성 · 열 · 기본 정보)를 그 자리에서 만듭니다.',
    cadence: '자주',
    // 「DMA 한 벌로 점탄성 계수 내기」 의 단계 — 그 작업은 이제 이 업무로 열린다.
    formerly: { pick: 'material', master: 'ready', fit: 'make', card: 'make' },
    steps: [
      {
        key: 'material',
        title: '재료 고르기',
        what: '카드를 만들 재료 하나를 고릅니다. 시험을 담아 둔 작업이면 그 시험의 재료를 바로 씁니다.',
        collects: 'material',
        view: { kind: 'material' },
        judge: (items) => {
          const found = live(items, 'material')
          if (found.length > 1) {
            return {
              ok: true,
              say: `재료를 ${found.length}건 담았습니다 — 이 업무는 첫 재료(${found[0].label})로 합니다. 여럿이면 「여러 카드를 한 묶음으로 내보내기」 가 맞습니다.`,
            }
          }
          if (found.length === 1) return { ok: true, say: `${found[0].label} 로 만듭니다.` }
          // 옛 점탄성 작업은 시험을 담았다 — 그 시험의 재료가 있으면 그것으로 한다.
          if (materialHref(items, 'cards')) {
            return { ok: true, say: '담은 시험의 재료로 만듭니다.' }
          }
          return { ok: false, say: '아직 고른 재료가 없습니다.' }
        },
      },
      {
        key: 'ready',
        title: '무엇이 나오나',
        what: '이 재료의 측정 · 선언 값으로 어떤 카드가 나오는지, 비었으면 어디서 채우는지 봅니다.',
        view: { kind: 'readiness' },
      },
      {
        key: 'make',
        title: '카드 만들기',
        what: '탄소성 · 점탄성(글로벌 피팅) · 열 · 재료 기본 정보 카드를 그 재료의 CAE 카드 패널에서 그대로 만듭니다.',
        view: { kind: 'cards' },
        judge: (items) => {
          const found = live(items, 'material')
          if (found.length === 0) return null
          const cards = fact(found[0], 'cards')
          const published = fact(found[0], 'published_cards')
          if (cards === 0) return { ok: false, say: '아직 이 재료의 카드가 없습니다.' }
          return {
            ok: true,
            say:
              published < cards
                ? `카드 ${cards}장 중 ${cards - published}장이 초안입니다 — 확정은 「카드 확정 전 검토하기」 에서 근거를 보고 합니다.`
                : `카드 ${cards}장이 모두 확정입니다.`,
          }
        },
      },
    ],
  },
  {
    key: 'review_cards',
    group: 'cards',
    title: '카드 확정 전 검토하기',
    when: '초안 카드의 근거(표본 수 · 경고 · 코멘트)를 보고 확정하거나 반려합니다.',
    cadence: '이따금',
    steps: [
      {
        key: 'pick',
        title: '초안 담기',
        what: '확정 대기 카드를 담습니다.',
        collects: 'card',
        where: '/cards',
        whereLabel: '카드 목록으로',
        judge: (items) => {
          const check = collected(items, 'card', '카드')
          // **사용 중지는 확정할 것이 아니다** — 담겨 있으면 뒤 단계가 그것을 초안처럼 센다.
          const retired = live(items, 'card').filter((one) => fact(one, 'deprecated') > 0)
          if (retired.length === 0) return check
          return {
            ok: check.ok,
            say: `${check.say} ${retired.length}장은 사용 중지라 확정할 것이 아닙니다 — 빼도 됩니다.`,
            blocking: retired,
          }
        },
      },
      {
        key: 'read',
        title: '근거 보기',
        what: '어느 시험에서 나왔는지, 표본이 몇인지, 경고 · 코멘트가 붙었는지 봅니다 — 재료 화면의 「CAE 카드」 탭에서.',
        where: '/cards',
        whereLabel: '카드 목록으로',
        judge: (items) => {
          const cards = live(items, 'card').filter((one) => fact(one, 'deprecated') === 0)
          if (cards.length === 0) return null
          // **표본 하나로 만든 카드는 만들 수는 있어도 그대로 확정하면 안 된다.**
          // 확정은 「이 값을 해석에 쓴다」 는 선언이라, 근거의 두께가 곧 판단 재료다.
          const thin = cards.filter((one) => fact(one, 'samples') === 1)
          // **경고만 센다**(서버의 `shared/card_notes`) — 출처 설명까지 세던 동안에는 모든
          // 카드에 「경고」 가 붙어 아무도 안 읽었다(2026-10-04).
          const warned = cards.filter((one) => fact(one, 'warnings') > 0)
          // 코멘트 — 근거 시험이 다른 재료로 옮겨졌다는 말이 여기 붙는다.
          const remarked = cards.filter((one) => fact(one, 'remarks') > 0)
          const say: string[] = []
          if (thin.length > 0) say.push(`${thin.length}장은 표본이 하나입니다.`)
          if (warned.length > 0) say.push(`${warned.length}장에 경고가 붙어 있습니다.`)
          if (remarked.length > 0) say.push(`${remarked.length}장에 코멘트가 있습니다.`)
          const href = materialHref(cards, 'cards')
          return {
            // 읽어 보라는 안내이지 막는 것이 아니다 — 읽었는지는 화면이 알 수 없다.
            ok: true,
            say: say.length > 0 ? say.join(' ') : `카드 ${cards.length}장의 근거를 보세요.`,
            blocking: [...new Set([...thin, ...warned, ...remarked])],
            // **근거는 재료 화면의 물성 패널에 있다.** 카드 목록은 내보내는 자리이지
            // 근거를 펴 보는 자리가 아니다.
            go: href ? { href, label: '그 재료의 CAE 카드로' } : undefined,
          }
        },
      },
      {
        key: 'decide',
        title: '확정 또는 반려',
        what: '재료 화면의 「CAE 카드」 탭에서 자료 관리자가 누릅니다 — 워크벤치가 대신 누르지 않습니다.',
        judge: (items) => {
          const cards = live(items, 'card').filter((one) => fact(one, 'deprecated') === 0)
          if (cards.length === 0) return null
          const left = pendingOf(cards, (one) => fact(one, 'published') > 0)
          const href = materialHref(left.length > 0 ? left : cards, 'cards')
          return {
            ok: left.length === 0,
            say:
              left.length === 0
                ? `담은 ${cards.length}건이 모두 확정됐습니다.`
                : `${left.length}건이 아직 초안입니다.`,
            blocking: left,
            // **「확정」 단추는 카드 목록에 없다.** 거기로 보내면 막다른 길이다 —
            // 눌러야 할 것이 없는 화면에 도착하면 사람은 기능이 없다고 결론 낸다.
            go: href ? { href, label: '그 재료의 CAE 카드로' } : undefined,
          }
        },
      },
    ],
  },

  // --- 해석 덱 ---------------------------------------------------------------
  {
    key: 'bom_deck',
    group: 'decks',
    title: '부품표(BOM)로 여러 카드를 한 덱에',
    when: '부품표를 붙여넣어 해석 덱 한 파일을 만듭니다 — 사내 확정 카드(실측)가 우선이고, 없는 부품은 문헌 물성으로 메꿉니다.',
    cadence: '프로젝트마다',
    // 붙여넣기 · 매칭 · 내보내기가 한 화면이라 단계를 하나로 합쳤다.
    formerly: { paste: 'deck', match: 'deck', export: 'deck' },
    steps: [
      {
        key: 'deck',
        title: '부품표로 덱 만들기',
        what: 'MID · 재료명 줄(엑셀 표 통째도 됩니다)을 붙여넣고 매칭을 돌립니다. 부품마다 사내 재료(확정 카드 유무)와 문헌 재료를 확인하고, 단위계를 골라 한 파일로 받습니다. 지난번에 고른 매칭은 자동으로 맞습니다.',
        view: { kind: 'bom' },
      },
    ],
  },
  {
    key: 'bundle_export',
    group: 'decks',
    title: '여러 카드를 한 묶음으로 내보내기',
    when: '제품군에 쓰이는 재료를 모아 무엇이 비었는지 보고, 카드를 manifest · 체크섬과 함께 한 묶음으로 냅니다.',
    cadence: '프로젝트마다',
    steps: [
      {
        key: 'scope',
        title: '무엇에 쓰나',
        what: '적용 제품·파트로 재료를 찾아 담습니다.',
        collects: 'material',
        where: '/materials',
        whereLabel: '재료 목록으로',
        judge: (items) => collected(items, 'material', '재료'),
      },
      {
        key: 'survey',
        title: '무엇이 있나',
        what: '재료마다 카드가 있는지, 초안인지 확정인지 봅니다.',
        // **이 업무의 산출물이 이 판정이다** — 「해석에 넘기기 전에 뭐가 비었나」.
        // 지금까지는 재료를 하나씩 열어 봐야 알 수 있었다.
        judge: (items) => {
          const found = live(items, 'material')
          if (found.length === 0) return null
          const empty = pendingOf(found, (one) => fact(one, 'cards') > 0)
          const draftOnly = found.filter(
            (one) => fact(one, 'cards') > 0 && fact(one, 'published_cards') === 0
          )
          const say: string[] = []
          if (empty.length > 0)
            say.push(
              `${empty.length}건에 카드가 없습니다 — 「물성 카드 하나 만들기」 로 만들거나, 문헌 물성으로 메꿀 수 있습니다(BOM 혼합 덱).`
            )
          if (draftOnly.length > 0) say.push(`${draftOnly.length}건은 초안뿐입니다.`)
          return {
            ok: empty.length === 0,
            say: say.length > 0 ? say.join(' ') : `담은 재료 ${found.length}건 모두 카드가 있습니다.`,
            // 카드가 아예 없는 것이 먼저다 — 초안뿐인 것은 만들 것이 아니라 확정할 것이다.
            blocking: [...empty, ...draftOnly],
            // 카드 없는 재료의 답이 이제 있다 — 실측이 없으면 문헌 스칼라로(이식 2.5단계).
            go: empty.length > 0 ? { href: '/cards/bom-deck', label: 'BOM 혼합 덱으로' } : undefined,
          }
        },
      },
      {
        key: 'collect',
        title: '카드 담기',
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
        what: 'manifest · 체크섬과 함께 한 번에 받습니다 — 담은 카드가 그대로 여기 섭니다.',
        view: { kind: 'bundle' },
        judge: (items) => {
          const cards = live(items, 'card')
          if (cards.length === 0) return null
          const retired = cards.filter((one) => fact(one, 'deprecated') > 0)
          const draft = pendingOf(
            cards,
            (one) => fact(one, 'published') > 0 || fact(one, 'deprecated') > 0
          )
          const say: string[] = []
          // **사용 중지가 섞였으면 먼저 말한다** — 쓰지 말라는 카드가 해석에 들어간다.
          if (retired.length > 0) say.push(`${retired.length}장이 사용 중지입니다 — 빼세요.`)
          // **막지 않는다.** 초안도 내보내진다 — 다만 해석에 쓰기 전에 알아야 한다.
          if (draft.length > 0)
            say.push(
              `${draft.length}건이 초안입니다. 내보낼 수는 있지만 해석에 쓰기 전에 확정하세요.`
            )
          return {
            ok: retired.length === 0 && draft.length === 0,
            say: say.length > 0 ? say.join(' ') : `담은 카드 ${cards.length}건이 모두 확정입니다.`,
            blocking: [...retired, ...draft],
          }
        },
      },
    ],
  },

  // --- 장비 · 형식 -----------------------------------------------------------
  {
    key: 'new_instrument',
    group: 'setup',
    title: '새 장비 파일 연결',
    when: '새 장비의 출력 파일을 읽게 만들고, 한 벌 올려 확인합니다.',
    cadence: '이따금',
    steps: [
      // 아래 셋은 **정의 편집기 안에서** 이어서 하는 일이다. 처음 만들 때는 새
      // 정의를 여는 것이 첫 걸음이고, 고칠 때는 목록에서 그 정의를 고른다.
      {
        key: 'sample',
        title: '예제 파일',
        what: '한 벌 올려 구조를 읽습니다. 고치는 중이면 목록에서 그 정의를 여세요.',
        where: '/settings/formats/new',
        whereLabel: '새 정의 생성',
      },
      {
        key: 'tables',
        title: '표 선택',
        what: '측정과 처리결과를 가릅니다 — 정의 편집기의 같은 화면에서 이어서.',
        where: '/settings/formats',
        whereLabel: '정의 목록으로',
      },
      {
        key: 'columns',
        title: '열 매핑',
        what: '이 열이 무슨 채널인지 정합니다 — 같은 편집기의 다음 칸입니다.',
        where: '/settings/formats',
        whereLabel: '정의 목록으로',
      },
      {
        key: 'verify',
        title: '한 벌 올려 확인',
        what: '그 정의로 파일을 올려 읽고, 담아서 열이 채널로 잡혔는지 봅니다.',
        collects: 'test_run',
        where: '/tests',
        whereLabel: '시험 목록으로',
        judge: (items) => {
          const runs = live(items, 'test_run')
          if (runs.length === 0) return null
          // **읽혔다고 매핑이 된 것은 아니다.** 열 이름이 하나도 안 맞아도 파일은
          // 읽히고, 표는 비어 있다 — 그 차이를 여기서 본다.
          const blank = pendingOf(runs, (one) => fact(one, 'channels') > 0)
          const unread = pendingOf(runs, (one) => fact(one, 'parsed') > 0)
          if (unread.length > 0) {
            return {
              ok: false,
              say: `${unread.length}건이 안 읽혔습니다 — 표를 고르는 규칙부터 보세요.`,
              blocking: unread,
            }
          }
          return {
            ok: blank.length === 0,
            say:
              blank.length === 0
                ? `채널이 잡혔습니다(${Math.max(...runs.map((one) => fact(one, 'channels')))}개). 이 채널로 열리는 탭과 처리 단계가 정해집니다.`
                : `${blank.length}건에서 채널이 하나도 안 잡혔습니다 — 열 매핑을 보세요.`,
            blocking: blank,
          }
        },
      },
    ],
  },
]

/** 이 이름의 업무. **옛 이름도 받는다**(`LEGACY_KEYS`) — 서버에 그 이름으로 적힌 작업이 있다. */
export function workflowOf(key: string): Workflow | undefined {
  const current = LEGACY_KEYS[key] ?? key
  return WORKFLOWS.find((one) => one.key === current)
}

/** 묶음 안의 업무들 — 자주 하는 것이 먼저다. */
const CADENCE_ORDER: Workflow['cadence'][] = ['매일', '자주', '프로젝트마다', '이따금']

export function workflowsIn(group: WorkflowGroup): Workflow[] {
  return WORKFLOWS.filter((one) => one.group === group).sort(
    (a, b) => CADENCE_ORDER.indexOf(a.cadence) - CADENCE_ORDER.indexOf(b.cadence)
  )
}

/**
 * 전용 화면을 가진 업무인가 — 홈의 배지 「전용 화면」 · 「안내」 를 가른다.
 *
 * **묶음 내보내기 띠는 세지 않는다.** 마지막 단계에 단추 하나를 끼운 것이고 앞 단계는 다른
 * 화면으로 데려가는 안내다 — 「전용 화면」 이라 적으면 여기서 다 끝나는 줄 안다.
 */
export function hasView(flow: Workflow): boolean {
  return flow.steps.some((one) => one.view !== undefined && one.view.kind !== 'bundle')
}

/**
 * 저장된 단계 이름을 지금 단계로. 옛 이름이면 `formerly` 로 옮기고, 모르면 그대로 둔다 —
 * 그때 화면이 「단계 구성이 바뀌었습니다」 를 말한다(조용히 1단계로 옮기지 않는다).
 */
export function stepKeyOf(flow: Workflow, saved: string): string {
  if (flow.steps.some((one) => one.key === saved)) return saved
  return flow.formerly?.[saved] ?? saved
}
