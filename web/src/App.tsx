import { useEffect, useRef, useState } from "react";
import {
  chat,
  downloadArtifact,
  getJob,
  getPresets,
  getReady,
  startInforme,
  type JobStatus,
  type PublicRespuesta,
  type ReadyStatus,
} from "./api";

type Mode = "consulta" | "informe";

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

export default function App() {
  const [mode, setMode] = useState<Mode>("consulta");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [respuesta, setRespuesta] = useState<PublicRespuesta | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<LocalTurn[]>([]);
  const [ready, setReady] = useState<ReadyStatus | null>(null);
  const [presets, setPresets] = useState<Awaited<ReturnType<typeof getPresets>> | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [lastCompleted, setLastCompleted] = useState<{ mode: Mode; text: string } | null>(null);
  const resultRef = useRef<HTMLElement>(null);
  const queryRef = useRef<HTMLTextAreaElement>(null);
  const pendingInformeText = useRef<string | null>(null);

  useEffect(() => {
    void getReady().then(setReady).catch(() => setReady({ agent: false, db: false, anthropic_key: false }));
    void getPresets().then(setPresets).catch(() => undefined);
  }, []);

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
      setLastCompleted({ mode: "informe", text: pendingInformeText.current });
      pendingInformeText.current = null;
    }
    if (job?.status === "error") {
      pendingInformeText.current = null;
    }
  }, [job?.status, job?.result]);

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
      setTurns((prev) => [
        ...prev,
        {
          index,
          usuario: text,
          respuesta: result,
          selected: true,
        },
      ]);
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
          <span className="trust-badge">Datos de prueba · solo lectura</span>
        </div>
      </header>

      <main className="main">
        <ReadyBanner data={ready} />
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
                <span className={`status ${respuesta.valor == null ? "warn" : "ok"}`}>
                  {respuesta.valor == null ? "Respuesta responsable" : "Respuesta trazable"}
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
      </main>

      <footer>
        <strong>Talia Ivonne Ojeda</strong>
        <span>TaliAnalytics convierte preguntas comerciales en respuestas verificables.</span>
        <a href="/docs" target="_blank" rel="noreferrer">Documentación API</a>
      </footer>
    </div>
  );
}
