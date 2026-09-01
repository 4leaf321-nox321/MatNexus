/**
 * 재료 상세 — 시료와 시편.
 *
 * 계층이 화면에 그대로 보여야 한다. 재료(규격) 아래 시료(실물 한 덩이), 그 아래
 * 시편(잘라낸 조각). **방향은 시편에 있다** — 자를 때 정해지기 때문이고, 그래야
 * 같은 시료의 MD/TD/DD 를 묶어 r값·이방성 파라미터를 구할 수 있다(ADR 0004).
 */

import { useState } from 'react'
import { ChevronLeft, ChevronRight, Globe2, ListTree, Pencil, Plus } from 'lucide-react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

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
import { tabOf } from '@/modules/materials/tabs'
import { MasterCurveNotice } from '@/modules/materials/MasterCurveNotice'
import { groupsApi } from '@/modules/materials/api.groups'
import { PropertySourcesSheet } from '@/modules/materials/PropertySourcesSheet'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { useResource } from '@/shared/hooks/useResource'
import { RecordName } from '@/shared/components/RecordName'

export default function MaterialDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const material = useResource(() => materialsApi.get(id), [id])
  /** 지금 켠 탭. **안내가 눌러서 데려간다** — 「그 시험 보기」 가 말만 하고 사람이
   *  탭을 다시 찾아야 하면 그 안내는 절반만 한 것이다. */
  // **탭을 주소에 담는다.** 「그 재료의 CAE 카드로」 같은 안내가 링크로 보내는데
  // 탭이 주소에 없으면 늘 첫 탭이 열리고, 사람은 안내가 말한 자리를 스스로 찾아야
  // 한다 — 그러면 그 안내는 없느니만 못하다.
  const [params, setParams] = useSearchParams()
  const asked = params.get('tab')
  const tab = tabOf(asked)
  const setTab = (next: string) => {
    // 되돌아가기로 탭을 되짚는 것은 자연스럽다 — 히스토리에 쌓는다.
    const copy = new URLSearchParams(params)
    copy.set('tab', next)
    setParams(copy)
  }

  const samples = useResource(() => materialsApi.samples(id), [id])
  // 시료를 더하거나 지우면 수가 달라진다 — 같은 신호로 다시 읽는다.
  const summary = useResource(() => materialsApi.summary(id), [id, samples.data])
  const [addingSample, setAddingSample] = useState(false)
  const [sources, setSources] = useState(false)
  const [editing, setEditing] = useState(false)
  // 물성 요약의 편집 단추가 이 창을 연다 — 값 목록이 그쪽에 있다.
  const [editingDeclared, setEditingDeclared] = useState<string | null>(null)
  // **묶음 결과는 물성이다.** 물성 표가 그것을 다른 값과 나란히 보이려면 여기서
  // 가져와 넘겨야 한다 — `statistics` 는 묶음 API 를 직접 부르지 않는다(모듈 경계).
  const groupRows = useResource(() => (id ? groupsApi.ofMaterial(id) : Promise.resolve([])), [id])
  const groupKinds = useResource(() => groupsApi.kinds(), [])
  const [removing, setRemoving] = useState(false)

  const item = material.data

  return (
    // **화면 높이를 채운다**(`AppShell.FULL_HEIGHT`). 스크롤은 탭 안쪽에서만
    // 일어나므로, 머리글과 탭 줄은 늘 제자리에 있다.
    <div className="flex h-full min-h-0 flex-col">
      {/* 왼쪽 사이드바 옆에 붙는 재료 목록. **다른 재료를 보려고 뒤로 갈 필요가
          없다** — 재료를 여러 개 견주는 일이 흔하다. */}
      <MaterialListPanel currentId={id} />

      <PageHeader
        title={item ? <RecordName name={item.record_name} /> : '재료'}
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

      {/* **열 수를 폭에 맞춘다.** 4열 고정이라 전체 폭을 쓰게 된 뒤로 한 칸이
          500px 을 넘었다 — 값은 `Metal`·`1.2 mm` 처럼 짧은데 그 뒤가 전부
          빈칸이라, 라벨과 값이 멀어져 어느 라벨의 값인지 눈으로 이어야 했다.
          한 칸이 250px 안팎이 되도록 늘린다. */}
      {item && (
        <div className="mb-4 grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 rounded-md border p-4 text-sm sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
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

        {/* **용도는 성격이 다르다.** 위쪽은 「이 재료가 무엇인가」(분류·치수·물성)
            이고 여기는 「어디에 쓰나」 다 — 물어보는 사람도 다르고, 값이 여럿이라
            한 칸에 넣으면 줄바꿈으로 옆 칸의 짝을 밀어낸다.

            **재료의 성질이다.** 시료에 있을 때는 로트를 전부 뒤져야 「이 재료
            어디에 쓰나」 를 알 수 있었다. */}
        <dl className="space-y-3 rounded-md border p-4 text-sm">
          <Field label="적용 제품" value={<Uses items={item.applied_products} />} />
          <Field label="적용 파트" value={<Uses items={item.applied_parts} />} />
        </dl>
        </div>
      )}

      {/* **재료 화면이 답해야 하는 질문이 둘이다** — "무엇이 있나(시료·시편)" 와
          "이 재료의 물성은 얼마인가". 세로로 이어 붙이면 시료가 늘수록 물성이
          아래로 밀려나는데, 물성이 이 화면의 결론이다. */}
      <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
        {/* **탭 셋이 서로 다른 질문에 답한다** — 무엇이 있나 / 물성이 얼마인가 /
            해석에 뭘 넣나. 한때 '시험' 탭을 따로 뒀는데, 시편 줄이 접히고 그
            줄에 시험 수·채택·실패가 붙으면서 답하던 것이 겹쳤다. 같은 것을 두
            자리에 두면 어느 쪽이 진짜인지 알 수 없게 된다. */}
        {/* **개수는 탭과 같은 줄에 둔다.** 한 줄을 통째로 차지할 만큼 큰
            정보가 아니고, 위에 두면 탭이 그만큼 아래로 밀려 첫 화면에서 물성이
            더 늦게 나온다. */}
        <div className="mb-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <TabsList>
            <TabsTrigger value="samples">시료·시편</TabsTrigger>
            <TabsTrigger value="properties">물성</TabsTrigger>
            <TabsTrigger value="cards">CAE 카드</TabsTrigger>
          </TabsList>
      {/* **계층을 한 줄로.** 시료 ▸ 시편 ▸ 시험이 아코디언 3단이라, 펼치기
          전에는 무엇이 얼마나 있는지 알 수 없었다 — 「구조가 한눈에 안 들어온다」
          가 그 말이다.

          **빠진 것을 함께 센다.** 시편을 잘라 놓고 시험을 안 한 것이 남으면
          아무도 모른다 — 그것이 다음에 할 일이고, 0 이면 그 칩이 사라진다. */}
      {summary.data && (
        <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
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
        </div>

        {/* **적은 값이 잰 값 위에 온다.** 탄성계수를 적으려는 사람은 먼저
            "시험에서 나온 게 있나" 를 봐야 한다 — 두 화면에 갈라 두면 잰 값이
            있는 재료에 문헌값을 또 적는다(ADR 0016). */}
        {/* **적은 값과 잰 값을 좌우로 둔다** (2026-08-30).
            셋이 세로로 쌓여 있어서, 「문헌값이 뭐였더라」 를 보려면 잰 값을 지나
            스크롤해 올라가야 했다 — 그런데 그 둘을 견주는 것이 이 탭의 일이다.
            폭은 1:2 다. 선언 물성은 항목이 몇 개뿐이고, 잰 값 쪽은 방향마다 표와
            곡선과 분포를 든다. */}
        {/* **왼쪽은 결론, 오른쪽은 근거다** (2026-08-30).
            좌우를 `PropertiesPanel` 이 스스로 나눈다 — 통계를 한 번만 가져오고
            배치도 한 곳에서 정한다.

            묶음은 **결과와 만들기가 갈린다.** 결과(Prony 계수)는 물성이라 왼쪽
            표에 `[묶음]` 배지로 서고, 만들기는 그 시험종류의 상세 안으로 간다 —
            묶을 방법이 없는 종류에서는 아예 안 뜬다. */}
        <TabsContent value="properties" className="mt-2 min-h-0 flex-1">
          {id && (
            <PropertiesPanel
              materialId={id}
              declared={item?.declared_properties}
              onEditDeclared={setEditingDeclared}
              groupResults={groupRows.data ?? []}
              groupKinds={groupKinds.data ?? []}
              groupSlot={<GroupsPanel materialId={id} list={false} />}
              notice={
                <MasterCurveNotice materialId={id} onGoToTests={() => setTab('samples')} />
              }
              header={
                item && (
                  <DeclaredPropertiesCard
                    level="재료"
                    list={false}
                    openItem={editingDeclared}
                    onOpenChange={setEditingDeclared}
                    rows={item.declared_properties}
                    onSave={async (rows) => {
                      await materialsApi.update(item.id, { declared_properties: rows })
                      material.reload()
                    }}
                  />
                )
              }
            />
          )}
        </TabsContent>

        {/* 물성 탭이 "이 재료가 이렇게 거동한다" 를 데이터로 보인다면, 여기는
            그 거동을 솔버가 읽는 모양으로 굳힌다. 옆 탭인 이유는 입력이 옆
            탭의 대표 곡선이기 때문이다. */}
        <TabsContent value="cards" className="mt-2 min-h-0 flex-1 overflow-y-auto pr-2">
          {id && <FittingPanel materialId={id} />}
        </TabsContent>

        <TabsContent value="samples" className="mt-2 min-h-0 flex-1 overflow-y-auto pr-2">
      {/* **층 이름만으로는 무엇인지 알 수 없다.** 실제로 "시료와 시편과 시험이
          각각 뭐냐" 는 질문이 나왔다. 나눠 둔 이유가 층마다 거기에만 붙는 것이
          있기 때문이므로, 그 붙는 것을 한 줄에 적는다(ADR 0004). */}
      <p className="text-muted-foreground mb-3 rounded-md border border-dashed p-2.5 text-xs">
        <b>시료</b>는 입고된 실물 한 덩이(코일·판 하나)입니다 — 제조사·생산일·로트가
        여기 붙습니다. <b>시편</b>은 거기서 잘라낸 조각이고, <b>방향과 실측 치수</b>가
        여기 있습니다 — 하중을 응력으로 바꾸는 단면적이 그 값입니다.
      </p>

      <ErrorNotice error={samples.error} className="mb-4" />

      {/* **시료 추가는 시료 목록 머리로 옮겼다**(2026-08-30). 여기 있을 때는
          그 단추가 화면 전체의 것처럼 보여, 시편·시험을 더하는 단추와 층이
          달라 보이지 않았다. 다만 **시료가 하나도 없으면 탐색기가 안 그려지므로**
          그때는 여기서 더한다 — 첫 시료를 못 만들면 아무것도 시작이 안 된다. */}
      {!samples.loading && (samples.data ?? []).length === 0 && (
        <div className="text-muted-foreground rounded-md border py-10 text-center text-sm">
          <p className="mb-3">시료가 없습니다. 시험을 등록하려면 시료와 시편이 먼저 있어야 합니다.</p>
          <Button size="sm" variant="secondary" onClick={() => setAddingSample(true)}>
            <Plus className="size-4" />
            시료 추가
          </Button>
        </div>
      )}

      {/* **아코디언을 걷었다.** 시료 ▸ 시편 ▸ 시험 3단 중첩이라 열기 전에는
          무엇이 있는지 모르고, 열고 나면 세로로 길어져 견줄 수가 없었다.
          왼쪽에서 시료를 고르고 오른쪽 표에서 시편을 견준다(`SampleExplorer`). */}
      <SampleExplorer
        materialId={id}
        samples={samples.data ?? []}
        onChanged={() => samples.reload()}
        onAddSample={() => setAddingSample(true)}
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

/**
 * 용도 목록.
 *
 * **쉼표로 이으면 어디까지가 한 항목인지 안 보인다.** 「이너 패널, 아우터 패널,
 * 리인포스먼트…」 가 열 개쯤 이어지면 눈이 쉼표를 세게 되고, 값 자체에 띄어쓰기가
 * 있어서 더 그렇다 — 배지는 그 경계를 자리로 말한다.
 */
export function Uses({ items }: { items?: string[] | null }) {
  const rows = items ?? []
  if (rows.length === 0) return <span className="text-muted-foreground">—</span>
  return (
    <span className="flex flex-wrap gap-1">
      {rows.map((one) => (
        <Badge key={one} variant="secondary" className="font-normal">
          {one}
        </Badge>
      ))}
    </span>
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
