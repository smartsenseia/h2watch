import { useState, useEffect, useRef, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  ResponsiveContainer, Tooltip, ReferenceLine, AreaChart, Area,
} from "recharts";
import {
  Activity, Play, Square, Zap, Thermometer, Droplets,
  Wind, AlertTriangle, CheckCircle, Settings, Download,
  ChevronRight, Gauge, FlaskConical, BarChart2, Layers,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

type ChGroup = "electrical" | "thermal" | "flow" | "quality";

interface Channel {
  id: string;
  label: string;
  unit: string;
  group: ChGroup;
  color: string;
  nominalMin: number;
  nominalMax: number;
  alarmLow?: number;
  alarmHigh?: number;
  baseValue: number;
  noise: number;
  drift: number;
  enabled: boolean;
}

interface DataPoint {
  t: number;
  [key: string]: number | undefined;
}

type Status = "STANDBY" | "RUNNING" | "WARNING" | "FAULT";

// ─── Channel Definitions ──────────────────────────────────────────────────────

const CHANNELS: Channel[] = [
  // ── Electrical ──
  {
    id: "VStack", label: "Tensão do Stack", unit: "V",
    group: "electrical", color: "#00c8a8",
    nominalMin: 58, nominalMax: 78, alarmLow: 55, alarmHigh: 82,
    baseValue: 68.4, noise: 0.18, drift: 0.05, enabled: true,
  },
  {
    id: "IStack", label: "Corrente do Stack", unit: "A",
    group: "electrical", color: "#22d3ee",
    nominalMin: 0, nominalMax: 500, alarmHigh: 510,
    baseValue: 312, noise: 1.8, drift: 0.3, enabled: true,
  },
  {
    id: "PWR", label: "Potência Consumida", unit: "kW",
    group: "electrical", color: "#818cf8",
    nominalMin: 0, nominalMax: 40, alarmHigh: 42,
    baseValue: 21.4, noise: 0.12, drift: 0.02, enabled: true,
  },
  {
    id: "EnerSpec", label: "Energia Específica", unit: "kWh/Nm³",
    group: "electrical", color: "#a78bfa",
    nominalMin: 4.0, nominalMax: 6.5, alarmHigh: 7.0,
    baseValue: 4.82, noise: 0.03, drift: 0.005, enabled: false,
  },
  // ── Thermal ──
  {
    id: "TStack", label: "Temp. Stack", unit: "°C",
    group: "thermal", color: "#f59e0b",
    nominalMin: 55, nominalMax: 85, alarmHigh: 90,
    baseValue: 72.5, noise: 0.25, drift: 0.04, enabled: true,
  },
  {
    id: "TAnode", label: "Temp. Ânodo", unit: "°C",
    group: "thermal", color: "#fb923c",
    nominalMin: 50, nominalMax: 82, alarmHigh: 88,
    baseValue: 70.1, noise: 0.3, drift: 0.05, enabled: false,
  },
  {
    id: "TCath", label: "Temp. Cátodo", unit: "°C",
    group: "thermal", color: "#fbbf24",
    nominalMin: 50, nominalMax: 82, alarmHigh: 88,
    baseValue: 68.7, noise: 0.28, drift: 0.04, enabled: false,
  },
  {
    id: "TCoolIn", label: "Refrigerante Entrada", unit: "°C",
    group: "thermal", color: "#34d399",
    nominalMin: 20, nominalMax: 45, alarmHigh: 48,
    baseValue: 32.3, noise: 0.15, drift: 0.02, enabled: true,
  },
  {
    id: "TCoolOut", label: "Refrigerante Saída", unit: "°C",
    group: "thermal", color: "#6ee7b7",
    nominalMin: 40, nominalMax: 65, alarmHigh: 70,
    baseValue: 51.8, noise: 0.2, drift: 0.03, enabled: false,
  },
  // ── Flow / Pressure ──
  {
    id: "PSys", label: "Pressão do Sistema", unit: "bar",
    group: "flow", color: "#60a5fa",
    nominalMin: 1, nominalMax: 30, alarmLow: 0.8, alarmHigh: 32,
    baseValue: 15.2, noise: 0.08, drift: 0.01, enabled: true,
  },
  {
    id: "DeltaP", label: "Pressão Diferencial", unit: "mbar",
    group: "flow", color: "#93c5fd",
    nominalMin: 0, nominalMax: 80, alarmHigh: 100,
    baseValue: 18.6, noise: 0.5, drift: 0.05, enabled: false,
  },
  {
    id: "FlowH2O", label: "Fluxo de Água", unit: "L/min",
    group: "flow", color: "#38bdf8",
    nominalMin: 0, nominalMax: 12, alarmLow: 0.5, alarmHigh: 13,
    baseValue: 6.4, noise: 0.08, drift: 0.01, enabled: true,
  },
  {
    id: "FlowH2", label: "Vazão H₂", unit: "Nm³/h",
    group: "flow", color: "#7dd3fc",
    nominalMin: 0, nominalMax: 5, alarmHigh: 5.5,
    baseValue: 2.18, noise: 0.04, drift: 0.006, enabled: true,
  },
  // ── Quality / Production ──
  {
    id: "H2Purity", label: "Pureza do H₂", unit: "%",
    group: "quality", color: "#4ade80",
    nominalMin: 99.0, nominalMax: 100, alarmLow: 99.0,
    baseValue: 99.87, noise: 0.015, drift: 0.002, enabled: true,
  },
  {
    id: "H2Prod", label: "Produção Acumulada", unit: "g/h",
    group: "quality", color: "#86efac",
    nominalMin: 0, nominalMax: 400,
    baseValue: 196, noise: 2.0, drift: 0.5, enabled: true,
  },
];

const GROUP_META: Record<ChGroup, { label: string; icon: React.ReactNode; color: string }> = {
  electrical: { label: "Elétrico", icon: <Zap size={11} />, color: "#00c8a8" },
  thermal:    { label: "Térmico",  icon: <Thermometer size={11} />, color: "#f59e0b" },
  flow:       { label: "Fluxo",    icon: <Droplets size={11} />, color: "#60a5fa" },
  quality:    { label: "Qualidade",icon: <FlaskConical size={11} />, color: "#4ade80" },
};

const BUFFER = 300;
const TICK_MS = 200;

// ─── Signal Simulation ────────────────────────────────────────────────────────

function genSample(ch: Channel, t: number, phase: number): number {
  const slow = Math.sin(2 * Math.PI * 0.02 * t + phase) * ch.drift;
  const fast = (Math.random() - 0.5) * 2 * ch.noise;
  return ch.baseValue + slow + fast;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(v: number, decimals = 2) {
  return v.toFixed(decimals);
}

function isAlarm(ch: Channel, v: number | undefined): boolean {
  if (v === undefined) return false;
  if (ch.alarmLow !== undefined && v < ch.alarmLow) return true;
  if (ch.alarmHigh !== undefined && v > ch.alarmHigh) return true;
  return false;
}

// ─── Custom Tooltip ───────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="border px-3 py-2 text-[11px]" style={{ background: "#0d1118", borderColor: "#1c2535", fontFamily: "JetBrains Mono, monospace" }}>
      <div className="mb-1.5" style={{ color: "#3d5065" }}>{Number(label).toFixed(1)} s</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex gap-4 justify-between">
          <span style={{ color: p.color }}>{p.dataKey}</span>
          <span style={{ color: "#d8e0ec" }}>{Number(p.value).toFixed(3)}</span>
        </div>
      ))}
    </div>
  );
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────

