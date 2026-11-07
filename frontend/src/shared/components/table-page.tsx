import { useEffect, useMemo, useState, type ReactNode } from 'react'

export const pageSizeChoices = [10, 25, 50, 100] as const

function pageNumbers(current: number, pages: number) {
  if (pages <= 7) return Array.from({ length: pages }, (_, index) => index + 1)
  const end = Math.min(pages, Math.max(current + 2, 5))
  const start = Math.max(1, end - 4)
  const numbers: Array<number | 'gap'> = []
  if (start > 1) numbers.push(1)
  if (start > 2) numbers.push('gap')
  for (let number = start; number <= end; number += 1) numbers.push(number)
  if (end < pages - 1) numbers.push('gap')
  if (end < pages) numbers.push(pages)
  return numbers
}

export function TablePager({
  page,
  totalPages,
  pageSize,
  onPage,
  onPageSize,
}: {
  page: number
  totalPages: number
  pageSize: number
  onPage: (page: number) => void
  onPageSize: (pageSize: number) => void
}) {
  const pages = Math.max(totalPages, 1)
  const current = Math.min(Math.max(page, 1), pages)
  const numbers = pageNumbers(current, pages)
  return (
    <div className="flex h-12 shrink-0 flex-wrap items-center justify-between gap-3 border-t border-gray-200 bg-gray-50/80 px-5">
      <label className="flex items-center gap-2 text-[10px] font-bold tracking-wider text-gray-500 uppercase">
        Show
        <select
          value={pageSizeChoices.includes(pageSize as (typeof pageSizeChoices)[number]) ? pageSize : 25}
          onChange={(event) => onPageSize(Number(event.target.value))}
          className="rounded-lg border border-gray-200 bg-white px-2 py-1 text-[10px] font-bold text-gray-700"
          aria-label="Records on this page"
        >
          {pageSizeChoices.map((size) => <option key={size} value={size}>{size}</option>)}
        </select>
      </label>
      <div className="flex items-center gap-1.5">
        <button type="button" disabled={current <= 1} onClick={() => onPage(current - 1)} className="flex h-7 items-center rounded-lg border border-gray-200 bg-white px-3 text-[10px] font-bold text-gray-600 shadow-sm hover:text-indigo-600 disabled:opacity-40">Prev</button>
        {numbers.map((number, index) => number === 'gap' ? (
          <span key={`gap-${index}`} className="px-1 text-[10px] font-bold text-gray-400">…</span>
        ) : (
          <button
            key={number}
            type="button"
            onClick={() => onPage(number)}
            className={`flex h-7 min-w-7 items-center justify-center rounded-lg border px-2 text-[10px] font-bold shadow-sm ${number === current ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-200 bg-white text-gray-600 hover:text-indigo-600'}`}
            aria-current={number === current ? 'page' : undefined}
          >
            {number}
          </button>
        ))}
        <button type="button" disabled={current >= pages} onClick={() => onPage(current + 1)} className="flex h-7 items-center rounded-lg border border-gray-200 bg-white px-3 text-[10px] font-bold text-gray-600 shadow-sm hover:text-indigo-600 disabled:opacity-40">Next</button>
      </div>
    </div>
  )
}

export function useClientPage<T>(rows: T[], resetKey?: unknown) {
  const [pageSize, setPageSize] = useState(25)
  const [page, setPage] = useState(1)
  useEffect(() => {
    setPage(1)
  }, [pageSize, resetKey])
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize))
  const current = Math.min(page, totalPages)
  const start = (current - 1) * pageSize
  return {
    rows: rows.slice(start, start + pageSize),
    page: current,
    totalPages,
    total: rows.length,
    pageSize,
    setPage,
    setPageSize,
  }
}

export type TableColumnSpec = {
  key: string
  label: string
  sortable?: boolean
  filterable?: boolean
  className?: string
}

function asText(value: unknown) {
  if (value == null || value === false) return ''
  if (value === true) return 'yes'
  return String(value).toLowerCase()
}

