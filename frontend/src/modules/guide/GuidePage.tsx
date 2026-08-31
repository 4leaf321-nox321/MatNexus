/**
 * 물성 핸드북 — **찾기 쉽고, 누구나 고치고, 검토자가 승인한다.**
 *
 * ## 세 단
 *
 *     왼쪽   목차 — 종류(무엇을 하려고 왔나) › 문서 › 절
 *     가운데 절 본문. 「편집」 을 누르면 그 자리가 편집기가 된다
 *     오른쪽 절 안 목차 · 판 정보 · 검토 대기
 *
 * ## 편집은 초안이다
 *
 * 저장하면 **초안**이 되어 검토자에게 간다. 검토자는 자기 것을 바로 낸다. 검토
 * 없이 본문이 바뀌는 길은 없다 — 화면이 그것을 숨기지 않고 말한다(「초안으로
 * 보냈습니다」).
 */

import { ChevronRight, FileCode2, Pencil, Search, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { EMPTY_DOC, KINDS, guideApi } from '@/modules/guide/api'
import type { Doc, GuideDocument, Revision, SearchHit, Section } from '@/modules/guide/api'
import { GuideEditor } from '@/modules/guide/GuideEditor'
import { useAuth } from '@/shared/auth/AuthContext'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { useResource } from '@/shared/hooks/useResource'
import { stamp } from '@/shared/lib/datetime'

/** 절 안의 제목들 — 오른쪽 목차. 서버가 아니라 여기서 뽑는다(본문이 이미 있다). */
export function headingsOf(doc: Doc): { level: number; text: string }[] {
  const content = (doc.content as Array<Record<string, unknown>> | undefined) ?? []
  return content
    .filter((node) => node.type === 'heading')
    .map((node) => ({
      level: Number((node.attrs as { level?: number } | undefined)?.level ?? 2),
      text: ((node.content as Array<{ text?: string }> | undefined) ?? [])
        .map((leaf) => leaf.text ?? '')
        .join(''),
    }))
}

export default function GuidePage() {
  const { documentKey, sectionKey } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const docs = useResource(() => guideApi.documents(), [])
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<SearchHit[] | null>(null)

  // 검색 — 두 글자부터, 타이핑이 멎으면.
  useEffect(() => {
    const needle = query.trim()
    if (needle.length < 2) {
      setHits(null)
      return
    }
    let cancelled = false
    const timer = setTimeout(() => {
      guideApi
        .search(needle)
        .then((found) => {
          if (!cancelled) setHits(found)
        })
        .catch(() => {
          if (!cancelled) setHits([])
        })
    }, 250)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query])

  const current = useMemo(() => {
    const document = docs.data?.find((d) => d.key === documentKey)
    const section = document?.sections.find((s) => s.key === sectionKey)
    return { document, section }
  }, [docs.data, documentKey, sectionKey])

  const isReviewer = Boolean(user?.is_system_admin || user?.memberships.some((m) => m.role === 'manager'))

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
      <aside className="w-full shrink-0 lg:w-64">
        <div className="relative mb-3">
          <Search className="text-muted-foreground absolute top-2.5 left-2 size-4" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="핸드북에서 찾기"
            aria-label="핸드북에서 찾기"
            className="pl-8"
          />
        </div>
        <ErrorNotice error={docs.error} />
        {hits !== null ? (
          <SearchResults hits={hits} onPick={() => setQuery('')} />
        ) : (
          <TableOfContents
            documents={docs.data ?? []}
            documentKey={documentKey}
            sectionKey={sectionKey}
          />
        )}
      </aside>

      <main className="min-w-0 flex-1">
        {!current.section && <Landing documents={docs.data ?? []} />}
        {current.document && current.section && (
          <SectionView
            key={current.section.id}
            document={current.document}
            sectionId={current.section.id}
            isReviewer={isReviewer}
            onSaved={() => docs.reload()}
            onMove={(key) => navigate(`/guide/${current.document?.key}/${key}`)}
          />
        )}
      </main>
    </div>
  )
}

