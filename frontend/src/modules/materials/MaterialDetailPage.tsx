/**
 * 재료 상세 — 시료와 시편.
 *
 * 계층이 화면에 그대로 보여야 한다. 재료(규격) 아래 시료(실물 한 덩이), 그 아래
 * 시편(잘라낸 조각). **방향은 시편에 있다** — 자를 때 정해지기 때문이고, 그래야
 * 같은 시료의 MD/TD/DD 를 묶어 r값·이방성 파라미터를 구할 수 있다(ADR 0004).
 */

import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  FlaskConical,
  Globe2,
  Layers,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { LENGTH_UNIT, materialsApi } from '@/modules/materials/api'
import type { Sample, Specimen } from '@/modules/materials/api'
import { FittingPanel } from '@/modules/fitting/FittingPanel'
import { EditMaterialDialog } from '@/modules/materials/EditMaterialDialog'
import { EditSpecimenDialog } from '@/modules/materials/EditSpecimenDialog'
import { NewSampleDialog } from '@/modules/materials/NewSampleDialog'
import { SpecimenTests } from '@/modules/tests/SpecimenTests'
import { PropertiesPanel } from '@/modules/statistics/PropertiesPanel'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { useResource } from '@/shared/hooks/useResource'

const ORIENTATIONS = ['MD', 'TD', 'DD', 'NA'] as const

/**
 * '모두 펼치기·접기' 명령.
 *
 * 여닫힘을 부모가 통째로 들고 있으면 줄 하나를 열 때마다 목록 전체가 다시
 * 그려진다. 그래서 상태는 줄에 두고 **명령만 내려보낸다.** `at` 은 같은 방향을
 * 두 번 눌러도 다시 반영되게 하는 값이다 — 사람이 하나를 손으로 닫은 뒤
 * '모두 펼치기' 를 다시 누르는 일이 실제로 있다.
 */
interface ExpandCommand {
  open: boolean
  at: number
}

