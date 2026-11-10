import { useEffect, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { useCapability } from '../../../shared/components/data-list'
import { safeCount, safeText } from '../../../shared/security/sanitize'
import { asId, readList, sendJson } from '../api'
import { Banners, Screen, fieldClass, messageFrom } from '../ui'

type Subject = { id: number; name: string; course_id: number | null }
type Outcome = { id: number; code: string; statement: string }
type ComponentRow = { id: number; name: string; max_marks: number; weight: number; kind: string; locked: boolean; outcome_codes: string[] }
type Link = { co_code: string; po_code: string; level: number }
type Figure = { code: string; statement: string; percent: number | null; level: number | null; students: number }
type Payload = {
  subjects?: { id?: unknown; name?: unknown; course_id?: unknown }[]
  subject?: { id?: unknown; course_id?: unknown } | null
  components?: Record<string, unknown>[]
  outcomes?: Record<string, unknown>[]
  program_outcomes?: Record<string, unknown>[]
  co_po?: Record<string, unknown>[]
  attainment?: { outcomes?: Record<string, unknown>[]; program_outcomes?: Record<string, unknown>[] }
  kinds?: unknown[]
  permissions?: { change?: boolean; lock?: boolean }
}
type MarkRow = { student_id: number; name: string; roll_number: string; marks: string }
type MarkPayload = { students?: Record<string, unknown>[]; can_change?: boolean; can_lock?: boolean; component?: { locked?: boolean }; import?: { saved?: unknown; unknown?: unknown[] } }

const kindsFallback = ['IA', 'assignment', 'practical', 'viva', 'project']

async function encodeBase64(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000))
  return btoa(binary)
}

function text(value: unknown, limit: number) {
  return safeText(value, limit)
}

function outcomeOf(row: Record<string, unknown>): Outcome | null {
  const code = text(row.code, 12)
  const statement = text(row.statement, 300)
  if (!code || !statement) return null
  return { id: asId(row.id), code, statement }
}

function componentOf(row: Record<string, unknown>): ComponentRow | null {
  const name = text(row.name, 80)
  if (!asId(row.id) || !name) return null
  const codes = Array.isArray(row.outcome_codes) ? row.outcome_codes.map((code) => text(code, 12)).filter(Boolean) : []
  return {
    id: asId(row.id), name, max_marks: Number(row.max_marks) || 0, weight: Number(row.weight) || 0,
    kind: text(row.kind, 20) || 'IA', locked: row.locked === true, outcome_codes: codes,
  }
}

function figureOf(row: Record<string, unknown>): Figure | null {
  const code = text(row.code, 12)
  if (!code) return null
  return {
    code, statement: text(row.statement, 300),
    percent: row.percent == null ? null : Number(row.percent),
    level: row.level == null ? null : safeCount(row.level),
    students: safeCount(row.students),
  }
}

