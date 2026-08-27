/**
 * 시편 치수 화면 — **칸을 화면이 정하지 않는다.**
 *
 * 전에는 두께·폭·게이지 세 칸이 이 파일에 적혀 있었다. 그래서 환봉 시편은 직경을
 * 적을 자리가 없었다 — 같은 인장 시험인데 평판은 폭·두께를 갖고 환봉은 직경을
 * 갖는다. 이제 규격이 칸을 정하고(ADR 0010) 화면은 그것을 그린다.
 *
 * 여기서 지키는 것:
 *
 *   규격의 칸이 그려진다   직경 칸이 나온다
 *   공칭은 흐리게          빈 칸의 자리표시가 규격값이다
 *   빈 칸은 안 보낸다      '안 쟀다' 와 '쟀는데 0' 은 다르다
 *   저장은 SI, 화면은 mm   `0.025` 를 치라고 하면 누군가 `25` 를 친다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { EditSpecimenDialog } from '@/modules/materials/EditSpecimenDialog'
import type { Specimen } from '@/modules/materials/api'

const dimensions = vi.fn()
const saveDimensions = vi.fn()
const updateSpecimen = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/materials/api')>()),
  materialsApi: {
    dimensions: (...args: unknown[]) => dimensions(...args),
    saveDimensions: (...args: unknown[]) => saveDimensions(...args),
    updateSpecimen: (...args: unknown[]) => updateSpecimen(...args),
  },
}))

/** 규격 피커는 서버를 부른다. 이 파일이 지키는 것과 무관하다. */
vi.mock('@/modules/vocabulary/VocabularyField', () => ({
  VocabularyField: ({ value }: { value: string }) => <div>규격 {value}</div>,
}))

const size = (key: string, label: string, extra: Record<string, unknown> = {}) => ({
  key,
  label,
  dimension: 'length',
  si_unit: 'm',
  is_required: false,
  help: null,
  inherited: true,
  nominal: null,
  measured: null,
  source: null,
  ...extra,
})

const SPECIMEN = {
  id: 'sp-1',
  record_name: 'SECC_1_MD_1',
  orientation: 'MD',
  standard: 'ASTM E8 R1',
  note: null,
} as unknown as Specimen

function show() {
  render(
    <EditSpecimenDialog specimen={SPECIMEN} open onClose={() => {}} onSaved={() => {}} />
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  updateSpecimen.mockResolvedValue(SPECIMEN)
  saveDimensions.mockResolvedValue({ fields: [], area: null })
  dimensions.mockResolvedValue({
    standard: 'ASTM E8 R1',
    cross_section: 'circle',
    cross_section_label: '환봉 (직경)',
    area: 1.227e-4,
    area_problem: null,
    fields: [
      size('gauge_length', '게이지 길이', { nominal: 0.05 }),
      size('diameter', '직경', { nominal: 0.0125, measured: 0.01248, source: 'measured' }),
    ],
  })
})

