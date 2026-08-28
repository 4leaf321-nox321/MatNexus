/**
 * 핸드북 편집기 — **서식은 앱이 정하고, 사람은 뜻만 고른다.**
 *
 * 워드처럼 글꼴·색·크기까지 열어 주면 25편이 25가지 얼굴이 된다 — 가져온 원본
 * HTML 이 딱 그 상태였다(문서마다 제 `<style>`). 여기서 허용하는 것:
 *
 *     제목(2·3·4단계) · 문단 · 굵게 · 기울임 · 코드 · 링크 · 목록 · 인용
 *     표(병합 포함) · 그림 · 구분선
 *
 * 넣지 않은 것은 붙여넣어도 사라진다. 워드에서 복사해 와도 서식 쓰레기가 안 들어온다.
 *
 * ## 그림은 파일로
 *
 * 붙여 넣거나 끌어다 놓는 순간 서버에 올리고 **주소만** 본문에 넣는다. base64 로
 * 박으면 본문이 그림 크기만큼 부풀고, 같은 그림이 절마다 복제된다.
 *
 * ## 읽기도 같은 부품
 *
 * 보는 화면은 이 편집기를 `editable=false` 로 쓴다. 그리는 코드가 하나라 편집 중에
 * 본 것과 저장 뒤에 본 것이 같다.
 */

