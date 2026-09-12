/**
 * 물성 매핑 표 — **세 층이 한 줄에 서고, 빈 곳이 세어지고, 눈금 있는 항목은
 * 눈금을 고르게 한다.**
 *
 *   안 이어진 항목 수가 위에 뜬다      0 이 아니면 그것부터 보이게
 *   잇기 창에서 눈금이 필수다          「경도」 는 HV 인지 HRC 인지 정해야 잇는다
 *   풀기는 링크 id 로 부른다            이름으로 짐작하지 않는다
 *   관리자가 아니면 단추가 없다         매핑은 모든 부서의 검색에 걸린다
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PropertyMappingPanel } from '@/modules/catalog/PropertyMappingPanel'
import type { PropertyMapping } from '@/modules/catalog/api'

const linkProperty = vi.fn()
const unlinkProperty = vi.fn()
const deprecateProperty = vi.fn()

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: {
    linkProperty: (...args: unknown[]) => linkProperty(...args),
    unlinkProperty: (...args: unknown[]) => unlinkProperty(...args),
    deprecateProperty: (...args: unknown[]) => deprecateProperty(...args),
  },
}))

vi.mock('@/shared/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/api/client')>()),
  downloadFile: vi.fn(),
}))

const HARDNESS = { term_id: 't-hard', item: '경도', dimension: 'dimensionless', scales: ['HV', 'HRC'] }
const FLEX = { term_id: 't-flex', item: '굴곡강도', dimension: 'stress', scales: [] }

const MAPPING: PropertyMapping = {
  axis_slug: 'property_item',
  kinds: ['same_as', 'narrower', 'related'],
  items: [
    { term_id: 't-yield', item: '항복강도', dimension: 'stress', scales: [] },
    HARDNESS,
    FLEX,
  ],
  unlinked_items: [FLEX],
  summary: { keys: 3, linked_keys: 2, measured_keys: 1, unlinked_items: 1 },
  rows: [
    {
      origin: 'catalog',
      deprecated: false,
      key: 'mechanical.yield_strength',
      name: '항복강도',
      domain: 'mechanical',
      si_unit: 'Pa',
      symbol: 'σy',
      test_standard: 'ISO 6892',
      value_count: 486,
      links: [
        {
          id: 'l-1',
          property_key: 'mechanical.yield_strength',
          term_id: 't-yield',
          item: '항복강도',
          kind: 'same_as',
          scale: null,
          note: null,
        },
      ],
      measured: [
        { plugin_id: 'tensile.proof_stress', plugin_label: '오프셋 항복강도', scalar_key: 'proof_stress' },
      ],
    },
    {
      origin: 'catalog',
      deprecated: false,
      key: 'mechanical.hardness_vickers',
      name: '비커스 경도',
      domain: 'mechanical',
      si_unit: 'HV',
      symbol: null,
      test_standard: 'ISO 6507',
      value_count: 248,
      links: [
        {
          id: 'l-2',
          property_key: 'mechanical.hardness_vickers',
          term_id: 't-hard',
          item: '경도',
          kind: 'same_as',
          scale: 'HV',
          note: null,
        },
      ],
      measured: [],
    },
    {
      origin: 'catalog',
      deprecated: false,
      key: 'mechanical.flexural_strength',
      name: '굽힘강도',
      domain: 'mechanical',
      si_unit: 'Pa',
      symbol: null,
      test_standard: 'ISO 178',
      value_count: 415,
      links: [],
      measured: [],
    },
  ],
}

function show(canEdit = true) {
  const onChanged = vi.fn()
  render(<PropertyMappingPanel mapping={MAPPING} canEdit={canEdit} onChanged={onChanged} />)
  return onChanged
}

beforeEach(() => {
  vi.clearAllMocks()
  linkProperty.mockResolvedValue({})
  unlinkProperty.mockResolvedValue(undefined)
  deprecateProperty.mockResolvedValue({})
})

describe('물성 매핑', () => {
  it('세 층이 한 줄에 서고, 안 이어진 항목이 세어진다', () => {
    show()
    const rows = screen.getAllByRole('row')
    const yield_ = rows.find((row) => within(row).queryByText('mechanical.yield_strength'))
    expect(yield_).toBeDefined()
    expect(within(yield_!).getByText('항복강도', { selector: 'span' })).toBeInTheDocument()
    expect(within(yield_!).getByText('proof_stress')).toBeInTheDocument()
    expect(within(yield_!).getByText(/오프셋 항복강도/)).toBeInTheDocument()
    // 눈금이 붙은 매핑은 눈금째 보인다.
    expect(screen.getByText('(HV)')).toBeInTheDocument()
    // 빈 곳.
    expect(screen.getByText(/안 이어진 사내 항목 1개/)).toBeInTheDocument()
  })

  it('요약 칸이 곧 거르개다 — 이어진 것·재는 것·안 쓰는 것만 남긴다', async () => {
    const user = userEvent.setup()
    show()
    const group = screen.getByRole('group', { name: '무엇을 볼까' })
    const keysShown = () =>
      screen.getAllByRole('row').filter((row) => within(row).queryByText(/^mechanical\./)).length

    await user.click(within(group).getByRole('button', { name: /사내 항목과 이어짐/ }))
    expect(keysShown()).toBe(2)
    expect(screen.queryByText('mechanical.flexural_strength')).toBeNull()

    await user.click(within(group).getByRole('button', { name: /시험으로 재는 것/ }))
    expect(keysShown()).toBe(1)
    expect(screen.getByText('mechanical.yield_strength')).toBeInTheDocument()

    await user.click(within(group).getByRole('button', { name: /사내에서 안 쓰는 것/ }))
    expect(keysShown()).toBe(1)
    expect(screen.getByText('mechanical.flexural_strength')).toBeInTheDocument()

    await user.click(within(group).getByRole('button', { name: /문헌 물성/ }))
    expect(keysShown()).toBe(3)
  })

  it('안 이어진 항목의 「잇기」 는 문헌 물성을 쳐서 찾아 잇는다', async () => {
    const user = userEvent.setup()
    const onChanged = show()
    await user.click(screen.getByRole('button', { name: '굴곡강도 잇기' }))
    await user.type(screen.getByLabelText('문헌 물성 찾기'), '굽힘')
    await user.click(screen.getByRole('button', { name: /굽힘강도/ }))
    await user.click(screen.getByRole('button', { name: '잇기' }))
    await waitFor(() =>
      expect(linkProperty).toHaveBeenCalledWith({
        property_key: 'mechanical.flexural_strength',
        item: '굴곡강도',
        kind: 'same_as',
        scale: null,
      })
    )
    expect(onChanged).toHaveBeenCalled()
  })

  it('눈금 있는 항목은 눈금을 골라야 이어진다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(screen.getByRole('button', { name: '비커스 경도 에 사내 항목 잇기' }))
    await user.selectOptions(screen.getByLabelText('사내 항목'), 't-hard')
    // 눈금을 안 고르면 안 눌린다.
    expect(screen.getByRole('button', { name: '잇기' })).toBeDisabled()
    await user.selectOptions(screen.getByLabelText('눈금'), 'HRC')
    await user.click(screen.getByRole('button', { name: '잇기' }))
    await waitFor(() =>
      expect(linkProperty).toHaveBeenCalledWith(
        expect.objectContaining({ property_key: 'mechanical.hardness_vickers', scale: 'HRC' })
      )
    )
  })

  it('풀기는 링크 id 로 부른다', async () => {
    const user = userEvent.setup()
    const onChanged = show()
    await user.click(screen.getByRole('button', { name: '비커스 경도 ↔ 경도 (HV) 풀기' }))
    await waitFor(() => expect(unlinkProperty).toHaveBeenCalledWith('l-2'))
    expect(onChanged).toHaveBeenCalled()
  })

  it('폐기는 후속 키를 골라 지우지 않고 표시한다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(screen.getByRole('button', { name: '굽힘강도 폐기' }))
    await user.type(screen.getByLabelText('후속 물성 찾기'), '항복')
    await user.click(screen.getByRole('button', { name: /mechanical\.yield_strength/ }))
    await user.type(screen.getByLabelText('왜'), '잘못 만듦')
    await user.click(screen.getByRole('button', { name: '폐기' }))
    await waitFor(() =>
      expect(deprecateProperty).toHaveBeenCalledWith('mechanical.flexural_strength', {
        superseded_by: 'mechanical.yield_strength',
        note: '잘못 만듦',
      })
    )
  })

  it('관리자가 아니면 잇고 푸는 단추가 없다', () => {
    show(false)
    expect(screen.queryByRole('button', { name: /잇기$/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /풀기$/ })).toBeNull()
  })
})
