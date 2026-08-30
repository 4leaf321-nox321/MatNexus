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
export type ImportableCurve = components['schemas']['ImportableCurveOut']

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

  /**
   * 장비가 계산해 준 표. **못 쓰는 것도 이유와 함께 온다** — 이동인자 표가 같은
   * 칸에 들어오므로, 안 보여 주면 「내 파일에 있는 그 표가 왜 없지」 가 된다.
   */
  importableCurves: (testRunId: string) =>
    api.get<ImportableCurve[]>(`/viscoelastic/runs/${testRunId}/importable-curves`),

  /**
   * **장비가 이미 겹쳐 준 곡선**을 마스터커브로 등록한다.
   *
   * TA TRIOS 같은 장비는 시간-온도 중첩을 제 소프트웨어에서 하고 마스터커브를
   * 함께 내보낸다. 장비 파일 정의가 그 표를 「처리결과」 로 읽어 두지만, 그것만
   * 으로는 **Prony 도 글로벌 피팅도 못 쓴다** — `MasterCurve` 행이 아니어서다.
   *
   * **겹치기를 다시 하지 않는다.** 장비가 쓴 이동인자를 모르고, 다시 겹치면
   * 다른 곡선이 나오는데 둘 다 그럴듯하다.
   */
  importMasterCurve: (
    testRunId: string,
    body: { curve_key: string; reference_temperature_k: number }
  ) =>
    api.post<MasterCurve>(`/viscoelastic/runs/${testRunId}/master-curves/import`, body),

  /**
   * **이 시험의 대표를 이 곡선으로 옮긴다.**
   *
   * 재료의 글로벌 피팅이 시험마다 대표 하나를 읽는다. 전에는 「가장 최근 것」 을
   * 말없이 썼는데, 기준 온도를 바꿔 하나 더 만들면 그 순간부터 재료 쪽 계산이
   * 바뀌면서 **그 전환이 화면 어디에도 안 보였다.**
   */
  setPrimary: (masterCurveId: string) =>
    api.post<MasterCurve>(`/viscoelastic/master-curves/${masterCurveId}/primary`, {}),

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
