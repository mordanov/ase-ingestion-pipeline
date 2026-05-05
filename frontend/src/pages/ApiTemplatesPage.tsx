import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listProviderSchemas,
  createProviderSchema,
  updateProviderSchema,
  deleteProviderSchema,
  type ProviderSchema,
  type CreateProviderSchemaRequest,
  type RequestMapping,
  type ResponseMapping,
} from '../api/providerApi'

// ── JSON Schema parsing (client-side) ────────────────────────────────────────

type ParsedField = { path: string; type: string; required: boolean; description: string }

function extractFields(schema: Record<string, unknown>, prefix = ''): ParsedField[] {
  const required = new Set((schema.required as string[]) ?? [])
  const fields: ParsedField[] = []
  for (const [name, raw] of Object.entries((schema.properties ?? {}) as Record<string, Record<string, unknown>>)) {
    const path = prefix ? `${prefix}.${name}` : name
    if (raw.type === 'object' || raw.properties) {
      fields.push(...extractFields(raw, path))
    } else {
      fields.push({
        path,
        type: (raw.type as string) ?? 'string',
        required: required.has(name),
        description: (raw.description as string) ?? '',
      })
    }
  }
  return fields
}

const HEIGHT_TERMS = ['height', 'tall', 'stature']
const WEIGHT_TERMS = ['weight', 'mass']
const UUID_TERMS = ['session_token', 'request_id', 'uuid', 'guid', 'correlation_id']
const TOKEN_TERMS = ['token', 'api_key', 'auth_token', 'key', 'access_token']
const TIMESTAMP_TERMS = ['birth_date', 'birthdate', 'dob', 'born']

function suggestExpr(field: ParsedField): string {
  const name = field.path.split('.').pop()!.toLowerCase()
  const desc = field.description.toLowerCase()
  if (HEIGHT_TERMS.some(t => name.includes(t) || desc.includes(t))) {
    if (['feet', 'foot', 'ft'].some(h => desc.includes(h))) return '$HEIGHT_FT'
    return '$HEIGHT'
  }
  if (WEIGHT_TERMS.some(t => name.includes(t) || desc.includes(t))) {
    if (['pound', 'lbs', 'lb'].some(h => desc.includes(h))) return '$WEIGHT_LBS'
    return '$WEIGHT'
  }
  if (UUID_TERMS.some(t => name === t)) return '$UUID'
  if (TIMESTAMP_TERMS.some(t => name === t) && field.type === 'integer') return '$BIRTHDATE'
  if (TOKEN_TERMS.some(t => name === t)) return '$CONST:'
  return '$CONST:'
}

// ── Built-in schema cards ─────────────────────────────────────────────────────

const SERVICE1_INPUT = `{ "height": 184.0, "weight": 84.0, "token": "service1-dev" }`
const SERVICE1_OUTPUT = `[{ "confidence": 0.4, "recommendation": "Walk more" }]`
const SERVICE2_INPUT = `{
  "measurements": { "mass": 405.6, "height": 6.036 },
  "birth_date": 1615876858,
  "session_token": "<uuid>"
}`
const SERVICE2_OUTPUT = `{
  "recommendations": [
    { "priority": 750, "title": "…", "details": "…" }
  ]
}`

function BuiltinCard({ title, input, output }: { title: string; input: string; output: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
        <span className="font-semibold text-slate-700 text-sm">{title}</span>
        <span className="text-xs bg-slate-200 text-slate-500 px-2 py-0.5 rounded">built-in · read-only</span>
      </div>
      <div className="grid grid-cols-2 divide-x divide-slate-100 text-xs">
        <div className="p-3">
          <p className="font-medium text-slate-400 uppercase tracking-wide mb-1.5">Request</p>
          <pre className="text-slate-600 whitespace-pre-wrap font-mono leading-relaxed">{input}</pre>
        </div>
        <div className="p-3">
          <p className="font-medium text-slate-400 uppercase tracking-wide mb-1.5">Response</p>
          <pre className="text-slate-600 whitespace-pre-wrap font-mono leading-relaxed">{output}</pre>
        </div>
      </div>
    </div>
  )
}