export function useDataTable<T>(
  rows: T[],
  columns: TableColumnSpec[],
  valueOf: (row: T, key: string) => unknown,
) {
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [sortKey, setSortKey] = useState('')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const columnKey = columns.map((column) => column.key).join('|')
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    const active = columns.filter((column) => (filters[column.key] || '').trim())
    const matched = rows.filter((row) => {
      const values = columns.map((column) => asText(valueOf(row, column.key)))
      if (query && !values.some((value) => value.includes(query))) return false
      return active.every((column) => asText(valueOf(row, column.key)).includes((filters[column.key] || '').trim().toLowerCase()))
    })
    if (!sortKey || !columns.some((column) => column.key === sortKey && column.sortable !== false)) return matched
    const direction = sortDir === 'asc' ? 1 : -1
    return [...matched].sort((left, right) => asText(valueOf(left, sortKey)).localeCompare(asText(valueOf(right, sortKey)), undefined, { numeric: true, sensitivity: 'base' }) * direction)
  }, [columnKey, columns, filters, rows, search, sortDir, sortKey, valueOf])
  const activeCount = columns.filter((column) => (filters[column.key] || '').trim()).length + (search.trim() ? 1 : 0) + (sortKey ? 1 : 0)
  const page = useClientPage(filtered, `${search}|${sortKey}|${sortDir}|${JSON.stringify(filters)}|${columnKey}`)

  function toggleSort(key: string) {
    const column = columns.find((item) => item.key === key)
    if (!column || column.sortable === false) return
    if (sortKey === key) setSortDir((current) => (current === 'asc' ? 'desc' : 'asc'))
    else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  function setFilter(key: string, value: string) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  function clear() {
    setSearch('')
    setFilters({})
    setSortKey('')
    setSortDir('asc')
  }

  return {
    ...page,
    search,
    setSearch,
    filters,
    setFilter,
    filtersOpen,
    setFiltersOpen,
    sortKey,
    sortDir,
    toggleSort,
    clear,
    matched: filtered.length,
    source: rows.length,
    activeCount,
  }
}

export function TableToolbar({
  search,
  onSearch,
  filtersOpen,
  onToggleFilters,
  matched,
  source,
  activeCount,
  onClear,
}: {
  search: string
  onSearch: (value: string) => void
  filtersOpen: boolean
  onToggleFilters: () => void
  matched: number
  source: number
  activeCount: number
  onClear: () => void
}) {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-gray-100 bg-white px-4 py-2.5">
      <label className="relative min-w-44 flex-1">
        <i className="fas fa-search pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-[10px] text-gray-400" />
        <input
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          placeholder="Search all columns"
          aria-label="Search all columns"
          className="w-full rounded-xl border border-gray-200 bg-gray-50 py-2 pr-3 pl-8 text-xs font-medium outline-none focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-100"
        />
      </label>
      <button
        type="button"
        onClick={onToggleFilters}
        aria-pressed={filtersOpen}
        className={`rounded-xl border px-3 py-2 text-[10px] font-bold tracking-wide uppercase ${filtersOpen ? 'border-indigo-200 bg-indigo-50 text-indigo-700' : 'border-gray-200 bg-white text-gray-600'}`}
      >
        <i className="fas fa-filter mr-1.5" /> Column filters
      </button>
      <span className="text-[10px] font-bold tracking-wide text-gray-400 uppercase">{matched} of {source}</span>
      {activeCount > 0 ? (
        <button type="button" onClick={onClear} className="text-[10px] font-bold tracking-wide text-indigo-600 uppercase">Clear</button>
      ) : null}
    </div>
  )
}

export function DataTableHead({
  columns,
  sortKey,
  sortDir,
  onSort,
  filtersOpen,
  filters,
  onFilter,
  leading,
  trailing,
}: {
  columns: TableColumnSpec[]
  sortKey: string
  sortDir: 'asc' | 'desc'
  onSort: (key: string) => void
  filtersOpen: boolean
  filters: Record<string, string>
  onFilter: (key: string, value: string) => void
  leading?: ReactNode
  trailing?: ReactNode
}) {
  return (
    <>
      <tr>
        {leading}
        {columns.map((column) => (
          <th key={column.key} className={`px-4 py-2.5 text-left text-[10px] font-bold tracking-wider text-gray-400 uppercase ${column.className || ''}`}>
            {column.sortable === false ? column.label : (
              <button type="button" onClick={() => onSort(column.key)} className="inline-flex items-center gap-1 hover:text-indigo-600">
                {column.label}
                <i className={`fas ${sortKey === column.key ? (sortDir === 'asc' ? 'fa-sort-up text-indigo-600' : 'fa-sort-down text-indigo-600') : 'fa-sort text-gray-300'} text-[8px]`} />
              </button>
            )}
          </th>
        ))}
        {trailing}
      </tr>
      {filtersOpen ? (
        <tr className="bg-white">
          {leading ? <th className="px-3 py-2" /> : null}
          {columns.map((column) => (
            <th key={column.key} className={`px-3 py-2 ${column.className || ''}`}>
              {column.filterable === false ? null : (
                <input
                  value={filters[column.key] || ''}
                  onChange={(event) => onFilter(column.key, event.target.value)}
                  placeholder={column.label}
                  aria-label={`Filter ${column.label}`}
                  className="w-full rounded-lg border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-medium text-gray-700 normal-case outline-none focus:border-indigo-500 focus:bg-white"
                />
              )}
            </th>
          ))}
          {trailing ? <th className="px-3 py-2" /> : null}
        </tr>
      ) : null}
    </>
  )
}
