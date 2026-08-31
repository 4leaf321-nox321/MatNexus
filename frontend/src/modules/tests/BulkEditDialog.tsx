/**
 * 고른 시험의 **칸 하나**를 한 번에 맞춘다.
 *
 * ## 왜 한 칸인가
 *
 * 여러 칸을 함께 받으면 「안 보낸 것」과 「비운 것」을 구별할 수 없다. 화면도
 * 「지금 무엇을 바꾸는 중인가」를 말하기 어려워지고, 그러면 20건을 바꾸는
 * 단추를 누르는 순간 무슨 일이 일어날지 사람이 확신할 수 없다.
 *
 * ## 왜 이 다섯 칸뿐인가
 *
 * 목록은 서버가 정한다(`EDITABLE_FIELDS`). 시편·재료·시험 종류는 이름을 만드는
 * 값이라 바꾸면 `record_name` 과 그 아래가 흔들리고, 상태·채택 결과는 처리
 * 파이프라인이 쓰는 값이라 손으로 옮기면 **「읽힌 적 없는데 처리됨」** 같은
 * 상태가 만들어진다. 남는 것은 올릴 때 사람이 적는 메타데이터뿐이다.
 *
 * ## 비우면 지운다
 *
 * 빈 칸으로 두고 적용하면 그 값을 지운다. 그것을 말해 주지 않으면, 값을 확인만
 * 하려고 창을 열었다 무심코 누른 사람이 스무 건을 비운다.
 */

import { useEffect, useState } from 'react'

import { testsApi } from '@/modules/tests/api'
import type { BulkUpdateField, BulkUpdateResult } from '@/modules/tests/api'
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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

/** 고칠 수 있는 칸. **서버의 `EDITABLE_FIELDS` 와 같은 목록이다.** */
const FIELDS: {
  key: BulkUpdateField
  label: string
  /** 기준정보를 거치는 칸이면 그 축. 자유 입력이면 없다. */
  slug?: string
  kind?: 'date'
  hint: string
}[] = [
  { key: 'division', label: '사업부', slug: 'division', hint: '이 시험을 낸 사업부' },
  { key: 'instrument', label: '장비', slug: 'instrument', hint: '시험을 돌린 장비' },
  { key: 'operator', label: '시험자', hint: '집계 축이 아니라 연락처에 가깝다' },
  { key: 'tested_at', label: '시험일', kind: 'date', hint: '실제로 시험한 날' },
  {
    key: 'testing_group',
    label: '시험 그룹',
    hint: '나중에 묶으려고 적는 이름. 스무 건을 올린 뒤에 정해지는 일이 잦다',
  },
  { key: 'note', label: '메모', hint: '' },
]

export function BulkEditDialog({
  open,
  runIds,
  onClose,
  onDone,
}: {
  open: boolean
  runIds: string[]
  onClose: () => void
  /** 바뀐 뒤 목록·집계를 다시 읽는다. */
  onDone: () => void
}) {
  const [field, setField] = useState<BulkUpdateField>('division')
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [result, setResult] = useState<BulkUpdateResult | null>(null)

  useEffect(() => {
    if (!open) return
    setField('division')
    setValue('')
    setError(null)
    setResult(null)
  }, [open])

  const picked = FIELDS.find((one) => one.key === field) ?? FIELDS[0]

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const done = await testsApi.bulkUpdate(runIds, field, value)
      setResult(done)
      onDone()
      if (done.blocked.length === 0) onClose()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('바꾸지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>시험 {runIds.length}건 한꺼번에 고치기</DialogTitle>
          <DialogDescription>
            <b>칸 하나</b>를 골라 고른 시험 전부에 같은 값을 넣습니다. 시편·재료·시험 종류와
            상태는 여기서 못 바꿉니다 — 이름과 처리 흐름이 매달려 있습니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={error} />

        <div className="space-y-1.5">
          <Label htmlFor="bulk-field">무엇을</Label>
          <Select
            value={field}
            onValueChange={(next) => {
              setField(next as BulkUpdateField)
              // **값을 남겨 두지 않는다.** 장비에 적은 글자가 사업부 칸에
              // 그대로 남아 있으면 그것이 그대로 스무 건에 들어간다.
              setValue('')
              setResult(null)
            }}
          >
            <SelectTrigger id="bulk-field" aria-label="고칠 칸">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FIELDS.map((one) => (
                <SelectItem key={one.key} value={one.key}>
                  {one.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {picked.slug ? (
          // **기준정보를 거친다.** 한 번에 스무 건을 바꾸는 자리라 오타의 파급이
          // 크다 — 자유 입력이면 한 글자 틀릴 때 스무 건이 새 값을 가리킨다.
          <VocabularyField
            slug={picked.slug}
            label={picked.label}
            value={value}
            onChange={setValue}
          />
        ) : (
          <div className="space-y-1.5">
            <Label htmlFor="bulk-value">{picked.label}</Label>
            <Input
              id="bulk-value"
              type={picked.kind === 'date' ? 'date' : 'text'}
              value={value}
              onChange={(event) => setValue(event.target.value)}
            />
          </div>
        )}

        <p className="text-muted-foreground text-xs">
          {picked.hint && `${picked.hint} · `}
          <b>비워 두고 적용하면 그 값을 지웁니다.</b>
        </p>

        {result && (
          <div className="text-xs">
            <p>
              {result.updated}건을 바꿨습니다
              {/* **조용히 성공으로 세지 않는다.** 20건을 골랐는데 「17건」이
                  나오면 나머지 셋이 왜 빠졌는지 알 수 있어야 한다. */}
              {result.unchanged > 0 && ` · ${result.unchanged}건은 이미 그 값이었습니다`}
            </p>
            {result.blocked.length > 0 && (
              <p className="text-destructive mt-1">
                {result.blocked.length}건은 권한이 없어 그대로입니다.
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={submit} disabled={busy || runIds.length === 0}>
            {busy ? '바꾸는 중…' : `${runIds.length}건에 적용`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
