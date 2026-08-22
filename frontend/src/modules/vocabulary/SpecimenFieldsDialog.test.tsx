/**
 * 치수 칸 정의 — **분류의 기본 칸이냐 이 규격의 칸이냐, 키는 계약이다.**
 *
 * 같은 창이 두 자리에서 쓰인다. 분류 값에서 열면 그 분류의 규격 **전부**가 갖는
 * 기본 칸을 정하고, 규격 값에서 열면 그 규격**만** 갖는 칸을 더한다. 가르는 것은
 * 상위 값이 있느냐다 — 화면에 축 slug 를 박지 않는다.
 *
 * 이미 저장된 치수가 칸의 키로 들어 있다. 키를 바꾸면 그 값들이 갈 곳을 잃으므로
 * 저장된 칸의 키는 못 고친다. 칸을 빼는 것은 되고, 그때 값은 남는다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SpecimenFieldsDialog } from '@/modules/vocabulary/SpecimenFieldsDialog'
import type { Term } from '@/modules/vocabulary/api'

const termFields = vi.fn()
const saveCategoryFields = vi.fn()
const update = vi.fn()

vi.mock('@/modules/vocabulary/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/vocabulary/api')>()),
  vocabularyApi: {
    termFields: (...args: unknown[]) => termFields(...args),
    saveCategoryFields: (...args: unknown[]) => saveCategoryFields(...args),
    update: (...args: unknown[]) => update(...args),
  },
}))

const field = (key: string, label: string, inherited = true) => ({
  key,
  label,
  dimension: 'length',
  si_unit: 'm',
  is_required: key === 'gauge_length',
  help: null,
  inherited,
})

/** 상위가 없는 값 = **시편 분류.** 기본 칸을 고친다. */
const CATEGORY = {
  id: 'cat-1',
  value: '인장',
  parent_value: null,
  usage_count: 2,
  status: 'active',
  attributes: {},
  extra_fields: [],
} as unknown as Term

/** 상위가 있는 값 = **시편 규격.** 자기만의 칸을 더한다. */
const STANDARD = {
  id: 'std-1',
  value: 'ASTM E8 R1',
  parent_value: '인장',
  usage_count: 0,
  status: 'active',
  attributes: {},
  extra_fields: [
    {
      key: 'diameter',
      label: '직경',
      dimension: 'length',
      si_unit: 'm',
      is_required: true,
      help: null,
    },
  ],
} as unknown as Term

function show(term: Term) {
  return render(
    <SpecimenFieldsDialog
      slug="specimen_standard"
      term={term}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />
  )
}

