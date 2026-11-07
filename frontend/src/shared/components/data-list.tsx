import { useEffect, useState, type ReactNode } from 'react'
import { useOutletContext } from 'react-router-dom'
import { useSetPageHeader } from '../../app/page-header'
import { ApiError, apiRequest } from '../api/client'
import { getCsrfToken, type SessionInfo } from '../api/endpoints'
import { pageFill } from '../layout/page-frame'
import { safeCount, safeText } from '../security/sanitize'
import { DataTableHead, TablePager, TableToolbar, useDataTable } from './table-page'

export type DataRow = Record<string, string | number | boolean>
export type DataColumn = { key: string; label: string; sortable?: boolean; filterable?: boolean }

function rowValue(row: DataRow, key: string) {
  return row[key]
}

export function messageFrom(error: unknown) {
  if (error instanceof ApiError) return error.message
  return 'The request could not be completed.'
}

export function displayValue(value: unknown, limit = 160) {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') return String(safeCount(value))
  return safeText(value, limit)
}

export async function postJson<T>(path: string, payload: object) {
  const { csrf_token: csrfToken } = await getCsrfToken()
  return apiRequest<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    body: JSON.stringify(payload),
  })
}

export function useSessionRole() {
  const session = useOutletContext<Extract<SessionInfo, { authenticated: true }>>()
  return session.role
}

