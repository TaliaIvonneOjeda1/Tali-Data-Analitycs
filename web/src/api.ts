const TOKEN =
  import.meta.env.VITE_ANALISTA_API_TOKEN || "dev-token-cambiar";
const BASE = import.meta.env.VITE_API_BASE || "/api";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${TOKEN}`,
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      const detail =
        typeof parsed.detail === "string"
          ? parsed.detail
          : JSON.stringify(parsed.detail || parsed);
      throw new Error(detail);
    } catch (error) {
      if (error instanceof SyntaxError) {
        throw new Error(text || res.statusText);
      }
      throw error;
    }
  }
  return res.json() as Promise<T>;
}

export type PublicRespuesta = {
  pregunta?: string;
  texto: string;
  valor?: number | string | null;
  unidad?: string | null;
  supuestos?: string[];
  consultas?: Array<{
    medida?: string | null;
    filtros?: Record<string, unknown>;
    sql?: string | null;
    valor?: number | null;
    explicacion_consulta?: string;
  }>;
  cuentas?: string[];
  siguiente_pregunta_sugerida?: string | null;
  alerta_desvio?: { activa?: boolean; motivo?: string } | null;
  meta?: {
    tiempo_s?: number;
    costo_usd?: number;
    usage?: {
      input_tokens?: number;
      output_tokens?: number;
      cache_read_input_tokens?: number;
      cache_creation_input_tokens?: number;
    };
    scope_blocked?: boolean;
    multi_question?: boolean;
  };
  session_id?: string;
  turno_index?: number;
  turnos_en_sesion?: number;
};

export type SessionTurn = {
  index: number;
  usuario?: string;
  texto?: string;
  valor?: number | string | null;
  unidad?: string | null;
  supuestos?: string[];
  consultas?: PublicRespuesta["consultas"];
  cuentas?: string[];
  tiene_evidencia?: boolean;
};

export type SessionSummary = {
  session_id: string;
  estado?: Record<string, unknown>;
  turnos: SessionTurn[];
  turnos_con_evidencia: number;
  usage_total?: {
    input_tokens?: number;
    output_tokens?: number;
    cache_read_input_tokens?: number;
    cache_creation_input_tokens?: number;
  };
  costo_usd?: number;
  costo?: {
    input_usd?: number;
    output_usd?: number;
    total_usd?: number;
  };
};

export type UsageTokens = {
  input_tokens?: number;
  output_tokens?: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
};

export type UsageEvent = {
  id: string;
  ts: number;
  kind: string;
  label: string;
  session_id?: string | null;
  usage: UsageTokens;
  costo: { total_usd?: number; input_usd?: number; output_usd?: number };
  tiempo_s?: number | null;
};

export type UsageSummary = {
  started_at: number;
  now: number;
  app: {
    consultas: number;
    usage: UsageTokens;
    costo: {
      input_usd?: number;
      output_usd?: number;
      cache_read_usd?: number;
      cache_write_usd?: number;
      total_usd?: number;
    };
    ahorro_cache_usd?: number;
    nota_cache?: string;
    rates?: Record<string, number>;
  };
  sesion_actual?: {
    session_id: string;
    consultas: number;
    usage: UsageTokens;
    total_usd?: number;
    ahorro_cache_usd?: number;
    eventos?: UsageEvent[];
  } | null;
  sesiones: Array<{
    session_id: string;
    consultas: number;
    usage: UsageTokens;
    total_usd?: number;
    ultimo_ts?: number;
  }>;
  eventos_recientes: UsageEvent[];
};

export type JobStatus = {
  job_id: string;
  status: string;
  kind: string;
  progress: Array<Record<string, unknown>>;
  result?: {
    pdf?: string;
    titulo?: string;
    resumen_ejecutivo?: string;
    indicadores?: Array<Record<string, unknown>>;
    conclusiones?: string[];
    consultas?: PublicRespuesta["consultas"];
    costo?: { total_usd?: number; tiempo_s?: number };
    siguiente_pregunta_sugerida?: string;
  } | null;
  error?: string | null;
};

export type ReadyStatus = {
  agent: boolean;
  db: boolean;
  anthropic_key: boolean;
};

export function ask(pregunta: string) {
  return api<PublicRespuesta>("/ask", {
    method: "POST",
    body: JSON.stringify({ pregunta, verbose: false }),
  });
}

export function chat(mensaje: string, sessionId?: string | null) {
  return api<PublicRespuesta>("/chat", {
    method: "POST",
    body: JSON.stringify({
      mensaje,
      session_id: sessionId || undefined,
      verbose: false,
    }),
  });
}

export function startInforme(
  informeId?: string,
  pedido?: string,
  options?: { sessionId?: string | null; turnIndices?: number[] },
) {
  return api<{ job_id: string; status: string }>("/informe", {
    method: "POST",
    body: JSON.stringify({
      informe_id: informeId || undefined,
      pedido: pedido || undefined,
      session_id: options?.sessionId || undefined,
      turn_indices: options?.turnIndices,
      verbose: false,
    }),
  });
}

export function getSession(sessionId: string) {
  return api<SessionSummary>(`/sessions/${encodeURIComponent(sessionId)}`);
}

export function getJob(jobId: string) {
  return api<JobStatus>(`/jobs/${jobId}`);
}

export function artifactUrl(jobId: string, name: string) {
  return `${BASE}/artifacts/${jobId}/${encodeURIComponent(name)}?token=${encodeURIComponent(TOKEN)}`;
}

/** Descarga autenticada (Bearer no viaja en <a href>). */
export async function downloadArtifact(jobId: string, name: string) {
  const res = await fetch(
    `${BASE}/artifacts/${jobId}/${encodeURIComponent(name)}`,
    { headers: { Authorization: `Bearer ${TOKEN}` } }
  );
  if (!res.ok) throw new Error("No se pudo descargar el artefacto");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function getPresets() {
  return api<{
    pregunta_demo: { id: string; texto: string };
    informe_demo: { id: string; texto: string };
    preguntas: Array<{ id: string; texto: string }>;
    informes: Array<{ id: string; texto: string }>;
  }>("/demo/presets");
}

export function getReady() {
  return api<ReadyStatus>("/ready");
}

export function getUsage(sessionId?: string | null) {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return api<UsageSummary>(`/usage${qs}`);
}
