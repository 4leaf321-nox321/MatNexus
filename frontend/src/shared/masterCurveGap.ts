/**
 * **겹칠 수 있는데 아직 안 겹친 시험이 몇인가.**
 *
 * 재료 화면에서 물성을 채우려는 사람에게 남은 일을 알려 준다. 점탄성은 시험 상세의
 * 다른 탭에서 만들어지고 「결과」 를 거치지 않아서, 그냥 두면 **통째로 건너뛴 채**
 * 재료에서 물성이 비었다고 여기게 된다.
 *
 * ## `shared` 에 있는 이유
 *
 * 재료 화면과 워크벤치가 같이 쓴다. 워크벤치가 재료 모듈을 부르면 방향이 뒤집히고,
 * 각자 세면 **두 화면이 같은 시험을 놓고 다른 말을 한다** — 한쪽은 「남은 일 2건」,
 * 다른 쪽은 「다 됐다」. 규칙은 한 벌이어야 한다(ADR 0024).
 *
 * ## 「할 수 없는 것」 을 「남은 일」 로 세지 않는다
 *
 * DMA 는 같은 시험종류 아래 성격이 다른 둘이 온다.
 *
 *     주파수-온도 스윕   온도 여러 단 → 겹쳐서 마스터커브를 만든다
 *     변형률 스윕        온도 한 단   → 겹칠 것이 없다(선형 구간을 본다)
 *
 * 시험종류 키로는 못 가른다. 온도 단 수를 안 보고 세면 변형률 스윕까지 「아직
 * 안 했다」 가 되고, 그 재촉은 **할 수 없는 일**을 가리킨다 — 한 번 그러면 사람은
 * 그 줄을 다시 안 읽는다.
 *
 * ## 모르는 것은 세지 않는다
 *
 * `temperature_step_count` 가 `null` 이면 「이 칸이 생기기 전에 읽은 시험」 이다.
 * 모르는 것을 「할 수 있다」 로 세면 없는 일을 만들고, 「할 수 없다」 로 세면 진짜
 * 남은 일을 숨긴다. 그래서 따로 센다 —
 * `scripts/backfill_temperature_steps.py` 가 채우면 제자리로 간다.
 */

/** 이 계산에 필요한 만큼만. 화면 타입 전체를 받지 않는다 — 시험이 못 만든다. */
export interface GapRun {
  test_type_key: string
  master_curve_count?: number | null
  temperature_step_count?: number | null
}

export interface Gap {
  /** 마스터커브가 있는 시험. 글로벌 피팅 후보다. */
  ready: number
  /** 온도가 여러 단인데 아직 안 겹친 시험. **이것이 남은 일이다.** */
  pending: number
  /** 온도가 한 단이라 겹칠 수 없는 시험(변형률 스윕 등). */
  cannot: number
  /** 온도 단 수를 아직 안 세어 본 시험. */
  unknown: number
}

/**
 * @param runs 그 재료의 읽힌 시험들
 * @param keys 이 계산을 쓸 수 있는 시험종류 키. **서버가 풀어서 준 것**을 쓴다
 *   (`/groups/kinds` 의 `applies_to`) — 선언에 적힌 키만 보면 부서가 만든 종류가
 *   빠진다. 비어 있으면 제한 없음으로 본다.
 */
export function masterCurveGap(runs: GapRun[], keys: string[]): Gap {
  const gap: Gap = { ready: 0, pending: 0, cannot: 0, unknown: 0 }
  for (const run of runs) {
    if (keys.length > 0 && !keys.includes(run.test_type_key)) continue
    if ((run.master_curve_count ?? 0) > 0) {
      gap.ready += 1
      continue
    }
    const steps = run.temperature_step_count
    if (steps == null) gap.unknown += 1
    else if (steps >= 2) gap.pending += 1
    else gap.cannot += 1
  }
  return gap
}
