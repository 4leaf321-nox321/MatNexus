/**
 * 새 측정 의뢰 — 한 화면 세 묶음.
 *
 *   ① 무엇을   **등록된 시료**를 고르거나, **아직 등록 안 된 새 재료**를 글로 적는다.
 *              새 재료면 받는 부서가 재료·시료를 등록한 뒤 의뢰에 잇는다(2026-09-14).
 *              목적은 자유 글(과제를 특정하는 키는 적지 않는다).
 *   ② 어떤 시험을  항목 표 — 시험 종류·조건·방향·수량·받을 것. 종류를 모르면 물성 이름만.
 *   ③ 시료·기한   시료 전달, 희망일, 우선순위, **받는 부서**(측정 조직이 하나가 아니다).
 *
 * 「임시 저장」 은 작성 중(나만 봄), 「의뢰」 는 접수 대기(받는 부서 관리자에게 알림).
 * `?sample=` 또는 `?material=` 로 오면 그 자리가 채워져 있다 — 재료·시료 화면의
 * 단추가 이 주소로 보낸다.
 */

import { useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { commissionsApi } from '@/modules/commissions/api'
import { ItemsEditor, emptyItem, itemReady, toPayload } from '@/modules/commissions/ItemsEditor'
import type { ItemDraft } from '@/modules/commissions/ItemsEditor'
import { SamplePicker } from '@/modules/commissions/SamplePicker'
import { fittingApi } from '@/modules/fitting/api'
import type { Sample } from '@/modules/materials/api'
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

type Target = 'sample' | 'new'

export default function CommissionNewPage() {
  const navigate = useNavigate()
  const [asked] = useSearchParams()

  const [title, setTitle] = useState('')
  const [purpose, setPurpose] = useState('')
  const [target, setTarget] = useState<Target>('sample')
  const [sample, setSample] = useState<Sample | null>(null)
  const [materialHint, setMaterialHint] = useState('')
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

  const targetReady = target === 'sample' ? sample !== null : materialHint.trim() !== ''
  const ready =
    title.trim() !== '' &&
    purpose.trim() !== '' &&
    targetReady &&
    lab !== '' &&
    items.length > 0 &&
    items.every(itemReady)

  async function save(submit: boolean) {
    setBusy(submit ? 'submit' : 'draft')
    setError(null)
    try {
      const made = await commissionsApi.create({
        title: title.trim(),
        purpose: purpose.trim(),
        sample_id: target === 'sample' ? (sample?.id ?? null) : null,
        material_hint: target === 'new' ? materialHint.trim() : null,
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
        description="시료(또는 새 재료)에 대해 어떤 시험을 어떤 조건으로 몇 개 할지 적고, 받는 부서에 보냅니다."
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

          {/* **등록된 시료인가, 새 재료인가.** 새 재료는 아직 재료 목록에 없어 고를 수 없다 —
              무엇인지 글로 적고, 받는 부서가 등록한 뒤 의뢰에 잇는다. */}
          <div className="flex flex-wrap gap-4 text-sm sm:col-span-2" role="radiogroup" aria-label="대상">
            <label className="flex items-center gap-1.5">
              <input
                type="radio"
                name="commission-target"
                checked={target === 'sample'}
                onChange={() => setTarget('sample')}
              />
              등록된 시료
            </label>
            <label className="flex items-center gap-1.5">
              <input
                type="radio"
                name="commission-target"
                checked={target === 'new'}
                onChange={() => setTarget('new')}
              />
              새 재료 (아직 등록 전)
            </label>
          </div>

          {target === 'sample' ? (
            <SamplePicker
              sample={sample}
              onChange={setSample}
              presetMaterialId={asked.get('material')}
              presetSampleId={asked.get('sample')}
            />
          ) : (
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="commission-material-hint">새 재료 — 무엇인지</Label>
              <textarea
                id="commission-material-hint"
                className={TEXTAREA}
                rows={3}
                value={materialHint}
                onChange={(event) => setMaterialHint(event.target.value)}
                placeholder="이름·등급·업체·두께 — 예: SGARC440 1.2t, 포스코, 신규 강종 후보. 받는 부서가 재료·시료를 등록한 뒤 이 의뢰에 잇습니다."
              />
            </div>
          )}
        </div>
      </section>

      <section className="mb-6 rounded-md border p-4">
        <h2 className="mb-1 font-medium">② 어떤 시험을</h2>
        <p className="text-muted-foreground mb-3 text-sm">
          조건 칸은 시험 종류의 정의에서 옵니다 — 시험 등록과 같은 칸, 같은 단위. 종류를 모르면
          「미정」 으로 두고 무엇을 잴지(물성 이름)만 적으세요 — 받는 부서가 종류를 정합니다.
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