function KpiCard({ ch, value, alarm }: { ch: Channel; value: number | undefined; alarm: boolean }) {
  const v = value ?? ch.baseValue;
  const pct = Math.max(0, Math.min(100, ((v - ch.nominalMin) / (ch.nominalMax - ch.nominalMin)) * 100));
  return (
    <div className="flex flex-col gap-1 px-4 py-2.5 border-r" style={{ borderColor: "#1c2535", minWidth: 110 }}>
      <div className="text-[9px] tracking-widest uppercase flex items-center gap-1"
        style={{ color: alarm ? "#ef4444" : "#3d5065", fontFamily: "Barlow Condensed, sans-serif", letterSpacing: "0.14em" }}>
        {alarm && <AlertTriangle size={8} />}
        {ch.label}
      </div>
      <div className="flex items-end gap-1">
        <span className="text-xl font-semibold tabular-nums" style={{ fontFamily: "JetBrains Mono, monospace", color: alarm ? "#ef4444" : ch.color, lineHeight: 1 }}>
          {fmt(v, ch.unit === "%" ? 3 : ch.unit === "kWh/Nm³" ? 2 : 1)}
        </span>
        <span className="text-[10px] mb-0.5" style={{ color: "#5a6a80" }}>{ch.unit}</span>
      </div>
      <div className="h-0.5 w-full" style={{ background: "#1c2535" }}>
        <div className="h-full transition-all duration-500" style={{ width: `${pct}%`, background: alarm ? "#ef4444" : ch.color }} />
      </div>
    </div>
  );
}

