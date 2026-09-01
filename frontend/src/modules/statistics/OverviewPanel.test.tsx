/**
 * 홈 요약.
 *
 * 여기서 지키는 것은 넷이다.
 *
 *   0 은 안 보인다          막힌 게 0인데 「0」을 그리면 그것도 상태처럼 읽힌다
 *   초안과 확정을 가른다     합쳐 놓으면 「카드 11」로만 보이고 남은 일이 사라진다
 *   덮인 정도를 말한다       카드 수만 보면 많아 보인다 — 94개 중 5개가 진짜 상태
 *   막힌 곳으로 데려간다     세어만 주면 어디로 가야 하는지 모른다
 */

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { OverviewPanel } from '@/modules/statistics/OverviewPanel'
import type { Overview } from '@/modules/statistics/api'

/** 개발 DB 의 실제 모양. */
const REAL: Overview = {
  material_count: 94,
  families: [
    { key: 'Metal', label: 'Metal', count: 91 },
    { key: 'Polymer', label: 'Polymer', count: 2 },
    { key: 'Family', label: 'Family', count: 1 },
  ],
  sample_count: 91,
  specimen_count: 127,
  run_count: 122,
  test_types: [
    { key: '인장시험', label: '인장시험', count: 120 },
    { key: 'DMA 스윕', label: 'DMA 스윕', count: 2 },
  ],
  card_total: 11,
  card_published: 1,
  card_draft: 10,
  card_deprecated: 0,
  materials_with_card: 5,
  waiting_to_process: 71,
  parse_failed: 0,
  inbox_waiting: 0,
}

function panel(overrides: Partial<Overview> = {}) {
  render(
    <MemoryRouter>
      <OverviewPanel data={{ ...REAL, ...overrides }} loading={false} workspaceSlug="metal" />
    </MemoryRouter>
  )
}

describe('홈 요약', () => {
  it('세어 준 것을 보인다', () => {
    panel()
    expect(screen.getByText('94')).toBeInTheDocument()
    expect(screen.getByText('122')).toBeInTheDocument()
    // **시료와 시편을 따로 센다.** 한 칸에 `91 · 127` 로 붙여 두었더니 어느
    // 수가 어느 것인지 매번 다시 읽어야 했다.
    expect(screen.getByText('91')).toBeInTheDocument()
    expect(screen.getByText('127')).toBeInTheDocument()
  })

  it('계층 순서로 늘어놓는다', () => {
    // 재료 → 시료 → 시편 → 시험 → 카드. 데이터가 쌓이는 순서라, 어느 층에서
    // 수가 줄어드는지가 그 순서대로 봐야 보인다.
    panel()
    const labels = screen
      .getAllByText(/^(재료|시료|시편|시험|물성 카드)$/)
      .map((node) => node.textContent)
    expect(labels).toEqual(['재료', '시료', '시편', '시험', '물성 카드'])
  })

  it('초안과 확정을 가른다', () => {
    // **합쳐 놓으면 「카드 11」로만 보이고 남은 일이 사라진다.**
    panel()
    expect(screen.getByText('확정 1')).toBeInTheDocument()
    expect(screen.getByText('초안 10')).toBeInTheDocument()
  })

  it('0인 상태는 안 보인다', () => {
    // 「내림 0」을 그리면 그것도 상태처럼 읽힌다.
    panel()
    expect(screen.queryByText(/내림/)).not.toBeInTheDocument()
    expect(screen.queryByText(/읽기 실패/)).not.toBeInTheDocument()
  })

  it('막힌 게 하나도 없으면 그 줄이 통째로 사라진다', () => {
    // **"지금 막힌 게 없다" 가 한눈에 와야 한다.**
    panel({ waiting_to_process: 0, parse_failed: 0, card_draft: 0 })
    expect(screen.queryByText('남은 일')).not.toBeInTheDocument()
  })

  it('막힌 곳으로 데려간다', () => {
    // 세어만 주면 어디로 가야 하는지 모른다.
    panel({ parse_failed: 3 })
    expect(screen.getByRole('link', { name: /읽기 실패 3/ })).toHaveAttribute(
      'href',
      '/w/metal/tests?status=failed'
    )
    expect(screen.getByRole('link', { name: /처리 대기 71/ })).toBeInTheDocument()
  })

  it('덮인 정도를 말한다', () => {
    // **카드 수만 보면 많아 보인다.** 94개 중 5개라는 사실이 진짜 상태다.
    panel()
    expect(screen.getByText(/재료 5\/94 에 있음 \(5%\)/)).toBeInTheDocument()
  })

  it('분포를 셋까지 적고 나머지는 접는다', () => {
    // 분류가 늘면 줄이 무너진다.
    panel({
      families: [
        { key: 'a', label: 'A', count: 4 },
        { key: 'b', label: 'B', count: 3 },
        { key: 'c', label: 'C', count: 2 },
        { key: 'd', label: 'D', count: 1 },
      ],
    })
    expect(screen.getByText(/A 4 · B 3 · C 2 외 1/)).toBeInTheDocument()
  })

  it('잘못 만든 분류가 드러난다', () => {
    // 개발 DB 에 `Family` 라는 재료군의 재료가 1건 있었다 — 요약을 만들고
    // 나서야 보였다. **그게 요약의 값이다.**
    panel()
    expect(screen.getByText(/Metal 91 · Polymer 2 · Family 1/)).toBeInTheDocument()
  })

  it('아직 못 받았으면 자리만 잡는다', () => {
    render(
      <MemoryRouter>
        <OverviewPanel data={null} loading workspaceSlug="metal" />
      </MemoryRouter>
    )
    expect(screen.queryByText('남은 일')).not.toBeInTheDocument()
  })
})

describe('붙일 파일', () => {
  /**
   * **수집함은 「데이터 수집 체계」 안쪽에 있어 매일 여는 자리가 아니다.** 장비는
   * 매일 파일을 보내는데 아무도 안 열면 쌓인 줄도 모른다 — 메뉴 위치를 바꾸면
   * 「찾기」 는 쉬워지지만 「봐야 한다」 는 신호는 안 생긴다. 홈의 남은 일 줄이
   * 이미 그 신호를 내는 자리다.
   */
  it('붙일 것이 있으면 홈이 말하고 커넥터로 보낸다', () => {
    panel({ inbox_waiting: 7 })
    const chip = screen.getByText(/붙일 파일 7/)
    expect(chip.closest('a')).toHaveAttribute('href', '/settings/connectors')
  })

  it('0 이면 안 보인다 — 0 을 그리면 그것도 상태처럼 읽힌다', () => {
    panel({ inbox_waiting: 0 })
    expect(screen.queryByText(/붙일 파일/)).not.toBeInTheDocument()
  })
})

