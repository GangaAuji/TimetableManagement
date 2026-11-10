import { RouterProvider } from 'react-router-dom'
import { SuccessProvider } from '../shared/components/success-notice'
import { router } from './router'

export function App() {
  return (
    <SuccessProvider>
      <RouterProvider router={router} />
    </SuccessProvider>
  )
}
