/**
 * 표로 시험 넣기.
 *
 * **곡선이 없는 시험도 데이터다.** 기존 표에 쌓인 것을 못 가져오면 사용자가
 * 옮겨오지 않는다 — 도입 성패가 여기서 갈린다.
 *
 * 여기서 지키는 것은 둘이다.
 *
 *   미리보기는 아무것도 안 쓴다        누르기 전에 무엇이 들어갈지 안다
 *   시편을 만드는지 보인다             켜 두면 표가 시편을 늘린다
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SummaryImportDialog } from '@/modules/tests/SummaryImportDialog'

const importSummaries = vi.fn()

vi.mock('@/modules/tests/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/tests/api')>()),
  testsApi: { importSummaries: (...args: unknown[]) => importSummaries(...args) },
}))

const ANSWER = {
  created: 1,
  existing: 0,
  skipped: 0,
  rejected: 0,
  specimens_created: 1,
  items: [
    {
      input: 'MD-2',
      status: 'new',
      specimen: 'SECC_1_MD_2',
      creates_specimen: true,
      run: null,
      conditions: {},
      summaries: {},
      reason: null,
      warnings: [],
    },
  ],
}

function show() {
  const onDone = vi.fn()
  render(
    <SummaryImportDialog
      sampleId="sample-1"
      sampleName="SECC_1"
      testType="tensile"
      testTypeLabel="인장시험"
      onClose={() => {}}
      onDone={onDone}
    />
  )
  return onDone
}

/** 표에 한 줄 적는다. 첫 열이 시편이다. */
async function type(user: ReturnType<typeof userEvent.setup>, value: string) {
  await user.type(screen.getByLabelText('1번 줄 시편'), value)
}

beforeEach(() => {
  vi.clearAllMocks()
  importSummaries.mockResolvedValue(ANSWER)
})

describe('표로 시험 넣기', () => {
  it('곡선이 없다는 것을 먼저 말한다', () => {
    // **모자란 데이터라는 뜻이 아니다** — 낼 수 있는 물성의 범위가 다를 뿐이다.
    show()
    expect(screen.getByText(/곡선은/)).toBeInTheDocument()
  })

  it('요약값 열을 사람이 정한다', async () => {
    // **표마다 열이 다르고 미리 알 방법이 없다.**
    const user = userEvent.setup()
    show()
    await user.clear(screen.getByLabelText('요약값 열'))
    await user.type(screen.getByLabelText('요약값 열'), 'n값')

    expect(screen.getByLabelText('1번 줄 n값')).toBeInTheDocument()
  })

  it('미리 보기는 쓰지 않는다고 서버에 말한다', async () => {
    const user = userEvent.setup()
    show()
    await type(user, 'MD-2')
    await user.click(screen.getByRole('button', { name: '미리 보기' }))

    await waitFor(() => expect(importSummaries).toHaveBeenCalled())
    expect(importSummaries.mock.calls[0][1]).toMatchObject({ dry: true })
  })

  it('없는 시편 만들기는 기본이 꺼짐이다', async () => {
    // **오타 하나가 유령 시편을 만든다.**
    const user = userEvent.setup()
    show()
    await type(user, 'MD-2')
    await user.click(screen.getByRole('button', { name: '넣기' }))

    await waitFor(() => expect(importSummaries).toHaveBeenCalled())
    expect(importSummaries.mock.calls[0][1]).toMatchObject({
      dry: false,
      createMissing: false,
    })
  })

  it('켜면 그렇게 보낸다', async () => {
    const user = userEvent.setup()
    show()
    await user.click(screen.getByRole('checkbox'))
    await type(user, 'MD-2')
    await user.click(screen.getByRole('button', { name: '넣기' }))

    await waitFor(() => expect(importSummaries).toHaveBeenCalled())
    expect(importSummaries.mock.calls[0][1]).toMatchObject({ createMissing: true })
  })

  it('시편까지 만드는 줄을 표시한다', async () => {
    // **켜 두면 표가 시편을 늘린다** — 그 사실이 줄마다 보여야 한다.
    const user = userEvent.setup()
    show()
    await type(user, 'MD-2')
    await user.click(screen.getByRole('button', { name: '미리 보기' }))

    expect(await screen.findByText('시편도 만듦')).toBeInTheDocument()
  })

  it('빈 표로는 못 보낸다', () => {
    show()
    expect(screen.getByRole('button', { name: '넣기' })).toBeDisabled()
  })
})