// --- 목차 -----------------------------------------------------------------------

function TableOfContents({
  documents,
  documentKey,
  sectionKey,
}: {
  documents: GuideDocument[]
  documentKey?: string
  sectionKey?: string
}) {
  return (
    <nav className="space-y-4 text-sm">
      {KINDS.map((kind) => {
        const mine = documents.filter((d) => d.kind === kind.key)
        if (mine.length === 0) return null
        return (
          <div key={kind.key}>
            <div className="text-muted-foreground mb-1 text-xs font-semibold tracking-wide uppercase">
              {kind.label}
            </div>
            <ul className="space-y-1">
              {mine.map((document) => {
                const open = document.key === documentKey
                const waiting = document.sections.reduce((n, s) => n + s.pending_count, 0)
                return (
                  <li key={document.id}>
                    <Link
                      to={`/guide/${document.key}/${document.sections[0]?.key ?? ''}`}
                      aria-current={open && !sectionKey ? 'page' : undefined}
                      className={`flex items-center gap-1 rounded px-2 py-1 hover:bg-muted ${open ? 'font-medium' : ''}`}
                    >
                      <ChevronRight
                        className={`size-3.5 shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}
                      />
                      <span className="truncate">{document.title}</span>
                      {waiting > 0 && (
                        <Badge variant="outline" className="ml-auto border-amber-500 text-amber-700">
                          {waiting}
                        </Badge>
                      )}
                    </Link>
                    {open && (
                      <ul className="mt-1 ml-4 space-y-0.5 border-l pl-2">
                        {document.sections.map((section) => (
                          <li key={section.id}>
                            <Link
                              to={`/guide/${document.key}/${section.key}`}
                              aria-current={section.key === sectionKey ? 'page' : undefined}
                              className={`block truncate rounded px-2 py-1 text-sm hover:bg-muted ${
                                section.key === sectionKey ? 'bg-muted font-medium' : ''
                              }`}
                            >
                              {section.title}
                              {section.pending_count > 0 && (
                                <span className="ml-1 text-amber-700">·{section.pending_count}</span>
                              )}
                            </Link>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        )
      })}
      {documents.length === 0 && (
        <p className="text-muted-foreground text-sm">아직 문서가 없습니다.</p>
      )}
    </nav>
  )
}

function SearchResults({ hits, onPick }: { hits: SearchHit[]; onPick: () => void }) {
  if (hits.length === 0) return <p className="text-muted-foreground text-sm">맞는 절이 없습니다.</p>
  return (
    <ul className="space-y-2 text-sm">
      {hits.map((hit) => (
        <li key={hit.section_id}>
          <Link
            to={`/guide/${hit.document_key}/${hit.section_key}`}
            onClick={onPick}
            className="hover:bg-muted block rounded px-2 py-1"
          >
            <div className="font-medium">{hit.section_title}</div>
            <div className="text-muted-foreground text-xs">{hit.document_title}</div>
            <div className="text-muted-foreground mt-0.5 line-clamp-2 text-xs">{hit.snippet}</div>
          </Link>
        </li>
      ))}
    </ul>
  )
}

// --- 첫 화면 ----------------------------------------------------------------------

function Landing({ documents }: { documents: GuideDocument[] }) {
  return (
    <div>
      <h1 className="text-xl font-semibold">물성 핸드북</h1>
      <p className="text-muted-foreground mt-1 mb-6 text-sm">
        시편을 어떻게 자르고, 어떻게 재고, 잰 것이 어떻게 물성이 되는지. 누구나 고칠 수
        있고, 검토자가 승인한 것이 본문이 됩니다.
      </p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {KINDS.map((kind) => {
          const mine = documents.filter((d) => d.kind === kind.key)
          return (
            <section key={kind.key} className="rounded-md border p-4">
              <h2 className="font-semibold">{kind.label}</h2>
              <p className="text-muted-foreground mb-2 text-xs">{kind.hint}</p>
              {mine.length === 0 ? (
                <p className="text-muted-foreground text-sm">아직 없음</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {mine.map((document) => (
                    <li key={document.id}>
                      <Link
                        to={`/guide/${document.key}/${document.sections[0]?.key ?? ''}`}
                        className="text-primary hover:underline"
                      >
                        {document.title}
                      </Link>
                      <span className="text-muted-foreground ml-1 text-xs">
                        {document.sections.length}절
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )
        })}
      </div>
    </div>
  )
}

// --- 절 ---------------------------------------------------------------------------

function SectionView({
  document,
  sectionId,
  isReviewer,
  onSaved,
  onMove,
}: {
  document: GuideDocument
  sectionId: string
  isReviewer: boolean
  onSaved: () => void
  onMove: (sectionKey: string) => void
}) {
  const section = useResource(() => guideApi.section(sectionId), [sectionId])
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Doc>(EMPTY_DOC)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [said, setSaid] = useState<string | null>(null)
  const [failed, setFailed] = useState<Error | null>(null)

  function startEditing(current: Section) {
    setDraft(current.body as Doc)
    setNote('')
    setSaid(null)
    setEditing(true)
  }

  async function save(publish: boolean) {
    setBusy(true)
    setFailed(null)
    try {
      const made = await guideApi.submit(sectionId, {
        body: draft,
        note: note.trim() || undefined,
        publish,
      })
      setEditing(false)
      setSaid(
        made.status === 'approved'
          ? '저장했습니다.'
          : '초안으로 보냈습니다. 검토자가 승인하면 본문이 됩니다.'
      )
      section.reload()
      onSaved()
    } catch (caught) {
      setFailed(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  const index = document.sections.findIndex((s) => s.id === sectionId)
  const previous = index > 0 ? document.sections[index - 1] : null
  const next = index >= 0 && index < document.sections.length - 1 ? document.sections[index + 1] : null
  const body = section.data?.body as Doc | undefined
  const headings = body ? headingsOf(body) : []

  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
      <article className="min-w-0 flex-1">
        <div className="text-muted-foreground mb-1 text-xs">
          <Link to="/guide" className="hover:underline">
            핸드북
          </Link>
          {' › '}
          {document.title}
        </div>
        {/* **정본이 어디인지 미리 말한다.** 저장소에서 온 문서는 배포가 빠진 절을
            채우고, 사람이 `--replace` 를 부르면 본문까지 갱신된다 — 고치는 사람이
            그 사실을 모르면 다음 릴리스에 자기 글이 바뀐 것을 보고 놀란다.
            (고친 것은 안 사라진다. 승인 이력에 남고, 저장소로 되돌리는 길도 있다.) */}
        {document.source_filename && (
          <p className="text-muted-foreground mb-2 flex items-start gap-1.5 text-xs">
            <FileCode2 className="mt-0.5 size-3.5 shrink-0" />
            <span>
              <b>저장소가 정본인 문서</b>입니다 — 여기서 고쳐 승인한 것은 그대로
              남지만, 저장소 쪽이 갱신되면 배포에서 본문이 바뀔 수 있습니다.
            </span>
          </p>
        )}
        <ErrorNotice error={section.error ?? failed} className="mb-3" />
        {section.data && (
          <>
            <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
              <h1 className="text-xl font-semibold">{section.data.title}</h1>
              {!editing && (
                <Button size="sm" variant="outline" onClick={() => startEditing(section.data!)}>
                  <Pencil className="mr-1 size-3.5" />
                  편집
                </Button>
              )}
            </div>
            {said && (
              <p className="mb-3 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
                {said}
              </p>
            )}
            {editing ? (
              <div className="space-y-3">
                <GuideEditor
                  content={draft}
                  editable
                  documentKey={document.key}
                  onChange={setDraft}
                />
                <Input
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="무엇을 왜 고쳤나 (한 줄, 선택)"
                  aria-label="고친 이유"
                />
                <div className="flex flex-wrap gap-2">
                  {isReviewer ? (
                    <Button disabled={busy} onClick={() => save(true)}>
                      저장 (바로 반영)
                    </Button>
                  ) : (
                    <Button disabled={busy} onClick={() => save(false)}>
                      초안 보내기
                    </Button>
                  )}
                  {isReviewer && (
                    <Button variant="outline" disabled={busy} onClick={() => save(false)}>
                      초안으로만
                    </Button>
                  )}
                  <Button variant="ghost" disabled={busy} onClick={() => setEditing(false)}>
                    취소
                  </Button>
                  {!isReviewer && (
                    <span className="text-muted-foreground self-center text-xs">
                      검토자가 승인하면 본문이 됩니다.
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <GuideEditor content={(section.data.body as Doc) ?? EMPTY_DOC} />
            )}
            <div className="mt-8 flex justify-between border-t pt-3 text-sm">
              {previous ? (
                <button className="text-primary hover:underline" onClick={() => onMove(previous.key)}>
                  ← {previous.title}
                </button>
              ) : (
                <span />
              )}
              {next ? (
                <button className="text-primary hover:underline" onClick={() => onMove(next.key)}>
                  {next.title} →
                </button>
              ) : (
                <span />
              )}
            </div>
          </>
        )}
      </article>

      <aside className="w-full shrink-0 text-sm xl:w-56">
        {headings.length > 0 && !editing && (
          <div className="mb-4">
            <div className="text-muted-foreground mb-1 text-xs font-semibold">이 절에서</div>
            <ul className="space-y-0.5">
              {headings.map((heading, i) => (
                <li
                  key={i}
                  className={`text-muted-foreground truncate ${heading.level > 2 ? 'pl-3' : ''}`}
                >
                  {heading.text}
                </li>
              ))}
            </ul>
          </div>
        )}
        {section.data && (
          <div className="text-muted-foreground space-y-1 text-xs">
            <div>{section.data.revision_no}판</div>
            <div>{stamp(section.data.updated_at)}</div>
            {section.data.updated_by && <div>{section.data.updated_by.name}</div>}
            {section.data.pending_count > 0 && (
              <div className="text-amber-700">검토 대기 {section.data.pending_count}건</div>
            )}
          </div>
        )}
        {isReviewer && section.data && section.data.pending_count > 0 && (
          <ReviewQueue sectionId={sectionId} onDone={() => {
            section.reload()
            onSaved()
          }} />
        )}
      </aside>
    </div>
  )
}

// --- 검토 -------------------------------------------------------------------------

function ReviewQueue({ sectionId, onDone }: { sectionId: string; onDone: () => void }) {
  const history = useResource(() => guideApi.history(sectionId), [sectionId])
  const [open, setOpen] = useState<Revision | null>(null)
  const [busy, setBusy] = useState(false)
  const pending = (history.data ?? []).filter((r) => r.status === 'pending')

  async function decide(revision: Revision, approve: boolean) {
    setBusy(true)
    try {
      if (approve) await guideApi.approve(revision.id)
      else await guideApi.reject(revision.id)
      setOpen(null)
      history.reload()
      onDone()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-4 border-t pt-3">
      <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-amber-700">
        <Sparkles className="size-3.5" /> 검토 대기
      </div>
      <ul className="space-y-1">
        {pending.map((revision) => (
          <li key={revision.id}>
            <button
              className="hover:bg-muted w-full rounded px-2 py-1 text-left"
              onClick={() => setOpen(open?.id === revision.id ? null : revision)}
            >
              <div className="truncate">{revision.author?.name ?? '?'}</div>
              <div className="text-muted-foreground truncate text-xs">
                {stamp(revision.created_at)}
                {revision.note ? ` · ${revision.note}` : ''}
              </div>
            </button>
            {open?.id === revision.id && (
              <div className="mt-1 rounded-md border p-2">
                <GuideEditor content={revision.body as Doc} />
                <div className="mt-2 flex gap-1">
                  <Button size="sm" disabled={busy} onClick={() => decide(revision, true)}>
                    승인
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => decide(revision, false)}
                  >
                    거절
                  </Button>
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