// ─── Channel Row ──────────────────────────────────────────────────────────────

function ChannelRow({ ch, value, alarm, selected, onToggle, onSelect }: {
  ch: Channel; value: number | undefined; alarm: boolean;
  selected: boolean; onToggle: () => void; onSelect: () => void;
}) {
  const v = value ?? ch.baseValue;
  return (
    <div
      onClick={onSelect}
      className="flex items-center gap-2 px-3 py-1.5 cursor-pointer transition-colors"
      style={{ background: selected ? `${ch.color}10` : "transparent" }}
    >
      <button
        onClick={(e) => { e.stopPropagation(); onToggle(); }}
        className="shrink-0 w-2.5 h-2.5 rounded-full border transition-all"
        style={{ background: ch.enabled ? ch.color : "transparent", borderColor: ch.enabled ? ch.color : "#3d5065" }}
      />
      <div className="flex-1 min-w-0">
        <div className="text-[10px] truncate" style={{ color: ch.enabled ? "#8899aa" : "#3d5065", fontFamily: "Barlow, sans-serif" }}>
          {ch.label}
        </div>
      </div>
      <div className="text-right shrink-0">
        <span className="tabular-nums text-[11px]" style={{ fontFamily: "JetBrains Mono, monospace", color: alarm ? "#ef4444" : ch.enabled ? ch.color : "#3d5065" }}>
          {ch.enabled ? fmt(v, v > 100 ? 1 : v > 10 ? 2 : 3) : "—"}
        </span>
        <span className="text-[9px] ml-0.5" style={{ color: "#3d5065" }}>{ch.unit}</span>
      </div>
      {alarm && <AlertTriangle size={9} color="#ef4444" />}
    </div>
  );
}

// ─── App ─────────────────────────────────────────────────────────────────────

