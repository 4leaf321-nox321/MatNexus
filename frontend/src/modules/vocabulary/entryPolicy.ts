/**
 * 이 축에 **새 값을 세울 수 있나** — 화면이 먼저 안다.
 *
 * `managed` 축(ADR 0032)은 이미 있는 값이면 누구나 고르지만 **새 값은 부서
 * 관리자**만 세운다. 서버가 403 으로 막는다. 그런데 눌러 보고 알게 하면 사람은
 * 자기가 무엇을 잘못했는지 모른다 — 오타를 낸 것인지, 원래 못 하는 일인지.
 * 「새로 추가」 를 아예 안 보여 주고 **왜 안 되는지**를 그 자리에 적는다.
 *
 * **이것은 표시일 뿐 권한이 아니다**(`shared/auth/roles` 와 같은 자리). 여기를
 * 고쳐 우회할 수 있고 그래도 된다 — 판정은 서버가 한다. 여기서 하는 일은 하나다:
 * 눌러 보고 403 을 알게 하지 않는 것.
 *
 * ## 정책을 왜 따로 받아 오나
 *
 * 값 검색(`/vocabularies/{slug}/terms`)은 값만 준다 — 축이 어떤 정책인지는 축
 * 목록에 있다. 피커마다 축 목록을 받으면 폼 하나 열 때마다 같은 요청이 예닐곱
 * 개 나가므로, **세션에 한 번만** 받아 모듈이 들고 있는다. 정책은 코드가 정본이라
 * (ADR 0032 D5) 배포 중에 바뀌지 않는다.
 */

import { useEffect, useState } from 'react'

import { vocabularyApi } from '@/modules/vocabulary/api'

export type EntryPolicy = 'open' | 'managed' | 'closed'

/** 아직 모르는 상태 — 안 받았거나, 못 받았거나, 그런 축이 없다. */
export type MaybePolicy = EntryPolicy | null

let pending: Promise<Map<string, EntryPolicy>> | null = null

/** 축별 정책. **세션에 한 번만 받는다.** */
export function axisPolicies(): Promise<Map<string, EntryPolicy>> {
  if (!pending) {
    // **정책을 못 받아 오는 것이 폼을 죽이면 안 된다.** 이것은 안내를 고르는
    // 데 쓰는 곁가지 정보다 — 여기서 던지면 그 칸을 품은 폼 전체가 안 뜬다.
    // 그래서 부르는 것까지 `async` 안에 넣는다(동기 예외도 같이 잡힌다).
    pending = (async () => {
      const axes = await vocabularyApi.list()
      return new Map(axes.map((one) => [one.slug, one.entry_policy as EntryPolicy]))
    })().catch(() => {
      // **못 받았으면 다음에 다시 묻는다.** 실패를 쥐고 있으면 그 세션 내내
      // 모든 피커가 정책을 모른 채로 산다 — 새로고침해야 낫는 화면이 된다.
      pending = null
      return new Map<string, EntryPolicy>()
    })
  }
  return pending
}

/** 시험용 — 다음 시험이 다른 축 목록을 쓰게 한다. */
export function forgetAxisPolicies(): void {
  pending = null
}

export function useEntryPolicy(slug: string): MaybePolicy {
  const [policy, setPolicy] = useState<MaybePolicy>(null)

  useEffect(() => {
    let cancelled = false
    void axisPolicies().then((all) => {
      if (!cancelled) setPolicy(all.get(slug) ?? null)
    })
    return () => {
      cancelled = true
    }
  }, [slug])

  return policy
}

/**
 * 이 사람이 이 축에 **새 값을 세울** 수 있나 — `managed` 축은 **자료 관리자**다(ADR 0035
 * 3단계 — 전에는 부서 관리자, ADR 0032 D2). 인자 이름이 `manager` 인 것은 그 흔적이다.
 *
 * `manager` 가 `null` 이면 **모른다** — 로그인 정보가 없는 자리에 얹힌 피커다
 * (`useMaybeAuth`). 모를 때는 감추지 않는다: 없는 권한을 준 것이 아니라, 판정을
 * 서버에 맡긴 것이다. 거꾸로 하면 제공자 하나 빠뜨린 화면에서 **관리자도 단추를
 * 못 보고**, 그 원인은 화면 어디에도 안 적힌다.
 *
 * 정책을 아직 모르는 동안(`policy === null`)도 같다 — 지금까지의 동작 그대로다.
 */
export function mayCoin(policy: MaybePolicy, manager: boolean | null): boolean {
  if (policy === 'closed') return false
  if (policy !== 'managed') return true
  return manager !== false
}

/**
 * 못 세우는 이유. **다음에 할 일까지 적는다** — 서버의 거절문과 같은 결이다
 * (ADR 0032 D3). 「권한이 없습니다」 로 끝내면 사람은 오타인지 새 값인지 모른다.
 */
export function coinHint(policy: MaybePolicy, label: string): string | undefined {
  if (policy === 'managed') {
    return `새 ${label} 을(를) 세우는 것은 자료 관리자만 할 수 있습니다 — 목록에서 고르거나 자료 관리자에게 등록을 요청하세요.`
  }
  if (policy === 'closed') {
    return `${label} 은(는) 관리자가 등록한 값만 고를 수 있습니다.`
  }
  return undefined
}
