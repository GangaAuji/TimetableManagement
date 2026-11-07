import { useEffect, useState } from 'react'
import { useSetPageHeader } from '../../../app/page-header'
import { apiRequest } from '../../../shared/api/client'
import { DirectoryFrame, displayValue, messageFrom, type DataColumn, type DataRow } from '../../../shared/components/data-list'

const columns: DataColumn[] = [
  { key: 'date', label: 'Date' },
  { key: 'original_faculty', label: 'Faculty' },
  { key: 'proxy_faculty', label: 'Proxy' },
  { key: 'subject', label: 'Subject' },
  { key: 'class_name', label: 'Class' },
  { key: 'status', label: 'Status' },
  { key: 'approval', label: 'Approval' },
]

function useEntries(title: string, path: string, columns: DataColumn[]) {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<DataRow[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    setPageHeader(title)
    void apiRequest<{ entries?: Record<string, unknown>[] }>(path)
      .then((data) => {
        setRows((data.entries || []).map((entry) => {
          const row: DataRow = {}
          for (const column of columns) row[column.key] = displayValue(entry[column.key])
          return row
        }))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
  }, [path, setPageHeader, title])

  return { rows, error }
}

export function ProxyPage() {
  const { rows, error } = useEntries('Proxy Log', '/api/proxy', columns)
  return (
    <DirectoryFrame
      title="Proxy log"
      subtitle={`${rows.length} faculty proxy records`}
      icon="fa-user-clock"
      error={error}
      columns={columns}
      rows={rows}
      empty="No proxy assignments to show."
    />
  )
}

export { MyProxyPage } from '../../teacher/pages/FacultyPortal'
