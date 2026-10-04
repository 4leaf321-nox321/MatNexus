/**
 * 배치 적용 창 — 고른 시험 전부에 같은 단계를. **본문은 `BatchPanel` 이다.**
 *
 * 시험 목록의 「일괄 데이터 처리」 와 처리 탭의 「이 단계 그대로 여러 건에」 가 이 창을 띄운다.
 * 워크벤치의 「시험 데이터 한번에 처리하기」 는 창 없이 같은 본문을 세운다(ADR 0058) — 무엇을
 * 왜 이렇게 하는지(보고 나서 정한다 · 나눠 보낸다 · 부분 실패를 보인다)는 그 파일에 적었다.
 */

import { Layers } from 'lucide-react'

import { BatchPanel } from '@/modules/processing/BatchPanel'
import type { BatchPanelProps } from '@/modules/processing/BatchPanel'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'

export function BatchDialog(props: BatchPanelProps & { onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(next) => !next && props.onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            <Layers className="mr-1.5 inline size-4" />
            {props.testRunIds.length}건에 같은 단계 적용
          </DialogTitle>
          <DialogDescription className="sr-only">
            처리 단계를 고르고, 미리 돌려 전/후를 견준 뒤 저장합니다.
          </DialogDescription>
        </DialogHeader>
        <BatchPanel {...props} />
      </DialogContent>
    </Dialog>
  )
}
