/**
 * 부서 선택기 — **경로가 보이고, 검색이 그 안에서 된다.**
 *
 * 컴포넌트를 실제로 열어 본다. 렌더만 확인하는 테스트는 "드롭다운이 안 열린다"
 * 같은 결함을 못 잡는다 — 이 저장소에서 실제로 그런 결함이 났고(Select 프리미티브
 * 가 트리거를 덮은 채 떴다) 사용자가 발견했다.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { WorkspacePicker } from '@/modules/workspaces/WorkspacePicker'
import type { PickableWorkspace } from '@/modules/workspaces/WorkspacePicker'

const TREE: PickableWorkspace[] = [
  { slug: 'dev', name: '개발본부', path: '개발본부', depth: 0, is_active: true },
  {
    slug: 'dev-quality',
    name: '품질팀',
    path: '개발본부 / 품질팀',
    depth: 1,
    is_active: true,
  },
  { slug: 'prod', name: '생산본부', path: '생산본부', depth: 0, is_active: true },
  {
    slug: 'prod-quality',
    name: '품질팀',
    path: '생산본부 / 품질팀',
    depth: 1,
    is_active: true,
  },
  {
    slug: 'old',
    name: '옛날팀',
    path: '옛날팀',
    depth: 0,
    is_active: false,
  },
]

function open() {
  return userEvent.click(screen.getByRole('button'))
}

describe('WorkspacePicker', () => {
  it('고른 부서를 경로로 보여 준다', () => {
    // **같은 이름의 팀이 본부마다 있다.** 이름만 보여 주면 어느 쪽인지 알 수 없다.
    render(<WorkspacePicker workspaces={TREE} value="prod-quality" onChange={() => {}} />)
    expect(screen.getByRole('button')).toHaveTextContent('생산본부 / 품질팀')
  })

  it('열면 검색칸에 커서가 간다', async () => {
    // 한 번 더 클릭하게 만들면 검색을 안 쓰게 된다.
    render(<WorkspacePicker workspaces={TREE} value={null} onChange={() => {}} />)
    await open()
    expect(screen.getByPlaceholderText('부서 이름으로 찾기')).toHaveFocus()
  })

  it('경로 전체로 검색한다', async () => {
    render(<WorkspacePicker workspaces={TREE} value={null} onChange={() => {}} />)
    await open()
    // 사람은 `개발 품질` 처럼 위아래를 섞어 친다.
    await userEvent.type(screen.getByPlaceholderText('부서 이름으로 찾기'), '개발 품질')

    const items = screen.getAllByRole('button').filter((node) => node.textContent === '품질팀')
    expect(items).toHaveLength(1)
  })

  it('없으면 없다고 말한다', async () => {
    // 빈 목록을 그냥 비워 두면 고장으로 보인다.
    render(<WorkspacePicker workspaces={TREE} value={null} onChange={() => {}} />)
    await open()
    await userEvent.type(screen.getByPlaceholderText('부서 이름으로 찾기'), 'zzz')
    expect(screen.getByText(/에 맞는 부서가 없습니다/)).toBeInTheDocument()
  })

  it('고르면 slug 를 준다', async () => {
    const onChange = vi.fn()
    render(<WorkspacePicker workspaces={TREE} value={null} onChange={onChange} />)
    await open()
    await userEvent.click(screen.getByText('생산본부'))
    expect(onChange).toHaveBeenCalledWith('prod')
  })

  it('새로 배정하는 자리에서는 보관 부서를 감춘다', async () => {
    render(
      <WorkspacePicker workspaces={TREE} value={null} onChange={() => {}} excludeArchived />
    )
    await open()
    expect(screen.queryByText('옛날팀')).not.toBeInTheDocument()
  })

  it('이미 골라져 있는 보관 부서는 남긴다', async () => {
    // 감추면 라벨이 빈칸이 되어 무엇이 골라져 있는지 알 수 없다.
    render(
      <WorkspacePicker workspaces={TREE} value="old" onChange={() => {}} excludeArchived />
    )
    // 트리거에 이름이 보이고,
    expect(screen.getByRole('button')).toHaveTextContent('옛날팀')
    await open()
    // 목록에도 그 항목만은 남는다(보관 표시와 함께).
    expect(screen.getAllByText('옛날팀')).toHaveLength(2)
    expect(screen.getByText('보관')).toBeInTheDocument()
  })
})