describe('시편 치수', () => {
  it('규격이 준 칸을 그린다', async () => {
    // **이 파일의 이유.** 세 칸을 화면에 박아 두면 환봉을 영영 못 담는다.
    show()
    expect(await screen.findByLabelText(/직경/)).toBeInTheDocument()
    expect(screen.getByLabelText(/게이지 길이/)).toBeInTheDocument()
  })

  it('잰 값은 mm 로 보인다', async () => {
    // 서버는 SI(m) 로 준다. `0.01248` 을 그대로 그리면 아무도 안 읽는다.
    show()
    expect(await screen.findByLabelText<HTMLInputElement>(/직경/)).toHaveValue('12.48')
  })

  it('안 잰 칸은 규격값을 흐리게 보여 준다', async () => {
    // **합쳐서 하나로 보여 주면 사람은 전부 실측으로 읽는다.**
    show()
    const gauge = await screen.findByLabelText<HTMLInputElement>(/게이지 길이/)
    expect(gauge).toHaveValue('')
    expect(gauge).toHaveAttribute('placeholder', '규격 50')
  })

  it('빈 칸은 안 보낸다', async () => {
    const user = userEvent.setup()
    show()
    await screen.findByLabelText(/직경/)
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(saveDimensions).toHaveBeenCalled())
    const [, values] = saveDimensions.mock.calls[0]
    // 게이지는 안 쟀다 — 키가 없어야 규격의 공칭이 쓰인다.
    expect(Object.keys(values)).toEqual(['diameter'])
    expect(values.diameter).toBeCloseTo(0.01248, 10)
  })

  it('친 값은 SI 로 바꿔 보낸다', async () => {
    const user = userEvent.setup()
    show()
    const gauge = await screen.findByLabelText<HTMLInputElement>(/게이지 길이/)
    await user.type(gauge, '49.8')
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(saveDimensions).toHaveBeenCalled())
    expect(saveDimensions.mock.calls[0][1].gauge_length).toBeCloseTo(0.0498, 10)
  })

  it('단면적을 못 내면 이유를 말한다', async () => {
    // **처리 화면에서 만나면 어디를 채울지 모른 채 되돌아온다.**
    dimensions.mockResolvedValue({
      standard: 'ASTM E8',
      cross_section: null,
      cross_section_label: null,
      area: null,
      area_problem: '단면적 식을 안 골랐고 폭·두께도 없습니다.',
      fields: [size('gauge_length', '게이지 길이')],
    })
    show()
    expect(await screen.findByText(/단면적 식을 안 골랐고/)).toBeInTheDocument()
  })

  it('규격 비율을 어기면 말하되 막지 않는다', async () => {
    // **규격이 권장값을 주는데 장비가 못 맞추는 일이 실제로 있다** — ISO 6721-4 는
    // 클램프 간 50~100 mm 를 권하지만 어느 DMA 장비도 그 값을 못 준다. 막으면
    // 실제로 잰 데이터를 못 넣고, 그러면 사람은 시스템 밖에서 일한다.
    const user = userEvent.setup()
    dimensions.mockResolvedValue({
      standard: 'ISO 6721-3',
      cross_section: null,
      cross_section_label: null,
      area: null,
      area_problem: null,
      fields: [size('gauge_length', '게이지 길이', { measured: 0.05 })],
      warnings: [
        {
          condition: '게이지 길이 / 두께 >= 50',
          actual: 10,
          help: '저장탄성률 ±5 % 정확도 확보',
        },
      ],
    })
    show()

    const notice = (await screen.findByText(/규격이 요구하는 비율/)).closest('div')
    expect(notice).toHaveTextContent('게이지 길이 / 두께 >= 50')
    expect(notice).toHaveTextContent('10.0')

    // 그래도 저장은 된다.
    await user.click(screen.getByRole('button', { name: '저장' }))
    await waitFor(() => expect(saveDimensions).toHaveBeenCalled())
  })
})

describe('방향 바꾸기', () => {
  /**
   * *"시편 수정에도 안 보여"* — 실사용에서 나왔다.
   *
   * 전에는 뱃지로 보여 주기만 했고 서버도 안 받았다. 잘못 고른 것을 되돌리려면
   * 지우고 다시 만드는 수밖에 없었고, 그러면 그 시편의 **시험이 함께 사라진다**.
   */
  it('고를 수 있다', async () => {
    show()
    expect(await screen.findByRole('button', { name: 'TD' })).toBeInTheDocument()
  })

  it('바꾸면 이름이 다시 매겨진다고 미리 말한다', async () => {
    // **방향만 골랐는데 번호까지 달라지는 것**은 사람이 예상 못 하는 일이다.
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: 'TD' }))
    expect(await screen.findByText(/이름과 번호가 다시 매겨집니다/)).toBeInTheDocument()
    expect(screen.getByText(/시험 이름도 함께/)).toBeInTheDocument()
  })

  it('안 바꾸면 아무 말도 안 한다', async () => {
    show()
    await screen.findByRole('button', { name: 'TD' })
    expect(screen.queryByText(/이름과 번호가 다시 매겨집니다/)).not.toBeInTheDocument()
  })

  it('고른 방향이 서버로 간다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(await screen.findByRole('button', { name: 'TD' }))
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(updateSpecimen).toHaveBeenCalled())
    const body = updateSpecimen.mock.calls[0][1] as Record<string, unknown>
    expect(body.orientation).toBe('TD')
  })
})
