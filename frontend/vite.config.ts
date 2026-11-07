import type { IncomingMessage, ServerResponse } from 'node:http'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin, type ProxyOptions } from 'vite'
import { securityHeaders } from './config/csp.ts'

const proxiedPrefixes = ['/api', '/admin', '/login', '/logout', '/static', '/teacher', '/student', '/profile', '/register', '/favicon.ico']

function headerValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value.join(',') : value || ''
}

function pathOf(url: string | undefined) {
  return (url || '').split('?')[0]
}

function isSpaDocument(url: string | undefined, method?: string, accept?: string) {
  const path = pathOf(url)
  const html = (!method || method === 'GET' || method === 'HEAD') && (accept || '').includes('text/html')
  if (!html) return false
  if (path === '/login' || path.startsWith('/login/')) return true
  if (path === '/register' || path.startsWith('/register/')) return true
  if (path === '/profile' || path.startsWith('/profile/')) return true
  if (path === '/admin' || path.startsWith('/admin/')) return true
  if (path === '/teacher' || path.startsWith('/teacher/')) return true
  if (path === '/student' || path.startsWith('/student/')) return true
  return false
}

function isProxied(url: string | undefined, method?: string, accept?: string) {
  if (isSpaDocument(url, method, accept)) return false
  const path = pathOf(url)
  return proxiedPrefixes.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))
}

function keepRedirectOnFrontend(target: string) {
  const backend = new URL(target)
  return (proxyRes: IncomingMessage) => {
    const location = headerValue(proxyRes.headers.location)
    if (!location) return
    const next = new URL(location, backend)
    if (next.host !== backend.host) return
    proxyRes.headers.location = `${next.pathname}${next.search}`
  }
}

function proxyOptions(target: string, pages = false): ProxyOptions {
  return {
    target,
    changeOrigin: true,
    bypass: pages
      ? (req) => {
          if (isSpaDocument(req.url, req.method, headerValue(req.headers.accept))) return '/index.html'
        }
      : undefined,
    configure(proxy) {
      proxy.on('proxyRes', keepRedirectOnFrontend(target))
    },
  }
}

function applyHeaders(res: ServerResponse, headers: Record<string, string>) {
  for (const [name, value] of Object.entries(headers)) {
    res.setHeader(name, value)
  }
}

function securityHeaderPlugin(mode: 'development' | 'production'): Plugin {
  const headers = securityHeaders(mode)
  return {
    name: 'security-headers',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!isProxied(req.url, req.method, headerValue(req.headers.accept))) applyHeaders(res, headers)
        next()
      })
    },
    configurePreviewServer(server) {
      server.middlewares.use((_req, res, next) => {
        applyHeaders(res, securityHeaders('production'))
        next()
      })
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = env.API_PROXY_TARGET
  const proxy = proxyOptions(proxyTarget)
  const pages = proxyOptions(proxyTarget, true)
  const headerMode = mode === 'production' ? 'production' : 'development'

  return {
    plugins: [react(), tailwindcss(), securityHeaderPlugin(headerMode)],
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy: {
        '/api': proxy,
        '/admin': pages,
        '/login': pages,
        '/logout': proxy,
        '/static': proxy,
        '/favicon.ico': proxy,
        '^/teacher(/|$)': pages,
        '^/student(/|$)': pages,
        '/profile': pages,
        '/register': pages,
      },
    },
    preview: {
      host: '127.0.0.1',
      port: 4173,
    },
  }
})
