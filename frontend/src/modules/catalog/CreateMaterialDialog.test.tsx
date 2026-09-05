/**
 * 문헌 재료로부터 사내 재료 만들기.
 *
 *   프리필이 세 겹 결정을 따른다 — grade 는 카탈로그 grade, alias 는 원본 이름
 *   전체, 긴 material_class 는 분류 칸이 아니라 참고 줄로만
 *   만들면 생성 → 문헌 연결 순서로 부르고 재료 상세로 간다
 *   연결이 실패하면 조용히 넘어가지 않는다 — 재료는 생겼다고 말한다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { CatalogMaterialDetail } from '@/modules/catalog/api'
import { CreateMaterialDialog } from '@/modules/catalog/CreateMaterialDialog'

const post = vi.fn()
const setLink = vi.fn()

vi.mock('@/shared/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/client')>()),
  api: { post: (...args: unknown[]) => post(...args) },
}))

vi.mock('@/modules/catalog/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/modules/catalog/api')>()
  return {
    ...original,
    catalogApi: {
      ...original.catalogApi,
      setLink: (...args: unknown[]) => setLink(...args),
    },
  }
})

const CATALOG_ID = '11111111-1111-1111-1111-111111111111'
const MATERIAL_ID = '22222222-2222-2222-2222-222222222222'

function makeDetail(over: Partial<CatalogMaterialDetail> = {}): CatalogMaterialDetail {
  return {
    id: CATALOG_ID,
    name: 'Ultramid A3WG5 (PA66-GF25, BASF)',
    material_code: null,
    category: 'polymer',
    description: null,
    subsystem: 'housing',
    role: null,
    manufacturer: 'BASF',
    material_class: 'PA66-GF25',
    grade: 'Ultramid A3WG5',
    attributes: null,
    values: [],
    ...over,
  } as CatalogMaterialDetail
}

function mount(detail: CatalogMaterialDetail) {
  return render(
    <MemoryRouter initialEntries={['/catalog/x']}>
      <Routes>
        <Route
          path="/catalog/x"
          element={<CreateMaterialDialog detail={detail} open onClose={() => {}} />}
        />
        <Route path="/materials/:id" element={<div>재료 상세 화면</div>} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  post.mockResolvedValue({ id: MATERIAL_ID })
  setLink.mockResolvedValue({})
})

describe('프리필', () => {
  it('규격급 — grade·분류·별칭이 카탈로그에서 온다', () => {
    mount(makeDetail())
    expect(screen.getByDisplayValue('Polymer')).toBeInTheDocument()
    expect(screen.getByDisplayValue('PA66-GF25')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Ultramid A3WG5')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Ultramid A3WG5 (PA66-GF25, BASF)')).toBeInTheDocument()
  })

  it('서술형 — grade 는 비고, 긴 material_class 는 분류 칸이 아니라 참고 줄에', () => {
    const long = 'low-Dk coverlay film for 5G FPC (polyimide 12.5um + adhesive 25um)'
    mount(makeDetail({ grade: null, material_class: long }))
    // 분류 칸은 비어 있다 — 자유 문장을 분류에 밀어 넣으면 기준정보가 오염된다.
    expect(screen.getByPlaceholderText(/PA66-GF25/)).toHaveValue('')
    expect(screen.getByText(new RegExp(long.slice(0, 20)))).toBeInTheDocument()
    // grade 가 비면 만들기가 막힌다 — 이름 첫 칸이라 사람이 지어야 한다.
    expect(screen.getByRole('button', { name: /만들고 연결/ })).toBeDisabled()
  })
})

describe('만들고 연결', () => {
  it('생성 → 연결 순서로 부르고 재료 상세로 간다', async () => {
    const user = userEvent.setup()
    mount(makeDetail())
    await user.click(screen.getByRole('button', { name: /만들고 연결/ }))
    await waitFor(() => expect(screen.getByText('재료 상세 화면')).toBeInTheDocument())
    expect(post).toHaveBeenCalledWith('/materials', {
      family: 'Polymer',
      category: 'PA66-GF25',
      grade: 'Ultramid A3WG5',
      details: null,
      alias: 'Ultramid A3WG5 (PA66-GF25, BASF)',
    })
    expect(setLink).toHaveBeenCalledWith(MATERIAL_ID, CATALOG_ID)
  })

  it('연결이 실패하면 재료가 생겼다는 사실을 말한다', async () => {
    setLink.mockRejectedValue(new Error('연결 실패'))
    const user = userEvent.setup()
    mount(makeDetail())
    await user.click(screen.getByRole('button', { name: /만들고 연결/ }))
    expect(await screen.findByText(/문헌 연결을 걸지 못했습니다/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '재료로 이동' }))
    expect(screen.getByText('재료 상세 화면')).toBeInTheDocument()
  })

  it('생성이 실패하면 오류가 보이고 이동하지 않는다', async () => {
    post.mockRejectedValue(new Error('같은 이름의 재료가 이미 있습니다'))
    const user = userEvent.setup()
    mount(makeDetail())
    await user.click(screen.getByRole('button', { name: /만들고 연결/ }))
    expect(await screen.findByText(/이미 있습니다/)).toBeInTheDocument()
    expect(setLink).not.toHaveBeenCalled()
    expect(screen.queryByText('재료 상세 화면')).not.toBeInTheDocument()
  })
})
