"use client"

import * as React from "react"
import { Dialog as DialogPrimitive } from "radix-ui"

import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/components/ui/button"
import { XIcon } from "lucide-react"

function Dialog({
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />
}

function DialogTrigger({
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Trigger>) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />
}

function DialogPortal({
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Portal>) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />
}

function DialogClose({
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />
}

function DialogOverlay({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      data-slot="dialog-overlay"
      className={cn(
        "fixed inset-0 isolate z-50 bg-black/10 duration-100 supports-backdrop-filter:backdrop-blur-xs data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0",
        className
      )}
      {...props}
    />
  )
}

/**
 * 기본 폭은 **512px(`lg`)** 이다. 전에는 384px(`sm`) 이었는데, 그 안에 2열·3열
 * 폼이 들어가 있었다 — 시편 추가는 「실측 두께 (mm)」 같은 라벨 셋을 **각 110px**
 * 칸에 욱여넣었고, 라벨이 칸보다 길었다.
 *
 * 384px 로 두면 **아무것도 안 적은 모달이 제일 좁아진다.** 폼이 대부분인데
 * 기본값이 확인창 크기였던 셈이다. 확인창은 짧은 문장 하나와 단추 둘이라
 * 좁아야 맞고, 그건 **그쪽이 `sm:max-w-sm` 을 적는 것**이 옳다.
 *
 * 내용에 따라 넓히는 것은 자유다(2열은 `xl`, 3열이나 표는 `2xl` 이상). 다만
 * **좁히려면 이유가 있어야 한다** — 기본값이 폼에 맞춰져 있으므로.
 */
function DialogContent({
  className,
  children,
  showCloseButton = true,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & {
  showCloseButton?: boolean
}) {
  const pinned = usePinnedLayout(children)
  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        data-slot="dialog-content"
        className={cn(
          // **키가 화면을 넘으면 가운데만 굴린다.** 안 넣으면 모달이 화면
          // 밖으로 자라고 **아래쪽 버튼을 누를 방법이 사라진다** — 기준정보에서
          // 값을 여러 개 적으면 '추가' 버튼이 그렇게 됐다.
          //
          // 바깥을 통째로 굴리지 않는다. 그러면 **확인·취소가 내용과 함께
          // 위로 사라진다** — 누르려면 끝까지 굴려야 하고, 긴 모달일수록
          // 그 거리가 멀다. 머리글과 바닥글은 붙박이고 가운데만 움직인다.
          //
          // 여기(프리미티브)에 두는 이유: 모달마다 적게 하면 새 모달을 만들
          // 때마다 잊는다. 실제로 21개 중 13개가 빠져 있었고, 빠진 것은
          // **내용이 길어지기 전까지 안 보인다.**
          "fixed top-1/2 left-1/2 z-50 flex max-h-[85vh] w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-hidden rounded-xl bg-popover p-4 text-sm text-popover-foreground ring-1 ring-foreground/10 duration-100 outline-none sm:max-w-lg data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95",
          className
        )}
        {...props}
      >
        {pinned}
        {showCloseButton && (
          <DialogPrimitive.Close data-slot="dialog-close" asChild>
            <Button
              variant="ghost"
              className="absolute top-2 right-2"
              size="icon-sm"
            >
              <XIcon
              />
              <span className="sr-only">Close</span>
            </Button>
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Content>
    </DialogPortal>
  )
}

/**
 * 머리글·바닥글은 붙박이로 두고 **가운데만 굴린다.**
 *
 * ## 왜 감싸 주는가 — 각 모달이 적게 하지 않고
 *
 * 굴릴 영역을 모달마다 손으로 감싸게 하면 **새 모달을 만들 때마다 잊는다.**
 * 스크롤 자체가 그렇게 빠져 있었다(21개 중 13개). 같은 실수를 한 겹 안쪽에서
 * 되풀이할 이유가 없다.
 *
 * ## 바닥글이 없으면 아무 일도 안 한다
 *
 * `DialogFooter` 를 안 쓰는 모달이 둘 있다. 그런 모달은 내용 전체가 굴러가고,
 * 그것은 이 함수가 없을 때와 같다 — **못 쓰게 만들지 않는다.**
 */
function usePinnedLayout(children: React.ReactNode): React.ReactNode {
  const items = React.Children.toArray(children)
  const head = items.filter(
    (one) => React.isValidElement(one) && one.type === DialogHeader
  )
  const foot = items.filter(
    (one) => React.isValidElement(one) && one.type === DialogFooter
  )
  const body = items.filter((one) => !head.includes(one) && !foot.includes(one))

  return (
    <>
      {head}
      {/* `-mx-4 px-4` 는 굴리는 영역이 모달의 좌우 여백까지 쓰게 한다 —
          안 그러면 스크롤바가 안쪽으로 들어와 내용과 겹쳐 보인다. */}
      <div className="-mx-4 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4">
        {body}
      </div>
      {foot}
    </>
  )
}

function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-header"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  )
}

function DialogFooter({
  className,
  showCloseButton = false,
  children,
  ...props
}: React.ComponentProps<"div"> & {
  showCloseButton?: boolean
}) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn(
        "-mx-4 -mb-4 flex flex-col-reverse gap-2 rounded-b-xl border-t bg-muted/50 p-4 sm:flex-row sm:justify-end",
        className
      )}
      {...props}
    >
      {children}
      {showCloseButton && (
        <DialogPrimitive.Close asChild>
          <Button variant="outline">Close</Button>
        </DialogPrimitive.Close>
      )}
    </div>
  )
}

function DialogTitle({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn(
        "font-heading text-base leading-none font-medium",
        className
      )}
      {...props}
    />
  )
}

function DialogDescription({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn(
        "text-sm text-muted-foreground *:[a]:underline *:[a]:underline-offset-3 *:[a]:hover:text-foreground",
        className
      )}
      {...props}
    />
  )
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
}
