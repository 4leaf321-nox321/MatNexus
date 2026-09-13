/**
 * 새 측정 의뢰 — 한 화면 세 묶음.
 *
 *   ① 무엇을   재료를 찾아 시료를 고른다. **시료가 있어야 의뢰한다** — 재료만으로는
 *              잴 것이 없다. 목적은 자유 글(과제를 특정하는 키는 적지 않는다).
 *   ② 어떤 시험을  항목 표 — 시험 종류·조건·방향·수량·받을 것.
 *   ③ 시료·기한   시료 전달, 희망일, 우선순위, **받는 부서**(측정 조직이 하나가 아니다).
 *
 * 「임시 저장」 은 작성 중(나만 봄), 「의뢰」 는 접수 대기(받는 부서 관리자에게 알림).
 * `?sample=` 또는 `?material=` 로 오면 그 자리가 채워져 있다 — 재료·시료 화면의
 * 단추가 이 주소로 보낸다.
 */

import { useEffect, useState } from 'react'
import { ArrowLeft, Search } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { commissionsApi } from '@/modules/commissions/api'
import { ItemsEditor, emptyItem, toPayload } from '@/modules/commissions/ItemsEditor'
import type { ItemDraft } from '@/modules/commissions/ItemsEditor'
import { fittingApi } from '@/modules/fitting/api'
import { materialsApi } from '@/modules/materials/api'
import type { Material, Sample } from '@/modules/materials/api'
import { testsApi } from '@/modules/tests/api'
import { workspacesApi } from '@/modules/workspaces/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { useResource } from '@/shared/hooks/useResource'

const TEXTAREA =
  'border-input bg-transparent focus-visible:ring-ring w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-1 focus-visible:outline-none'

