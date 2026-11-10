import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'

type Tone = 'success' | 'warning' | 'failed'

type NoticeRequest = {
  id: number
  tone: Tone
  message: string
  href?: string
  hrefLabel?: string
  note?: string
  detail?: string
  hold?: boolean
  onDone?: () => void
}

type NoticeExtra = {
  href?: string
  hrefLabel?: string
  note?: string
  detail?: string
  hold?: boolean
  onDone?: () => void
}

type ShowNotice = (tone: Tone, message: string, extra?: NoticeExtra) => void

const NoticeContext = createContext<ShowNotice>(() => {})

const toneStroke: Record<Tone, string> = {
  success: '#059669',
  warning: '#d97706',
  failed: '#dc2626',
}

function holdOpen(request: NoticeRequest) {
  if (request.hold || request.detail) return true
  if (/password|https?:\/\/|copy it now|will not be shown|shown once/i.test(request.message)) return true
  if (request.message.length > 160) return true
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function Mark({ tone }: { tone: Tone }) {
  const stroke = toneStroke[tone]
  return (
    <svg viewBox="0 0 52 52" className="h-16 w-16" aria-hidden="true">
      <circle className="notice-ring" cx="26" cy="26" r="24" fill="none" stroke={stroke} strokeWidth="2" />
      {tone === 'success' ? <path className="notice-mark" fill="none" stroke={stroke} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" d="M14 27 l8 8 l16-16" /> : null}
      {tone === 'failed' ? <path className="notice-mark" fill="none" stroke={stroke} strokeWidth="3" strokeLinecap="round" d="M18 18 L34 34 M34 18 L18 34" /> : null}
      {tone === 'warning' ? (
        <>
          <path className="notice-mark" fill="none" stroke={stroke} strokeWidth="3" strokeLinecap="round" d="M26 16 V30" />
          <circle cx="26" cy="37" r="1.7" fill={stroke} />
        </>
      ) : null}
    </svg>
  )
}

function NoticeModal({ request, onClose }: { request: NoticeRequest; onClose: () => void }) {
  const titleId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const previous = useRef<HTMLElement | null>(null)
  const [paused, setPaused] = useState(false)
  const [copied, setCopied] = useState(false)
  const stay = holdOpen(request)
  const close = useCallback(() => {
    request.onDone?.()
    onClose()
  }, [onClose, request])

  useEffect(() => {
    previous.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    closeRef.current?.focus()
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previous.current?.focus()
    }
  }, [close])

  useEffect(() => {
    if (stay || paused) return
    const timer = window.setTimeout(close, 1500)
    return () => window.clearTimeout(timer)
  }, [close, paused, stay])

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault()
      close()
      return
    }
    if (event.key !== 'Tab') return
    const root = dialogRef.current
    if (!root) return
    const items = [...root.querySelectorAll<HTMLElement>('a[href], button:not([disabled])')]
    if (items.length === 0) return
    const first = items[0]
    const last = items[items.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-gray-900/40 px-4" onClick={close}>
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="success-pop relative w-full max-w-sm rounded-2xl border border-gray-200 bg-white px-6 py-6 text-center shadow-xl"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={onKeyDown}
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
      >
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center">
          <Mark tone={request.tone} />
        </div>
        <h2 id={titleId} className="text-base font-semibold text-gray-800">{request.message}</h2>
        {request.detail ? <p className="mt-3 break-all rounded-lg bg-gray-50 px-3 py-2 text-left font-mono text-xs text-gray-800 select-all">{request.detail}</p> : null}
        {request.href && request.hrefLabel ? (
          <p className="mt-2 text-sm text-gray-600">
            <a href={request.href} className="font-semibold text-gray-900 underline" onClick={close}>{request.hrefLabel}</a>
            {request.note ? ` ${request.note}` : null}
          </p>
        ) : null}
        <div className="mt-5 flex justify-center gap-2">
          {request.detail ? (
            <button
              type="button"
              className="rounded-xl border border-gray-200 px-4 py-2.5 text-sm font-bold text-gray-800"
              onClick={() => {
                const clip = navigator.clipboard
                if (!clip) return
                void clip.writeText(request.detail || '').then(() => setCopied(true)).catch(() => setCopied(false))
              }}
            >
              {copied ? 'Copied' : 'Copy'}
            </button>
          ) : null}
          <button ref={closeRef} type="button" className="rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-bold text-white" onClick={close}>Done</button>
        </div>
      </div>
    </div>
  )
}

export function SuccessProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<NoticeRequest | null>(null)
  const nextId = useRef(0)
  const show = useCallback<ShowNotice>((tone, message, extra) => {
    const text = message.trim()
    if (!text) return
    const next: NoticeRequest = {
      id: ++nextId.current,
      tone,
      message: text,
      href: extra?.href,
      hrefLabel: extra?.hrefLabel,
      note: extra?.note,
      detail: extra?.detail,
      hold: extra?.hold,
      onDone: extra?.onDone,
    }
    setCurrent((existing) => (existing && holdOpen(existing) && !holdOpen(next) ? existing : next))
  }, [])
  return (
    <NoticeContext.Provider value={show}>
      {children}
      {current ? <NoticeModal key={current.id} request={current} onClose={() => setCurrent(null)} /> : null}
    </NoticeContext.Provider>
  )
}

function NoticeTrigger({ tone, message, href, hrefLabel, note, detail, hold, onDone }: { tone: Tone; message: string; href?: string; hrefLabel?: string; note?: string; detail?: string; hold?: boolean; onDone?: () => void }) {
  const show = useContext(NoticeContext)
  const seen = useRef('')
  const doneRef = useRef(onDone)
  doneRef.current = onDone
  useEffect(() => {
    const text = message.trim()
    const token = `${tone}|${text}|${href || ''}|${hrefLabel || ''}|${note || ''}|${detail || ''}`
    if (!text) {
      seen.current = ''
      return
    }
    if (token === seen.current) return
    seen.current = token
    show(tone, text, { href, hrefLabel, note, detail, hold, onDone: () => doneRef.current?.() })
  }, [detail, hold, href, hrefLabel, message, note, show, tone])
  return null
}

export function SuccessNotice({ message, href, hrefLabel, note }: { message: string; href?: string; hrefLabel?: string; note?: string }) {
  return <NoticeTrigger tone="success" message={message} href={href} hrefLabel={hrefLabel} note={note} />
}

export function FailureNotice({ message, hold }: { message: string; hold?: boolean }) {
  return <NoticeTrigger tone="failed" message={message} hold={hold} />
}

export function WarningNotice({ message, detail, hold, onDone }: { message: string; detail?: string; hold?: boolean; onDone?: () => void }) {
  return <NoticeTrigger tone="warning" message={message} detail={detail} hold={hold} onDone={onDone} />
}
