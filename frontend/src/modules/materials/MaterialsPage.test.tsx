/**
 * 재료 목록의 **일괄 삭제** — 무엇을 지우겠다고 서버에 말하는가.
 *
 * 여기서 틀리면 사라지는 것이 고른 재료가 아니라 그 아래 트리 전체다. 그리고
 * 사람이 「예」 를 누른 근거는 이 화면이 보여 준 숫자이므로, 숫자와 실제가
 * 어긋나면 그 「예」 는 다른 것에 대한 대답이 된다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MaterialsPage from '@/modules/materials/MaterialsPage'

const list = vi.fn()
const classifications = vi.fn()
const bulkDeletePlan = vi.fn()
const removeMany = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    list: (...args: unknown[]) => list(...args),
    classifications: () => classifications(),
    bulkDeletePlan: (...args: unknown[]) => bulkDeletePlan(...args),
    removeMany: (...args: unknown[]) => removeMany(...args),
  },
}))

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: true, memberships: [] } }),
}))

function material(id: string, name: string) {
  return {
    id,
    record_name: name,
    alias: null,
    family: 'Metal',
    category: 'Steel',
    grade: name,
    details: null,
    spec_thickness: 1,
    spec_thickness_unit: 'mm',
    owner_workspace_id: null,
    owner_workspace_name: null,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function plan(samples: number, specimens: number, test_runs: number, blocked = []) {
  return { materials: 2, samples, specimens, test_runs, blocked }
}

beforeEach(() => {
  list.mockReset()
  classifications.mockReset()
  bulkDeletePlan.mockReset()
  removeMany.mockReset()
  list.mockResolvedValue({
    items: [material('m1', 'SPCC_-_1.2'), material('m2', 'SGCC_-_0.8')],
    total: 2,
    limit: 50,
    offset: 0,
  })
  classifications.mockResolvedValue([])
  removeMany.mockResolvedValue({ deleted: 2, blocked: [], samples: 0, specimens: 0, test_runs: 0 })
})

function show() {
  return render(
    <MemoryRouter>
      <MaterialsPage />
    </MemoryRouter>
  )
}

/** 두 재료를 고르고 「지우기」 를 눌러 확인창을 연다. */
async function pickAndOpen(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByText('SPCC_-_1.2')
  const boxes = screen.getAllByRole('checkbox')
  // 첫 칸은 '전부 고르기' 다. 그것을 눌러 둘을 함께 고른다.
  await user.click(boxes[0])
  await user.click(await screen.findByRole('button', { name: /지우기/ }))
}

describe('일괄 삭제', () => {
  it('열 때 무엇이 딸려 있는지 서버에 묻는다', async () => {
    // **화면이 세지 않는다.** 목록에는 시료·시편 수가 없고, 있다 해도 화면이
    // 나름대로 세면 실제로 지워지는 것과 어긋난다.
    bulkDeletePlan.mockResolvedValue(plan(2, 6, 0))
    const user = userEvent.setup()
    show()
    await pickAndOpen(user)

    await waitFor(() => expect(bulkDeletePlan).toHaveBeenCalledWith(['m1', 'm2']))
    expect(await screen.findByText(/시료 2건 · 시편 6건/)).toBeInTheDocument()
  })

  it('기본은 아래를 안 지운다', async () => {
    // **고르고 지우기를 누르는 것이 갑자기 트리를 날리는 뜻이 되면 안 된다.**
    bulkDeletePlan.mockResolvedValue(plan(2, 6, 0))
    const user = userEvent.setup()
    show()
    await pickAndOpen(user)
    await screen.findByText(/시료 2건/)

    await user.click(screen.getByRole('button', { name: '지우기', hidden: false }))
    await waitFor(() =>
      expect(removeMany).toHaveBeenCalledWith(['m1', 'm2'], {
        cascade: false,
        includeTestRuns: false,
      })
    )
  })

  it('켜면 아래까지 지운다고 말한다', async () => {
    bulkDeletePlan.mockResolvedValue(plan(2, 6, 0))
    const user = userEvent.setup()
    show()
    await pickAndOpen(user)
    await screen.findByText(/시료 2건/)

    await user.click(screen.getByRole('checkbox', { name: /아래까지 함께 지웁니다/ }))
    await user.click(screen.getByRole('button', { name: '지우기' }))
    await waitFor(() =>
      expect(removeMany).toHaveBeenCalledWith(['m1', 'm2'], {
        cascade: true,
        includeTestRuns: false,
      })
    )
  })

  it('시험 칸은 아래까지를 켜야 뜬다', async () => {
    // 늘 띄우면 사람이 습관적으로 켜게 되고, 그러면 칸이 막는 일을 못 한다.
    bulkDeletePlan.mockResolvedValue(plan(2, 6, 4))
    const user = userEvent.setup()
    show()
    await pickAndOpen(user)
    await screen.findByText(/시험 4건/)

    expect(screen.queryByRole('checkbox', { name: /시험 4건도 함께/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: /아래까지 함께 지웁니다/ }))
    expect(
      await screen.findByRole('checkbox', { name: /시험 4건도 함께/ })
    ).toBeInTheDocument()
  })

  it('아래까지를 끄면 시험 칸도 함께 꺼진다', async () => {
    // **켠 채로 숨으면 그 뜻이 그대로 서버에 간다.** 사람은 껐다고 생각한다.
    bulkDeletePlan.mockResolvedValue(plan(2, 6, 4))
    const user = userEvent.setup()
    show()
    await pickAndOpen(user)
    await screen.findByText(/시험 4건/)

    const cascade = screen.getByRole('checkbox', { name: /아래까지 함께 지웁니다/ })
    await user.click(cascade)
    await user.click(await screen.findByRole('checkbox', { name: /시험 4건도 함께/ }))
    await user.click(cascade)
    await user.click(cascade)

    await user.click(screen.getByRole('button', { name: '지우기' }))
    await waitFor(() =>
      expect(removeMany).toHaveBeenCalledWith(['m1', 'm2'], {
        cascade: true,
        includeTestRuns: false,
      })
    )
  })

  it('딸려 간 것을 지운 뒤에 말한다', async () => {
    // "2건 지웠습니다" 만 뜨면 사람은 시편 여섯이 함께 사라진 것을 모른다.
    bulkDeletePlan.mockResolvedValue(plan(2, 6, 0))
    removeMany.mockResolvedValue({
      deleted: 2,
      blocked: [],
      samples: 2,
      specimens: 6,
      test_runs: 0,
    })
    const user = userEvent.setup()
    show()
    await pickAndOpen(user)
    await screen.findByText(/시료 2건/)
    await user.click(screen.getByRole('checkbox', { name: /아래까지 함께 지웁니다/ }))
    await user.click(screen.getByRole('button', { name: '지우기' }))

    expect(
      await screen.findByText(/재료 2건과 함께 시료 2건 · 시편 6건을 지웠습니다/)
    ).toBeInTheDocument()
  })
})
