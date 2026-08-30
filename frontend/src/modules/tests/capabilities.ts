/**
 * **이 매핑이면 무엇이 열리나.**
 *
 * 점탄성 탭은 「시험 종류에 `storage_modulus` 와 `loss_modulus` 가 있는가」 로
 * 뜬다. 시험 종류 키를 안 박은 것은 옳다 — 부서가 자기 DMA 종류를 만들어도 탭이
 * 떠야 한다. 다만 그 규칙이 **어디에도 안 적혀 있었다.** 장비 파일 정의를 만드는
 * 사람은 열을 매핑하면서 무엇이 중요한지 모른 채 골랐고, 저장한 뒤 시험을 열어
 * 봐야 탭이 없다는 것을 알았다.
 *
 * 그래서 요건을 한 곳에 적고, **정의를 만드는 화면이 그것을 미리 보여 준다.**
 *
 * ## 무엇을 보는지가 셋 다 다르다
 *
 *     점탄성 탭      시험 종류의 채널 목록   — 파일과 무관하다
 *     겹치기         측정 곡선의 실제 열
 *     가져오기       처리결과 곡선의 실제 열
 *
 * 이 차이 때문에 「탭은 떴는데 겹칠 스윕이 없습니다」 가 나온다. 세 줄을 나란히
 * 두면 그 조합이 화면에서 바로 읽힌다.
 *
 * ## 정본은 서버다
 *
 * 여기 적은 것은 **안내**다. 실제 판정은 세 자리에서 한다 —
 * `TestRunDetailPage` 의 `isViscoelastic`(이 파일의 `hasViscoelasticTab` 을 쓴다),
 * `app/modules/viscoelastic/services.py` 의 `sweeps_of`·`importable_curves`.
 * 뒤 둘이 바뀌면 여기도 고쳐야 한다 — 그래서 요건을 표로 두고 시험이 문구까지 왼다.
 */

/** 어느 목록의 키를 보는가. */
export type CapabilityScope = 'type' | 'measured' | 'derived'

export type Capability = {
  id: string
  label: string
  /** 어디에서 보이나. 사람이 「그래서 어디를 봐야 하지」 를 안 묻게. */
  where: string
  scope: CapabilityScope
  /** 필요한 채널. 안쪽 배열은 **그 중 하나면 된다**. */
  needs: string[][]
  why: string
}

export const CAPABILITIES: Capability[] = [
  {
    id: 'viscoelastic_tab',
    label: '점탄성 탭',
    where: '시험 상세 화면의 탭',
    scope: 'type',
    // **시험 종류의 채널 목록**을 본다 — 이번 파일에 그 열이 있었는지가 아니다.
    needs: [['storage_modulus'], ['loss_modulus']],
    why: '이 둘이 시험 종류에 선언돼 있어야 탭이 뜹니다. 파일에 그 열이 있어도 종류에 없으면 안 뜹니다.',
  },
  {
    id: 'master_curve',
    label: '겹치기 (마스터커브 만들기)',
    where: '점탄성 탭의 첫 블록',
    scope: 'measured',
    // 주파수는 각주파수로 대신할 수 있다 — 실측 파일의 첫 표에만 `Frequency` 가 있었다.
    needs: [['temperature'], ['storage_modulus'], ['frequency', 'angular_frequency']],
    why: '온도가 다른 스윕을 주파수 축으로 밀어 겹칩니다. 셋 중 하나라도 없는 표는 경고와 함께 빠집니다.',
  },
  {
    id: 'master_curve_import',
    label: '장비가 만든 마스터커브 가져오기',
    where: '점탄성 탭의 둘째 블록',
    scope: 'derived',
    needs: [
      ['frequency', 'angular_frequency', 'omega'],
      ['storage_modulus', 'storage_pa', 'e_prime', 'g_prime'],
    ],
    why: '장비가 이미 겹쳐 준 곡선을 그대로 받습니다. 처리결과 표에 이 열이 있어야 합니다.',
  },
]

/** 못 채운 요건. 빈 배열이면 열린다. */
export function missingFor(capability: Capability, keys: Iterable<string>): string[][] {
  const found = new Set(keys)
  return capability.needs.filter((one) => !one.some((name) => found.has(name)))
}

/**
 * 점탄성 탭이 뜨는가. **시험 상세 화면과 정의 화면이 같은 함수를 쓴다** — 두 곳이
 * 각자 적으면 한쪽만 고쳐진 채 「정의 화면은 뜬다는데 안 뜬다」 가 된다.
 */
export function hasViscoelasticTab(keys: Iterable<string>): boolean {
  const capability = CAPABILITIES.find((one) => one.id === 'viscoelastic_tab')
  return capability ? missingFor(capability, keys).length === 0 : false
}
