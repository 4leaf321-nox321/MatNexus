/**
 * 채널·조건을 **여러 개 한 번에** 받는 모달.
 *
 * 하나씩 「추가」 를 눌러 네 칸을 채우는 화면이었다. DMA 스윕은 채널이 아홉이고
 * 인장은 조건이 여섯이다 — 그걸 한 줄씩 만드는 동안 사람은 **같은 판단을 아홉
 * 번** 한다. 그리고 그 목록은 대개 이미 어딘가에 적혀 있다(장비 설명서·엑셀).
 *
 * 표 장치는 `shared/components/PasteGrid` 를 그대로 쓴다 — 재료 여러 개 등록이
 * 같은 문제를 이미 겪었고 그때 나온 것이다. 여기서 다시 만들지 않는다.
 *
 * ## 넣기 전에 보여 준다
 *
 * 시험 종류 정의는 **나중에 못 바꾸는 자리가 있다** — 데이터가 붙으면 키·단위·
 * 차원이 잠긴다(ADR 0015). 그래서 「몇 줄이 들어가고 어느 줄이 문제인지」 를
 * 넣기 전에 말한다.
 */

import { useState } from 'react'
import { TriangleAlert } from 'lucide-react'

import { PasteGrid } from '@/shared/components/PasteGrid'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { DIMENSIONS, DIMENSION_LABELS, VALUE_TYPES } from '@/shared/units'
import { CHANNEL_COLUMNS, CONDITION_COLUMNS, parseRows } from '@/modules/tests/typeRows'
import type { ParsedRow } from '@/modules/tests/typeRows'

export function BulkRowsDialog({
  kind,
  open,
  taken,
  onClose,
  onAdd,
}: {
  kind: 'channel' | 'condition'
  open: boolean
  /** 이미 쓰이고 있는 키. 겹치면 그 줄을 막는다. */
  taken: string[]
  onClose: () => void
  onAdd: (rows: ParsedRow[]) => void
}) {
  const columns = kind === 'channel' ? CHANNEL_COLUMNS : CONDITION_COLUMNS
  const [rows, setRows] = useState<string[][]>([columns.map(() => '')])
  const { rows: parsed, problems } = parseRows(kind, rows, taken)

  function close() {
    setRows([columns.map(() => '')])
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && close()}>
      <DialogContent className="sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>{kind === 'channel' ? '채널' : '조건'} 여러 개 넣기</DialogTitle>
          <DialogDescription>
            엑셀에서 복사해 아무 칸에나 붙여 넣으세요. 표는 사람이 보라고 있는
            것이고, 저장 단위는 <b>차원이 정합니다</b> — 고르는 칸이 아닙니다.
          </DialogDescription>
        </DialogHeader>

        <PasteGrid
          columns={[...columns]}
          rows={rows}
          onRows={setRows}
          required="key"
          header={
            <div className="text-muted-foreground space-y-1 text-xs">
              <p>
                <b>차원</b>은 영문 키와 한글 이름을 둘 다 받습니다 —{' '}
                <code>length</code> 도 <code>길이</code> 도 됩니다.
              </p>
              {kind === 'condition' && (
                <p>
                  <b>종류</b>는 {VALUE_TYPES.map((one) => one.label).join('·')} 중
                  하나입니다. 비우면 숫자이고, <b>숫자가 아니면 차원을 비웁니다.</b>
                </p>
              )}
              <p>
                <b>필수</b> 칸에 <code>Y</code> 를 적으면{' '}
                {kind === 'channel'
                  ? '그 열이 없는 파일은 등록이 실패합니다.'
                  : '안 적고는 못 올립니다.'}{' '}
                비우면 아닙니다.
              </p>
            </div>
          }
        />

        {/* **넣기 전에 말한다.** 정의는 데이터가 붙으면 잠기는 자리가 있다. */}
        {problems.length > 0 && (
          <div className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs text-amber-800 dark:text-amber-400">
            <p className="flex items-center gap-1.5 font-medium">
              <TriangleAlert className="size-3.5" />
              {problems.length}줄은 못 넣습니다 — 나머지는 넣습니다
            </p>
            {problems.map((problem) => (
              <p key={problem.line}>
                {problem.line}번 줄: {problem.said}
              </p>
            ))}
          </div>
        )}

        <details className="text-muted-foreground text-xs">
          <summary className="cursor-pointer">쓸 수 있는 차원 {DIMENSIONS.length}개</summary>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
            {DIMENSIONS.map((one) => (
              <span key={one}>
                <code>{one}</code> {DIMENSION_LABELS[one] ?? ''}
              </span>
            ))}
          </div>
        </details>

        <DialogFooter>
          <Button variant="ghost" onClick={close}>
            취소
          </Button>
          <Button
            disabled={parsed.length === 0}
            onClick={() => {
              onAdd(parsed)
              close()
            }}
          >
            {parsed.length}줄 넣기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
