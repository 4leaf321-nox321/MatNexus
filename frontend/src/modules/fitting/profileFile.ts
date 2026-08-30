/**
 * 해석용 물성 정의를 **파일로 주고받는다** — 개발 서버에서 만들어 운영 서버로.
 *
 * ## 왜 서버를 안 거치나
 *
 * 목록이 이미 정의 전체를 들고 있고(`definition`), 만드는 길도 이미 있다. 여기서
 * 하는 일은 **그 둘 사이의 파일 모양을 정하는 것**뿐이라 새 엔드포인트가 필요
 * 없다. 검증은 그대로 서버가 한다 — 들여올 때 `createExportProfile` 이 정의를
 * 실제로 만들어 보고(`_checked`), key 가 겹치면 막는다.
 *
 * ## 무엇을 안 싣나
 *
 * `id` · `owner_workspace_slug` · `is_global` · 시각은 **그 서버의 사정**이다.
 * 특히 소유 부서를 실으면 두 가지로 틀린다 — 운영에 같은 slug 가 없으면 들여오기가
 * 통째로 실패하고, 있으면 **남의 부서 것으로 들어간다.** 들여온 정의는 언제나
 * 들여온 사람의 부서로 간다(전역 승격은 성격이 다른 결정이라 별도 경로다).
 *
 * ## 하나든 여럿이든 같은 모양이다
 *
 * 한 벌만 내보내도 `profiles` 는 배열이다. 모양이 갈리면 읽는 쪽이 둘을 다뤄야
 * 하고, 그 분기는 **파일을 손으로 고친 사람** 앞에서 처음 틀린다.
 */

/** 파일이 이 앱의 것인지 알아보는 표. 값이 다르면 안 읽는다. */
export const PROFILE_FILE_KIND = 'matnexus.export-profile'

/** 모양이 바뀌면 올린다. 읽는 쪽이 모르는 판이면 **읽지 않고 말한다.** */
export const PROFILE_FILE_VERSION = 1

/** 파일 안의 정의 하나 — 서버에 만들 때 그대로 쓰는 칸만 있다. */
export interface ProfileInFile {
  key: string
  label: string
  description: string | null
  is_active: boolean
  definition: Record<string, unknown>
}

export interface ProfileFile {
  kind: typeof PROFILE_FILE_KIND
  version: number
  exported_at: string
  /** 어디서 나왔나. **사람이 읽을 흔적일 뿐** — 들여올 때 안 쓴다. */
  exported_from: string
  profiles: ProfileInFile[]
}

/** 목록의 한 줄에서 파일에 실을 것만 뽑는다. */
export function toFileEntry(item: {
  key: string
  label: string
  description?: string | null
  is_active: boolean
  definition: Record<string, unknown>
}): ProfileInFile {
  return {
    key: item.key,
    label: item.label,
    description: item.description ?? null,
    is_active: item.is_active,
    definition: item.definition,
  }
}

export function makeFile(profiles: ProfileInFile[], origin: string): ProfileFile {
  return {
    kind: PROFILE_FILE_KIND,
    version: PROFILE_FILE_VERSION,
    exported_at: new Date().toISOString(),
    exported_from: origin,
    profiles,
  }
}

/** 사람이 파일 이름만 보고 무엇인지 알게. 하나면 그 key, 여럿이면 수. */
export function fileNameFor(profiles: ProfileInFile[]): string {
  const day = new Date().toISOString().slice(0, 10)
  const what =
    profiles.length === 1
      ? profiles[0].key.replace(/[^\w.-]+/g, '_')
      : `${profiles.length}건`
  return `물성정의_${what}_${day}.json`
}

export class ProfileFileError extends Error {}

/**
 * 파일 글자를 읽어 정의 목록으로. **못 읽으면 왜 못 읽는지 말한다.**
 *
 * 사람이 손으로 고친 파일이 들어올 자리라, `JSON.parse` 가 통과했다는 것만으로는
 * 부족하다 — 여기서 안 걸러진 것은 **서버가 500 으로** 걸러 준다.
 */
export function readProfileFile(text: string): ProfileInFile[] {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new ProfileFileError('JSON 파일이 아닙니다.')
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new ProfileFileError('JSON 파일이 아닙니다.')
  }
  const file = parsed as Partial<ProfileFile>
  if (file.kind !== PROFILE_FILE_KIND) {
    throw new ProfileFileError(
      '이 앱이 내보낸 물성 정의 파일이 아닙니다. 「내보내기」 로 만든 파일을 고르세요.'
    )
  }
  if (typeof file.version !== 'number' || file.version > PROFILE_FILE_VERSION) {
    // **모르는 판을 짐작해서 읽지 않는다.** 새 칸이 조용히 빠진 정의가 들어가면,
    // 저장은 되고 나중에 덱이 틀린다.
    throw new ProfileFileError(
      `이 앱보다 새 판의 파일입니다(판 ${String(file.version)}). 앱을 올리고 다시 여세요.`
    )
  }
  if (!Array.isArray(file.profiles) || file.profiles.length === 0) {
    throw new ProfileFileError('파일에 정의가 없습니다.')
  }

  return file.profiles.map((one, index) => {
    const where = `${index + 1}번째 정의`
    if (!one || typeof one !== 'object') throw new ProfileFileError(`${where}가 비었습니다.`)
    const { key, label, definition } = one as Partial<ProfileInFile>
    if (typeof key !== 'string' || !key.trim()) {
      throw new ProfileFileError(`${where}에 key 가 없습니다.`)
    }
    if (typeof label !== 'string' || !label.trim()) {
      throw new ProfileFileError(`${where}(${key})에 이름이 없습니다.`)
    }
    if (!definition || typeof definition !== 'object' || Array.isArray(definition)) {
      throw new ProfileFileError(`${where}(${key})에 정의 내용이 없습니다.`)
    }
    if (!Array.isArray((definition as Record<string, unknown>).lines)) {
      throw new ProfileFileError(`${where}(${key})의 정의에 줄 목록이 없습니다.`)
    }
    return {
      key,
      label,
      description: typeof one.description === 'string' ? one.description : null,
      // 안 적혀 있으면 켠 것으로 본다 — 파일을 손으로 만든 사람이 흔히 빠뜨린다.
      is_active: one.is_active !== false,
      definition: definition as Record<string, unknown>,
    }
  })
}

/** 만든 JSON 을 파일로 내려받는다. */
export function saveProfileFile(file: ProfileFile, name: string): void {
  const blob = new Blob([JSON.stringify(file, null, 2)], {
    type: 'application/json',
  })
  const url = URL.createObjectURL(blob)
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = name
    anchor.click()
  } finally {
    // 즉시 해제하면 저장이 시작되기 전에 사라지는 브라우저가 있다.
    setTimeout(() => URL.revokeObjectURL(url), 10_000)
  }
}
