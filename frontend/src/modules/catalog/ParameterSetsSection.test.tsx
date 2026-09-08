/**
 * 문헌 재료의 모델 파라미터 벌 — **묶음으로 보이고 묶음으로 담긴다.**
 *
 * 무는 것 넷:
 *   한 벌이 한 덩이로 선다        낱개로 흩으면 같은 이름이 아홉 번 선다
 *   단위를 항마다 적는다          한 벌 안에서 MPa·1/s·K 가 섞인다
 *   무차원은 단위를 안 적는다      `1` 을 적으면 그것이 단위처럼 읽힌다
 *   담을 때 한 벌이 통째로 간다    `A` 만 담으면 모델이 못 쓴다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ParameterSetsSection } from '@/modules/catalog/ParameterSetsSection'

const get = vi.fn()
const post = vi.fn()

vi.mock('@/shared/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client')
  return {
    ...actual,
    api: {
      ...actual.api,
      get: (...args: unknown[]) => get(...args),
      post: (...args: unknown[]) => post(...args),
    },
  }
})

const SET = {
  property_key: 'mechanical.anand_constant',
  label: 'Anand 점소성 상수',
  model: 'anand',
  set_id: 'wang1998',
  quality_tier: 3,
  source_detail: 'Wang 1998',
  terms: [
    { term: 'a', value: 1.34, text: null, unit: '1' },
    { term: 'h0', value: 2640.75, text: null, unit: 'MPa' },
    { term: 'Q/R', value: 10830, text: null, unit: 'K' },
  ],
}

beforeEach(() => {
  get.mockReset()
  post.mockReset()
})

describe('ParameterSetsSection', () => {
  it('한 벌이 한 덩이로 서고 단위를 항마다 적는다', async () => {
    get.mockResolvedValue([SET])
    render(<ParameterSetsSection materialId="cat-1" />)

    expect(await screen.findByText('Anand 점소성 상수')).toBeInTheDocument()
    expect(screen.getByText('wang1998')).toBeInTheDocument()
    expect(screen.getByText(/2640.75 MPa/)).toBeInTheDocument()
    expect(screen.getByText(/10830 K/)).toBeInTheDocument()
    // 무차원은 단위를 안 적는다 — `1` 을 적으면 그것이 단위처럼 읽힌다.
    expect(screen.getByText(/= 1.34$/)).toBeInTheDocument()
  })

  it('벌이 없으면 아무것도 안 그린다', async () => {
    get.mockResolvedValue([])
    const { container } = render(<ParameterSetsSection materialId="cat-1" />)
    await waitFor(() => expect(get).toHaveBeenCalled())
    expect(container.querySelector('section')).toBeNull()
  })

  it('담을 때 한 벌이 통째로 간다', async () => {
    get.mockImplementation((url: string) =>
      String(url).includes('/materials?q=')
        ? Promise.resolve({ items: [{ id: 'm-9', record_name: 'SECC_1.0' }], total: 1 })
        : Promise.resolve([SET])
    )
    post.mockResolvedValue({ id: 'ps-1' })
    render(<ParameterSetsSection materialId="cat-1" />)

    await userEvent.click(await screen.findByRole('button', { name: /사내 재료에 담기/ }))
    await userEvent.type(screen.getByLabelText('사내 재료 찾기'), 'SECC')
    await userEvent.click(await screen.findByRole('button', { name: '담기' }))

    await waitFor(() => expect(post).toHaveBeenCalled())
    expect(post.mock.calls[0][0]).toBe('/materials/m-9/parameter-sets')
    expect(post.mock.calls[0][1]).toMatchObject({
      property_key: 'mechanical.anand_constant',
      catalog_material_id: 'cat-1',
      model: 'anand',
      set_id: 'wang1998',
    })
  })
})
