import React, { useEffect, useMemo, useRef, useState } from "react";
import UplotReact from "uplot-react";
import "uplot/dist/uPlot.min.css";

const MAX_LIVE_POINTS = 240; // ~2 min at 2 Hz

export default function App() {
  const [assets, setAssets] = useState([]);
  const [latest, setLatest] = useState({});            // asset_id -> {metric: value}
  const [alarms, setAlarms] = useState([]);            // active alarms
  const [history, setHistory] = useState([]);          // alarm history
  const [oee, setOee] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [view, setView] = useState("floor");           // 'floor' | 'fleet' | 'alarms'
  const [connected, setConnected] = useState(false);

  // live ring buffers: asset_id -> metric -> [{ts, value}]
  const buffersRef = useRef({});

  // --- Bootstrap -------------------------------------------------------------
  useEffect(() => {
    fetch("/api/assets").then(r => r.json()).then(setAssets);
    fetch("/api/alarms/active").then(r => r.json()).then(setAlarms);
    fetch("/api/alarms/history").then(r => r.json()).then(setHistory);

    const oeeTimer = setInterval(() => {
      fetch("/api/oee").then(r => r.json()).then(setOee);
    }, 2000);
    return () => clearInterval(oeeTimer);
  }, []);

  // --- WebSocket -------------------------------------------------------------
  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);

    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);

      if (msg.type === "snapshot") {
        setLatest(msg.latest || {});
        setAlarms(msg.active_alarms || []);
      } else if (msg.type === "reading") {
        const { asset_id, metric, value, ts } = msg;
        // update latest
        setLatest(prev => ({
          ...prev,
          [asset_id]: { ...(prev[asset_id] || {}), [metric]: value },
        }));
        // ring buffer
        const bufs = buffersRef.current;
        bufs[asset_id] = bufs[asset_id] || {};
        const arr = bufs[asset_id][metric] = bufs[asset_id][metric] || [];
        arr.push({ ts, value });
        if (arr.length > MAX_LIVE_POINTS) arr.shift();
      } else if (msg.type === "alarm_raised") {
        setAlarms(a => [msg.alarm, ...a]);
        setHistory(h => [msg.alarm, ...h].slice(0, 200));
      } else if (msg.type === "alarm_cleared") {
        setAlarms(a => a.filter(x => x.key !== msg.alarm.key));
      } else if (msg.type === "alarm_acked") {
        setAlarms(a => a.map(x => x.key === msg.key ? { ...x, acknowledged: true } : x));
      }
    };

    return () => ws.close();
  }, []);

  const selected = assets.find(a => a.id === selectedId);
  const alarmingIds = useMemo(
    () => new Set(alarms.map(a => a.asset_id)),
    [alarms]
  );

  return (
    <div style={{ display: "grid", gridTemplateRows: "auto 1fr", height: "100vh" }}>
      <Header connected={connected} oee={oee} view={view} setView={setView} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", overflow: "hidden" }}>
        <main style={{ padding: 16, overflow: "auto" }}>
          {view === "floor" && (
            <FloorMap
              assets={assets}
              alarmingIds={alarmingIds}
              latest={latest}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          )}
          {view === "floor" && selected && (
            <AssetDetail
              asset={selected}
              latest={latest[selected.id] || {}}
              buffers={buffersRef.current[selected.id] || {}}
            />
          )}
          {view === "fleet" && <FleetView assets={assets} alarmingIds={alarmingIds} latest={latest} oee={oee} />}
          {view === "alarms" && <AlarmHistory history={history} />}
        </main>
        <AlarmConsole alarms={alarms} onAck={async (k) => {
          await fetch(`/api/alarms/${encodeURIComponent(k)}/ack`, { method: "POST" });
        }} />
      </div>
    </div>
  );
}

