/**
 * 레시피 목록 — **이름만 고치고, 나머지는 받은 그대로 돌려보낸다.**
 *
 * 서버의 고치기(PUT)는 레시피를 통째로 받는다. 이름을 고치는 자리가 단계를 빼거나
 * 열었을 때의 `revision` 을 안 보내면, 이름 한 번 고친 것이 단계를 지우거나 남이 고친 것을
 * 옛것으로 덮는다. 무는 자리는 그 몸통이다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import RecipesPage from '@/modules/processing/RecipesPage'
import { LeftPanelHost, LeftPanelProvider } from '@/shared/layout/SidePanel'

const recipes = vi.fn()
const updateRecipe = vi.fn()

vi.mock('@/modules/processing/api', async () => {
  const actual =
    await vi.importActual<typeof import('@/modules/processing/api')>('@/modules/processing/api')
  return {
    ...actual,
    processingApi: {
      recipes: (...args: unknown[]) => recipes(...args),
      updateRecipe: (...args: unknown[]) => updateRecipe(...args),
      removeRecipe: vi.fn(),
    },
  }
})

const STEPS = [
  { plugin: 'tensile.engineering', options: { gauge_length: 0.05 } },
  { plugin: 'tensile.strength', options: {} },
]

const RECIPE = {
  id: 'r1',
  key: 'rcp_1a2b3c4d',
  label: '인장 표준',
  description: '사내규격',
  owner_workspace_slug: 'metal',
  owner_workspace_name: '금속재료팀',
  access: { can_edit: true, reason: null, registrant: '홍길동', edit_workspace: null },
  test_type_key: 'tensile',
  test_type_label: '인장',
  steps: STEPS,
  is_active: true,
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
  revision: 3,
}

function show() {
  render(
    <MemoryRouter>
      <LeftPanelProvider>
        <LeftPanelHost />
        <RecipesPage />
      </LeftPanelProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  recipes.mockReset()
  updateRecipe.mockReset()
})

describe('이름 고치기', () => {
  it('이름 · 설명만 바꾸고 단계 · 종류 · 켜짐 · revision 은 받은 그대로 보낸다', async () => {
    recipes.mockResolvedValue([RECIPE])
    updateRecipe.mockResolvedValue({ ...RECIPE, label: '인장 표준 v2', revision: 4 })
    show()
    // 데이터로 그려진 것을 기다린다 — 레시피 이름이 서야 줄이 선 것이다.
    await screen.findByText('인장 표준')
    await userEvent.click(screen.getByRole('button', { name: '이름 고치기' }))

    const label = screen.getByLabelText('이름')
    await userEvent.clear(label)
    await userEvent.type(label, '인장 표준 v2')
    await userEvent.clear(screen.getByLabelText('설명'))
    await userEvent.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(updateRecipe).toHaveBeenCalledTimes(1))
    expect(updateRecipe).toHaveBeenCalledWith('rcp_1a2b3c4d', {
      label: '인장 표준 v2',
      // 비운 설명은 지운다 — 빈 글자로 남기지 않는다.
      description: null,
      test_type_key: 'tensile',
      steps: STEPS,
      is_active: true,
      expected_revision: 3,
    })
    // 저장하면 목록을 다시 읽는다 — 새 revision 을 받아야 다음 고치기가 안 막힌다.
    await waitFor(() => expect(recipes).toHaveBeenCalledTimes(2))
  })

  it('바뀐 것이 없거나 이름을 비우면 저장을 막는다', async () => {
    recipes.mockResolvedValue([RECIPE])
    show()
    await screen.findByText('인장 표준')
    await userEvent.click(screen.getByRole('button', { name: '이름 고치기' }))
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled()
    await userEvent.clear(screen.getByLabelText('이름'))
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled()
  })

  it('그사이 남이 고쳤으면 서버의 말을 대화상자에 세우고 닫지 않는다', async () => {
    recipes.mockResolvedValue([RECIPE])
    updateRecipe.mockRejectedValue(new Error('다른 사람이 먼저 고쳤습니다. 다시 열어 주세요.'))
    show()
    await screen.findByText('인장 표준')
    await userEvent.click(screen.getByRole('button', { name: '이름 고치기' }))
    await userEvent.type(screen.getByLabelText('이름'), ' v2')
    await userEvent.click(screen.getByRole('button', { name: '저장' }))

    expect(await screen.findByText('다른 사람이 먼저 고쳤습니다. 다시 열어 주세요.')).toBeVisible()
    expect(screen.getByLabelText('이름')).toHaveValue('인장 표준 v2')
  })

  it('고칠 수 없으면 단추를 잠그고 누구에게 물을지 단다', async () => {
    recipes.mockResolvedValue([
      {
        ...RECIPE,
        access: {
          can_edit: false,
          reason: '등록자 홍길동 또는 편집 부서에 물으세요',
          registrant: '홍길동',
          edit_workspace: null,
        },
      },
    ])
    show()
    await screen.findByText('인장 표준')
    const button = screen.getByRole('button', { name: '이름 고치기' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('title', '등록자 홍길동 또는 편집 부서에 물으세요')
  })
})
