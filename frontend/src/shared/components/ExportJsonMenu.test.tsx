/**
 * 「JSON 내보내기」 메뉴 — **고른 계가 요청과 파일 이름에 실리는가**(ADR 0036).
 *
 * 재료·문헌 내보내기는 해석 연동으로 나가는 파일이다. 계를 잘못 실으면 받는 쪽은 오류
 * 없이 1000배 틀린 숫자를 읽는다. 그래서 셋을 본다:
 *
 *   1. 안 고르면 **서버가 기본이라 한 것** — 화면이 'si' 를 적어 두지 않는다
 *   2. 고른 계가 실리고 파일 이름이 따라 바뀐다 — 부서가 만든 계도
 *   3. 계 목록을 못 받았으면 받지 않는다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ExportJsonMenu } from '@/shared/components/ExportJsonMenu'

const list = vi.fn()

vi.mock('@/shared/api/unitSystems', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/unitSystems')>()),
  unitSystemsApi: { list: () => list() },
}))

//: **기본이 첫째가 아니다.** 순서로 고르면 통과해 버려서 `is_default` 를 보는지 알 수 없다.
const SYSTEMS = [
  { key: 'si', label: 'SI (kg · m · s · Pa)', is_default: false },
  { key: 'mm_n_tonne', label: 'mm · N · tonne (MPa)', is_default: true },
  { key: 'mm_ms_kg', label: 'mm · ms · kg (GPa)', is_default: false },
]

const exported = vi.fn()

beforeEach(() => {
  exported.mockReset()
  list.mockReset()
  list.mockResolvedValue(SYSTEMS)
})

async function open(stem = 'matnexus_materials') {
  render(<ExportJsonMenu stem={stem} busy={false} onExport={exported} />)
  await userEvent.click(screen.getByRole('button', { name: /JSON 내보내기/ }))
}

describe('단위계를 고르고 받는다', () => {
  it('안 고르면 서버가 기본이라 한 것으로 받는다', async () => {
    await open()
    await userEvent.click(
      await screen.findByRole('menuitem', { name: /matnexus_materials_mm_n_tonne\.json/ })
    )
    await waitFor(() => expect(exported).toHaveBeenCalled())
    const [system, filename] = exported.mock.calls[0] as [{ key: string }, string]
    expect(system.key).toBe('mm_n_tonne')
    expect(filename).toBe('matnexus_materials_mm_n_tonne.json')
  })

  it('고른 계가 실리고 파일 이름이 따라 바뀐다 — 부서가 만든 계도', async () => {
    // 이름이 계를 말해야 두 계가 한 폴더에 섞여도 열지 않고 가려진다.
    await open()
    await userEvent.click(await screen.findByRole('button', { name: /mm · ms · kg/ }))
    await userEvent.click(
      screen.getByRole('menuitem', { name: /matnexus_materials_mm_ms_kg\.json/ })
    )
    await waitFor(() => expect(exported).toHaveBeenCalled())
    const [system, filename] = exported.mock.calls[0] as [{ key: string }, string]
    expect(system.key).toBe('mm_ms_kg')
    expect(filename).toBe('matnexus_materials_mm_ms_kg.json')
  })

  it('계 목록을 못 받았으면 받지 않는다', async () => {
    // 받으면 서버 기본으로 나가는데, 화면은 그것이 어느 계인지 말할 수 없다.
    list.mockReturnValue(new Promise(() => {}))
    await open('matnexus_catalog')
    const item = await screen.findByRole('menuitem', { name: /JSON 받기/ })
    expect(item).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText('단위계를 읽는 중…')).toBeInTheDocument()
    await userEvent.click(item)
    expect(exported).not.toHaveBeenCalled()
  })
})
