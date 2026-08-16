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
 */

import { useState } from 'react'
import { FlaskConical, Globe2, Trash2 } from 'lucide-react'

import { processingApi } from '@/modules/processing/api'
import type { Recipe, RecipeStep } from '@/modules/processing/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

export default function RecipesPage() {
  const recipes = useResource(() => processingApi.recipes(), [])
  const [error, setError] = useState<Error | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const rows = recipes.data ?? []

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
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="처리 레시피"
        description="변위·하중을 물성으로 바꾸는 단계 묶음. 시험 하나에서 맞춘 뒤 나머지에 한 번에 겁니다."
      />

      <ErrorNotice error={recipes.error ?? error} className="mb-4" />

      {!recipes.loading && rows.length === 0 ? (
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
              <TableHead>누구 것</TableHead>
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
                </TableCell>
                <TableCell className="text-sm">
                  {item.is_global ? (
                    <Badge variant="outline" className="gap-1">
                      <Globe2 className="size-3" />
                      전역
                    </Badge>
                  ) : (
                    <span className="text-muted-foreground text-xs">
                      {item.owner_workspace_name}
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-sm">{item.test_type_label}</TableCell>
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
                <TableCell className="text-right">
                  <Button
                    size="sm"
                    variant="ghost"
                    title="지웁니다. 이 레시피로 만든 결과는 그대로 남습니다."
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

      <p className="text-muted-foreground mt-4 text-xs">
        레시피를 고치거나 지워도 <b>이미 저장된 결과는 바뀌지 않습니다.</b> 결과는
        그때의 단계를 통째로 갖고 있습니다(ADR 0007) — 어제 뽑은 항복강도가 무엇으로
        나온 값인지가 레시피를 고쳤다고 사라지면 안 됩니다.
      </p>
    </div>
  )
}