export default function MaterialDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const material = useResource(() => materialsApi.get(id), [id])
  const samples = useResource(() => materialsApi.samples(id), [id])
  const [addingSample, setAddingSample] = useState(false)
  const [editing, setEditing] = useState(false)
  const [deleteError, setDeleteError] = useState<Error | null>(null)
  const [expand, setExpand] = useState<ExpandCommand | null>(null)

  const item = material.data

  async function removeMaterial() {
    setDeleteError(null)
    try {
      await materialsApi.remove(id)
      navigate('/materials')
    } catch (caught) {
      // 서버가 "시료 N건이 남아 있어 지울 수 없습니다" 를 이유와 함께 준다.
      setDeleteError(caught instanceof Error ? caught : new Error('삭제에 실패했습니다.'))
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title={item?.record_name ?? '재료'}
        description={item?.alias ?? undefined}
        actions={
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setEditing(true)} disabled={!item}>
              <Pencil className="size-4" />
              수정
            </Button>
            <Button variant="outline" onClick={removeMaterial}>
              삭제
            </Button>
          </div>
        }
      />

      <ErrorNotice error={material.error ?? deleteError} className="mb-4" />

      {item && (
        <dl className="mb-8 grid grid-cols-2 gap-x-6 gap-y-3 rounded-md border p-4 text-sm sm:grid-cols-4">
          <Field label="Family" value={item.family} />
          <Field label="Category" value={item.category} />
          <Field label="Grade" value={item.grade} />
          <Field label="Details" value={item.details ?? '—'} />
          <Field
            label="스펙 두께"
            value={
              item.spec_thickness == null
                ? '—'
                : `${item.spec_thickness} ${item.spec_thickness_unit}`
            }
          />
          <Field
            label="소속"
            value={
              item.is_global ? (
                <Badge variant="outline" className="gap-1">
                  <Globe2 className="size-3" />
                  전역
                </Badge>
              ) : (
                (item.owner_workspace_name ?? '—')
              )
            }
          />
          <Field label="시료" value={`${item.sample_count}건`} />
          <Field
            label="등록"
            value={new Date(item.created_at).toLocaleDateString('ko-KR')}
          />
        </dl>
      )}

      {/* **재료 화면이 답해야 하는 질문이 둘이다** — "무엇이 있나(시료·시편)" 와
          "이 재료의 물성은 얼마인가". 세로로 이어 붙이면 시료가 늘수록 물성이
          아래로 밀려나는데, 물성이 이 화면의 결론이다. */}
      <Tabs defaultValue="samples">
        {/* **탭 셋이 서로 다른 질문에 답한다** — 무엇이 있나 / 물성이 얼마인가 /
            해석에 뭘 넣나. 한때 '시험' 탭을 따로 뒀는데, 시편 줄이 접히고 그
            줄에 시험 수·채택·실패가 붙으면서 답하던 것이 겹쳤다. 같은 것을 두
            자리에 두면 어느 쪽이 진짜인지 알 수 없게 된다. */}
        <TabsList>
          <TabsTrigger value="samples">시료·시편</TabsTrigger>
          <TabsTrigger value="properties">물성</TabsTrigger>
          <TabsTrigger value="cards">CAE 카드</TabsTrigger>
        </TabsList>

        <TabsContent value="properties">
          {id && <PropertiesPanel materialId={id} />}
        </TabsContent>

        {/* 물성 탭이 "이 재료가 이렇게 거동한다" 를 데이터로 보인다면, 여기는
            그 거동을 솔버가 읽는 모양으로 굳힌다. 옆 탭인 이유는 입력이 옆
            탭의 대표 곡선이기 때문이다. */}
        <TabsContent value="cards">{id && <FittingPanel materialId={id} />}</TabsContent>

        <TabsContent value="samples">
      {/* **층 이름만으로는 무엇인지 알 수 없다.** 실제로 "시료와 시편과 시험이
          각각 뭐냐" 는 질문이 나왔다. 나눠 둔 이유가 층마다 거기에만 붙는 것이
          있기 때문이므로, 그 붙는 것을 한 줄에 적는다(ADR 0004). */}
      <p className="text-muted-foreground mb-3 rounded-md border border-dashed p-2.5 text-xs">
        <b>시료</b>는 입고된 실물 한 덩이(코일·판 하나)입니다 — 제조사·생산일·로트가
        여기 붙습니다. <b>시편</b>은 거기서 잘라낸 조각이고, <b>방향과 실측 치수</b>가
        여기 있습니다 — 하중을 응력으로 바꾸는 단면적이 그 값입니다.
      </p>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-medium">
          <Layers className="size-4" />
          시료
        </h2>
        <div className="flex items-center gap-1">
          {/* **두 층을 한 번에 여닫는다.** 시료 3개 × 시편 6개를 손으로 여는
              것은 클릭 20번이다. 펼치면 시편마다 시험 목록을 부르므로 요청이
              늘지만, 그것은 누른 사람이 요청한 일이다 — 기본이 접힘인 이유는
              누르지 않았을 때 그 비용을 치르지 않게 하는 것이다. */}
          <Button
            size="sm"
            variant="ghost"
            title="시료와 시편을 모두 펼칩니다"
            onClick={() => setExpand({ open: true, at: Date.now() })}
          >
            <ChevronsUpDown className="size-4" />
            모두 펼치기
          </Button>
          <Button
            size="sm"
            variant="ghost"
            title="시료와 시편을 모두 접습니다"
            onClick={() => setExpand({ open: false, at: Date.now() })}
          >
            <ChevronsDownUp className="size-4" />
            모두 접기
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setAddingSample(true)}>
            <Plus className="size-4" />
            시료 추가
          </Button>
        </div>
      </div>

      <ErrorNotice error={samples.error} className="mb-4" />

      {!samples.loading && (samples.data ?? []).length === 0 && (
        <div className="text-muted-foreground rounded-md border py-10 text-center text-sm">
          시료가 없습니다. 시험을 등록하려면 시료와 시편이 먼저 있어야 합니다.
        </div>
      )}

      <ul className="space-y-2">
        {(samples.data ?? []).map((sample, index) => (
          <SampleRow
            key={sample.id}
            sample={sample}
            /* 첫 시료는 펼친 채로 연다. 전부 접어 두면 시편도 '시험 등록'도
               보이지 않아, 처음 온 사람이 어디서 시작하는지 알 수 없다. */
            defaultOpen={index === 0}
            expand={expand}
            onChanged={() => samples.reload()}
          />
        ))}
      </ul>

        </TabsContent>
      </Tabs>

      {item && (
        <EditMaterialDialog
          material={item}
          open={editing}
          onClose={() => setEditing(false)}
          onDone={() => {
            setEditing(false)
            material.reload()
            // 이름이 바뀌었으면 시료·시편 이름도 따라 바뀌었다. 다시 읽지 않으면
            // 화면에 옛 이름이 남아, 저장이 안 된 것처럼 보인다.
            samples.reload()
          }}
        />
      )}

      {/* 시험 등록 화면과 **같은 폼**을 쓴다. 두 벌로 두면 한쪽에만 필드가 늘거나
          단위를 한쪽만 명시하는 식으로 갈라진다. */}
      <NewSampleDialog
        materialId={id ?? null}
        open={addingSample}
        onClose={() => setAddingSample(false)}
        onCreated={() => {
          setAddingSample(false)
          samples.reload()
          material.reload()
        }}
      />
    </div>
  )
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5">{value}</dd>
    </div>
  )
}

