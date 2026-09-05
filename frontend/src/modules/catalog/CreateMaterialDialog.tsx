/**
 * 문헌 재료로부터 사내 재료 만들기 — **세 겹 지칭** (사용자 결정 2026-09-06).
 *
 *   grade    규격·제품급이면 카탈로그의 grade 를 그대로(짧은 이름), 서술형이면
 *            사람이 짓는다 — 이름 칸에 긴 서술을 밀어 넣으면 기준정보가 오염된다
 *   alias    카탈로그의 원본 이름 **전체**를 담는다(≤200자, 실측 최장 198) —
 *            서술형 이름으로도 검색이 닿는다
 *   연결      만들자마자 문헌 연결을 건다 — 이름을 어떻게 줄였든 원본 추적이
 *            끊기지 않고, 「카탈로그에서 채우기」 가 바로 된다
 *
 * 재료 생성은 기존 `POST /materials` 를 그대로 쓴다 — 이름 조립·기준정보 연결·
 * 유니크 검사는 서버 한 곳의 일이다(ADR 0004). 여기는 칸을 채워 줄 뿐이다.
 */

import { Loader2, FilePlus2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { CATEGORY_LABELS, catalogApi } from '@/modules/catalog/api'
import type { CatalogMaterialDetail } from '@/modules/catalog/api'
import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
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

type MaterialOut = components['schemas']['MaterialOut']

/** material_class 가 짧은 형식명(PA66-GF25)일 때만 Category 칸에 프리필한다 —
 *  자유 문장은 분류가 아니라 설명이다(서버 상한 50자도 같은 이유로 못 받는다). */
function classPrefill(materialClass: string | null): string {
  if (!materialClass) return ''
  return materialClass.length <= 50 ? materialClass : ''
}

export function CreateMaterialDialog({
  detail,
  open,
  onClose,
}: {
  detail: CatalogMaterialDetail
  open: boolean
  onClose: () => void
}) {
  const navigate = useNavigate()
  const [family, setFamily] = useState('')
  const [category, setCategory] = useState('')
  const [grade, setGrade] = useState('')
  const [details, setDetails] = useState('')
  const [alias, setAlias] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [linkFailed, setLinkFailed] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setFamily(CATEGORY_LABELS[detail.category] ?? detail.category)
    setCategory(classPrefill(detail.material_class))
    setGrade(detail.grade ?? '')
    setDetails('')
    setAlias(detail.name)
    setError(null)
    setLinkFailed(null)
  }, [open, detail])

  const ready = family.trim() !== '' && category.trim() !== '' && grade.trim() !== ''

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const material = await api.post<MaterialOut>('/materials', {
        family: family.trim(),
        category: category.trim(),
        grade: grade.trim(),
        details: details.trim() || null,
        alias: alias.trim() || null,
      })
      try {
        await catalogApi.setLink(material.id, detail.id)
      } catch {
        // 재료는 이미 생겼다 — 조용히 삼키지 않고, 연결만 못 걸었다고 말한다.
        setLinkFailed(material.id)
        setBusy(false)
        return
      }
      navigate(`/materials/${material.id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !busy && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>사내 재료로 등록</DialogTitle>
          <DialogDescription>
            이 문헌 재료를 참고해 사내 재료를 만들고, 문헌 연결까지 겁니다. 원본
            이름 전체는 별칭에 담겨 검색이 닿습니다.
          </DialogDescription>
        </DialogHeader>

        {linkFailed ? (
          <div className="space-y-3">
            <p className="text-sm">
              재료는 만들어졌지만 <b>문헌 연결을 걸지 못했습니다.</b> 재료 상세의
              「문헌 연결」 에서 다시 걸 수 있습니다.
            </p>
            <DialogFooter>
              <Button onClick={() => navigate(`/materials/${linkFailed}`)}>
                재료로 이동
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <>
            <div className="space-y-3">
              <ErrorNotice error={error} />
              <p className="text-muted-foreground text-xs">
                원본: {detail.name}
                {detail.manufacturer ? ` · ${detail.manufacturer}` : ''}
                {detail.material_class && detail.material_class.length > 50
                  ? ` · ${detail.material_class}`
                  : ''}
              </p>
              <label className="block text-sm">
                <span className="text-muted-foreground mb-1 block text-xs">Family</span>
                <Input value={family} onChange={(e) => setFamily(e.target.value)} maxLength={50} />
              </label>
              <label className="block text-sm">
                <span className="text-muted-foreground mb-1 block text-xs">Category</span>
                <Input
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  maxLength={50}
                  placeholder="예: Steel, PA66-GF25"
                />
              </label>
              <label className="block text-sm">
                <span className="text-muted-foreground mb-1 block text-xs">
                  Grade — 재료 이름의 첫 칸입니다
                </span>
                <Input
                  value={grade}
                  onChange={(e) => setGrade(e.target.value)}
                  maxLength={100}
                  placeholder="규격·제품명, 없으면 짧은 대표 이름을 짓습니다"
                />
              </label>
              <label className="block text-sm">
                <span className="text-muted-foreground mb-1 block text-xs">
                  Details (선택)
                </span>
                <Input value={details} onChange={(e) => setDetails(e.target.value)} maxLength={100} />
              </label>
              <label className="block text-sm">
                <span className="text-muted-foreground mb-1 block text-xs">
                  별칭 — 원본 이름이 담깁니다
                </span>
                <Input value={alias} onChange={(e) => setAlias(e.target.value)} maxLength={200} />
              </label>
              <p className="text-muted-foreground text-xs">
                물성값은 여기서 담지 않습니다 — 만들어진 재료의 「카탈로그에서
                채우기」 가 출처와 함께 담습니다.
              </p>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={onClose} disabled={busy}>
                취소
              </Button>
              <Button onClick={submit} disabled={!ready || busy}>
                {busy ? <Loader2 className="size-4 animate-spin" /> : <FilePlus2 className="size-4" />}
                만들고 연결
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
