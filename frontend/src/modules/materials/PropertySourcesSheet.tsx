/**
 * 값 출처 — **같은 이름의 값이 여러 층에 산다.**
 *
 * 규격 두께는 재료에 있고 이름의 한 칸이지만, 계산에 들어가는 것은 시편의 실측
 * 두께다. 밀도는 재료(공칭)와 시료(실측)에 둘 다 있고 카드는 실측을 먼저 본다.
 * 푸아송비는 재료에만 있다.
 *
 * **이 배치를 사람이 외우게 하면 안 된다.** 외우게 하면 "밀도를 넣었는데
 * 내보내기가 안 된다" 가 난다 — 시료에 넣어야 할 것을 재료에 넣었거나 그 반대다.
 *
 * ## 왜 시트인가
 *
 * 전역 사이드바로 두면 가로 공간을 늘 먹는데 시험 목록·업로드·공지에서는 쓸
 * 데가 없다. 별도 탭으로 두면 카드를 만들다 말고 옮겨 가야 해서, **값이 필요한
 * 그 순간에 못 본다.** 시트는 어느 탭에서든 같은 버튼으로 열리고 닫으면 사라진다.
 */

import { AlertTriangle, CheckCircle2, MinusCircle } from 'lucide-react'

import { materialsApi } from '@/modules/materials/api'
import type { ValueSource } from '@/modules/materials/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/shared/components/ui/sheet'
import { useResource } from '@/shared/hooks/useResource'

/** 어디에 적는 값인가. **층을 말로 보여 준다** — 코드는 사람이 못 읽는다. */
const LEVEL_LABEL: Record<string, string> = {
  material: '재료',
  sample: '시료',
  specimen: '시편',
  result: '처리 결과',
}

const STATUS_ICON = {
  ok: CheckCircle2,
  missing: MinusCircle,
  conflict: AlertTriangle,
} as const

interface Props {
  materialId: string
  open: boolean
  onClose: () => void
}

export function PropertySourcesSheet({ materialId, open, onClose }: Props) {
  // 열 때마다 다시 읽는다. 다른 탭에서 값을 채우고 돌아오는 것이 정상 흐름이다.
  const sources = useResource(
    () => (open ? materialsApi.propertySources(materialId) : Promise.resolve(null)),
    [materialId, open]
  )

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>값 출처</SheetTitle>
          <SheetDescription>
            어떤 값이 어디에 적혀 있고, 무엇에 쓰이는지.
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-3 p-4 pt-0">
          <ErrorNotice error={sources.error} />
          {sources.data?.rows.map((row) => (
            <SourceRow key={row.key} row={row} />
          ))}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function SourceRow({ row }: { row: ValueSource }) {
  const Icon = STATUS_ICON[row.status as keyof typeof STATUS_ICON] ?? MinusCircle
  const tone =
    row.status === 'ok'
      ? 'text-emerald-600 dark:text-emerald-500'
      : row.status === 'conflict'
        ? 'text-amber-700 dark:text-amber-500'
        : 'text-muted-foreground'

  return (
    <div className="rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Icon className={`size-4 shrink-0 ${tone}`} />
        <span className="text-sm font-medium">{row.label}</span>
        <Badge variant="secondary" className="text-xs">
          {LEVEL_LABEL[row.level] ?? row.level}
        </Badge>
        <span className="ml-auto font-mono text-sm tabular-nums">
          {row.value === null
            ? '—'
            : `${Number(row.value.toPrecision(6))}${row.display_unit ? ` ${row.display_unit}` : ''}`}
        </span>
      </div>

      {row.origin && <p className="text-muted-foreground mt-1.5 text-xs">{row.origin}</p>}
      <p className="text-muted-foreground mt-1 text-xs">
        <b>쓰임</b> · {row.used_for}
      </p>
      {/* **없다는 사실만 알려 주고 길을 안 주면 결국 다시 헤맨다.** */}
      {row.edit_hint && (
        <p className="mt-1.5 text-xs text-amber-700 dark:text-amber-500">
          채우려면 → {row.edit_hint}
        </p>
      )}
    </div>
  )
}