function SampleRow({
  sample,
  onChanged,
  defaultOpen = false,
  expand,
}: {
  sample: Sample
  onChanged: () => void
  defaultOpen?: boolean
  expand: ExpandCommand | null
}) {
  const [open, setOpen] = useState(defaultOpen)
  const [adding, setAdding] = useState(false)
  const [specimenError, setSpecimenError] = useState<Error | null>(null)
  const specimens = useResource(
    () => (open ? materialsApi.specimens(sample.id) : Promise.resolve([])),
    [open, sample.id]
  )

  // '모두 펼치기·접기'. 명령이 올 때만 따라가고, 그 뒤에는 다시 이 줄이 자기
  // 상태를 갖는다 — 하나만 손으로 닫는 것이 계속 가능해야 한다.
  useEffect(() => {
    if (expand) setOpen(expand.open)
  }, [expand])

  return (
    <li className="rounded-md border">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="hover:bg-muted/40 flex w-full items-center gap-3 p-3 text-left"
      >
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        <span className="font-mono text-xs">{sample.record_name}</span>
        {sample.lot_no && <Badge variant="outline">로트 {sample.lot_no}</Badge>}
        {/* **접힌 줄이 상태를 말한다.** 펼치지 않고도 "시험이 몇 건이고 몇 건이
            채택됐나" 가 보여야, 물성 탭의 n 이 왜 그 수인지 여기서 설명된다. */}
        <span className="text-muted-foreground ml-auto flex items-center gap-2 text-sm">
          <span>시편 {sample.specimen_count}</span>
          <RunTally
            total={sample.test_run_count}
            adopted={sample.adopted_count}
            failed={sample.failed_count}
          />
        </span>
      </button>

      {open && (
        <div className="border-t p-3">
          <dl className="mb-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
            <Field label="제조사" value={sample.manufacturer ?? '—'} />
            <Field label="벤더" value={sample.primary_vendor ?? '—'} />
            <Field label="생산일" value={sample.production_date ?? '—'} />
            <Field
              label="밀도"
              value={
                sample.density == null ? '—' : `${sample.density} ${sample.density_unit}`
              }
            />
          </dl>

          <div className="mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-sm font-medium">
              <FlaskConical className="size-3.5" />
              시편
            </span>
            <Button size="sm" variant="ghost" onClick={() => setAdding(true)}>
              <Plus className="size-3.5" />
              시편 추가
            </Button>
          </div>

          <ErrorNotice error={specimens.error ?? specimenError} className="mb-2" />

          {(specimens.data ?? []).length === 0 ? (
            <p className="text-muted-foreground py-4 text-center text-sm">시편이 없습니다.</p>
          ) : (
            <ul className="divide-y">
              {(specimens.data ?? []).map((specimen, index) => (
                <SpecimenRow
                  key={specimen.id}
                  specimen={specimen}
                  /* 시료와 같은 규칙 — 첫 줄만 펼쳐 둔다. 전부 접으면 '시험
                     등록' 이 어디 있는지 알 수 없고, 전부 펼치면 시편 11개짜리
                     시료에서 화면이 끝없이 늘어난다.
                     '모두 펼치기' 뒤에 시료를 열면 시편도 펼쳐진 채로 붙는다 —
                     그러지 않으면 명령이 절반만 먹은 것처럼 보인다. */
                  defaultOpen={expand?.open === true || index === 0}
                  expand={expand}
                  onChanged={() => {
                    specimens.reload()
                    onChanged()
                  }}
                  onRemove={async () => {
                    setSpecimenError(null)
                    try {
                      await materialsApi.removeSpecimen(specimen.id)
                      specimens.reload()
                      onChanged()
                    } catch (caught) {
                      setSpecimenError(
                        caught instanceof Error ? caught : new Error('삭제 실패')
                      )
                    }
                  }}
                />
              ))}
            </ul>
          )}

          <AddSpecimenDialog
            sampleId={sample.id}
            open={adding}
            onClose={() => setAdding(false)}
            onDone={() => {
              setAdding(false)
              specimens.reload()
              onChanged()
            }}
          />
        </div>
      )}
    </li>
  )
}

