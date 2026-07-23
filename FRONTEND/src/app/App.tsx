import { useState, useEffect, useRef, useCallback } from "react";
import type { ReactNode } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  ResponsiveContainer, Tooltip, AreaChart, Area,
} from "recharts";
import {
  Activity, Zap, Thermometer, Droplets, Wind,
  Gauge, FlaskConical, BarChart2, Layers, Percent,
} from "lucide-react";

const API = window.location.origin + "/api/v1/endpoints/";
const MAX_PTS = 60;

// O coletor publica a cada 5 s. Amostrar mais rápido só gera requisição
// descartada pelo dedupe de id.
const POLL_MS = 2500;

// Sem amostra nova por este tempo, a aquisição é considerada parada.
const STALE_MS = 20000;

type GroupId = "electrical" | "thermal" | "pressure" | "water" | "dryer";

interface Channel {
  /** Chave do campo no payload da API, ou campo derivado começando com "_". */
  id: string;
  label: string;
  unit: string;
  group: GroupId;
  color: string;
  /** Fundo de escala usado nas barras dos KPIs e na normalização. */
  max: number;
  /** Casas decimais na exibição. */
  dec: number;
  /** Calculado no cliente, não vem da API. */
  derived?: boolean;
}

/** Linha crua devolvida por GET /api/v1/endpoints/ */
interface Measurement {
  id: number;
  timestamp: string;
  stack_1_temperature: number | null;
  water_temperature: number | null;
  a_column_temperature: number | null;
  b_column_temperature: number | null;
  h2_pressure: number | null;
  aim_tank_pressure: number | null;
  stack_voltage: number | null;
  stack_current: number | null;
  h2o_flow: number | null;
  aim_water_volume: number | null;
  water_conductivity: number | null;
  stack_load: number | null;
  pump_speed: number | null;
  dryer_cycle: number | null;
}

/** Linha com os campos derivados no cliente. */
type Row = Measurement & { _power: number | null };

/** Linha já no buffer do gráfico. */
type HistoryRow = Row & { _t: number; _label: string };

// Limites das barras e dos eixos. Derivados das faixas medidas em 21/07/2026
// (1 amostra/min, 17:59-19:50), com folga para operação fora do normal.
// As unidades seguem exatamente o que connection_clp.py entrega.
const CHANNELS: Channel[] = [
  // faixa medida 0,5 - 53,3 V
  { id: "stack_voltage", label: "Tensão do stack", unit: "V", group: "electrical", color: "#378ADD", max: 60, dec: 1 },
  // faixa medida 0 - 49,8 A
  { id: "stack_current", label: "Corrente do stack", unit: "A", group: "electrical", color: "#1D9E75", max: 60, dec: 1 },
  // 0 - 99 %
  { id: "stack_load", label: "Carga do stack", unit: "%", group: "electrical", color: "#6FD3B4", max: 100, dec: 0 },
  // derivado: V x A
  { id: "_power", label: "Potência", unit: "kW", group: "electrical", color: "#C3E88D", max: 4, dec: 2, derived: true },

  // 26 - 46 °C
  { id: "stack_1_temperature", label: "Temp. do stack", unit: "°C", group: "thermal", color: "#EF9F27", max: 80, dec: 1 },
  // 31,03 - 50,67 °C  (resolução de 0,01 °C no registrador 526)
  { id: "water_temperature", label: "Temp. da água", unit: "°C", group: "thermal", color: "#F0997B", max: 80, dec: 2 },
  // 26 - 28 °C
  { id: "a_column_temperature", label: "Temp. coluna A", unit: "°C", group: "thermal", color: "#FAC775", max: 60, dec: 1 },
  // 27 - 31 °C
  { id: "b_column_temperature", label: "Temp. coluna B", unit: "°C", group: "thermal", color: "#F5C4B3", max: 60, dec: 1 },

  // 1,01 - 23,85 bar
  { id: "h2_pressure", label: "Pressão de H₂", unit: "bar", group: "pressure", color: "#EF9F27", max: 35, dec: 2 },
  // 0 - 29,17 bar
  { id: "aim_tank_pressure", label: "Pressão da linha", unit: "bar", group: "pressure", color: "#7F77DD", max: 35, dec: 2 },

  // 3,9 - 5,9 L/min
  { id: "h2o_flow", label: "Vazão de água", unit: "L/min", group: "water", color: "#5DCAA5", max: 10, dec: 1 },
  // 0 - 138,9 L
  { id: "aim_water_volume", label: "Volume no tanque", unit: "L", group: "water", color: "#85B7EB", max: 150, dec: 1 },
  // 0,4 - 1,4 µS/cm
  { id: "water_conductivity", label: "Condutividade", unit: "µS/cm", group: "water", color: "#9FE1CB", max: 2, dec: 2 },
  // 39 - 85 %
  { id: "pump_speed", label: "Bomba", unit: "%", group: "water", color: "#4FA3D1", max: 100, dec: 0 },

  // contador n/300
  { id: "dryer_cycle", label: "Ciclo do secador", unit: "/300", group: "dryer", color: "#B49BE0", max: 300, dec: 0 },
];

