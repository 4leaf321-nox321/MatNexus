/**
 * 재료 카탈로그 — 목록·검색·등록.
 *
 * 등록 폼에 **이름 미리보기**가 있다. 값을 넣는 동안 서버가 만들 이름을 그대로
 * 보여 주고, 이미 쓰이는 이름이면 저장 전에 알려 준다. 화면이 이름 규칙을 다시
 * 구현하지 않는 것이 핵심이다 — 기존 앱은 화면(DOM)이 ID를 만들어서 서버·배치가
 * 같은 이름을 만들 방법 자체가 없었다(ADR 0004).
 */

import { useEffect, useState } from 'react'
import { Boxes, ChevronLeft, ChevronRight, Globe2, Plus, Search } from 'lucide-react'
import { Link } from 'react-router-dom'

import { LENGTH_UNIT, materialsApi } from '@/modules/materials/api'
import type { NamePreview } from '@/modules/materials/api'
import { ApiError } from '@/shared/api/client'
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
import { useResource } from '@/shared/hooks/useResource'

/**
 * 한 번에 가져올 수 있는 수. **서버가 200 에서 자른다**(`shared/pagination.py`).
 *
 * 화면이 '전부'를 요구할 수 있으면 언젠가 `?limit=1000000` 이 나가고, 악의가
 * 없어도 그렇게 된다. 대신 **넘길 수 있게** 한다 — 137건 중 50건이라고 적어
 * 놓고 나머지를 볼 길이 없던 것이 문제였다.
 */
const PAGE_SIZES = [50, 100, 200] as const

export default function MaterialsPage() {
  const [query, setQuery] = useState('')
  const [applied, setApplied] = useState('')
  const [registering, setRegistering] = useState(false)
  const [size, setSize] = useState<number>(PAGE_SIZES[0])
  const [offset, setOffset] = useState(0)
  const materials = useResource(
    () => materialsApi.list({ q: applied, limit: size, offset }),
    [applied, size, offset]
  )

  const page = materials.data
  const rows = page?.items ?? []
  const total = page?.total ?? 0

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="재료"
        description="규격 단위로 관리합니다. 실물 한 덩이는 시료, 잘라낸 조각은 시편입니다."
        actions={
          <Button onClick={() => setRegistering(true)}>
            <Plus className="size-4" />
            재료 등록
          </Button>
        }
      />

      <form
        className="mb-4 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          setApplied(query.trim())
          // 검색은 결과 집합을 바꾼다. 3페이지에 머문 채로 좁히면 빈 화면이 뜬다.
          setOffset(0)
        }}
      >
        <div className="relative flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="이름 · 별칭 · Grade 로 찾기"
            className="pl-9"
          />
        </div>
        <Button type="submit" variant="secondary">
          찾기
        </Button>
      </form>

      <ErrorNotice error={materials.error} className="mb-4" />

      {!materials.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          <Boxes className="mx-auto mb-2 size-5 opacity-50" />
          {applied ? `'${applied}' 에 맞는 재료가 없습니다.` : '등록된 재료가 없습니다.'}
        </div>
      )}

      {rows.length > 0 && (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>이름</TableHead>
                <TableHead>별칭</TableHead>
                <TableHead>분류</TableHead>
                <TableHead className="text-right">두께</TableHead>
                <TableHead className="text-right">시료</TableHead>
                <TableHead>소속</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((material) => (
                <TableRow key={material.id}>
                  <TableCell className="font-mono text-xs">
                    <Link
                      to={`/materials/${material.id}`}
                      className="hover:text-primary hover:underline"
                    >
                      {material.record_name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {material.alias ?? '—'}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {material.family} / {material.category}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {material.spec_thickness == null
                      ? '—'
                      : `${material.spec_thickness} ${material.spec_thickness_unit}`}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {material.sample_count}
                  </TableCell>
                  <TableCell>
                    {material.is_global ? (
                      <Badge variant="outline" className="gap-1">
                        <Globe2 className="size-3" />
                        전역
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground text-sm">
                        {material.owner_workspace_name ?? '—'}
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
            <span className="text-muted-foreground tabular-nums">
              {offset + 1}–{offset + rows.length} / {total}건
            </span>

            <div className="text-muted-foreground flex items-center gap-1">
              <span>한 쪽에</span>
              {PAGE_SIZES.map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => {
                    setSize(value)
                    setOffset(0)
                  }}
                  className={`rounded px-1.5 py-0.5 tabular-nums ${
                    size === value ? 'bg-muted text-foreground font-medium' : 'hover:bg-muted/60'
                  }`}
                >
                  {value}
                </button>
              ))}
            </div>

            <div className="ml-auto flex gap-1">
              <Button
                size="sm"
                variant="outline"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - size))}
              >
                <ChevronLeft className="size-3.5" />
                이전
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={offset + rows.length >= total}
                onClick={() => setOffset(offset + size)}
              >
                다음
                <ChevronRight className="size-3.5" />
              </Button>
            </div>
          </div>
        </>
      )}

      <RegisterDialog
        open={registering}
        onClose={() => setRegistering(false)}
        onDone={() => {
          setRegistering(false)
          materials.reload()
        }}
      />
    </div>
  )
}

