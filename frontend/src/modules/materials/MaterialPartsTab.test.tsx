/**
 * 적용 부품 탭 — **찾고 거르고 쪽을 나누는 것은 서버다**(ADR 0064).
 *
 *   거르기는 서버로 간다                사업부를 고르면 첫 쪽부터 다시 묻는다
 *   쪽을 넘기면 offset 이 간다          부품 50개 넘는 재료
 *   붙여넣기는 미리보기를 거친다         미리보기 없이는 못 넣고, 고치면 미리보기가 낡는다
 *   못 고치는 재료는 단추가 잠긴다        판정은 서버, 여기는 미리
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MaterialPartsTab } from '@/modules/materials/MaterialPartsTab'

const parts = vi.fn()
const addParts = vi.fn()
const removeParts = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    parts: (...args: unknown[]) => parts(...args),
    addParts: (...args: unknown[]) => addParts(...args),
    removeParts: (...args: unknown[]) => removeParts(...args),
    updatePart: vi.fn(),
  },
}))

vi.mock('@/modules/vocabulary/VocabularyField', () => ({
  VocabularyField: ({ label }: { label: string }) => <div>{label}</div>,
}))

function row(index: number, division = '가전') {
  return {
    id: `p${index}`,
    part: `파트 ${index}`,
    product: '세탁기',
    part_code: `WM-${index}`,
    division,
    note: null,
    source: 'bom',
    source_ref: '모델 X BOM',
    position: index,
    created_at: '2026-10-21T00:00:00Z',
  }
}

function page(items: ReturnType<typeof row>[], total = items.length) {
  return {
    items,
    total,
    limit: 50,
    offset: 0,
    divisions: [
      { value: '가전', count: 40 },
      { value: '전장', count: 20 },
    ],
    products: [{ value: '세탁기', count: 60 }],
  }
}

const onChanged = vi.fn()

function show(editable = true) {
  return render(
    <MemoryRouter>
      <MaterialPartsTab
        materialId="m1"
        editable={editable}
        lockedTitle={editable ? undefined : '다른 부서의 재료입니다'}
        onChanged={onChanged}
      />
    </MemoryRouter>
  )
}

beforeEach(() => {
  parts.mockReset()
  addParts.mockReset()
  removeParts.mockReset()
  onChanged.mockReset()
  parts.mockResolvedValue(page([row(1), row(2)], 60))
})

describe('적용 부품 탭', () => {
  it('줄을 그리고, 사업부를 고르면 서버에 다시 묻는다', async () => {
    const user = userEvent.setup()
    show()
    expect(await screen.findByText('WM-1')).toBeInTheDocument()
    expect(screen.getAllByText('모델 X BOM')).toHaveLength(2)

    // 고를 값은 서버가 센 것이다 — 그려진 뒤에 고른다.
    await screen.findByRole('option', { name: '전장 (20)' })
    parts.mockResolvedValue(page([row(41, '전장')], 20))
    await user.selectOptions(screen.getByLabelText('사업부'), '전장')
    expect(await screen.findByText('WM-41')).toBeInTheDocument()
    expect(parts).toHaveBeenLastCalledWith(
      'm1',
      expect.objectContaining({ division: '전장', offset: 0 })
    )
  })

  it('쪽을 넘기면 다음 쪽을 묻는다', async () => {
    const user = userEvent.setup()
    show()
    expect(await screen.findByText('1–50 / 60')).toBeInTheDocument()
    parts.mockResolvedValue({ ...page([row(51)], 60), offset: 50 })
    await user.click(screen.getByRole('button', { name: '다음' }))
    expect(await screen.findByText('WM-51')).toBeInTheDocument()
    // 찾기 칸의 지연(300ms)이 지나도 넘긴 쪽에 머문다 — 처음 그릴 때 돈 지연이 쪽을 0으로
    // 되돌려 첫 쪽으로 튀던 것(2026-10-22, 느린 머신의 전체 실행에서 드러남).
    await new Promise((resolve) => setTimeout(resolve, 400))
    expect(parts).toHaveBeenLastCalledWith('m1', expect.objectContaining({ offset: 50 }))
    expect(screen.getByText('WM-51')).toBeInTheDocument()
  })

  it('찾는 글자를 바꾸면 첫 쪽부터 서버에 묻는다', async () => {
    const user = userEvent.setup()
    show()
    expect(await screen.findByText('1–50 / 60')).toBeInTheDocument()
    parts.mockResolvedValue({ ...page([row(51)], 60), offset: 50 })
    await user.click(screen.getByRole('button', { name: '다음' }))
    await screen.findByText('WM-51')

    parts.mockResolvedValue(page([row(7)], 1))
    await user.type(screen.getByLabelText('찾기'), 'WM-7')
    expect(await screen.findByText('WM-7')).toBeInTheDocument()
    expect(parts).toHaveBeenLastCalledWith(
      'm1',
      expect.objectContaining({ q: 'WM-7', offset: 0 })
    )
  })

  it('붙여넣기는 미리보기를 거쳐야 넣고, 고치면 미리보기가 낡는다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByText('WM-1')
    await user.click(screen.getByRole('button', { name: '붙여넣기' }))

    const dialog = await screen.findByRole('dialog')
    const area = within(dialog).getByLabelText('엑셀에서 복사한 범위')
    await user.click(area)
    await user.paste('품번\t품명\tNo\nP-1\t도어 이너\t1\nP-2\t도어 아우터\t2')
    // 머리글로 짐작한 열이 보인다 — 고르기 상자로 고칠 수 있다.
    expect(within(dialog).getByLabelText('1번 열')).toHaveValue('part_code')
    expect(within(dialog).getByLabelText('3번 열')).toHaveValue('')
    expect(within(dialog).getByRole('button', { name: '넣기' })).toBeDisabled()

    addParts.mockResolvedValueOnce({
      applied: false,
      new: 1,
      exists: 1,
      errors: 0,
      rows: [
        { index: 0, part: '도어 이너', product: null, part_code: 'P-1', division: '가전', status: 'exists', reason: '이미 있는 줄입니다.' },
        { index: 1, part: '도어 아우터', product: null, part_code: 'P-2', division: '가전', status: 'new', reason: null },
      ],
    })
    await user.type(within(dialog).getByLabelText('사업부(칸이 빈 줄에)'), '가전')
    await user.click(within(dialog).getByRole('button', { name: '미리보기' }))
    expect(await within(dialog).findByText('이미 있는 줄입니다.')).toBeInTheDocument()
    expect(addParts).toHaveBeenLastCalledWith(
      'm1',
      [
        { part: '도어 이너', product: null, part_code: 'P-1', division: '가전', note: null },
        { part: '도어 아우터', product: null, part_code: 'P-2', division: '가전', note: null },
      ],
      { dryRun: true, sourceRef: null }
    )

    // 본 뒤에 고치면 본 것과 다른 것이 들어간다 — 다시 미리보기 전에는 못 넣는다.
    await user.type(within(dialog).getByLabelText('사업부(칸이 빈 줄에)'), '2')
    expect(within(dialog).getByRole('button', { name: '넣기' })).toBeDisabled()
    await user.type(within(dialog).getByLabelText('사업부(칸이 빈 줄에)'), '{Backspace}')

    addParts.mockResolvedValueOnce({ applied: true, new: 1, exists: 1, errors: 0, rows: [] })
    await user.click(within(dialog).getByRole('button', { name: '1줄 넣기' }))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(addParts).toHaveBeenLastCalledWith('m1', expect.any(Array), {
      dryRun: false,
      sourceRef: null,
    })
    expect(await screen.findByText('1줄을 넣었습니다. 이미 있던 1줄은 넘겼습니다.')).toBeInTheDocument()
  })

  it('고른 줄을 지운다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('checkbox', { name: '파트 1 선택' }))
    removeParts.mockResolvedValueOnce({ removed: 1 })
    await user.click(screen.getByRole('button', { name: '고른 1줄 지우기' }))
    const confirm = await screen.findByRole('dialog')
    expect(confirm).toHaveTextContent('고른 1줄을 지웁니다')
    await user.click(within(confirm).getByRole('button', { name: '삭제' }))
    await waitFor(() => expect(removeParts).toHaveBeenCalledWith('m1', ['p1']))
    expect(await screen.findByText('1줄을 지웠습니다.')).toBeInTheDocument()
  })

  it('못 고치는 재료는 넣기 · 고치기를 잠근다', async () => {
    show(false)
    await screen.findByText('WM-1')
    expect(screen.getByRole('button', { name: '붙여넣기' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '한 줄 추가' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '파트 1 고치기' })).toBeDisabled()
  })

  it('줄이 없으면 어떻게 넣는지 말한다', async () => {
    parts.mockResolvedValue(page([], 0))
    show()
    expect(await screen.findByText('적용 부품이 없습니다.')).toBeInTheDocument()
  })
})
