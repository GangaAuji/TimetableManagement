import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { apiRequest } from '../../../shared/api/client'
import { getCsrfToken } from '../../../shared/api/endpoints'
import { messageFrom } from '../../../shared/components/data-list'
import { ThemeModeButton } from '../../../shared/components/ThemeModeButton'
import { safeText } from '../../../shared/security/sanitize'

const tokenPattern = /^[A-Za-z0-9_-]{16,200}$/
const fieldClass = 'w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm outline-none focus:border-transparent focus:bg-white focus:ring-2 focus:ring-slate-500'

type InviteState = 'checking' | 'open' | 'expired' | 'used' | 'invalid'

function cameraMessage(error: unknown) {
  if (error instanceof DOMException && (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError')) {
    return 'Allow camera access in the browser, then try again.'
  }
  if (error instanceof DOMException && (error.name === 'NotFoundError' || error.name === 'OverconstrainedError')) {
    return 'No usable camera was found on this device.'
  }
  return 'The camera could not be started.'
}

async function openCamera() {
  const attempts: MediaStreamConstraints[] = [
    { video: true, audio: false },
    { video: { facingMode: { ideal: 'user' } }, audio: false },
  ]
  let lastError: unknown = new Error('camera')
  for (const constraints of attempts) {
    try {
      return await navigator.mediaDevices.getUserMedia(constraints)
    } catch (error) {
      lastError = error
    }
  }
  throw lastError
}

export function RegisterPage() {
  const { token = '' } = useParams()
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [capture, setCapture] = useState('')
  const [error, setError] = useState('')
  const [cameraError, setCameraError] = useState('')
  const [ready, setReady] = useState(false)
  const [done, setDone] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [state, setState] = useState<InviteState>('checking')
  const [invite, setInvite] = useState({ name: '', role: '' })
  const validToken = tokenPattern.test(token)

  function attach(node: HTMLVideoElement | null) {
    videoRef.current = node
    if (!node) return
    node.muted = true
    node.defaultMuted = true
    node.playsInline = true
    if (!streamRef.current) return
    node.srcObject = streamRef.current
    void node.play().catch(() => undefined)
  }

  function stopCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setReady(false)
  }

  async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('This browser cannot open a camera.')
      return
    }
    setCameraError('')
    setReady(false)
    stopCamera()
    try {
      const stream = await openCamera()
      streamRef.current = stream
      const video = videoRef.current
      if (video) {
        video.muted = true
        video.srcObject = stream
        await video.play().catch(() => undefined)
      }
    } catch (reason) {
      setCameraError(cameraMessage(reason))
    }
  }

  useEffect(() => {
    if (!validToken) {
      setState('invalid')
      return
    }
    void apiRequest<{ state?: string; name?: string; role?: string }>(`/api/register/${encodeURIComponent(token)}`)
      .then((data) => {
        const next = data.state
        setState(next === 'open' || next === 'expired' || next === 'used' ? next : 'invalid')
        setInvite({ name: safeText(data.name, 100), role: safeText(data.role, 50) })
      })
      .catch((reason: unknown) => {
        setState('invalid')
        setError(messageFrom(reason))
      })
  }, [token, validToken])

  useEffect(() => {
    if (state !== 'open') return undefined
    let cancelled = false
    void openCamera()
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }
        streamRef.current = stream
        const video = videoRef.current
        if (!video) return
        video.muted = true
        video.srcObject = stream
        return video.play().catch(() => undefined)
      })
      .catch((reason: unknown) => {
        if (!cancelled) setCameraError(cameraMessage(reason))
      })
    return () => {
      cancelled = true
      stopCamera()
    }
  }, [state])

  function takePhoto() {
    const video = videoRef.current
    if (!video || video.readyState < 2 || video.videoWidth < 2) {
      setError('The camera is not ready.')
      return
    }
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const context = canvas.getContext('2d')
    if (!context) return
    context.drawImage(video, 0, 0)
    setCapture(canvas.toDataURL('image/jpeg', 0.9))
    setError('')
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (state !== 'open') return
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    if (!capture) {
      setError('Capture a face photo before continuing.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const { csrf_token: csrfToken } = await getCsrfToken()
      const body = new FormData()
      body.set('csrf_token', csrfToken)
      body.set('username', username)
      body.set('password', password)
      body.set('confirm_password', confirmPassword)
      body.set('face_capture_data', capture)
      body.set('face_template_version', 'mobilefacenet_192_l2_v1')
      body.set('face_detector_model', 'yolov8n_float32.tflite')
      const response = await fetch(`/register/${encodeURIComponent(token)}`, {
        method: 'POST',
        credentials: 'include',
        cache: 'no-store',
        redirect: 'follow',
        body,
      })
      if (!response.ok || response.url.includes('/register/')) {
        setError('Registration could not be completed. Check the username and photo, then try again.')
        return
      }
      stopCamera()
      setDone(true)
    } catch {
      setError('The server is not reachable.')
    } finally {
      setSubmitting(false)
    }
  }

  const blocked = state === 'expired' || state === 'used' || state === 'invalid'

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-100 p-4 font-sans">
      <ThemeModeButton className="fixed top-4 right-4 z-20 border border-gray-200 bg-white text-gray-700 shadow-sm" />
      <div className="flex w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl md:min-h-[640px] md:flex-row">
        <div className="relative hidden flex-col justify-between overflow-hidden bg-slate-900 p-12 text-white md:flex md:w-5/12">
          <div className="absolute inset-0 bg-gradient-to-br from-slate-800 via-slate-900 to-blue-950" />
          <div className="relative z-10">
            <div className="mb-6 flex items-center gap-2">
              <i className="fas fa-user-check text-3xl text-blue-300" />
              <span className="text-xl font-bold tracking-wider">REGISTER</span>
            </div>
            <h2 className="mb-4 text-3xl leading-tight font-bold">Create your account</h2>
            <p className="text-slate-300">Use the invitation from your college, choose a username, and capture a clear face photo.</p>
          </div>
          <p className="relative z-10 text-sm text-slate-400">The photo is used for attendance. Face the camera in good light.</p>
        </div>
        <div className="flex flex-1 flex-col justify-center p-8 md:p-12">
          {state === 'checking' && <p className="text-sm text-gray-500">Checking this invitation…</p>}
          {blocked && (
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{state === 'expired' ? 'This invitation has expired' : state === 'used' ? 'This invitation was already used' : 'This registration link is not valid'}</h1>
              <p className="mt-2 text-sm text-gray-500">{state === 'expired' ? 'Ask an administrator to resend the invitation.' : 'Ask an administrator for a new registration link.'}</p>
              {error && <p className="mt-4 text-sm text-red-700">{error}</p>}
              <a href="/" className="mt-6 inline-block text-sm font-semibold text-slate-700 underline">Back to sign in</a>
            </div>
          )}
          {done && (
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Account ready</h1>
              <p className="mt-2 text-sm text-gray-500">You can sign in with the username you just created.</p>
              <a href="/" className="mt-6 inline-flex rounded-lg bg-slate-900 px-4 py-3 text-sm font-semibold text-white">Sign in</a>
            </div>
          )}
          {state === 'open' && !done && (
            <form onSubmit={(event) => void onSubmit(event)} className="space-y-5">
              <div>
                <h1 className="text-2xl font-bold text-gray-900">Complete registration</h1>
                <p className="mt-1 text-sm text-gray-500">{invite.name || 'Invited user'}{invite.role ? ` · ${invite.role}` : ''}</p>
              </div>
              {error && <p className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
              <label className="block text-sm font-medium text-gray-700">Username
                <input required minLength={3} maxLength={50} value={username} onChange={(event) => setUsername(event.target.value)} className={`mt-1 ${fieldClass}`} />
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block text-sm font-medium text-gray-700">Password
                  <input required type="password" minLength={6} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} className={`mt-1 ${fieldClass}`} />
                </label>
                <label className="block text-sm font-medium text-gray-700">Confirm password
                  <input required type="password" minLength={6} maxLength={128} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className={`mt-1 ${fieldClass}`} />
                </label>
              </div>
              <div>
                <p className="mb-2 text-sm font-medium text-gray-700">Face photo</p>
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_140px]">
                  <div className="relative overflow-hidden rounded-2xl bg-slate-900">
                    <video ref={attach} autoPlay playsInline muted onLoadedMetadata={(event) => setReady(event.currentTarget.videoWidth > 1)} className="aspect-[4/3] w-full bg-slate-900 object-cover" />
                    {!ready && !cameraError && <p className="absolute inset-0 flex items-center justify-center text-xs text-white">Starting camera…</p>}
                    {cameraError && (
                      <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-900/90 px-4 text-center">
                        <p className="text-xs text-white">{cameraError}</p>
                        <button type="button" onClick={() => void startCamera()} className="rounded-lg bg-white px-3 py-1.5 text-xs font-bold text-slate-900">Try camera again</button>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col justify-between gap-3">
                    {capture ? <img src={capture} alt="Captured face" className="aspect-[4/3] w-full rounded-xl object-cover" /> : <div className="flex aspect-[4/3] items-center justify-center rounded-xl border border-dashed border-gray-300 text-[10px] text-gray-400">No photo yet</div>}
                    <button type="button" onClick={takePhoto} disabled={!ready} className="rounded-lg border border-gray-300 px-3 py-2 text-xs font-bold text-gray-800 disabled:opacity-50">{capture ? 'Retake photo' : 'Capture photo'}</button>
                  </div>
                </div>
              </div>
              <button type="submit" disabled={submitting} className="flex w-full justify-center rounded-lg bg-slate-900 px-4 py-3 text-sm font-semibold text-white disabled:opacity-60">{submitting ? 'Saving…' : 'Create account'}</button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
