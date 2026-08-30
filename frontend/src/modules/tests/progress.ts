/**
 * 시험 하나가 **어디까지 됐나.**
 *
 * 탭 넷이 나란히 있을 뿐 진행 상태가 화면 어디에도 없었다. 그래서 두 가지가
 * 조용히 일어났다.
 *
 *   결과를 저장해 놓고 **채택을 안 한** 시험이 재료 통계에서 빠진다. 통계는
 *   `adopted_result_id` 가 걸린 것만 세는데, 시험 화면은 그 사실을 말하지 않았다.
 *
 *   DMA 를 올린 사람이 「결과」 탭이 빈 것을 **고장으로 읽는다.** 점탄성은 다른
 *   탭에 살고 거기 결과를 안 남긴다.
 *
 * ## 경로가 둘이고, 둘 사이에 선행 관계가 없다
 *
 *     값 내기   곡선 하나에서 나오는 값 → 채택 → 재료 물성 표(통계)
 *     점탄성    온도를 가로질러 겹친 것 → 카드 → CAE 덱
 *
 * 둘 다 해도 되고 필요한 쪽만 해도 된다.
 *
 * ## 왜 화면이 아니라 여기서 정하나
 *
 * 「무엇이 남았나」 는 **판단**이고, 판단은 시험이 물 수 있는 자리에 있어야 한다.
 * 화면 안의 삼항 연산자로 두면 「결과가 3건인데 채택이 없을 때 무엇을 권하는가」
 * 를 시험이 못 짚는다 — 그리고 그 문장이 틀리면 사람은 엉뚱한 탭으로 간다.
 */

/** 진행 띠가 읽는 만큼만. 화면 타입 전체를 받지 않는다 — 시험이 못 만든다. */
export interface RunState {
  status: string
  /** 저장된 처리 결과 수. */
  resultCount: number
  /** 채택된 결과가 있는가. */
  adopted: boolean
  /** 곡선 몇 벌로 읽혔나. */
  curveCount: number
  /** 이 시험이 점탄성인가(시험 종류에 저장·손실 탄성률이 있는가). */
  viscoelastic: boolean
  masterCurveCount: number
  pronyFitCount: number
}

export interface Step {
  key: string
  title: string
  /** 이 단계가 끝났는가. **끝난 것에만 표시한다** — 「안 함」 을 달면 아직 할
   *  필요가 없는 단계까지 미완으로 보여 재촉하는 화면이 된다. */
  done: boolean
  /** 지금 상태 한 줄. 무엇이 몇 개이고, 그래서 무엇이 남았는지. */
  now: string
  /** 데려갈 곳. 없으면 할 일이 없는 단계다. */
  go?: { label: string; tab: string }
}

export function runProgress(state: RunState): Step[] {
  if (state.status !== 'parsed') return []

  const steps: Step[] = [
    { key: 'source', title: '읽힘', done: true, now: `곡선 ${state.curveCount}벌` },
    {
      key: 'results',
      title: '값 내기',
      // **채택이 곧 완료다.** 결과를 저장만 한 것은 아무 데도 안 실린다.
      done: state.adopted,
      now: state.adopted
        ? '채택됨 — 재료의 물성 표(통계)에 실립니다'
        : state.resultCount === 0
          ? '처리 단계를 돌려 결과를 저장하세요'
          : `결과 ${state.resultCount}건 · 아직 채택 안 함 — 채택해야 통계에 실립니다`,
      go: state.adopted
        ? { label: '결과 보기', tab: 'results' }
        : state.resultCount === 0
          ? { label: '처리하러 가기', tab: 'process' }
          : { label: '채택하러 가기', tab: 'results' },
    },
  ]

  if (state.viscoelastic) {
    steps.push({
      key: 'viscoelastic',
      title: '점탄성',
      // **적합까지를 「됨」 으로 본다.** 카드는 재료에 매달려서 이 시험만 보고는
      // 셀 수 없다 — 카드가 적합을 외래키로 잡지 않기 때문이다(그래야 시험을
      // 지워도 카드가 남는다). 없는 것을 세는 척하지 않는다.
      done: state.pronyFitCount > 0,
      now:
        state.masterCurveCount === 0
          ? '겹치거나, 장비가 만든 마스터커브를 가져오세요'
          : state.pronyFitCount === 0
            ? `마스터커브 ${state.masterCurveCount}벌 · 아직 계수를 안 맞춤`
            : `마스터커브 ${state.masterCurveCount} · 적합 ${state.pronyFitCount} — ` +
              '카드로 만들면 CAE 덱이 나갑니다',
      go: { label: '점탄성으로', tab: 'viscoelastic' },
    })
  }

  return steps
}
