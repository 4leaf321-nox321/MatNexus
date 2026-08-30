/**
 * 물성 정의 파일 — **손으로 고친 파일이 들어올 자리다.**
 *
 * 개발 서버에서 운영으로 옮기는 길이라, 도중에 파일이 편집기를 한 번 지난다.
 * 무는 데를 고를 때 「제대로 된 파일이 읽힌다」 보다 **「망가진 파일이 통과하지
 * 않는다」·「서버 사정이 안 실린다」** 를 우선한다 — 앞엣것은 안 되면 바로
 * 보이지만, 뒤엣것은 운영에서 조용히 틀린다.
 */

import { describe, expect, it } from 'vitest'

import {
  PROFILE_FILE_KIND,
  ProfileFileError,
  fileNameFor,
  makeFile,
  readProfileFile,
  toFileEntry,
} from '@/modules/fitting/profileFile'

const ROW = {
  id: 'uuid-1',
  key: 'lsdyna',
  label: 'LS-DYNA',
  description: '키워드 카드 10칸',
  owner_workspace_slug: 'metal',
  owner_workspace_name: '금속재료팀',
  is_global: false,
  is_active: true,
  created_at: '2026-08-30T00:00:00Z',
  updated_at: '2026-08-30T00:00:00Z',
  definition: { extension: 'k', lines: [{ text: '*KEYWORD' }] },
}

function roundTrip(rows: (typeof ROW)[]) {
  const file = makeFile(rows.map(toFileEntry), 'dev.example')
  return readProfileFile(JSON.stringify(file))
}

describe('내보내기', () => {
  it('서버 사정은 안 싣는다', () => {
    /**
     * **여기가 제일 조용히 틀리는 자리다.** 소유 부서를 실으면 운영에 같은 slug 가
     * 있을 때 **남의 부서 것으로 들어가고**, 없으면 통째로 실패한다. id·시각도
     * 그 서버의 것이라 옮겨 봐야 뜻이 없다.
     */
    // **읽은 뒤가 아니라 쓴 것을 본다.** `readProfileFile` 은 아는 칸만 다시
    // 쌓으므로, 왕복해서 보면 파일에 실제로 실린 것이 안 보인다 — 사보타주로
    // 확인했다(2026-08-31): 소유 부서를 실어도 왕복 시험은 통과했다.
    const written = makeFile([toFileEntry(ROW)], 'dev.example').profiles[0]

    expect(written).toEqual({
      key: 'lsdyna',
      label: 'LS-DYNA',
      description: '키워드 카드 10칸',
      is_active: true,
      definition: ROW.definition,
    })
    expect(Object.keys(written).sort()).toEqual([
      'definition',
      'description',
      'is_active',
      'key',
      'label',
    ])

    // 읽는 쪽도 같은 것을 낸다.
    expect(roundTrip([ROW])[0]).toEqual(written)
  })

  it('한 벌만 내보내도 배열이다', () => {
    // 모양이 갈리면 읽는 쪽이 둘을 다뤄야 하고, 그 분기는 손으로 고친 파일
    // 앞에서 처음 틀린다.
    const file = makeFile([toFileEntry(ROW)], 'dev')
    expect(Array.isArray(file.profiles)).toBe(true)
    expect(file.kind).toBe(PROFILE_FILE_KIND)
  })

  it('파일 이름으로 무엇인지 안다', () => {
    expect(fileNameFor([toFileEntry(ROW)])).toMatch(/^물성정의_lsdyna_\d{4}-\d{2}-\d{2}\.json$/)
    expect(fileNameFor([toFileEntry(ROW), toFileEntry(ROW)])).toContain('2건')
  })
})

describe('읽기 — 망가진 파일을 막는다', () => {
  it('JSON 이 아니면 왜인지 말한다', () => {
    expect(() => readProfileFile('덱덱덱')).toThrow(ProfileFileError)
    expect(() => readProfileFile('덱덱덱')).toThrow(/JSON/)
  })

  it('남의 JSON 은 안 읽는다', () => {
    /** 표를 안 보면 **아무 JSON 이나 정의로 들어간다.** */
    expect(() => readProfileFile('{"profiles":[]}')).toThrow(/내보낸 물성 정의 파일이 아닙니다/)
  })

  it('모르는 판은 짐작해서 읽지 않는다', () => {
    /**
     * 새 칸이 조용히 빠진 정의가 들어가면 **저장은 되고 나중에 덱이 틀린다.**
     * 그때는 파일도 사람 손을 떠난 뒤다.
     */
    const file = { ...makeFile([toFileEntry(ROW)], 'dev'), version: 99 }
    expect(() => readProfileFile(JSON.stringify(file))).toThrow(/새 판의 파일/)
  })

  it('빈 파일을 받지 않는다', () => {
    const file = makeFile([], 'dev')
    expect(() => readProfileFile(JSON.stringify(file))).toThrow(/정의가 없습니다/)
  })

  it('줄 목록이 없으면 막고 어느 것인지 말한다', () => {
    // 서버까지 가면 500 이다 — 여기서 이름을 붙여 돌려준다.
    const file = makeFile([{ ...toFileEntry(ROW), definition: { extension: 'k' } }], 'dev')
    expect(() => readProfileFile(JSON.stringify(file))).toThrow(/lsdyna.*줄 목록/)
  })

  it('key 가 빠지면 몇 번째인지 말한다', () => {
    const file = makeFile(
      [toFileEntry(ROW), { ...toFileEntry(ROW), key: '' }],
      'dev'
    )
    expect(() => readProfileFile(JSON.stringify(file))).toThrow(/2번째 정의에 key 가 없습니다/)
  })

  it('is_active 가 없으면 켠 것으로 본다', () => {
    // 파일을 손으로 만든 사람이 흔히 빠뜨린다. 빠뜨렸다고 꺼진 정의로 들어가면
    // 「넣었는데 안 나온다」 가 된다.
    const file = makeFile([toFileEntry(ROW)], 'dev') as unknown as {
      profiles: Record<string, unknown>[]
    }
    delete file.profiles[0].is_active
    expect(readProfileFile(JSON.stringify(file))[0].is_active).toBe(true)
  })
})
