import { FailureNotice } from '../../../shared/components/success-notice'
import { useEffect, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { messageFrom } from '../../../shared/components/data-list'
import { safeText } from '../../../shared/security/sanitize'

type Assignment = {
  subject: string
  department: string
  course: string
  className: string
  division: string
  syllabus: string
}

function readAssignment(row: Record<string, unknown>): Assignment {
  const syllabus = safeText(row.syllabus_url, 300)
  return {
    subject: safeText(row.subject, 100),
    department: safeText(row.department, 100),
    course: safeText(row.course, 100),
    className: safeText(row.class_name, 100),
    division: safeText(row.division, 50),
    syllabus: syllabus.startsWith('https://') ? syllabus : '',
  }
}

export function AssignmentsPage() {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<Assignment[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    setPageHeader('Assigned subjects')
    void apiRequest<Record<string, unknown>>('/api/portal/assignments')
      .then((data) => {
        const source = Array.isArray(data.assignments) ? data.assignments : []
        setRows(source.map((item) => readAssignment(item as Record<string, unknown>)))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [setPageHeader])

  return (
    <section className="flex flex-1 flex-col gap-2">
      <p className="text-sm text-gray-500">Subjects allocated to you, with their class and division.</p>
      <FailureNotice message={error} />
      {rows.length === 0 && !error ? (
        <p className="rounded-2xl border border-gray-200 bg-white px-4 py-10 text-center text-sm text-gray-500">No subjects are assigned yet.</p>
      ) : (
        <>
          <ul className="grid gap-2 md:hidden">
            {rows.map((row) => (
              <li key={`${row.subject}-${row.className}-${row.division}`} className="rounded-2xl border border-gray-200 bg-white p-4">
                <p className="font-bold text-gray-800">{row.subject}</p>
                <p className="mt-1 text-sm text-gray-600">{row.className}{row.course ? ` · ${row.course}` : ''}</p>
                <p className="text-xs text-gray-500">{row.department || 'No department'} · Div {row.division || '—'}</p>
                {row.syllabus ? <a className="mt-2 inline-flex text-sm font-semibold text-gray-800 underline" href={row.syllabus} target="_blank" rel="noreferrer">Open syllabus</a> : null}
              </li>
            ))}
          </ul>
          <div className="hidden min-h-[320px] overflow-hidden rounded-2xl border border-gray-200 bg-white md:block">
            <div className="overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-50 text-[10px] font-bold tracking-wider text-gray-400 uppercase">
                  <tr>
                    <th className="px-4 py-3">Subject</th>
                    <th className="px-4 py-3">Department</th>
                    <th className="px-4 py-3">Class / course</th>
                    <th className="px-4 py-3">Division</th>
                    <th className="px-4 py-3">Syllabus</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {rows.map((row) => (
                    <tr key={`${row.subject}-${row.className}-${row.division}`}>
                      <td className="px-4 py-3 font-semibold text-gray-800">{row.subject}</td>
                      <td className="px-4 py-3 text-gray-700">{row.department || '—'}</td>
                      <td className="px-4 py-3 text-gray-700">{row.className}{row.course ? ` · ${row.course}` : ''}</td>
                      <td className="px-4 py-3 text-gray-700">{row.division || '—'}</td>
                      <td className="px-4 py-3">{row.syllabus ? <a className="font-semibold text-gray-800 underline" href={row.syllabus} target="_blank" rel="noreferrer">Open</a> : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  )
}