export default function App() {
  const [channels, setChannels] = useState<Channel[]>(CHANNELS);
  const [data, setData] = useState<DataPoint[]>([]);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<Status>("STANDBY");
  const [selectedIds, setSelectedIds] = useState<string[]>(["VStack", "IStack", "TStack"]);
  const [elapsed, setElapsed] = useState(0);
  const [accumulated, setAccumulated] = useState(0); // g H₂ produzidos
  const [splitMode, setSplitMode] = useState(false);
  const [activeGroup, setActiveGroup] = useState<ChGroup | "all">("all");
  const phaseRef = useRef<Record<string, number>>({});
  const tRef = useRef(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startRef = useRef(0);

  // init phases
  useEffect(() => {
    CHANNELS.forEach((ch, i) => { phaseRef.current[ch.id] = (i * Math.PI * 0.618); });
  }, []);

  const tick = useCallback(() => {
    tRef.current += TICK_MS / 1000;
    const t = tRef.current;
    const point: DataPoint = { t: parseFloat(t.toFixed(2)) };
    channels.forEach((ch) => {
      point[ch.id] = parseFloat(genSample(ch, t, phaseRef.current[ch.id] ?? 0).toFixed(4));
    });
    setData((prev) => {
      const next = [...prev, point];
      return next.length > BUFFER ? next.slice(next.length - BUFFER) : next;
    });
    // accumulate H₂ (g)
    const flowH2 = point["FlowH2"] as number;
    if (flowH2) setAccumulated((a) => a + (flowH2 * 89.88 * TICK_MS) / 3_600_000); // Nm³ → g
    setElapsed(Math.floor((performance.now() - startRef.current) / 1000));
  }, [channels]);

  useEffect(() => {
    if (running) {
      startRef.current = performance.now() - elapsed * 1000;
      intervalRef.current = setInterval(tick, TICK_MS);
      setStatus("RUNNING");
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (status === "RUNNING") setStatus("STANDBY");
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [running, tick]);

  const lastPoint = data[data.length - 1];

  const alarms = channels.filter((ch) => isAlarm(ch, lastPoint?.[ch.id] as number | undefined));
  if (alarms.length > 0 && status === "RUNNING") {
    // would set WARNING — keep it simple for demo
  }

  const toggleChannel = (id: string) =>
    setChannels((prev) => prev.map((c) => c.id === id ? { ...c, enabled: !c.enabled } : c));

  const toggleSelected = (id: string) =>
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  const kpiChannels = ["FlowH2", "H2Purity", "PWR", "TStack", "PSys", "H2Prod"];
  const visibleChannels = channels.filter((ch) =>
    activeGroup === "all" ? true : ch.group === activeGroup
  );
  const chartChannels = channels.filter((ch) => selectedIds.includes(ch.id));
  const xDomain = data.length > 1 ? [data[0].t, data[data.length - 1].t] : [0, 30];

  const formatElapsed = (s: number) =>
    `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  const statusColor: Record<Status, string> = {
    STANDBY: "#5a6a80",
    RUNNING: "#00c8a8",
    WARNING: "#f59e0b",
    FAULT:   "#ef4444",
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden"
      style={{ background: "#090c11", fontFamily: "Barlow, sans-serif", fontSize: "13px", color: "#d8e0ec" }}>

      {/* ── Top Bar ─────────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-4 shrink-0 border-b"
        style={{ height: 44, borderColor: "#1c2535", background: "#0d1118" }}>
        <div className="flex items-center gap-3">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <Wind size={16} color="#00c8a8" />
            <span className="font-bold tracking-widest text-sm"
              style={{ fontFamily: "Barlow Condensed, sans-serif", color: "#d8e0ec", letterSpacing: "0.16em" }}>
              H₂WATCH
            </span>
            <span className="text-[9px] px-1 py-0.5 border"
              style={{ color: "#00c8a8", borderColor: "#00c8a820", background: "#00c8a810", fontFamily: "JetBrains Mono, monospace" }}>
              ELECTROLYZER DAQ
            </span>
          </div>

          <div className="h-4 w-px" style={{ background: "#1c2535" }} />

          {/* Controls */}
          <div className="flex items-center gap-1.5">
            <button onClick={() => setRunning(true)} disabled={running}
              className="flex items-center gap-1.5 px-3 py-1 text-xs font-semibold border transition-all"
              style={{
                fontFamily: "Barlow Condensed, sans-serif", letterSpacing: "0.08em",
                background: running ? "#00c8a815" : "#00c8a8",
                color: running ? "#00c8a8" : "#090c11",
                borderColor: "#00c8a8",
                cursor: running ? "not-allowed" : "pointer",
              }}>
              <Play size={11} /> {running ? "MONITORANDO" : "INICIAR"}
            </button>
            <button onClick={() => setRunning(false)} disabled={!running}
              className="flex items-center gap-1.5 px-3 py-1 text-xs font-semibold border transition-all"
              style={{
                fontFamily: "Barlow Condensed, sans-serif", letterSpacing: "0.08em",
                background: "transparent",
                color: running ? "#ef4444" : "#3d5065",
                borderColor: running ? "#ef4444" : "#1c2535",
                cursor: running ? "pointer" : "not-allowed",
              }}>
              <Square size={11} /> PARAR
            </button>
            <button onClick={() => { setRunning(false); setData([]); tRef.current = 0; setElapsed(0); setAccumulated(0); }}
              className="px-2 py-1 text-xs border transition-all"
              style={{ color: "#5a6a80", borderColor: "#1c2535" }}>
              RESET
            </button>
          </div>
        </div>

        {/* Status + KPIs */}
        <div className="flex items-center gap-4">
          {/* H₂ acumulado */}
          <div className="flex flex-col items-end">
            <span className="text-[9px] tracking-widest" style={{ color: "#3d5065", fontFamily: "Barlow Condensed, sans-serif" }}>H₂ PRODUZIDO</span>
            <span className="text-sm tabular-nums font-semibold" style={{ fontFamily: "JetBrains Mono, monospace", color: "#4ade80" }}>
              {accumulated.toFixed(2)} g
            </span>
          </div>

          <div className="h-4 w-px" style={{ background: "#1c2535" }} />

          {/* Timer */}
          <div className="flex flex-col items-end">
            <span className="text-[9px] tracking-widest" style={{ color: "#3d5065", fontFamily: "Barlow Condensed, sans-serif" }}>TEMPO</span>
            <span className="text-sm tabular-nums" style={{ fontFamily: "JetBrains Mono, monospace", color: running ? "#d8e0ec" : "#3d5065" }}>
              {formatElapsed(elapsed)}
            </span>
          </div>

          <div className="h-4 w-px" style={{ background: "#1c2535" }} />

          {/* Status pill */}
          <div className="flex items-center gap-2 px-3 py-1 border"
            style={{ borderColor: `${statusColor[status]}40`, background: `${statusColor[status]}10` }}>
            <div className="w-1.5 h-1.5 rounded-full"
              style={{ background: statusColor[status], boxShadow: running ? `0 0 6px ${statusColor[status]}` : "none" }} />
            <span className="text-[10px] font-bold tracking-widest"
              style={{ fontFamily: "Barlow Condensed, sans-serif", letterSpacing: "0.14em", color: statusColor[status] }}>
              {status}
            </span>
          </div>

          {alarms.length > 0 && (
            <div className="flex items-center gap-1.5 px-2 py-1 border"
              style={{ borderColor: "#ef444440", background: "#ef444410", color: "#ef4444" }}>
              <AlertTriangle size={11} />
              <span style={{ fontFamily: "Barlow Condensed, sans-serif", fontSize: "10px", letterSpacing: "0.1em" }}>
                {alarms.length} ALARME{alarms.length > 1 ? "S" : ""}
              </span>
            </div>
          )}

          {alarms.length === 0 && running && (
            <div className="flex items-center gap-1.5" style={{ color: "#4ade80" }}>
              <CheckCircle size={12} />
              <span style={{ fontFamily: "Barlow Condensed, sans-serif", fontSize: "10px", letterSpacing: "0.1em" }}>NORMAL</span>
            </div>
          )}
        </div>
      </header>

      {/* ── KPI Strip ──────────────────────────────────────────────────────── */}
      <div className="flex shrink-0 border-b overflow-x-auto" style={{ borderColor: "#1c2535", background: "#0a0e15" }}>
        {kpiChannels.map((id) => {
          const ch = channels.find((c) => c.id === id)!;
          const v = lastPoint?.[id] as number | undefined;
          const alarm = isAlarm(ch, v);
          return <KpiCard key={id} ch={ch} value={v} alarm={alarm} />;
        })}
        {/* Total efficiency computed */}
        <div className="flex flex-col gap-1 px-4 py-2.5 border-r" style={{ borderColor: "#1c2535", minWidth: 110 }}>
          <div className="text-[9px] tracking-widest uppercase"
            style={{ color: "#3d5065", fontFamily: "Barlow Condensed, sans-serif", letterSpacing: "0.14em" }}>
            Eficiência
          </div>
          <div className="flex items-end gap-1">
            <span className="text-xl font-semibold tabular-nums"
              style={{ fontFamily: "JetBrains Mono, monospace", color: "#818cf8", lineHeight: 1 }}>
              {lastPoint ? fmt(
                Math.min(100, (lastPoint["FlowH2"] as number * 2.39 / ((lastPoint["PWR"] as number) || 1)) * 100),
                1
              ) : "—"}
            </span>
            <span className="text-[10px] mb-0.5" style={{ color: "#5a6a80" }}>%</span>
          </div>
          <div className="h-0.5 w-full" style={{ background: "#1c2535" }}>
            <div className="h-full" style={{ width: "68%", background: "#818cf8" }} />
          </div>
        </div>
      </div>

      {/* ── Main Layout ────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Sidebar ──────────────────────────────────────────────────────── */}
        <aside className="flex flex-col shrink-0 border-r overflow-hidden"
          style={{ width: 230, borderColor: "#1c2535", background: "#0d1118" }}>

          {/* Group filter */}
          <div className="flex border-b shrink-0" style={{ borderColor: "#1c2535" }}>
            {(["all", "electrical", "thermal", "flow", "quality"] as const).map((g) => (
              <button key={g} onClick={() => setActiveGroup(g)}
                className="flex-1 py-1.5 text-[9px] tracking-widest uppercase transition-colors"
                style={{
                  fontFamily: "Barlow Condensed, sans-serif",
                  background: activeGroup === g ? "#141b26" : "transparent",
                  color: activeGroup === g
                    ? (g === "all" ? "#d8e0ec" : GROUP_META[g as ChGroup].color)
                    : "#3d5065",
                  borderBottom: activeGroup === g
                    ? `1px solid ${g === "all" ? "#d8e0ec" : GROUP_META[g as ChGroup].color}`
                    : "1px solid transparent",
                }}>
                {g === "all" ? "ALL" : g.slice(0, 3).toUpperCase()}
              </button>
            ))}
          </div>

          {/* Channel list scrollable */}
          <div className="flex-1 overflow-y-auto">
            {(["electrical", "thermal", "flow", "quality"] as ChGroup[]).map((grp) => {
              const grpChannels = visibleChannels.filter((c) => c.group === grp);
              if (!grpChannels.length) return null;
              const meta = GROUP_META[grp];
              return (
                <div key={grp}>
                  <div className="flex items-center gap-2 px-3 py-1.5 border-b"
                    style={{ borderColor: "#1c2535", background: "#090c11" }}>
                    <span style={{ color: meta.color }}>{meta.icon}</span>
                    <span className="text-[9px] tracking-widest uppercase"
                      style={{ fontFamily: "Barlow Condensed, sans-serif", color: meta.color, letterSpacing: "0.14em" }}>
                      {meta.label}
                    </span>
                  </div>
                  <div className="divide-y" style={{ borderColor: "#1c2535" }}>
                    {grpChannels.map((ch) => {
                      const v = lastPoint?.[ch.id] as number | undefined;
                      return (
                        <ChannelRow
                          key={ch.id} ch={ch} value={v}
                          alarm={isAlarm(ch, v)}
                          selected={selectedIds.includes(ch.id)}
                          onToggle={() => toggleChannel(ch.id)}
                          onSelect={() => toggleSelected(ch.id)}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Sidebar footer */}
          <div className="border-t px-3 py-2 shrink-0" style={{ borderColor: "#1c2535" }}>
            <div className="text-[9px] tracking-widest mb-1" style={{ color: "#3d5065", fontFamily: "Barlow Condensed, sans-serif" }}>
              {channels.filter((c) => c.enabled).length}/15 CANAIS ATIVOS · {data.length} AMOSTRAS
            </div>
            <div className="flex gap-2">
              <button onClick={() => setSplitMode((v) => !v)}
                className="flex items-center gap-1 px-2 py-1 text-[9px] border flex-1 justify-center"
                style={{ fontFamily: "Barlow Condensed, sans-serif", letterSpacing: "0.08em",
                  color: splitMode ? "#00c8a8" : "#5a6a80", borderColor: splitMode ? "#00c8a8" : "#1c2535" }}>
                {splitMode ? <BarChart2 size={9} /> : <Layers size={9} />}
                {splitMode ? "SEPARADO" : "SOBREPOSTO"}
              </button>
              <button className="flex items-center gap-1 px-2 py-1 text-[9px] border"
                style={{ color: "#5a6a80", borderColor: "#1c2535" }}>
                <Download size={9} />
              </button>
            </div>
          </div>
        </aside>

        {/* ── Chart Area ───────────────────────────────────────────────────── */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {chartChannels.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3" style={{ color: "#3d5065" }}>
              <FlaskConical size={36} strokeWidth={1} />
              <p style={{ fontFamily: "Barlow Condensed, sans-serif", letterSpacing: "0.1em", fontSize: 13 }}>
                SELECIONE VARIÁVEIS NA BARRA LATERAL
              </p>
              <p style={{ fontSize: 11 }}>Clique em qualquer canal para adicionar ao gráfico</p>
            </div>
          ) : splitMode ? (
            // Split: one chart per selected channel
            <div className="flex-1 overflow-hidden" style={{ display: "grid", gridTemplateRows: `repeat(${chartChannels.length}, 1fr)` }}>
              {chartChannels.map((ch) => (
                <SingleChannelChart
                  key={ch.id} ch={ch} data={data} xDomain={xDomain}
                  alarm={isAlarm(ch, lastPoint?.[ch.id] as number | undefined)}
                  lastValue={lastPoint?.[ch.id] as number | undefined}
                />
              ))}
            </div>
          ) : (
            // Overlay: all selected channels on one chart
            <div className="flex-1 flex flex-col overflow-hidden">
              <div className="flex items-center gap-3 px-4 py-2 border-b shrink-0" style={{ borderColor: "#1c2535" }}>
                <span className="text-[9px] tracking-widest" style={{ color: "#3d5065", fontFamily: "Barlow Condensed, sans-serif", letterSpacing: "0.14em" }}>
                  SOBREPOSIÇÃO
                </span>
                {chartChannels.map((ch) => (
                  <div key={ch.id} className="flex items-center gap-1.5">
                    <div className="w-2 h-0.5" style={{ background: ch.color }} />
                    <span className="text-[10px]" style={{ color: ch.color, fontFamily: "Barlow Condensed, sans-serif" }}>
                      {ch.id}
                    </span>
                  </div>
                ))}
              </div>
              <div className="flex-1 min-h-0">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data} margin={{ top: 12, right: 24, left: 4, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="1 5" stroke="#1c2535" vertical={false} />
                    <XAxis dataKey="t" type="number" domain={xDomain}
                      tickFormatter={(v) => `${Number(v).toFixed(0)}s`}
                      tick={{ fill: "#3d5065", fontSize: 9, fontFamily: "JetBrains Mono, monospace" }}
                      axisLine={{ stroke: "#1c2535" }} tickLine={false} />
                    <YAxis tick={{ fill: "#3d5065", fontSize: 9, fontFamily: "JetBrains Mono, monospace" }}
                      axisLine={false} tickLine={false} width={40} />
                    <Tooltip content={<ChartTooltip />} />
                    {chartChannels.map((ch) => (
                      <Line key={ch.id} dataKey={ch.id} stroke={ch.color} strokeWidth={1.5}
                        dot={false} isAnimationActive={false} connectNulls />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* ── Status Bar ────────────────────────────────────────────────── */}
          <div className="flex items-center gap-4 px-4 shrink-0 border-t"
            style={{ height: 28, borderColor: "#1c2535", background: "#0d1118" }}>
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full"
                style={{ background: running ? "#00c8a8" : "#3d5065", boxShadow: running ? "0 0 6px #00c8a8" : "none" }} />
              <span className="text-[9px] tracking-widest"
                style={{ fontFamily: "Barlow Condensed, sans-serif", letterSpacing: "0.14em", color: running ? "#00c8a8" : "#3d5065" }}>
                {running ? "AQUISIÇÃO ATIVA" : "AGUARDANDO"}
              </span>
            </div>
            <span className="text-[9px]" style={{ color: "#3d5065", fontFamily: "JetBrains Mono, monospace" }}>
              {(1000 / TICK_MS).toFixed(0)} Sa/s · BUF {data.length}/{BUFFER}
            </span>
            <span className="text-[9px]" style={{ color: "#3d5065", fontFamily: "JetBrains Mono, monospace" }}>
              STACK: PEM · 100 CÉLULAS · 30 bar MAX
            </span>
            <div className="ml-auto flex items-center gap-2 text-[9px]" style={{ color: "#3d5065", fontFamily: "Barlow Condensed, sans-serif", letterSpacing: "0.08em" }}>
              <span>{selectedIds.length} CANAIS NO GRÁFICO</span>
              <span>·</span>
              <span>CLIQUE CANAL PARA ADICIONAR/REMOVER</span>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

// ─── Single Channel Chart (split mode) ───────────────────────────────────────

function SingleChannelChart({ ch, data, xDomain, alarm, lastValue }: {
  ch: Channel; data: DataPoint[]; xDomain: [number, number];
  alarm: boolean; lastValue: number | undefined;
}) {
  return (
    <div className="flex flex-col border-b" style={{ borderColor: "#1c2535", minHeight: 0 }}>
      <div className="flex items-center gap-3 px-4 py-1.5 shrink-0 border-b" style={{ borderColor: "#1c2535" }}>
        <div className="w-2 h-2 rounded-full" style={{ background: alarm ? "#ef4444" : ch.color }} />
        <span className="text-[11px] font-semibold"
          style={{ fontFamily: "Barlow Condensed, sans-serif", color: alarm ? "#ef4444" : ch.color, letterSpacing: "0.1em" }}>
          {ch.id}
        </span>
        <span className="text-[10px]" style={{ color: "#5a6a80" }}>{ch.label}</span>
        <div className="ml-auto flex items-center gap-4">
          <div className="flex flex-col items-end">
            <span className="text-[9px]" style={{ color: "#3d5065", fontFamily: "Barlow Condensed, sans-serif" }}>ATUAL</span>
            <span className="text-base tabular-nums font-semibold"
              style={{ fontFamily: "JetBrains Mono, monospace", color: alarm ? "#ef4444" : ch.color, lineHeight: 1 }}>
              {lastValue !== undefined ? fmt(lastValue, lastValue > 100 ? 1 : lastValue > 10 ? 2 : 3) : "—"}
              <span className="text-[10px] ml-1" style={{ color: "#5a6a80" }}>{ch.unit}</span>
            </span>
          </div>
          {alarm && (
            <div className="flex items-center gap-1 px-2 py-0.5 border text-[9px]"
              style={{ color: "#ef4444", borderColor: "#ef444440", background: "#ef444410", fontFamily: "Barlow Condensed, sans-serif" }}>
              <AlertTriangle size={9} /> ALARME
            </div>
          )}
          <div className="flex flex-col items-end">
            <span className="text-[9px]" style={{ color: "#3d5065", fontFamily: "Barlow Condensed, sans-serif" }}>FAIXA NOMINAL</span>
            <span className="text-[10px] tabular-nums" style={{ fontFamily: "JetBrains Mono, monospace", color: "#5a6a80" }}>
              {ch.nominalMin} – {ch.nominalMax} {ch.unit}
            </span>
          </div>
        </div>
      </div>
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 6, right: 20, left: 4, bottom: 4 }}>
            <defs>
              <linearGradient id={`grad-${ch.id}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={ch.color} stopOpacity={0.15} />
                <stop offset="95%" stopColor={ch.color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="1 5" stroke="#1c2535" vertical={false} />
            <XAxis dataKey="t" type="number" domain={xDomain}
              tickFormatter={(v) => `${Number(v).toFixed(0)}s`}
              tick={{ fill: "#3d5065", fontSize: 9, fontFamily: "JetBrains Mono, monospace" }}
              axisLine={{ stroke: "#1c2535" }} tickLine={false} />
            <YAxis domain={[ch.nominalMin - (ch.nominalMax - ch.nominalMin) * 0.05, ch.nominalMax + (ch.nominalMax - ch.nominalMin) * 0.05]}
              tickFormatter={(v) => fmt(v, 1)}
              tick={{ fill: "#3d5065", fontSize: 9, fontFamily: "JetBrains Mono, monospace" }}
              axisLine={false} tickLine={false} width={44} />
            <Tooltip content={<ChartTooltip />} />
            {ch.alarmHigh && <ReferenceLine y={ch.alarmHigh} stroke="#ef4444" strokeDasharray="3 3" strokeWidth={1} strokeOpacity={0.5} />}
            {ch.alarmLow !== undefined && <ReferenceLine y={ch.alarmLow} stroke="#f59e0b" strokeDasharray="3 3" strokeWidth={1} strokeOpacity={0.5} />}
            <Area dataKey={ch.id} stroke={ch.color} strokeWidth={1.5} fill={`url(#grad-${ch.id})`}
              dot={false} isAnimationActive={false} connectNulls />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
