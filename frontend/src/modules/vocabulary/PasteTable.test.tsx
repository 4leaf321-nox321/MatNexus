/**
 * 표로 붙여넣기.
 *
 * **사용자가 무엇을 적어야 하는지 몰랐다.** 헤더에 칸 이름을 적으라고만 하면 그
 * 이름을 알 방법이 없다 — 규격의 칸은 분류가 정하고 분류마다 다르다. 그래서 열을
 * 서버가 주는 목록에서 고르고, 표에 그대로 붙여넣는다.
 *
 * 그리고 **표는 껍데기다.** 서버로 갈 때는 지금까지와 같은 탭으로 갈린 줄 +
 * 헤더가 된다 — 형식이 둘이 되면 두 곳이 갈라진다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { copyText } from '@/shared/clipboard'

vi.mock('@/shared/clipboard', () => ({ copyText: vi.fn(() => Promise.resolve(true)) }))

import { PasteTable, columnsOf, headerOf, toLines } from '@/modules/vocabulary/PasteTable'
import type { SpecimenField } from '@/modules/vocabulary/api'

const field = (
  key: string,
  label: string,
  kind = 'number',
  si_unit = 'm',
  dimension = 'length'
): SpecimenField =>
  ({
    key,
    label,
    kind,
    choices: [],
    symbol: null,
    dimension,
    si_unit,
    is_required: false,
    help: null,
    inherited: true,
  }) as SpecimenField

const FIELDS = [
  field('gauge_length', '게이지 길이'),
  field('edition', '판(edition)', 'text', '1', 'dimensionless'),
]

describe('열 이름', () => {
  it('숫자 칸은 표시 단위를 헤더에 넣는다', () => {
    // **`50` 이 50 mm 인지 50 m 인지 서버는 모른다.** 화면이 표시 단위를 아니까
    // 여기서 만든다 — 사람이 적다가 틀릴 자리를 없앤다.
    expect(headerOf(FIELDS[0])).toBe('게이지 길이 (mm)')
  })

  it('문자 칸에는 단위를 안 붙인다', () => {
    expect(headerOf(FIELDS[1])).toBe('판(edition)')
  })
})

describe('서버로 보내는 모양', () => {
  it('헤더 한 줄과 탭으로 갈린 줄이 된다', () => {
    const columns = columnsOf(FIELDS, new Set(['gauge_length']), true)
    const lines = toLines(columns, [
      ['인장', '사내 A', '', '50'],
      ['', '', '', ''],
    ])
    expect(lines[0]).toBe('상위\t값\t표기\t게이지 길이 (mm)')
    expect(lines[1]).toBe('인장\t사내 A\t\t50')
    // **빈 줄은 안 보낸다** — 표에는 늘 빈 줄이 하나 남아 있다.
    expect(lines).toHaveLength(2)
  })

  it('안 고른 속성은 열에 없다', () => {
    const columns = columnsOf(FIELDS, new Set(), false)
    expect(columns.map((one) => one.header)).toEqual(['값', '표기'])
  })
})

describe('표', () => {
  // 열은 값·표기 둘이다(속성을 안 골랐다).
  function show(rows = [['', '']]) {
    const onRows = vi.fn()
    render(
      <PasteTable
        fields={FIELDS}
        hasParent={false}
        picked={new Set()}
        onPicked={vi.fn()}
        rows={rows}
        onRows={onRows}
      />
    )
    return onRows
  }

  it('고를 수 있는 속성을 보여 준다', () => {
    // **이름을 알 방법이 없으면 "헤더에 칸 이름을 적으세요" 가 소용없다.**
    show()
    expect(screen.getByRole('button', { name: '게이지 길이 (mm)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '판(edition)' })).toBeInTheDocument()
  })

  it('엑셀에서 복사한 범위가 그 자리부터 채워진다', async () => {
    const user = userEvent.setup()
    const onRows = show()
    await user.click(screen.getByLabelText('1번 줄 값'))
    await user.paste('사내 A\t사내에이\n사내 B\t사내비')

    const next = onRows.mock.calls.at(-1)?.[0]
    expect(next[0]).toEqual(['사내 A', '사내에이'])
    expect(next[1]).toEqual(['사내 B', '사내비'])
  })

  it('마지막 줄에 적으면 빈 줄이 하나 더 생긴다', async () => {
    // '줄 더하기' 를 누르러 가지 않아도 계속 칠 수 있다.
    const user = userEvent.setup()
    const onRows = show()
    await user.type(screen.getByLabelText('1번 줄 값'), 'A')

    expect(onRows.mock.calls.at(-1)?.[0]).toHaveLength(2)
  })

  it('줄이 하나뿐이면 뺄 수 없다', () => {
    show()
    expect(screen.queryByLabelText('1번 줄 빼기')).not.toBeInTheDocument()
  })

  it('헤더까지 함께 복사한다', async () => {
    // **엑셀에서 채워 오는 길.** 헤더가 없으면 붙여 놓고 열 이름을 손으로
    // 적어야 하고, 그러다 틀리면 그 열은 안 들어간다.
    const user = userEvent.setup()
    show([['사내 A', '사내에이'], ['', '']])
    await user.click(screen.getByRole('button', { name: /엑셀로 복사/ }))

    await waitFor(() => expect(copyText).toHaveBeenCalled())
    expect(vi.mocked(copyText).mock.calls[0][0]).toBe('값\t표기\n사내 A\t사내에이')
  })

  it('빈 표라도 헤더는 복사된다', async () => {
    // 그것을 엑셀에 붙여 놓고 채워서 다시 가져오는 것이 이 기능의 쓰임이다.
    const user = userEvent.setup()
    show()
    await user.click(screen.getByRole('button', { name: /엑셀로 복사/ }))

    await waitFor(() => expect(copyText).toHaveBeenCalledWith('값\t표기'))
  })

  it('브라우저가 막으면 직접 복사할 길을 준다', async () => {
    // **버튼만 눌리고 아무 일도 안 일어나는 것이 가장 나쁘다.** HTTPS 가 아니면
    // 클립보드 API 가 아예 없다.
    vi.mocked(copyText).mockResolvedValueOnce(false)
    const user = userEvent.setup()
    show()
    await user.click(screen.getByRole('button', { name: /엑셀로 복사/ }))

    const box = await screen.findByLabelText<HTMLTextAreaElement>('복사할 표')
    expect(box.value).toBe('값\t표기')
  })
})
