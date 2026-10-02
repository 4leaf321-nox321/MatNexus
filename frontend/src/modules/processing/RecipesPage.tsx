/**
 * 처리 레시피 목록 — **저장한 것을 볼 수 있어야 한다.**
 *
 * 레시피를 만드는 자리는 시험 상세의 처리 탭이고, 쓰는 자리는 목록의 배치
 * 적용이다. 그런데 **저장한 것을 보는 자리가 없었다** — 배치 다이얼로그의
 * 드롭다운이 유일했고, 거기서는 어떤 단계로 이뤄졌는지도, 누구 것인지도,
 * 지우는 방법도 없었다. 만들 수만 있고 관리할 수 없는 자산이 쌓이면 목록이
 * 금방 쓰레기가 된다(형식 프로파일에서 같은 판단을 했다).
 *
 * **단계 편집은 여기서 하지 않는다.** 단계를 고치려면 곡선을 보면서 돌려 봐야
 * 하고, 그건 처리 탭의 일이다. 여기서는 무엇이 있는지 보고, 이름을 고치고,
 * 지운다.
 *
 * 「이름을 고치고」 는 이 설명에만 있고 단추가 없었다 — 서버의 고치기(PUT)와
 * `updateRecipe` 는 있는데 부르는 화면이 없어, 이름을 바꾸려면 새로 저장하고 옛것을
 * 지우는 수밖에 없었다(2026-10-03 사용자 질문으로 드러났다).
 */

import { useState } from 'react'
import { FlaskConical, Pencil, Trash2, Users } from 'lucide-react'

import { processingApi } from '@/modules/processing/api'
import type { Recipe, RecipeStep } from '@/modules/processing/api'
import { OwnershipDialog } from '@/modules/ownership/OwnershipDialog'
import { canEdit, lockedTitle } from '@/modules/ownership/access'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { ownerOf, TestTypeFilterPanel } from '@/modules/tests/TestTypeFilterPanel'
import { Textarea } from '@/shared/components/ui/textarea'
import { useResource } from '@/shared/hooks/useResource'

