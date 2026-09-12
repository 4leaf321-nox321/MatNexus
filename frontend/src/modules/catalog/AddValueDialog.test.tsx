/**
 * 문헌 값 넣기 — **물성은 서버가 풀고, 출처 없이는 못 넣고, 추정은 tier 4 로 맞춰진다.**
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AddValueDialog } from '@/modules/catalog/AddValueDialog'
import type { CatalogMaterialDetail } from '@/modules/catalog/api'

const resolveProperty = vi.fn()
const createValue = vi.fn()

vi.mock('@/modules/catalog/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/catalog/api')>()),
  catalogApi: {
    resolveProperty: (...args: unknown[]) => resolveProperty(...args),
    createValue: (...args: unknown[]) => createValue(...args),
  },
}))

const DETAIL = { id: 'cm-1', name: 'PA66-GF30', values: [] } as unknown as CatalogMaterialDetail

beforeEach(() => {
  vi.clearAllMocks()
  resolveProperty.mockResolvedValue({
    query: '열전도',
    ambiguous: false,
    candidates: [
      { key: 'thermal.conductivity', name: '열전도율', si_unit: 'W/(m.K)', deprecated: false },
      { key: 'local.thermal.old_k', name: '옛 열전도율', si_unit: 'W/(m.K)', deprecated: true },
    ],
  })
  createValue.mockResolvedValue({
    value: { property_name: '열전도율', value_num: 0.3, unit: 'W/(m.K)' },
    converted: null,
  })
})

describe('AddValueDialog', () => {
  it('물성을 이름으로 찾아 고르고(폐기된 키는 안 보이고), 출처와 함께 넣는다', async () => {
    const user = userEvent.setup()
    const onDone = vi.fn()
    render(<AddValueDialog detail={DETAIL} open onClose={vi.fn()} onDone={onDone} />)

    await user.type(screen.getByLabelText('물성 찾기'), '열전도')
    await user.click(await screen.findByRole('button', { name: /열전도율/ }))
    expect(screen.queryByText('옛 열전도율')).toBeNull()
    // 단위는 정의의 단위가 기본으로 들어온다.
    expect(screen.getByLabelText('단위')).toHaveValue('W/(m.K)')

    await user.type(screen.getByLabelText('값'), '0.3')
    await user.type(screen.getByLabelText('온도 (°C)'), '23')
    // 출처가 없으면 못 누른다.
    expect(screen.getByRole('button', { name: '넣기' })).toBeDisabled()
    await user.type(screen.getByLabelText('제목'), 'PA66-GF30 데이터시트')
    await user.type(screen.getByLabelText('출처 안의 위치'), '표 2')
    await user.click(screen.getByRole('button', { name: '넣기' }))

    await waitFor(() => expect(createValue).toHaveBeenCalled())
    const [materialId, payload] = createValue.mock.calls[0] as [string, Record<string, unknown>]
    expect(materialId).toBe('cm-1')
    expect(payload).toMatchObject({
      property_key: 'thermal.conductivity',
      value_num: 0.3,
      unit: 'W/(m.K)',
      method: 'handbook',
      quality_tier: 2,
      conditions: { temperature_k: 296.15 },
      source: { kind: 'datasheet', title: 'PA66-GF30 데이터시트' },
      source_detail: '표 2',
    })
    expect(onDone).toHaveBeenCalledWith(expect.stringContaining('넣었습니다'))
  })

  it('추정·계산을 고르면 등급이 4 로 잠긴다', async () => {
    const user = userEvent.setup()
    render(<AddValueDialog detail={DETAIL} open onClose={vi.fn()} onDone={vi.fn()} />)
    await user.selectOptions(screen.getByLabelText('방법'), 'estimated')
    const tier = screen.getByLabelText('등급')
    expect(tier).toHaveValue('4')
    expect(tier).toBeDisabled()
  })
})
