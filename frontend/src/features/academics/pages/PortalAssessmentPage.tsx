import { useEffect, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { messageFrom, useCapability, useSessionRole } from '../../../shared/components/data-list'
import { safeText } from '../../../shared/security/sanitize'
import { asId, readList, sendJson } from '../api'
import { Banners, Screen, fieldClass } from '../ui'

type StudentSubject = { subject_id: number; name: string; code: string; components: { name: string; kind: string; max_marks: number; marks: number }[] }
type TeacherComponent = { id: number; name: string; locked: boolean; max_marks: number }
type TeacherSubject = { id: number; name: string; components: TeacherComponent[] }
type MarkRow = { student_id: number; name: string; roll_number: string; marks: string }

export function InternalsRoute() {
  const role = useSessionRole()
  if (role === 'Teacher') return <TeacherInternalsPage />
  return <StudentInternalsPage />
}

export function StudentInternalsPage() {
  const setPageHeader = useSetPageHeader()
  const enabled = useCapability('assessments')
  const [subjects, setSubjects] = useState<StudentSubject[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => { setPageHeader('Internals') }, [setPageHeader])
  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    let live = true
    readList<{ subjects?: Record<string, unknown>[] }>('/api/portal/student/assessments')
      .then((data) => {
        if (!live) return
        setSubjects((data.subjects || []).map((row) => ({
          subject_id: asId(row.subject_id),
          name: safeText(row.name, 100),
          code: safeText(row.code, 20),
          components: Array.isArray(row.components) ? row.components.map((item) => ({
            name: safeText((item as Record<string, unknown>).name, 80),
            kind: safeText((item as Record<string, unknown>).kind, 20),
            max_marks: Number((item as Record<string, unknown>).max_marks) || 0,
            marks: Number((item as Record<string, unknown>).marks) || 0,
          })) : [],
        })).filter((row) => row.subject_id > 0))
      })
      .catch((reason) => { if (live) setError(messageFrom(reason)) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [enabled])

  return (
    <Screen title="Internal marks" subtitle={enabled ? 'Marks appear here after the component is locked.' : 'Internal assessment is switched off.'}>
      <Banners error={error} notice="" />
      {loading || !enabled ? null : subjects.length === 0 ? <p className="text-sm text-gray-500">No locked marks yet.</p> : (
        <div className="space-y-3">
          {subjects.map((subject) => (
            <section key={subject.subject_id} className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <h3 className="text-sm font-bold text-gray-800">{subject.code} {subject.name}</h3>
              <ul className="mt-2 space-y-1 text-sm text-gray-700">
                {subject.components.map((row) => <li key={row.name}>{row.name} ({row.kind}): {row.marks} / {row.max_marks}</li>)}
              </ul>
            </section>
          ))}
        </div>
      )}
    </Screen>
  )
}

export function TeacherInternalsPage() {
  const setPageHeader = useSetPageHeader()
  const enabled = useCapability('assessments')
  const [subjects, setSubjects] = useState<TeacherSubject[]>([])
  const [componentId, setComponentId] = useState(0)
  const [marks, setMarks] = useState<MarkRow[]>([])
  const [canChange, setCanChange] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const input = fieldClass()

  useEffect(() => { setPageHeader('Internals') }, [setPageHeader])
  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    let live = true
    readList<{ subjects?: Record<string, unknown>[] }>('/api/portal/teacher/assessments')
      .then((data) => {
        if (!live) return
        setSubjects((data.subjects || []).map((row) => ({
          id: asId(row.id),
          name: safeText(row.name, 140),
          components: Array.isArray(row.components) ? row.components.map((item) => {
            const record = item as Record<string, unknown>
            return { id: asId(record.id), name: safeText(record.name, 80), locked: record.locked === true, max_marks: Number(record.max_marks) || 0 }
          }).filter((item) => item.id > 0) : [],
        })).filter((row) => row.id > 0))
      })
      .catch((reason) => { if (live) setError(messageFrom(reason)) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [enabled])

  useEffect(() => {
    if (!componentId) return
    let live = true
    readList<{ students?: Record<string, unknown>[]; can_change?: boolean }>(`/api/assessments/components/${componentId}/marks`)
      .then((data) => {
        if (!live) return
        setCanChange(data.can_change === true)
        setMarks((data.students || []).map((row) => ({
          student_id: asId(row.student_id),
          name: safeText(row.name, 100),
          roll_number: safeText(row.roll_number, 50),
          marks: row.marks == null ? '' : String(row.marks),
        })).filter((row) => row.student_id > 0))
      })
      .catch((reason) => { if (live) setError(messageFrom(reason)) })
    return () => { live = false }
  }, [componentId])

  async function save() {
    setError('')
    setNotice('')
    try {
      await sendJson('PUT', `/api/assessments/components/${componentId}/marks`, {
        marks: marks.map((row) => ({ student_id: row.student_id, marks: row.marks.trim() === '' ? null : Number(row.marks) })),
      })
      setNotice('Marks saved.')
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  const choices = subjects.flatMap((subject) => subject.components.map((row) => ({ ...row, subject: subject.name })))
  return (
    <Screen title="Internal marks" subtitle={enabled ? 'Enter marks for a subject you teach. Locking is done by the head of department.' : 'Internal assessment is switched off.'}>
      <Banners error={error} notice={notice} />
      {loading || !enabled ? null : choices.length === 0 ? <p className="text-sm text-gray-500">No components on your allocated subjects yet.</p> : (
        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <select className={input} value={componentId || ''} onChange={(event) => setComponentId(Number(event.target.value))}>
            <option value="">Choose a component</option>
            {choices.map((row) => <option key={row.id} value={row.id}>{row.subject} — {row.name}{row.locked ? ' (locked)' : ''}</option>)}
          </select>
          {componentId ? (
            <>
              <table className="mt-3 w-full text-sm">
                <thead><tr className="text-left text-xs text-gray-500"><th>Roll</th><th>Name</th><th>Marks</th></tr></thead>
                <tbody>
                  {marks.map((row) => (
                    <tr key={row.student_id}>
                      <td className="py-1">{row.roll_number}</td>
                      <td>{row.name}</td>
                      <td><input className={input} disabled={!canChange} value={row.marks} onChange={(event) => setMarks(marks.map((item) => item.student_id === row.student_id ? { ...item, marks: event.target.value } : item))} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {canChange ? <button type="button" className="mt-3 rounded bg-indigo-600 px-3 py-1.5 text-xs text-white" onClick={() => void save()}>Save marks</button> : null}
            </>
          ) : null}
        </section>
      )}
    </Screen>
  )
}