// ── Expression reference ──────────────────────────────────────────────────────

const EXPRESSIONS = [
  { expr: '$HEIGHT', label: 'Patient height in cm' },
  { expr: '$HEIGHT_FT', label: 'Patient height in feet' },
  { expr: '$WEIGHT', label: 'Patient weight in kg' },
  { expr: '$WEIGHT_LBS', label: 'Patient weight in lbs' },
  { expr: '$UUID', label: 'Random UUID per request' },
  { expr: '$BIRTHDATE', label: 'Current Unix timestamp (seconds since epoch)' },
  { expr: '$CONST:value', label: 'Literal constant (replace "value")' },
]

function ExpressionRef() {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs">
      <p className="font-semibold text-amber-800 mb-1.5">Available field expressions</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        {EXPRESSIONS.map(({ expr, label }) => (
          <div key={expr} className="flex gap-2 items-baseline">
            <code className="text-amber-700 font-mono shrink-0">{expr}</code>
            <span className="text-slate-500">{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Field value row ───────────────────────────────────────────────────────────

function FieldValueRow({
  field,
  value,
  onChange,
}: {
  field: ParsedField
  value: string
  onChange: (v: string) => void
}) {
  return (
    <tr className="border-b border-slate-100 last:border-0">
      <td className="py-2 pr-3 w-48">
        <span className="font-mono text-xs text-slate-700">{field.path}</span>
        {field.required && <span className="ml-1 text-red-400 text-xs">*</span>}
        <span className="ml-2 text-xs text-slate-400">{field.type}</span>
        {field.description && (
          <p className="text-xs text-slate-400 truncate max-w-[180px]" title={field.description}>
            {field.description}
          </p>
        )}
      </td>
      <td className="py-2">
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="$CONST:value or $UUID"
          className="w-full px-2 py-1 border border-slate-300 rounded text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-400 bg-white"
        />
      </td>
    </tr>
  )
}

// ── Response mapping section ──────────────────────────────────────────────────

function ResponseMappingEditor({
  value,
  onChange,
}: {
  value: ResponseMapping
  onChange: (r: ResponseMapping) => void
}) {
  const set = (key: keyof ResponseMapping, v: string | number) =>
    onChange({ ...value, [key]: v })

  return (
    <div className="grid grid-cols-2 gap-3">
      <div>
        <label className="block text-xs font-medium text-slate-600 mb-1">
          Array path
          <span className="ml-1 font-normal text-slate-400">(empty if root is the array)</span>
        </label>
        <input
          value={value.array_path}
          onChange={(e) => set('array_path', e.target.value)}
          placeholder='e.g. "recommendations" or leave empty'
          className="w-full px-2 py-1.5 border border-slate-300 rounded text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-slate-600 mb-1">Detail field <span className="font-normal text-slate-400">(optional)</span></label>
        <input
          value={value.detail_field}
          onChange={(e) => set('detail_field', e.target.value)}
          placeholder='e.g. "details"'
          className="w-full px-2 py-1.5 border border-slate-300 rounded text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-slate-600 mb-1">Text field <span className="text-red-400">*</span></label>
        <input
          value={value.text_field}
          onChange={(e) => set('text_field', e.target.value)}
          placeholder='e.g. "recommendation" or "title"'
          className="w-full px-2 py-1.5 border border-slate-300 rounded text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-slate-600 mb-1">Score field <span className="text-red-400">*</span></label>
        <input
          value={value.score_field}
          onChange={(e) => set('score_field', e.target.value)}
          placeholder='e.g. "confidence" or "priority"'
          className="w-full px-2 py-1.5 border border-slate-300 rounded text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-slate-600 mb-1">
          Score multiplier
          <span className="ml-1 font-normal text-slate-400">(1000 for 0–1 confidence, 1 for 0–1000 priority)</span>
        </label>
        <input
          type="number"
          value={value.score_multiplier}
          onChange={(e) => set('score_multiplier', Number(e.target.value))}
          className="w-full px-2 py-1.5 border border-slate-300 rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
      </div>
    </div>
  )
}

// ── Provider form (add / edit) ────────────────────────────────────────────────

const EMPTY_RESPONSE_MAPPING: ResponseMapping = {
  array_path: '',
  text_field: '',
  score_field: '',
  score_multiplier: 1,
  detail_field: '',
}

function ProviderForm({
  initial,
  onSave,
  onCancel,
  isSaving,
}: {
  initial?: ProviderSchema
  onSave: (data: CreateProviderSchemaRequest) => void
  onCancel: () => void
  isSaving: boolean
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [endpointUrl, setEndpointUrl] = useState(initial?.endpoint_url ?? '')
  const [isActive, setIsActive] = useState(initial?.is_active ?? true)

  const [schemaText, setSchemaText] = useState('')
  const [parseError, setParseError] = useState<string | null>(null)
  const [parsedFields, setParsedFields] = useState<ParsedField[] | null>(
    initial
      ? Object.keys(initial.request_mapping?.fields ?? {}).map(path => ({
          path, type: '', required: false, description: '',
        }))
      : null
  )

  const [requestMapping, setRequestMapping] = useState<RequestMapping>(
    initial?.request_mapping ?? { fields: {} }
  )
  const [responseMapping, setResponseMapping] = useState<ResponseMapping>(
    initial?.response_mapping ?? EMPTY_RESPONSE_MAPPING
  )

  const handleParseSchema = () => {
    setParseError(null)
    let schema: Record<string, unknown>
    try {
      schema = JSON.parse(schemaText)
    } catch {
      setParseError('Invalid JSON — check the pasted content.')
      return
    }
    const fields = extractFields(schema)
    if (fields.length === 0) {
      setParseError('No fields found — make sure this is a JSON Schema with a "properties" object.')
      return
    }
    setParsedFields(fields)
    setRequestMapping({ fields: Object.fromEntries(fields.map(f => [f.path, suggestExpr(f)])) })
  }

  const updateField = (path: string, expr: string) =>
    setRequestMapping(rm => ({ fields: { ...rm.fields, [path]: expr } }))

  const canSave = name.trim() && endpointUrl.trim() &&
    responseMapping.text_field.trim() && responseMapping.score_field.trim()

  const handleSave = () => {
    onSave({
      name: name.trim(),
      endpoint_url: endpointUrl.trim(),
      request_mapping: requestMapping,
      response_mapping: responseMapping,
      is_active: isActive,
    })
  }

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50 p-5 space-y-5">
      {/* Name + active */}
      <div className="flex gap-3 items-end">
        <div className="flex-1">
          <label className="block text-xs font-medium text-slate-600 mb-1">Provider name <span className="text-red-400">*</span></label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. my-health-api"
            className="w-full px-3 py-1.5 border border-slate-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
          />
        </div>
        <label className="flex items-center gap-1.5 text-sm text-slate-600 pb-1.5">
          <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} className="rounded" />
          Active
        </label>
      </div>

      {/* Endpoint URL */}
      <div>
        <label className="block text-xs font-medium text-slate-600 mb-1">Endpoint URL <span className="text-red-400">*</span></label>
        <input
          value={endpointUrl}
          onChange={(e) => setEndpointUrl(e.target.value)}
          placeholder="https://api.example.com/recommendations"
          className="w-full px-3 py-1.5 border border-slate-300 rounded text-sm font-mono bg-white focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
      </div>

      {/* JSON Schema import */}
      <div className="space-y-2">
        <label className="block text-xs font-medium text-slate-600">
          Request JSON Schema
          <span className="ml-1 font-normal text-slate-400">
            (paste the service's input schema to auto-suggest field mappings)
          </span>
        </label>
        <textarea
          value={schemaText}
          onChange={(e) => setSchemaText(e.target.value)}
          rows={6}
          placeholder={'{\n  "$schema": "https://json-schema.org/draft/2020-12/schema",\n  "type": "object",\n  "properties": { … }\n}'}
          className="w-full px-3 py-2 border border-slate-300 rounded text-xs font-mono bg-white focus:outline-none focus:ring-1 focus:ring-blue-400 resize-y"
        />
        <div className="flex items-center gap-3">
          <button
            onClick={handleParseSchema}
            disabled={!schemaText.trim()}
            className="px-4 py-1.5 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            Parse Schema
          </button>
          {parsedFields && (
            <span className="text-xs text-emerald-600">
              {parsedFields.length} field{parsedFields.length !== 1 ? 's' : ''} found
            </span>
          )}
        </div>
        {parseError && <p className="text-xs text-red-600">{parseError}</p>}
      </div>

      {/* Request field mappings */}
      {parsedFields && parsedFields.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-700 uppercase tracking-wide">Request field mappings</p>
          <ExpressionRef />
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="px-3 py-2 text-left text-slate-500 font-medium">Field</th>
                  <th className="px-3 py-2 text-left text-slate-500 font-medium">Value expression</th>
                </tr>
              </thead>
              <tbody className="px-3">
                {parsedFields.map((field) => (
                  <FieldValueRow
                    key={field.path}
                    field={field}
                    value={requestMapping.fields[field.path] ?? '$CONST:'}
                    onChange={(v) => updateField(field.path, v)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Response mapping */}
      <div>
        <p className="text-xs font-semibold text-slate-700 mb-2 uppercase tracking-wide">
          Response mapping
          <span className="ml-2 font-normal normal-case text-slate-400">how to extract recommendations from the response</span>
        </p>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <ResponseMappingEditor value={responseMapping} onChange={setResponseMapping} />
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2 justify-end pt-1">
        <button
          onClick={onCancel}
          className="px-4 py-1.5 text-sm text-slate-600 border border-slate-300 rounded hover:bg-slate-50 bg-white"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={isSaving || !canSave}
          className="px-5 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {isSaving ? 'Saving…' : 'Save provider'}
        </button>
      </div>
    </div>
  )
}

// ── Provider card (list item) ─────────────────────────────────────────────────

function ProviderCard({
  provider,
  onEdit,
}: {
  provider: ProviderSchema
  onEdit: () => void
}) {
  const qc = useQueryClient()
  const del = useMutation({
    mutationFn: () => deleteProviderSchema(provider.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['providerSchemas'] }),
  })

  const fieldCount = Object.keys(provider.request_mapping?.fields ?? {}).length

  return (
    <div className={`rounded-xl border bg-white shadow-sm p-4 ${!provider.is_active ? 'opacity-60' : ''}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-slate-700">{provider.name}</span>
            {!provider.is_active && (
              <span className="text-xs bg-slate-100 text-slate-400 px-2 py-0.5 rounded">inactive</span>
            )}
            <span className="text-xs bg-indigo-100 text-indigo-600 px-2 py-0.5 rounded">
              {fieldCount} field{fieldCount !== 1 ? 's' : ''} mapped
            </span>
          </div>
          <p className="text-xs font-mono text-slate-400 truncate">{provider.endpoint_url}</p>
          {provider.response_mapping?.text_field && (
            <p className="text-xs text-slate-400">
              Response: <code className="bg-slate-100 px-1 rounded">{provider.response_mapping.text_field}</code>
              {' '}+{' '}
              <code className="bg-slate-100 px-1 rounded">{provider.response_mapping.score_field}</code>
              {' '}×{provider.response_mapping.score_multiplier}
            </p>
          )}
          {fieldCount > 0 && (
            <p className="text-xs text-slate-400 font-mono">
              {Object.entries(provider.request_mapping.fields).slice(0, 3).map(([k, v]) => `${k}: ${v}`).join(' · ')}
              {fieldCount > 3 && ' …'}
            </p>
          )}
        </div>
        <div className="flex gap-1 shrink-0">
          <button
            onClick={onEdit}
            className="px-3 py-1 text-xs border border-slate-200 rounded hover:bg-slate-50 text-slate-600"
          >
            Edit
          </button>
          <button
            onClick={() => confirm(`Delete "${provider.name}"?`) && del.mutate()}
            disabled={del.isPending}
            className="px-3 py-1 text-xs border border-red-200 rounded hover:bg-red-50 text-red-600 disabled:opacity-40"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function ApiTemplatesPage() {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null)

  const toast$ = (msg: string, ok = true) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3500)
  }

  const { data: providers, isLoading } = useQuery({
    queryKey: ['providerSchemas'],
    queryFn: listProviderSchemas,
  })

  const createMut = useMutation({
    mutationFn: createProviderSchema,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['providerSchemas'] })
      setShowAdd(false)
      toast$('Provider added successfully.')
    },
    onError: (e: Error) => toast$(e.message, false),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CreateProviderSchemaRequest> }) =>
      updateProviderSchema(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['providerSchemas'] })
      setEditingId(null)
      toast$('Provider updated.')
    },
    onError: (e: Error) => toast$(e.message, false),
  })

  return (
    <div className="p-6 space-y-8 max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">API Templates</h1>
        <p className="mt-1 text-sm text-slate-500">
          Add custom recommendation providers by pasting their request JSON Schema. Field values are mapped
          using expressions: <code className="bg-slate-100 px-1 rounded text-xs">$HEIGHT</code>,{' '}
          <code className="bg-slate-100 px-1 rounded text-xs">$WEIGHT</code>,{' '}
          <code className="bg-slate-100 px-1 rounded text-xs">$UUID</code>,{' '}
          <code className="bg-slate-100 px-1 rounded text-xs">$CONST:value</code>.
        </p>
      </div>

      {toast && (
        <div className={`px-4 py-2 rounded border text-sm ${toast.ok ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-700'}`}>
          {toast.msg}
        </div>
      )}

      {/* Built-in providers */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Built-in providers</h2>
        <BuiltinCard title="Service 1 — confidence list" input={SERVICE1_INPUT} output={SERVICE1_OUTPUT} />
        <BuiltinCard title="Service 2 — priority object" input={SERVICE2_INPUT} output={SERVICE2_OUTPUT} />
      </section>

      {/* Custom providers */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Custom providers</h2>
          {!showAdd && !editingId && (
            <button
              onClick={() => setShowAdd(true)}
              className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              + Add provider
            </button>
          )}
        </div>

        {showAdd && (
          <ProviderForm
            onSave={(data) => createMut.mutate(data)}
            onCancel={() => setShowAdd(false)}
            isSaving={createMut.isPending}
          />
        )}

        {isLoading && <p className="text-slate-400 text-sm">Loading…</p>}

        {providers?.map((p) =>
          editingId === p.id ? (
            <ProviderForm
              key={p.id}
              initial={p}
              onSave={(data) => updateMut.mutate({ id: p.id, data })}
              onCancel={() => setEditingId(null)}
              isSaving={updateMut.isPending}
            />
          ) : (
            <ProviderCard
              key={p.id}
              provider={p}
              onEdit={() => { setShowAdd(false); setEditingId(p.id) }}
            />
          )
        )}

        {!isLoading && providers?.length === 0 && !showAdd && (
          <p className="text-slate-400 text-sm">No custom providers yet. Click "+ Add provider" to add one.</p>
        )}
      </section>
    </div>
  )
}
