/**
 * 시편 고르기 — **여기서 만들 수도 있어야 한다.**
 *
 * 실사용에서 나온 것이다. 「시험 등록」이 재료·시료·시편을 고르기만 해서, 새 판을
 * 받아 시편을 뜬 사람이 *"재료 상세에서 먼저 만드세요"* 를 보고 다른 화면에
 * 다녀와야 했다. 일괄 등록에는 이미 새 시료·새 시편이 있었으므로 **한 건 올릴
 * 때가 오히려 불편했다.**
 *
 * 여기서 지키는 것은 셋이다.
 *
 *   세 층 모두 만들 수 있다     재료에서 막히면 나머지도 못 간다
 *   만든 것을 곧바로 고른다     목록을 다시 받아 찾게 하면 방금 만든 것이 안 보인다
 *   왜 잠겼는지 말한다          흐리기만 하면 고장으로 보인다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SpecimenPicker } from '@/modules/materials/SpecimenPicker'

const samples = vi.fn()
const specimens = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    samples: (...args: unknown[]) => samples(...args),
    specimens: (...args: unknown[]) => specimens(...args),
  },
}))

/** 재료 검색은 서버에 묻는다. 이 시험이 보는 것은 그게 아니라 만들기 경로다. */
vi.mock('@/modules/materials/MaterialPicker', () => ({
  MaterialPicker: ({ onSelect }: { onSelect: (m: unknown) => void }) => (
    <button onClick={() => onSelect({ id: 'm1', record_name: 'DP600 1.2t' })}>재료 고르기</button>
  ),
}))

/** 세 다이얼로그는 각자 시험이 있다. 여기서는 **열리는지와 결과를 받는지**만 본다. */
vi.mock('@/modules/materials/NewMaterialDialog', () => ({
  NewMaterialDialog: ({
    open,
    onDone,
  }: {
    open: boolean
    onDone: (m: unknown) => void
  }) =>
    open ? (
      <button onClick={() => onDone({ id: 'm9', record_name: '새 재료' })}>재료 만들기</button>
    ) : null,
}))
vi.mock('@/modules/materials/NewSampleDialog', () => ({
  NewSampleDialog: ({
    open,
    onCreated,
  }: {
    open: boolean
    onCreated: (s: unknown) => void
  }) =>
    open ? (
      <button onClick={() => onCreated({ id: 's9', seq_no: 9, lot_no: 'L9', material_id: 'm1' })}>
        시료 만들기
      </button>
    ) : null,
}))
vi.mock('@/modules/materials/NewSpecimenDialog', () => ({
  NewSpecimenDialog: ({
    open,
    onDone,
  }: {
    open: boolean
    onDone: (s: unknown) => void
  }) =>
    open ? (
      <button onClick={() => onDone({ id: 'p9', orientation: 'MD', seq_no: 9 })}>
        시편 만들기
      </button>
    ) : null,
}))

beforeEach(() => {
  vi.clearAllMocks()
  samples.mockResolvedValue([])
  specimens.mockResolvedValue([])
})

/** 드롭다운을 열고 「새로 만들기」 줄을 누른다. */
async function openList(label: string, name: RegExp) {
  await userEvent.click(await screen.findByRole('combobox', { name: label }))
  await userEvent.click(await screen.findByRole('option', { name }))
}

async function pickMaterial() {
  await userEvent.click(screen.getByRole('button', { name: '재료 고르기' }))
  await waitFor(() => expect(samples).toHaveBeenCalled())
}

