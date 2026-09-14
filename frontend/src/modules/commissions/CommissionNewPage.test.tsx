/**
 * 새 측정 의뢰 — **왜 못 보내는지 화면이 말한다.**
 *
 *   처음엔 단추가 잠겨 있고 그 옆에 「아직 필요한 것: 제목 · 목적 · 시료 · 받는 부서」 가 선다
 *   채우는 대로 목록에서 빠지고, 다 채우면 문구가 사라지고 단추가 열린다
 *   새 재료로 바꾸면 「시료」 대신 「새 재료가 무엇인지」 를 묻는다
 *   종류 미정 항목은 물성 이름이 없으면 「n번 항목의 시험 종류 또는 물성 이름」
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CommissionNewPage from '@/modules/commissions/CommissionNewPage'

const create = vi.fn()

vi.mock('@/modules/commissions/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/commissions/api')>()),
  commissionsApi: { create: (...args: unknown[]) => create(...args) },
}))

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: {
    types: () =>
      Promise.resolve([{ key: 'tensile', label: '인장시험', abbr: 'TEN', conditions: [], channels: [] }]),
  },
}))

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: { blocks: () => Promise.resolve([]) },
}))

vi.mock('@/modules/workspaces/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/workspaces/api')>()),
  workspacesApi: {
    options: () => Promise.resolve([{ slug: 'reliability', name: '신뢰성그룹', path: '품질센터 / 신뢰성그룹', depth: 1 }]),
  },
}))

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: { list: vi.fn(), get: vi.fn(), samples: () => Promise.resolve([]) },
}))

async function show() {
  render(
    <MemoryRouter initialEntries={['/commissions/new']}>
      <CommissionNewPage />
    </MemoryRouter>
  )
  await screen.findByRole('button', { name: '의뢰' })
}

describe('새 측정 의뢰', () => {
  beforeEach(() => create.mockReset())

  it('처음엔 무엇이 비어서 못 보내는지 말하고, 채우면 빠진다', async () => {
    await show()
    const submit = screen.getByRole('button', { name: '의뢰' })
    expect(submit).toBeDisabled()
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('제목 · 목적 · 시료 (재료를 찾아 고르기) · 받는 부서')
    // 단추에 마우스를 올려도 같은 말.
    expect(submit).toHaveAttribute('title', expect.stringContaining('제목'))

    const user = userEvent.setup()
    await user.type(screen.getByLabelText('제목'), 'SECC 인장')
    expect(status).not.toHaveTextContent('제목')
    expect(status).toHaveTextContent('목적 · 시료')
    await user.selectOptions(screen.getByLabelText('받는 부서'), 'reliability')
    expect(status).not.toHaveTextContent('받는 부서')
  })

  it('새 재료로 바꾸면 시료 대신 새 재료가 무엇인지를 묻고, 종류 미정 항목은 물성 이름을 묻는다', async () => {
    await show()
    const user = userEvent.setup()
    await user.click(screen.getByLabelText('새 재료 (아직 등록 전)'))
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('새 재료가 무엇인지')
    expect(status).not.toHaveTextContent('시료 (재료를 찾아 고르기)')

    await user.selectOptions(screen.getByLabelText('1번 시험 종류'), '')
    expect(status).toHaveTextContent('1번 항목의 시험 종류 또는 물성 이름')
    await user.type(screen.getByLabelText(/무엇을 잴지/), '80 °C 탄성계수')
    expect(status).not.toHaveTextContent('1번 항목')

    // 나머지를 채우면 문구가 사라지고 단추가 열린다.
    await user.type(screen.getByLabelText('제목'), 'SGARC440 물성')
    await user.type(screen.getByLabelText('목적'), '신규 강종 검토')
    await user.type(screen.getByLabelText('새 재료 — 무엇인지'), 'SGARC440 1.2t, 포스코')
    await user.selectOptions(screen.getByLabelText('받는 부서'), 'reliability')
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: '의뢰' })).toBeEnabled()
  })
})
