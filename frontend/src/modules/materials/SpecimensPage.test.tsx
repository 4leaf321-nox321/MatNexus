/**
 * 시편 표 — **거르기가 서버로 나가는가.**
 *
 * 무는 자리를 여기로 고른 이유: 표가 그려지는 것은 시험이 없어도 눈에 보이지만,
 * **화면에서 걸러 버리는 실수는 조용히 틀린다.** 50건짜리 쪽에서 「MD」 를
 * 골랐는데 다음 쪽의 MD 가 안 나오면, 사람은 그것을 「없다」 로 읽는다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SpecimensPage from '@/modules/materials/SpecimensPage'

const specimenRows = vi.fn()
const bulkUpdateSpecimens = vi.fn()

vi.mock('@/modules/materials/api', async () => {
  const actual =
    await vi.importActual<typeof import('@/modules/materials/api')>('@/modules/materials/api')
  return {
    ...actual,
    materialsApi: {
      specimenRows: (...args: unknown[]) => specimenRows(...args),
      bulkUpdateSpecimens: (...args: unknown[]) => bulkUpdateSpecimens(...args),
    },
  }
})

const ROW = {
  id: 'sp1',
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
  thickness: 0.8,
  width: 12.5,
  gauge_length: 50,
  length_unit: 'mm',
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
  specimenRows.mockResolvedValue(page())
  bulkUpdateSpecimens.mockResolvedValue({
    updated: 1,
    unchanged: 0,
    blocked: [],
    renamed: [],
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
  it('규격을 치면 서버로 나간다', async () => {
    open()
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.type(screen.getByLabelText('규격 로 거르기'), 'E8')
    await waitFor(() =>
      expect(specimenRows).toHaveBeenLastCalledWith(expect.objectContaining({ standard: 'E8' }))
    )
  })

  it('방향은 고르는 칸이다', async () => {
    // 넷뿐이라 자유 입력으로 두면 `md` 를 쳐서 0건을 보게 된다.
    open()
    await screen.findByText('SECC_MDOI_1.0')

    await userEvent.selectOptions(screen.getByLabelText('방향 로 거르기'), 'TD')
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

    await userEvent.type(screen.getByLabelText('로트 로 거르기'), 'L')
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

    await userEvent.click(screen.getByRole('button', { name: /1건에 걸기/ }))
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

    await userEvent.type(screen.getByLabelText('로트 로 거르기'), 'L')
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '일괄 수정' })).not.toBeInTheDocument()
    )
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
