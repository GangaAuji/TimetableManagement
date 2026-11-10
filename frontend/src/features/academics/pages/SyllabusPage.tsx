import { useEffect, useState, type FormEvent } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { useCapability } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { asId, permissionsOf, readList, sendJson, type Option, type Permissions } from '../api'
import { AddButton, Banners, Dialog, fieldClass, messageFrom, RowActions, Screen, Table } from '../ui'

type Unit = {
  id: number
  unit_no: number
  title: string
  planned_hours: number
  delivered_hours: number
  percent: number | null
  expected_hours: number | null
  pace: string
}
type Draft = { id: number | null; unit_no: string; title: string; planned_hours: string }
type Coverage = {
  subject_id?: number
  subject_name?: string
  elapsed_weeks?: number | null
  total_weeks?: number | null
  units?: Partial<Unit>[]
}
type Payload = { subjects?: Option[]; coverage?: Coverage | null; permissions?: Partial<Permissions> }

const empty: Draft = { id: null, unit_no: '', title: '', planned_hours: '' }
const paceLabel: Record<string, string> = { behind: 'Behind', ahead: 'Ahead', on_track: 'On track', no_pace: '—' }

function asUnit(value: Partial<Unit> | null | undefined): Unit | null {
  const id = asId(value?.id)
  const title = safeText(value?.title, 120)
  if (!id || !title) return null
  const pace = safeText(value?.pace, 20)
  return {
    id,
    unit_no: safeCount(value?.unit_no),
    title,
    planned_hours: Number(value?.planned_hours) || 0,
    delivered_hours: Number(value?.delivered_hours) || 0,
    percent: value?.percent == null ? null : Number(value.percent),
    expected_hours: value?.expected_hours == null ? null : Number(value.expected_hours),
    pace: paceLabel[pace] ? pace : 'no_pace',
  }
}

