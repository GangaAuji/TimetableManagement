import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { ListTable, displayValue, messageFrom, type DataRow } from '../../../shared/components/data-list'
import { safeText } from '../../../shared/security/sanitize'

export function FacultySessionsPage() {
  const { facultyId } = useParams()
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<DataRow[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    setPageHeader('Faculty timetable')
    void apiRequest<{ name?: unknown; sessions?: Record<string, unknown>[] }>(`/api/faculty/${facultyId}/sessions`)
      .then((data) => {
        setPageHeader(safeText(data.name, 100) || 'Faculty timetable')
        setRows((data.sessions || []).map((row) => ({
          day: displayValue(row.day),
          start_time: displayValue(row.start_time),
          end_time: displayValue(row.end_time),
          subject: displayValue(row.subject),
          class_name: displayValue(row.class_name),
          division_name: displayValue(row.division_name),
          room: displayValue(row.room),
        })))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [facultyId, setPageHeader])
  return (
    <section className="flex flex-col gap-2">
      <a href="/admin/faculty" className="text-xs font-bold text-emerald-700">Back to faculty</a>
      {error && <p className="text-xs text-red-700">{error}</p>}
      <ListTable columns={[{ key: 'day', label: 'Day' }, { key: 'start_time', label: 'Start' }, { key: 'end_time', label: 'End' }, { key: 'subject', label: 'Subject' }, { key: 'class_name', label: 'Class' }, { key: 'division_name', label: 'Division' }, { key: 'room', label: 'Room' }]} rows={rows} />
    </section>
  )
}