export default function RecipesPage() {
  const recipes = useResource(() => processingApi.recipes(), [])
  const [error, setError] = useState<Error | null>(null)
  /** 「권한」 을 연 레시피 — 등록자·편집 부서를 보고 넘긴다(ADR 0035 3단계). */
  const [handing, setHanding] = useState<Recipe | null>(null)
  /** 이름을 고치는 레시피. */
  const [renaming, setRenaming] = useState<Recipe | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  // `null` 이면 전체. **인장 레시피를 손보는 사람에게 DMA 레시피는 소음이다.**
  const [kind, setKind] = useState<string | null>(null)
  // 부서 축. 켜지 않으면 늘 `null` 이다(패널이 끄면서 풀어 준다).
  const [owner, setOwner] = useState<string | null>(null)
  const all = recipes.data ?? []
  // **두 축이 함께 걸린다**(AND). 「인장 + 우리 부서」가 실제로 찾는 것이고,
  // 하나만 고르게 하면 절반은 여전히 눈으로 훑어야 한다.
  const rows = all.filter(
    (item) =>
      (kind === null || item.test_type_key === kind) &&
      (owner === null || ownerOf(item) === owner)
  )

  async function remove(item: Recipe) {
    setError(null)
    try {
      await processingApi.removeRecipe(item.key)
      recipes.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    }
  }

  return (
    <div>
      {/* 시험 종류로 거른다. **표에 종류를 보여만 주고 거르지는 못했다** —
          다른 종류의 것을 눈으로 훑어 넘겨야 했다. */}
      <TestTypeFilterPanel
        label="레시피 종류"
        rows={all}
        current={kind}
        onPick={setKind}
        owner={owner}
        onPickOwner={setOwner}
        ownerKey="recipes"
      />

      <PageHeader
        title="처리 레시피"
        description="변위·하중을 물성으로 바꾸는 단계 묶음. 시험 하나에서 맞춘 뒤 나머지에 한 번에 겁니다."
      />

      <ErrorNotice error={recipes.error ?? error} className="mb-4" />

      {/* **걸러서 0건인 것과 하나도 없는 것은 다르다.** 「저장된 레시피가
          없습니다」라고 하면 거짓말이고, 사람은 만들러 갔다가 이미 있는 것을
          또 만든다. */}
      {!recipes.loading && rows.length === 0 && (kind !== null || owner !== null) ? (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          거른 조건에 맞는 레시피가 없습니다.
          <p className="mx-auto mt-2 max-w-md text-xs">
            왼쪽에서 <b>전체</b> 를 누르면 나머지를 볼 수 있습니다.
          </p>
        </div>
      ) : !recipes.loading && rows.length === 0 ? (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          <FlaskConical className="mx-auto mb-2 size-5 opacity-50" />
          저장된 레시피가 없습니다.
          <p className="mx-auto mt-2 max-w-md text-xs">
            시험 하나를 열어 <b>처리</b> 탭에서 단계를 맞추고 <b>레시피로 저장</b>을
            누르세요. 곡선을 보면서 맞춰야 하므로 만드는 자리가 거기입니다.
          </p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>이름</TableHead>
              <TableHead>등록 부서</TableHead>
              <TableHead>시험 종류</TableHead>
              <TableHead>단계</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((item) => (
              <TableRow key={item.key}>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{item.label}</span>
                    {!item.is_active && <Badge variant="destructive">중단</Badge>}
                  </div>
                  <span className="text-muted-foreground font-mono text-xs">{item.key}</span>
                  {item.description && (
                    <p className="text-muted-foreground mt-0.5 text-xs">{item.description}</p>
                  )}
                  {/* 누가 고치나 — 레시피는 부서의 규격이라 등록자가 부서에 편집을 준다. */}
                  {item.access && (
                    <p className="text-muted-foreground mt-0.5 text-xs">
                      등록자 {item.access.registrant ?? '없음'} · 편집 부서{' '}
                      {item.access.edit_workspace ?? '없음'}
                    </p>
                  )}
                </TableCell>
                <TableCell>{item.owner_workspace_name ?? '부서 없음'}</TableCell>
                <TableCell>{item.test_type_label}</TableCell>
                <TableCell>
                  <button
                    type="button"
                    className="text-muted-foreground text-xs underline-offset-2 hover:underline"
                    onClick={() => setOpen(open === item.key ? null : item.key)}
                  >
                    {item.steps.length}단계 {open === item.key ? '접기' : '보기'}
                  </button>
                  {open === item.key && (
                    <ol className="text-muted-foreground mt-1 space-y-0.5 text-xs">
                      {(item.steps as unknown as RecipeStep[]).map((step, index) => (
                        <li key={`${step.plugin}-${index}`} className="font-mono">
                          {index + 1}. {step.plugin}
                        </li>
                      ))}
                    </ol>
                  )}
                </TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  {/* **보는 것은 누구나, 지우는 것은 고칠 수 있는 사람**(ADR 0035). 레시피는
                      「이 시험을 어떻게 처리했나」 의 답이라 누구나 봐야 한다. 못 지우면
                      단추를 막고 누구에게 물을지 단다 — 눌러 보고 403 을 알게 하지 않는다. */}
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label="이름 고치기"
                    disabled={!canEdit(item.access)}
                    title={lockedTitle(item.access) ?? '이름 · 설명을 고칩니다. 단계는 그대로입니다.'}
                    onClick={() => setRenaming(item)}
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    title="권한 — 등록자와 편집 부서"
                    onClick={() => setHanding(item)}
                  >
                    <Users className="size-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={!canEdit(item.access)}
                    title={
                      lockedTitle(item.access) ??
                      '지웁니다. 이 레시피로 만든 결과는 그대로 남습니다.'
                    }
                    onClick={() => remove(item)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {renaming && (
        <RenameRecipeDialog
          recipe={renaming}
          onClose={() => setRenaming(null)}
          onSaved={() => {
            setRenaming(null)
            recipes.reload()
          }}
        />
      )}

      {handing && (
        <OwnershipDialog
          kind="recipe"
          id={handing.id}
          onClose={() => setHanding(null)}
          onChanged={() => recipes.reload()}
        />
      )}

      <p className="text-muted-foreground mt-4 text-xs">
        레시피를 고치거나 지워도 <b>이미 저장된 결과는 바뀌지 않습니다.</b> 결과는
        그때의 단계를 통째로 갖고 있습니다(ADR 0007) — 어제 뽑은 항복강도가 무엇으로
        나온 값인지가 레시피를 고쳤다고 사라지면 안 됩니다.
      </p>
    </div>
  )
}

/**
 * 이름 · 설명만 고친다 — **나머지는 열었을 때 받은 그대로 돌려보낸다.**
 *
 * 서버의 고치기(PUT)는 레시피를 통째로 받는다. 단계 · 시험 종류 · 켜짐을 받은 그대로
 * 보내고, `revision` 도 그때 것을 보낸다 — 그사이 다른 사람이 고쳤으면 서버가 409 로
 * 막는다(ADR 0015). 안 막으면 이름을 고친 사람이 남이 고친 것을 옛것으로 되돌린다.
 */
function RenameRecipeDialog({
  recipe,
  onClose,
  onSaved,
}: {
  recipe: Recipe
  onClose: () => void
  onSaved: () => void
}) {
  const [label, setLabel] = useState(recipe.label)
  const [description, setDescription] = useState(recipe.description ?? '')
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)
  const unchanged =
    label.trim() === recipe.label && (description.trim() || null) === (recipe.description || null)

  async function save() {
    setBusy(true)
    setError(null)
    try {
      await processingApi.updateRecipe(recipe.key, {
        label: label.trim(),
        // 비우면 지운다 — 빈 글자를 설명으로 남기지 않는다.
        description: description.trim() || null,
        test_type_key: recipe.test_type_key,
        steps: recipe.steps,
        is_active: recipe.is_active,
        expected_revision: recipe.revision,
      })
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('고치지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>레시피 이름 고치기</DialogTitle>
          <DialogDescription>
            단계는 그대로입니다. 이 레시피로 이미 만든 결과는 그때의 이름을 그대로 갖습니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={error} />

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="recipe-rename-label">이름</Label>
            <Input
              id="recipe-rename-label"
              value={label}
              maxLength={120}
              onChange={(event) => setLabel(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="recipe-rename-description">설명</Label>
            <Textarea
              id="recipe-rename-description"
              value={description}
              rows={3}
              placeholder="무엇에 쓰는 레시피인지 — 비워도 됩니다"
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button onClick={save} disabled={busy || !label.trim() || unchanged}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
