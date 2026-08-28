/**
 * 묶음 — **여러 시험을 묶어 만든 것**(ADR 0020).
 *
 * ## 왜 물성 탭인가
 *
 * 묶음은 「이 재료가 이렇게 거동한다」 를 만드는 일이다. 시료·시편 탭은 무엇이
 * 있나를, CAE 카드 탭은 해석에 뭘 넣나를 답한다 — 그 사이가 여기다.
 *
 * **제 화면을 따로 두지 않았다.** 묶는 자리가 둘이 되면 어느 쪽이 진짜인지 알 수
 * 없다(시험 탭을 없앤 것과 같은 판단).
 *
 * ## 고른 것과 쓴 것을 나란히 보인다
 *
 * 대표를 고르면 셋을 골라도 하나만 쓴다. 그 차이가 안 보이면 「셋을 묶었다」 가
 * 거짓말이 된다 — 서버가 둘을 따로 주는 이유가 그것이다.
 *
 * ## 방법 목록을 화면이 안 적는다
 *
 * `/groups/kinds` 가 고를 값과 설명까지 준다. 화면이 적어 두면 새 물성을 붙일 때
 * 화면도 고쳐야 하고, 그러면 확장이 아니다(D7).
 */

import { useState } from 'react'
import { Layers } from 'lucide-react'

import { groupsApi } from '@/modules/materials/api.groups'
import type { GroupResult, GroupingSpec } from '@/modules/materials/api.groups'
import { testsApi } from '@/modules/tests/api'
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
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { useResource } from '@/shared/hooks/useResource'
import { formatScalar } from '@/shared/units'

/** 값 한 줄. 단위는 **서버가 준 것**을 쓴다(라벨에 손으로 안 적는다). */
function Value({ label, value, unit }: { label: string; value: number; unit: string }) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="font-mono text-sm tabular-nums">
        {unit === '1' ? value.toPrecision(4) : formatScalar(value, unit, undefined)}
      </dd>
    </div>
  )
}