describe('치수 칸 정의', () => {
  beforeEach(() => {
    // 분류에서 보면 자기 칸이라 `inherited` 가 false, 규격에서 보면 true 다.
    termFields.mockImplementation((_slug: string, termId: string) =>
      termId === CATEGORY.id
        ? Promise.resolve([
            field('gauge_length', '게이지 길이', false),
            field('total_length', '전체 길이', false),
          ])
        : // 규격에서 열면 분류가 준 칸(inherited)과 이 규격의 칸이 함께 온다.
          Promise.resolve([
            field('gauge_length', '게이지 길이', true),
            field('total_length', '전체 길이', true),
            field('diameter', '직경', false),
          ])
    )
    saveCategoryFields.mockReset()
    saveCategoryFields.mockResolvedValue([])
    update.mockReset()
    update.mockResolvedValue(STANDARD)
  })

  it('저장된 칸의 키는 못 고친다 — 계약이라서', async () => {
    show(CATEGORY)
    const key = await screen.findByLabelText('1번 칸 키')
    expect(key).toBeDisabled()
    expect(key).toHaveValue('gauge_length')
    // 이름은 얼마든지 고쳐도 된다.
    expect(screen.getByLabelText('1번 칸 이름')).not.toBeDisabled()
  })

  it('새 칸은 이름에서 키를 만들어 준다', async () => {
    const user = userEvent.setup()
    show(CATEGORY)
    await screen.findByLabelText('1번 칸 이름')

    await user.click(screen.getByRole('button', { name: /칸 더하기/ }))
    await user.type(screen.getByLabelText('3번 칸 이름'), 'grip length')

    expect(screen.getByLabelText('3번 칸 키')).toHaveValue('grip_length')
  })

  it('한글만 치면 키를 지어내지 않는다', async () => {
    // `field_1` 같은 것이 쌓이면 나중에 그게 무엇인지 알 방법이 없다.
    const user = userEvent.setup()
    show(CATEGORY)
    await screen.findByLabelText('1번 칸 이름')

    await user.click(screen.getByRole('button', { name: /칸 더하기/ }))
    await user.type(screen.getByLabelText('3번 칸 이름'), '그립부 길이')

    expect(screen.getByLabelText('3번 칸 키')).toHaveValue('')
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled()
  })

  it('분류에서는 기본 칸을 저장한다', async () => {
    const user = userEvent.setup()
    show(CATEGORY)
    await screen.findByLabelText('1번 칸 이름')

    await user.click(screen.getByRole('button', { name: '1번 칸 빼기' }))
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(saveCategoryFields).toHaveBeenCalled())
    const [, , fields] = saveCategoryFields.mock.calls[0]
    expect(fields.map((item: { key: string }) => item.key)).toEqual(['total_length'])
    // 화면 전용 표시(`saved`)는 안 보낸다.
    expect('saved' in fields[0]).toBe(false)
  })

  it('규격에서는 그 규격만의 칸을 저장한다', async () => {
    // **분류의 기본 칸을 건드리지 않는다.** 그건 그 분류의 규격 전부에 영향을 준다.
    const user = userEvent.setup()
    show(STANDARD)
    await screen.findByLabelText('1번 칸 이름')
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    expect(saveCategoryFields).not.toHaveBeenCalled()
    const [, , body] = update.mock.calls[0]
    expect(body.extra_fields.map((item: { key: string }) => item.key)).toEqual(['diameter'])
  })

  it('규격에서는 분류가 준 칸을 못 지운다고 말한다', async () => {
    show(STANDARD)
    // `<b>` 안에 조각이 따로 잡히므로 문단 전체를 잡는다.
    const notice = (await screen.findByText(/여기서는 못 지웁니다/)).closest('p')
    expect(notice).toHaveTextContent('게이지 길이')
  })

  it('칸을 빼면 값이 어떻게 되는지 말한다', async () => {
    const user = userEvent.setup()
    show(CATEGORY)
    await screen.findByLabelText('2번 칸 이름')

    await user.click(screen.getByRole('button', { name: '2번 칸 빼기' }))

    // **"뺀다" 만으로는 부족하다.** 이미 적어 둔 치수가 어떻게 되는지가 궁금하다.
    const notice = (await screen.findByText(/화면에 안 보이게 됩니다/)).closest('p')
    expect(notice).toHaveTextContent('전체 길이')
    expect(notice).toHaveTextContent('되살리면 다시 나옵니다')
  })

  it('길이가 아닌 차원도 만든다', async () => {
    // **단면적 칸을 길이로 만들면 화면이 mm 로 환산해 10의 6제곱 배 틀린다.**
    // D3039 탭 베벨각은 각도, D5766 의 w/d 는 무차원 — 규격표가 요구한다.
    const user = userEvent.setup()
    show(STANDARD)
    await screen.findByLabelText('1번 칸 이름')
    await user.click(screen.getByRole('button', { name: '칸 더하기' }))

    const row = screen.getAllByLabelText(/번 칸 이름$/).length
    await user.type(screen.getByLabelText(`${row}번 칸 이름`), 'section area')
    await user.selectOptions(screen.getByLabelText(`${row}번 칸 차원`), 'area')
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    const [, , body] = update.mock.calls[0]
    const added = body.extra_fields.at(-1)
    expect(added.dimension).toBe('area')
    // 저장 단위는 고르는 것이 아니라 차원이 정한다.
    expect(added.si_unit).toBe('m2')
  })

  it('지운 칸은 다시 열어도 안 돌아온다', async () => {
    // **목록에서 들고 온 옛 객체를 읽고 있었다.** 규격 쪽 행을
    // `term.extra_fields` 에서 만들었는데 그 객체는 저장 뒤에도 옛 값이라,
    // 칸을 지우고 저장한 뒤 다시 열면 지운 칸이 되살아났다.
    // 서버는 직경을 이미 지웠는데, `term.extra_fields` 에는 아직 남아 있다.
    termFields.mockResolvedValue([field('gauge_length', '게이지 길이', true)])
    show(STANDARD)

    await waitFor(() => expect(termFields).toHaveBeenCalled())
    expect(screen.queryByDisplayValue('직경')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('1번 칸 이름')).not.toBeInTheDocument()
  })

  it('차원을 전부 고를 수 있다', async () => {
    // 좁혀 둘 근거가 없었다 — 시편에 붙는 값이 길이·면적·각도로 끝난다는
    // 보장이 없다.
    show(STANDARD)
    const picker = await screen.findByLabelText<HTMLSelectElement>('1번 칸 차원')
    const values = [...picker.options].map((option) => option.value)
    expect(values).toEqual(expect.arrayContaining(['length', 'area', 'angle', 'mass', 'stress']))
  })

  it('저장된 칸의 차원을 바꾸면 값이 어떻게 읽히는지 말한다', async () => {
    // 두께 0.001 을 면적으로 바꾸면 그 값이 0.001 m² 로 읽힌다 — 오류 없이.
    const user = userEvent.setup()
    show(STANDARD)
    await user.selectOptions(await screen.findByLabelText('1번 칸 차원'), 'area')
    expect(await screen.findAllByText(/다시 확인하세요/)).not.toHaveLength(0)
  })
})
