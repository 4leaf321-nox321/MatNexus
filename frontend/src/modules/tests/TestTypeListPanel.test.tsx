/**
 * 시험 종류 목록 옆패널.
 *
 * 전에는 종류마다 카드 하나를 세로로 쌓았다. 카드 하나가 채널 표 + 조건 표라
 * 백 줄이 넘는데, 개발 DB 만 해도 종류 넷에 **채널이 스물셋**이다.
 *
 * 여기서 지키는 것은 셋이다.
 *
 *   고르기 전에 규모를 안다   채널 11개짜리를 열기 전에 알아야 한다
 *   전역을 목록에서 짚는다     편집을 눌러 보고 403 을 받는 일이 없게
 *   중단된 것을 짚는다        안 쓰는 종류가 섞여 있으면 목록이 거짓말을 한다
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { TestTypeListPanel } from '@/modules/tests/TestTypeListPanel'
import { LeftPanelHost, LeftPanelProvider } from '@/shared/layout/SidePanel'

function type(overrides: Record<string, unknown> = {}) {
  return {
    id: 't1',
    key: 'tensile',
    label: '인장시험',
    abbr: 'TEN',
    description: null,
    parser_key: null,
    extensions: [],
    is_active: true,
    max_upload_bytes: null,
    max_upload_bytes_effective: 52428800,
    revision: 1,
    run_count: 120,
    owner_workspace_slug: null,
    owner_workspace_name: null,
    is_global: true,
    channels: [{ key: 'force' }, { key: 'displacement' }, { key: 'width' }],
    conditions: [{ key: 'temperature' }],
    ...overrides,
  }
}

const TYPES = [
  type(),
  type({
    id: 't2',
    key: 'dma_sweep',
    label: 'DMA 스윕',
    is_global: false,
    run_count: 2,
    channels: new Array(11).fill({ key: 'x' }),
    conditions: new Array(3).fill({ key: 'y' }),
  }),
  type({ id: 't3', key: 'old_rig', label: '옛 장비', is_active: false, run_count: 0 }),
]

function panel(current: string | null = 'tensile', onPick = vi.fn()) {
  render(
    <LeftPanelProvider>
      <LeftPanelHost />
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      <TestTypeListPanel types={TYPES as any} current={current} onPick={onPick} />
    </LeftPanelProvider>
  )
  return onPick
}

describe('시험 종류 목록', () => {
  it('고르기 전에 규모를 보인다', () => {
    // **채널 11개짜리를 열기 전에 알아야 한다.**
    panel()
    expect(screen.getByRole('button', { name: /DMA 스윕/ })).toHaveTextContent(
      '채널 11 · 조건 3 · 시험 2'
    )
  })

  it('시험이 0건이면 그 수를 안 적는다', () => {
    // 「시험 0」은 자리만 차지한다.
    panel()
    expect(screen.getByRole('button', { name: /옛 장비/ })).not.toHaveTextContent('시험 0')
  })

  it('전역을 목록에서 짚는다', () => {
    // **편집을 눌러 보고 403 을 받는 일이 없어야 한다.**
    panel()
    const global = screen.getByRole('button', { name: /인장시험/ })
    expect(global.querySelector('[aria-label="전역"]')).not.toBeNull()
    const owned = screen.getByRole('button', { name: /DMA 스윕/ })
    expect(owned.querySelector('[aria-label="전역"]')).toBeNull()
  })

  it('중단된 것을 짚는다', () => {
    panel()
    expect(screen.getByRole('button', { name: /옛 장비/ })).toHaveTextContent('중단')
    expect(screen.getByRole('button', { name: /인장시험/ })).not.toHaveTextContent('중단')
  })

  it('고른 것을 짚는다', () => {
    panel('dma_sweep')
    expect(screen.getByRole('button', { name: /DMA 스윕/ })).toHaveAttribute(
      'aria-current',
      'true'
    )
    expect(screen.getByRole('button', { name: /인장시험/ })).not.toHaveAttribute('aria-current')
  })

  it('누르면 그 종류를 넘긴다', async () => {
    const onPick = panel()
    await userEvent.click(screen.getByRole('button', { name: /DMA 스윕/ }))
    expect(onPick).toHaveBeenCalledWith('dma_sweep')
  })
})