// =============================================================================
// Header / status bar
// =============================================================================
function Header({ connected, oee, view, setView }) {
  const tabs = [
    ["floor",  "Factory Floor"],
    ["fleet",  "Fleet Overview"],
    ["alarms", "Alarm History"],
  ];
  return (
    <header style={{
      borderBottom: "1px solid var(--border)",
      background: "var(--panel)",
      padding: "10px 18px",
      display: "flex", alignItems: "center", gap: 24,
    }}>
      <div style={{ fontFamily: "var(--mono)", letterSpacing: 2, fontWeight: 600 }}>
        BLUE&nbsp;ORIGIN&nbsp;·&nbsp;NEW&nbsp;GLENN&nbsp;FACTORY
      </div>
      <div style={{ color: "var(--muted)", fontFamily: "var(--mono)", fontSize: 11 }}>
        EXPLORATION PARK · MERRITT ISLAND, FL
      </div>
      <div style={{ flex: 1 }} />
      <nav style={{ display: "flex", gap: 4 }}>
        {tabs.map(([id, label]) => (
          <button key={id} onClick={() => setView(id)}
            style={{
              padding: "6px 12px", border: "1px solid var(--border)",
              background: view === id ? "var(--panel-2)" : "transparent",
              color: view === id ? "var(--accent)" : "var(--text)",
              fontFamily: "var(--mono)", fontSize: 11, cursor: "pointer",
              borderRadius: 4,
            }}>{label}</button>
        ))}
      </nav>
      {oee && (
        <div style={{ display: "flex", gap: 16, fontFamily: "var(--mono)", fontSize: 11 }}>
          <KPI label="ONLINE" value={`${oee.online}/${oee.total_assets}`} tone="good" />
          <KPI label="ALARMS" value={oee.active_alarms} tone={oee.active_alarms ? "bad" : "muted"} />
          <KPI label="AVAIL" value={`${(oee.availability * 100).toFixed(1)}%`} tone="good" />
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{
          width: 8, height: 8, borderRadius: "50%",
          background: connected ? "var(--good)" : "var(--bad)",
          boxShadow: connected ? "0 0 6px var(--good)" : "none",
        }} />
        <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--muted)" }}>
          {connected ? "TELEMETRY LIVE" : "DISCONNECTED"}
        </span>
      </div>
    </header>
  );
}

function KPI({ label, value, tone }) {
  const colors = { good: "var(--good)", bad: "var(--bad)", muted: "var(--muted)" };
  return (
    <div>
      <div style={{ color: "var(--muted)", fontSize: 10 }}>{label}</div>
      <div style={{ color: colors[tone] || "var(--text)", fontWeight: 600, fontSize: 14 }}>{value}</div>
    </div>
  );
}

// =============================================================================
// Factory floor map
// =============================================================================
function FloorMap({ assets, alarmingIds, latest, selectedId, onSelect }) {
  const areas = [
    { id: "tank-fab",   x: 60,  y: 80,  w: 200, h: 240, label: "TANK FAB" },
    { id: "composites", x: 280, y: 80,  w: 200, h: 320, label: "COMPOSITES" },
    { id: "chem-proc",  x: 500, y: 80,  w: 160, h: 240, label: "CHEM PROC" },
    { id: "2cat",       x: 680, y: 80,  w: 160, h: 120, label: "2CAT" },
    { id: "hif",        x: 680, y: 220, w: 160, h: 140, label: "HIF" },
  ];

  return (
    <section style={{
      background: "var(--panel)", border: "1px solid var(--border)",
      borderRadius: 6, padding: 16, marginBottom: 16,
    }}>
      <SectionTitle title="Factory Floor" subtitle="Click an asset for live telemetry" />
      <svg viewBox="0 0 880 420" style={{ width: "100%", height: 420, display: "block" }}>
        <defs>
          <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#1a2230" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="880" height="420" fill="url(#grid)" />

        {areas.map(area => (
          <g key={area.id}>
            <rect x={area.x} y={area.y} width={area.w} height={area.h}
              fill="var(--panel-2)" stroke="var(--border)" strokeWidth="1" rx="4" />
            <text x={area.x + 8} y={area.y + 16} fill="var(--muted)"
              fontFamily="var(--mono)" fontSize="10" letterSpacing="2">
              {area.label}
            </text>
          </g>
        ))}

        {assets.map(a => {
          const alarming = alarmingIds.has(a.id);
          const stale = !latest[a.id];
          const fill = alarming ? "var(--bad)" : stale ? "var(--muted)" : "var(--good)";
          const isSelected = selectedId === a.id;
          return (
            <g key={a.id} style={{ cursor: "pointer" }} onClick={() => onSelect(a.id)}>
              <circle cx={a.x} cy={a.y} r={isSelected ? 14 : 10} fill={fill}
                opacity={alarming ? 1 : 0.85}
                style={alarming ? { filter: "drop-shadow(0 0 6px var(--bad))" } : {}}>
                {alarming && (
                  <animate attributeName="r" values="10;15;10" dur="1.2s" repeatCount="indefinite" />
                )}
              </circle>
              {isSelected && (
                <circle cx={a.x} cy={a.y} r={20} fill="none" stroke="var(--accent)" strokeWidth="2" />
              )}
              <text x={a.x} y={a.y + 28} fill="var(--text)" fontFamily="var(--mono)"
                fontSize="10" textAnchor="middle">{a.id}</text>
            </g>
          );
        })}
      </svg>
    </section>
  );
}

