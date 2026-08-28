/**
 * 부서 홈 — **첫 화면이 무엇을 어디서 하는지 말하는가.**
 *
 * 이 자리가 공사 표지판이던 동안 "어느 화면을 어떻게 써야 하는지 모르겠다" 는
 * 말이 나왔다. 그래서 여기서 지키는 것은 모양이 아니라 **안내가 실제로 있는가**
 * 다 — 네 단계의 입구, 남은 일의 개수, 아무것도 없을 때의 다음 할 일.
 *
 * 숫자는 **서버가 센 것**(`total`)이어야 한다. 목록 길이를 세면 상한에 걸린
 * 순간 조용히 틀리는데, 화면에는 그냥 작은 숫자가 적힌다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import WorkspaceHomePage from '@/modules/workspaces/WorkspaceHomePage'

const runs = vi.fn()
const materials = vi.fn()

vi.mock('@/modules/tests/api', () => ({
  RUN_STATUS_LABEL: { parsed: '읽음', failed: '실패', uploaded: '올림' },
  testsApi: { runs: (query: Record<string, unknown>) => runs(query) },
}))

vi.mock('@/modules/materials/api', () => ({
  materialsApi: { list: (query: Record<string, unknown>) => materials(query) },
}))

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({
    user: {
      memberships: [{ slug: 'metal', name: '금속재료팀', path: '개발본부 / 금속재료팀' }],
    },
  }),
}))

interface Page {
  items: unknown[]
  total: number
}

/** 세 번의 `runs` 호출을 인자로 가른다 — 최근 목록 · 처리 대기 · 실패. */
function answer({
  recent = [],
  total = 0,
  waiting = 0,
  failed = 0,
}: {
  recent?: unknown[]
  total?: number
  waiting?: number
  failed?: number
}) {
  runs.mockImplementation((query: Record<string, unknown>): Promise<Page> => {
    if (query.adopted === false) return Promise.resolve({ items: [{}], total: waiting })
    if (query.status === 'failed') return Promise.resolve({ items: [], total: failed })
    return Promise.resolve({ items: recent, total })
  })
  materials.mockResolvedValue({ items: [], total: 12 })
}

function show() {
  return render(
    <MemoryRouter initialEntries={['/w/metal']}>
      <Routes>
        <Route path="/w/:slug" element={<WorkspaceHomePage />} />
      </Routes>
    </MemoryRouter>
  )
}

const RUN = {
  id: 'run-1',
  record_name: 'SECC-01-MD-1',
  test_type_label: '인장',
  material_name: 'SECC 1.2t',
  status: 'parsed',
}

describe('부서 홈', () => {
  beforeEach(() => {
    runs.mockReset()
    materials.mockReset()
  })

  it('네 단계로 가는 입구가 순서대로 있다', async () => {
    answer({ recent: [RUN], total: 1 })
    show()

    const steps = ['업로드', '처리', '물성 조회', '카드 내보내기']
    for (const title of steps) {
      expect(await screen.findByText(title)).toBeInTheDocument()
    }

    // 1·2단계는 **내 부서**로 간다. `default` 로 가면 목록이 비어 보이고,
    // 데이터가 없는 것과 구별이 안 된다.
    const upload = (await screen.findByText('업로드')).closest('a')
    expect(upload).toHaveAttribute('href', '/w/metal/tests/upload')
    expect((await screen.findByText('처리')).closest('a')).toHaveAttribute(
      'href',
      '/w/metal/tests'
    )
  })

  it('처리 대기는 서버가 센 수를 그대로 보여 준다', async () => {
    // 목록으로는 1건만 오는데 총계는 137 이다. 화면이 목록을 세면 1 이 뜬다.
    answer({ recent: [RUN], total: 200, waiting: 137 })
    show()

    expect(await screen.findByText('137')).toBeInTheDocument()
    expect(screen.getByText('건 처리 대기')).toBeInTheDocument()
  })

  it('읽지 못한 파일이 있으면 눈에 띄게 말한다', async () => {
    answer({ recent: [RUN], total: 5, failed: 3 })
    show()

    expect(await screen.findByText(/읽지 못한 파일 3건/)).toBeInTheDocument()
  })

  it('읽지 못한 파일이 없으면 그 줄을 띄우지 않는다', async () => {
    answer({ recent: [RUN], total: 5, failed: 0 })
    show()

    await screen.findByText('업로드')
    await waitFor(() => expect(screen.queryByText(/읽지 못한 파일/)).not.toBeInTheDocument())
  })

  it('아무것도 없으면 다음에 할 일을 적는다', async () => {
    // **빈 표는 시작을 못 한다.** 처음 들어온 사람이 보는 화면이다.
    answer({ recent: [], total: 0 })
    show()

    expect(await screen.findByText(/장비 파일을 올리면 여기에 쌓입니다/)).toBeInTheDocument()
  })
})
