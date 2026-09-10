/**
 * 「이 단계 그대로 여러 건에」 — **한 건으로 맞춘 뒤가 진짜 일이다.**
 *
 * ## 왜 여기서 시작하나 (2026-09-11 요청)
 *
 * 배치는 진작 있었지만 **저장된 레시피만** 걸 수 있었고, 레시피 저장은 부서
 * 관리자만 할 수 있었다. 그래서 관리자가 아닌 사람은 배치를 아예 못 썼고,
 * 실측(개발 DB)으로 채택된 결과 52건 중 **49건이 「레시피 없이」** 나왔다 —
 * 사람들은 레시피를 안 만든다. 그런데 그 49건은 전부 한 건씩 손으로 돌린
 * 것이다.
 *
 * 맞춘 단계에 **이름을 붙이지 않고** 그대로 나머지에 건다. 서버는 진작
 * `steps` 만으로 받고 있었다 — 막고 있던 것은 화면이었다.
 *
 * ## 대상은 「형제」 다
 *
 * 같은 재료·같은 시험법의 다른 시험. 시편 20~30장을 한 재료로 자르고 같은
 * 시험을 돌리는 것이 실무이므로, 그 묶음이 곧 배치의 단위다.
 *
 * **이미 채택된 것을 기본으로 안 고른다.** 이미 값이 정해진 시험을 덮는 것은
 * 사람이 뜻을 갖고 하는 일이지 기본값이 아니다 — 다시 걸어야 하는 상황(단계를
 * 고쳤다)도 흔하므로 고를 수는 있게 두고, 「채택됨」 을 줄에 적는다.
 */

import { useMemo, useState } from 'react'
import { Layers } from 'lucide-react'

import { BatchDialog } from '@/modules/processing/BatchDialog'
import { testsApi } from '@/modules/tests/api'
import type { RecipeStep } from '@/modules/processing/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { useResource } from '@/shared/hooks/useResource'
import { useRowSelection } from '@/shared/hooks/useRowSelection'

interface Props {
  /** 지금 보고 있는 시험. **대상에서 뺀다** — 여기는 이미 돌린 자리다. */
  testRunId: string
  testTypeKey: string
  materialId: string | null
  /** 지금 화면에 맞춰 둔 단계. */
  steps: RecipeStep[]
  onClose: () => void
  onDone: () => void
}

export function BatchFromSteps({
  testRunId,
  testTypeKey,
  materialId,
  steps,
  onClose,
  onDone,
}: Props) {
  const siblings = useResource(
    () =>
      materialId
        ? testsApi.runs({
            material_id: materialId,
            test_type_key: testTypeKey,
            status: 'parsed',
            limit: 200,
          })
        : Promise.resolve({ items: [], total: 0, limit: 0, offset: 0 }),
    [materialId, testTypeKey]
  )
  const rows = useMemo(
    () => (siblings.data?.items ?? []).filter((one) => one.id !== testRunId),
    [siblings.data, testRunId]
  )
  const selection = useRowSelection(rows.map((one) => one.id))
  const [ready, setReady] = useState(false)

  // **아직 채택 안 한 것을 기본으로 고른다.** 이미 값이 정해진 시험을 덮는 것은
  // 뜻을 갖고 하는 일이라 사람이 직접 켜게 둔다.
  const fresh = useMemo(() => rows.filter((one) => !one.adopted_result_id), [rows])
  const [primed, setPrimed] = useState(false)
  if (!primed && rows.length > 0) {
    selection.replace(fresh.map((one) => one.id))
    setPrimed(true)
  }

  const picked = [...selection.picked]

  if (ready) {
    return (
      <BatchDialog
        testRunIds={picked}
        testTypeKey={testTypeKey}
        steps={steps}
        stepsLabel="이 시험에서 맞춘 단계"
        onClose={onClose}
        onDone={onDone}
      />
    )
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            <Layers className="mr-1.5 inline size-4" />이 단계 그대로 여러 건에
          </DialogTitle>
          <DialogDescription>
            같은 재료·같은 시험법의 다른 시험입니다. 고른 것에 <b>지금 맞춰 둔 단계</b>를
            그대로 겁니다 — 레시피로 저장하지 않아도 됩니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={siblings.error} />

        {!materialId ? (
          <p className="text-muted-foreground rounded-md border p-3 text-sm">
            이 시험이 어느 재료의 것인지 알 수 없어 형제를 찾지 못했습니다. 시험 목록에서
            여러 건을 골라 <b>일괄 데이터 처리</b>로 거세요.
          </p>
        ) : rows.length === 0 ? (
          <p className="text-muted-foreground rounded-md border p-3 text-sm">
            {siblings.loading ? '찾는 중…' : '같은 재료·같은 시험법의 다른 시험이 없습니다.'}
          </p>
        ) : (
          <>
            <div className="flex items-center gap-2 text-sm">
              <span>
                <b>{picked.length}건</b> 골랐습니다 (전체 {rows.length})
              </span>
              <Button
                size="sm"
                variant="ghost"
                className="ml-auto"
                onClick={() => selection.setAll(true)}
              >
                전부
              </Button>
              <Button size="sm" variant="ghost" onClick={() => selection.clear()}>
                해제
              </Button>
            </div>

            <div className="max-h-72 space-y-1 overflow-y-auto">
              {rows.map((one) => (
                <label
                  key={one.id}
                  className="hover:bg-muted/50 flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-xs"
                >
                  <input
                    type="checkbox"
                    checked={selection.picked.has(one.id)}
                    onClick={(event) => selection.toggle(one.id, event)}
                    onChange={() => {}}
                  />
                  <span className="font-mono">{one.record_name}</span>
                  {one.adopted_result_id && (
                    <Badge variant="outline" className="text-xs">
                      채택됨
                    </Badge>
                  )}
                  <span className="text-muted-foreground ml-auto tabular-nums">
                    결과 {one.result_count}
                  </span>
                </label>
              ))}
            </div>
          </>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button onClick={() => setReady(true)} disabled={picked.length === 0}>
            {picked.length}건으로 넘어가기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
