/**
 * 물성 정의 목록 — **파일로 주고받는 자리.**
 *
 * 개발 서버에서 만들어 운영으로 옮기는 길이라, 무는 데를 고를 때 「파일이 받아
 * 진다」 보다 **「겹치는 key 를 말없이 덮지 않는다」** 를 우선한다. 덮인 정의로
 * 다음에 뽑는 덱이 달라지는데, 파일은 사람 컴퓨터에 있고 서버에는 흔적이 없다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ExportProfilesPage from '@/modules/fitting/ExportProfilesPage'
import { makeFile, toFileEntry } from '@/modules/fitting/profileFile'

const exportProfiles = vi.fn()
const createExportProfile = vi.fn()
const saveExportProfile = vi.fn()

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: {
    exportProfiles: () => exportProfiles(),
    createExportProfile: (...args: unknown[]) => createExportProfile(...args),
    saveExportProfile: (...args: unknown[]) => saveExportProfile(...args),
    removeExportProfile: vi.fn(),
  },
}))

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_system_admin: true, memberships: [] } }),
}))

const LSDYNA = {
  id: 'p1',
  key: 'lsdyna',
  label: 'LS-DYNA',
  description: null,
  owner_workspace_slug: 'metal',
  owner_workspace_name: '금속재료팀',
  is_global: false,
  is_active: true,
  created_at: '2026-08-30T00:00:00Z',
  updated_at: '2026-08-30T00:00:00Z',
  definition: { extension: 'k', lines: [{ text: '*KEYWORD' }] },
}

/** 파일 고르기를 흉내 낸다 — 숨은 input 에 직접 올린다. */
async function drop(json: unknown) {
  const file = new File([JSON.stringify(json)], 'x.json', { type: 'application/json' })
  await userEvent.upload(screen.getByLabelText('물성 정의 파일'), file)
}

function show() {
  render(
    <MemoryRouter>
      <ExportProfilesPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  exportProfiles.mockReset()
  createExportProfile.mockReset()
  saveExportProfile.mockReset()
  exportProfiles.mockResolvedValue([LSDYNA])
  createExportProfile.mockResolvedValue(LSDYNA)
  saveExportProfile.mockResolvedValue(LSDYNA)
})

describe('불러오기', () => {
  it('겹치는 key 는 기본이 건너뛰기다', async () => {
    /**
     * **제일 위험한 자리다.** 말없이 덮으면 운영의 정의가 개발 것으로 바뀌고,
     * 그 뒤로 뽑는 덱이 달라진다 — 되돌릴 근거가 서버 어디에도 없다.
     */
    show()
    await screen.findByText('LS-DYNA')

    await drop(makeFile([toFileEntry(LSDYNA)], 'dev'))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('이미 있음')

    // 덮기를 안 켰으니 넣을 것이 없다.
    expect(screen.getByRole('button', { name: '넣을 것이 없습니다' })).toBeDisabled()
    expect(saveExportProfile).not.toHaveBeenCalled()
  })

  it('섞여 있으면 새것만 들어간다', async () => {
    /**
     * **여기가 「기본은 건너뛰기」 를 실제로 무는 자리다.** 앞 시험은 넣기 단추가
     * 잠겨 있어 넣는 길이 안 돌았다 — 사보타주로 확인했다(2026-08-31): 건너뛰기를
     * 통째로 없애도 앞 시험만으로는 안 물렸다.
     */
    show()
    await screen.findByText('LS-DYNA')

    await drop(
      makeFile(
        [
          toFileEntry(LSDYNA), // 이미 있다 — 덮기를 안 켠다
          toFileEntry({ ...LSDYNA, key: 'optistruct' }), // 새것
        ],
        'dev'
      )
    )
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: '1건 넣기' }))

    await waitFor(() => expect(createExportProfile).toHaveBeenCalledTimes(1))
    expect(
      (createExportProfile.mock.calls[0][0] as { key: string }).key
    ).toBe('optistruct')
    expect(saveExportProfile).not.toHaveBeenCalled()
  })

  it('덮기를 켜야 덮는다', async () => {
    show()
    await screen.findByText('LS-DYNA')

    await drop(makeFile([toFileEntry({ ...LSDYNA, label: '고친 이름' })], 'dev'))
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('checkbox', { name: 'lsdyna 덮어쓰기' }))
    await userEvent.click(screen.getByRole('button', { name: '1건 넣기' }))

    await waitFor(() =>
      expect(saveExportProfile).toHaveBeenCalledWith(
        'lsdyna',
        expect.objectContaining({ label: '고친 이름' })
      )
    )
    expect(createExportProfile).not.toHaveBeenCalled()
  })

  it('새 key 는 만든다 — 부서를 안 실어 보낸다', async () => {
    /** 소유를 실으면 운영에서 **남의 부서 것**으로 들어간다. */
    show()
    await screen.findByText('LS-DYNA')

    await drop(makeFile([toFileEntry({ ...LSDYNA, key: 'optistruct' })], 'dev'))
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: '1건 넣기' }))

    await waitFor(() => expect(createExportProfile).toHaveBeenCalled())
    const sent = createExportProfile.mock.calls[0][0] as Record<string, unknown>
    expect(sent.key).toBe('optistruct')
    expect(sent).not.toHaveProperty('owner_workspace_slug')
    expect(sent).not.toHaveProperty('is_global')
  })

  it('망가진 파일은 왜인지 말하고 창을 안 연다', async () => {
    show()
    await screen.findByText('LS-DYNA')

    await drop({ hello: 'world' })

    expect(await screen.findByText(/내보낸 물성 정의 파일이 아닙니다/)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('하나가 막혀도 나머지는 들어간다', async () => {
    // 열 개 중 하나가 코드 렌더러와 이름이 겹쳤다고 아홉을 다시 고르게 하지 않는다.
    createExportProfile
      .mockRejectedValueOnce(new Error("'abaqus' 는 코드로 만든 솔버 형식입니다."))
      .mockResolvedValueOnce(LSDYNA)
    show()
    await screen.findByText('LS-DYNA')

    await drop(
      makeFile(
        [
          toFileEntry({ ...LSDYNA, key: 'abaqus' }),
          toFileEntry({ ...LSDYNA, key: 'optistruct' }),
        ],
        'dev'
      )
    )
    await screen.findByRole('dialog')
    await userEvent.click(screen.getByRole('button', { name: '2건 넣기' }))

    expect(await screen.findByText(/1건이 안 들어갔습니다/)).toBeInTheDocument()
    expect(screen.getByText(/abaqus — /)).toBeInTheDocument()
    expect(createExportProfile).toHaveBeenCalledTimes(2)
  })
})

describe('내보내기', () => {
  it('정의가 없으면 잠근다', async () => {
    exportProfiles.mockResolvedValue([])
    show()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: '전부 내보내기' })).toBeDisabled()
    )
  })
})