export function SyllabusPage() {
  const setPageHeader = useSetPageHeader()
  const enabled = useCapability('syllabus')
  const [subjects, setSubjects] = useState<Option[]>([])
  const [subjectId, setSubjectId] = useState(0)
  const [rows, setRows] = useState<Unit[]>([])
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [total, setTotal] = useState<number | null>(null)
  const [permissions, setPermissions] = useState<Permissions>({ add: false, change: false, delete: false })
  const [editor, setEditor] = useState<Draft | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  function apply(data: Payload, chosen: number) {
    const coverage = data.coverage
    const nextId = asId(coverage?.subject_id) || chosen
    setSubjectId(nextId)
    setRows((coverage?.units || []).map(asUnit).filter((row): row is Unit => row !== null))
    setElapsed(coverage?.elapsed_weeks == null ? null : safeCount(coverage.elapsed_weeks))
    setTotal(coverage?.total_weeks == null ? null : safeCount(coverage.total_weeks))
    setPermissions(permissionsOf(data.permissions))
    setSubjects((data.subjects || []).map((item) => ({ id: asId(item.id), name: safeText(item.name, 140) })).filter((item) => item.id > 0 && item.name))
  }

  async function load(chosen = subjectId) {
    const path = chosen ? `/api/syllabus?subject_id=${chosen}` : '/api/syllabus'
    apply(await readList<Payload>(path), chosen)
  }

  useEffect(() => { setPageHeader('Syllabus') }, [setPageHeader])
  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    let gone = false
    load(0).catch((cause: unknown) => { if (!gone) setError(messageFrom(cause)) }).finally(() => { if (!gone) setLoading(false) })
    return () => { gone = true }
  }, [enabled])

  async function choose(next: number) {
    setError('')
    setLoading(true)
    try {
      await load(next)
    } catch (cause) {
      setError(messageFrom(cause))
    } finally {
      setLoading(false)
    }
  }

  function payloadFrom(next: Unit[], draft: Draft | null, removeId: number | null) {
    const units: { id?: number; unit_no: number; title: string; planned_hours: number }[] = next.filter((row) => row.id !== removeId).map((row) => ({
      id: row.id,
      unit_no: row.unit_no,
      title: row.title,
      planned_hours: row.planned_hours,
    }))
    if (draft) {
      const item = { unit_no: Number(draft.unit_no), title: draft.title.trim(), planned_hours: Number(draft.planned_hours) }
      if (draft.id) {
        const index = units.findIndex((row) => row.id === draft.id)
        if (index >= 0) units[index] = { ...units[index], ...item }
      } else {
        units.push(item)
      }
    }
    return { units }
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!editor || !subjectId) return
    setSaving(true)
    setError('')
    try {
      const saved = await sendJson<{ coverage?: Coverage }>('PUT', `/api/syllabus/${subjectId}`, payloadFrom(rows, editor, null))
      apply({ subjects, coverage: saved.coverage, permissions }, subjectId)
      setEditor(null)
      setNotice('Syllabus saved.')
    } catch (cause) {
      setError(messageFrom(cause))
    } finally {
      setSaving(false)
    }
  }

  async function remove(unit: Unit) {
    setError('')
    try {
      const saved = await sendJson<{ coverage?: Coverage }>('PUT', `/api/syllabus/${subjectId}`, payloadFrom(rows, null, unit.id))
      apply({ subjects, coverage: saved.coverage, permissions }, subjectId)
      setNotice('Unit removed.')
    } catch (cause) {
      setError(messageFrom(cause))
    }
  }

  const pace = elapsed != null && total ? `${elapsed} of ${total} teaching weeks elapsed` : 'No teaching calendar, so pace is not compared to the week.'

  return (
    <Screen title="Syllabus coverage" subtitle={enabled ? pace : 'Turn on Syllabus coverage under Settings → Capabilities.'} action={enabled && permissions.change ? <AddButton onClick={() => setEditor(empty)} /> : undefined}>
      {!enabled ? null : (
        <>
          <Banners error={error} notice={notice} />
          <label className="block max-w-md text-xs font-semibold text-gray-500">Subject
            <select value={subjectId || ''} onChange={(event) => void choose(Number(event.target.value))} className={fieldClass()}>
              {subjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <Table headers={['Unit', 'Title', 'Planned', 'Delivered', '%', 'Pace', 'Actions']} count={rows.length} loading={loading} empty="No units yet.">
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="px-4 py-2">{row.unit_no}</td>
                <td className="px-4 py-2">{row.title}</td>
                <td className="px-4 py-2">{row.planned_hours}</td>
                <td className="px-4 py-2">{row.delivered_hours}</td>
                <td className="px-4 py-2">{row.percent == null ? '—' : row.percent}</td>
                <td className="px-4 py-2">{paceLabel[row.pace] || '—'}</td>
                <RowActions canChange={permissions.change} canDelete={permissions.change} onEdit={() => setEditor({ id: row.id, unit_no: String(row.unit_no), title: row.title, planned_hours: String(row.planned_hours) })} onDelete={() => void remove(row)} />
              </tr>
            ))}
          </Table>
          {editor ? (
            <Dialog title={editor.id ? 'Edit unit' : 'Add unit'} onClose={() => setEditor(null)}>
              <form className="flex flex-col gap-3" onSubmit={(event) => void save(event)}>
                <label className="text-xs font-semibold text-gray-500">Unit number
                  <input required value={editor.unit_no} onChange={(event) => setEditor({ ...editor, unit_no: event.target.value })} className={fieldClass()} inputMode="numeric" />
                </label>
                <label className="text-xs font-semibold text-gray-500">Title
                  <input required maxLength={120} value={editor.title} onChange={(event) => setEditor({ ...editor, title: event.target.value })} className={fieldClass()} />
                </label>
                <label className="text-xs font-semibold text-gray-500">Planned hours
                  <input required value={editor.planned_hours} onChange={(event) => setEditor({ ...editor, planned_hours: event.target.value })} className={fieldClass()} inputMode="decimal" />
                </label>
                <button type="submit" disabled={saving} className="rounded bg-indigo-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">{saving ? 'Saving…' : 'Save'}</button>
              </form>
            </Dialog>
          ) : null}
        </>
      )}
    </Screen>
  )
}
