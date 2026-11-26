import { useEffect, useRef, useState } from "react";
import {
  chat,
  downloadArtifact,
  getJob,
  getPresets,
  getReady,
  getUsage,
  startInforme,
  type JobStatus,
  type PublicRespuesta,
  type ReadyStatus,
  type UsageSummary,
} from "./api";

type Mode = "consulta" | "informe";
type Screen = "analisis" | "consumos";

function formatUsd(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "—";
  return `USD ${value.toFixed(6)}`;
}

function formatTokens(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return "0";
  return new Intl.NumberFormat("es-AR").format(value);
}

/** Mismas tarifas default que `src/costing.py` (USD por millón de tokens). */
const DEFAULT_RATES = {
  input_usd_per_mtok: 1.0,
  output_usd_per_mtok: 5.0,
  cache_read_usd_per_mtok: 0.1,
  cache_write_usd_per_mtok: 1.25,
};

function estimateCostFromUsage(
  usage?: UsageSummary["app"]["usage"] | null,
  rates: Record<string, number> = DEFAULT_RATES,
) {
  const inp = usage?.input_tokens || 0;
  const out = usage?.output_tokens || 0;
  const cacheR = usage?.cache_read_input_tokens || 0;
  const cacheW = usage?.cache_creation_input_tokens || 0;
  const inputUsd = (inp / 1_000_000) * (rates.input_usd_per_mtok ?? DEFAULT_RATES.input_usd_per_mtok);
  const outputUsd = (out / 1_000_000) * (rates.output_usd_per_mtok ?? DEFAULT_RATES.output_usd_per_mtok);
  const cacheReadUsd =
    (cacheR / 1_000_000) * (rates.cache_read_usd_per_mtok ?? DEFAULT_RATES.cache_read_usd_per_mtok);
  const cacheWriteUsd =
    (cacheW / 1_000_000) * (rates.cache_write_usd_per_mtok ?? DEFAULT_RATES.cache_write_usd_per_mtok);
  const totalUsd = inputUsd + outputUsd + cacheReadUsd + cacheWriteUsd;
  const fullInputIfNoCache =
    (cacheR / 1_000_000) * (rates.input_usd_per_mtok ?? DEFAULT_RATES.input_usd_per_mtok);
  return {
    input_usd: Number(inputUsd.toFixed(6)),
    output_usd: Number(outputUsd.toFixed(6)),
    cache_read_usd: Number(cacheReadUsd.toFixed(6)),
    cache_write_usd: Number(cacheWriteUsd.toFixed(6)),
    total_usd: Number(totalUsd.toFixed(6)),
    ahorro_cache_usd: Number(Math.max(fullInputIfNoCache - cacheReadUsd, 0).toFixed(6)),
  };
}

function emptyUsageSummary(): UsageSummary {
  return {
    started_at: Date.now() / 1000,
    now: Date.now() / 1000,
    app: {
      consultas: 0,
      usage: {
        input_tokens: 0,
        output_tokens: 0,
        cache_read_input_tokens: 0,
        cache_creation_input_tokens: 0,
      },
      costo: {
        input_usd: 0,
        output_usd: 0,
        cache_read_usd: 0,
        cache_write_usd: 0,
        total_usd: 0,
      },
      rates: { ...DEFAULT_RATES },
    },
    sesion_actual: null,
    sesiones: [],
    eventos_recientes: [],
  };
}

function addTok(
  base: UsageSummary["app"]["usage"],
  part?: UsageSummary["app"]["usage"] | null,
) {
  return {
    input_tokens: (base.input_tokens || 0) + (part?.input_tokens || 0),
    output_tokens: (base.output_tokens || 0) + (part?.output_tokens || 0),
    cache_read_input_tokens:
      (base.cache_read_input_tokens || 0) + (part?.cache_read_input_tokens || 0),
    cache_creation_input_tokens:
      (base.cache_creation_input_tokens || 0) + (part?.cache_creation_input_tokens || 0),
  };
}

