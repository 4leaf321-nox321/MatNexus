/**
 * 재료 상세 — 시료와 시편.
 *
 * 계층이 화면에 그대로 보여야 한다. 재료(규격) 아래 시료(실물 한 덩이), 그 아래
 * 시편(잘라낸 조각). **방향은 시편에 있다** — 자를 때 정해지기 때문이고, 그래야
 * 같은 시료의 MD/TD/DD 를 묶어 r값·이방성 파라미터를 구할 수 있다(ADR 0004).
 */

import { useState } from 'react'
import { ChevronLeft, ChevronRight, Globe2, Layers, ListTree, Pencil, Plus } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { DeleteMaterialDialog } from '@/modules/materials/DeleteMaterialDialog'
import { materialsApi } from '@/modules/materials/api'
import { FittingPanel } from '@/modules/fitting/FittingPanel'
import { EditMaterialDialog } from '@/modules/materials/EditMaterialDialog'
import { MaterialListPanel } from '@/modules/materials/MaterialListPanel'
import { SampleExplorer } from '@/modules/materials/SampleExplorer'
import { NewSampleDialog } from '@/modules/materials/NewSampleDialog'
import { PropertiesPanel } from '@/modules/statistics/PropertiesPanel'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { DeclaredPropertiesCard } from '@/modules/materials/DeclaredPropertiesCard'
import { GroupsPanel } from '@/modules/materials/GroupsPanel'
import { PropertySourcesSheet } from '@/modules/materials/PropertySourcesSheet'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { useResource } from '@/shared/hooks/useResource'

