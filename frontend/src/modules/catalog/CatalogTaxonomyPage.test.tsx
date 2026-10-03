/**
 * 물성 분류 — **고르고, 한 번에 넣는다. 밀어 넣기는 미리 본 것만 넣는다** (ADR 0054).
 *
 * 무는 자리:
 *
 *   트리         분야 › 물성군 › 물성이 데이터대로 서고, 군에 안 든 것은 「미분류」 에 선다
 *   고르기       자료 관리자가 여럿을 골라 군 하나로 넣는다 — 고른 키 그대로 간다
 *   판정         자료 관리자가 아니면 고르는 칸도 · 밀어 넣기도 없다
 *   밀어 넣기    오류가 있으면 「넣기」 가 안 눌린다. 표를 고치면 미리 보기를 버린다.
 *               줄 번호가 표의 줄과 맞게 중간의 빈 줄을 남긴다
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CatalogTaxonomyPage from '@/modules/catalog/CatalogTaxonomyPage'
import { payloadOf, rowsOf } from '@/modules/catalog/taxonomyRows'
import type { Taxonomy } from '@/modules/catalog/taxonomyApi'

const tree = vi.fn()
const assign = vi.fn()
const importRows = vi.fn()

vi.mock('@/modules/catalog/taxonomyApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/taxonomyApi')>()),
  taxonomyApi: {
    tree: (...args: unknown[]) => tree(...args),
    assign: (...args: unknown[]) => assign(...args),
    importRows: (...args: unknown[]) => importRows(...args),
    createField: vi.fn(),
    updateField: vi.fn(),
    createGroup: vi.fn(),
    updateGroup: vi.fn(),
  },
}))

let me: Record<string, unknown> = {}
vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: me, reload: vi.fn(), logout: vi.fn() }),
  useMaybeAuth: () => ({ user: me, reload: vi.fn(), logout: vi.fn() }),
}))

const STEWARD = {
  id: 'u1',
  email: 'steward',
  display_name: '관리자',
  is_system_admin: false,
  is_data_manager: true,
  memberships: [],
}
const MEMBER = { ...STEWARD, id: 'u2', email: 'member', is_data_manager: false }

function property(key: string, name: string, group: string | null, domain = 'mechanical') {
  return {
    key,
    name,
    symbol: null,
    si_unit: 'Pa',
    domain,
    local: key.startsWith('local.'),
    deprecated: false,
    group_key: group,
    value_count: 3,
  }
}

const TREE: Taxonomy = {
  fields: [
    {
      key: 'mechanical',
      name: '기계',
      description: null,
      sort_order: 10,
      retired: false,
      group_count: 2,
      property_count: 1,
    },
    {
      key: 'thermal',
      name: '열',
      description: null,
      sort_order: 20,
      retired: false,
      group_count: 0,
      property_count: 0,
    },
  ],
  groups: [
    {
      key: 'pg-0001',
      field_key: 'mechanical',
      name: '강도',
      description: null,
      sort_order: 10,
      retired: false,
      property_count: 1,
    },
    {
      key: 'pg-0002',
      field_key: 'mechanical',
      name: '탄성',
      description: null,
      sort_order: 20,
      retired: false,
      property_count: 0,
    },
  ],
  properties: [
    property('mechanical.yield_strength', '항복강도', 'pg-0001'),
    property('mechanical.tensile_strength', '인장강도', null),
    property('mechanical.youngs_modulus', '영률', null),
    property('thermal.cte_linear', '선팽창계수', null, 'thermal'),
  ],
  truncated: false,
}

function show() {
  render(
    <MemoryRouter>
      <CatalogTaxonomyPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  tree.mockReset()
  assign.mockReset()
  importRows.mockReset()
  tree.mockResolvedValue(TREE)
  me = STEWARD
})

describe('트리', () => {
  it('분야 › 물성군 › 물성이 서고, 군에 안 든 것은 미분류에 선다', async () => {
    show()
    const strength = await screen.findByRole('region', { name: '물성군 강도' })
    expect(within(strength).getByText('항복강도')).toBeInTheDocument()
    const elastic = screen.getByRole('region', { name: '물성군 탄성' })
    expect(within(elastic).getByText('든 물성이 없습니다.')).toBeInTheDocument()

    const loose = screen.getByRole('region', { name: '미분류' })
    expect(within(loose).getByText('인장강도')).toBeInTheDocument()
    expect(within(loose).getByText('선팽창계수')).toBeInTheDocument()
    expect(within(loose).queryByText('항복강도')).not.toBeInTheDocument()
  })

  it('찾으면 걸린 물성이 있는 군만 남는다', async () => {
    show()
    await screen.findByRole('region', { name: '물성군 강도' })
    await userEvent.type(screen.getByLabelText('물성 찾기'), '영률')
    expect(screen.queryByRole('region', { name: '물성군 강도' })).not.toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: '미분류' })).getByText('영률')).toBeInTheDocument()
  })
})

describe('고르고 넣기', () => {
  it('여럿을 골라 군 하나로 — 고른 키 그대로 간다', async () => {
    assign.mockResolvedValue({ group_key: 'pg-0002', changed: [], unchanged: [] })
    show()
    await userEvent.click(await screen.findByLabelText('인장강도 고르기'))
    await userEvent.click(screen.getByLabelText('영률 고르기'))
    expect(screen.getByText('2개 고름')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('넣을 물성군'), 'pg-0002')
    await userEvent.click(screen.getByRole('button', { name: '넣기' }))
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1))
    expect(assign).toHaveBeenCalledWith('pg-0002', [
      'mechanical.tensile_strength',
      'mechanical.youngs_modulus',
    ])
    // 넣고 나면 다시 읽고, 고름은 풀린다.
    await waitFor(() => expect(tree).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(screen.queryByText('2개 고름')).not.toBeInTheDocument())
  })

  it('자료 관리자가 아니면 고르는 칸도 밀어 넣기도 없다', async () => {
    me = MEMBER
    show()
    await screen.findByRole('region', { name: '물성군 강도' })
    expect(screen.getByText('인장강도')).toBeInTheDocument()
    expect(screen.queryByLabelText('인장강도 고르기')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /밀어 넣기/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /분야 추가/ })).not.toBeInTheDocument()
  })
})

const PLAN_OK = {
  applied: false,
  fields: [{ key: 'mechanical', name: '기계', action: 'unchanged' }],
  groups: [{ key: 'pg-0003', name: '경도', field_key: 'mechanical', action: 'create' }],
  members: [
    {
      property_key: 'mechanical.tensile_strength',
      property_name: '인장강도',
      group_key: 'pg-0003',
      action: 'assign',
    },
  ],
  errors: [],
}

describe('밀어 넣기', () => {
  async function openAndFill() {
    show()
    await screen.findByRole('region', { name: '물성군 강도' })
    await userEvent.click(screen.getByRole('button', { name: /밀어 넣기/ }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText('1번 줄 분야'), '기계')
    await userEvent.type(within(dialog).getByLabelText('1번 줄 물성군'), '경도')
    await userEvent.type(within(dialog).getByLabelText('1번 줄 물성'), '인장강도')
    return dialog
  }

  it('미리 보고, 오류가 없을 때만 넣는다', async () => {
    importRows.mockResolvedValueOnce(PLAN_OK).mockResolvedValueOnce({ ...PLAN_OK, applied: true })
    const dialog = await openAndFill()
    const apply = within(dialog).getByRole('button', { name: /^넣기/ })
    expect(apply).toBeDisabled() // 미리 보기 전

    await userEvent.click(within(dialog).getByRole('button', { name: '미리 보기' }))
    await within(dialog).findByRole('region', { name: '미리 보기' })
    expect(importRows).toHaveBeenLastCalledWith(
      [{ field: '기계', group: '경도', property: '인장강도' }],
      true
    )
    expect(within(dialog).getByText('기계 › 경도')).toBeInTheDocument()

    const ready = within(dialog).getByRole('button', { name: '넣기 (2건)' })
    await userEvent.click(ready)
    await waitFor(() => expect(importRows).toHaveBeenCalledTimes(2))
    expect(importRows).toHaveBeenLastCalledWith(
      [{ field: '기계', group: '경도', property: '인장강도' }],
      false
    )
  })

  it('키 앞머리와 다른 분야로 가는 물성을 세워 보인다 — 이름이 같아도 뜻이 다를 수 있다', async () => {
    importRows.mockResolvedValueOnce({
      ...PLAN_OK,
      members: [
        {
          property_key: 'rheological.yield_stress',
          property_name: '항복응력',
          group_key: 'pg-0003',
          action: 'assign',
          domain: 'rheological',
          cross_domain: true,
        },
      ],
    })
    const dialog = await openAndFill()
    await userEvent.click(within(dialog).getByRole('button', { name: '미리 보기' }))
    const warn = await within(dialog).findByLabelText('다른 분야의 물성')
    expect(warn).toHaveTextContent('항복응력 (rheological.yield_stress) — 유변 물성 → 기계 › 경도')
  })

  it('오류가 있으면 줄 번호와 함께 보이고 넣기가 안 눌린다', async () => {
    importRows.mockResolvedValueOnce({
      ...PLAN_OK,
      errors: [{ row: 1, message: '물성 「인장강도x」 을 찾을 수 없습니다' }],
    })
    const dialog = await openAndFill()
    await userEvent.click(within(dialog).getByRole('button', { name: '미리 보기' }))
    const alert = await within(dialog).findByRole('alert')
    expect(alert).toHaveTextContent('1번 줄 — 물성 「인장강도x」 을 찾을 수 없습니다')
    expect(within(dialog).getByRole('button', { name: /^넣기/ })).toBeDisabled()
  })

  it('표를 고치면 미리 보기를 버린다 — 본 것과 넣는 것이 달라지지 않게', async () => {
    importRows.mockResolvedValueOnce(PLAN_OK)
    const dialog = await openAndFill()
    await userEvent.click(within(dialog).getByRole('button', { name: '미리 보기' }))
    await within(dialog).findByRole('region', { name: '미리 보기' })

    await userEvent.type(within(dialog).getByLabelText('1번 줄 물성'), '2')
    expect(within(dialog).queryByRole('region', { name: '미리 보기' })).not.toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: /^넣기/ })).toBeDisabled()
  })
})

describe('표 ↔ 줄', () => {
  it('중간의 빈 줄은 남기고 끝의 빈 줄만 뗀다 — 서버의 줄 번호가 표의 줄과 맞는다', () => {
    const blank = ['', '', '', '', '', '', '']
    const rows = [['기계', '강도', 'a', '', '', '', ''], blank, ['열', '팽창', 'b', '', '', '', ''], blank]
    expect(payloadOf(rows)).toEqual([
      { field: '기계', group: '강도', property: 'a' },
      {},
      { field: '열', group: '팽창', property: 'b' },
    ])
  })

  it('지금 분류를 표로 — 빈 군도 한 줄로 남아 왕복해도 사라지지 않는다', () => {
    expect(rowsOf(TREE)).toEqual([
      ['기계', '강도', 'mechanical.yield_strength', 'mechanical', 'pg-0001', '', ''],
      ['기계', '탄성', '', 'mechanical', 'pg-0002', '', ''],
    ])
  })
})
