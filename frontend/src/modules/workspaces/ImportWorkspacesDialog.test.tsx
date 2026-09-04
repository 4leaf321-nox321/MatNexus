/**
 * 부서 트리 가져오기 창 — **계획을 보고 누른다.**
 *
 * 지키는 것이 셋이다.
 *
 *   파일을 골라도 바로 안 만든다     조직도는 잘못 들어가면 지우기 어렵다
 *   만들 것이 없으면 단추가 잠긴다    0개 가져오기는 누르는 사람을 헷갈리게 한다
 *   끝나면 몇 개가 들어왔는지 말한다   결과 없이 닫히면 「됐나?」 로 남는다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ImportWorkspacesDialog } from '@/modules/workspaces/ImportWorkspacesDialog'

const previewImport = vi.fn()
const runImport = vi.fn()

vi.mock('@/modules/workspaces/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/workspaces/api')>()),
  workspacesApi: {
    previewImport: (...args: unknown[]) => previewImport(...args),
    runImport: (...args: unknown[]) => runImport(...args),
  },
}))

const PLAN = {
  rows: [
    { line: 2, slug: 'rnd', name: '연구소', parent_slug: null, action: 'create', reason: '' },
    {
      line: 3,
      slug: 'tf-x',
      name: '충돌TF',
      parent_slug: null,
      action: 'skip_kind',
      reason: '한시 조직(TF)·개인 공간은 조직도가 아니라 들여오지 않습니다.',
    },
  ],
  created: 1,
  skipped: 1,
  errors: 0,
}

function show(onDone = vi.fn()) {
  render(<ImportWorkspacesDialog open onClose={() => {}} onDone={onDone} />)
  return onDone
}

async function pickFile() {
  const file = new File(['slug,name'], '부서정보.csv', { type: 'text/csv' })
  await userEvent.upload(screen.getByLabelText('부서 CSV 파일'), file)
}

beforeEach(() => {
  vi.clearAllMocks()
  previewImport.mockResolvedValue(PLAN)
  runImport.mockResolvedValue(PLAN)
})

describe('계획을 보고 누른다', () => {
  it('파일을 골라도 바로 만들지 않는다', async () => {
    show()
    await pickFile()
    expect(await screen.findByText(/1개를 만듭니다/)).toBeInTheDocument()
    expect(runImport).not.toHaveBeenCalled()
    // 왜 건너뛰는지 줄마다 보인다 — 세기만 하면 어느 것인지 모른다.
    expect(screen.getByText(/한시 조직/)).toBeInTheDocument()
  })

  it('가져오기를 눌러야 만들고, 끝나면 결과를 말한다', async () => {
    const onDone = show()
    await pickFile()
    await userEvent.click(await screen.findByRole('button', { name: /1개 가져오기/ }))
    await waitFor(() => expect(runImport).toHaveBeenCalled())
    expect(await screen.findByText(/1개를 만들었습니다/)).toBeInTheDocument()
    expect(onDone).toHaveBeenCalled()
  })

  it('만들 것이 없으면 단추가 잠긴다', async () => {
    previewImport.mockResolvedValue({ ...PLAN, created: 0, rows: [PLAN.rows[1]] })
    show()
    await pickFile()
    expect(await screen.findByRole('button', { name: /0개 가져오기/ })).toBeDisabled()
  })
})
