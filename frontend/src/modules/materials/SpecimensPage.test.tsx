/**
 * 시편 표 — **거르기가 서버로 나가는가.**
 *
 * 무는 자리를 여기로 고른 이유: 표가 그려지는 것은 시험이 없어도 눈에 보이지만,
 * **화면에서 걸러 버리는 실수는 조용히 틀린다.** 50건짜리 쪽에서 「MD」 를
 * 골랐는데 다음 쪽의 MD 가 안 나오면, 사람은 그것을 「없다」 로 읽는다.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SpecimensPage from '@/modules/materials/SpecimensPage'

const specimenRows = vi.fn()
const bulkUpdateSpecimens = vi.fn()
const specimenFacets = vi.fn()
const relocatePlan = vi.fn()
const relocate = vi.fn()

//: 서버가 센 거르기 목록 — 재료는 id 가 key, 규격은 「(없음)」 이 끝에 선다.
const FACETS = {
  materials: [{ key: 'm1', label: 'SECC', count: 3 }],
  lots: [
    { key: 'L-9', label: 'L-9', count: 2 },
    { key: 'L-90', label: 'L-90', count: 1 },
  ],
  standards: [
    { key: 'ASTM E8/E8M 박판형', label: 'ASTM E8/E8M 박판형', count: 2 },
    { key: '__none__', label: '(없음)', count: 1 },
  ],
  orientations: [
    { key: 'MD', label: 'MD', count: 2 },
    { key: 'TD', label: 'TD', count: 1 },
  ],
  // key 는 비율 — 0개인 선택지는 서버가 안 준다.
  thickness_gaps: [
    { key: '0.05', label: '기준 두께와 5% 이상 차이', count: 2 },
    { key: '0.2', label: '기준 두께와 20% 이상 차이', count: 1 },
  ],
}

// **이 화면은 이제 로그인한 사람을 안다** — 정렬을 그 계정 자리에 적어 두기
// 때문이다. 프로바이더 없이 `useAuth` 를 부르면 던지는데, 그 가드는 옳다.
// 일괄 수정의 기준정보 칸은 **내가 관리자인지**를 본다(새 값은 부서 관리자만,
// ADR 0032) — 그쪽은 제공자 밖에서도 뜨는 칸이라 `useMaybeAuth` 를 쓴다.
vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'user-1' } }),
  useMaybeAuth: () => ({ user: { id: 'user-1', memberships: [] } }),
}))

vi.mock('@/modules/materials/api', async () => {
  const actual =
    await vi.importActual<typeof import('@/modules/materials/api')>('@/modules/materials/api')
  return {
    ...actual,
    materialsApi: {
      specimenRows: (...args: unknown[]) => specimenRows(...args),
      specimenFacets: (...args: unknown[]) => specimenFacets(...args),
      bulkUpdateSpecimens: (...args: unknown[]) => bulkUpdateSpecimens(...args),
      relocatePlan: (...args: unknown[]) => relocatePlan(...args),
      relocate: (...args: unknown[]) => relocate(...args),
    },
  }
})

const ROW = {
  id: 'sp1',
  code: 'P-000187',
  sample_id: 'sa1',
  workspace_id: 'w1',
  material_id: 'm1',
  material_name: 'SECC_MDOI_1.0',
  sample_name: 'SECC_MDOI_1.0__01',
  lot_no: 'L-9',
  seq_no: 1,
  orientation: 'MD',
  record_name: 'SECC_MDOI_1.0__01_MD_01',
  standard: 'ASTM E8/E8M 박판형',
  // 응답은 SI 다(2026-09-24). 화면은 이 셋이 아니라 `sizes` 를 읽는다.
  thickness: 0.0008,
  width: 0.0125,
  gauge_length: 0.05,
  length_unit: 'm',
  sizes: [{ key: 'thickness', label: '두께', value: 0.0008, source: 'measured', si_unit: 'm' }],
  note: null,
  created_at: '2026-08-28T00:00:00Z',
  test_run_count: 2,
  adopted_count: 1,
  failed_count: 0,
  registered_by: null,
}

function page(items: unknown[] = [ROW], total = items.length) {
  return { items, total, limit: 50, offset: 0 }
}

function open() {
  render(
    <MemoryRouter>
      <SpecimensPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  specimenRows.mockReset()
  bulkUpdateSpecimens.mockReset()
  specimenFacets.mockReset()
  specimenRows.mockResolvedValue(page())
  specimenFacets.mockResolvedValue(FACETS)
  bulkUpdateSpecimens.mockResolvedValue({
    updated: 1,
    unchanged: 0,
    blocked: [],
    renamed: [],
  })
  relocatePlan.mockReset()
  relocate.mockReset()
  relocatePlan.mockResolvedValue({
    specimens: 1,
    test_runs: 2,
    thickness: 1.2,
    thickness_unit: 'mm',
    targets: [
      {
        from_material_id: 'm1',
        from_material_name: 'SECC_MDOI_1.0',
        to_material_id: null,
        to_material_name: 'SECC_MDOI_1.2',
        exists: false,
        specimens: 1,
        test_runs: 2,
      },
    ],
    samples: [],
    cards: [],
    records: [],
    blocked: [],
  })
  relocate.mockResolvedValue({
    moved: 1,
    test_runs: 2,
    created_materials: ['SECC_MDOI_1.2'],
    joined_materials: [],
    split_samples: 1,
    cards_noted: 1,
    cards_deprecated: 0,
    blocked: [],
  })
})

describe('시편 표', () => {
  it('재료와 로트를 함께 보인다', async () => {
    // 시편 이름만으로는 표가 안 읽힌다 — 어느 재료의 것인지 이름 규칙에 묻혀 있다.
    open()
    expect(await screen.findByText('SECC_MDOI_1.0')).toBeInTheDocument()
    expect(screen.getByText('L-9')).toBeInTheDocument()
    expect(screen.getByText('ASTM E8/E8M 박판형')).toBeInTheDocument()
  })

  it('시편 이름이 그 시편의 자리로 가는 문이다', async () => {
    // 전에는 재료 이름만 링크였다 — 시편을 찾아 놓고도 그 시편으로는 못 가고,
    // 재료로 간 다음 시료를 하나씩 열어 눈으로 찾아야 했다(2026-09-11 지적).
    open()

    const link = await screen.findByRole('link', { name: /SECC_MDOI_1\.0__01_MD_01/ })
    expect(link).toHaveAttribute(
      'href',
      '/materials/m1?tab=samples&sample=sa1&specimen=sp1'
    )
  })

  it('규격이 없으면 그 사실을 드러낸다', async () => {
    /**
     * **비어 있다는 것이 중요한 정보다.** 규격이 없으면 그 시편은 치수 칸조차
     * 못 갖는다(ADR 0010) — 이관에서 실제로 그 상태가 무더기로 생겼다.
     */
    specimenRows.mockResolvedValue(page([{ ...ROW, standard: null }]))
    open()
    expect(await screen.findByText('규격 없음')).toBeInTheDocument()
  })
})

