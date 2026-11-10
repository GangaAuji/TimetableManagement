import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useSetPageHeader } from '../../app/page-header'

const copy: Record<number, { title: string; body: string }> = {
  400: { title: 'Bad request', body: 'The request could not be completed.' },
  401: { title: 'Sign in required', body: 'Sign in is required.' },
  403: { title: 'Not allowed', body: 'You do not have permission to open this page.' },
  404: { title: 'Page not found', body: 'This page does not exist.' },
  500: { title: 'Something went wrong', body: 'The page could not be loaded.' },
}

export function ErrorPage({ status = 404 }: { status?: number }) {
  const item = copy[status] || copy[500]
  const setPageHeader = useSetPageHeader()
  useEffect(() => {
    setPageHeader(item.title)
  }, [item.title, setPageHeader])
  return (
    <section className="mx-auto flex min-h-[50vh] max-w-lg flex-col items-center justify-center px-6 py-16 text-center">
      <p className="text-5xl font-bold tracking-tight text-gray-900">{status}</p>
      <h1 className="mt-3 text-lg font-semibold text-gray-800">{item.title}</h1>
      <p className="mt-2 text-sm text-gray-500">{item.body}</p>
      <Link to="/" className="mt-6 rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-bold text-white">Back to the timetable</Link>
    </section>
  )
}