export function ListScreen({ title, path, rowsKey, columns }: { title: string; path: string; rowsKey: string; columns: DataColumn[] }) {
  const setPageHeader = useSetPageHeader()
  const [rows, setRows] = useState<DataRow[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const table = useDataTable(rows, columns, rowValue)

  useEffect(() => {
    setPageHeader(title)
  }, [setPageHeader, title])

  useEffect(() => {
    void apiRequest<Record<string, unknown>>(path)
      .then((data) => {
        const source = data[rowsKey]
        if (!Array.isArray(source)) {
          setRows([])
          return
        }
        setRows(source.map((item) => {
          const row: DataRow = {}
          if (item && typeof item === 'object') {
            for (const column of columns) row[column.key] = displayValue((item as Record<string, unknown>)[column.key])
          }
          return row
        }))
      })
      .catch((reason: unknown) => setError(messageFrom(reason)))
      .finally(() => setLoading(false))
  }, [columns, path, rowsKey])

  return (
    <section className={`${pageFill} overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm`}>
      <header className="shrink-0 border-b border-gray-100 px-5 py-4">
        <h2 className="text-sm font-bold text-gray-800">{title}</h2>
      </header>
      {error && <p className="shrink-0 px-5 py-3 text-xs text-red-700">{error}</p>}
      <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={table.matched} source={table.source} activeCount={table.activeCount} onClear={table.clear} />
      <div className="flex-1 overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 z-10 border-b border-gray-200 bg-gray-50">
            <DataTableHead columns={columns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={table.setFilter} />
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading && <tr><td className="px-4 py-10 text-gray-400" colSpan={columns.length}>Loading...</td></tr>}
            {!loading && rows.length === 0 && <tr><td className="px-4 py-10 text-gray-400" colSpan={columns.length}>Nothing to show.</td></tr>}
            {!loading && rows.length > 0 && table.rows.length === 0 && <tr><td className="px-4 py-10 text-center text-gray-400" colSpan={columns.length}>No records match these filters.</td></tr>}
            {table.rows.map((row, index) => (
              <tr key={index} className="hover:bg-indigo-50/40">
                {columns.map((column) => <td key={column.key} className="px-4 py-2 text-gray-700">{row[column.key]}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <TablePager page={table.page} totalPages={table.totalPages} pageSize={table.pageSize} onPage={table.setPage} onPageSize={table.setPageSize} />
    </section>
  )
}

export function ListTable({ columns, rows }: { columns: DataColumn[]; rows: DataRow[] }) {
  const table = useDataTable(rows, columns, rowValue)
  return (
    <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white">
      <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={table.matched} source={table.source} activeCount={table.activeCount} onClear={table.clear} />
      <div className="overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 z-10 border-b border-gray-200 bg-gray-50">
            <DataTableHead columns={columns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={table.setFilter} />
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.length === 0 && <tr><td className="px-4 py-10 text-gray-400" colSpan={columns.length}>Nothing to show.</td></tr>}
            {rows.length > 0 && table.rows.length === 0 && <tr><td className="px-4 py-10 text-center text-gray-400" colSpan={columns.length}>No records match these filters.</td></tr>}
            {table.rows.map((row, index) => <tr key={index} className="hover:bg-indigo-50/40">{columns.map((column) => <td key={column.key} className="px-4 py-2 text-gray-700">{row[column.key]}</td>)}</tr>)}
          </tbody>
        </table>
      </div>
      <TablePager page={table.page} totalPages={table.totalPages} pageSize={table.pageSize} onPage={table.setPage} onPageSize={table.setPageSize} />
    </div>
  )
}

export function DirectoryFrame({
  title,
  subtitle,
  icon,
  toolbar,
  error,
  notice,
  columns,
  rows,
  empty,
  renderCell,
}: {
  title: string
  subtitle: string
  icon: string
  toolbar?: ReactNode
  error?: string
  notice?: string
  columns: DataColumn[]
  rows: DataRow[]
  empty: string
  renderCell?: (row: DataRow, key: string) => ReactNode
}) {
  const table = useDataTable(rows, columns, rowValue)
  const span = columns.length
  return (
    <div className={`${pageFill} max-w-full`}>
      <div className="flex shrink-0 flex-col justify-between gap-4 rounded-t-2xl border border-gray-200/80 bg-white p-3.5 shadow-[0_2px_8px_-2px_rgba(0,0,0,0.04)] md:flex-row md:items-center">
        <div className="flex items-center gap-4">
          <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-2.5 text-indigo-600 shadow-sm">
            <i className={`fas ${icon} text-lg`} />
          </div>
          <div>
            <h2 className="text-sm leading-tight font-bold tracking-tight text-gray-800">{title}</h2>
            <div className="mt-0.5 flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              <p className="text-[10px] font-medium tracking-wide text-gray-500 uppercase">{subtitle}</p>
            </div>
          </div>
        </div>
        {toolbar ? <div className="flex flex-wrap items-center gap-2.5">{toolbar}</div> : null}
      </div>
      {error ? <p className="border-x border-red-100 bg-red-50 px-4 py-2 text-xs text-red-700">{error}</p> : null}
      {notice ? <p className="border-x border-emerald-100 bg-emerald-50 px-4 py-2 text-xs text-emerald-700">{notice}</p> : null}
      <div className="flex flex-1 flex-col overflow-hidden rounded-b-2xl border-x border-b border-gray-200 bg-white shadow-[0_2px_15px_-3px_rgba(0,0,0,0.02)]">
        <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={table.matched} source={table.source} activeCount={table.activeCount} onClear={table.clear} />
        <div className="flex-1 overflow-hidden">
          <div className="h-full overflow-auto">
            <table className="w-full border-collapse text-left text-xs">
              <thead className="sticky top-0 z-10 border-b border-gray-200 bg-gray-50/90">
                <DataTableHead columns={columns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={table.setFilter} />
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {rows.length === 0 ? (
                  <tr><td colSpan={span} className="px-6 py-16 text-center text-xs font-medium text-gray-400">{empty}</td></tr>
                ) : table.rows.length === 0 ? (
                  <tr><td colSpan={span} className="px-6 py-16 text-center text-xs font-medium text-gray-400">No records match these filters.</td></tr>
                ) : table.rows.map((row, index) => (
                  <tr key={index} className="hover:bg-indigo-50/40">
                    {columns.map((column) => <td key={column.key} className="px-5 py-2 text-gray-700">{renderCell ? renderCell(row, column.key) : row[column.key]}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <TablePager page={table.page} totalPages={table.totalPages} pageSize={table.pageSize} onPage={table.setPage} onPageSize={table.setPageSize} />
      </div>
    </div>
  )
}

export function Stat({ label, value }: { label: string; value: number }) {
  return <div className="rounded-2xl border border-gray-200 bg-white p-4"><p className="text-[10px] font-bold tracking-wide text-gray-400 uppercase">{label}</p><p className="mt-1 text-xl font-bold text-gray-800">{value}</p></div>
}

export function DefinitionItem({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-[10px] font-bold tracking-wide text-gray-400 uppercase">{label}</dt><dd className="text-gray-800">{value || '-'}</dd></div>
}
