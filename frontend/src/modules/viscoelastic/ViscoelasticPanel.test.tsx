/**
 * 장비가 만든 마스터커브 가져오기.
 *
 * **마스터커브만 내보낸 파일도 쓸 수 있어야 한다.** TA TRIOS 같은 장비는 시간-온도
 * 중첩을 제 소프트웨어에서 하고 마스터커브를 함께 내보낸다. 장비 파일 정의가 그
 * 표를 읽어 두기는 해도 `MasterCurve` 행이 아니어서, 그런 파일은 Prony 도 글로벌
 * 피팅도 못 썼다(2026-08-30).
 *
 * 여기서 보는 것은 **조용히 틀릴 수 있는 것들**이다 — 기준 온도를 짐작해 채우거나,
 * 못 쓰는 표를 고르게 두거나, °C 를 K 자리에 그대로 보내는 것.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ViscoelasticPanel } from '@/modules/viscoelastic/ViscoelasticPanel'

const sweeps = vi.fn()
const masterCurves = vi.fn()
const importableCurves = vi.fn()
const importMasterCurve = vi.fn()
const points = vi.fn()
const pronyFits = vi.fn()
const setPrimary = vi.fn()

/** 겹쳐 놓은 마스터커브 하나. 상세 화면(곡선·이동인자·Prony)을 그리게 한다. */
const CURVE = {
  id: 'curve-1',
  test_run_id: 'run-1',
  reference_temperature_k: 293.15,
  method: 'wlf',
  parameters: { c1: 12.3, c2: 90.1 },
  shifts: [
    {
      temperature_k: 253.15,
      log10_a_t: 2.5,
      observed_log10_a_t: 2.4,
      residual: 0.1,
      source: 'wlf',
    },
  ],
  notes: [],
  is_primary: true,
  point_count: 2,
  minimum_frequency_hz: 0.01,
  maximum_frequency_hz: 100,
  source_curve_keys: [],
  created_at: '2026-08-30T00:00:00Z',
}

vi.mock('@/modules/viscoelastic/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/viscoelastic/api')>()),
  viscoelasticApi: {
    sweeps: (...args: unknown[]) => sweeps(...args),
    masterCurves: (...args: unknown[]) => masterCurves(...args),
    importableCurves: (...args: unknown[]) => importableCurves(...args),
    importMasterCurve: (...args: unknown[]) => importMasterCurve(...args),
    points: (...args: unknown[]) => points(...args),
    pronyFits: (...args: unknown[]) => pronyFits(...args),
    setPrimary: (...args: unknown[]) => setPrimary(...args),
  },
}))

const MASTER = {
  curve_key: 'tts_master_curve_20_0_c',
  label: 'TTS - master curve (20.0 °C)',
  row_count: 7,
  channels: ['frequency', 'storage_modulus'],
  usable: true,
  note: null,
}

const SHIFTS = {
  curve_key: 'tts_shift_factors',
  label: 'TTS - shift factors',
  row_count: 6,
  channels: ['temperature', 'at_x_variable'],
  usable: false,
  note: '주파수 · 저장 탄성률 열이 없습니다. 있는 열: temperature, at_x_variable',
}

function show() {
  render(<ViscoelasticPanel testRunId="run-1" />)
}

/** 가져오기 블록. 겹치기 쪽 버튼과 헷갈리지 않게 그 안에서만 찾는다. */
function block() {
  return within(screen.getByLabelText('장비가 만든 마스터커브'))
}

beforeEach(() => {
  vi.clearAllMocks()
  sweeps.mockResolvedValue({ items: [], warnings: [] })
  masterCurves.mockResolvedValue([])
  importableCurves.mockResolvedValue([MASTER, SHIFTS])
  importMasterCurve.mockResolvedValue({ id: 'made-1', method: 'imported' })
  points.mockResolvedValue({ frequency: [0.01, 100], storage_modulus: [1e9, 1e7] })
  pronyFits.mockResolvedValue([])
  setPrimary.mockResolvedValue({ ...CURVE, is_primary: true })
})