const CHANNEL_BY_ID: Record<string, Channel> = Object.fromEntries(
  CHANNELS.map(c => [c.id, c]),
);

const GROUP_META: Record<GroupId, { label: string; icon: ReactNode }> = {
  electrical: { label: "Elétrico", icon: <Zap size={12} /> },
  thermal:    { label: "Térmico",  icon: <Thermometer size={12} /> },
  pressure:   { label: "Pressão",  icon: <Gauge size={12} /> },
  water:      { label: "Água",     icon: <Droplets size={12} /> },
  dryer:      { label: "Secador",  icon: <Activity size={12} /> },
};
const GROUPS: GroupId[] = ["electrical", "thermal", "pressure", "water", "dryer"];

const KPI_IDS = ["stack_voltage", "stack_current", "_power", "aim_tank_pressure", "h2_pressure", "water_conductivity"];
const KPI_CHANNELS: Channel[] = KPI_IDS.map(id => CHANNEL_BY_ID[id]);

type Status = "STANDBY" | "LIVE" | "PARADO" | "ERRO";

function pct(v: number, max: number): number {
  return Math.min(100, Math.max(0, (v / max) * 100));
}

function fmt(v: number | null | undefined, dec = 1): string {
  return v == null || Number.isNaN(v) ? "—" : Number(v).toFixed(dec);
}

/**
 * Lê um canal de uma linha. Os ids dos canais são strings em runtime, então
 * indexar Measurement diretamente não passa no compilador; esta função
 * concentra a conversão num ponto só.
 */
function valueFor(row: Row | HistoryRow | null | undefined, id: string): number | null {
  if (!row) return null;
  const v = (row as unknown as Record<string, unknown>)[id];
  return typeof v === "number" ? v : null;
}

/** Acrescenta os campos derivados a uma linha vinda da API. */
function derive(row: Measurement): Row {
  const v = row.stack_voltage;
  const a = row.stack_current;
  return {
    ...row,
    _power: v == null || a == null ? null : (v * a) / 1000,
  };
}

interface TooltipEntry {
  dataKey?: string | number | ((obj: unknown) => unknown);
  name?: string | number;
  value?: number;
  color?: string;
  payload?: HistoryRow;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  normalized?: boolean;
}

function CustomTooltip({ active, payload, normalized = false }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  if (!row) return null;

  return (
    <div style={{ background: "#0d1118", border: "0.5px solid #1c2535", padding: "8px 12px", fontFamily: "monospace", fontSize: 12 }}>
      {row._label && (
        <div style={{ color: "#5a6a80", marginBottom: 6, fontSize: 11 }}>{row._label}</div>
      )}
      {payload.map((p, i) => {
        // Em modo normalizado a série é uma função, então o id do canal vem
        // pelo name, que é sempre setado explicitamente abaixo.
        const key = typeof p.name === "string" ? p.name : String(p.dataKey ?? i);
        const ch = CHANNEL_BY_ID[key];
        const raw = normalized && ch ? valueFor(row, ch.id) : p.value ?? null;
        return (
          <div key={key} style={{ display: "flex", gap: 16, justifyContent: "space-between" }}>
            <span style={{ color: p.color }}>{ch?.label ?? key}</span>
            <span style={{ color: "#d8e0ec" }}>
              {fmt(raw, ch?.dec ?? 2)} <span style={{ color: "#5a6a80" }}>{ch?.unit ?? ""}</span>
            </span>
          </div>
        );
      })}
    </div>
  );
}

interface KpiCardProps {
  ch: Channel;
  value: number | null;
}