function GroupCard({ row, spec }: { row: GroupResult; spec?: GroupingSpec }) {
  const units = new Map((spec?.makes_values ?? []).map((one) => [one.key, one]))
  const method = String(row.options?.method ?? row.detail?.method ?? '')
  const terms = (row.detail?.terms as { relaxation_time_s: number }[] | undefined) ?? []

  return (
    <div className="rounded-md border p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge variant="outline">{spec?.label ?? row.plugin_id}</Badge>
        {method && <Badge>{method}</Badge>}
        <span className="text-muted-foreground text-xs">
          {/* **고른 것과 쓴 것을 나란히.** 대표를 고르면 셋 중 하나만 쓴다. */}
          고른 {row.members.length}건 · 쓴 {row.used.length}건
          {terms.length > 0 && ` · ${terms.length}항`}
        </span>
        <span className="text-muted-foreground ml-auto text-xs">
          {new Date(row.created_at).toLocaleString('ko-KR')}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
        {Object.entries(row.values).map(([key, value]) => (
          <Value
            key={key}
            label={units.get(key)?.label ?? key}
            value={value}
            unit={units.get(key)?.si_unit ?? '1'}
          />
        ))}
      </dl>

      <p className="text-muted-foreground mt-2 font-mono text-xs break-all">
        {row.used.join(' · ')}
      </p>

      {/* **감수한 것을 적는다.** 조건이 조금씩 다른 것을 묶는 일이라, 무엇을
          넘겼는지가 남아야 한다. */}
      {row.warnings.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {row.warnings.map((said) => (
            <li key={said} className="text-xs text-amber-700 dark:text-amber-500">
              {said}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function GroupsPanel({ materialId }: { materialId: string }) {
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState('')
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [options, setOptions] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<Error | null>(null)

  const kinds = useResource(() => groupsApi.kinds(), [])
  const rows = useResource(() => groupsApi.ofMaterial(materialId), [materialId])
  // 묶을 후보는 **채택까지 끝난 것**이 아니라 읽힌 것 전부다 — 마스터커브는
  // 채택과 무관하게 만든다.
  const runs = useResource(
    () => testsApi.runs({ material_id: materialId, status: 'parsed', limit: 200 }),
    [materialId]
  )

  const specs = kinds.data ?? []
  const chosen = specs.find((one) => one.id === kind) ?? specs[0]
  const candidates = runs.data?.items ?? []

  async function create() {
    if (!chosen) return
    setBusy(true)
    setFailed(null)
    try {
      await groupsApi.create({
        plugin_id: chosen.id,
        run_ids: [...picked],
        options: Object.fromEntries(
          Object.entries(options)
            .filter(([, value]) => value !== '')
            // 숫자 칸은 숫자로 보낸다 — 서버가 `int` 를 기대한다.
            .map(([key, value]) => [
              key,
              chosen.params.find((one) => one.name === key)?.type === 'int'
                ? Number(value)
                : value,
            ])
        ),
      })
      setOpen(false)
      setPicked(new Set())
      rows.reload()
    } catch (error) {
      setFailed(error as Error)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-medium">묶음</h3>
        <span className="text-muted-foreground text-xs">
          여러 시험을 묶어 계수 한 벌을 만듭니다
        </span>
        <Button
          size="sm"
          variant="outline"
          className="ml-auto"
          disabled={specs.length === 0}
          onClick={() => {
            setKind(specs[0]?.id ?? '')
            setOptions({})
            setOpen(true)
          }}
        >
          <Layers className="size-4" />
          새로 묶기
        </Button>
      </div>

      <ErrorNotice error={rows.error ?? kinds.error} />

      {!rows.loading && (rows.data ?? []).length === 0 && (
        <p className="text-muted-foreground rounded-md border py-8 text-center text-sm">
          아직 묶은 것이 없습니다.
        </p>
      )}

      <div className="space-y-2">
        {(rows.data ?? []).map((row) => (
          <GroupCard key={row.id} row={row} spec={specs.find((s) => s.id === row.plugin_id)} />
        ))}
      </div>

      <Dialog open={open} onOpenChange={(next) => !next && setOpen(false)}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>새로 묶기</DialogTitle>
            <DialogDescription>
              둘 이상을 고르세요. 하나를 「묶었다」 고 부르면 나중에 묶음인지 한 건인지
              구별할 수 없습니다.
            </DialogDescription>
          </DialogHeader>

          <ErrorNotice error={failed} />

          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>무엇으로</Label>
              <select
                aria-label="묶는 계산"
                className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                value={chosen?.id ?? ''}
                onChange={(event) => {
                  setKind(event.target.value)
                  setOptions({})
                }}
              >
                {specs.map((one) => (
                  <option key={one.id} value={one.id}>
                    {one.label}
                  </option>
                ))}
              </select>
            </div>

            {/* **고를 값도 서버가 준다.** 화면이 적어 두면 새 방법이 생겨도 안 보인다. */}
            {(chosen?.params ?? []).map((param) => {
              const choices = param.choices ?? []
              return (
              <div key={param.name} className="space-y-1.5">
                <Label>{param.label}</Label>
                {choices.length > 0 ? (
                  <select
                    aria-label={param.label}
                    className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                    value={options[param.name] ?? String(param.default ?? '')}
                    onChange={(event) =>
                      setOptions((now) => ({ ...now, [param.name]: event.target.value }))
                    }
                  >
                    {choices.map((one) => (
                      <option key={one} value={one}>
                        {one}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Input
                    aria-label={param.label}
                    value={options[param.name] ?? ''}
                    placeholder={String(param.default ?? '')}
                    onChange={(event) =>
                      setOptions((now) => ({ ...now, [param.name]: event.target.value }))
                    }
                  />
                )}
                {param.help && (
                  <p className="text-muted-foreground text-xs">{param.help}</p>
                )}
                </div>
              )
            })}

            <div className="space-y-1.5">
              <Label>무엇을 ({picked.size}건 고름)</Label>
              <div className="max-h-56 space-y-1 overflow-y-auto rounded-md border p-2">
                {candidates.map((run) => (
                  <label key={run.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      aria-label={`${run.record_name} 고르기`}
                      checked={picked.has(run.id)}
                      onChange={(event) =>
                        setPicked((now) => {
                          const next = new Set(now)
                          if (event.target.checked) next.add(run.id)
                          else next.delete(run.id)
                          return next
                        })
                      }
                    />
                    <span className="font-mono text-xs">{run.record_name}</span>
                    <span className="text-muted-foreground text-xs">
                      {run.test_type_label}
                    </span>
                  </label>
                ))}
                {candidates.length === 0 && (
                  <p className="text-muted-foreground p-2 text-xs">
                    읽힌 시험이 없습니다.
                  </p>
                )}
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
              취소
            </Button>
            <Button onClick={() => void create()} disabled={busy || picked.size < 2}>
              {busy ? '묶는 중…' : `${picked.size}건 묶기`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
