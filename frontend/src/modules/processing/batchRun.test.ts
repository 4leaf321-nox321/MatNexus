/**
 * 배치를 나눠 보내고 전후를 견준다 — **무는 것은 다섯.**
 *
 *     나눠 보낸다              1000건짜리 요청 하나는 프록시가 끊는다
 *     진행을 건수로 센다        조각 수로 세면 사람이 못 읽는다
 *     끊기면 여기까지를 들려준다  삼키면 절반 저장된 것을 모른 채 넘어간다
 *     전후를 키로 맞춘다        자리로 맞추면 엉뚱한 값끼리 견준다
 *     0 으로 안 나눈다          전이 0 이면 비율이 없다
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CHUNK, changesOf, runInChunks, shifted, undoInChunks } from '@/modules/processing/batchRun'
import type { BatchItem } from '@/modules/processing/api'

const batch = vi.fn()
const undoBatch = vi.fn()

vi.mock('@/modules/processing/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/modules/processing/api')>()),
  processingApi: {
    batch: (...args: unknown[]) => batch(...args),
    undoBatch: (...args: unknown[]) => undoBatch(...args),
  },
}))

const ASK = { steps: [{ plugin: 'tensile.strength', options: {} }], adopt: true, dryRun: false }

function reply(ids: string[]) {
  return {
    requested: ids.length,
    succeeded: ids.length,
    failed: 0,
    dry_run: false,
    items: ids.map((id) => ({
      test_run_id: id,
      record_name: id,
      status: 'ok',
      result_id: `r-${id}`,
      adopted: true,
      error: null,
      scalars: [],
      previous: [],
      previous_adopted_id: null,
    })),
  }
}

function scalar(key: string, value: number) {
  return { key, label: key, value, si_unit: 'Pa', dimension: 'stress' }
}

beforeEach(() => vi.clearAllMocks())

describe('나눠 전송', () => {
  it('조각으로 잘라 보낸다', async () => {
    batch.mockImplementation((body: { test_run_ids: string[] }) =>
      Promise.resolve(reply(body.test_run_ids))
    )
    const ids = Array.from({ length: CHUNK + 3 }, (_, at) => `t${at}`)

    const got = await runInChunks({ ...ASK, testRunIds: ids })

    expect(batch).toHaveBeenCalledTimes(2)
    expect(batch.mock.calls[0][0].test_run_ids).toHaveLength(CHUNK)
    expect(batch.mock.calls[1][0].test_run_ids).toHaveLength(3)
    // 합쳐서 하나로 온다 — 부르는 쪽이 조각을 알 이유가 없다.
    expect(got.items).toHaveLength(CHUNK + 3)
    expect(got.requested).toBe(CHUNK + 3)
  })

  it('진행을 건수로 센다', async () => {
    batch.mockImplementation((body: { test_run_ids: string[] }) =>
      Promise.resolve(reply(body.test_run_ids))
    )
    const ids = Array.from({ length: CHUNK + 1 }, (_, at) => `t${at}`)
    const seen: [number, number][] = []

    await runInChunks({ ...ASK, testRunIds: ids }, (done, total) => seen.push([done, total]))

    expect(seen[0]).toEqual([0, CHUNK + 1])
    expect(seen.at(-1)).toEqual([CHUNK + 1, CHUNK + 1])
  })

  it('끊기면 여기까지 된 것을 들려 던진다', async () => {
    // **삼키면 안 된다.** 앞 조각은 이미 저장됐는데 「실패했다」 로만 말하면,
    // 사람은 다시 걸어 같은 것을 두 벌 만든다.
    batch
      .mockImplementationOnce((body: { test_run_ids: string[] }) =>
        Promise.resolve(reply(body.test_run_ids))
      )
      .mockRejectedValueOnce(new Error('끊겼습니다'))
    const ids = Array.from({ length: CHUNK + 2 }, (_, at) => `t${at}`)

    await expect(runInChunks({ ...ASK, testRunIds: ids })).rejects.toMatchObject({
      partial: { succeeded: CHUNK },
    })
  })

  it('되돌리기도 나눠 보낸다', async () => {
    undoBatch.mockImplementation((items: { result_id: string }[]) =>
      Promise.resolve({
        requested: items.length,
        undone: items.length,
        failed: 0,
        items: items.map((one) => ({
          result_id: one.result_id,
          status: 'ok',
          restored: true,
          error: null,
        })),
      })
    )
    const rows = Array.from({ length: CHUNK + 1 }, (_, at) => ({ result_id: `r${at}` }))

    const got = await undoInChunks(rows)

    expect(undoBatch).toHaveBeenCalledTimes(2)
    expect(got.undone).toBe(CHUNK + 1)
  })
})

describe('전후 비교', () => {
  const item = (previous: ReturnType<typeof scalar>[], scalars: ReturnType<typeof scalar>[]) =>
    ({
      test_run_id: 't1',
      record_name: 'T-1',
      status: 'ok',
      result_id: 'r1',
      adopted: false,
      error: null,
      scalars,
      previous,
      previous_adopted_id: null,
    }) as unknown as BatchItem

  it('키로 맞춘다', () => {
    // 자리로 맞추면 단계가 하나 늘었을 때 엉뚱한 값끼리 견주게 된다.
    const rows = changesOf(
      item(
        [scalar('proof_stress', 300), scalar('youngs_modulus', 200e9)],
        [scalar('youngs_modulus', 205e9), scalar('proof_stress', 310)]
      )
    )
    const modulus = rows.find((one) => one.key === 'youngs_modulus')
    expect(modulus?.before).toBe(200e9)
    expect(modulus?.after).toBe(205e9)
    expect(modulus?.ratio).toBeCloseTo(0.025)
  })

  it('먼저 볼 값이 앞에 온다', () => {
    const rows = changesOf(
      item([], [scalar('elastic_r_squared', 0.99), scalar('youngs_modulus', 200e9)])
    )
    expect(rows[0].key).toBe('youngs_modulus')
  })

  it('없던 값이 생긴 것도 변화다', () => {
    const rows = changesOf(item([], [scalar('youngs_modulus', 200e9)]))
    expect(rows[0].before).toBeNull()
    expect(rows[0].ratio).toBeNull()
    expect(shifted(item([], [scalar('youngs_modulus', 200e9)]))).toBe(true)
  })

  it('0 으로 나누지 않는다', () => {
    const rows = changesOf(item([scalar('a', 0)], [scalar('a', 5)]))
    expect(rows[0].ratio).toBeNull()
  })

  it('거의 같으면 눈에 띄는 변화가 아니다', () => {
    // 다시 걸 이유가 없는 건을 표 위로 올리면, 정작 봐야 할 건이 묻힌다.
    const same = item([scalar('youngs_modulus', 200e9)], [scalar('youngs_modulus', 200.1e9)])
    expect(shifted(same)).toBe(false)
  })
})