export function AssessmentPage() {
  const setPageHeader = useSetPageHeader()
  const enabled = useCapability('assessments')
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [subjectId, setSubjectId] = useState(0)
  const [courseId, setCourseId] = useState(0)
  const [outcomes, setOutcomes] = useState<Outcome[]>([])
  const [components, setComponents] = useState<ComponentRow[]>([])
  const [programs, setPrograms] = useState<Outcome[]>([])
  const [links, setLinks] = useState<Link[]>([])
  const [coFigures, setCoFigures] = useState<Figure[]>([])
  const [poFigures, setPoFigures] = useState<Figure[]>([])
  const [kindChoices, setKindChoices] = useState<string[]>(kindsFallback)
  const [canChange, setCanChange] = useState(false)
  const [componentId, setComponentId] = useState(0)
  const [marks, setMarks] = useState<MarkRow[]>([])
  const [marksLocked, setMarksLocked] = useState(false)
  const [canEditMarks, setCanEditMarks] = useState(false)
  const [canLock, setCanLock] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)

  function apply(data: Payload, chosen: number) {
    const nextSubjects = (data.subjects || []).map((row) => ({
      id: asId(row.id), name: text(row.name, 140), course_id: asId(row.course_id) || null,
    })).filter((row) => row.id > 0 && row.name)
    setSubjects(nextSubjects)
    const nextId = asId(data.subject?.id) || chosen || nextSubjects[0]?.id || 0
    setSubjectId(nextId)
    setCourseId(asId(data.subject?.course_id))
    setOutcomes((data.outcomes || []).map(outcomeOf).filter((row): row is Outcome => row !== null))
    setComponents((data.components || []).map(componentOf).filter((row): row is ComponentRow => row !== null))
    setPrograms((data.program_outcomes || []).map(outcomeOf).filter((row): row is Outcome => row !== null))
    setLinks((data.co_po || []).map((row) => ({
      co_code: text(row.co_code, 12), po_code: text(row.po_code, 12), level: safeCount(row.level) || 1,
    })).filter((row) => row.co_code && row.po_code))
    setCoFigures((data.attainment?.outcomes || []).map(figureOf).filter((row): row is Figure => row !== null))
    setPoFigures((data.attainment?.program_outcomes || []).map(figureOf).filter((row): row is Figure => row !== null))
    const kinds = (data.kinds || []).map((item) => text(item, 20)).filter(Boolean)
    if (kinds.length) setKindChoices(kinds)
    setCanChange(data.permissions?.change === true)
    setCanLock(data.permissions?.lock === true)
  }

  async function load(chosen = subjectId) {
    const path = chosen ? `/api/assessments?subject_id=${chosen}` : '/api/assessments'
    apply(await apiRequest<Payload>(path), chosen)
  }

  async function loadMarks(id: number) {
    if (!id) {
      setMarks([])
      return
    }
    const data = await readList<MarkPayload>(`/api/assessments/components/${id}/marks`)
    setMarks((data.students || []).map((row) => ({
      student_id: asId(row.student_id),
      name: text(row.name, 100),
      roll_number: text(row.roll_number, 50),
      marks: row.marks == null ? '' : String(row.marks),
    })).filter((row) => row.student_id > 0))
    setMarksLocked(data.component?.locked === true)
    setCanEditMarks(data.can_change === true)
    setCanLock(data.can_lock === true)
  }

  useEffect(() => { setPageHeader('Internals') }, [setPageHeader])
  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    let live = true
    setLoading(true)
    load().then(() => { if (live) setLoading(false) }).catch((reason) => { if (live) { setError(messageFrom(reason)); setLoading(false) } })
    return () => { live = false }
    // The first load picks the first subject the API returns.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled])

  useEffect(() => {
    if (!enabled || !componentId) return
    let live = true
    loadMarks(componentId).catch((reason) => { if (live) setError(messageFrom(reason)) })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [componentId, enabled])

  async function save(path: string, payload: object, done: string) {
    setError('')
    setNotice('')
    try {
      apply(await sendJson<Payload>('PUT', path, payload), subjectId)
      setNotice(done)
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function saveMarks() {
    setError('')
    setNotice('')
    try {
      await sendJson('PUT', `/api/assessments/components/${componentId}/marks`, {
        marks: marks.map((row) => ({ student_id: row.student_id, marks: row.marks.trim() === '' ? null : Number(row.marks) })),
      })
      setNotice('Marks saved.')
      await load(subjectId)
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function lock(locked: boolean) {
    setError('')
    setNotice('')
    try {
      await sendJson('POST', `/api/assessments/components/${componentId}/${locked ? 'lock' : 'unlock'}`)
      setNotice(locked ? 'Marks locked. Students can see them.' : 'Marks unlocked.')
      await loadMarks(componentId)
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  async function importCsv(file: File) {
    setError('')
    setNotice('')
    try {
      const name = file.name.toLowerCase()
      const payload = name.endsWith('.xlsx') ? { xlsx_base64: await encodeBase64(file) } : { csv: await file.text() }
      const data = await sendJson<MarkPayload>('POST', `/api/assessments/components/${componentId}/import`, payload)
      const unknown = (data.import?.unknown || []).map((roll) => text(roll, 50)).filter(Boolean)
      setNotice(`Imported ${safeCount(data.import?.saved)} row${safeCount(data.import?.saved) === 1 ? '' : 's'}.${unknown.length ? ` Unknown rolls: ${unknown.join(', ')}` : ''}`)
      await loadMarks(componentId)
      await load(subjectId)
    } catch (reason) {
      setError(messageFrom(reason))
    }
  }

  const input = fieldClass()
  return (
    <Screen title="Internal assessment" subtitle={enabled ? 'Components, outcomes and attainment. Students see marks only after a component is locked.' : 'Turn on Internal assessment under Settings → Capabilities.'}>
      <Banners error={error} notice={notice} />
      {!enabled || loading ? null : (
        <div className="space-y-4">
          <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <label className="block text-xs font-bold text-gray-500">Subject
              <select className={input} value={subjectId || ''} onChange={(event) => { const id = Number(event.target.value); setSubjectId(id); setComponentId(0); void load(id).catch((reason) => setError(messageFrom(reason))) }}>
                {subjects.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
              </select>
            </label>
          </section>
          <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-bold text-gray-800">Course outcomes</h3>
              {canChange ? <button type="button" className="text-xs font-bold text-indigo-700" onClick={() => setOutcomes([...outcomes, { id: 0, code: '', statement: '' }])}>Add</button> : null}
            </div>
            {outcomes.map((row, index) => (
              <div key={`${row.id}-${index}`} className="mb-2 grid gap-2 md:grid-cols-[8rem_1fr_auto]">
                <input className={input} disabled={!canChange} value={row.code} placeholder="CO1" onChange={(event) => setOutcomes(outcomes.map((item, at) => at === index ? { ...item, code: event.target.value } : item))} />
                <input className={input} disabled={!canChange} value={row.statement} placeholder="Statement" onChange={(event) => setOutcomes(outcomes.map((item, at) => at === index ? { ...item, statement: event.target.value } : item))} />
                {canChange ? <button type="button" className="text-xs text-gray-500" onClick={() => setOutcomes(outcomes.filter((_, at) => at !== index))}>Remove</button> : null}
              </div>
            ))}
            {canChange ? <button type="button" className="mt-2 rounded bg-indigo-600 px-3 py-1.5 text-xs text-white" onClick={() => void save(`/api/assessments/subjects/${subjectId}/outcomes`, { outcomes: outcomes.map(({ code, statement }) => ({ code, statement })) }, 'Course outcomes saved.')}>Save outcomes</button> : null}
          </section>
          <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-bold text-gray-800">Components</h3>
              {canChange ? <button type="button" className="text-xs font-bold text-indigo-700" onClick={() => setComponents([...components, { id: 0, name: '', max_marks: 20, weight: 0, kind: 'IA', locked: false, outcome_codes: [] }])}>Add</button> : null}
            </div>
            {components.map((row, index) => (
              <div key={`${row.id}-${index}`} className="mb-2 grid gap-2 md:grid-cols-[1fr_8rem_6rem_6rem_8rem_auto]">
                <input className={input} disabled={!canChange || row.locked} value={row.name} placeholder="Name" onChange={(event) => setComponents(components.map((item, at) => at === index ? { ...item, name: event.target.value } : item))} />
                <select className={input} disabled={!canChange || row.locked} value={row.kind} onChange={(event) => setComponents(components.map((item, at) => at === index ? { ...item, kind: event.target.value } : item))}>
                  {kindChoices.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
                </select>
                <input className={input} disabled={!canChange || row.locked} value={row.max_marks} onChange={(event) => setComponents(components.map((item, at) => at === index ? { ...item, max_marks: Number(event.target.value) } : item))} />
                <input className={input} disabled={!canChange || row.locked} value={row.weight} onChange={(event) => setComponents(components.map((item, at) => at === index ? { ...item, weight: Number(event.target.value) } : item))} />
                <input className={input} disabled={!canChange || row.locked} value={row.outcome_codes.join(' ')} placeholder="CO1 CO2" onChange={(event) => setComponents(components.map((item, at) => at === index ? { ...item, outcome_codes: event.target.value.split(/[\s,]+/).filter(Boolean) } : item))} />
                {canChange && !row.locked ? <button type="button" className="text-xs text-gray-500" onClick={() => setComponents(components.filter((_, at) => at !== index))}>Remove</button> : <span className="text-xs text-gray-400">{row.locked ? 'Locked' : ''}</span>}
              </div>
            ))}
            {canChange ? <button type="button" className="mt-2 rounded bg-indigo-600 px-3 py-1.5 text-xs text-white" onClick={() => void save(`/api/assessments/subjects/${subjectId}/components`, { components: components.map((row) => ({ id: row.id || undefined, name: row.name, kind: row.kind, max_marks: row.max_marks, weight: row.weight, outcome_codes: row.outcome_codes })) }, 'Components saved.')}>Save components</button> : null}
          </section>
          <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-bold text-gray-800">Program outcomes</h3>
              {canChange ? <button type="button" className="text-xs font-bold text-indigo-700" onClick={() => setPrograms([...programs, { id: 0, code: '', statement: '' }])}>Add</button> : null}
            </div>
            {programs.map((row, index) => (
              <div key={`${row.id}-${index}`} className="mb-2 grid gap-2 md:grid-cols-[8rem_1fr_auto]">
                <input className={input} disabled={!canChange} value={row.code} placeholder="PO1" onChange={(event) => setPrograms(programs.map((item, at) => at === index ? { ...item, code: event.target.value } : item))} />
                <input className={input} disabled={!canChange} value={row.statement} placeholder="Statement" onChange={(event) => setPrograms(programs.map((item, at) => at === index ? { ...item, statement: event.target.value } : item))} />
                {canChange ? <button type="button" className="text-xs text-gray-500" onClick={() => setPrograms(programs.filter((_, at) => at !== index))}>Remove</button> : null}
              </div>
            ))}
            {canChange && courseId ? <button type="button" className="mt-2 rounded bg-indigo-600 px-3 py-1.5 text-xs text-white" onClick={() => void sendJson('PUT', `/api/assessments/courses/${courseId}/outcomes`, { outcomes: programs.map(({ code, statement }) => ({ code, statement })) }).then(() => load(subjectId)).then(() => setNotice('Program outcomes saved.')).catch((reason) => setError(messageFrom(reason)))}>Save program outcomes</button> : null}
            <div className="mt-4">
              <h3 className="mb-2 text-sm font-bold text-gray-800">CO to PO map</h3>
              {links.map((row, index) => (
                <div key={`${row.co_code}-${index}`} className="mb-2 grid gap-2 md:grid-cols-[8rem_8rem_6rem_auto]">
                  <input className={input} disabled={!canChange} value={row.co_code} placeholder="CO1" onChange={(event) => setLinks(links.map((item, at) => at === index ? { ...item, co_code: event.target.value } : item))} />
                  <input className={input} disabled={!canChange} value={row.po_code} placeholder="PO1" onChange={(event) => setLinks(links.map((item, at) => at === index ? { ...item, po_code: event.target.value } : item))} />
                  <select className={input} disabled={!canChange} value={row.level} onChange={(event) => setLinks(links.map((item, at) => at === index ? { ...item, level: Number(event.target.value) } : item))}>
                    {[1, 2, 3].map((level) => <option key={level} value={level}>{level}</option>)}
                  </select>
                  {canChange ? <button type="button" className="text-xs text-gray-500" onClick={() => setLinks(links.filter((_, at) => at !== index))}>Remove</button> : null}
                </div>
              ))}
              {canChange ? <button type="button" className="mr-2 text-xs font-bold text-indigo-700" onClick={() => setLinks([...links, { co_code: outcomes[0]?.code || '', po_code: programs[0]?.code || '', level: 1 }])}>Add link</button> : null}
              {canChange ? <button type="button" className="rounded bg-indigo-600 px-3 py-1.5 text-xs text-white" onClick={() => void save(`/api/assessments/subjects/${subjectId}/map`, { links }, 'Mapping saved.')}>Save map</button> : null}
            </div>
          </section>
          <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <h3 className="mb-2 text-sm font-bold text-gray-800">Attainment</h3>
            <ul className="space-y-1 text-sm text-gray-700">
              {coFigures.map((row) => <li key={`co-${row.code}`}>{row.code}: {row.percent == null ? '—' : `${row.percent}%`} · level {row.level ?? '—'} · {row.students} students</li>)}
              {poFigures.map((row) => <li key={`po-${row.code}`}>{row.code}: {row.percent == null ? '—' : `${row.percent}%`} · level {row.level ?? '—'}</li>)}
              {!coFigures.length && !poFigures.length ? <li className="text-gray-400">No outcomes yet.</li> : null}
            </ul>
          </section>
          <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <h3 className="mb-2 text-sm font-bold text-gray-800">Marks</h3>
            <select className={input} value={componentId || ''} onChange={(event) => setComponentId(Number(event.target.value))}>
              <option value="">Choose a component</option>
              {components.filter((row) => row.id).map((row) => <option key={row.id} value={row.id}>{row.name}{row.locked ? ' (locked)' : ''}</option>)}
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
                        <td><input className={input} disabled={!canEditMarks} value={row.marks} onChange={(event) => setMarks(marks.map((item) => item.student_id === row.student_id ? { ...item, marks: event.target.value } : item))} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="mt-3 flex flex-wrap gap-2">
                  {canEditMarks ? <button type="button" className="rounded bg-indigo-600 px-3 py-1.5 text-xs text-white" onClick={() => void saveMarks()}>Save marks</button> : null}
                  {canLock ? <button type="button" className="rounded border border-gray-300 px-3 py-1.5 text-xs" onClick={() => void lock(!marksLocked)}>{marksLocked ? 'Unlock' : 'Lock'}</button> : null}
                  {canEditMarks ? <label className="cursor-pointer rounded border border-gray-300 px-3 py-1.5 text-xs">Import CSV or Excel<input type="file" accept=".csv,.xlsx,text/csv" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importCsv(file); event.target.value = '' }} /></label> : null}
                </div>
              </>
            ) : null}
          </section>
        </div>
      )}
    </Screen>
  )
}
