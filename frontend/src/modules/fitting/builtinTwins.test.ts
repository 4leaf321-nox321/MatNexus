/**
 * 기본 형식의 정의판 50벌이 **편집기를 지나도 한 글자도 안 바뀐다**(ADR 0038).
 *
 * 정의판은 코드판과 덱이 글자까지 같다(`backend/tests/unit/test_export_twins.py`). 코드판이
 * 틀려 사용 중단하면 정의판을 켜서 **화면에서** 고친다 — 그런데 편집기가 줄을 폼으로 옮겼다
 * 돌리면서 칸 하나만 흘려도, 고치러 들어와 저장만 눌렀는데 덱이 달라진다. 그것을 파일 전체로
 * 본다: 줄 → 폼 → 묶음 → 폼 → 줄.
 */

import { readFileSync } from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { fromDefinitionLine, toDefinitionLine } from '@/modules/fitting/deckLines'
import { fromSections, toSections } from '@/modules/fitting/deckSections'

type Profile = { key: string; definition: { lines: Record<string, unknown>[] } }

const seed = JSON.parse(
  readFileSync(
    path.resolve(process.cwd(), '../backend/seeds/export-profiles/기본-형식-정의.json'),
    'utf-8'
  )
) as { profiles: Profile[] }

describe('기본 형식의 정의판', () => {
  it('50벌이 있다', () => {
    expect(seed.profiles.length).toBeGreaterThanOrEqual(50)
  })

  it.each(seed.profiles.map((one) => [one.key, one] as const))(
    '%s 는 편집기를 지나도 같다',
    (_key, profile) => {
      const lines = profile.definition.lines
      const round = fromSections(toSections(lines.map(fromDefinitionLine))).map(
        toDefinitionLine
      )
      expect(round).toEqual(lines)
    }
  )
})
