import { useEffect, useState } from 'react'
import { Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom'
import { CreditsTablePage } from './pages/CreditsTablePage'
import { AdminConfigPage } from './pages/AdminConfigPage'
import { ApiTemplatesPage } from './pages/ApiTemplatesPage'
import { RecommendationsPage } from './pages/RecommendationsPage'
import { DisabledDevicesPage } from './pages/DisabledDevicesPage'

const DEFAULT_API_KEY = import.meta.env.VITE_API_KEY ?? ''

function ApiKeyGate() {
  const stored = sessionStorage.getItem('apiKey')
  const [key, setKey] = useState(stored ?? DEFAULT_API_KEY)
  const [saved, setSaved] = useState(!!stored)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const onUnauthorized = () => {
      sessionStorage.removeItem('apiKey')
      setSaved(false)
      setError('API key rejected (401). Please enter the correct key.')
    }
    window.addEventListener('api:unauthorized', onUnauthorized)
    return () => window.removeEventListener('api:unauthorized', onUnauthorized)
  }, [])

  const saveKey = () => {
    const trimmed = key.trim()
    if (!trimmed) {
      setError('Key cannot be empty')
      return
    }
    sessionStorage.setItem('apiKey', trimmed)
    setSaved(true)
    setError(null)
  }

  if (!saved) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="bg-white rounded-xl shadow-md p-8 w-full max-w-sm space-y-4">
          <h1 className="text-xl font-bold text-slate-800">Health Platform</h1>
          <p className="text-sm text-slate-500">
            Enter your API key — check <code className="bg-slate-100 px-1 rounded">API_KEY</code> in{' '}
            <code className="bg-slate-100 px-1 rounded">.env</code>
          </p>
          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
              {error}
            </p>
          )}
          <input
            type="text"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && saveKey()}
            placeholder="e.g. poc-dev-key"
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono"
            autoFocus
          />
          <button
            onClick={saveKey}
            className="w-full py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
          >
            Continue
          </button>
        </div>
      </div>
    )
  }

  return <AppShell />
}

function TreeNavLink({
  to,
  children,
  indent = false,
}: {
  to: string
  children: React.ReactNode
  indent?: boolean
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
          indent ? 'ml-4' : ''
        } ${isActive ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-800'}`
      }
    >
      {children}
    </NavLink>
  )
}

function RecommendationsSection() {
  return (
    <TreeNavLink to="/recommendations">
      <span className="text-slate-400 text-xs">◆</span>
      Recommendations
    </TreeNavLink>
  )
}

function DevicesSection() {
  const location = useLocation()
  const isExpanded =
    location.pathname.startsWith('/credits') ||
    location.pathname.startsWith('/admin') ||
    location.pathname.startsWith('/rules')

  return (
    <div className="space-y-0.5">
      <TreeNavLink to="/credits">
        <span className="text-slate-400 text-xs">◆</span>
        Devices
      </TreeNavLink>
      {isExpanded && (
        <>
          <TreeNavLink to="/admin" indent>
            <span className="text-slate-400 text-xs">·</span>
            Admin Config
          </TreeNavLink>
          <TreeNavLink to="/rules/disabled-devices" indent>
            <span className="text-slate-400 text-xs">·</span>
            Disabled Devices
          </TreeNavLink>
        </>
      )}
    </div>
  )
}

function Sidebar() {
  return (
    <aside className="w-52 shrink-0 bg-white border-r border-slate-200 flex flex-col min-h-screen">
      <div className="px-4 py-5 border-b border-slate-100">
        <span className="font-bold text-slate-800 text-base">Health Platform</span>
      </div>

      <nav className="flex-1 px-2 py-4 space-y-0.5">
        <DevicesSection />
        <RecommendationsSection />
        <TreeNavLink to="/api-templates">
          <span className="text-slate-400 text-xs">◆</span>
          API Templates
        </TreeNavLink>
      </nav>

      <div className="px-3 py-4 border-t border-slate-100">
        <p className="text-xs text-slate-400 truncate font-mono px-1">
          {sessionStorage.getItem('apiKey')}
        </p>
      </div>
    </aside>
  )
}

function AppShell() {
  return (
    <div className="min-h-screen flex bg-slate-50">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<Navigate to="/credits" replace />} />
          <Route path="/credits" element={<CreditsTablePage />} />
          <Route path="/admin" element={<AdminConfigPage />} />
          <Route path="/api-templates" element={<ApiTemplatesPage />} />
          <Route path="/recommendations" element={<RecommendationsPage />} />
          <Route path="/rules/disabled-devices" element={<DisabledDevicesPage />} />
        </Routes>
      </main>
    </div>
  )
}

export function App() {
  return <ApiKeyGate />
}
