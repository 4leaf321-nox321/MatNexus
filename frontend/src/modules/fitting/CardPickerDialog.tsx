/**
 * 미리보기에 쓸 카드를 **찾아서** 고른다.
 *
 * 드롭다운은 최근 20장만 보여 준다. 그것으로 되는 때도 있지만, 덱 정의를 만드는
 * 일은 대개 **「이 정의를 설명하기 좋은 카드」** 를 찾는 일이다 — 값이 다 들어
 * 있고, 표가 있고, 그 솔버로 실제로 내보낼 재료의 카드. 최근 스무 장에 그것이
 * 있으리라는 보장이 없다.
 *
 * ## 무엇을 보여 주나
 *
 * 카드 이름은 사람이 지은 것이라 **어느 재료의 무슨 물성인지 안 들어 있다.**
 * 그래서 재료·방향·든 물성·점 수를 함께 보인다 — 고르는 기준이 그것이기 때문이다.
 *
 * **점 수를 보이는 이유**: 표를 쓰는 정의를 만들 때 점이 없는 카드를 고르면
 * 미리보기가 빈 표를 내는데, 그것이 정의 탓인지 카드 탓인지 화면에 안 나온다.
 */

import { useEffect, useState } from 'react'
import { Search } from 'lucide-react'

import { fittingApi } from '@/modules/fitting/api'
import type { BlockSpec, PropertyCard } from '@/modules/fitting/api'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onPick: (card: PropertyCard) => void
  specs: BlockSpec[]
  /** 지금 고른 카드. 표에서 어느 줄인지 보인다. */
  current?: string
}

export function CardPickerDialog({ open, onOpenChange, onPick, specs, current }: Props) {
  const [text, setText] = useState('')
  const [rows, setRows] = useState<PropertyCard[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)

  // **적는 대로 찾는다.** 다만 글자마다 부르지는 않는다 — 목록 조회라 비싸다.
  useEffect(() => {
    if (!open) return
    let alive = true
    setLoading(true)
    const timer = setTimeout(() => {
      void fittingApi
        .cards({ q: text || undefined, limit: 50 })
        .then((page) => {
          if (!alive) return
          setRows(page.items)
          setTotal(page.total)
        })
        .finally(() => {
          if (alive) setLoading(false)
        })
    }, 250)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [text, open])

  const kinds = (card: PropertyCard) =>
    Object.keys(card.blocks ?? {}).map(
      (key) => specs.find((spec) => spec.key === key)?.label ?? key
    )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>미리보기에 쓸 카드 고르기</DialogTitle>
          <DialogDescription>
            정의가 쓰는 값이 든 카드를 고르면 오른쪽 덱이 제대로 그려집니다. 재료
            이름이나 카드 이름으로 찾을 수 있습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="relative">
          <Search className="text-muted-foreground absolute top-2.5 left-2.5 size-4" />
          <Input
            className="pl-8"
            value={text}
            autoFocus
            onChange={(event) => setText(event.target.value)}
            placeholder="재료 이름 · 카드 이름"
            aria-label="카드 찾기"
          />
        </div>

        <div className="max-h-[50vh] overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>재료</TableHead>
                <TableHead>물성</TableHead>
                <TableHead className="text-right">점</TableHead>
                <TableHead className="w-20" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((card) => (
                <TableRow key={card.id} data-current={card.id === current || undefined}>
                  <TableCell>
                    <span className="font-medium">{card.material_name}</span>
                    {card.orientation ? (
                      <span className="text-muted-foreground"> · {card.orientation}</span>
                    ) : null}
                    <div className="text-muted-foreground text-xs">{card.label}</div>
                  </TableCell>
                  <TableCell>
                    <span className="flex flex-wrap gap-1">
                      {kinds(card).length === 0 ? (
                        <span className="text-muted-foreground text-xs">값 없음</span>
                      ) : (
                        kinds(card).map((name) => (
                          <Badge key={name} variant="secondary">
                            {name}
                          </Badge>
                        ))
                      )}
                    </span>
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {/* **점이 없으면 표를 쓰는 정의를 못 그려 본다.** 그때 미리보기가
                        빈 표를 내는데, 정의 탓인지 카드 탓인지 화면에 안 나온다. */}
                    {card.point_count || '—'}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      variant={card.id === current ? 'secondary' : 'outline'}
                      onClick={() => {
                        onPick(card)
                        onOpenChange(false)
                      }}
                    >
                      {card.id === current ? '고른 것' : '고르기'}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {rows.length === 0 && !loading ? (
            <p className="text-muted-foreground p-6 text-center text-sm">
              {text
                ? `'${text}' 로 찾은 카드가 없습니다.`
                : '아직 물성 카드가 없습니다. 카드를 하나 만들면 여기서 덱을 그려 볼 수 있습니다.'}
            </p>
          ) : null}
        </div>

        {/* **몇 장 중 몇 장인지 말한다.** 50장만 받아 오므로, 그 말이 없으면 찾던
            카드가 없을 때 「없다」 인지 「안 왔다」 인지 알 수 없다. */}
        {total > rows.length ? (
          <p className="text-muted-foreground text-xs">
            {total}장 중 {rows.length}장을 보이고 있습니다 — 더 좁혀서 찾아 주세요.
          </p>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
