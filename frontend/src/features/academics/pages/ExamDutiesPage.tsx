import { useEffect, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { useCapability } from '../../../shared/components/data-list'
import { safeText } from '../../../shared/security/sanitize'
import { readList } from '../api'
import { Banners, Screen, messageFrom } from '../ui'

type Duty = { exam_name: string; subject_name: string; course_code: string; date: string; start: string; end: string; room_number: string; role: string }

export function ExamDutiesPage() {
  const setPageHeader = useSetPageHeader()
  const enabled = useCapability('exams')
  const [duties, setDuties] = useState<Duty[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => { setPageHeader('Exam duties') }, [setPageHeader])
  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    let cancel = false
    readList<{ duties?: Record<string, unknown>[] }>('/api/portal/teacher/exams')
      .then((data) => {
        if (cancel) return
        setDuties((data.duties || []).map((row) => ({
          exam_name: safeText(row.exam_name, 80),
          subject_name: safeText(row.subject_name, 100),
          course_code: safeText(row.course_code, 20),
          date: safeText(row.date, 10),
          start: safeText(row.start, 8),
          end: safeText(row.end, 8),
          room_number: safeText(row.room_number, 20),
          role: safeText(row.role, 20),
        })).filter((row) => row.exam_name && row.date))
      })
      .catch((reason) => { if (!cancel) setError(messageFrom(reason)) })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [enabled])

  return (
    <Screen title="Exam duties" subtitle={enabled ? 'Rooms you are invigilating.' : 'Turn on Exam timetable under Settings → Capabilities.'}>
      <Banners error={error} notice="" />
      {!enabled || loading ? null : duties.length ? (
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="text-gray-500">
              <th className="px-4 py-2">Date</th>
              <th className="py-2">Time</th>
              <th className="py-2">Exam</th>
              <th className="py-2">Paper</th>
              <th className="py-2">Room</th>
              <th className="py-2 pr-4">Role</th>
            </tr>
          </thead>
          <tbody>
            {duties.map((row) => (
              <tr key={`${row.date}-${row.start}-${row.room_number}-${row.subject_name}`} className="border-t border-gray-100">
                <td className="px-4 py-2">{row.date}</td>
                <td className="py-2">{row.start}–{row.end}</td>
                <td className="py-2">{row.exam_name}</td>
                <td className="py-2">{row.course_code ? `${row.course_code} ` : ''}{row.subject_name}</td>
                <td className="py-2">{row.room_number}</td>
                <td className="py-2 pr-4">{row.role}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="px-4 pb-4 text-xs text-gray-500">No invigilation duties.</p>}
    </Screen>
  )
}
