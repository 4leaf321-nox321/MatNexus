/**
 * 덱 단위계 만들기 — **저장 전에 무엇이 어떻게 적힐지 본다.**
 *
 * 응력이 GPa 인지 MPa 인지는 만든 뒤 덱을 열어야 알면 늦다. 셋을 고르면 서버가
 * 유도한 기호가 그 자리에서 보이고, 만들기는 그 셋과 key·이름만 보낸다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { UnitSystemsSection } from '@/modules/fitting/UnitSystemsSection'

const unitSystems = vi.fn()
const deriveUnitSystem = vi.fn()
const createUnitSystem = vi.fn()
const removeUnitSystem = vi.fn()

vi.mock('@/modules/fitting/api', () => ({
  fittingApi: {
    unitSystems: () => unitSystems(),
    unitSystemBaseUnits: () =>
      Promise.resolve({ mass: ['kg', 'g', 'tonne'], length: ['m', 'mm'], time: ['s', 'ms'] }),
    deriveUnitSystem: (...args: unknown[]) => deriveUnitSystem(...args),
    createUnitSystem: (...args: unknown[]) => createUnitSystem(...args),
    removeUnitSystem: (...args: unknown[]) => removeUnitSystem(...args),
  },
}))

const SI = {
  key: 'si',
  label: 'SI (kg · m · s · Pa)',
  declaration: 'kg, m, s, Pa',
  is_default: false,
  builtin: true,
  mass: 'kg',
  length: 'm',
  time: 's',
  symbols: { Pa: 'Pa', 'kg/m3': 'kg/m3', s: 's' },
}
const CUSTOM = {
  key: 'mm_ms_kg',
  label: 'LS-DYNA (GPa)',
  declaration: 'kg, mm, ms, GPa',
  is_default: false,
  builtin: false,
  mass: 'kg',
  length: 'mm',
  time: 'ms',
  symbols: { Pa: 'GPa', 'kg/m3': 'kg/mm3', s: 'ms' },
}

beforeEach(() => {
  vi.clearAllMocks()
  unitSystems.mockResolvedValue([SI, CUSTOM])
  deriveUnitSystem.mockImplementation(({ length }: { length: string }) =>
    Promise.resolve(
      length === 'mm'
        ? { ...CUSTOM, key: 'preview', declaration: 'kg, mm, ms, GPa' }
        : { ...SI, key: 'preview' }
    )
  )
  createUnitSystem.mockResolvedValue(CUSTOM)
  removeUnitSystem.mockResolvedValue(undefined)
})

describe('덱 단위계', () => {
  it('붙박이는 지우기가 없고, 만든 것만 지운다', async () => {
    render(<UnitSystemsSection canEdit />)
    await screen.findByText('LS-DYNA (GPa)')
    expect(screen.queryByLabelText('SI (kg · m · s · Pa) 지우기')).toBeNull()
    await userEvent.click(screen.getByLabelText('LS-DYNA (GPa) 지우기'))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '삭제' }))
    await waitFor(() => expect(removeUnitSystem).toHaveBeenCalledWith('mm_ms_kg'))
  })

  it('관리자가 아니면 만들기·지우기가 없다', async () => {
    render(<UnitSystemsSection canEdit={false} />)
    await screen.findByText('LS-DYNA (GPa)')
    expect(screen.queryByRole('button', { name: '단위계 만들기' })).toBeNull()
    expect(screen.queryByLabelText('LS-DYNA (GPa) 지우기')).toBeNull()
  })

  it('셋을 고르면 유도된 기호가 보이고, 만들기는 그 셋을 보낸다', async () => {
    render(<UnitSystemsSection canEdit />)
    await screen.findByText('LS-DYNA (GPa)')
    await userEvent.click(screen.getByRole('button', { name: '단위계 만들기' }))
    const dialog = screen.getByRole('dialog')
    // 기본 조합(kg·mm·ms)의 미리보기 — 응력이 GPa 로 적힌다.
    await waitFor(() => expect(within(dialog).getByLabelText('유도된 단위')).toHaveTextContent('GPa'))
    expect(deriveUnitSystem).toHaveBeenLastCalledWith({ mass: 'kg', length: 'mm', time: 'ms' })

    // 같은 key 는 만들기가 막힌다 — 서버까지 안 간다.
    await userEvent.type(within(dialog).getByLabelText('key'), 'mm_ms_kg')
    expect(within(dialog).getByRole('button', { name: '만들기' })).toBeDisabled()
    await userEvent.clear(within(dialog).getByLabelText('key'))
    await userEvent.type(within(dialog).getByLabelText('key'), 'dyna')
    await userEvent.type(within(dialog).getByLabelText('이름'), '다이나')
    await userEvent.click(within(dialog).getByRole('button', { name: '만들기' }))
    await waitFor(() =>
      expect(createUnitSystem).toHaveBeenCalledWith({
        key: 'dyna',
        label: '다이나',
        mass: 'kg',
        length: 'mm',
        time: 'ms',
      })
    )
  })
})