/**
 * 시험 상태 한 조각 — 시료 줄과 시편 줄이 같은 것을 쓴다.
 *
 * **채택을 눈에 띄게 두는 이유:** 통계와 적합에 들어가는 것은 채택된 결과뿐이다
 * (ADR 0007). 물성 탭의 n 이 왜 그 수인지가 이 숫자에 있다 — 안 보이면 "시험은
 * 15건인데 왜 8개로 평균을 냈지" 를 답할 수 없다.
 */
function RunTally({
  total,
  adopted,
  failed,
}: {
  total: number
  adopted: number
  failed: number
}) {
  if (total === 0) return <span className="text-muted-foreground text-xs">시험 0</span>
  return (
    <span className="flex items-center gap-1.5 text-xs">
      <span>시험 {total}</span>
      {adopted > 0 && (
        <span className="inline-flex items-center gap-0.5 text-emerald-700 dark:text-emerald-500">
          <CheckCircle2 className="size-3" />
          채택 {adopted}
        </span>
      )}
      {failed > 0 && (
        <span className="inline-flex items-center gap-0.5 text-destructive">
          <AlertTriangle className="size-3" />
          실패 {failed}
        </span>
      )}
    </span>
  )
}

/**
 * 시편 한 줄 — **접힌다.**
 *
 * 시편 11개를 전부 펼쳐 두면 화면이 끝없이 늘어나고, 시험 목록을 시편마다
 * 한 번씩 불러 요청이 11번 나간다. 접힌 줄이 아무것도 말하지 않으면 접는 뜻이
 * 없으므로, **시험 수는 접힌 채로도 보인다**(목록이 한 번에 세어 준다).
 */