describe('열 머리에서 거른다', () => {
  it('규격은 서버가 센 목록에서 고르고, 고른 것은 정확히 나간다', async () => {
    // 치면 「E8」 이 다른 규격까지 물고, 「규격 없음」 은 쳐서는 표현이 안 된다.
    open()
    await screen.findByText('SECC_MDOI_1.0')

    const picker = await screen.findByLabelText('규격 로 필터')
    await userEvent.selectOptions(picker, '__none__')
    await waitFor(() =>
      expect(specimenRows).toHaveBeenLastCalledWith(
        expect.objectContaining({ standard_exact: '__none__' })
      )
    )
    // 수가 옆에 붙는다 — 서버가 센 것이다.
    expect(screen.getByRole('option', { name: /\(없음\).*1/ })).toBeInTheDocument()
  })

  it('재료는 이름이 아니라 id 로 나간다', async () => {
    // 개명돼도 걸어 둔 거르개가 살아 있어야 한다.
    open()
    await screen.findByText('SECC_MDOI_1.0')
    await userEvent.selectOptions(await screen.findByLabelText('재료 로 필터'), 'm1')
    await waitFor(() =>
      expect(specimenRows).toHaveBeenLastCalledWith(expect.objectContaining({ material_id: 'm1' }))
    )
  })

  it('방향은 고르는 칸이다', async () => {
    // 넷뿐이라 자유 입력으로 두면 `md` 를 쳐서 0건을 보게 된다.
    open()
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.selectOptions(screen.getByLabelText('방향 로 필터'), 'TD')
    await waitFor(() =>
      expect(specimenRows).toHaveBeenLastCalledWith(
        expect.objectContaining({ orientation: 'TD' })
      )
    )
  })

  it('거르면 첫 쪽으로 돌아간다', async () => {
    /**
     * 3쪽을 보다 거르면 걸러진 결과의 3쪽이 나오는데, 그게 비어 있으면 사람은
     * 「없다」 로 읽는다.
     */
    specimenRows.mockResolvedValue(page([ROW], 300))
    open()
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.click(screen.getByRole('button', { name: '다음' }))
    await waitFor(() =>
      expect(specimenRows).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 50 }))
    )

    await userEvent.selectOptions(await screen.findByLabelText('로트 로 필터'), 'L-9')
    await waitFor(() =>
      expect(specimenRows).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 0 }))
    )
  })
})


