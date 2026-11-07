import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { safeText } from '../../../shared/security/sanitize'
import { asId, permissionsOf, readList, sendJson, type Permissions } from '../api'
import { AddButton, Banners, Dialog, fieldClass, messageFrom, RowActions, Screen, Table } from '../ui'

type Year = { id: number; name: string; start_date: string; end_date: string; is_current: boolean; description: string }
type Draft = Omit<Year, 'id'>

const empty: Draft = { name: '', start_date: '', end_date: '', is_current: false, description: '' }

function asYear(value: Partial<Year> | null | undefined): Year | null {
  const id = asId(value?.id)
  const name = safeText(value?.name, 50)
  if (!id || !name) return null
  return {
    id,
    name,
    start_date: safeText(value?.start_date, 10),
    end_date: safeText(value?.end_date, 10),
    is_current: value?.is_current === true,
    description: safeText(value?.description, 4000),
  }
}

export function YearsPage() {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<Year[]>([])
  const [permissions, setPermissions] = useState<Permissions>({ add: false, change: false, delete: false })
  const [editor, setEditor] = useState<{ id: number | null; draft: Draft } | null>(null)
  const [pending, setPending] = useState<Year | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  async function load() {
    const data = await readList<{ years?: Partial<Year>[] }>('/api/academic-years')
    setRows((data.years || []).map(asYear).filter((row): row is Year => row !== null))
    setPermissions(permissionsOf(data.permissions))
  }

  useEffect(() => { setPageHeader('Academic Years') }, [setPageHeader])
  useEffect(() => { void load().catch((reason: unknown) => setError(messageFrom(reason))).finally(() => setLoading(false)) }, [])

  async function onSave(event: FormEvent) {
    event.preventDefault()
    if (!editor) return
    setSaving(true)
    setError('')
    try {
      await sendJson(editor.id ? 'PUT' : 'POST', editor.id ? `/api/academic-years/${editor.id}` : '/api/academic-years', editor.draft)
      setNotice(editor.id ? 'Academic year updated.' : 'Academic year added.')
      setEditor(null)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  async function onDelete() {
    if (!pending) return
    setSaving(true)
    setError('')
    try {
      await sendJson('DELETE', `/api/academic-years/${pending.id}`)
      setNotice('Academic year deleted.')
      setPending(null)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Screen title="Academic Years" subtitle="Named periods used by semesters and batches" action={permissions.add ? <AddButton onClick={() => setEditor({ id: null, draft: empty })} /> : null}>
      <Banners error={error} notice={notice} />
      <Table headers={['Year', 'Dates', 'Current', 'Actions']} count={rows.length} loading={loading} empty="No academic years found.">
        {rows.map((year) => (
          <tr key={year.id}>
            <td className="px-4 py-2 font-semibold text-gray-900">{year.name}</td>
            <td className="px-4 py-2 text-xs text-gray-600">{year.start_date} – {year.end_date}</td>
            <td className="px-4 py-2">{year.is_current ? <span className="rounded bg-green-100 px-2 py-0.5 text-[10px] font-bold text-green-800">Current</span> : '—'}</td>
            <RowActions canChange={permissions.change} canDelete={permissions.delete} onEdit={() => setEditor({ id: year.id, draft: { name: year.name, start_date: year.start_date, end_date: year.end_date, is_current: year.is_current, description: year.description } })} onDelete={() => setPending(year)} />
          </tr>
        ))}
      </Table>
      {editor ? (
        <Dialog title={editor.id ? 'Edit Academic Year' : 'Add Academic Year'} onClose={() => setEditor(null)}>
          <form className="grid gap-4" onSubmit={(event) => void onSave(event)}>
            <label className="text-xs font-semibold text-gray-700">Name<input required maxLength={50} value={editor.draft.name} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, name: event.target.value } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold text-gray-700">Start<input required type="date" value={editor.draft.start_date} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, start_date: event.target.value } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold text-gray-700">End<input required type="date" value={editor.draft.end_date} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, end_date: event.target.value } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold text-gray-700">Description<textarea rows={3} maxLength={4000} value={editor.draft.description} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, description: event.target.value } })} className={fieldClass()} /></label>
            <label className="inline-flex items-center text-sm"><input type="checkbox" checked={editor.draft.is_current} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, is_current: event.target.checked } })} className="mr-2" />Current year</label>
            <button type="submit" disabled={saving} className="rounded bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-60">{saving ? 'Saving…' : 'Save'}</button>
          </form>
        </Dialog>
      ) : null}
      {pending ? (
        <Dialog title="Delete academic year?" onClose={() => setPending(null)}>
          <p className="text-sm text-gray-600">Delete {pending.name}? Years used by semesters or batches cannot be removed.</p>
          <button type="button" disabled={saving} className="mt-4 rounded bg-red-600 px-4 py-2 text-sm text-white" onClick={() => void onDelete()}>Delete</button>
        </Dialog>
      ) : null}
    </Screen>
  )
}