function KpiCard({ ch, value }: KpiCardProps) {
  return (
    <div style={{ flex: 1, padding: "10px 14px", borderRight: "0.5px solid #1c2535", minWidth: 120 }}>
      <div style={{ fontSize: 10, color: "#5a6a80", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>
        {ch.label}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
        <span style={{ fontFamily: "monospace", fontSize: 20, fontWeight: 600, color: ch.color, lineHeight: 1 }}>
          {fmt(value, ch.dec)}
        </span>
        <span style={{ fontSize: 10, color: "#5a6a80" }}>{ch.unit}</span>
      </div>
      <div style={{ height: 2, background: "#1c2535", marginTop: 6, borderRadius: 2 }}>
        <div style={{ height: "100%", width: `${pct(value ?? 0, ch.max)}%`, background: ch.color, borderRadius: 2, transition: "width 0.5s" }} />
      </div>
    </div>
  );
}

interface ChannelRowProps {
  ch: Channel;
  value: number | null;
  selected: boolean;
  onSelect: () => void;
}

function ChannelRow({ ch, value, selected, onSelect }: ChannelRowProps) {
  return (
    <div
      onClick={onSelect}
      role="checkbox"
      aria-checked={selected}
      tabIndex={0}
      onKeyDown={e => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(); }
      }}
      style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "7px 12px", cursor: "pointer", borderBottom: "0.5px solid #1c2535",
        background: selected ? `${ch.color}18` : "transparent",
        transition: "background 0.15s",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ width: 8, height: 8, borderRadius: "50%", background: selected ? ch.color : "transparent", border: `1.5px solid ${selected ? ch.color : "#3d5065"}`, transition: "all 0.2s" }} />
        <span style={{ fontSize: 12, color: selected ? "#a8b8cc" : "#3d5065" }}>{ch.label}</span>
      </div>
      <span style={{ fontFamily: "monospace", fontSize: 12, color: selected ? ch.color : "#3d5065" }}>
        {fmt(value, ch.dec)} <span style={{ fontSize: 10, color: "#3d5065" }}>{ch.unit}</span>
      </span>
    </div>
  );
}