function SpecimenRow({
  specimen,
  defaultOpen,
  expand,
  onRemove,
  onChanged,
}: {
  specimen: Specimen
  defaultOpen: boolean
  expand: ExpandCommand | null
  onRemove: () => void
  onChanged: () => void
}) {
  const [open, setOpen] = useState(defaultOpen)
  const [editing, setEditing] = useState(false)

  useEffect(() => {
    if (expand) setOpen(expand.open)
  }, [expand])
  const dimensions = [specimen.thickness, specimen.width, specimen.gauge_length]
    .map((value) => (value == null ? '—' : value))
    .join(' × ')

  return (
    <li className="text-sm">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="hover:bg-muted/40 -mx-1 flex flex-1 items-center gap-3 rounded px-1 py-2 text-left"
        >
          {open ? (
            <ChevronDown className="size-3.5 shrink-0" />
          ) : (
            <ChevronRight className="size-3.5 shrink-0" />
          )}
          <Badge variant="secondary">{specimen.orientation}</Badge>
          <span className="font-mono text-xs">{specimen.record_name}</span>
          <span className="text-muted-foreground ml-auto tabular-nums">
            {dimensions} {specimen.length_unit}
          </span>
          {/* 접힌 줄에서 시험 상태가 보여야 한다. 없으면 하나씩 펼쳐 봐야
              "어느 시편이 실패했나 · 채택됐나" 를 알게 된다. */}
          <RunTally
            total={specimen.test_run_count}
            adopted={specimen.adopted_count}
            failed={specimen.failed_count}
          />
        </button>

        {/* **치수를 고칠 자리.** 일괄 등록은 방향만 주고 시편을 만들어서
            치수가 빈 채로 쌓인다 — 그 상태로는 처리가 첫 단계에서 막힌다. */}
        <Button
          size="sm"
          variant="ghost"
          title="시편 수정 (치수·메모)"
          onClick={() => setEditing(true)}
        >
          <Pencil className="size-3.5" />
        </Button>

        {/* 일괄 등록이 만든 뒤 업로드가 실패하면 빈 시편이 남는다. 치울 길이
            없으면 목록이 계속 지저분해진다. 서버가 시험이 달린 시편은 거절하므로
            실수로 지울 수는 없다. */}
        <Button
          size="sm"
          variant="ghost"
          title="시편 삭제 (시험이 있으면 서버가 막습니다)"
          onClick={onRemove}
        >
          <Trash2 className="size-3.5" />
        </Button>
      </div>

      {/* 시험 UI 는 시험 모듈이 갖는다. 여기는 자리만 내어 준다(R5).
          접혀 있으면 아예 부르지 않는다 — 요청도 같이 줄어든다. */}
      {open && (
        <div className="pb-2 pl-7">
          <SpecimenTests specimenId={specimen.id} specimenName={specimen.record_name} />
        </div>
      )}

      <EditSpecimenDialog
        specimen={specimen}
        open={editing}
        onClose={() => setEditing(false)}
        onSaved={() => {
          setEditing(false)
          onChanged()
        }}
      />
    </li>
  )
}

function AddSpecimenDialog({
  sampleId,
  open,
  onClose,
  onDone,
}: {
  sampleId: string
  open: boolean
  onClose: () => void
  onDone: () => void
}) {
  const [orientation, setOrientation] = useState<string>('MD')
  const [form, setForm] = useState({ thickness: '', width: '', gauge_length: '' })
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit() {
    setSaving(true)
    setError(null)
    try {
      await materialsApi.createSpecimen(sampleId, {
        orientation,
        thickness: form.thickness === '' ? null : Number(form.thickness),
        width: form.width === '' ? null : Number(form.width),
        gauge_length: form.gauge_length === '' ? null : Number(form.gauge_length),
        length_unit: LENGTH_UNIT,
      })
      setForm({ thickness: '', width: '', gauge_length: '' })
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('등록에 실패했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  const field = (key: keyof typeof form) => ({
    value: form[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value })),
  })

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>시편 추가</DialogTitle>
          <DialogDescription>
            방향은 자를 때 정해집니다. 번호는 방향별로 이어서 붙습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label>방향</Label>
          <div className="flex gap-2">
            {ORIENTATIONS.map((value) => (
              <Button
                key={value}
                type="button"
                size="sm"
                variant={orientation === value ? 'default' : 'outline'}
                onClick={() => setOrientation(value)}
              >
                {value}
              </Button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="thickness">실측 두께 (mm)</Label>
            <Input id="thickness" type="number" step="0.01" {...field('thickness')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="width">실측 폭 (mm)</Label>
            <Input id="width" type="number" step="0.01" {...field('width')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gauge">게이지 길이 (mm)</Label>
            <Input id="gauge" type="number" step="0.1" {...field('gauge_length')} />
          </div>
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            취소
          </Button>
          <Button onClick={submit} disabled={saving}>
            추가
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
