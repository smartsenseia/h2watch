import { useState, useEffect, useRef, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  ResponsiveContainer, Tooltip, AreaChart, Area,
} from "recharts";
import {
  Activity, Zap, Thermometer, Droplets, Wind,
  AlertTriangle, CheckCircle, Gauge, FlaskConical,
  BarChart2, Layers, Download,
} from "lucide-react";

const API = window.location.origin + "/api/v1/endpoints/";
const MAX_PTS = 60;
const POLL_MS = 1500;

const CHANNELS = [
  { id: "vazao_1",   label: "Stack Voltage",  unit: "V",      group: "electrical", color: "#378ADD", min: 0, max: 600  },
  { id: "vazao_2",   label: "Stack Current",  unit: "A",      group: "electrical", color: "#1D9E75", min: 0, max: 500  },
  { id: "temp_1",    label: "Stack 1 Temp",   unit: "°C",     group: "thermal",    color: "#EF9F27", min: 0, max: 100  },
  { id: "temp_3",    label: "Water Temp",     unit: "°C",     group: "thermal",    color: "#F0997B", min: 0, max: 60   },
  { id: "temp_4",    label: "Col. A Temp",    unit: "°C",     group: "thermal",    color: "#FAC775", min: 0, max: 60   },
  { id: "temp_5",    label: "Col. B Temp",    unit: "°C",     group: "thermal",    color: "#F5C4B3", min: 0, max: 60   },
  { id: "pressao_1", label: "H₂ Pressure",   unit: "mbar",   group: "pressure",   color: "#EF9F27", min: 0, max: 4000 },
  { id: "pressao_2", label: "Tank Pressure",  unit: "mbar",   group: "pressure",   color: "#7F77DD", min: 0, max: 4000 },
  { id: "vazao_3",   label: "H₂ Flow",       unit: "L/min",  group: "flow",       color: "#5DCAA5", min: 0, max: 600  },
  { id: "vazao_4",   label: "Water Volume",   unit: "L",      group: "flow",       color: "#85B7EB", min: 0, max: 600  },
  { id: "valvula",   label: "Conductivity",   unit: "µS/cm",  group: "flow",       color: "#9FE1CB", min: 0, max: 30   },
];

const GROUP_META = {
  electrical: { label: "Elétrico",  icon: <Zap size={12} /> },
  thermal:    { label: "Térmico",   icon: <Thermometer size={12} /> },
  pressure:   { label: "Pressão",   icon: <Gauge size={12} /> },
  flow:       { label: "Fluxo",     icon: <Droplets size={12} /> },
};

const KPI_CHANNELS = [
  { id: "vazao_1",   label: "Stack Voltage",  unit: "V",    color: "#378ADD", max: 600  },
  { id: "vazao_2",   label: "Stack Current",  unit: "A",    color: "#1D9E75", max: 500  },
  { id: "pressao_1", label: "H₂ Pressure",   unit: "mbar", color: "#EF9F27", max: 4000 },
  { id: "pressao_2", label: "Tank Pressure",  unit: "mbar", color: "#7F77DD", max: 4000 },
  { id: "vazao_3",   label: "H₂ Flow",       unit: "L/min",color: "#5DCAA5", max: 600  },
];

