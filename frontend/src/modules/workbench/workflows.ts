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

/** 담을 수 있는 것. 서버의 `ITEM_KINDS` 와 같은 말이다. */
export type ItemKind = 'test_run' | 'material' | 'card'

export interface WorkflowStep {
  key: string
  title: string
  /** 이 단계에서 무엇을 하나. 한 줄로. */
  what: string
  /** 이 단계가 담는 것. 없으면 담지 않는 단계(고르기만·내보내기만). */
  collects?: ItemKind
  /** 어디서 하나. 화면 밖에서 해도 되는 일이면 그 자리를 가리킨다. */
  where?: string
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
 * 지금은 얼개까지다 — 각 단계가 실제 화면을 끼우는 것은 시나리오마다 따로 붙인다
 * (계획의 3단계부터). 그때까지도 이 목록은 「무엇을 할 수 있나」 와 「어디서 하나」 를
 * 말해 주므로, 흩어진 화면을 오가는 사람에게 지도 역할을 한다.
 */
export const WORKFLOWS: Workflow[] = [
  {
    key: 'daily_intake',
    title: '오늘 들어온 것 처리하기',
    when: '장비에서 올라온 파일을 시편에 붙이고, 처리해서 채택까지.',
    cadence: '매일',
    steps: [
      { key: 'pick', title: '파일 고르기', what: '커넥터 수집함에서 담습니다.', collects: 'test_run', where: '/settings/connectors' },
      { key: 'attach', title: '시편에 붙이기', what: '어느 시편의 것인지 사람이 정합니다(ADR 0021).' },
      { key: 'process', title: '처리', what: '레시피를 걸어 한 번에 돌립니다.' },
      { key: 'adopt', title: '채택', what: '시험마다 값 하나를 고릅니다 — 그것이 재료 통계로 갑니다.' },
    ],
  },
  {
    key: 'viscoelastic_set',
    title: 'DMA 한 벌로 점탄성 계수 내기',
    when: '시편 여럿의 DMA 를 겹쳐 Prony 계수 한 벌을 만들고 카드까지.',
    cadence: '자주',
    steps: [
      { key: 'pick', title: '시험 고르기', what: '그 재료의 DMA 시험을 담습니다.', collects: 'test_run' },
      { key: 'master', title: '마스터커브 갖추기', what: '겹치거나, 장비가 만든 것을 가져옵니다. 대표를 정합니다.' },
      { key: 'fit', title: '글로벌 피팅', what: '담은 시편을 한 번에 적합해 계수 한 벌을 냅니다.' },
      { key: 'card', title: '카드 만들기', what: '그 계수로 물성 카드를 만듭니다.' },
    ],
  },
  {
    key: 'analysis_deck',
    title: '해석에 쓸 물성 갖추기',
    when: '제품군에 쓰이는 재료의 카드를 모아 한 덱 묶음으로 내보냅니다.',
    cadence: '프로젝트마다',
    steps: [
      { key: 'scope', title: '무엇에 쓰나', what: '적용 제품·파트로 재료를 찾습니다.', collects: 'material' },
      { key: 'survey', title: '무엇이 있나', what: '재료마다 카드가 있는지, 초안인지 확정인지 봅니다.' },
      { key: 'collect', title: '골라 담기', what: '해석에 쓸 카드를 담습니다.', collects: 'card', where: '/cards' },
      { key: 'export', title: '묶음 내보내기', what: 'manifest·체크섬과 함께 한 번에 받습니다.', where: '/cards' },
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
      { key: 'pick', title: '초안 고르기', what: '확정 대기 카드를 담습니다.', collects: 'card', where: '/cards' },
      { key: 'read', title: '근거 보기', what: '어느 시험·표본 수·경고를 봅니다.' },
      { key: 'decide', title: '확정 또는 반려', what: '부서 관리자가 누릅니다 — 워크벤치가 대신 누르지 않습니다.' },
    ],
  },
]

export function workflowOf(key: string): Workflow | undefined {
  return WORKFLOWS.find((one) => one.key === key)
}