// =============================================================================
// Asset detail with live charts
// =============================================================================
function AssetDetail({ asset, latest, buffers }) {
  return (
    <section style={{
      background: "var(--panel)", border: "1px solid var(--border)",
      borderRadius: 6, padding: 16,
    }}>
      <SectionTitle
        title={`${asset.name} (${asset.id})`}
        subtitle={`${asset.type_label} · ${asset.area}/${asset.cell}`}
      />
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
        gap: 12,
      }}>
        {asset.metrics.map(m => (
          <MetricCard key={m.name} metric={m}
            latest={latest[m.name]}
            buffer={buffers[m.name] || []} />
        ))}
      </div>
    </section>
  );
}

function MetricCard({ metric, latest, buffer }) {
  const high = metric.redline_high, low = metric.redline_low;
  const value = latest;
  const breached = value !== undefined && (value > high || value < low);

  // Build uPlot data from ring buffer
  const data = useMemo(() => {
    if (!buffer.length) return [[], []];
    const xs = buffer.map(p => p.ts / 1000);
    const ys = buffer.map(p => p.value);
    return [xs, ys];
  }, [buffer.length, buffer[buffer.length - 1]?.ts]);

  const opts = useMemo(() => ({
    width: 320, height: 110,
    cursor: { show: false },
    legend: { show: false },
    scales: { x: { time: true }, y: { auto: true } },
    axes: [
      { stroke: "var(--muted)", grid: { stroke: "#1a2230" }, size: 30, font: "10px ui-monospace" },
      { stroke: "var(--muted)", grid: { stroke: "#1a2230" }, size: 40, font: "10px ui-monospace" },
    ],
    series: [
      {},
      { stroke: breached ? "#ff4d4f" : "#4ad8ff", width: 1.5,
        fill: breached ? "rgba(255,77,79,0.10)" : "rgba(74,216,255,0.10)" },
    ],
  }), [breached]);

  return (
    <div style={{
      background: "var(--panel-2)", border: `1px solid ${breached ? "var(--bad)" : "var(--border)"}`,
      borderRadius: 4, padding: 12,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--muted)" }}>
          {metric.name.toUpperCase()}
        </span>
        <span style={{
          fontFamily: "var(--mono)", fontSize: 18, fontWeight: 600,
          color: breached ? "var(--bad)" : "var(--text)",
        }}>
          {value !== undefined ? value.toFixed(2) : "—"}
        </span>
      </div>
      <div style={{ fontSize: 10, color: "var(--muted)", fontFamily: "var(--mono)", marginBottom: 6 }}>
        redline: {low} / {high}
      </div>
      {data[0].length > 1 && <UplotReact options={opts} data={data} />}
    </div>
  );
}

// =============================================================================
// Fleet overview (table)
// =============================================================================
function FleetView({ assets, alarmingIds, latest, oee }) {
  return (
    <section style={{
      background: "var(--panel)", border: "1px solid var(--border)",
      borderRadius: 6, padding: 16,
    }}>
      <SectionTitle title="Fleet Overview" subtitle="All monitored assets" />
      <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--mono)", fontSize: 12 }}>
        <thead>
          <tr style={{ color: "var(--muted)", textAlign: "left" }}>
            {["ASSET", "TYPE", "AREA", "STATUS", "METRICS"].map(h => (
              <th key={h} style={{ padding: "8px 6px", borderBottom: "1px solid var(--border)" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {assets.map(a => {
            const alarming = alarmingIds.has(a.id);
            const stale = !latest[a.id];
            const status = alarming ? "ALARM" : stale ? "OFFLINE" : "NOMINAL";
            const tone = alarming ? "var(--bad)" : stale ? "var(--muted)" : "var(--good)";
            const metricCount = a.metrics.length;
            return (
              <tr key={a.id} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={{ padding: "8px 6px" }}>{a.id} — {a.name}</td>
                <td style={{ padding: "8px 6px", color: "var(--muted)" }}>{a.type_label}</td>
                <td style={{ padding: "8px 6px", color: "var(--muted)" }}>{a.area}/{a.cell}</td>
                <td style={{ padding: "8px 6px", color: tone, fontWeight: 600 }}>{status}</td>
                <td style={{ padding: "8px 6px", color: "var(--muted)" }}>{metricCount} tags</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

// =============================================================================
// Alarm console (right rail, always visible)
// =============================================================================
function AlarmConsole({ alarms, onAck }) {
  return (
    <aside style={{
      borderLeft: "1px solid var(--border)", background: "var(--panel)",
      display: "flex", flexDirection: "column", overflow: "hidden",
    }}>
      <div style={{
        padding: "12px 16px", borderBottom: "1px solid var(--border)",
        display: "flex", justifyContent: "space-between",
      }}>
        <span style={{ fontFamily: "var(--mono)", fontSize: 11, letterSpacing: 2, color: "var(--muted)" }}>
          ACTIVE ALARMS
        </span>
        <span style={{ fontFamily: "var(--mono)", fontSize: 14, fontWeight: 600,
          color: alarms.length ? "var(--bad)" : "var(--good)" }}>
          {alarms.length}
        </span>
      </div>
      <div style={{ overflow: "auto", flex: 1 }}>
        {!alarms.length && (
          <div style={{ padding: 20, color: "var(--muted)", fontFamily: "var(--mono)", fontSize: 11, textAlign: "center" }}>
            ALL SYSTEMS NOMINAL
          </div>
        )}
        {alarms.map(a => (
          <div key={a.key} style={{
            padding: 12, borderBottom: "1px solid var(--border)",
            opacity: a.acknowledged ? 0.5 : 1,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, color: "var(--bad)" }}>
                {a.asset_id}
              </span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--muted)" }}>
                {new Date(a.raised_at).toLocaleTimeString()}
              </span>
            </div>
            <div style={{ fontSize: 11, color: "var(--text)", marginBottom: 8 }}>
              {a.message}
            </div>
            {!a.acknowledged && (
              <button onClick={() => onAck(a.key)} style={{
                fontFamily: "var(--mono)", fontSize: 10, padding: "4px 10px",
                background: "transparent", color: "var(--accent)",
                border: "1px solid var(--accent)", borderRadius: 3, cursor: "pointer",
              }}>ACK</button>
            )}
            {a.acknowledged && (
              <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--muted)" }}>
                ACKNOWLEDGED
              </span>
            )}
          </div>
        ))}
      </div>
    </aside>
  );
}

// =============================================================================
// Alarm history view
// =============================================================================
function AlarmHistory({ history }) {
  return (
    <section style={{
      background: "var(--panel)", border: "1px solid var(--border)",
      borderRadius: 6, padding: 16,
    }}>
      <SectionTitle title="Alarm History" subtitle="Last 200 events" />
      <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--mono)", fontSize: 12 }}>
        <thead>
          <tr style={{ color: "var(--muted)", textAlign: "left" }}>
            {["TIME", "ASSET", "METRIC", "VALUE", "MESSAGE"].map(h => (
              <th key={h} style={{ padding: "8px 6px", borderBottom: "1px solid var(--border)" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {history.map((a, i) => (
            <tr key={`${a.key}-${i}`} style={{ borderBottom: "1px solid var(--border)" }}>
              <td style={{ padding: "6px", color: "var(--muted)" }}>
                {new Date(a.raised_at).toLocaleString()}
              </td>
              <td style={{ padding: "6px" }}>{a.asset_id}</td>
              <td style={{ padding: "6px", color: "var(--muted)" }}>{a.metric}</td>
              <td style={{ padding: "6px", color: "var(--bad)" }}>{a.value?.toFixed?.(2)}</td>
              <td style={{ padding: "6px", color: "var(--muted)" }}>{a.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function SectionTitle({ title, subtitle }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <h2 style={{ margin: 0, fontSize: 14, fontFamily: "var(--mono)", letterSpacing: 1 }}>
        {title.toUpperCase()}
      </h2>
      {subtitle && (
        <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 2 }}>{subtitle}</div>
      )}
    </div>
  );
}