function pct(v, max) { return Math.min(100, Math.max(0, (v / max) * 100)); }
function fmt(v, dec = 1) { return v == null ? "—" : Number(v).toFixed(dec); }

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#0d1118", border: "0.5px solid #1c2535", padding: "8px 12px", fontFamily: "monospace", fontSize: 12 }}>
      {payload.map(p => (
        <div key={p.dataKey} style={{ display: "flex", gap: 16, justifyContent: "space-between" }}>
          <span style={{ color: p.color }}>{p.name}</span>
          <span style={{ color: "#d8e0ec" }}>{Number(p.value).toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

function KpiCard({ ch, value }) {
  const v = value ?? 0;
  return (
    <div style={{ flex: 1, padding: "10px 14px", borderRight: "0.5px solid #1c2535", minWidth: 120 }}>
      <div style={{ fontSize: 10, color: "#5a6a80", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>
        {ch.label}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
        <span style={{ fontFamily: "monospace", fontSize: 20, fontWeight: 600, color: ch.color, lineHeight: 1 }}>
          {fmt(v, v > 100 ? 0 : 1)}
        </span>
        <span style={{ fontSize: 10, color: "#5a6a80" }}>{ch.unit}</span>
      </div>
      <div style={{ height: 2, background: "#1c2535", marginTop: 6, borderRadius: 2 }}>
        <div style={{ height: "100%", width: `${pct(v, ch.max)}%`, background: ch.color, borderRadius: 2, transition: "width 0.5s" }} />
      </div>
    </div>
  );
}

function ChannelRow({ ch, value, selected, onSelect }) {
  const v = value ?? 0;
  return (
    <div
      onClick={onSelect}
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
        {fmt(v, v > 100 ? 0 : 1)} <span style={{ fontSize: 10, color: "#3d5065" }}>{ch.unit}</span>
      </span>
    </div>
  );
}

export default function App() {
  const [history, setHistory] = useState([]);
  const [latest, setLatest] = useState(null);
  const [selected, setSelected] = useState(new Set(["vazao_1", "vazao_2"]));
  const [splitMode, setSplitMode] = useState(false);
  const [status, setStatus] = useState("STANDBY");
  const [lastId, setLastId] = useState(null);
  const [error, setError] = useState(null);
  const lastIdRef = useRef(null);

  const fetchLatest = useCallback(async () => {
    try {
      const res = await fetch(`${API}?limit=1&skip=0`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const rows = await res.json();
      if (!rows.length) return;

      const row = rows[0];
      if (row.id === lastIdRef.current) return;
      lastIdRef.current = row.id;
      setLastId(row.id);
      setLatest(row);
      setHistory(prev => {
        const next = [...prev, { ...row, _t: prev.length }];
        return next.length > MAX_PTS ? next.slice(next.length - MAX_PTS) : next;
      });
      setStatus("LIVE");
      setError(null);
    } catch (e) {
      setStatus("ERRO");
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    fetchLatest();
    const id = setInterval(fetchLatest, POLL_MS);
    return () => clearInterval(id);
  }, [fetchLatest]);

  const toggleSelected = id =>
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const chartChannels = CHANNELS.filter(ch => selected.has(ch.id));
  const groups = ["electrical", "thermal", "pressure", "flow"];

  const statusColor = status === "LIVE" ? "#1D9E75" : status === "ERRO" ? "#ef4444" : "#5a6a80";

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
          {lastId && <span style={{ fontSize: 11, color: "#3d5065", fontFamily: "monospace" }}>ID {lastId}</span>}
        </div>
      </div>

      {/* KPI strip */}
      <div style={{ display: "flex", borderBottom: "0.5px solid #1c2535", background: "#0a0e15", flexShrink: 0 }}>
        {KPI_CHANNELS.map(ch => <KpiCard key={ch.id} ch={ch} value={latest?.[ch.id]} />)}
      </div>

      {/* Main */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

        {/* Sidebar */}
        <div style={{ width: 240, borderRight: "0.5px solid #1c2535", background: "#0d1118", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {groups.map(grp => {
              const chs = CHANNELS.filter(c => c.group === grp);
              const meta = GROUP_META[grp];
              return (
                <div key={grp}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: "#5a6a80", background: "#090c11", borderBottom: "0.5px solid #1c2535" }}>
                    {meta.icon} {meta.label}
                  </div>
                  {chs.map(ch => (
                    <ChannelRow
                      key={ch.id} ch={ch}
                      value={latest?.[ch.id]}
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
            <div style={{ flex: 1, overflow: "hidden", display: "grid", gridTemplateRows: `repeat(${chartChannels.length}, 1fr)` }}>
              {chartChannels.map(ch => (
                <div key={ch.id} style={{ borderBottom: "0.5px solid #1c2535", minHeight: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 16px", borderBottom: "0.5px solid #1c2535" }}>
                    <div style={{ width: 8, height: 8, borderRadius: "50%", background: ch.color }} />
                    <span style={{ fontSize: 12, color: ch.color, fontWeight: 600 }}>{ch.label}</span>
                    <span style={{ marginLeft: "auto", fontFamily: "monospace", fontSize: 14, color: ch.color }}>
                      {fmt(latest?.[ch.id], (latest?.[ch.id] ?? 0) > 100 ? 0 : 1)} {ch.unit}
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
                        <YAxis tick={{ fill: "#5a6a80", fontSize: 10 }} axisLine={false} tickLine={false} width={40} />
                        <Tooltip content={<CustomTooltip />} />
                        <Area dataKey={ch.id} name={ch.label} stroke={ch.color} strokeWidth={2} fill={`url(#g-${ch.id})`} dot={false} isAnimationActive={false} connectNulls />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 16px", borderBottom: "0.5px solid #1c2535", flexShrink: 0 }}>
                {chartChannels.map(ch => (
                  <div key={ch.id} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <div style={{ width: 12, height: 2, background: ch.color, borderRadius: 1 }} />
                    <span style={{ fontSize: 11, color: ch.color }}>{ch.label}</span>
                  </div>
                ))}
              </div>
              <div style={{ flex: 1, minHeight: 0 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={history} margin={{ top: 16, right: 24, left: 8, bottom: 12 }}>
                    <CartesianGrid strokeDasharray="1 5" stroke="#1c2535" vertical={false} />
                    <XAxis dataKey="_t" hide />
                    <YAxis tick={{ fill: "#5a6a80", fontSize: 11, fontFamily: "monospace" }} axisLine={false} tickLine={false} width={48} />
                    <Tooltip content={<CustomTooltip />} />
                    {chartChannels.map(ch => (
                      <Line key={ch.id} dataKey={ch.id} name={ch.label} stroke={ch.color} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "0 16px", height: 32, borderTop: "0.5px solid #1c2535", background: "#0d1118", flexShrink: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: statusColor, boxShadow: status === "LIVE" ? `0 0 5px ${statusColor}` : "none" }} />
              <span style={{ fontSize: 11, color: statusColor, letterSpacing: "0.1em" }}>
                {status === "LIVE" ? "AQUISIÇÃO ATIVA" : "AGUARDANDO"}
              </span>
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