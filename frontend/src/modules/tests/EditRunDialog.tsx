/**
 * 시험 고치기 — **등록한 뒤에 적을 자리** (VOC 2026-09-13).
 *
 * 지그를 나중에 알았거나, 시험자를 잘못 적었거나, 파일을 잘못 올렸을 때 갈 자리가
 * 없었다. 목록의 일괄 수정은 한 칸씩이고 단위 딸린 조건은 안 받는다 — 값만 갈아
 * 끼우면 입력 단위 기록과 어긋나기 때문이다. 여기서는 **등록 창과 같은 칸에 같은
 * 단위로** 받으므로 조건도 고칠 수 있다.
 *
 * ## 원본 교체는 따로 묻는다
 *
 * 파일이 바뀌면 곡선이 바뀌고, 그 전에 채택한 처리 결과는 옛 곡선의 것이 된다.
 * 자동으로 다시 돌리지 않는다 — 저장된 레시피를 사람 모르게 돌리는 셈이라서.
 * 대신 그 결과에 「옛 원본의 결과」 가 붙고, 다시 돌릴지는 사람이 정한다.
 * 옛 파일은 지우지 않는다.
 */

import { Loader2, Upload } from 'lucide-react'
import { useState } from 'react'

import { testsApi } from '@/modules/tests/api'
import type { TestRunDetail, TestType } from '@/modules/tests/api'
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { FileDrop } from '@/shared/components/FileDrop'
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
import { conditionUnits, display, toDisplay } from '@/shared/units'

interface Props {
  run: TestRunDetail
  /** 이 시험의 종류 — 조건 칸의 정의가 여기 있다. 아직 못 읽었으면 조건 칸은 안 보인다. */
  testType: TestType | null
  onClose: () => void
  onDone: (message: string) => void
}

