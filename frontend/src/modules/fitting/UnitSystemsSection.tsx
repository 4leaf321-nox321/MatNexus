/**
 * 덱 단위계 — 목록과 「단위계 만들기」.
 *
 * **질량·길이·시간 셋만 고른다.** 응력·밀도·비열·전도도의 기호와 인수는 서버가
 * 차원식으로 유도한다(2026-09-05). 두 계(SI · mm·N·tonne)가 코드에 박혀 있어
 * LS-DYNA 의 mm·ms·kg(GPa) 같은 조합은 배포가 필요했다. 저장하기 전에 **무엇이
 * 어떻게 적힐지** 보여 준다 — 응력이 GPa 인지 MPa 인지는 만든 뒤에 알면 늦다.
 */

import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

import { fittingApi } from '@/modules/fitting/api'
import type { UnitSystem } from '@/modules/fitting/api'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

/** 표에 보이는 물리량 — 덱에 실제로 적히는 것들이다. 순서는 사람이 찾는 순서. */
const SHOWN: ReadonlyArray<[si: string, label: string]> = [
  ['Pa', '응력'],
  ['kg/m3', '밀도'],
  ['s', '시간'],
  ['J/(kg.K)', '비열'],
  ['W/(m.K)', '열전도율'],
]

export function UnitSystemsSection({ canEdit }: { canEdit: boolean }) {
  const systems = useResource(() => fittingApi.unitSystems(), [])
  const [making, setMaking] = useState(false)
  const [removing, setRemoving] = useState<UnitSystem | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const rows = systems.data ?? []

  async function remove(item: UnitSystem) {
    setBusy(true)
    setError(null)
    try {
      await fittingApi.removeUnitSystem(item.key)
      setRemoving(null)
      systems.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="mt-10" aria-labelledby="unit-systems-heading">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="unit-systems-heading" className="text-lg font-semibold">
            덱 단위계
          </h2>
          <p className="text-muted-foreground text-sm">
            덱을 내려받을 때 고르는 계입니다. 질량·길이·시간 셋만 정하면 응력·밀도·비열·
            열전도율은 그 셋에서 따라옵니다 — 인수를 손으로 적지 않습니다.
          </p>
        </div>
        {canEdit ? (
          <Button variant="outline" onClick={() => setMaking(true)}>
            <Plus className="size-4" />
            단위계 만들기
          </Button>
        ) : null}
      </div>
      {error ? <ErrorNotice error={error} className="mb-3" /> : null}
      {systems.error ? <ErrorNotice error={systems.error} className="mb-3" /> : null}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>이름</TableHead>
            <TableHead>선언</TableHead>
            {SHOWN.map(([si, label]) => (
              <TableHead key={si}>{label}</TableHead>
            ))}
            <TableHead className="w-12" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((item) => (
            <TableRow key={item.key}>
              <TableCell>
                <span className="flex flex-wrap items-center gap-2">
                  {item.label}
                  <span className="text-muted-foreground font-mono text-xs">{item.key}</span>
                  {item.is_default ? <Badge variant="secondary">기본</Badge> : null}
                  {item.builtin ? <Badge variant="outline">붙박이</Badge> : null}
                </span>
              </TableCell>
              <TableCell className="font-mono text-xs">{item.declaration}</TableCell>
              {SHOWN.map(([si]) => (
                <TableCell key={si} className="font-mono text-xs">
                  {item.symbols?.[si] ?? '—'}
                </TableCell>
              ))}
              <TableCell className="text-right">
                {/* **붙박이는 못 지운다.** 지운 계로 이미 받은 덱은 파일 머리의
                    선언이 정본이라 흔들리지 않는다. */}
                {canEdit && !item.builtin ? (
                  <Button
                    variant="ghost"
                    size="icon"
                    title="지우기"
                    aria-label={`${item.label} 지우기`}
                    onClick={() => setRemoving(item)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                ) : null}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <NewUnitSystemDialog
        open={making}
        existing={new Set(rows.map((one) => one.key))}
        onClose={() => setMaking(false)}
        onMade={() => {
          setMaking(false)
          systems.reload()
        }}
      />
      <ConfirmDialog
        open={removing !== null}
        title="단위계를 지웁니다"
        body={
          <p>
            <b>{removing?.label}</b> 을(를) 지웁니다. 이미 이 계로 받은 덱은 파일 머리에
            계가 적혀 있어 그대로 읽힙니다.
          </p>
        }
        busy={busy}
        onConfirm={() => {
          if (removing) void remove(removing)
        }}
        onClose={() => setRemoving(null)}
      />
    </section>
  )
}

function NewUnitSystemDialog({
  open,
  existing,
  onClose,
  onMade,
}: {
  open: boolean
  existing: Set<string>
  onClose: () => void
  onMade: () => void
}) {
  const bases = useResource(() => fittingApi.unitSystemBaseUnits(), [])
  const [mass, setMass] = useState('kg')
  const [length, setLength] = useState('mm')
  const [time, setTime] = useState('ms')
  const [key, setKey] = useState('')
  const [label, setLabel] = useState('')
  const [preview, setPreview] = useState<UnitSystem | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)

  // **고를 때마다 무엇이 어떻게 적힐지 본다.** 저장하지 않는 미리보기다.
  useEffect(() => {
    if (!open) return
    let alive = true
    void fittingApi
      .deriveUnitSystem({ mass, length, time })
      .then((made) => {
        if (alive) setPreview(made)
      })
      .catch((caught: unknown) => {
        if (alive) setError(caught instanceof Error ? caught : new Error('유도하지 못했습니다.'))
      })
    return () => {
      alive = false
    }
  }, [open, mass, length, time])

  // 세 단위로 key 와 이름을 지어 둔다 — 사람이 고쳐도 된다.
  const suggestedKey = `${length}_${time}_${mass}`.toLowerCase().replace(/[^a-z0-9]+/g, '_')
  const suggestedLabel = preview
    ? `${length} · ${time} · ${mass} (${preview.symbols?.Pa ?? '?'})`
    : `${length} · ${time} · ${mass}`
  const finalKey = key || suggestedKey
  const finalLabel = label || suggestedLabel
  const taken = existing.has(finalKey)
  const keyOk = /^[a-z][a-z0-9_]{1,49}$/.test(finalKey)

  async function make() {
    setBusy(true)
    setError(null)
    try {
      await fittingApi.createUnitSystem({ key: finalKey, label: finalLabel, mass, length, time })
      setKey('')
      setLabel('')
      onMade()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('만들지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  function picker(
    name: string,
    value: string,
    onChange: (next: string) => void,
    options: string[] | undefined
  ) {
    return (
      <div className="space-y-1">
        <Label className="text-xs">{name}</Label>
        <Select value={value} onValueChange={onChange}>
          <SelectTrigger aria-label={name}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(options ?? [value]).map((one) => (
              <SelectItem key={one} value={one}>
                {one}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    )
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? null : onClose())}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>단위계 만들기</DialogTitle>
          <DialogDescription>
            질량·길이·시간을 고르면 나머지는 차원식으로 따라옵니다. 응력이 MPa 인지 GPa
            인지 아래에서 먼저 확인하세요.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid grid-cols-3 gap-3">
            {picker('질량', mass, setMass, bases.data?.mass)}
            {picker('길이', length, setLength, bases.data?.length)}
            {picker('시간', time, setTime, bases.data?.time)}
          </div>

          <div className="rounded-md border p-3 text-sm" aria-label="유도된 단위">
            <div className="text-muted-foreground mb-2 text-xs">이 계에서 덱에 적히는 단위</div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
              {SHOWN.map(([si, name]) => (
                <div key={si} className="flex items-baseline justify-between gap-2">
                  <dt className="text-muted-foreground">{name}</dt>
                  <dd className="font-mono">{preview?.symbols?.[si] ?? '…'}</dd>
                </div>
              ))}
            </dl>
            <div className="text-muted-foreground mt-2 text-xs">
              덱 머리 선언: <span className="font-mono">{preview?.declaration ?? '…'}</span>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="unit-system-key" className="text-xs">
                key
              </Label>
              <Input
                id="unit-system-key"
                value={key}
                placeholder={suggestedKey}
                onChange={(event) => setKey(event.target.value)}
              />
              <p className="text-muted-foreground text-xs">
                파일 이름과 API 인자에 들어갑니다. 소문자·숫자·밑줄.
              </p>
            </div>
            <div className="space-y-1">
              <Label htmlFor="unit-system-label" className="text-xs">
                이름
              </Label>
              <Input
                id="unit-system-label"
                value={label}
                placeholder={suggestedLabel}
                onChange={(event) => setLabel(event.target.value)}
              />
            </div>
          </div>
          {taken ? (
            <p className="text-destructive text-sm">같은 key 의 단위계가 이미 있습니다.</p>
          ) : !keyOk ? (
            <p className="text-destructive text-sm">key 는 소문자로 시작하는 2~50자입니다.</p>
          ) : null}
          {error ? <ErrorNotice error={error} /> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
          <Button disabled={busy || taken || !keyOk || !preview} onClick={() => void make()}>
            만들기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
