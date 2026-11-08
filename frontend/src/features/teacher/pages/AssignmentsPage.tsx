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
      {error ? <p className="rounded-r-lg border-l-4 border-red-500 bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      <div className="min-h-[320px] overflow-hidden rounded-2xl border border-gray-200 bg-white">
        <div className="overflow-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
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
              {rows.length === 0 ? (
                <tr><td colSpan={5} className="px-4 py-16 text-center text-gray-500">No subjects are assigned yet.</td></tr>
              ) : rows.map((row) => (
                <tr key={`${row.subject}-${row.className}-${row.division}`} className="hover:bg-indigo-50/40">
                  <td className="px-4 py-3 font-semibold text-gray-800">{row.subject}</td>
                  <td className="px-4 py-3 text-gray-700">{row.department || '—'}</td>
                  <td className="px-4 py-3 text-gray-700">{row.className}{row.course ? ` · ${row.course}` : ''}</td>
                  <td className="px-4 py-3 text-gray-700">{row.division || '—'}</td>
                  <td className="px-4 py-3">{row.syllabus ? <a className="font-semibold text-indigo-600" href={row.syllabus} target="_blank" rel="noreferrer">Open</a> : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