describe('일괄 수정', () => {
  it('고르기 전에는 단추가 없다', async () => {
    // 아무것도 안 고른 채로 열리면 「0건에 걸기」 가 된다.
    open()
    await screen.findByText('SECC_MDOI_1.0')
    expect(screen.queryByRole('button', { name: '일괄 수정' })).not.toBeInTheDocument()
  })

  it('고른 시편에만 건다', async () => {
    open()
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.click(screen.getByLabelText('SECC_MDOI_1.0__01_MD_01 선택'))
    await userEvent.click(screen.getByRole('button', { name: '일괄 수정' }))
    await screen.findByRole('dialog')

    await userEvent.click(screen.getByRole('button', { name: /1건에 적용/ }))
    await waitFor(() =>
      expect(bulkUpdateSpecimens).toHaveBeenCalledWith(['sp1'], 'standard', null)
    )
  })

  it('거르면 선택이 풀린다', async () => {
    /**
     * **걸러서 안 보이게 된 줄이 골라진 채 남으면** 「12건에 걸기」 가 화면에
     * 없는 것까지 건드린다.
     */
    open()
    await screen.findByText('SECC_MDOI_1.0')
    await userEvent.click(screen.getByLabelText('SECC_MDOI_1.0__01_MD_01 선택'))
    expect(screen.getByRole('button', { name: '일괄 수정' })).toBeInTheDocument()

    await userEvent.selectOptions(await screen.findByLabelText('로트 로 필터'), 'L-9')
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '일괄 수정' })).not.toBeInTheDocument()
    )
  })
})


describe('다른 두께로 옮기기', () => {
  it('고른 시편만 옮기고, 무엇이 어디로 갔는지 말한 뒤 표를 다시 읽는다', async () => {
    // 「옮겼습니다」 만으로는 새 재료가 생겼는지, 카드에 무엇이 붙었는지 모른다.
    open()
    await screen.findByText('SECC_MDOI_1.0')
    expect(screen.queryByRole('button', { name: '다른 두께로 옮기기' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByLabelText('SECC_MDOI_1.0__01_MD_01 선택'))
    await userEvent.click(screen.getByRole('button', { name: '다른 두께로 옮기기' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText(/기준 두께/), '1.2')
    // 그려진 계획을 기다린다 — 옮기기 단추는 계획이 와야 풀린다.
    await within(dialog).findByText(/없어서 새로 만듭니다/)
    const calls = specimenRows.mock.calls.length
    await userEvent.click(within(dialog).getByRole('button', { name: '시편 1개 옮기기' }))

    expect(
      await screen.findByText(/SECC_MDOI_1\.2\(새로 만듦\) 로 옮겼습니다/)
    ).toHaveTextContent('카드 1장에 코멘트를 남겼습니다')
    expect(relocate.mock.calls[0][0]).toMatchObject({ specimen_ids: ['sp1'] })
    await waitFor(() => expect(specimenRows.mock.calls.length).toBeGreaterThan(calls))
  })
})


describe('번호', () => {
  it('번호가 첫 열에 서고, 그 열로 서버에 정렬을 묻는다', async () => {
    // 이름은 밑줄로 엮여 길고 옮기면 바뀐다 — 말로 전할 손잡이는 번호다(ADR 0043).
    open()
    expect(await screen.findByText('P-000187')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '번호 로 정렬' }))
    await waitFor(() =>
      expect(specimenRows).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'code' }))
    )
  })
})


