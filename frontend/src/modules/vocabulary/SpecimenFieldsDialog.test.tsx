/**
 * 치수 칸 정의 — **키는 계약이고, 뺀 칸의 값은 안 지운다.**
 *
 * 이미 저장된 규격의 치수가 칸의 키로 들어 있다. 키를 바꾸면 그 값들이 갈 곳을
 * 잃으므로 저장된 칸의 키는 못 고친다. 칸을 빼는 것은 되고, 그때 값은 남는다 —
 * 화면에서 사라질 뿐이라 되살리면 다시 보인다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SpecimenFieldsDialog } from '@/modules/vocabulary/SpecimenFieldsDialog'

const specimenFields = vi.fn()
const saveSpecimenFields = vi.fn()

vi.mock('@/modules/vocabulary/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/vocabulary/api')>()),
  vocabularyApi: {
    specimenFields: (...args: unknown[]) => specimenFields(...args),
    saveSpecimenFields: (...args: unknown[]) => saveSpecimenFields(...args),
  },
}))

const EXISTING = [
  {
    key: 'gauge_length',
    label: '게이지 길이',
    dimension: 'length',
    si_unit: 'm',
    is_required: true,
    help: null,
    sort_order: 0,
  },
  {
    key: 'shoulder_radius',
    label: '어깨 반경',
    dimension: 'length',
    si_unit: 'm',
    is_required: false,
    help: null,
    sort_order: 10,
  },
]

function show() {
  return render(
    <SpecimenFieldsDialog
      slug="specimen_standard"
      kind="tensile"
      kindLabel="인장시험"
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />
  )
}

describe('치수 칸 정의', () => {
  beforeEach(() => {
    specimenFields.mockResolvedValue(EXISTING)
    saveSpecimenFields.mockReset()
    saveSpecimenFields.mockResolvedValue(EXISTING)
  })

  it('저장된 칸의 키는 못 고친다 — 계약이라서', async () => {
    show()
    const key = await screen.findByLabelText('1번 칸 키')
    expect(key).toBeDisabled()
    expect(key).toHaveValue('gauge_length')
    // 이름은 얼마든지 고쳐도 된다.
    expect(screen.getByLabelText('1번 칸 이름')).not.toBeDisabled()
  })

  it('새 칸은 이름에서 키를 만들어 준다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByLabelText('1번 칸 이름')

    await user.click(screen.getByRole('button', { name: /칸 더하기/ }))
    await user.type(screen.getByLabelText('3번 칸 이름'), 'grip length')

    expect(screen.getByLabelText('3번 칸 키')).toHaveValue('grip_length')
  })

  it('한글만 치면 키를 지어내지 않는다', async () => {
    // `field_1` 같은 것이 쌓이면 나중에 그게 무엇인지 알 방법이 없다.
    const user = userEvent.setup()
    show()
    await screen.findByLabelText('1번 칸 이름')

    await user.click(screen.getByRole('button', { name: /칸 더하기/ }))
    await user.type(screen.getByLabelText('3번 칸 이름'), '그립부 길이')

    expect(screen.getByLabelText('3번 칸 키')).toHaveValue('')
    // 키가 비면 저장도 막는다.
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled()
  })

  it('칸을 빼면 값이 어떻게 되는지 말한다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByLabelText('2번 칸 이름')

    await user.click(screen.getByRole('button', { name: '2번 칸 빼기' }))

    // **"뺀다" 만으로는 부족하다.** 이미 적어 둔 치수가 어떻게 되는지가 궁금하다.
    // `<b>` 안에 이름만 든 조각이 따로 잡히므로 문단 전체를 잡는다.
    const notice = (await screen.findByText(/화면에 안 보이게 됩니다/)).closest('p')
    expect(notice).toHaveTextContent('어깨 반경')
    expect(notice).toHaveTextContent('되살리면 다시 나옵니다')
  })

  it('통째로 보낸다 — 순서가 곧 화면의 순서다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByLabelText('1번 칸 이름')

    await user.click(screen.getByRole('button', { name: '1번 칸 빼기' }))
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(saveSpecimenFields).toHaveBeenCalled())
    const [, , fields] = saveSpecimenFields.mock.calls[0]
    expect(fields.map((item: { key: string }) => item.key)).toEqual(['shoulder_radius'])
    // 화면 전용 표시(`saved`)는 안 보낸다.
    expect('saved' in fields[0]).toBe(false)
  })
})