import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import { TableKit } from '@tiptap/extension-table'
import { EditorContent, useEditor } from '@tiptap/react'
import type { Editor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import {
  Bold,
  Code,
  Heading2,
  Heading3,
  ImagePlus,
  Italic,
  Link2,
  List,
  ListOrdered,
  Minus,
  Quote,
  Table as TableIcon,
} from 'lucide-react'
import { useEffect, useRef } from 'react'

import { guideApi } from '@/modules/guide/api'
import type { Doc } from '@/modules/guide/api'
import { Button } from '@/shared/components/ui/button'

/** 편집기 본문 스타일. 한 벌뿐이라 25편이 같은 얼굴이다. */
const PROSE =
  'max-w-none text-sm leading-6 ' +
  '[&_h2]:mt-6 [&_h2]:mb-2 [&_h2]:text-lg [&_h2]:font-semibold ' +
  '[&_h3]:mt-4 [&_h3]:mb-1 [&_h3]:text-base [&_h3]:font-semibold ' +
  '[&_h4]:mt-3 [&_h4]:font-medium ' +
  '[&_p]:my-2 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-6 ' +
  '[&_blockquote]:border-l-4 [&_blockquote]:border-amber-400 [&_blockquote]:bg-amber-50 [&_blockquote]:px-3 [&_blockquote]:py-1 [&_blockquote]:my-3 ' +
  '[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:font-mono [&_code]:text-[0.85em] ' +
  '[&_pre]:my-3 [&_pre]:rounded-md [&_pre]:bg-muted [&_pre]:p-3 [&_pre]:font-mono [&_pre]:text-xs ' +
  '[&_a]:text-primary [&_a]:underline ' +
  '[&_hr]:my-6 ' +
  '[&_table]:my-3 [&_table]:w-full [&_table]:border-collapse [&_table]:text-xs ' +
  '[&_th]:border [&_th]:bg-muted [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_th]:font-semibold ' +
  '[&_td]:border [&_td]:px-2 [&_td]:py-1 [&_td]:align-top ' +
  '[&_img]:my-3 [&_img]:max-w-full [&_img]:rounded-md ' +
  '[&_.ProseMirror]:outline-none [&_.ProseMirror-selectednode]:ring-2'

function extensions(placeholder: string) {
  return [
    StarterKit.configure({
      heading: { levels: [2, 3, 4] },
      // 글꼴·색·밑줄은 없다. 있는 것만 남긴다.
      underline: false,
      link: { openOnClick: false, autolink: true },
    }),
    TableKit.configure({ table: { resizable: false } }),
    Image.configure({ inline: false, allowBase64: false }),
    Placeholder.configure({ placeholder }),
  ]
}

async function uploadAndInsert(editor: Editor, files: File[], documentKey?: string) {
  for (const file of files) {
    if (!file.type.startsWith('image/')) continue
    try {
      const asset = await guideApi.upload(file, documentKey)
      editor.chain().focus().setImage({ src: asset.url, alt: file.name }).run()
    } catch {
      // 올리기에 실패한 그림은 안 들어간다. 조용히 base64 로 박히는 것보다 낫다.
    }
  }
}

export interface GuideEditorProps {
  content: Doc
  editable?: boolean
  /** 그림을 올릴 때 어느 문서 것인지. 없어도 된다. */
  documentKey?: string
  /** 편집 중 내용이 바뀔 때. `editable` 일 때만 부른다. */
  onChange?: (doc: Doc) => void
  placeholder?: string
}

export function GuideEditor({
  content,
  editable = false,
  documentKey,
  onChange,
  placeholder = '여기에 씁니다. 워드·엑셀에서 복사해 붙여 넣어도 됩니다.',
}: GuideEditorProps) {
  const fileInput = useRef<HTMLInputElement>(null)
  const editor = useEditor({
    extensions: extensions(placeholder),
    content,
    editable,
    // React 19 + Tiptap v3: 첫 렌더에서 즉시 그리게 둔다(SSR 없음).
    immediatelyRender: true,
    onUpdate: ({ editor: instance }) => onChange?.(instance.getJSON() as Doc),
    editorProps: {
      attributes: { class: 'min-h-[8rem] focus:outline-none', role: 'textbox' },
      handlePaste: (_view, event) => {
        const files = Array.from(event.clipboardData?.files ?? [])
        if (!files.some((f) => f.type.startsWith('image/'))) return false
        event.preventDefault()
        return true
      },
      handleDrop: (_view, event) => {
        const files = Array.from(event.dataTransfer?.files ?? [])
        if (!files.some((f) => f.type.startsWith('image/'))) return false
        event.preventDefault()
        return true
      },
    },
  })

  // 붙여넣기·끌어놓기의 그림은 위에서 막고 여기서 올린다 — handlePaste 는 동기라
  // 업로드를 기다릴 수 없다.
  useEffect(() => {
    if (!editor || !editable) return
    const dom = editor.view.dom
    const onPaste = (event: ClipboardEvent) => {
      const files = Array.from(event.clipboardData?.files ?? []).filter((f) =>
        f.type.startsWith('image/')
      )
      if (files.length) void uploadAndInsert(editor, files, documentKey)
    }
    const onDrop = (event: DragEvent) => {
      const files = Array.from(event.dataTransfer?.files ?? []).filter((f) =>
        f.type.startsWith('image/')
      )
      if (files.length) void uploadAndInsert(editor, files, documentKey)
    }
    dom.addEventListener('paste', onPaste)
    dom.addEventListener('drop', onDrop)
    return () => {
      dom.removeEventListener('paste', onPaste)
      dom.removeEventListener('drop', onDrop)
    }
  }, [editor, editable, documentKey])

  // 다른 절로 옮기면 내용을 갈아 끼운다. 편집 중인 것을 덮지 않도록 읽기일 때만.
  useEffect(() => {
    if (!editor || editable) return
    editor.commands.setContent(content, { emitUpdate: false })
  }, [editor, content, editable])

  useEffect(() => {
    editor?.setEditable(editable)
  }, [editor, editable])

  if (!editor) return null

  return (
    <div>
      {editable && (
        <div className="bg-muted/40 mb-2 flex flex-wrap gap-0.5 rounded-md border p-1">
          <Tool
            label="제목"
            icon={Heading2}
            active={editor.isActive('heading', { level: 2 })}
            onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
          />
          <Tool
            label="작은 제목"
            icon={Heading3}
            active={editor.isActive('heading', { level: 3 })}
            onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
          />
          <Tool
            label="굵게"
            icon={Bold}
            active={editor.isActive('bold')}
            onClick={() => editor.chain().focus().toggleBold().run()}
          />
          <Tool
            label="기울임"
            icon={Italic}
            active={editor.isActive('italic')}
            onClick={() => editor.chain().focus().toggleItalic().run()}
          />
          <Tool
            label="코드"
            icon={Code}
            active={editor.isActive('code')}
            onClick={() => editor.chain().focus().toggleCode().run()}
          />
          <Tool
            label="링크"
            icon={Link2}
            active={editor.isActive('link')}
            onClick={() => {
              const previous = editor.getAttributes('link').href as string | undefined
              const href = window.prompt('링크 주소', previous ?? 'https://')
              if (href === null) return
              if (href === '') editor.chain().focus().unsetLink().run()
              else editor.chain().focus().setLink({ href }).run()
            }}
          />
          <Tool
            label="목록"
            icon={List}
            active={editor.isActive('bulletList')}
            onClick={() => editor.chain().focus().toggleBulletList().run()}
          />
          <Tool
            label="번호 목록"
            icon={ListOrdered}
            active={editor.isActive('orderedList')}
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
          />
          <Tool
            label="안내 상자"
            icon={Quote}
            active={editor.isActive('blockquote')}
            onClick={() => editor.chain().focus().toggleBlockquote().run()}
          />
          <Tool
            label="표"
            icon={TableIcon}
            onClick={() =>
              editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
            }
          />
          <Tool
            label="그림"
            icon={ImagePlus}
            onClick={() => fileInput.current?.click()}
          />
          <Tool
            label="구분선"
            icon={Minus}
            onClick={() => editor.chain().focus().setHorizontalRule().run()}
          />
          {editor.isActive('table') && (
            <span className="ml-2 flex gap-0.5 border-l pl-2">
              <Button size="sm" variant="ghost" onClick={() => editor.chain().focus().addRowAfter().run()}>
                행+
              </Button>
              <Button size="sm" variant="ghost" onClick={() => editor.chain().focus().addColumnAfter().run()}>
                열+
              </Button>
              <Button size="sm" variant="ghost" onClick={() => editor.chain().focus().mergeOrSplit().run()}>
                병합/나눔
              </Button>
              <Button size="sm" variant="ghost" onClick={() => editor.chain().focus().deleteRow().run()}>
                행−
              </Button>
              <Button size="sm" variant="ghost" onClick={() => editor.chain().focus().deleteColumn().run()}>
                열−
              </Button>
            </span>
          )}
          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            className="hidden"
            aria-label="그림 파일"
            onChange={(event) => {
              const files = Array.from(event.target.files ?? [])
              event.target.value = ''
              if (files.length) void uploadAndInsert(editor, files, documentKey)
            }}
          />
        </div>
      )}
      <EditorContent
        editor={editor}
        className={`${PROSE} ${editable ? 'rounded-md border px-3 py-2' : ''}`}
      />
    </div>
  )
}

function Tool({
  label,
  icon: Icon,
  active = false,
  onClick,
}: {
  label: string
  icon: typeof Bold
  active?: boolean
  onClick: () => void
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant={active ? 'secondary' : 'ghost'}
      className="h-7 px-1.5"
      aria-label={label}
      title={label}
      aria-pressed={active}
      onMouseDown={(event) => event.preventDefault()}
      onClick={onClick}
    >
      <Icon className="size-4" />
    </Button>
  )
}
