/**
 * 만들다 만 프로파일을 **이 브라우저에** 임시로 둔다.
 *
 * ## 무엇을 잃고 있었나
 *
 * 저장 실패만으로는 안 잃는다 — 화면이 오류만 띄우고 상태를 그대로 둔다.
 * 잃는 자리는 따로 있었다.
 *
 *   - 새로고침 / 뒤로가기 / 다른 화면 갔다 오기
 *   - **시험 종류만 만들어지고 프로파일 저장이 실패한 경우.** 저장은 종류를
 *     먼저 만드는데(`ensureTestType`), 그 뒤가 실패해도 종류는 남긴다. 그러면
 *     사람은 「종류는 있는데 프로파일이 없는」 상태에서 다시 시작한다
 *   - 열이 20개인 장비에서 매핑을 다 하고 실패했을 때
 *
 * ## 왜 서버가 아니라 브라우저인가
 *
 * 만들다 만 것은 **아직 아무 뜻도 없는 것**이다. 서버에 두면 표가 하나 늘고,
 * 그 표에는 부서 권한이 붙어야 하고, 언제 지울지도 정해야 한다 — 임시 저장
 * 하나에 마이그레이션과 권한 판단이 딸려 온다. 다른 PC 에서 못 잇는 것은
 * 받아들일 만하다. 프로파일 하나를 두 자리에서 만드는 일은 없다.
 *
 * ## 파일은 못 담는다
 *
 * `File` 은 직렬화가 안 되고, 장비 파일을 통째로 담으면 브라우저 저장 한도를
 * 금방 넘는다. 그래서 **이름만 적어 둔다** — 무엇을 다시 놓아야 하는지 알면
 * 사람이 하는 일은 파일 하나 끌어다 놓는 것뿐이고, 손으로 정한 것은 다 남는다.
 *
 * ## 말없이 채우지 않는다
 *
 * 복원은 **사람이 누른다.** 말없이 채우면, 어제 만들다 만 것 위에 오늘 새로
 * 만들려던 사람이 그 사실을 모른 채 저장한다.
 */

export const DRAFT_VERSION = 1

export interface ProfileDraft {
  version: number
  /** 언제 적었나. 복원할지 정할 때 사람이 보는 값이다. */
  at: string
  /** 무엇을 보며 만들고 있었나. 파일 자체는 못 담는다. */
  fileName: string | null
  state: Record<string, unknown>
}

/** 새로 만들기는 `new`, 편집은 그 프로파일 키. **섞이면 안 된다.** */
function slot(key: string | undefined): string {
  return `matnexus.profile-draft.${key ?? 'new'}`
}

/**
 * 브라우저가 저장을 막을 수 있다(사생활 보호 창·설정). 그때 화면이 멈추면
 * 안 된다 — 임시 저장은 거들기이지 기능이 아니다.
 */
function store(): Storage | null {
  try {
    const probe = window.localStorage
    const mark = '__matnexus__'
    probe.setItem(mark, '1')
    probe.removeItem(mark)
    return probe
  } catch {
    return null
  }
}

export function writeDraft(
  key: string | undefined,
  state: Record<string, unknown>,
  fileName: string | null,
  now: string
): boolean {
  const box = store()
  if (!box) return false
  try {
    const draft: ProfileDraft = { version: DRAFT_VERSION, at: now, fileName, state }
    box.setItem(slot(key), JSON.stringify(draft))
    return true
  } catch {
    // 한도를 넘었을 수 있다. 조용히 포기한다 — 저장이 안 된 것을 화면이 말한다.
    return false
  }
}

export function readDraft(key: string | undefined): ProfileDraft | null {
  const box = store()
  if (!box) return null
  try {
    const raw = box.getItem(slot(key))
    if (!raw) return null
    const parsed = JSON.parse(raw) as ProfileDraft
    // **모양이 바뀌면 안 읽는다.** 옛 임시본을 새 화면에 밀어 넣으면 어디가
    // 비었는지 모르는 채로 저장된다.
    if (parsed?.version !== DRAFT_VERSION || typeof parsed.state !== 'object') return null
    return parsed
  } catch {
    return null
  }
}

export function forgetDraft(key: string | undefined): void {
  const box = store()
  if (!box) return
  try {
    box.removeItem(slot(key))
  } catch {
    /* 지우지 못해도 할 일이 없다 */
  }
}

/** `3분 전` 처럼. 사람이 "이게 아까 그건가" 를 판단하는 데 쓴다. */
export function since(at: string, now: number): string {
  const written = Date.parse(at)
  if (Number.isNaN(written)) return ''
  const seconds = Math.max(0, Math.round((now - written) / 1000))
  if (seconds < 60) return '방금'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}분 전`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}시간 전`
  return `${Math.floor(seconds / 86400)}일 전`
}