const EMPTY = {
  family: 'Metal',
  category: 'Steel',
  grade: '',
  details: '',
  spec_thickness: '',
  alias: '',
}

function RegisterDialog({
  open,
  onClose,
  onDone,
}: {
  open: boolean
  onClose: () => void
  onDone: () => void
}) {
  const [form, setForm] = useState(EMPTY)
  const [preview, setPreview] = useState<NamePreview | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [saving, setSaving] = useState(false)

  const thickness = form.spec_thickness === '' ? null : Number(form.spec_thickness)

  // 입력하는 동안 서버에 이름을 물어본다. 잠깐 기다렸다 보내는 이유는, 글자마다
  // 요청하면 목록 화면 하나가 서버를 두드리는 꼴이 되기 때문이다.
  useEffect(() => {
    if (!open) return
    const timer = setTimeout(() => {
      materialsApi
        .previewName({
          grade: form.grade || null,
          details: form.details || null,
          spec_thickness: thickness,
          spec_thickness_unit: LENGTH_UNIT,
        })
        .then(setPreview)
        .catch(() => setPreview(null))
    }, 250)
    return () => clearTimeout(timer)
  }, [open, form.grade, form.details, thickness])

  useEffect(() => {
    if (open) {
      setForm(EMPTY)
      setPreview(null)
      setError(null)
    }
  }, [open])

  async function submit() {
    setSaving(true)
    setError(null)
    try {
      await materialsApi.create({
        family: form.family,
        category: form.category,
        grade: form.grade,
        details: form.details || null,
        spec_thickness: thickness,
        spec_thickness_unit: LENGTH_UNIT,
        alias: form.alias || null,
      })
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('등록에 실패했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  const field = (key: keyof typeof EMPTY) => ({
    value: form[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value })),
  })

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>재료 등록</DialogTitle>
          <DialogDescription>
            이름은 입력한 값에서 자동으로 만들어집니다. 부르기 쉬운 이름은 별칭에 넣으세요.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="family">Family</Label>
            <Input id="family" placeholder="Metal" {...field('family')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="category">Category</Label>
            <Input id="category" placeholder="Steel" {...field('category')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="grade">Grade</Label>
            <Input id="grade" placeholder="SECC" {...field('grade')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="details">Details</Label>
            <Input id="details" placeholder="MDOI (같은 규격 구분용)" {...field('details')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="thickness">스펙 두께 (mm)</Label>
            <Input id="thickness" type="number" step="0.01" placeholder="1.0" {...field('spec_thickness')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="alias">별칭 (선택)</Label>
            <Input id="alias" placeholder="도어 이너 강판" {...field('alias')} />
          </div>
        </div>

        <div className="bg-muted/40 rounded-md border p-3">
          <p className="text-muted-foreground mb-1 text-xs">이름 (자동)</p>
          <p className="font-mono text-sm">{preview?.record_name ?? '—'}</p>
          {preview?.taken && (
            <p className="text-destructive mt-1 text-xs">
              같은 이름의 재료가 이미 있습니다. Details 로 구분하세요.
            </p>
          )}
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            취소
          </Button>
          <Button onClick={submit} disabled={saving || !form.grade || preview?.taken}>
            등록
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
