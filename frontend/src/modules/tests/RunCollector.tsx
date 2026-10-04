/**
 * 시험 골라 담기 — **목록에서 바로 골라 담는다**(ADR 0058).
 *
 * 카드에 쓸 시험을 고르는 `fitting/RunPicker` 와는 다른 일이다 — 그것은 이미 채택된 시험 중
 * 무엇을 뺄지, 이것은 업무에 무엇을 담을지다.
 *
 * 워크벤치 업무의 첫 단계가 「시험을 담는다」 인데, 전에는 시험 목록 화면으로 갔다가 고르고
 * 담기 창을 거쳐 돌아와야 했다. 오가는 사이 거르기가 풀리고, 돌아와서는 무엇을 담았는지
 * 다시 세어야 했다. 여기서는 그 자리에서 거르고 고른다 — 담긴 것은 바구니(서버)에 남는다.
 *
 * **처음 거르기는 업무가 정한다**(처리 상태). 「한번에 처리하기」 는 아직 처리 안 한 것을,
 * 「한번에 채택하기」 는 결과는 있는데 채택 안 한 것을 먼저 세운다. 사람이 바꿀 수 있다.
 *
 * 한 쪽은 100건이다. 넘으면 몇 건 중 몇 건인지 말한다 — 잘렸다는 사실을 숨기면 없는 시험처럼
 * 보인다(재료 고르기와 같은 판단).
 */

import { useEffect, useState } from 'react'
import { Plus, Search } from 'lucide-react'

import type { Material } from '@/modules/materials/api'
import { MaterialPicker } from '@/modules/materials/MaterialPicker'
import { RUN_STATUS_LABEL, testsApi } from '@/modules/tests/api'
import type { TestRun } from '@/modules/tests/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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
import { useResource } from '@/shared/hooks/useResource'

/** 한 쪽에 보이는 수. 나머지는 거르기로. */
export const PICK_PAGE = 100

export type ProcessingState = 'none' | 'results' | 'adopted'

const PROCESSING_LABEL: Record<ProcessingState, string> = {
  none: '처리 전',
  results: '결과 있음 · 채택 전',
  adopted: '채택됨',
}

const SELECT = 'border-input bg-background h-8 rounded-md border px-2 text-sm'

interface Props {
  /** 처음 거르기 — 처리 상태. 비우면 전부. */
  processing?: ProcessingState
  /** 이미 담은 것 — 「담김」 으로 표시하고 다시 고르지 않는다. */
  taken: string[]
  /** 담을 수 없을 때(남의 부서 작업을 읽기로 연 때). */
  disabled?: boolean
  onPick: (ids: string[]) => Promise<void>
}

