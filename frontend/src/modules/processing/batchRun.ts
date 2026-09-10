/**
 * 배치를 **나눠 보낸다** — 진행을 보이고, 끊겨도 어디까지 됐는지 남긴다.
 *
 * ## 왜 한 번에 안 보내나
 *
 * 서버는 한 요청에 1000건까지 받는다(건당 30ms → 30초). 그런데 **30초짜리 HTTP
 * 요청은 프록시·브라우저가 끊는 자리**이고, 끊기면 사람은 어디까지 됐는지 알
 * 방법이 없다 — 서버는 건별로 커밋하므로 데이터는 남는데 응답을 못 받는다
 * (`MAX_BATCH` 주석이 그 위험을 이미 적어 뒀다).
 *
 * 잘라 보내면 세 가지가 함께 풀린다.
 *
 *     진행을 보인다        「12/40건」 — 30초 동안 스피너만 도는 것과 다르다
 *     끊겨도 남는다        앞의 묶음은 이미 끝났고 결과도 이미 손에 있다
 *     상한을 안 넘는다      1000건 규칙에 사람이 걸릴 일이 없다
 *
 * ## 조각 크기
 *
 * 25건. 건당 30ms 이므로 한 조각이 1초 안쪽이고, 진행이 1초마다 움직인다.
 * 더 잘게 쪼개면 왕복 고정비(요청 하나에 수십 ms)가 계산 시간을 넘어선다.
 */

import { processingApi } from '@/modules/processing/api'
import type { BatchItem, BatchOut, BatchUndoOut, RecipeStep } from '@/modules/processing/api'

/** 한 번에 보내는 건수. 위 주석의 근거로 정한 값이다. */
export const CHUNK = 25

export interface BatchAsk {
  testRunIds: string[]
  steps: RecipeStep[]
  recipeKey?: string | null
  adopt: boolean
  dryRun: boolean
}

/** 진행. `done`/`total` 은 **건수**다 — 조각 수로 세면 사람이 못 읽는다. */
export type OnProgress = (done: number, total: number) => void

/**
 * 조각으로 나눠 돌리고 **하나로 합친 결과**를 돌려준다.
 *
 * 조각 하나가 통째로 실패하면(네트워크·서버 오류) 거기서 멈추고 **그때까지의
 * 결과를 담아 던진다** — 삼키면 사람은 절반만 처리된 것을 모른 채 다음으로
 * 넘어간다.
 */
export async function runInChunks(ask: BatchAsk, onProgress?: OnProgress): Promise<BatchOut> {
  const items: BatchItem[] = []
  const total = ask.testRunIds.length
  onProgress?.(0, total)

  for (let at = 0; at < total; at += CHUNK) {
    const slice = ask.testRunIds.slice(at, at + CHUNK)
    try {
      const got = await processingApi.batch({
        test_run_ids: slice,
        steps: ask.steps,
        recipe_key: ask.recipeKey ?? null,
        adopt: ask.adopt,
        dry_run: ask.dryRun,
      })
      items.push(...got.items)
    } catch (caught) {
      const error = caught instanceof Error ? caught : new Error('돌리지 못했습니다.')
      // **여기까지 된 것을 붙여 던진다.** 부르는 쪽이 그것을 보여 줘야
      // 「절반은 이미 저장됐다」 를 사람이 안다.
      throw Object.assign(error, { partial: merge(items, total, ask.dryRun) })
    }
    onProgress?.(Math.min(at + CHUNK, total), total)
  }
  return merge(items, total, ask.dryRun)
}

function merge(items: BatchItem[], requested: number, dryRun: boolean): BatchOut {
  const succeeded = items.filter((one) => one.status === 'ok').length
  return {
    requested,
    succeeded,
    failed: items.length - succeeded,
    dry_run: dryRun,
    items,
  }
}

/** 되돌리기도 나눠 보낸다 — 스무 건을 지우는 것도 한 요청일 이유가 없다. */
export async function undoInChunks(
  items: { result_id: string; restore_adopted_id?: string | null }[],
  onProgress?: OnProgress
): Promise<BatchUndoOut> {
  const rows: BatchUndoOut['items'] = []
  const total = items.length
  onProgress?.(0, total)
  for (let at = 0; at < total; at += CHUNK) {
    const got = await processingApi.undoBatch(items.slice(at, at + CHUNK))
    rows.push(...got.items)
    onProgress?.(Math.min(at + CHUNK, total), total)
  }
  const undone = rows.filter((one) => one.status === 'ok' || one.status === 'missing').length
  return { requested: total, undone, failed: rows.length - undone, items: rows }
}

/** 전후를 견줄 항목. **둘 중 하나만 있어도 줄은 선다** — 없어진 것도 변화다. */
export interface Change {
  key: string
  label: string
  unit: string
  dimension: string | null
  before: number | null
  after: number | null
  /** 상대 변화. 전이 없거나 0 이면 `null` — 0 으로 나눈 수를 보여 주지 않는다. */
  ratio: number | null
}

/** 사람이 먼저 보는 값. 앞의 것이 표의 앞에 온다. */
const HEADLINE = ['youngs_modulus', 'proof_stress', 'tensile_strength']

/**
 * 전/후를 항목별로 맞춘다.
 *
 * **키로 맞춘다.** 자리로 맞추면 단계가 하나 늘거나 줄었을 때 엉뚱한 값끼리
 * 견주게 되고, 그 표는 그럴듯해 보인다.
 */
export function changesOf(item: BatchItem): Change[] {
  const before = new Map(item.previous.map((one) => [one.key, one]))
  const after = new Map(item.scalars.map((one) => [one.key, one]))
  const keys = [...new Set([...before.keys(), ...after.keys()])]
  const rows = keys.map((key) => {
    const left = before.get(key)
    const right = after.get(key)
    const one = right ?? left
    const from = left?.value ?? null
    const to = right?.value ?? null
    return {
      key,
      label: one?.label ?? key,
      unit: one?.si_unit ?? '1',
      dimension: one?.dimension ?? null,
      before: from,
      after: to,
      ratio: from !== null && to !== null && from !== 0 ? (to - from) / Math.abs(from) : null,
    }
  })
  return rows.sort((a, b) => rank(a.key) - rank(b.key) || a.key.localeCompare(b.key))
}

function rank(key: string): number {
  const at = HEADLINE.indexOf(key)
  return at < 0 ? HEADLINE.length : at
}

/** 이 건이 **눈에 띄게 달라지나.** 표에서 먼저 보여 줄 줄을 고르는 데 쓴다. */
export function shifted(item: BatchItem, threshold = 0.01): boolean {
  return changesOf(item).some(
    (one) =>
      (one.before === null) !== (one.after === null) ||
      (one.ratio !== null && Math.abs(one.ratio) >= threshold)
  )
}