export default function CommissionNewPage() {
  const navigate = useNavigate()
  const [asked] = useSearchParams()

  const [title, setTitle] = useState('')
  const [purpose, setPurpose] = useState('')
  const [material, setMaterial] = useState<Material | null>(null)
  const [sample, setSample] = useState<Sample | null>(null)
  const [items, setItems] = useState<ItemDraft[]>([emptyItem('tensile')])
  const [samplePlan, setSamplePlan] = useState('')
  const [dueOn, setDueOn] = useState('')
  const [priority, setPriority] = useState<'normal' | 'urgent'>('normal')
  const [lab, setLab] = useState('')
  const [busy, setBusy] = useState<'draft' | 'submit' | null>(null)
  const [error, setError] = useState<Error | null>(null)

  const testTypes = useResource(() => testsApi.types(), [])
  const blocks = useResource(() => fittingApi.blocks(), [])
  const labs = useResource(() => workspacesApi.options(), [])

  // `?material=` / `?sample=` — 재료·시료 화면에서 온 경우.
  const askedMaterial = asked.get('material')
  const askedSample = asked.get('sample')
  useEffect(() => {
    if (!askedMaterial) return
    materialsApi
      .get(askedMaterial)
      .then((found) => setMaterial(found))
      .catch(() => undefined)
  }, [askedMaterial])

  const samples = useResource(
    () => (material ? materialsApi.samples(material.id) : Promise.resolve<Sample[]>([])),
    [material?.id]
  )
  useEffect(() => {
    if (!askedSample || !samples.data) return
    const found = samples.data.find((one) => one.id === askedSample)
    if (found) setSample(found)
  }, [askedSample, samples.data])

  const ready =
    title.trim() !== '' &&
    purpose.trim() !== '' &&
    sample !== null &&
    lab !== '' &&
    items.length > 0 &&
    items.every((one) => one.test_type_key !== '')

  async function save(submit: boolean) {
    if (!sample) return
    setBusy(submit ? 'submit' : 'draft')
    setError(null)
    try {
      const made = await commissionsApi.create({
        title: title.trim(),
        purpose: purpose.trim(),
        sample_id: sample.id,
        lab_workspace_slug: lab,
        sample_plan: samplePlan.trim() || null,
        due_on: dueOn || null,
        priority,
        items: items.map((one) =>
          toPayload(
            one,
            testTypes.data?.find((type) => type.key === one.test_type_key)
          )
        ),
        submit,
      })
      navigate(`/commissions/${made.id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('의뢰를 만들지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <Link
        to="/commissions"
        className="text-muted-foreground hover:text-foreground mb-3 inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" />
        측정 의뢰 목록
      </Link>
      <PageHeader
        title="새 측정 의뢰"
        description="시료 하나에 대해 어떤 시험을 어떤 조건으로 몇 개 할지 적고, 받는 부서에 보냅니다."
      />

      <ErrorNotice error={error ?? testTypes.error ?? labs.error} className="mb-4" />

      <section className="mb-6 rounded-md border p-4">
        <h2 className="mb-3 font-medium">① 무엇을</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="commission-title">제목</Label>
            <Input
              id="commission-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="예: SECC 1.0t 인장 물성 — 성형 해석용"
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="commission-purpose">목적</Label>
            <textarea
              id="commission-purpose"
              className={TEXTAREA}
              rows={3}
              value={purpose}
              onChange={(event) => setPurpose(event.target.value)}
              placeholder="왜 필요한가 — 어느 해석·판정·비교에 쓸지. 과제를 특정하는 키는 적지 않습니다."
            />
          </div>
          <MaterialPicker
            value={material}
            onChange={(next) => {
              setMaterial(next)
              setSample(null)
            }}
          />
          <div className="space-y-1.5">
            <Label htmlFor="commission-sample">시료</Label>
            <select
              id="commission-sample"
              className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
              disabled={!material}
              value={sample?.id ?? ''}
              onChange={(event) =>
                setSample(samples.data?.find((one) => one.id === event.target.value) ?? null)
              }
            >
              <option value="">{material ? '— 시료 선택 —' : '재료를 먼저 고르세요'}</option>
              {(samples.data ?? []).map((one) => (
                <option key={one.id} value={one.id}>
                  {one.record_name}
                  {one.lot_no ? ` · ${one.lot_no}` : ''}
                </option>
              ))}
            </select>
            {material && samples.data?.length === 0 && (
              <p className="text-muted-foreground text-xs">
                이 재료에 시료가 없습니다 —{' '}
                <Link to={`/materials/${material.id}`} className="underline">
                  재료 상세
                </Link>
                에서 시료를 먼저 등록하세요.
              </p>
            )}
          </div>
        </div>
      </section>

      <section className="mb-6 rounded-md border p-4">
        <h2 className="mb-1 font-medium">② 어떤 시험을</h2>
        <p className="text-muted-foreground mb-3 text-sm">
          조건 칸은 시험 종류의 정의에서 옵니다 — 시험 등록과 같은 칸, 같은 단위.
        </p>
        <ItemsEditor
          items={items}
          onChange={setItems}
          testTypes={testTypes.data ?? []}
          blocks={blocks.data ?? []}
        />
      </section>

      <section className="mb-6 rounded-md border p-4">
        <h2 className="mb-3 font-medium">③ 시료·기한·받는 부서</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1.5 sm:col-span-3">
            <Label htmlFor="commission-plan">시료 전달</Label>
            <textarea
              id="commission-plan"
              className={TEXTAREA}
              rows={2}
              value={samplePlan}
              onChange={(event) => setSamplePlan(event.target.value)}
              placeholder="몇 개를, 어떻게, 언제 — 예: 원판 3장, 9/20 직접 전달"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="commission-due">희망 기한</Label>
            <Input
              id="commission-due"
              type="date"
              value={dueOn}
              onChange={(event) => setDueOn(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="commission-priority">우선순위</Label>
            <select
              id="commission-priority"
              className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
              value={priority}
              onChange={(event) => setPriority(event.target.value as 'normal' | 'urgent')}
            >
              <option value="normal">보통</option>
              <option value="urgent">급함</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="commission-lab">받는 부서</Label>
            <select
              id="commission-lab"
              className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
              value={lab}
              onChange={(event) => setLab(event.target.value)}
            >
              <option value="">— 받는 부서 —</option>
              {(labs.data ?? []).map((one) => (
                <option key={one.slug} value={one.slug}>
                  {one.path}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button variant="outline" disabled={busy !== null || !ready} onClick={() => save(false)}>
          임시 저장
        </Button>
        <Button disabled={busy !== null || !ready} onClick={() => save(true)}>
          의뢰
        </Button>
      </div>
    </div>
  )
}

/** 재료 찾기 — 이름·등급으로 검색해 하나 고른다. */
function MaterialPicker({
  value,
  onChange,
}: {
  value: Material | null
  onChange: (next: Material | null) => void
}) {
  const [typed, setTyped] = useState('')
  const [q, setQ] = useState('')
  const found = useResource(
    () => (q ? materialsApi.list({ q, limit: 20 }) : Promise.resolve(null)),
    [q]
  )

  return (
    <div className="space-y-1.5">
      <Label htmlFor="commission-material">재료</Label>
      {value ? (
        <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
          <span className="font-medium">{value.record_name}</span>
          <span className="text-muted-foreground">{value.grade}</span>
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            onClick={() => {
              onChange(null)
              setQ('')
              setTyped('')
            }}
          >
            다시 선택
          </Button>
        </div>
      ) : (
        <>
          <form
            className="relative"
            onSubmit={(event) => {
              event.preventDefault()
              setQ(typed.trim())
            }}
          >
            <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
            <Input
              id="commission-material"
              className="pl-8"
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              placeholder="재료 이름·등급으로 검색 후 Enter"
            />
          </form>
          {found.data && (
            <ul className="max-h-48 overflow-y-auto rounded-md border text-sm" aria-label="재료 후보">
              {found.data.items.length === 0 && (
                <li className="text-muted-foreground px-3 py-2">맞는 재료가 없습니다.</li>
              )}
              {found.data.items.map((one) => (
                <li key={one.id}>
                  <button
                    type="button"
                    className="hover:bg-muted flex w-full items-center gap-2 px-3 py-1.5 text-left"
                    onClick={() => onChange(one)}
                  >
                    <span className="font-medium">{one.record_name}</span>
                    <span className="text-muted-foreground">
                      {one.family} · {one.grade}
                    </span>
                    <span className="text-muted-foreground ml-auto tabular-nums">시료 {one.sample_count}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