export function RunCollector({ processing, taken, disabled = false, onPick }: Props) {
  const [state, setState] = useState<ProcessingState | ''>(processing ?? '')
  const [type, setType] = useState('')
  const [material, setMaterial] = useState<Material | null>(null)
  const [typed, setTyped] = useState('')
  const [query, setQuery] = useState('')
  const [chosen, setChosen] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // 타이핑이 멎으면 찾는다 — 글자마다 부르면 목록이 깜빡인다.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(typed.trim()), 300)
    return () => clearTimeout(timer)
  }, [typed])

  const types = useResource(() => testsApi.types(), [])
  const page = useResource(
    () =>
      testsApi.runs({
        processing: state || undefined,
        test_type_key: type || undefined,
        material_id: material?.id,
        q: query || undefined,
        sort: 'created_at',
        desc: true,
        limit: PICK_PAGE,
      }),
    [state, type, material?.id, query]
  )
  const rows = page.data?.items ?? []
  const already = new Set(taken)
  const open = rows.filter((row) => !already.has(row.id))

  async function pick(ids: string[]) {
    if (ids.length === 0) return
    setBusy(true)
    setError(null)
    try {
      await onPick(ids)
      setChosen(new Set())
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('담지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  function toggle(id: string) {
    const next = new Set(chosen)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setChosen(next)
  }

  return (
    <section aria-label="시험 고르기" className="space-y-2">
      <ErrorNotice error={types.error ?? page.error ?? error} />

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="text-muted-foreground absolute top-2 left-2 size-4" />
          <Input
            aria-label="시험 찾기"
            className="h-8 w-56 pl-8"
            placeholder="이름 · 파일명 · 번호"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
          />
        </div>
        <MaterialPicker
          value={material}
          onSelect={setMaterial}
          placeholder="재료 전체"
          ariaLabel="재료로 거르기"
          className="h-8 w-56"
        />
        {material && (
          <Button size="sm" variant="ghost" onClick={() => setMaterial(null)}>
            재료 풀기
          </Button>
        )}
        <select
          aria-label="시험 종류"
          className={SELECT}
          value={type}
          onChange={(event) => setType(event.target.value)}
        >
          <option value="">시험 종류 전체</option>
          {(types.data ?? []).map((one) => (
            <option key={one.key} value={one.key}>
              {one.label}
            </option>
          ))}
        </select>
        <select
          aria-label="처리 상태"
          className={SELECT}
          value={state}
          onChange={(event) => setState(event.target.value as ProcessingState | '')}
        >
          <option value="">처리 상태 전체</option>
          {(Object.keys(PROCESSING_LABEL) as ProcessingState[]).map((key) => (
            <option key={key} value={key}>
              {PROCESSING_LABEL[key]}
            </option>
          ))}
        </select>
        <span className="text-muted-foreground ml-auto text-xs">
          {page.data
            ? page.data.total > rows.length
              ? `${page.data.total}건 중 최근 ${rows.length}건 — 더 좁혀 찾으세요`
              : `${page.data.total}건`
            : ''}
        </span>
      </div>

      <div className="max-h-[26rem] overflow-y-auto rounded-md border">
        <Table className="text-sm">
          <TableHeader>
            <TableRow>
              <TableHead className="w-8">
                <input
                  type="checkbox"
                  aria-label="보이는 것 모두"
                  disabled={disabled || open.length === 0}
                  checked={open.length > 0 && open.every((row) => chosen.has(row.id))}
                  onChange={(event) =>
                    setChosen(new Set(event.target.checked ? open.map((row) => row.id) : []))
                  }
                />
              </TableHead>
              <TableHead>시험</TableHead>
              <TableHead>재료</TableHead>
              <TableHead>종류</TableHead>
              <TableHead>상태</TableHead>
              <TableHead>처리</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!page.loading && rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-muted-foreground py-6 text-center">
                  이 조건의 시험이 없습니다.
                </TableCell>
              </TableRow>
            ) : null}
            {rows.map((row) => (
              <PickRow
                key={row.id}
                row={row}
                taken={already.has(row.id)}
                checked={chosen.has(row.id)}
                disabled={disabled}
                onToggle={() => toggle(row.id)}
              />
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          disabled={disabled || busy || chosen.size === 0}
          onClick={() => void pick([...chosen])}
        >
          <Plus className="size-3.5" />
          고른 {chosen.size}건 담기
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={disabled || busy || open.length === 0}
          onClick={() => void pick(open.map((row) => row.id))}
        >
          보이는 {open.length}건 모두 담기
        </Button>
        {taken.length > 0 && (
          <span className="text-muted-foreground text-xs">이미 담은 것 {taken.length}건</span>
        )}
      </div>
    </section>
  )
}

function PickRow({
  row,
  taken,
  checked,
  disabled,
  onToggle,
}: {
  row: TestRun
  taken: boolean
  checked: boolean
  disabled: boolean
  onToggle: () => void
}) {
  return (
    <TableRow>
      <TableCell>
        <input
          type="checkbox"
          aria-label={`${row.record_name} 고르기`}
          checked={taken || checked}
          disabled={disabled || taken}
          onChange={onToggle}
        />
      </TableCell>
      <TableCell>
        <span className="block font-mono">{row.code}</span>
        <span className="block">{row.record_name}</span>
      </TableCell>
      <TableCell>{row.material_name ?? <Muted>—</Muted>}</TableCell>
      <TableCell>{row.test_type_label}</TableCell>
      <TableCell>{RUN_STATUS_LABEL[row.status] ?? row.status}</TableCell>
      <TableCell>
        {taken ? (
          <Badge variant="outline">담김</Badge>
        ) : row.adopted_result_id ? (
          <Badge className="bg-emerald-600 hover:bg-emerald-600">채택됨</Badge>
        ) : row.result_count > 0 ? (
          <span>결과 {row.result_count}</span>
        ) : (
          <Muted>처리 전</Muted>
        )}
      </TableCell>
    </TableRow>
  )
}

/** 값이 아닌 것 — 흐리게(표의 규칙). */
function Muted({ children }: { children: string }) {
  return <span className="text-muted-foreground">{children}</span>
}