export default function App() {
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [latest, setLatest] = useState<Row | null>(null);
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(["stack_voltage", "stack_current"]),
  );
  const [splitMode, setSplitMode] = useState(false);
  const [normalized, setNormalized] = useState(false);
  const [status, setStatus] = useState<Status>("STANDBY");
  const [lastId, setLastId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const lastIdRef = useRef<number | null>(null);
  const lastChangeRef = useRef<number>(Date.now());
  // Contador monotônico para o eixo X. Usar prev.length gerava chaves
  // repetidas depois que o buffer atingia MAX_PTS e passava a ser cortado.
  const seqRef = useRef(0);

  const fetchLatest = useCallback(async () => {
    try {
      const res = await fetch(`${API}?limit=1&skip=0`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const rows: Measurement[] = await res.json();
      setError(null);

      if (rows.length && rows[0].id !== lastIdRef.current) {
        const row = derive(rows[0]);
        lastIdRef.current = row.id;
        lastChangeRef.current = Date.now();
        setLastId(row.id);
        setLatest(row);
        setHistory(prev => {
          const ts = row.timestamp ? new Date(row.timestamp) : null;
          const next: HistoryRow[] = [...prev, {
            ...row,
            _t: seqRef.current++,
            _label: ts ? ts.toLocaleTimeString() : "",
          }];
          return next.length > MAX_PTS ? next.slice(next.length - MAX_PTS) : next;
        });
      }

      // A API devolve a última linha gravada mesmo com o coletor parado.
      // Sem esta checagem o painel ficaria em LIVE indefinidamente.
      const parado = Date.now() - lastChangeRef.current > STALE_MS;
      setStatus(parado ? "PARADO" : "LIVE");
    } catch (e) {
      setStatus("ERRO");
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    fetchLatest();
    const id = setInterval(fetchLatest, POLL_MS);
    return () => clearInterval(id);
  }, [fetchLatest]);

  const toggleSelected = (id: string) =>
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });

  const chartChannels = CHANNELS.filter(ch => selected.has(ch.id));

  // Faixas muito diferentes num eixo só (28 bar contra 0,8 µS/cm) escondem
  // as séries pequenas. Normalizar põe tudo em % do fundo de escala.
  const yDomain: [number, number] | ["auto", "auto"] = normalized ? [0, 100] : ["auto", "auto"];

  const valueOf = (ch: Channel) => (d: unknown): number | null => {
    const raw = valueFor(d as HistoryRow, ch.id);
    if (raw == null) return null;
    return normalized ? (raw / ch.max) * 100 : raw;
  };

  const statusColor =
    status === "LIVE" ? "#1D9E75" :
    status === "ERRO" ? "#ef4444" :
    status === "PARADO" ? "#EF9F27" : "#5a6a80";

  const statusLabel =
    status === "LIVE" ? "AQUISIÇÃO ATIVA" :
    status === "ERRO" ? "SEM RESPOSTA DA API" :
    status === "PARADO" ? "SEM AMOSTRA NOVA" : "AGUARDANDO";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "#090c11", color: "#d8e0ec", fontFamily: "sans-serif", fontSize: 14 }}>

      {/* Top bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 16px", height: 52, background: "#0d1118", borderBottom: "0.5px solid #1c2535", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Wind size={18} color="#00c8a8" />
          <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: "0.14em", color: "#d8e0ec" }}>H₂WATCH</span>
          <span style={{ fontSize: 10, padding: "2px 8px", border: "0.5px solid #00c8a820", background: "#00c8a810", color: "#00c8a8", fontFamily: "monospace" }}>
            ELECTROLYZER DAQ
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {error && <span style={{ fontSize: 11, color: "#ef4444" }}>{error}</span>}
          <span style={{ fontSize: 11, color: "#5a6a80", fontFamily: "monospace" }}>
            {latest?.timestamp ? new Date(latest.timestamp).toLocaleTimeString() : "—"}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 10px", border: `0.5px solid ${statusColor}40`, background: `${statusColor}10` }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: statusColor, boxShadow: status === "LIVE" ? `0 0 6px ${statusColor}` : "none" }} />
            <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: statusColor }}>{status}</span>
          </div>
          {lastId != null && <span style={{ fontSize: 11, color: "#3d5065", fontFamily: "monospace" }}>ID {lastId}</span>}
        </div>
      </div>

      {/* KPI strip */}
      <div style={{ display: "flex", borderBottom: "0.5px solid #1c2535", background: "#0a0e15", flexShrink: 0, overflowX: "auto" }}>
        {KPI_CHANNELS.map(ch => (
          <KpiCard key={ch.id} ch={ch} value={valueFor(latest, ch.id)} />
        ))}
      </div>

      {/* Main */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

        {/* Sidebar */}
        <div style={{ width: 240, borderRight: "0.5px solid #1c2535", background: "#0d1118", display: "flex", flexDirection: "column", overflow: "hidden", flexShrink: 0 }}>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {GROUPS.map(grp => {
              const chs = CHANNELS.filter(c => c.group === grp);
              const meta = GROUP_META[grp];
              return (
                <div key={grp}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: "#5a6a80", background: "#090c11", borderBottom: "0.5px solid #1c2535" }}>
                    {meta.icon} {meta.label}
                  </div>
                  {chs.map(ch => (
                    <ChannelRow
                      key={ch.id}
                      ch={ch}
                      value={valueFor(latest, ch.id)}
                      selected={selected.has(ch.id)}
                      onSelect={() => toggleSelected(ch.id)}
                    />
                  ))}
                </div>
              );
            })}
          </div>
          <div style={{ padding: "10px 12px", borderTop: "0.5px solid #1c2535", display: "flex", gap: 8 }}>
            <button
              onClick={() => setSplitMode(v => !v)}
              style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "6px 0", border: `0.5px solid ${splitMode ? "#00c8a8" : "#1c2535"}`, background: "transparent", color: splitMode ? "#00c8a8" : "#5a6a80", cursor: "pointer", fontSize: 11, letterSpacing: "0.06em" }}
            >
              {splitMode ? <BarChart2 size={12} /> : <Layers size={12} />}
              {splitMode ? "SEPARADO" : "SOBREPOSTO"}
            </button>
            <button
              onClick={() => setNormalized(v => !v)}
              disabled={splitMode}
              title="Põe todas as séries em % do fundo de escala"
              style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "6px 10px", border: `0.5px solid ${normalized && !splitMode ? "#00c8a8" : "#1c2535"}`, background: "transparent", color: splitMode ? "#243044" : (normalized ? "#00c8a8" : "#5a6a80"), cursor: splitMode ? "not-allowed" : "pointer", fontSize: 11 }}
            >
              <Percent size={12} />
            </button>
          </div>
        </div>

        {/* Chart area */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {chartChannels.length === 0 ? (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, color: "#3d5065" }}>
              <FlaskConical size={40} strokeWidth={1} />
              <p style={{ letterSpacing: "0.1em", fontSize: 13 }}>SELECIONE VARIÁVEIS NA BARRA LATERAL</p>
            </div>
          ) : splitMode ? (
            <div style={{ flex: 1, overflowY: "auto", display: "grid", gridTemplateRows: `repeat(${chartChannels.length}, minmax(140px, 1fr))` }}>
              {chartChannels.map(ch => (
                <div key={ch.id} style={{ borderBottom: "0.5px solid #1c2535", minHeight: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 16px", borderBottom: "0.5px solid #1c2535" }}>
                    <div style={{ width: 8, height: 8, borderRadius: "50%", background: ch.color }} />
                    <span style={{ fontSize: 12, color: ch.color, fontWeight: 600 }}>{ch.label}</span>
                    <span style={{ marginLeft: "auto", fontFamily: "monospace", fontSize: 14, color: ch.color }}>
                      {fmt(valueFor(latest, ch.id), ch.dec)} {ch.unit}
                    </span>
                  </div>
                  <div style={{ height: "calc(100% - 34px)" }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={history} margin={{ top: 8, right: 16, left: 8, bottom: 4 }}>
                        <defs>
                          <linearGradient id={`g-${ch.id}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={ch.color} stopOpacity={0.15} />
                            <stop offset="95%" stopColor={ch.color} stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="1 5" stroke="#1c2535" vertical={false} />
                        <XAxis dataKey="_t" hide />
                        <YAxis tick={{ fill: "#5a6a80", fontSize: 10 }} axisLine={false} tickLine={false} width={48} domain={["auto", "auto"]} />
                        <Tooltip content={<CustomTooltip />} />
                        <Area dataKey={ch.id} name={ch.id} stroke={ch.color} strokeWidth={2} fill={`url(#g-${ch.id})`} dot={false} isAnimationActive={false} connectNulls />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 16px", borderBottom: "0.5px solid #1c2535", flexShrink: 0, flexWrap: "wrap" }}>
                {chartChannels.map(ch => (
                  <div key={ch.id} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <div style={{ width: 12, height: 2, background: ch.color, borderRadius: 1 }} />
                    <span style={{ fontSize: 11, color: ch.color }}>
                      {ch.label} <span style={{ color: "#3d5065" }}>{ch.unit}</span>
                    </span>
                  </div>
                ))}
                {normalized && (
                  <span style={{ marginLeft: "auto", fontSize: 10, color: "#5a6a80", fontFamily: "monospace" }}>
                    EIXO EM % DO FUNDO DE ESCALA
                  </span>
                )}
              </div>
              <div style={{ flex: 1, minHeight: 0 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={history} margin={{ top: 16, right: 24, left: 8, bottom: 12 }}>
                    <CartesianGrid strokeDasharray="1 5" stroke="#1c2535" vertical={false} />
                    <XAxis dataKey="_t" hide />
                    <YAxis
                      tick={{ fill: "#5a6a80", fontSize: 11, fontFamily: "monospace" }}
                      axisLine={false} tickLine={false} width={48}
                      domain={yDomain}
                      unit={normalized ? "%" : undefined}
                    />
                    <Tooltip content={<CustomTooltip normalized={normalized} />} />
                    {chartChannels.map(ch => (
                      <Line
                        key={ch.id}
                        dataKey={normalized ? valueOf(ch) : ch.id}
                        name={ch.id}
                        stroke={ch.color} strokeWidth={2} dot={false}
                        isAnimationActive={false} connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "0 16px", height: 32, borderTop: "0.5px solid #1c2535", background: "#0d1118", flexShrink: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: statusColor, boxShadow: status === "LIVE" ? `0 0 5px ${statusColor}` : "none" }} />
              <span style={{ fontSize: 11, color: statusColor, letterSpacing: "0.1em" }}>{statusLabel}</span>
            </div>
            <span style={{ fontSize: 11, color: "#3d5065", fontFamily: "monospace" }}>
              BUF {history.length}/{MAX_PTS} · {POLL_MS}ms poll
            </span>
            <span style={{ fontSize: 11, color: "#3d5065", fontFamily: "monospace" }}>
              {selected.size} canais no gráfico
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}