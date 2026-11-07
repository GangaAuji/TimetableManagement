import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { safeText } from '../../../shared/security/sanitize'
import { asId, permissionsOf, readList, sendJson, type Permissions } from '../api'
import { AddButton, Banners, Dialog, fieldClass, messageFrom, RowActions, Screen, Table } from '../ui'

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const programs = ['UG', 'PG', 'Both'] as const

type Holiday = {
  id: number
  name: string
  holiday_date: string
  day_of_week: string
  applies_to_program: string
  is_recurring: boolean
}

type Draft = {
  name: string
  applies_to_program: 'UG' | 'PG' | 'Both'
  holiday_type: 'date' | 'weekly'
  holiday_date: string
  day_of_week: string
}

const empty: Draft = { name: '', applies_to_program: 'Both', holiday_type: 'date', holiday_date: '', day_of_week: 'Monday' }

function asHoliday(value: Partial<Holiday>): Holiday | null {
  const id = asId(value.id)
  const name = safeText(value.name, 120)
  if (!id || !name) return null
  return {
    id,
    name,
    holiday_date: safeText(value.holiday_date, 10),
    day_of_week: safeText(value.day_of_week, 20),
    applies_to_program: safeText(value.applies_to_program, 10),
    is_recurring: value.is_recurring === true,
  }
}

export function HolidaysPage() {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<Holiday[]>([])
  const [permissions, setPermissions] = useState<Permissions>({ add: false, change: false, delete: false })
  const [editor, setEditor] = useState<{ id: number | null; draft: Draft } | null>(null)
  const [pending, setPending] = useState<Holiday | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  async function load() {
    const data = await readList<{ holidays?: Partial<Holiday>[] }>('/api/holidays')
    setRows((data.holidays || []).map(asHoliday).filter((row): row is Holiday => row !== null))
    setPermissions(permissionsOf(data.permissions))
  }

  useEffect(() => { setPageHeader('Holidays') }, [setPageHeader])
  useEffect(() => { void load().catch((reason: unknown) => setError(messageFrom(reason))).finally(() => setLoading(false)) }, [])

  async function onSave(event: FormEvent) {
    event.preventDefault()
    if (!editor) return
    setSaving(true)
    setError('')
    try {
      await sendJson(editor.id ? 'PUT' : 'POST', editor.id ? `/api/holidays/${editor.id}` : '/api/holidays', editor.draft)
      setNotice(editor.id ? 'Holiday updated.' : 'Holiday added.')
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
    try {
      await sendJson('DELETE', `/api/holidays/${pending.id}`)
      setNotice('Holiday deleted.')
      setPending(null)
      await load()
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Screen title="Holidays" subtitle="Date-specific and weekly recurring holidays" action={permissions.add ? <AddButton onClick={() => setEditor({ id: null, draft: empty })} /> : null}>
      <Banners error={error} notice={notice} />
      <Table headers={['Holiday', 'When', 'Program', 'Actions']} count={rows.length} loading={loading} empty="No holidays found.">
        {rows.map((row) => (
          <tr key={row.id}>
            <td className="px-4 py-2 font-semibold">{row.name}</td>
            <td className="px-4 py-2 text-xs">{row.is_recurring ? `Every ${row.day_of_week}` : row.holiday_date}</td>
            <td className="px-4 py-2 text-xs">{row.applies_to_program}</td>
            <RowActions canChange={permissions.change} canDelete={permissions.delete} onEdit={() => setEditor({ id: row.id, draft: { name: row.name, applies_to_program: (programs.includes(row.applies_to_program as 'UG') ? row.applies_to_program : 'Both') as Draft['applies_to_program'], holiday_type: row.is_recurring ? 'weekly' : 'date', holiday_date: row.holiday_date, day_of_week: row.day_of_week || 'Monday' } })} onDelete={() => setPending(row)} />
          </tr>
        ))}
      </Table>
      {editor ? (
        <Dialog title={editor.id ? 'Edit Holiday' : 'Add Holiday'} onClose={() => setEditor(null)}>
          <form className="grid gap-4" onSubmit={(event) => void onSave(event)}>
            <label className="text-xs font-semibold">Name<input required maxLength={120} value={editor.draft.name} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, name: event.target.value } })} className={fieldClass()} /></label>
            <label className="text-xs font-semibold">Program<select value={editor.draft.applies_to_program} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, applies_to_program: event.target.value as Draft['applies_to_program'] } })} className={fieldClass()}>{programs.map((program) => <option key={program}>{program}</option>)}</select></label>
            <label className="text-xs font-semibold">Type<select value={editor.draft.holiday_type} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, holiday_type: event.target.value as Draft['holiday_type'] } })} className={fieldClass()}><option value="date">Specific date</option><option value="weekly">Weekly</option></select></label>
            {editor.draft.holiday_type === 'weekly' ? (
              <label className="text-xs font-semibold">Day<select value={editor.draft.day_of_week} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, day_of_week: event.target.value } })} className={fieldClass()}>{days.map((day) => <option key={day}>{day}</option>)}</select></label>
            ) : (
              <label className="text-xs font-semibold">Date<input required type="date" value={editor.draft.holiday_date} onChange={(event) => setEditor({ ...editor, draft: { ...editor.draft, holiday_date: event.target.value } })} className={fieldClass()} /></label>
            )}
            <button type="submit" disabled={saving} className="rounded bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-60">{saving ? 'Saving…' : 'Save'}</button>
          </form>
        </Dialog>
      ) : null}
      {pending ? <Dialog title="Delete holiday?" onClose={() => setPending(null)}><p className="text-sm text-gray-600">Delete {pending.name}?</p><button type="button" disabled={saving} className="mt-4 rounded bg-red-600 px-4 py-2 text-sm text-white" onClick={() => void onDelete()}>Delete</button></Dialog> : null}
    </Screen>
  )
}
