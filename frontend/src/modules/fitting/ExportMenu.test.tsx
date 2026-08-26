/**
 * 내보내기 메뉴 — **덱을 실제로 어떻게 뽑는가.**
 *
 * 단위계를 고르게 만들어 놓고 이 화면은 시험이 없었다. 백엔드는 두 계로 덱을
 * 내는 것을 실측까지 했는데, **사람이 그 계를 고를 수 있는지는 아무도 안 봤다.**
 * 스모크(playwright)에도 CAE 카드 경로가 없다.
 *
 * 이 파일이 보는 것 셋:
 *
 *   1. 고른 계가 **요청과 파일 이름에** 실리는가
 *   2. 목록을 **서버에서 받는가** — 화면이 적어 두면 계가 늘 때 뒤처진다
 *   3. 낼 수 없는 형식을 **미리** 막는가
 *
 * ## 여기서 못 보는 것
 *
 * 「계를 고를 때 메뉴가 안 닫히는가」 를 여기 적었다가 지웠다. jsdom 에서는
 * **실패할 수가 없어서** — 사보타주를 걸어도 통과했다. 못 물리는 시험은 없느니만
 * 못하다: 초록을 보고 확인했다고 믿게 된다.
 *
 * 그 성질은 진짜 브라우저가 봐야 한다. `e2e/smoke.spec.ts` 로 옮겼다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ExportMenu } from '@/modules/fitting/ExportMenu'
import type { ExportFormat, PropertyCard } from '@/modules/fitting/api'

const download = vi.fn((..._args: unknown[]) => Promise.resolve())
const unitSystems = vi.fn()

vi.mock('@/modules/fitting/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/fitting/api')>()),
  fittingApi: {
    download: (...args: unknown[]) => download(...args),
    unitSystems: () => unitSystems(),
  },
}))

//: **기본이 첫 번째가 아니다.** 순서로 고르면 통과해 버려서, 그 시험이
//: `is_default` 를 실제로 보는지 알 수 없다.
const SYSTEMS = [
  {
    key: 'mm_n_tonne',
    label: 'mm · N · tonne (MPa)',
    declaration: 'tonne, mm, s, MPa',
    is_default: false,
  },
  { key: 'si', label: 'SI (kg · m · s · Pa)', declaration: 'kg, m, s, Pa', is_default: true },
]

const FORMATS = [
  {
    key: 'abaqus',
    label: 'Abaqus',
    extension: 'inp',
    describe: '*MATERIAL / *ELASTIC / *PLASTIC',
    requires: [],
  },
  {
    key: 'openradioss',
    label: 'OpenRadioss',
    extension: 'rad',
    describe: '/MAT/LAW36',
    requires: ['밀도'],
  },
] as ExportFormat[]

const CARD = {
  id: 'c1',
  label: '인장 MD (상온)',
  available_formats: ['abaqus'],
} as unknown as PropertyCard

beforeEach(() => {
  download.mockClear()
  unitSystems.mockReset()
  unitSystems.mockResolvedValue(SYSTEMS)
})

async function open() {
  render(<ExportMenu card={CARD} formats={FORMATS} onError={() => {}} />)
  await userEvent.click(screen.getByRole('button', { name: /내보내기/ }))
  return screen.findByText('덱의 단위계')
}

describe('단위계를 고른다', () => {
  it('안 고르면 서버가 기본이라 한 것으로 낸다', async () => {
    // **화면이 `si` 를 적어 두지 않는다.** 기본이 무엇인지는 서버가 안다.
    await open()
    await userEvent.click(screen.getByText('Abaqus'))
    await waitFor(() => expect(download).toHaveBeenCalled())
    const [, , , picked] = download.mock.calls[0] as unknown as unknown[]
    expect(picked).toMatchObject({ key: 'si' })
  })

  it('고른 계가 실린다', async () => {
    await open()
    await userEvent.click(screen.getByRole('button', { name: /mm · N · tonne/ }))
    await userEvent.click(screen.getByText('Abaqus'))
    await waitFor(() => expect(download).toHaveBeenCalled())
    const [, , , picked] = download.mock.calls[0] as unknown as unknown[]
    expect(picked).toMatchObject({ key: 'mm_n_tonne' })
  })

  it('덱에 적힐 줄을 그대로 보인다', async () => {
    // 받는 사람이 파일에서 읽을 글자와 같아야 나중에 대조할 수 있다.
    await open()
    expect(screen.getByText('kg, m, s, Pa')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /mm · N · tonne/ }))
    expect(screen.getByText('tonne, mm, s, MPa')).toBeInTheDocument()
  })

  it('목록을 서버에서 받는다', async () => {
    // 화면이 적어 두면 계가 늘 때 뒤처지고, 그때 사람은 그 계로 못 낸다는 것을
    // **목록에 없다는 사실로만** 안다 — 오류가 아니라 부재라서 원인을 못 찾는다.
    await open()
    expect(unitSystems).toHaveBeenCalled()
    for (const system of SYSTEMS) {
      expect(screen.getByRole('button', { name: system.label })).toBeInTheDocument()
    }
  })
})

describe('낼 수 없는 형식', () => {
  it('이유를 미리 말하고 못 누르게 한다', async () => {
    // 내려받기를 누른 뒤에 "밀도가 없습니다" 를 보는 것은 늦다.
    await open()
    expect(screen.getByText(/밀도 가 있어야 냅니다/)).toBeInTheDocument()
    await userEvent.click(screen.getByText('OpenRadioss'))
    expect(download).not.toHaveBeenCalled()
  })
})
