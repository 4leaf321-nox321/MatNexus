/**
 * 점탄성 API — 마스터커브와 Prony 적합.
 *
 * **DMA 는 한 온도에서 좁은 창(0.1~20 Hz)만 훑는다.** 해석이 필요한 범위는
 * 그보다 훨씬 넓어서, 온도를 바꿔 여러 번 재고 주파수 축으로 밀어 겹친다.
 *
 * 장비도 그것을 해 주지만 **장비가 고른 기준 온도에 묶여 있다.** 60 °C 해석을
 * 하려면 시험을 다시 하거나 우리가 겹쳐야 한다 — 그게 이 API 가 있는 이유다.
 *
 * 만들고 나면 안 고친다. 기준 온도를 바꾸면 **새로 만들고 둘 다 남는다**
 * (ADR 0007 의 결과 불변성과 같은 판단).
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Sweep = components['schemas']['SweepOut']
export type SweepList = components['schemas']['SweepListOut']
export type MasterCurve = components['schemas']['MasterCurveOut']
export type ShiftFactor = components['schemas']['ShiftOut']
export type PronyFit = components['schemas']['PronyFitOut']
export type PronyCandidate = components['schemas']['PronyCandidateOut']
export type PronyTerm = components['schemas']['PronyTermOut']

/** 겹친 곡선의 점. 화면이 그린다. */
export type MasterCurvePoints = Record<string, (number | null)[]>

export const viscoelasticApi = {
  /**
   * 겹칠 후보. **기준 온도는 잰 온도 중에 있어야 하므로** 무엇이 있는지 먼저
   * 보여 준다 — 입력칸에 숫자를 치게 두면 없는 온도를 적고 나서 오류를 본다.
   */
  sweeps: (testRunId: string) =>
    api.get<SweepList>(`/viscoelastic/runs/${testRunId}/sweeps`),

  masterCurves: (testRunId: string) =>
    api.get<MasterCurve[]>(`/viscoelastic/runs/${testRunId}/master-curves`),

  /**
   * 겹친다. `wlf`·`arrhenius` 는 **실제로 겹쳐 본 값을 목표로** 모델을 맞추고
   * 관측값도 함께 돌려준다 — 둘이 벌어지면 그 모델이 이 재료에 안 맞는다는
   * 뜻이고, 그 판단은 사람이 한다.
   *
   * `manual` 은 사람(또는 장비)이 준 이동인자를 그대로 쓴다.
   */
  createMasterCurve: (
    testRunId: string,
    body: {
      reference_temperature_k: number
      method?: 'wlf' | 'arrhenius' | 'manual'
      manual_shifts?: Record<string, number>
      curve_keys?: string[]
    }
  ) => api.post<MasterCurve>(`/viscoelastic/runs/${testRunId}/master-curves`, body),

  points: (masterCurveId: string) =>
    api.get<MasterCurvePoints>(`/viscoelastic/master-curves/${masterCurveId}/points`),

  pronyFits: (masterCurveId: string) =>
    api.get<PronyFit[]>(`/viscoelastic/master-curves/${masterCurveId}/prony`),

  /**
   * 일반화 Maxwell 계수를 맞춘다. 항 수를 안 주면 후보를 재고 BIC 로 고른다.
   *
   * **재 본 것이 전부 돌아온다.** "3항이면 충분한데 왜 6항이지" 를 사람이 볼
   * 수 있어야 한다 — 경화식 견주기와 같은 판단이다.
   */
  fitProny: (masterCurveId: string, body: { terms?: number } = {}) =>
    api.post<PronyFit>(`/viscoelastic/master-curves/${masterCurveId}/prony`, body),
}
