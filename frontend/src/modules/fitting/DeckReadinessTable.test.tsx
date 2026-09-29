/**
 * 「낼 수 있는 형식」 표 — 나오는 형식은 카드와 함께, 안 나오는 형식은 **빠진 것과 채울 길**을
 * 한 줄에. 「없다」 만 말하면 다음에 무엇을 해야 하는지는 사람이 알아내야 한다.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DeckReadinessCheck, DeckReadinessTable } from '@/modules/fitting/DeckReadinessTable'

const deckReadiness = vi.fn()

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: { deckReadiness: (...args: unknown[]) => deckReadiness(...args) },
}))

const READY = {
  key: 'dyna',
  label: 'LS-DYNA 곡선',
  extension: 'k',
  ready: true,
  card_id: 'c1',
  card_label: '대표 TD',
  missing: [],
}
const BLOCKED = {
  key: 'dyna_viscoelastic',
  label: 'LS-DYNA 점탄성',
  extension: 'k',
  ready: false,
  card_id: 'c1',
  card_label: '대표 TD',
  missing: [
    {
      block: 'viscoelastic',
      label: '점탄성',
      what: ['점탄성'],
      tests: [{ key: 'dma_sweep', label: '동적 점탄성', test_type_ids: ['t1'] }],
      catalog: { property_keys: ['mechanical.prony_long_term_modulus'], values_available: 0 },
      declarable_values: ['mechanical.prony_long_term_modulus'],
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('낼 수 있는 형식', () => {
  it('나오는 형식은 카드와, 안 나오는 형식은 빠진 것과 채울 길을 보인다', async () => {
    deckReadiness.mockResolvedValue({
      material_id: 'm',
      card_count: 1,
      formats: [READY, BLOCKED],
      note: '',
    })
    render(<DeckReadinessTable materialId="m" />)
    const ready = await screen.findByTestId('readiness-dyna')
    expect(ready).toHaveTextContent('대표 TD')
    expect(ready).toHaveTextContent('나옵니다')

    const blocked = screen.getByTestId('readiness-dyna_viscoelastic')
    expect(blocked).toHaveTextContent('점탄성')
    expect(blocked).toHaveTextContent('동적 점탄성 시험을 하면 생깁니다')
    expect(blocked).toHaveTextContent('채택할 값 없음')
    expect(blocked).toHaveTextContent('적어 넣을 수 있습니다')
    expect(deckReadiness).toHaveBeenCalledWith('m')
  })

  it('그 시험 종류를 만든 부서가 없으면 그렇게 말한다 — 「시험을 하면 된다」 는 거짓이다', async () => {
    deckReadiness.mockResolvedValue({
      material_id: 'm',
      card_count: 0,
      formats: [
        {
          ...BLOCKED,
          card_id: null,
          card_label: null,
          missing: [
            {
              ...BLOCKED.missing[0],
              tests: [{ key: 'dma_sweep', label: 'dma_sweep', test_type_ids: [] }],
            },
          ],
        },
      ],
      note: '이 재료에는 카드가 없습니다 — 형식마다 무엇이 필요한지만 적었습니다.',
    })
    render(<DeckReadinessTable materialId="m" />)
    const row = await screen.findByTestId('readiness-dyna_viscoelastic')
    expect(row).toHaveTextContent('만든 부서가 아직 없습니다')
    expect(row).toHaveTextContent('없음')
    expect(screen.getByText(/카드가 없습니다/)).toBeInTheDocument()
  })
})

describe('형식 점검 모달', () => {
  it('단추를 누르기 전에는 묻지 않고, 열면 요약과 표가 서며 나오는 형식이 위로 온다', async () => {
    // 탭에 50줄이 늘 펼쳐져 있던 것을 모달로 옮겼다(2026-09-29). 서버 차례는 안 나오는 것이
    // 먼저지만, 화면은 나오는 것을 위로 올린다 — 「무엇이 나오나」 를 끝까지 굴려 찾지 않게.
    deckReadiness.mockResolvedValue({
      material_id: 'm',
      card_count: 1,
      formats: [BLOCKED, READY],
      note: '',
    })
    render(<DeckReadinessCheck materialId="m" />)
    expect(deckReadiness).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: /형식 점검/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('낼 수 있는 형식 점검')).toBeInTheDocument()
    const summary = await within(dialog).findByTestId('readiness-summary')
    expect(summary).toHaveTextContent('전체 2개 형식 중 1개를 지금 낼 수 있습니다')
    const ready = within(dialog).getByTestId('readiness-dyna')
    const blocked = within(dialog).getByTestId('readiness-dyna_viscoelastic')
    expect(ready.compareDocumentPosition(blocked) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(deckReadiness).toHaveBeenCalledTimes(1)
  })
})
