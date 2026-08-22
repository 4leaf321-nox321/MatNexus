/**
 * 시편 규격 치수 — **칸을 화면이 정하지 않는다.**
 *
 * 칸은 두 층이다 — 분류가 준 기본 칸과, 이 규격만의 칸. 인장 평판은 폭·두께를
 * 갖고 환봉은 직경을 갖는다. 그 목록을 화면에 적으면 분류를 추가할 때 두 곳을
 * 고쳐야 하고, 그러면 한 곳을 빠뜨린다.
 *
 * 그리고 **저장은 SI, 화면은 mm** 다. 규격서가 mm 로 적혀 있는데 `0.025` 를 치라고
 * 하면 누군가 `25` 를 치고, 그러면 변형률이 1000배 틀린다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SpecimenStandardDialog } from '@/modules/vocabulary/SpecimenStandardDialog'
import type { Term } from '@/modules/vocabulary/api'

const termFields = vi.fn()
const crossSections = vi.fn()
const update = vi.fn()

vi.mock('@/modules/vocabulary/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/vocabulary/api')>()),
  vocabularyApi: {
    termFields: (...args: unknown[]) => termFields(...args),
    crossSections: () => crossSections(),
    update: (...args: unknown[]) => update(...args),
    saveCategoryFields: vi.fn(),
  },
}))

const field = (key: string, label: string, required = false, inherited = true) => ({
  key,
  label,
  dimension: 'length',
  si_unit: 'm',
  is_required: required,
  help: null,
  inherited,
})

/** 분류가 준 기본 칸 + 이 규격만의 칸(어깨 반경). */
const FIELDS = [
  field('gauge_length', '게이지 길이', true),
  field('width', '평행부 폭', true),
  field('thickness', '두께', false),
  field('shoulder_radius', '어깨 반경', false, false),
]

const TERM = {
  id: 'term-1',
  value: 'ASTM E8 subsize',
  parent_value: '인장',
  usage_count: 3,
  status: 'active',
  // **저장은 SI 다** — 25 mm 는 0.025 m 로 담긴다.
  attributes: { gauge_length: 0.025, width: 0.006 },
  extra_fields: [],
} as unknown as Term

function show(term: Term = TERM) {
  return render(
    <SpecimenStandardDialog
      slug="specimen_standard"
      term={term}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />
  )
}

describe('시편 규격 치수', () => {
  beforeEach(() => {
    termFields.mockResolvedValue(FIELDS)
    crossSections.mockResolvedValue([
      { key: 'rectangle', label: '평판 (폭 곱하기 두께)', needs: ['width', 'thickness'], help: null },
      { key: 'circle', label: '환봉 (직경)', needs: ['diameter'], help: null },
    ])
    update.mockReset()
    update.mockResolvedValue(TERM)
  })

  it('분류의 기본 칸과 이 규격의 칸이 함께 뜬다', async () => {
    show()
    expect(await screen.findByLabelText('게이지 길이')).toBeInTheDocument()
    expect(screen.getByLabelText('어깨 반경')).toBeInTheDocument()
  })

  it('어느 쪽 칸인지 보인다 — 지우려면 갈 곳이 다르다', async () => {
    show()
    await screen.findByLabelText('게이지 길이')
    // 이 규격의 칸만 표시가 붙는다. 분류가 준 칸은 분류에서 고쳐야 한다.
    expect(screen.getByText('어깨 반경').closest('label')).toHaveTextContent('· 이 규격')
    expect(screen.getByText('게이지 길이').closest('label')).not.toHaveTextContent('· 이 규격')
  })

  it('어느 분류에 속하는지 말한다', async () => {
    show()
    expect(await screen.findByText(/인장/)).toBeInTheDocument()
  })

  it('저장된 SI 를 화면 단위로 보여 준다', async () => {
    show()
    // 0.025 m 를 25 로 보여 준다. `0.025` 를 그대로 띄우면 아무도 못 읽는다.
    await waitFor(() => expect(screen.getByLabelText('게이지 길이')).toHaveValue('25'))
    expect(screen.getByLabelText('평행부 폭')).toHaveValue('6')
  })

  it('입력한 mm 를 SI 로 바꿔 보낸다', async () => {
    const user = userEvent.setup()
    show()
    await user.type(await screen.findByLabelText('어깨 반경'), '5')
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    const [, , body] = update.mock.calls[0]
    // 5 mm → 0.005 m
    expect(body.attributes.shoulder_radius).toBeCloseTo(0.005, 9)
    expect(body.attributes.gauge_length).toBeCloseTo(0.025, 9)
  })

  it('빈 칸은 안 보낸다 — 0 이 아니라 없는 것이다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByLabelText('어깨 반경')
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    const [, , body] = update.mock.calls[0]
    expect('shoulder_radius' in body.attributes).toBe(false)
  })

  it('칸이 하나도 없으면 무엇을 하면 되는지 말한다', async () => {
    termFields.mockResolvedValue([])
    show({ ...TERM, parent_value: null, attributes: {} } as Term)
    expect(await screen.findByText(/아직 칸이 없습니다/)).toBeInTheDocument()
  })

  it('요구 칸이 없는 단면적 식은 못 고른다', async () => {
    // **골라 봐야 늘 실패한다.** 사람은 그 이유를 처리 화면에서 만나게 되고,
    // 거기엔 "왜 단면적이 안 나오지" 밖에 안 적혀 있다.
    show()
    await screen.findByLabelText('게이지 길이')
    // 이 규격에는 폭·두께가 있고 직경은 없다.
    expect(screen.getByRole('button', { name: /평판/ })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: /환봉/ })).toBeDisabled()
  })

  it('안 고르면 옛 규칙으로 돈다고 말한다', async () => {
    show()
    await screen.findByLabelText('게이지 길이')
    expect(screen.getByText(/옛 규칙/)).toBeInTheDocument()
  })

  it('고른 식을 함께 보낸다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByLabelText('게이지 길이')
    await user.click(screen.getByRole('button', { name: /평판/ }))
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    const [, , body] = update.mock.calls[0]
    expect(body.cross_section).toBe('rectangle')
  })

  it('못 고르는 식은 이유를 화면에 적는다', async () => {
    // **회색 버튼만 보이면 막다른 길이다.** 전에는 마우스를 올려야만 보였고,
    // 칸이 하나도 없는 규격에서는 모든 식이 회색이라 할 일을 알 수 없었다.
    show()
    await screen.findByLabelText('게이지 길이')
    const notice = await screen.findByText(/못 고릅니다/)
    expect(notice.closest('p')).toHaveTextContent('diameter')
    expect(notice.closest('p')).toHaveTextContent('이 규격만의 칸')
  })
})