/** Acumula en el cliente el costo de una respuesta (por si /usage aún no refleja). */
function absorbLocalEvent(
  prev: UsageSummary | null,
  opts: {
    kind: string;
    label: string;
    sessionId?: string | null;
    usage?: UsageSummary["app"]["usage"] | null;
    totalUsd?: number | null;
    tiempoS?: number | null;
  },
): UsageSummary {
  const next = prev ? structuredClone(prev) : emptyUsageSummary();
  const usage = {
    input_tokens: opts.usage?.input_tokens || 0,
    output_tokens: opts.usage?.output_tokens || 0,
    cache_read_input_tokens: opts.usage?.cache_read_input_tokens || 0,
    cache_creation_input_tokens: opts.usage?.cache_creation_input_tokens || 0,
  };
  if (!next.app.rates) next.app.rates = { ...DEFAULT_RATES };
  const partCost = estimateCostFromUsage(usage, next.app.rates);
  // Preferimos el total del backend si vino; el desglose siempre sale de tokens × tarifas.
  const totalUsd = Number(opts.totalUsd != null ? opts.totalUsd : partCost.total_usd);
  const event = {
    id: `local-${Date.now().toString(36)}`,
    ts: Date.now() / 1000,
    kind: opts.kind,
    label: opts.label,
    session_id: opts.sessionId || null,
    usage,
    costo: {
      total_usd: totalUsd,
      input_usd: partCost.input_usd,
      output_usd: partCost.output_usd,
    },
    tiempo_s: opts.tiempoS ?? null,
  };
  next.app.consultas += 1;
  next.app.usage = addTok(next.app.usage, usage);
  const appCost = estimateCostFromUsage(next.app.usage, next.app.rates);
  next.app.costo = {
    input_usd: appCost.input_usd,
    output_usd: appCost.output_usd,
    cache_read_usd: appCost.cache_read_usd,
    cache_write_usd: appCost.cache_write_usd,
    // Si el backend mandó totales distintos, conservamos la suma de totales reportados.
    total_usd: Number(((next.app.costo.total_usd || 0) + totalUsd).toFixed(6)),
  };
  next.app.ahorro_cache_usd = appCost.ahorro_cache_usd;
  next.eventos_recientes = [event, ...(next.eventos_recientes || [])].slice(0, 40);
  if (opts.sessionId) {
    const sess = next.sesiones.find((s) => s.session_id === opts.sessionId);
    if (sess) {
      sess.consultas += 1;
      sess.usage = addTok(sess.usage, usage);
      sess.total_usd = Number(sess.total_usd || 0) + totalUsd;
      sess.ultimo_ts = event.ts;
    } else {
      next.sesiones = [
        {
          session_id: opts.sessionId,
          consultas: 1,
          usage,
          total_usd: totalUsd,
          ultimo_ts: event.ts,
        },
        ...next.sesiones,
      ];
    }
    next.sesion_actual = {
      session_id: opts.sessionId,
      consultas: (next.sesion_actual?.session_id === opts.sessionId
        ? (next.sesion_actual.consultas || 0) + 1
        : 1),
      usage:
        next.sesion_actual?.session_id === opts.sessionId
          ? addTok(next.sesion_actual.usage, usage)
          : usage,
      total_usd:
        (next.sesion_actual?.session_id === opts.sessionId
          ? Number(next.sesion_actual.total_usd || 0)
          : 0) + totalUsd,
    };
  }
  next.now = Date.now() / 1000;
  return next;
}

type LocalTurn = {
  index: number;
  usuario: string;
  respuesta: PublicRespuesta;
  selected: boolean;
};

function formatValue(value: number | string, unit?: string | null) {
  const number = Number(value);
  const formatted = Number.isFinite(number)
    ? new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 }).format(number)
    : String(value);
  return unit?.toUpperCase() === "ARS"
    ? `$ ${formatted}`
    : `${formatted}${unit ? ` ${unit}` : ""}`;
}

function formatSql(sql: string) {
  return sql
    .replace(/\s+(FROM|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT)\s+/gi, "\n$1 ")
    .replace(/\s+(LEFT JOIN|RIGHT JOIN|INNER JOIN|FULL JOIN|JOIN)\s+/gi, "\n$1 ")
    .replace(/\s+ON\s+/gi, "\n  ON ")
    .replace(/\s+(AND|OR)\s+/gi, "\n  $1 ")
    .trim();
}

function ReadyBanner({ data }: { data: ReadyStatus | null }) {
  const ready = Boolean(data?.agent && data.db && data.anthropic_key);
  return (
    <p className={`ready ${ready ? "is-ok" : data ? "is-bad" : ""}`} role="status">
      {ready ? "Listo para consultar" : data ? "Configuración incompleta" : "Comprobando disponibilidad…"}
    </p>
  );
}

function CopySqlButton({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <button type="button" className="copy-sql" onClick={() => void copy()}>
      {copied ? "Copiado" : "Copiar SQL"}
    </button>
  );
}

