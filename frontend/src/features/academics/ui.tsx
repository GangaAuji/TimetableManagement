import { Children, isValidElement, type ReactNode } from 'react'
import { ApiError } from '../../shared/api/client'
import { DataTableHead, TablePager, TableToolbar, useDataTable } from '../../shared/components/table-page'
import { pageFill } from '../../shared/layout/page-frame'

export function messageFrom(error: unknown) {
  if (error instanceof ApiError) return error.message
  return 'The request could not be completed.'
}

export function Screen({ title, subtitle, action, children }: { title: string; subtitle: string; action?: ReactNode; children: ReactNode }) {
  return (
    <div className={`${pageFill} gap-2`}>
      <section className="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="flex items-center justify-between gap-4 p-4">
          <div>
            <h2 className="text-lg font-bold text-gray-800">{title}</h2>
            <p className="text-xs text-gray-500">{subtitle}</p>
          </div>
          {action}
        </div>
      </section>
      {children}
    </div>
  )
}

export function Banners({ error, notice }: { error: string; notice: string }) {
  return (
    <>
      {error ? <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p> : null}
      {notice ? <p className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">{notice}</p> : null}
    </>
  )
}

function nodeText(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(nodeText).join(' ')
  if (isValidElement<{ children?: ReactNode }>(node)) return nodeText(node.props.children)
  return ''
}

function cellAt(row: ReactNode, key: string) {
  if (!isValidElement<{ children?: ReactNode }>(row)) return key === '0' ? nodeText(row) : ''
  return nodeText(Children.toArray(row.props.children)[Number(key)])
}

export function Table({ headers, children, count, loading, empty }: { headers: string[]; children: ReactNode; count: number; loading: boolean; empty: string }) {
  const items = Children.toArray(children)
  const columns = headers.map((label, index) => ({
    key: String(index),
    label,
    sortable: label !== 'Actions',
    filterable: label !== 'Actions',
    className: label === 'Actions' ? 'text-right' : '',
  }))
  const table = useDataTable(items, columns, cellAt)
  return (
    <section className={`${pageFill} overflow-hidden rounded-lg border border-gray-200 bg-white shadow-md`}>
      <TableToolbar search={table.search} onSearch={table.setSearch} filtersOpen={table.filtersOpen} onToggleFilters={() => table.setFiltersOpen((open) => !open)} matched={loading ? 0 : table.matched} source={count} activeCount={table.activeCount} onClear={table.clear} />
      <div className="flex-1 overflow-auto">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="sticky top-0 z-10 bg-gray-50">
            <DataTableHead columns={columns} sortKey={table.sortKey} sortDir={table.sortDir} onSort={table.toggleSort} filtersOpen={table.filtersOpen} filters={table.filters} onFilter={table.setFilter} />
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white">
            {loading ? <tr><td colSpan={headers.length} className="px-4 py-8 text-center text-gray-500">Loading…</td></tr> : count === 0 ? <tr><td colSpan={headers.length} className="px-4 py-8 text-center text-gray-500">{empty}</td></tr> : table.rows.length === 0 ? <tr><td colSpan={headers.length} className="px-4 py-8 text-center text-gray-500">No records match these filters.</td></tr> : table.rows}
          </tbody>
        </table>
      </div>
      <TablePager page={table.page} totalPages={table.totalPages} pageSize={table.pageSize} onPage={table.setPage} onPageSize={table.setPageSize} />
    </section>
  )
}

export function RowActions({ canChange, canDelete, onEdit, onDelete }: { canChange: boolean; canDelete: boolean; onEdit: () => void; onDelete: () => void }) {
  return (
    <td className="px-4 py-2 text-right">
      <div className="flex justify-end gap-2">
        {canChange ? <button type="button" title="Edit" className="rounded p-1.5 text-blue-600 hover:bg-blue-50" onClick={onEdit}><i className="fas fa-edit" /></button> : null}
        {canDelete ? <button type="button" title="Delete" className="rounded p-1.5 text-red-600 hover:bg-red-50" onClick={onDelete}><i className="fas fa-trash-alt" /></button> : null}
      </div>
    </td>
  )
}

export function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-sm">
      <button type="button" aria-label="Close" className="absolute inset-0 bg-gray-900/60" onClick={onClose} />
      <div className="relative m-4 max-h-[90vh] w-full max-w-lg overflow-auto rounded-lg bg-white shadow-2xl">
        <div className="flex items-center justify-between bg-indigo-600 px-6 py-4">
          <h3 className="text-lg font-bold text-white">{title}</h3>
          <button type="button" className="text-xl text-white" onClick={onClose}>&times;</button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  )
}

export function fieldClass() {
  return 'mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm'
}

export function AddButton({ onClick }: { onClick: () => void }) {
  return <button type="button" className="rounded bg-indigo-600 px-4 py-1.5 text-xs text-white shadow hover:bg-indigo-700" onClick={onClick}><i className="fas fa-plus mr-2" />Add</button>
}
