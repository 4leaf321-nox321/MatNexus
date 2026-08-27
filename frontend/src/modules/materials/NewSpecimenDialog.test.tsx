/**
 * 시편 추가 — **여기서 묻는 것은 규격이지 치수가 아니다.**
 *
 * 실사용에서 나왔다 — *"시편 추가에 왜 실측 추가가 나오지? 시편의 값은 규격의
 * 값으로 하고, 시험에다 두께·폭 같은 걸 넣기로 한 거 아니었어?"*.
 *
 * 맞다. 치수를 읽는 순서가 셋이다(v1.118.0):
 *
 *     ① 이 시험이 잰 값     장비 파일의 `a0`·`b0` — 파싱이 담는다
 *     ② 시편에 적힌 값
 *     ③ 규격이 정한 공칭
 *
 * 그러니 시편을 만들 때 할 일은 **규격을 고르는 것**이고, 치수는 대개 적을 일이
 * 없다. 앞에 내놓으면 사람은 적어야 하는 줄 알고, 그때 적은 값이 규격 공칭과
 * 어긋나면 어느 것이 맞는지 알 수 없게 된다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { NewSpecimenDialog } from '@/modules/materials/NewSpecimenDialog'

const createSpecimen = vi.fn()

vi.mock('@/modules/materials/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/modules/materials/api')>()
  return {
    ...original,
    materialsApi: { createSpecimen: (...args: unknown[]) => createSpecimen(...args) },
  }
})

/** 규격 피커는 서버에 묻는다. 여기서 보는 것은 그게 아니라 **폼의 모양**이다. */
vi.mock('@/modules/vocabulary/VocabularyField', () => ({
  VocabularyField: ({ label }: { label: string }) => <div>{label}</div>,
}))

const onDone = vi.fn()

function open() {
  return render(
    <NewSpecimenDialog sampleId="s1" open onClose={() => {}} onDone={onDone} />
  )
}

beforeEach(() => {
  createSpecimen.mockReset()
  createSpecimen.mockResolvedValue({ id: 'p1', orientation: 'MD', seq_no: 1 })
  onDone.mockReset()
})

describe('시편 추가', () => {
  it('규격을 앞에 묻는다', async () => {
    open()
    expect(await screen.findByText('시편 규격')).toBeInTheDocument()
  })

  it('치수는 접어 두고, 왜 여는지 적는다', async () => {
    // **앞에 내놓지 않는다.** 사람은 보이는 칸을 채워야 하는 줄 안다.
    open()
    expect(await screen.findByText(/규격과 다르면 적으세요/)).toBeInTheDocument()
    // 접힌 안쪽에 무엇이 있는지는 열어야 보인다 — `<details>` 는 jsdom 에서도
    // 안쪽이 DOM 에 있으므로, 여기서 보는 것은 **접혔다는 사실**이다.
    const box = screen.getByText(/규격과 다르면 적으세요/).closest('details')
    expect(box).not.toBeNull()
    expect(box).not.toHaveAttribute('open')
  })

  it('「실측」 이라고 부르지 않는다', async () => {
    // 실측은 **시험이 잰 값**이다. 시편 칸을 그렇게 부르면 둘이 뒤섞인다.
    open()
    await screen.findByText('시편 규격')
    expect(screen.queryByText(/실측/)).not.toBeInTheDocument()
  })

  it('비워 둔 채로 만들 수 있다', async () => {
    // **보통은 비운다.** 규격이 값을 갖고 있고, 시험은 자기 파일 값을 쓴다.
    const user = userEvent.setup()
    open()
    await screen.findByText('시편 규격')
    await user.click(screen.getByRole('button', { name: '추가' }))

    await waitFor(() => expect(createSpecimen).toHaveBeenCalled())
    const body = createSpecimen.mock.calls[0][1] as Record<string, unknown>
    expect(body.thickness ?? null).toBeNull()
    expect(body.width ?? null).toBeNull()
    expect(onDone).toHaveBeenCalled()
  })
})