describe('장비가 만든 마스터커브 가져오기', () => {
  it('장비가 계산해 준 표가 없으면 아예 안 뜬다', async () => {
    // 대부분의 시험에는 없다. 늘 보이면 "이건 뭐지" 가 하나 는다.
    importableCurves.mockResolvedValue([])
    show()
    await waitFor(() => expect(importableCurves).toHaveBeenCalled())
    expect(screen.queryByLabelText('장비가 만든 마스터커브')).toBeNull()
  })

  it('못 쓰는 표도 이유와 함께 보인다', async () => {
    // 걸러 버리면 "내 파일에 있는 그 표가 왜 안 보이지" 가 된다.
    show()
    const shown = await screen.findByText('TTS - shift factors')
    expect(shown).toBeTruthy()
    expect(block().getByText(/저장 탄성률 열이 없습니다/)).toBeTruthy()
  })

  it('못 쓰는 표는 고를 수 없다', async () => {
    show()
    await screen.findByText('TTS - shift factors')
    expect(block().getByLabelText('TTS - shift factors 고르기')).toBeDisabled()
  })

  it('기준 온도를 안 적으면 안 보낸다', async () => {
    // **틀린 온도로 등록하면 그 곡선은 조용히 다른 온도의 해석에 쓰인다.**
    show()
    await screen.findByText(/TTS - master curve/)
    expect(block().getByRole('button', { name: '가져오기' })).toBeDisabled()
    expect(importMasterCurve).not.toHaveBeenCalled()
  })

  it('이름에 적힌 온도를 자동으로 채우지 않는다', async () => {
    // 힌트로만 보인다 — 장비가 다른 뜻으로 적은 숫자가 기준 온도로 굳으면 안 된다.
    show()
    await screen.findByText(/TTS - master curve/)
    expect(block().getByText(/이름에 적힌 온도: 20.0/)).toBeTruthy()
    expect(block().getByLabelText('기준 온도')).toHaveValue('')
  })

  it('적은 온도를 켈빈으로 바꿔 보낸다', async () => {
    // **여기가 조용히 틀리는 자리다.** 20 을 20 K 로 보내면 -253 °C 곡선이 된다.
    show()
    await screen.findByText(/TTS - master curve/)
    await userEvent.type(block().getByLabelText('기준 온도'), '20')
    await userEvent.click(block().getByRole('button', { name: '가져오기' }))
    await waitFor(() => expect(importMasterCurve).toHaveBeenCalled())
    expect(importMasterCurve).toHaveBeenCalledWith('run-1', {
      curve_key: 'tts_master_curve_20_0_c',
      reference_temperature_k: 293.15,
    })
  })

  it('여럿이면 고른 것을 보낸다', async () => {
    const other = { ...MASTER, curve_key: 'tts_master_curve_60_0_c', label: 'TTS - 60 °C' }
    importableCurves.mockResolvedValue([MASTER, other, SHIFTS])
    show()
    await screen.findByText('TTS - 60 °C')
    await userEvent.click(block().getByLabelText('TTS - 60 °C 고르기'))
    await userEvent.type(block().getByLabelText('기준 온도'), '60')
    await userEvent.click(block().getByRole('button', { name: '가져오기' }))
    await waitFor(() => expect(importMasterCurve).toHaveBeenCalled())
    expect(importMasterCurve.mock.calls[0][1].curve_key).toBe('tts_master_curve_60_0_c')
  })

  it('가져오고 나면 목록을 다시 읽는다', async () => {
    // 안 그러면 "눌렀는데 아무 일도 안 일어났다" 가 된다 — 등록은 됐는데 화면이 옛것이다.
    show()
    await screen.findByText(/TTS - master curve/)
    await waitFor(() => expect(masterCurves).toHaveBeenCalledTimes(1))
    await userEvent.type(block().getByLabelText('기준 온도'), '20')
    await userEvent.click(block().getByRole('button', { name: '가져오기' }))
    await waitFor(() => expect(masterCurves).toHaveBeenCalledTimes(2))
  })
})

describe('마스터커브 상세', () => {
  it('곡선과 숫자를 함께 보여 준다', async () => {
    // **견주는 것이 이 화면의 일이다.** 세로로 이어 붙이면 곡선이 화면 하나를
    // 먹어서, 이동인자를 볼 때 곡선이 화면 밖으로 나간다.
    masterCurves.mockResolvedValue([CURVE])
    show()
    expect(await screen.findByText('이동인자')).toBeInTheDocument()
    expect(screen.getByText(/Prony 계수 맞추기/)).toBeInTheDocument()
    // 겹치기에 쓴 모델의 계수도 그대로 남는다.
    expect(screen.getByText(/c1/)).toBeInTheDocument()
  })
})

describe('대표 마스터커브', () => {
  const OTHER = {
    ...CURVE,
    id: 'curve-2',
    reference_temperature_k: 303.15,
    is_primary: false,
  }

  it('어느 것이 대표인지 표시한다', async () => {
    // **재료로 나가는 것은 대표 하나다.** 전에는 「가장 최근 것」 이 말없이 쓰여,
    // 하나 더 만든 순간 재료 쪽 계산이 바뀌는데 화면에 아무 표시가 없었다.
    masterCurves.mockResolvedValue([CURVE, OTHER])
    show()
    // 「대표」 라는 글자는 안내 문장에도 있다 — **배지**가 목록의 그 곡선에
    // 붙어 있는지를 본다.
    const marks = await screen.findAllByText('대표')
    expect(marks.some((one) => one.closest('button'))).toBe(true)
  })

  it('고른 것이 대표가 아니면 옮길 수 있다', async () => {
    masterCurves.mockResolvedValue([OTHER, CURVE])
    show()
    // 목록의 첫 곡선이 골라진다 — 그것이 대표가 아니면 옮기는 길이 보여야 한다.
    const move = await screen.findByRole('button', { name: '고른 것을 대표로' })
    await userEvent.click(move)
    await waitFor(() => expect(setPrimary).toHaveBeenCalledWith('curve-2'))
    // **옮긴 뒤 다시 읽는다.** 안 읽으면 배지가 옛 자리에 남는다.
    await waitFor(() => expect(masterCurves).toHaveBeenCalledTimes(2))
  })

  it('이미 대표면 옮기는 길을 안 만든다', async () => {
    masterCurves.mockResolvedValue([CURVE, OTHER])
    show()
    await screen.findAllByText('대표')
    expect(screen.queryByRole('button', { name: '고른 것을 대표로' })).toBeNull()
  })
})
