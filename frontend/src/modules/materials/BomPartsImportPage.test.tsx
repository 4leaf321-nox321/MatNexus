/**
 * BOM 가져오기 — **재질로 재료를 찾되 고르는 것은 사람이다**(ADR 0064).
 *
 *   재질 열을 안 고르면 묻지 않는다      재료를 찾을 길이 없다
 *   여럿에 맞은 재질은 고르게 한다        고른 짝을 실어 다시 묻는다
 *   고르면 미리보기가 낡는다              본 것과 다른 재료에 줄이 들어가지 않게
 *   넣은 뒤 재료마다 몇 줄인지 말한다
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import BomPartsImportPage from '@/modules/materials/BomPartsImportPage'

const importBomParts = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    importBomParts: (...args: unknown[]) => importBomParts(...args),
    list: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 }),
  },
}))

function bomRow(index: number, material: string, status: string, extra: object = {}) {
  return {
    index,
    material,
    part: `파트 ${index}`,
    product: null,
    part_code: `C-${index}`,
    division: '가전',
    status,
    reason: status === 'new' ? null : '이유',
    material_id: status === 'new' ? 'm-secc' : null,
    material_name: status === 'new' ? 'SECC_-_1.0' : null,
    candidates: [],
    ...extra,
  }
}

const AMBIGUOUS = {
  candidates: [
    { id: 'm-a', name: 'SGCC_A_1.0' },
    { id: 'm-b', name: 'SGCC_B_1.0' },
  ],
}

function show() {
  return render(
    <MemoryRouter>
      <BomPartsImportPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  importBomParts.mockReset()
})

describe('BOM 가져오기', () => {
  it('재질 열을 안 고르면 미리보기를 못 누른다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(screen.getByLabelText('엑셀에서 복사한 범위'))
    await user.paste('품번\t품명\nC-1\t베이스')
    expect(screen.getByText('재질 열을 골라야 재료를 찾습니다.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '미리보기' })).toBeDisabled()
  })

  it('여럿에 맞은 재질을 고르고, 다시 본 뒤에 넣는다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(screen.getByLabelText('엑셀에서 복사한 범위'))
    await user.paste('품번\t품명\t재질\nC-1\t베이스\tSECC\nC-3\t브래킷\tSGCC')
    expect(screen.getByLabelText('3번 열')).toHaveValue('material')
    await user.type(screen.getByLabelText('사업부(칸이 빈 줄에)'), '가전')

    importBomParts.mockResolvedValueOnce({
      applied: false,
      counts: { new: 1, ambiguous: 1 },
      materials: [{ id: 'm-secc', name: 'SECC_-_1.0', new: 1 }],
      rows: [bomRow(0, 'SECC', 'new'), bomRow(1, 'SGCC', 'ambiguous', AMBIGUOUS)],
    })
    await user.click(screen.getByRole('button', { name: '미리보기' }))
    const pick = await screen.findByRole('combobox', { name: 'SGCC 재료' })
    expect(importBomParts).toHaveBeenLastCalledWith({
      rows: [
        { material: 'SECC', part: '베이스', product: null, part_code: 'C-1', division: null },
        { material: 'SGCC', part: '브래킷', product: null, part_code: 'C-3', division: null },
      ],
      division: '가전',
      source_ref: null,
      choices: {},
      dry_run: true,
    })
    expect(screen.getByRole('button', { name: '1줄 넣기' })).toBeEnabled()

    // 고르면 본 것이 낡는다 — 다시 보기 전에는 넣지 못한다.
    await user.selectOptions(pick, 'm-b')
    expect(screen.getByRole('button', { name: '넣기' })).toBeDisabled()
    expect(screen.getByText('바뀐 것이 있습니다 — 다시 미리보기를 누릅니다.')).toBeInTheDocument()

    importBomParts.mockResolvedValueOnce({
      applied: false,
      counts: { new: 2 },
      materials: [
        { id: 'm-secc', name: 'SECC_-_1.0', new: 1 },
        { id: 'm-b', name: 'SGCC_B_1.0', new: 1 },
      ],
      rows: [bomRow(0, 'SECC', 'new'), bomRow(1, 'SGCC', 'new')],
    })
    await user.click(screen.getByRole('button', { name: '미리보기' }))
    await waitFor(() =>
      expect(importBomParts).toHaveBeenLastCalledWith(
        expect.objectContaining({ choices: { SGCC: 'm-b' }, dry_run: true })
      )
    )
    // 고른 재질은 목록에 남는다 — 잘못 골랐으면 여기서 되돌린다.
    expect(await screen.findByRole('button', { name: '2줄 넣기' })).toBeEnabled()
    expect(screen.getByRole('combobox', { name: 'SGCC 재료' })).toHaveValue('m-b')

    importBomParts.mockResolvedValueOnce({
      applied: true,
      counts: { new: 2 },
      materials: [
        { id: 'm-secc', name: 'SECC_-_1.0', new: 1 },
        { id: 'm-b', name: 'SGCC_B_1.0', new: 1 },
      ],
      rows: [bomRow(0, 'SECC', 'new'), bomRow(1, 'SGCC', 'new')],
    })
    await user.click(screen.getByRole('button', { name: '2줄 넣기' }))
    expect(await screen.findByText('재료 2개에 2줄을 넣었습니다.')).toBeInTheDocument()
    expect(importBomParts).toHaveBeenLastCalledWith(expect.objectContaining({ dry_run: false }))
    const done = screen.getByText('재료 2개에 2줄을 넣었습니다.').parentElement as HTMLElement
    expect(within(done).getAllByRole('link').map((one) => one.getAttribute('href'))).toEqual([
      '/materials/m-secc?tab=parts',
      '/materials/m-b?tab=parts',
    ])
  })
})