export default function MaterialDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const material = useResource(() => materialsApi.get(id), [id])
  const samples = useResource(() => materialsApi.samples(id), [id])
  // 시료를 더하거나 지우면 수가 달라진다 — 같은 신호로 다시 읽는다.
  const summary = useResource(() => materialsApi.summary(id), [id, samples.data])
  const [addingSample, setAddingSample] = useState(false)
  const [sources, setSources] = useState(false)
  const [editing, setEditing] = useState(false)
  const [removing, setRemoving] = useState(false)

  const item = material.data

  return (
    <div>
      {/* 왼쪽 사이드바 옆에 붙는 재료 목록. **다른 재료를 보려고 뒤로 갈 필요가
          없다** — 재료를 여러 개 견주는 일이 흔하다. */}
      <MaterialListPanel currentId={id} />

      <PageHeader
        title={item?.record_name ?? '재료'}
        description={item?.alias ?? undefined}
        created={item?.created_at}
        actions={
          <div className="flex gap-2">
            {/* **돌아갈 길이 없었다.** 브라우저 뒤로 가기가 유일한 길이었는데,
                그건 화면이 준 길이 아니다 — 상세로 바로 들어온 사람(링크·북마크)
                에게는 뒤가 이 화면이 아니다. */}
            <Button variant="ghost" asChild>
              <Link to="/materials">
                <ChevronLeft className="size-4" />
                목록
              </Link>
            </Button>
            {/* **어느 탭에서든 같은 버튼이다.** 카드를 만들다 말고 화면을 옮기지
                않아도 값이 어디 있는지 볼 수 있어야 한다. */}
            <Button variant="outline" onClick={() => setSources(true)} disabled={!item}>
              <ListTree className="size-4" />
              값 출처
            </Button>
            <Button variant="outline" onClick={() => setEditing(true)} disabled={!item}>
              <Pencil className="size-4" />
              수정
            </Button>
            {/* **확인이 없었다.** 누르면 바로 지우려 들었고, 시료가 남아 있으면
                그제서야 실패 이유가 떴다 — 그리고 거기서 할 수 있는 일이 없었다.
                이제 무엇이 함께 사라지는지 먼저 보여 준다. */}
            <Button variant="outline" onClick={() => setRemoving(true)} disabled={!item}>
              삭제
            </Button>
          </div>
        }
      />

      {item && (
        <PropertySourcesSheet
          materialId={item.id}
          open={sources}
          onClose={() => setSources(false)}
        />
      )}

      <ErrorNotice error={material.error} className="mb-4" />

      {item && (
        <DeleteMaterialDialog
          materialId={item.id}
          materialName={item.record_name}
          open={removing}
          onClose={() => setRemoving(false)}
          onDeleted={() => navigate('/materials')}
        />
      )}

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
          {/* **용도는 재료의 성질이다.** 시료에 있을 때는 로트를 전부 뒤져야
              "이 재료 어디에 쓰나" 를 알 수 있었다. */}
          {/* 여러 개다 — 쉼표로 잇는다. 값 자체에 쉼표가 들어갈 일은 없다
              (기준정보를 거친 용어다). */}
          <Field label="적용 제품" value={(item.applied_products ?? []).join(', ') || '—'} />
          <Field label="적용 부위" value={(item.applied_parts ?? []).join(', ') || '—'} />
          <Field label="밀도" value={item.density == null ? '—' : `${item.density} ${item.density_unit}`} />
          <Field label="푸아송비" value={item.poisson_ratio == null ? '—' : String(item.poisson_ratio)} />
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

      {/* **계층을 한 줄로.** 시료 ▸ 시편 ▸ 시험이 아코디언 3단이라, 펼치기
          전에는 무엇이 얼마나 있는지 알 수 없었다 — 「구조가 한눈에 안 들어온다」
          가 그 말이다.

          **빠진 것을 함께 센다.** 시편을 잘라 놓고 시험을 안 한 것이 남으면
          아무도 모른다 — 그것이 다음에 할 일이고, 0 이면 그 칩이 사라진다. */}
      {summary.data && (
        <div className="text-muted-foreground mb-4 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          <span className="text-foreground font-medium">시료 {summary.data.sample_count}</span>
          <ChevronRight className="size-3.5 opacity-50" />
          <span className="text-foreground font-medium">
            시편 {summary.data.specimen_count}
          </span>
          <ChevronRight className="size-3.5 opacity-50" />
          <span className="text-foreground font-medium">시험 {summary.data.run_count}</span>
          {summary.data.specimens_without_run > 0 && (
            <Badge variant="outline" className="ml-1 text-xs">
              시험 없는 시편 {summary.data.specimens_without_run}
            </Badge>
          )}
        </div>
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

        {/* **적은 값이 잰 값 위에 온다.** 탄성계수를 적으려는 사람은 먼저
            "시험에서 나온 게 있나" 를 봐야 한다 — 두 화면에 갈라 두면 잰 값이
            있는 재료에 문헌값을 또 적는다(ADR 0016). */}
        <TabsContent value="properties" className="space-y-6">
          {item && (
            <DeclaredPropertiesCard
              level="재료"
              rows={item.declared_properties}
              onSave={async (rows) => {
                await materialsApi.update(item.id, { declared_properties: rows })
                material.reload()
              }}
            />
          )}
          {id && <PropertiesPanel materialId={id} />}
          {/* **여러 시험을 묶는 자리**(ADR 0020). 시료·시편 탭은 무엇이 있나를,
              CAE 카드 탭은 해석에 뭘 넣나를 답한다 — 그 사이가 여기다. 제 화면을
              따로 두면 묶는 자리가 둘이 되고, 그때 어느 쪽이 진짜인지 알 수 없다. */}
          {id && <GroupsPanel materialId={id} />}
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

      {/* **아코디언을 걷었다.** 시료 ▸ 시편 ▸ 시험 3단 중첩이라 열기 전에는
          무엇이 있는지 모르고, 열고 나면 세로로 길어져 견줄 수가 없었다.
          왼쪽에서 시료를 고르고 오른쪽 표에서 시편을 견준다(`SampleExplorer`). */}
      <SampleExplorer
        materialId={id}
        samples={samples.data ?? []}
        onChanged={() => samples.reload()}
      />

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
