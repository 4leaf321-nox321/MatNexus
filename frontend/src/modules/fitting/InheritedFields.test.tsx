/**
 * 푸아송비·밀도 칸 — **비우면 무엇이 들어오는지 보이는가.**
 *
 * 「재료에 있으면 비워 두세요」 만 적혀 있어서 사람은 그 값이 무엇인지 모른 채
 * 비웠다(2026-09-05). 값과 출처가 칸 옆에 서야 한다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { InheritedFields } from '@/modules/fitting/InheritedFields'

const inherited = vi.fn()

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: {
    inherited: (...args: unknown[]) => inherited(...args),
  },
}))

const ROWS = [
  {
    key: 'poisson_ratio',
    label: '푸아송비',
    value: 0.29,
    si_unit: '1',
    source: 'material',
    detail: '재료에 적힌 값입니다.',
  },
  {
    key: 'density',
    label: '밀도',
    value: 7900,
    si_unit: 'kg/m3',
    source: 'sample',
    detail: '시료에서 잰 값입니다 (7.9e-09 tonne/mm3).',
  },
]

function Host({ rows, materialId }: { rows?: typeof ROWS; materialId?: string }) {
  return (
    <InheritedFields
      rows={rows}
      materialId={materialId}
      idPrefix="t"
      poisson=""
      density=""
      onPoisson={() => {}}
      onDensity={() => {}}
    />
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  inherited.mockResolvedValue(ROWS)
})

describe('물려받을 값', () => {
  it('아는 값이 있으면 자리 표시자와 출처에 그 값을 적는다', () => {
    render(<Host rows={ROWS} />)
    expect(screen.getByLabelText('푸아송비')).toHaveAttribute('placeholder', '0.29 (물려받음)')
    expect(screen.getByText(/재료에 적힌 값입니다/)).toBeInTheDocument()
    expect(screen.getByText(/시료에서 잰 값입니다/)).toBeInTheDocument()
  })

  it('밀도는 라벨의 표시 단위로 적는다', () => {
    // 라벨은 tonne/mm³ 인데 자리 표시자가 kg/m³ 값(7900)이면 그대로 적는 사람이 생긴다 —
    // 그 값은 SI 로 나가서 카드가 10¹² 배 무거워진다.
    render(<Host rows={ROWS} />)
    expect(screen.getByLabelText(/밀도/)).toHaveAttribute('placeholder', '7.9e-9 (물려받음)')
  })

  it('재료만 주면 서버에 물어본다', async () => {
    render(<Host materialId="m1" />)
    await waitFor(() => expect(inherited).toHaveBeenCalledWith('m1'))
    expect(await screen.findByText(/시료에서 잰 값입니다/)).toBeInTheDocument()
  })

  it('없으면 왜 없는지 서버의 말을 그대로 보인다', () => {
    render(
      <Host
        rows={[
          {
            key: 'density',
            label: '밀도',
            value: null as unknown as number,
            si_unit: 'kg/m3',
            source: 'conflict',
            detail: '시료마다 밀도가 다릅니다(7800, 7900 kg/m3) — 쓸 값을 직접 넣으세요.',
          },
        ]}
      />
    )
    expect(screen.getByText(/시료마다 밀도가 다릅니다/)).toBeInTheDocument()
    expect(screen.getByLabelText(/밀도/)).toHaveAttribute('placeholder', '값 없음 — 비우면 넣지 않음')
  })

  it('적으면 직접 입력이라고 말하고 값은 그대로 둔다', async () => {
    const onPoisson = vi.fn()
    render(
      <InheritedFields
        rows={ROWS}
        idPrefix="t"
        poisson="0.3"
        density=""
        onPoisson={onPoisson}
        onDensity={() => {}}
      />
    )
    expect(screen.getByText('직접 입력한 값을 씁니다.')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('푸아송비'), '1')
    expect(onPoisson).toHaveBeenCalled()
  })
})
