import type { ReactNode } from 'react'

export function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-gray-600/50 px-4 py-8" role="presentation" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} className="mx-auto w-full max-w-lg rounded-md border border-gray-200 bg-white p-5 shadow-lg" onClick={(event) => event.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">{title}</h3>
          <button type="button" className="text-gray-400 hover:text-gray-600" aria-label="Close" onClick={onClose}><i className="fas fa-times" /></button>
        </div>
        {children}
      </div>
    </div>
  )
}
