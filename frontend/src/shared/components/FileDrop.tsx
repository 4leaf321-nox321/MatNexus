/**
 * 파일을 **끌어다 놓거나 골라서** 넣는 자리.
 *
 * 일괄 등록에는 있었고 시험 등록 하나짜리에는 없었다 — 같은 일을 하는 두 화면이
 * 서로 다르게 동작했다. 탐색기에서 파일을 끌어다 놓는 것이 몸에 밴 사람은 단일
 * 등록에서도 그렇게 하고, **아무 일도 안 일어나면 고장으로 읽는다.**
 *
 * ## 왜 조각으로 빼는가
 *
 * 끌어 놓기는 `dragover` 에서 `preventDefault` 를 안 하면 브라우저가 파일을
 * 새 탭으로 열어 버린다 — **작업하던 화면이 통째로 날아간다.** 화면마다 다시
 * 적으면 언젠가 한 곳이 그것을 빠뜨린다.
 */

import { useRef, useState } from 'react'
import { FileUp } from 'lucide-react'

import { Button } from '@/shared/components/ui/button'

export function FileDrop({
  onFiles,
  multiple = false,
  accept,
  disabled = false,
  hint,
}: {
  onFiles: (files: FileList) => void
  multiple?: boolean
  accept?: string
  disabled?: boolean
  /** 크기 한도처럼 고르기 전에 알아야 하는 것. */
  hint?: string
}) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)

  return (
    <div
      onDragOver={(event) => {
        // **막지 않으면 브라우저가 파일을 새 탭으로 연다.** 작업하던 화면이
        // 통째로 날아간다.
        event.preventDefault()
        if (!disabled) setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault()
        setOver(false)
        if (!disabled && event.dataTransfer.files.length > 0) onFiles(event.dataTransfer.files)
      }}
      className={`rounded-md border-2 border-dashed p-4 text-center transition-colors ${
        over ? 'border-primary bg-primary/5' : 'border-muted'
      } ${disabled ? 'opacity-50' : ''}`}
    >
      <FileUp className="text-muted-foreground mx-auto mb-1.5 size-5" />
      <p className="text-sm">파일을 여기에 끌어다 놓으세요</p>
      <Button
        variant="secondary"
        size="sm"
        className="mt-2"
        disabled={disabled}
        onClick={() => input.current?.click()}
      >
        파일 고르기
      </Button>
      {hint && <p className="text-muted-foreground mt-1.5 text-xs">{hint}</p>}
      <input
        ref={input}
        type="file"
        multiple={multiple}
        accept={accept}
        className="hidden"
        aria-label="원본 파일"
        onChange={(event) => {
          if (event.target.files?.length) onFiles(event.target.files)
          // **같은 파일을 다시 고를 수 있어야 한다.** 값이 남아 있으면
          // `change` 가 안 뜨고, 사람은 눌렀는데 아무 일도 없다고 읽는다.
          event.target.value = ''
        }}
      />
    </div>
  )
}