function TracePanel({ data }: { data: PublicRespuesta }) {
  return (
    <div className="trace">
      {(data.consultas || []).map((query, index) => (
        <details key={`${query.medida || "sql"}-${index}`} open={index === 0}>
          <summary>{query.medida || "Consulta SQL"}</summary>
          <div className="trace-body">
            {query.explicacion_consulta && <p>{query.explicacion_consulta}</p>}
            {query.sql && (
              <>
                <div className="sql-toolbar">
                  <span>SQL</span>
                  <CopySqlButton sql={formatSql(query.sql)} />
                </div>
                <pre tabIndex={0}>{formatSql(query.sql)}</pre>
              </>
            )}
          </div>
        </details>
      ))}
      {(data.cuentas || []).length > 0 && (
        <details>
          <summary>Cuentas utilizadas</summary>
          <div className="trace-body">
            <ul>{data.cuentas?.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        </details>
      )}
    </div>
  );
}

function LoadingState({ message }: { message: string }) {
  return (
    <div className="loading-state" role="status">
      <p><span className="spinner" aria-hidden="true" />{message}</p>
      <div className="skeleton short" />
      <div className="skeleton" />
      <div className="skeleton" />
    </div>
  );
}

function ConsumosView({
  usage,
  sessionId,
  onRefresh,
  loading,
}: {
  usage: UsageSummary | null;
  sessionId: string | null;
  onRefresh: () => void;
  loading: boolean;
}) {
  const app = usage?.app;
  const sesion = usage?.sesion_actual;
  const rates = { ...DEFAULT_RATES, ...(app?.rates || {}) };
  const appCost = estimateCostFromUsage(app?.usage, rates);
  const sessionCost = estimateCostFromUsage(sesion?.usage, rates);
  const appTotal =
    app?.costo?.total_usd != null && app.costo.total_usd > 0
      ? app.costo.total_usd
      : appCost.total_usd;
  const sessionTotal =
    sesion?.total_usd != null && sesion.total_usd > 0
      ? sesion.total_usd
      : sessionCost.total_usd;

  return (
    <section className="panel usage-panel" aria-labelledby="usage-title">
      <div className="usage-head">
        <div>
          <p className="panel-kicker">Seguimiento de consumo</p>
          <h2 id="usage-title">Consumos de sesión y corridas</h2>
          <p className="composer-hint">
            Acá ves lo que consumió esta sesión y las corridas del momento, más la evidencia de la suite integral.
          </p>
        </div>
        <button type="button" className="secondary-action" disabled={loading} onClick={onRefresh}>
          {loading ? "Actualizando…" : "Actualizar"}
        </button>
      </div>

      <div className="usage-grid">
        <article className="usage-card">
          <p className="usage-label">Corrida integral (evidencia)</p>
          <p className="usage-kpi">USD 2,33</p>
          <ul>
            <li>20 / 20 preguntas</li>
            <li>5 / 5 conversaciones</li>
            <li>3 / 3 informes</li>
            <li>415 s de corrida total</li>
            <li>Holdout 5 / 5 respuestas</li>
          </ul>
        </article>

        <article className="usage-card">
          <p className="usage-label">App en este momento</p>
          <p className="usage-kpi">{formatUsd(appTotal)}</p>
          <ul>
            <li>{app?.consultas ?? 0} consultas / informes</li>
            <li>
              Input {formatTokens(app?.usage?.input_tokens)} tok · {formatUsd(appCost.input_usd)}
            </li>
            <li>
              Output {formatTokens(app?.usage?.output_tokens)} tok · {formatUsd(appCost.output_usd)}
            </li>
            <li>
              Cache read {formatTokens(app?.usage?.cache_read_input_tokens)} tok ·{" "}
              {formatUsd(appCost.cache_read_usd)}
            </li>
            <li>
              Cache write {formatTokens(app?.usage?.cache_creation_input_tokens)} tok ·{" "}
              {formatUsd(appCost.cache_write_usd)}
            </li>
            {appCost.ahorro_cache_usd > 0 && (
              <li>Ahorro por cache · {formatUsd(appCost.ahorro_cache_usd)}</li>
            )}
          </ul>
        </article>

        <article className="usage-card">
          <p className="usage-label">Sesión actual</p>
          <p className="usage-kpi">{sessionId ? formatUsd(sessionTotal) : "Sin sesión"}</p>
          <ul>
            <li>{sessionId ? `ID ${sessionId}` : "Todavía no hay chat activo"}</li>
            <li>{sesion?.consultas ?? 0} eventos en esta sesión</li>
            <li>
              Input {formatTokens(sesion?.usage?.input_tokens)} tok · {formatUsd(sessionCost.input_usd)}
            </li>
            <li>
              Output {formatTokens(sesion?.usage?.output_tokens)} tok ·{" "}
              {formatUsd(sessionCost.output_usd)}
            </li>
            <li>
              Cache read {formatTokens(sesion?.usage?.cache_read_input_tokens)} tok ·{" "}
              {formatUsd(sessionCost.cache_read_usd)}
            </li>
          </ul>
        </article>
      </div>

      <p className="composer-hint" style={{ marginBottom: "1rem" }}>
        El prompt cache abarata reutilizar el system prompt: cache read suele costar menos que input nuevo.
        Tarifas (USD / MTok): input {rates.input_usd_per_mtok} · output {rates.output_usd_per_mtok} ·
        cache read {rates.cache_read_usd_per_mtok}.
      </p>

      <div className="usage-tables">
        <div>
          <h3>Por sesión</h3>
          {(usage?.sesiones || []).length === 0 ? (
            <p className="composer-hint">Todavía no hay consumos registrados.</p>
          ) : (
            <table className="usage-table">
              <thead>
                <tr>
                  <th>Sesión</th>
                  <th>Consultas</th>
                  <th>Tokens in/out</th>
                  <th>USD</th>
                </tr>
              </thead>
              <tbody>
                {(usage?.sesiones || []).map((row) => (
                  <tr key={row.session_id} className={row.session_id === sessionId ? "is-current" : ""}>
                    <td>{row.session_id}</td>
                    <td>{row.consultas}</td>
                    <td>
                      {formatTokens(row.usage?.input_tokens)} / {formatTokens(row.usage?.output_tokens)}
                    </td>
                    <td>{formatUsd(row.total_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div>
          <h3>Eventos recientes</h3>
          {(usage?.eventos_recientes || []).length === 0 ? (
            <p className="composer-hint">Sin eventos todavía.</p>
          ) : (
                <table className="usage-table">
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Consulta</th>
                  <th>In / Out / Cache</th>
                  <th>USD</th>
                </tr>
              </thead>
              <tbody>
                {(usage?.eventos_recientes || []).map((ev) => (
                  <tr key={ev.id}>
                    <td>{ev.kind}</td>
                    <td title={ev.label}>{ev.label.length > 48 ? `${ev.label.slice(0, 48)}…` : ev.label}</td>
                    <td>
                      {formatTokens(ev.usage?.input_tokens)} / {formatTokens(ev.usage?.output_tokens)} /{" "}
                      {formatTokens(ev.usage?.cache_read_input_tokens)}
                    </td>
                    <td>{formatUsd(ev.costo?.total_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  );
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("analisis");
  const [mode, setMode] = useState<Mode>("consulta");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [usageLoading, setUsageLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [respuesta, setRespuesta] = useState<PublicRespuesta | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<LocalTurn[]>([]);
  const [ready, setReady] = useState<ReadyStatus | null>(null);
  const [presets, setPresets] = useState<Awaited<ReturnType<typeof getPresets>> | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [lastCompleted, setLastCompleted] = useState<{ mode: Mode; text: string } | null>(null);
  const resultRef = useRef<HTMLElement>(null);
  const queryRef = useRef<HTMLTextAreaElement>(null);
  const pendingInformeText = useRef<string | null>(null);

  async function refreshUsage(sid?: string | null) {
    setUsageLoading(true);
    try {
      const remote = await getUsage(sid ?? sessionId);
      setUsage((prev) => {
        // Si el servidor aún no tiene eventos pero el cliente sí, conservamos lo local.
        if (
          prev
          && (remote.app?.consultas || 0) === 0
          && (prev.app?.consultas || 0) > 0
        ) {
          return prev;
        }
        return remote;
      });
    } catch {
      /* demo: si falla, no bloqueamos el análisis; queda el acumulado local */
    } finally {
      setUsageLoading(false);
    }
  }

  useEffect(() => {
    void getReady().then(setReady).catch(() => setReady({ agent: false, db: false, anthropic_key: false }));
    void getPresets().then(setPresets).catch(() => undefined);
    void refreshUsage(null);
  }, []);

  useEffect(() => {
    if (screen === "consumos") {
      void refreshUsage(sessionId);
    }
  }, [screen, sessionId]);

  const jobPending = Boolean(job && job.status !== "done" && job.status !== "error");
  const busy = loading || jobPending;
  const selectedTurns = turns.filter((turn) => turn.selected);
  const canReportFromSession = selectedTurns.length >= 1;
  const latestProgress = job?.progress?.[job.progress.length - 1];
  const progressLabel = (() => {
    if (!jobPending) return "Preparando el informe…";
    const phase = String(latestProgress?.phase || job?.status || "queued");
    const role = latestProgress?.role ? String(latestProgress.role) : null;
    if (latestProgress?.skipped) return "Usando evidencia de la sesión…";
    if (phase === "worker_start" && role) return `Ejecutando rol: ${role}…`;
    if (phase === "start") return "Arrancando el workflow…";
    if (job?.status === "queued") return "Informe en cola…";
    return "Generando informe (puede tardar 1–2 minutos)…";
  })();

  useEffect(() => {
    if (!job || job.status === "done" || job.status === "error") return;
    let cancelled = false;
    let attempts = 0;
    const timer = setInterval(() => {
      void (async () => {
        attempts += 1;
        if (attempts > 120) {
          clearInterval(timer);
          if (!cancelled) {
            setError("El informe sigue procesándose. Revisá su estado en unos minutos.");
          }
          return;
        }
        try {
          const next = await getJob(job.job_id);
          if (!cancelled) setJob(next);
        } catch (reason) {
          if (!cancelled) {
            setError(reason instanceof Error ? reason.message : String(reason));
          }
          clearInterval(timer);
        }
      })();
    }, 1500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [job?.job_id, job?.status]);

  useEffect(() => {
    if (respuesta || job?.result || jobPending || error) {
      resultRef.current?.focus({ preventScroll: true });
    }
  }, [respuesta, job?.result, jobPending, error]);

  useEffect(() => {
    if (job?.status === "done" && job.result && pendingInformeText.current) {
      const label = pendingInformeText.current;
      setLastCompleted({ mode: "informe", text: label });
      pendingInformeText.current = null;
      setUsage((prev) =>
        absorbLocalEvent(prev, {
          kind: "informe",
          label,
          sessionId,
          totalUsd: job.result?.costo?.total_usd,
          tiempoS: job.result?.costo?.tiempo_s,
        }),
      );
      void refreshUsage(sessionId);
    }
    if (job?.status === "error") {
      pendingInformeText.current = null;
    }
  }, [job?.status, job?.result, sessionId]);

  function resetOutput() {
    setError(null);
    setRespuesta(null);
    setJob(null);
  }

  function changeMode(next: Mode) {
    if (busy || next === mode) return;
    setMode(next);
    // Conservamos la sesión y los turnos: consulta e informe son el mismo flujo.
    setError(null);
    setInput("");
    if (next === "consulta") {
      setJob(null);
    } else {
      setRespuesta(null);
    }
  }

  function clearSession() {
    setSessionId(null);
    setTurns([]);
    resetOutput();
    setLastCompleted(null);
    setInput("");
  }

  function confirmDuplicateRun(text: string, kind: Mode): boolean {
    if (lastCompleted?.mode !== kind || lastCompleted.text !== text) return true;
    const message =
      kind === "informe"
        ? "Ya generaste este mismo informe sin cambios.\n\n¿Querés continuar de todos modos? Volverá a consumir tiempo y tokens."
        : "Ya realizaste esta misma consulta sin cambios.\n\n¿Querés continuar de todos modos?";
    return window.confirm(message);
  }

  async function runQuestion() {
    const text = input.trim();
    if (!text || busy) return;
    if (!confirmDuplicateRun(text, "consulta")) return;
    setLoading(true);
    resetOutput();
    try {
      const result = await chat(text, sessionId);
      const sid = result.session_id || sessionId;
      setSessionId(sid);
      setRespuesta(result);
      setLastCompleted({ mode: "consulta", text });
      setInput("");
      const index = result.turno_index ?? turns.length;
      const isBlocked = Boolean(result.meta?.scope_blocked)
        || Boolean(result.texto?.startsWith("Lo siento, no cuento"));
      const isMulti = Boolean(result.meta?.multi_question)
        || Boolean(result.texto?.startsWith("Detecté varias preguntas"));
      const turnLabel = isMulti
        ? "Varias preguntas (pedir una)"
        : text.length > 140
          ? `${text.slice(0, 137)}…`
          : text;
      setTurns((prev) => [
        ...prev,
        {
          index,
          usuario: turnLabel,
          respuesta: result,
          selected: !isBlocked && !isMulti,
        },
      ]);
      setUsage((prev) =>
        absorbLocalEvent(prev, {
          kind: isBlocked ? "chat_blocked" : isMulti ? "chat_clarify" : "chat",
          label: turnLabel,
          sessionId: sid,
          usage: result.meta?.usage,
          totalUsd: result.meta?.costo_usd,
          tiempoS: result.meta?.tiempo_s,
        }),
      );
      void refreshUsage(sid);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  async function runReport(fromSession: boolean) {
    const pedido = input.trim();
    if (busy) return;

    if (fromSession) {
      if (!sessionId || !canReportFromSession) return;
      const key = `session:${sessionId}:${selectedTurns.map((t) => t.index).join(",")}`;
      if (!confirmDuplicateRun(key, "informe")) return;
      setLoading(true);
      resetOutput();
      pendingInformeText.current = key;
      try {
        const created = await startInforme(undefined, pedido || undefined, {
          sessionId,
          turnIndices: selectedTurns.map((t) => t.index),
        });
        setJob(await getJob(created.job_id));
        setMode("informe");
      } catch (reason) {
        pendingInformeText.current = null;
        setError(reason instanceof Error ? reason.message : String(reason));
      } finally {
        setLoading(false);
      }
      return;
    }

    if (!pedido) return;
    if (!confirmDuplicateRun(pedido, "informe")) return;
    setLoading(true);
    resetOutput();
    pendingInformeText.current = pedido;
    try {
      const created = await startInforme(undefined, pedido);
      setJob(await getJob(created.job_id));
    } catch (reason) {
      pendingInformeText.current = null;
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  function useSuggestedQuestion(question: string) {
    setMode("consulta");
    setInput(question);
    window.requestAnimationFrame(() => {
      queryRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      queryRef.current?.focus();
    });
  }

  function toggleTurn(index: number) {
    setTurns((prev) =>
      prev.map((turn) =>
        turn.index === index ? { ...turn, selected: !turn.selected } : turn,
      ),
    );
  }

  const queryLabel = mode === "informe" ? "Pedido de informe" : "Qué querés saber";
  const placeholder = mode === "informe"
    ? canReportFromSession
      ? "Opcional: agregá un foco (ej. énfasis en margen y acciones)."
      : "Preparame un informe ejecutivo del T2 del AF2026 con foco en margen."
    : sessionId
      ? "¿Y en la región Sur?"
      : "¿Cuánto vendió la cadena en el año fiscal 2025?";
  const multiInformeHint = (() => {
    if (mode !== "informe" || canReportFromSession) return null;
    const text = input.trim();
    if (!text) return null;
    const lower = text.toLowerCase();
    const informeMentions = (lower.match(/\binforme\b/g) || []).length;
    const looksStacked =
      informeMentions >= 2
      || /\.\s*(preparame|necesito|armame)\b/i.test(text)
      || ((text.match(/[.!?]/g) || []).length >= 3 && text.length > 160);
    if (!looksStacked) return null;
    return "Pedido compuesto detectado: TaliAnalytics investigará cada foco y fusionará un único informe ejecutivo.";
  })();

  return (
    <div className="app">
      <header className="hero">
        <div className="hero-inner">
          <div className="brand-lockup">
            <img className="brand-logo" src="/taligent-logo.png" alt="TaliAnalytics, tu analista de datos" />
            <div>
              <p className="eyebrow">Inteligencia comercial trazable</p>
              <h1>Preguntá. Verificá. Decidí.</h1>
              <p>Explorá con preguntas, acumulá evidencia y cerrá con un informe ejecutivo de esa misma sesión.</p>
            </div>
          </div>
          <div className="hero-actions">
            <button
              type="button"
              className={`nav-chip ${screen === "consumos" ? "active" : ""}`}
              onClick={() => setScreen(screen === "consumos" ? "analisis" : "consumos")}
            >
              {screen === "consumos" ? "Volver al análisis" : "Ver consumos"}
            </button>
            <span className="trust-badge">Datos de prueba · solo lectura</span>
          </div>
        </div>
      </header>

      <main className="main">
        <ReadyBanner data={ready} />
        {screen === "consumos" ? (
          <ConsumosView
            usage={usage}
            sessionId={sessionId}
            loading={usageLoading}
            onRefresh={() => void refreshUsage(sessionId)}
          />
        ) : (
        <div className="shell">
          <section className="panel" aria-labelledby="query-title">
            <p className="panel-kicker">Sesión de análisis</p>
            <div className="query-heading-row">
              <h2 id="query-title">¿Qué necesitás analizar?</h2>
              <div className="tabs" role="tablist" aria-label="Tipo de análisis">
                {([
                  ["consulta", "Explorar"],
                  ["informe", "Informe"],
                ] as const).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    role="tab"
                    aria-selected={mode === id}
                    className={mode === id ? "active" : ""}
                    disabled={busy}
                    onClick={() => changeMode(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="composer">
              <label htmlFor="query">{queryLabel}</label>
              <textarea
                id="query"
                ref={queryRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                    void (mode === "informe" ? runReport(canReportFromSession) : runQuestion());
                  }
                }}
                placeholder={placeholder}
              />
              <p className="composer-hint">
                {mode === "consulta"
                  ? "Cada pregunta queda en la sesión. Cuando tengas hallazgos, generá el informe con esa evidencia. Ctrl + Enter ejecuta."
                  : canReportFromSession
                    ? `Informe desde sesión: ${selectedTurns.length} hallazgo${selectedTurns.length === 1 ? "" : "s"} seleccionado${selectedTurns.length === 1 ? "" : "s"}. El investigador no vuelve a buscar desde cero.`
                    : "Sin sesión: pedí un informe desde cero. O explorá primero para armarlo con tus hallazgos."}
              </p>
              {multiInformeHint && <p className="composer-warning" role="status">{multiInformeHint}</p>}

              <div className="composer-footer">
                {mode === "consulta" ? (
                  <>
                    <button
                      className="primary-action"
                      type="button"
                      disabled={busy || !input.trim()}
                      onClick={() => void runQuestion()}
                    >
                      {busy ? "Procesando…" : "Consultar"}
                    </button>
                    <button
                      className="secondary-action"
                      type="button"
                      disabled={busy || !canReportFromSession}
                      onClick={() => void runReport(true)}
                      title={
                        canReportFromSession
                          ? "Genera un PDF con los hallazgos tildados"
                          : "Hacé al menos una consulta con evidencia"
                      }
                    >
                      Generar informe con la sesión
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      className="primary-action"
                      type="button"
                      disabled={
                        busy
                        || (canReportFromSession ? false : !input.trim())
                      }
                      onClick={() => void runReport(canReportFromSession)}
                    >
                      {busy
                        ? "Generando informe…"
                        : canReportFromSession
                          ? "Generar desde sesión"
                          : "Generar informe"}
                    </button>
                    {canReportFromSession && (
                      <button
                        className="secondary-action"
                        type="button"
                        disabled={busy || !input.trim()}
                        onClick={() => void runReport(false)}
                      >
                        Informe desde cero
                      </button>
                    )}
                  </>
                )}
                <div className="preset-group">
                  <p>Ejemplos para probar</p>
                  <div className="presets">
                    {mode === "informe"
                      ? (presets?.informes || [{ id: "I1", texto: "Margen T2 AF2026" }]).map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            disabled={busy}
                            onClick={() => {
                              setInput(item.texto);
                              window.requestAnimationFrame(() => queryRef.current?.focus());
                            }}
                          >
                            {item.id} · {item.texto.length > 32 ? `${item.texto.slice(0, 32)}…` : item.texto}
                          </button>
                        ))
                      : (presets?.preguntas || []).slice(0, 4).map((item) => (
                          <button key={item.id} type="button" disabled={busy} onClick={() => setInput(item.texto)}>
                            {item.id}
                          </button>
                        ))}
                  </div>
                </div>
              </div>

              {sessionId && (
                <div className="session-row">
                  <span>
                    Sesión {sessionId} · {turns.length} turno{turns.length === 1 ? "" : "s"}
                    {canReportFromSession ? ` · ${selectedTurns.length} para informe` : ""}
                  </span>
                  <button type="button" disabled={busy} onClick={clearSession}>
                    Nueva conversación
                  </button>
                </div>
              )}

              {turns.length > 0 && (
                <div className="session-turns" aria-label="Hallazgos de la sesión">
                  <div className="session-turns-head">
                    <h3>Hallazgos de esta sesión</h3>
                    <p>Tildá qué incluir en el informe.</p>
                  </div>
                  <ul>
                    {turns.map((turn) => (
                      <li key={turn.index}>
                        <label>
                          <input
                            type="checkbox"
                            checked={turn.selected}
                            disabled={busy}
                            onChange={() => toggleTurn(turn.index)}
                          />
                          <span>
                            <strong>P{turn.index + 1}.</strong> {turn.usuario}
                            {turn.respuesta.valor != null && (
                              <>
                                {" · "}
                                {formatValue(turn.respuesta.valor, turn.respuesta.unidad)}
                              </>
                            )}
                          </span>
                        </label>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </section>

          <section
            className="panel answer"
            ref={resultRef}
            tabIndex={-1}
            aria-live="polite"
            aria-busy={busy}
          >
            <p className="panel-kicker">{job?.result ? "Informe ejecutivo" : "Resultado y evidencia"}</p>
            {busy && (
              <LoadingState
                message={
                  mode === "informe" || jobPending
                    ? progressLabel
                    : "Consultando medidas y datos comerciales…"
                }
              />
            )}
            {jobPending && job?.job_id && (
              <p className="composer-hint">Job {job.job_id} · estado {job.status}. Podés seguir en otra pestaña; el PDF queda listo al finalizar.</p>
            )}
            {error && <div className="error" role="alert"><strong>No pudimos completar el análisis.</strong><br />{error}</div>}
            {!busy && respuesta && (
              <>
                <span
                  className={`status ${
                    respuesta.meta?.scope_blocked
                    || respuesta.texto?.startsWith("Lo siento, no cuento")
                    || respuesta.meta?.multi_question
                    || respuesta.texto?.startsWith("Detecté varias preguntas")
                    || respuesta.valor == null
                      ? "warn"
                      : "ok"
                  }`}
                >
                  {respuesta.meta?.scope_blocked
                  || respuesta.texto?.startsWith("Lo siento, no cuento")
                    ? "Fuera de alcance"
                    : respuesta.meta?.multi_question
                      || respuesta.texto?.startsWith("Detecté varias preguntas")
                      ? "Elegí una pregunta"
                      : respuesta.valor == null
                        ? "Respuesta responsable"
                        : "Respuesta trazable"}
                </span>
                {respuesta.valor != null && <p className="kpi">{formatValue(respuesta.valor, respuesta.unidad)}</p>}
                <p className="texto">
                  {respuesta.texto?.trim()
                    || "La consulta no devolvió un texto interpretable. Probá reformular o iniciar una nueva conversación."}
                </p>
                {!(respuesta.consultas || []).length && !(respuesta.cuentas || []).length && (
                  <p className="composer-hint">Sin evidencia SQL en este turno.</p>
                )}
                <div className="meta-row">
                  {respuesta.meta?.tiempo_s != null && <span>{respuesta.meta.tiempo_s} s</span>}
                  {respuesta.meta?.costo_usd != null && <span>~ USD {respuesta.meta.costo_usd}</span>}
                  {(respuesta.meta?.usage?.cache_read_input_tokens || 0) > 0 && (
                    <span>
                      cache {formatTokens(respuesta.meta?.usage?.cache_read_input_tokens)} tok
                    </span>
                  )}
                  {respuesta.session_id && <span>Sesión {respuesta.session_id}</span>}
                </div>
                {respuesta.alerta_desvio?.activa && <div className="alerta">{respuesta.alerta_desvio.motivo}</div>}
                {(respuesta.supuestos || []).length > 0 && (
                  <>
                    <h3>Supuestos declarados</h3>
                    <ul className="support-list">{respuesta.supuestos?.map((item) => <li key={item}>{item}</li>)}</ul>
                  </>
                )}
                <h3>Evidencia de la respuesta</h3>
                <TracePanel data={respuesta} />
                {canReportFromSession && (
                  <div className="suggestion session-cta">
                    <strong>¿Cerramos con un informe?</strong>
                    <p>
                      Ya hay {selectedTurns.length} hallazgo{selectedTurns.length === 1 ? "" : "s"} con evidencia.
                      Podés generar un PDF ejecutivo sin redescubrir los datos.
                    </p>
                    <div className="suggestion-actions">
                      <button type="button" disabled={busy} onClick={() => void runReport(true)}>
                        Generar informe con la sesión →
                      </button>
                    </div>
                  </div>
                )}
                {respuesta.siguiente_pregunta_sugerida && (
                  <div className="suggestion">
                    <strong>Siguiente análisis sugerido</strong>
                    <p>{respuesta.siguiente_pregunta_sugerida}</p>
                    <div className="suggestion-actions">
                      <button
                        type="button"
                        onClick={() => useSuggestedQuestion(respuesta.siguiente_pregunta_sugerida || "")}
                      >
                        Usar esta pregunta →
                      </button>
                      <span className="suggestion-hint">Luego presioná Consultar arriba</span>
                    </div>
                  </div>
                )}
              </>
            )}
            {!busy && job?.status === "error" && (
              <div className="error" role="alert">
                <strong>El informe falló.</strong>
                <br />
                {job.error || "Revisá los logs del backend e intentá de nuevo."}
              </div>
            )}
            {!busy && job?.result && (
              <>
                <span className="status info">Informe listo</span>
                <h2 className="report-title">{job.result.titulo || "Informe ejecutivo"}</h2>
                <p className="texto">{job.result.resumen_ejecutivo}</p>
                <div className="meta-row">
                  {job.result.costo?.tiempo_s != null && <span>{job.result.costo.tiempo_s} s</span>}
                  {job.result.costo?.total_usd != null && <span>~ USD {job.result.costo.total_usd}</span>}
                  {sessionId && <span>Desde sesión {sessionId}</span>}
                </div>
                {(job.result.indicadores || []).length > 0 && (
                  <>
                    <h3>Indicadores principales</h3>
                    <div className="indicator-grid">
                      {job.result.indicadores?.map((item, index) => {
                        const name = String(item.nombre || "Indicador");
                        const value = item.valor as number | string | undefined;
                        const unit = item.unidad as string | undefined;
                        return <div className="indicator" key={`${name}-${index}`}><span>{name}</span><strong>{value != null ? formatValue(value, unit) : "—"}</strong></div>;
                      })}
                    </div>
                  </>
                )}
                {(job.result.conclusiones || []).length > 0 && (
                  <>
                    <h3>Conclusiones</h3>
                    <ul className="support-list">{job.result.conclusiones?.map((item) => <li key={item}>{item}</li>)}</ul>
                  </>
                )}
                {job.result.pdf && (
                  <div className="cta-row">
                    <button
                      type="button"
                      className="primary-action"
                      onClick={() => void downloadArtifact(job.job_id, job.result!.pdf!)}
                    >
                      Descargar PDF
                    </button>
                  </div>
                )}
                <h3>Evidencia del informe</h3>
                <TracePanel data={{ texto: "", consultas: job.result.consultas }} />
              </>
            )}
            {!busy && !error && !respuesta && !job?.result && job?.status !== "error" && (
              <div className="empty-state">
                <h2>Tu análisis aparecerá acá</h2>
                <p>Explorá con preguntas, revisá la evidencia y cerrá con un informe de esa misma sesión.</p>
                <ol>
                  <li>Hacé una o más consultas comerciales.</li>
                  <li>Tildá los hallazgos que importan.</li>
                  <li>Generá el informe ejecutivo con esa evidencia.</li>
                </ol>
              </div>
            )}
          </section>
        </div>
        )}
      </main>

      <footer>
        <strong>Talia Ivonne Ojeda</strong>
        <span>TaliAnalytics convierte preguntas comerciales en respuestas verificables.</span>
        <a href="/docs" target="_blank" rel="noreferrer">Documentación API</a>
      </footer>
    </div>
  );
}