/** `datetime-local` 이 받는 모양(로컬 시각, 초 없이). */
function localInput(iso: string | null): string {
  if (!iso) return ''
  const at = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`
}

/** 저장된 SI 값 → 등록 창이 쓰는 화면 단위의 글자. 글자 조건은 그대로. */
function shownConditions(run: TestRunDetail, testType: TestType | null): Record<string, string> {
  const out: Record<string, string> = {}
  for (const field of testType?.conditions ?? []) {
    const raw = run.conditions[field.key]
    if (raw === undefined || raw === null || raw === '') continue
    if (field.value_type === 'number' && field.si_unit && typeof raw === 'number') {
      out[field.key] = String(
        Number(toDisplay(raw, field.si_unit, field.dimension).toPrecision(10))
      )
    } else {
      out[field.key] = String(raw)
    }
  }
  return out
}

export function EditRunDialog({ run, testType, onClose, onDone }: Props) {
  const [testedAt, setTestedAt] = useState(localInput(run.tested_at))
  const [operator, setOperator] = useState(run.operator ?? '')
  const [instrument, setInstrument] = useState(run.instrument ?? '')
  const [division, setDivision] = useState(run.division ?? '')
  const [note, setNote] = useState(run.note ?? '')
  const [conditions, setConditions] = useState<Record<string, string>>(() =>
    shownConditions(run, testType)
  )
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState<'save' | 'replace' | null>(null)
  const [error, setError] = useState<Error | null>(null)

  async function save() {
    setBusy('save')
    setError(null)
    try {
      const fields = testType?.conditions ?? []
      const filled = Object.fromEntries(
        Object.entries(conditions)
          .filter(([, value]) => value !== '')
          .map(([key, value]) => {
            const field = fields.find((c) => c.key === key)
            return [key, field?.value_type === 'number' ? Number(value) : value]
          })
      )
      await testsApi.update(run.id, {
        tested_at: testedAt ? new Date(testedAt).toISOString() : null,
        operator: operator || null,
        instrument: instrument || null,
        division: division || null,
        note: note || null,
        // 조건 정의를 못 읽었으면 조건은 안 보낸다 — 안 보낸 것은 그대로다.
        conditions: testType ? filled : null,
        condition_units: conditionUnits(fields),
      })
      onDone('시험 정보를 고쳤습니다.')
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('고치지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  async function replace() {
    if (!file) return
    setBusy('replace')
    setError(null)
    try {
      const done = await testsApi.replaceSource(run.id, file)
      onDone(done.message)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('원본을 바꾸지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>시험 편집 — {run.record_name}</DialogTitle>
          <DialogDescription>
            등록 창과 같은 칸입니다. 조건은 화면 단위로 적으면 서버가 저장 단위로 바꿉니다.
          </DialogDescription>
        </DialogHeader>

        {testType && testType.conditions.length > 0 && (
          <div className="space-y-1.5">
            <Label>시험 조건</Label>
            <div className="grid grid-cols-2 gap-3">
              {testType.conditions.map((field) => (
                <div key={field.key} className="space-y-1">
                  <Label htmlFor={`edit-${field.key}`} className="text-muted-foreground text-xs">
                    {field.label}
                    {field.si_unit && ` (${display(field.si_unit, field.dimension).unit})`}
                    {field.is_required && <span className="text-destructive"> *</span>}
                  </Label>
                  {field.value_type === 'choice' ? (
                    <select
                      id={`edit-${field.key}`}
                      className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                      value={conditions[field.key] ?? ''}
                      onChange={(event) =>
                        setConditions((current) => ({ ...current, [field.key]: event.target.value }))
                      }
                    >
                      <option value="">—</option>
                      {(field.choices ?? []).map((one) => (
                        <option key={one} value={one}>
                          {one}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <Input
                      id={`edit-${field.key}`}
                      type={field.value_type === 'number' ? 'number' : 'text'}
                      step="any"
                      value={conditions[field.key] ?? ''}
                      onChange={(event) =>
                        setConditions((current) => ({ ...current, [field.key]: event.target.value }))
                      }
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="edit-tested-at">시험일시</Label>
            <Input
              id="edit-tested-at"
              type="datetime-local"
              value={testedAt}
              onChange={(event) => setTestedAt(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="edit-operator">시험자</Label>
            <Input
              id="edit-operator"
              value={operator}
              onChange={(event) => setOperator(event.target.value)}
            />
          </div>
        </div>
        <VocabularyField slug="instrument" label="장비" value={instrument} onChange={setInstrument} />
        <VocabularyField slug="division" label="사업부" value={division} onChange={setDivision} />
        <div className="space-y-1.5">
          <Label htmlFor="edit-note">메모</Label>
          <Input id="edit-note" value={note} onChange={(event) => setNote(event.target.value)} />
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy !== null}>
            취소
          </Button>
          <Button onClick={() => void save()} disabled={busy !== null}>
            {busy === 'save' && <Loader2 className="size-4 animate-spin" />}
            저장
          </Button>
        </DialogFooter>

        {/* 원본 교체 — 저장과 별개다. 누르는 순간 다시 읽기가 큐에 들어간다. */}
        <div className="mt-2 space-y-2 rounded-md border border-dashed p-3">
          <Label>원본 파일 변경</Label>
          <p className="text-muted-foreground text-xs">
            지금 원본: <b className="text-foreground font-mono">{run.source_filename ?? '없음'}</b>
            {(run.source_history?.length ?? 0) > 0 && ` · 전에 ${run.source_history.length}번 바꿈`}
          </p>
          <FileDrop onFiles={(files) => setFile(files[0] ?? null)} />
          {file && (
            <p className="text-muted-foreground text-xs">
              고른 파일: <b className="text-foreground font-mono">{file.name}</b>
            </p>
          )}
          <p className="text-muted-foreground text-xs">
            바꾸면 새 파일로 다시 읽습니다. 옛 파일은 남습니다.
            {run.result_count > 0 && (
              <>
                {' '}
                <b className="text-foreground">
                  처리 결과 {run.result_count}건은 옛 원본의 것이 됩니다
                </b>{' '}
                — 지우지도 다시 돌리지도 않습니다. 결과 탭에서 표시를 보고 다시 돌리세요.
              </>
            )}
          </p>
          <Button
            variant="outline"
            size="sm"
            disabled={!file || busy !== null}
            onClick={() => void replace()}
          >
            {busy === 'replace' ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Upload className="size-4" />
            )}
            원본 교체 후 재파싱
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
