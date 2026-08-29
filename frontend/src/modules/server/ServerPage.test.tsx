/**
 * 서버 현황 — **모르는 것을 0 이라고 그리지 않는가.**
 *
 * 이 화면을 보는 이유는 하나다: **디스크가 차기 전에 아는 것.** 그래서 무는 자리를
 * 「카드가 뜬다」 가 아니라 **「곧 찬다고 말하는가」**·「없는 값을 0 으로 그리지
 * 않는가」 에 둔다. 뒤엣것이 틀리면 화면이 조용히 거짓말을 하고, 그러면 이 화면이
 * 있는 것이 없는 것보다 나쁘다.
 */

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ServerPage, { bytes, duration } from '@/modules/server/ServerPage'
import { LeftPanelProvider } from '@/shared/layout/SidePanel'

const info = vi.fn()
vi.mock('@/modules/server/api', () => ({ serverApi: { info: () => info() } }))

const GB = 1024 ** 3

function reply(over: Record<string, unknown> = {}) {
  return {
    host: {
      hostname: 'MATNEXUS-PC',
      os: 'Windows 11',
      kernel: '10.0.26200',
      arch: 'AMD64',
      uptime_seconds: 90000,
    },
    cpu: {
      model: 'AMD Ryzen 9',
      logical_cpus: 32,
      load_avg_1m: null,
      load_avg_5m: null,
      load_avg_15m: null,
    },
    memory: {
      total_bytes: 64 * GB,
      available_bytes: 40 * GB,
      used_bytes: 24 * GB,
      percent_used: 37.5,
    },
    disks: [
      {
        label: '파일 저장소',
        path: 'F:\\MatNexus\\filestore',
        total_bytes: 4000 * GB,
        used_bytes: 3900 * GB,
        free_bytes: 100 * GB,
        percent_used: 97.5,
      },
    ],
    process: { pid: 1234, rss_bytes: 70 * 1024 ** 2, python_version: '3.13.15' },
    database: { version: '17.5', size_bytes: 26 * 1024 ** 2, pool: { size: 5, checkedout: 1 } },
    app_version: 'v1.163.0',
    ...over,
  }
}

function mount() {
  render(
    <MemoryRouter initialEntries={['/server']}>
      <LeftPanelProvider>
        <ServerPage />
      </LeftPanelProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  info.mockResolvedValue(reply())
})

describe('디스크', () => {
  it('남은 양이 적으면 곧 찬다고 말한다', async () => {
    // **비율이 아니라 절대량으로 본다.** 4TB 의 97.5% 는 100GB 가 남아 아직
    // 넉넉한데, 비율로 재면 여기서 이미 붉어진다.
    info.mockResolvedValue(
      reply({
        disks: [
          {
            label: '파일 저장소',
            path: 'F:\\x',
            total_bytes: 500 * GB,
            used_bytes: 495 * GB,
            free_bytes: 5 * GB,
            percent_used: 99,
          },
        ],
      })
    )
    mount()
    expect(await screen.findByText('디스크가 곧 찹니다')).toBeInTheDocument()
  })

  it('넉넉하면 경고를 안 띄운다 — 늘 떠 있으면 아무도 안 본다', async () => {
    mount()
    // 위 픽스처는 100GB 남았다. 비율(97.5%)로 재면 여기서 잘못 울린다.
    expect(await screen.findByText(/100.0 GB 남음/)).toBeInTheDocument()
    expect(screen.queryByText('디스크가 곧 찹니다')).not.toBeInTheDocument()
  })

  it('어느 드라이브인지 경로로 말한다', async () => {
    // 「디스크가 찼다」 만으로는 무엇을 비울지 모른다.
    mount()
    expect(await screen.findByText('F:\\MatNexus\\filestore')).toBeInTheDocument()
  })
})

describe('없는 값', () => {
  it('load average 가 없으면 그 줄을 아예 안 그린다', async () => {
    // Windows 에는 없다. 0 을 그리면 「한가하다」 로 읽히고, 「—」 만 늘어놓으면
    // 무엇이 고장 난 것처럼 보인다.
    mount()
    await screen.findByText('AMD Ryzen 9')
    expect(screen.queryByText(/부하 \(1·5·15분\)/)).not.toBeInTheDocument()
  })

  it('메모리를 못 읽으면 못 읽었다고 적는다', async () => {
    info.mockResolvedValue(
      reply({
        memory: {
          total_bytes: null,
          available_bytes: null,
          used_bytes: null,
          percent_used: null,
        },
      })
    )
    mount()
    expect(await screen.findByText('읽지 못했습니다.')).toBeInTheDocument()
  })
})

describe('자리', () => {
  it('저장소 정리로 가는 탭이 함께 선다', async () => {
    mount()
    expect(await screen.findByRole('tab', { name: '저장소 정리' })).toBeInTheDocument()
  })
})

describe('단위', () => {
  it('크기를 사람이 읽는 단위로 적는다', () => {
    expect(bytes(0)).toBe('0 B')
    expect(bytes(1536)).toBe('2 KB')
    expect(bytes(1.5 * GB)).toBe('1.5 GB')
    // **모르는 것은 「—」 다.** 0 으로 적으면 「비었다」 가 된다.
    expect(bytes(null)).toBe('—')
  })

  it('켜진 지를 사람이 읽는 말로 적는다', () => {
    expect(duration(90000)).toBe('1일 1시간')
    expect(duration(3700)).toBe('1시간 1분')
    expect(duration(120)).toBe('2분')
    expect(duration(null)).toBe('—')
  })
})