describe('기준 두께와 차이', () => {
  it('치수 열은 기준 두께와의 차이로 거르고, 고른 것은 서버로 나간다', async () => {
    // **화면에서 거르면 이 쪽에 실린 것만 걸러진다** — 다른 두께에 넣은 시편이 다음 쪽에
    // 있으면 「없다」 로 읽힌다.
    open()
    await screen.findByText('SECC_MDOI_1.0')

    const picker = await screen.findByLabelText('치수 로 필터')
    expect(
      within(picker).getByRole('option', { name: '기준 두께와 20% 이상 차이 (1)' })
    ).toBeInTheDocument()
    await userEvent.selectOptions(picker, '0.2')
    await waitFor(() =>
      expect(specimenRows).toHaveBeenLastCalledWith(
        expect.objectContaining({ thickness_gap: 0.2, offset: 0 })
      )
    )
  })

  it('크게 다른 줄에는 무엇과 무엇을 견줬는지 말한다', async () => {
    // 시험 파일이 잰 두께는 치수 칸에 안 보인다 — 배지가 말하지 않으면 왜 걸렸는지 모른다.
    specimenRows.mockResolvedValue(
      page([
        {
          ...ROW,
          thickness_gap: { spec: 0.0008, value: 0.001, deviation: 0.25, source: 'run' },
        },
        {
          ...ROW,
          id: 'sp2',
          record_name: 'SECC_MDOI_1.0__01_MD_02',
          thickness_gap: { spec: 0.0008, value: 0.000816, deviation: 0.02, source: 'measured' },
        },
      ])
    )
    open()

    // 시험 파일이 잰 값은 치수 칸에 없으니 배지가 적는다.
    const badge = await screen.findByText('시험 파일 1 mm · 기준 대비 +25%')
    expect(badge).toHaveAttribute('title', expect.stringContaining('시험 파일이 잰 두께 1 mm'))
    expect(badge).toHaveAttribute('title', expect.stringContaining('기준 두께 0.8 mm'))
    // 압연 공차(2%)는 표시하지 않는다 — 가장 작은 선택지(5%)보다 작다.
    expect(screen.getAllByText(/기준 대비/)).toHaveLength(1)
  })
})


describe('정렬', () => {
  it('기본은 최근 등록순으로 서버에 묻는다', async () => {
    // **목록에는 늘 순서가 있어야 한다.** 「정렬 없음」 은 DB 가 주는 대로라는
    // 뜻이고, 그건 쪽마다 달라질 수 있어 순서가 아니다.
    open()
    await waitFor(() =>
      expect(specimenRows).toHaveBeenCalledWith(
        expect.objectContaining({ sort: 'created_at', desc: true })
      )
    )
  })

  it('누르면 그 열로 서버에 다시 묻는다', async () => {
    /** **화면에서 정렬하면 이 쪽에 실린 것만 정렬된다.** 거르기와 같은 거짓말이다. */
    open()
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.click(screen.getByRole('button', { name: '규격 로 정렬' }))
    await waitFor(() =>
      expect(specimenRows).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort: 'standard', desc: true })
      )
    )
  })

  it('같은 열을 다시 누르면 뒤집는다', async () => {
    open()
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.click(screen.getByRole('button', { name: '규격 로 정렬' }))
    await userEvent.click(screen.getByRole('button', { name: '규격 로 정렬' }))
    await waitFor(() =>
      expect(specimenRows).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort: 'standard', desc: false })
      )
    )
  })

  it('새 열은 내림차순부터', async () => {
    // 등록 일시·시험일처럼 **최근 것이 궁금한 열**이 많다. 오름차순부터 시작하면
    // 거의 매번 두 번 눌러야 한다.
    open()
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.click(screen.getByRole('button', { name: '규격 로 정렬' }))
    await userEvent.click(screen.getByRole('button', { name: '규격 로 정렬' }))
    await userEvent.click(screen.getByRole('button', { name: '로트 로 정렬' }))
    await waitFor(() =>
      expect(specimenRows).toHaveBeenLastCalledWith(
        expect.objectContaining({ sort: 'lot_no', desc: true })
      )
    )
  })
})