describe('시편 고르기', () => {
  it('재료를 고르기 전에도 새 재료를 만들 수 있다', async () => {
    // **여기서 막히면 나머지 두 층도 못 간다.**
    render(<SpecimenPicker onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: /\+ 새 재료/ })).toBeEnabled()
  })

  it('만든 재료를 곧바로 고른다', async () => {
    render(<SpecimenPicker onChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /\+ 새 재료/ }))
    await userEvent.click(await screen.findByRole('button', { name: '재료 만들기' }))
    // 고른 재료의 시료를 곧바로 받으러 간다 — 사람이 다시 고를 필요가 없다.
    await waitFor(() => expect(samples).toHaveBeenCalledWith('m9'))
  })

  it('만든 시료를 곧바로 고른다', async () => {
    render(<SpecimenPicker onChange={vi.fn()} />)
    await pickMaterial()
    await openList('시료', /새 시료 만들기/)
    await userEvent.click(await screen.findByRole('button', { name: '시료 만들기' }))
    await waitFor(() => expect(specimens).toHaveBeenCalledWith('s9'))
  })

  it('만든 시편이 곧 선택 결과다', async () => {
    // 시편은 이 컴포넌트의 최종 결과물이다. 만들었으면 그것이 골라진 것이다.
    const onChange = vi.fn()
    samples.mockResolvedValue([{ id: 's1', seq_no: 1, lot_no: null, material_id: 'm1' }])
    render(<SpecimenPicker onChange={onChange} />)
    await pickMaterial()
    // 시료가 하나면 그것은 골라 준다 — 시편만 사람이 고른다.
    await waitFor(() => expect(specimens).toHaveBeenCalled())
    await openList('시편', /새 시편 만들기/)
    await userEvent.click(await screen.findByRole('button', { name: '시편 만들기' }))
    expect(onChange).toHaveBeenCalledWith({ id: 'p9', orientation: 'MD', seq_no: 9 })
  })

  it('앞 단계를 안 골랐으면 잠근다', async () => {
    // **만들기가 목록 안으로 들어갔다**(v1.118.0). 밑에 작은 링크로 두었더니
    // 사람이 못 보고 지나쳐서, 새 판이 왔는데도 옛 시료에 붙이게 됐다.
    render(<SpecimenPicker onChange={vi.fn()} />)
    expect(screen.getByRole('combobox', { name: /시료/ })).toBeDisabled()
    expect(screen.getByRole('combobox', { name: /시편/ })).toBeDisabled()
  })

  it('말없이 시편을 고르지 않는다', async () => {
    // **여기가 이 변경의 요점이다.** 시편이 하나뿐이면 그것을 골라 주고 있었는데,
    // 그래서 둘째 파일이 자동으로 첫 시편에 붙었다 — 실사용에서 나왔다.
    //
    // 시편을 잘못 짚으면 되돌릴 수 없다. 시험은 만들 때 그 시편 id 에 묶인다.
    const onChange = vi.fn()
    samples.mockResolvedValue([{ id: 's1', seq_no: 1, lot_no: 'L1', material_id: 'm1' }])
    specimens.mockResolvedValue([
      { id: 'p1', orientation: 'MD', seq_no: 1, test_run_count: 1 },
    ])
    render(<SpecimenPicker onChange={onChange} />)
    await pickMaterial()
    await waitFor(() => expect(specimens).toHaveBeenCalled())

    expect(onChange).not.toHaveBeenCalledWith(expect.objectContaining({ id: 'p1' }))
  })

  it('목록 안에서 새로 만든다', async () => {
    samples.mockResolvedValue([{ id: 's1', seq_no: 1, lot_no: 'L1', material_id: 'm1' }])
    render(<SpecimenPicker onChange={vi.fn()} />)
    await pickMaterial()

    await userEvent.click(await screen.findByRole('combobox', { name: /시료/ }))
    expect(await screen.findByRole('option', { name: /새 시료 만들기/ })).toBeInTheDocument()
  })

  it('비었을 때 다른 화면으로 보내지 않는다', async () => {
    // 예전 안내는 "재료 상세에서 시료와 시편을 먼저 만드세요" 였다 — 파일을 들고
    // 온 사람에게 왕복을 시키는 말이다.
    render(<SpecimenPicker onChange={vi.fn()} />)
    await pickMaterial()
    expect(await screen.findByText(/이 재료에 시료가 없습니다/)).toBeInTheDocument()
    expect(screen.queryByText(/재료 상세에서/)).not.toBeInTheDocument()
  })
})
