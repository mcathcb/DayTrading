import { useState, useEffect, useRef, useCallback } from "react";

// ── Simulated API data (replace BASE_URL with your FastAPI server) ──────────
const BASE_URL = "http://localhost:8000";

const MOCK_SIGNALS = [
  { ticker:"NVDA", strategy:"momentum_breakout", direction:"call", entry:875.40, target:893.20, stop_loss:866.00, confidence:82, rsi:62.4, atr:8.2, risk_reward:1.98, expiry:"2026-05-17", timestamp:"2026-05-10T09:47:00", indicators:{ema_9:872.1,ema_21:865.3,ema_50:851.0,vwap:868.9,macd_hist:2.14} },
  { ticker:"META", strategy:"options_flow", direction:"call", entry:512.80, target:538.60, stop_loss:497.20, confidence:76, rsi:58.1, atr:10.3, risk_reward:1.65, expiry:"2026-05-24", timestamp:"2026-05-10T09:52:00", flow_data:{call_volume:12400,put_volume:2100,call_ratio:0.86,top_vol_oi_ratio:4.2,top_iv:0.38,unusual_contracts:7}, indicators:{vwap:509.3,ema_9:511.2} },
  { ticker:"AMD", strategy:"momentum_breakout", direction:"put", entry:154.20, target:148.80, stop_loss:157.40, confidence:69, rsi:38.6, atr:3.1, risk_reward:1.69, expiry:"2026-05-17", timestamp:"2026-05-10T10:03:00", indicators:{ema_9:155.1,ema_21:157.8,ema_50:161.2,vwap:156.4,macd_hist:-0.87} },
  { ticker:"TSLA", strategy:"options_flow", direction:"put", entry:182.50, target:174.30, stop_loss:187.10, confidence:71, rsi:44.2, atr:4.8, risk_reward:1.78, expiry:"2026-05-24", timestamp:"2026-05-10T10:18:00", flow_data:{call_volume:3200,put_volume:18700,call_ratio:0.15,top_vol_oi_ratio:5.8,top_iv:0.62,unusual_contracts:14}, indicators:{vwap:184.1,ema_9:183.2} },
];

const MOCK_POSITIONS = [
  { ticker:"SPY", direction:"call", entry:521.30, current_price:524.85, stop_loss:517.80, target:531.00, shares:10, unrealized_pnl:355.00, strategy:"momentum_breakout", expiry:"2026-05-17", timestamp:"2026-05-10T09:35:00" },
  { ticker:"QQQ", direction:"call", entry:443.20, current_price:441.10, stop_loss:438.60, target:452.80, shares:8, unrealized_pnl:-168.00, strategy:"options_flow", expiry:"2026-05-24", timestamp:"2026-05-10T09:48:00" },
];

const MOCK_HISTORY = [
  { ticker:"AAPL", direction:"call", entry:189.40, exit_price:194.20, pnl:480, shares:10, strategy:"momentum_breakout", timestamp:"2026-05-09T14:22:00", status:"closed" },
  { ticker:"MSFT", direction:"put", entry:414.80, exit_price:408.30, pnl:650, shares:10, strategy:"options_flow", timestamp:"2026-05-09T13:15:00", status:"closed" },
  { ticker:"AMZN", direction:"call", entry:183.60, exit_price:181.20, pnl:-240, shares:10, strategy:"momentum_breakout", timestamp:"2026-05-09T11:45:00", status:"closed" },
  { ticker:"GOOG", direction:"call", entry:174.20, exit_price:177.90, pnl:370, shares:10, strategy:"momentum_breakout", timestamp:"2026-05-08T15:10:00", status:"closed" },
  { ticker:"NFLX", direction:"put", entry:629.50, exit_price:618.30, pnl:560, shares:5, strategy:"options_flow", timestamp:"2026-05-08T12:30:00", status:"closed" },
  { ticker:"META", direction:"call", entry:497.80, exit_price:494.10, pnl:-185, shares:5, strategy:"momentum_breakout", timestamp:"2026-05-07T10:55:00", status:"closed" },
  { ticker:"TSLA", direction:"put", entry:178.40, exit_price:172.20, pnl:620, shares:10, strategy:"options_flow", timestamp:"2026-05-07T14:40:00", status:"closed" },
];

const PNL_CHART_DATA = [
  { date:"05/01", pnl: 320 },{ date:"05/02", pnl: 780 },{ date:"05/05", pnl: -210 },
  { date:"05/06", pnl: 1100 },{ date:"05/07", pnl: 1035 },{ date:"05/08", pnl: 745 },
  { date:"05/09", pnl: 1490 },{ date:"05/10", pnl: 187 },
];

// ── Utility helpers ────────────────────────────────────────────────────────
const fmt = (n, d=2) => typeof n === 'number' ? (n >= 0 ? '+' : '') + n.toFixed(d) : '—';
const fmtUSD = (n) => typeof n === 'number' ? `${n >= 0 ? '+' : ''}$${Math.abs(n).toLocaleString('en-US', {minimumFractionDigits:2})}` : '—';
const fmtPct = (n) => typeof n === 'number' ? `${(n * 100).toFixed(1)}%` : '—';
const timeAgo = (ts) => { const d = (Date.now() - new Date(ts)) / 60000; return d < 1 ? 'now' : d < 60 ? `${Math.floor(d)}m ago` : `${Math.floor(d/60)}h ago`; };

// ── Mini sparkline ─────────────────────────────────────────────────────────
function Sparkline({ data, color = "#00ff88", width = 80, height = 28 }) {
  if (!data || data.length < 2) return null;
  const vals = data.map(d => d.pnl);
  const min = Math.min(...vals), max = Math.max(...vals);
  const range = max - min || 1;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * width;
    const y = height - ((v - min) / range) * height;
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg width={width} height={height} style={{ overflow: 'visible' }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx={pts.split(' ').at(-1).split(',')[0]} cy={pts.split(' ').at(-1).split(',')[1]} r="2.5" fill={color} />
    </svg>
  );
}

// ── Badge ──────────────────────────────────────────────────────────────────
function Badge({ label, color }) {
  const colors = {
    call: { bg: 'rgba(0,255,136,0.12)', border: '#00ff88', text: '#00ff88' },
    put: { bg: 'rgba(255,80,80,0.12)', border: '#ff5050', text: '#ff5050' },
    momentum_breakout: { bg: 'rgba(255,200,0,0.1)', border: '#ffc800', text: '#ffc800' },
    options_flow: { bg: 'rgba(100,160,255,0.12)', border: '#64a0ff', text: '#64a0ff' },
    manual: { bg: 'rgba(200,100,255,0.12)', border: '#c864ff', text: '#c864ff' },
  };
  const c = colors[label] || colors[color] || { bg: 'rgba(255,255,255,0.06)', border: '#444', text: '#aaa' };
  return (
    <span style={{ background: c.bg, border: `1px solid ${c.border}`, color: c.text, borderRadius: 3, padding: '2px 7px', fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
      {label === 'momentum_breakout' ? 'MOM.BREAK' : label === 'options_flow' ? 'OPT.FLOW' : label}
    </span>
  );
}

// ── Confidence bar ─────────────────────────────────────────────────────────
function ConfBar({ val }) {
  const color = val >= 80 ? '#00ff88' : val >= 60 ? '#ffc800' : '#ff8040';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 64, height: 5, background: 'rgba(255,255,255,0.08)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${val}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.5s' }} />
      </div>
      <span style={{ color, fontSize: 11, fontFamily: 'monospace', fontWeight: 700 }}>{val}%</span>
    </div>
  );
}

// ── PnL chart (simple canvas-like SVG) ────────────────────────────────────
function PnlChart({ data }) {
  const W = 340, H = 90;
  const vals = data.map(d => d.pnl);
  const min = Math.min(...vals, 0), max = Math.max(...vals);
  const range = max - min || 1;
  const toY = v => H - 8 - ((v - min) / range) * (H - 16);
  const toX = i => 24 + (i / (data.length - 1)) * (W - 32);

  const pts = data.map((d, i) => `${toX(i)},${toY(d.pnl)}`).join(' ');
  const areaBase = toY(0);
  const areaPts = `${toX(0)},${areaBase} ${pts} ${toX(data.length-1)},${areaBase}`;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display:'block' }}>
      <defs>
        <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#00ff88" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#00ff88" stopOpacity="0" />
        </linearGradient>
      </defs>
      <line x1="24" y1={toY(0)} x2={W-8} y2={toY(0)} stroke="rgba(255,255,255,0.08)" strokeWidth="1" strokeDasharray="3,3" />
      <polygon points={areaPts} fill="url(#pnlGrad)" />
      <polyline points={pts} fill="none" stroke="#00ff88" strokeWidth="2" strokeLinejoin="round" />
      {data.map((d, i) => (
        <g key={i}>
          <circle cx={toX(i)} cy={toY(d.pnl)} r="2.5" fill={d.pnl >= 0 ? '#00ff88' : '#ff5050'} />
          <text x={toX(i)} y={H-1} textAnchor="middle" fontSize="7" fill="rgba(255,255,255,0.35)">{d.date}</text>
        </g>
      ))}
    </svg>
  );
}

// ── Ticker tape ────────────────────────────────────────────────────────────
function TickerTape({ positions, signals }) {
  const items = [
    ...positions.map(p => ({ ticker: p.ticker, val: p.unrealized_pnl, label: 'PnL' })),
    ...signals.map(s => ({ ticker: s.ticker, val: s.confidence, label: 'CONF', pct: true })),
  ];
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setOffset(o => (o + 0.4) % (items.length * 120 + 1)), 30);
    return () => clearInterval(id);
  }, [items.length]);

  return (
    <div style={{ overflow: 'hidden', borderBottom: '1px solid rgba(255,255,255,0.06)', background: 'rgba(0,0,0,0.4)' }}>
      <div style={{ display: 'flex', transform: `translateX(-${offset}px)`, transition: 'none', whiteSpace: 'nowrap', padding: '6px 0' }}>
        {[...items, ...items].map((it, i) => (
          <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, marginRight: 40, fontFamily: 'monospace', fontSize: 11 }}>
            <span style={{ color: '#fff', fontWeight: 700 }}>{it.ticker}</span>
            <span style={{ color: it.val >= 0 ? '#00ff88' : '#ff5050' }}>
              {it.pct ? `${it.val}%` : fmtUSD(it.val)}
            </span>
            <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: 9 }}>{it.label}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Main Dashboard ─────────────────────────────────────────────────────────
export default function TradingDashboard() {
  const [tab, setTab] = useState('signals');
  const [signals, setSignals] = useState(MOCK_SIGNALS);
  const [positions, setPositions] = useState(MOCK_POSITIONS);
  const [history, setHistory] = useState(MOCK_HISTORY);
  const [engineOn, setEngineOn] = useState(false);
  const [isMarket, setIsMarket] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [selectedSignal, setSelectedSignal] = useState(null);
  const [log, setLog] = useState(["[09:30:01] Market open. Engine initializing...", "[09:31:15] Loaded 8 tickers | vol filter: 500K", "[09:32:44] NVDA: EMA aligned, VWAP hold → SIGNAL", "[09:35:00] SPY: Breakout confirmed, order placed", "[09:48:10] QQQ: Options flow bullish 86% calls", "[09:52:20] META: Unusual OI 4.2× → SIGNAL"]);
  const logRef = useRef(null);

  const totalPnl = history.reduce((s, t) => s + (t.pnl || 0), 0);
  const wins = history.filter(t => t.pnl > 0);
  const winRate = history.length ? wins.length / history.length : 0;
  const unrealized = positions.reduce((s, p) => s + (p.unrealized_pnl || 0), 0);

  const addLog = (msg) => {
    const ts = new Date().toLocaleTimeString('en-US', {hour12:false});
    setLog(l => [...l.slice(-50), `[${ts}] ${msg}`]);
  };

  const handleScan = async () => {
    setScanning(true);
    addLog("Manual scan triggered...");
    await new Promise(r => setTimeout(r, 1800));
    addLog(`Scanned ${MOCK_SIGNALS.length} tickers | ${signals.length} signals found`);
    setScanning(false);
  };

  const handleEngine = () => {
    setEngineOn(e => {
      addLog(e ? "⛔ Engine stopped. Positions closed." : "🚀 Engine started. Scanning every 60s.");
      return !e;
    });
  };

  const closePosition = (ticker) => {
    setPositions(p => p.filter(pos => pos.ticker !== ticker));
    const pos = positions.find(p => p.ticker === ticker);
    if (pos) {
      setHistory(h => [{ ...pos, status:'closed', exit_price: pos.current_price, pnl: pos.unrealized_pnl, timestamp: new Date().toISOString() }, ...h]);
      addLog(`🔴 Closed ${ticker} | PnL: ${fmtUSD(pos.unrealized_pnl)}`);
    }
  };

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [log]);

  // ── Styles ────────────────────────────────────────────────────────────────
  const S = {
    root: { minHeight:'100vh', background:'#080c10', color:'#e0e8f0', fontFamily:"'JetBrains Mono', 'Fira Code', 'Courier New', monospace", fontSize:12 },
    header: { display:'flex', alignItems:'center', justifyContent:'space-between', padding:'14px 20px 10px', borderBottom:'1px solid rgba(0,255,136,0.15)', background:'rgba(0,12,20,0.9)' },
    logo: { display:'flex', alignItems:'center', gap:10 },
    logoIcon: { width:32, height:32, background:'linear-gradient(135deg,#00ff88,#00a0ff)', borderRadius:6, display:'flex', alignItems:'center', justifyContent:'center', fontSize:16 },
    title: { fontSize:15, fontWeight:700, color:'#fff', letterSpacing:'0.08em' },
    subtitle: { fontSize:9, color:'rgba(255,255,255,0.4)', letterSpacing:'0.12em', textTransform:'uppercase' },
    headerRight: { display:'flex', alignItems:'center', gap:12 },
    statusDot: (on) => ({ width:8, height:8, borderRadius:'50%', background: on ? '#00ff88' : '#ff4444', boxShadow: on ? '0 0 8px #00ff88' : 'none', animation: on ? 'pulse 2s infinite' : 'none' }),
    btn: (variant) => ({
      padding: '7px 14px', borderRadius:4, border: 'none', cursor:'pointer', fontSize:11, fontWeight:700, letterSpacing:'0.06em', fontFamily:'inherit',
      ...(variant === 'primary' ? { background:'linear-gradient(90deg,#00cc66,#00a0ff)', color:'#000' } :
         variant === 'danger' ? { background:'rgba(255,60,60,0.12)', border:'1px solid #ff3c3c', color:'#ff6060' } :
         variant === 'ghost' ? { background:'rgba(255,255,255,0.05)', border:'1px solid rgba(255,255,255,0.12)', color:'rgba(255,255,255,0.7)' } :
         { background:'rgba(0,255,136,0.1)', border:'1px solid rgba(0,255,136,0.3)', color:'#00ff88' }),
    }),
    grid: { display:'grid', gridTemplateColumns:'1fr 1fr 1fr 1fr', gap:1, padding:'1px', background:'rgba(255,255,255,0.04)', margin:'0 0 1px' },
    statCard: { background:'#0a0f18', padding:'14px 18px' },
    statLabel: { fontSize:9, color:'rgba(255,255,255,0.35)', letterSpacing:'0.12em', textTransform:'uppercase', marginBottom:6 },
    statVal: (pos) => ({ fontSize:22, fontWeight:700, color: pos === null ? '#fff' : pos ? '#00ff88' : '#ff5050', letterSpacing:'-0.02em' }),
    statSub: { fontSize:9, color:'rgba(255,255,255,0.3)', marginTop:3 },
    tabs: { display:'flex', gap:0, borderBottom:'1px solid rgba(255,255,255,0.06)', paddingLeft:20, background:'#0a0f18' },
    tab: (active) => ({ padding:'10px 18px', fontSize:11, fontWeight:700, letterSpacing:'0.08em', textTransform:'uppercase', cursor:'pointer', border:'none', background:'transparent', color: active ? '#00ff88' : 'rgba(255,255,255,0.4)', borderBottom: active ? '2px solid #00ff88' : '2px solid transparent', transition:'all 0.2s', fontFamily:'inherit' }),
    main: { display:'grid', gridTemplateColumns:'1fr 320px', minHeight:'calc(100vh - 200px)' },
    content: { padding:16, overflowY:'auto' },
    sidebar: { borderLeft:'1px solid rgba(255,255,255,0.06)', display:'flex', flexDirection:'column', height:'calc(100vh - 200px)', overflow:'hidden' },
    sidebarHdr: { padding:'12px 14px', borderBottom:'1px solid rgba(255,255,255,0.06)', fontSize:10, fontWeight:700, letterSpacing:'0.1em', textTransform:'uppercase', color:'rgba(255,255,255,0.5)' },
    table: { width:'100%', borderCollapse:'collapse' },
    th: { textAlign:'left', padding:'7px 10px', fontSize:9, color:'rgba(255,255,255,0.3)', fontWeight:700, letterSpacing:'0.1em', textTransform:'uppercase', borderBottom:'1px solid rgba(255,255,255,0.06)' },
    td: { padding:'9px 10px', borderBottom:'1px solid rgba(255,255,255,0.04)', verticalAlign:'middle' },
    row: (hover) => ({ background: hover ? 'rgba(0,255,136,0.03)' : 'transparent', cursor:'pointer', transition:'background 0.15s' }),
    signalCard: (sel) => ({ background: sel ? 'rgba(0,255,136,0.05)' : 'rgba(255,255,255,0.02)', border: `1px solid ${sel ? 'rgba(0,255,136,0.3)' : 'rgba(255,255,255,0.06)'}`, borderRadius:6, marginBottom:8, padding:'12px 14px', cursor:'pointer', transition:'all 0.2s' }),
    posCard: (pnl) => ({ background:'rgba(255,255,255,0.02)', border:`1px solid ${pnl >= 0 ? 'rgba(0,255,136,0.15)' : 'rgba(255,80,80,0.15)'}`, borderRadius:6, marginBottom:8, padding:'12px 14px' }),
    logWrap: { flex:1, overflowY:'auto', padding:'10px 14px', fontFamily:'monospace', fontSize:10, color:'rgba(255,255,255,0.5)', lineHeight:1.7 },
    detailPanel: { background:'rgba(0,255,136,0.03)', border:'1px solid rgba(0,255,136,0.15)', borderRadius:6, padding:'14px', marginBottom:12 },
    detailRow: { display:'flex', justifyContent:'space-between', alignItems:'center', padding:'4px 0', borderBottom:'1px solid rgba(255,255,255,0.04)' },
    detailKey: { fontSize:10, color:'rgba(255,255,255,0.4)', letterSpacing:'0.06em' },
    detailVal: { fontSize:11, fontWeight:700, fontFamily:'monospace' },
    scanAnim: { animation: 'spin 1s linear infinite' },
  };

  const totalUnrealized = unrealized;
  const dailyLoss = 0;
  const maxDailyLoss = 25000 * 0.05;

  // ── Signal detail panel ───────────────────────────────────────────────────
  const SignalDetail = ({ sig }) => {
    const isCall = sig.direction === 'call';
    const rr = sig.risk_reward;
    return (
      <div style={S.detailPanel}>
        <div style={{ display:'flex', justifyContent:'space-between', marginBottom:12, alignItems:'center' }}>
          <div>
            <span style={{ fontSize:18, fontWeight:700, color:'#fff', marginRight:10 }}>{sig.ticker}</span>
            <Badge label={sig.direction} />
            <span style={{ marginLeft:8 }}><Badge label={sig.strategy} /></span>
          </div>
          <ConfBar val={sig.confidence} />
        </div>
        {[
          ['Entry', `$${sig.entry}`],
          ['Target', { val: `$${sig.target}`, color: '#00ff88' }],
          ['Stop Loss', { val: `$${sig.stop_loss}`, color: '#ff5050' }],
          ['Risk/Reward', { val: `1:${rr}`, color: rr >= 2 ? '#00ff88' : '#ffc800' }],
          ['ATR', `$${sig.atr}`],
          ['RSI', { val: sig.rsi, color: sig.rsi > 70 ? '#ff8040' : sig.rsi < 30 ? '#8080ff' : '#e0e8f0' }],
          ['Expiry', sig.expiry],
          ['Signal time', timeAgo(sig.timestamp)],
        ].map(([k, v]) => (
          <div key={k} style={S.detailRow}>
            <span style={S.detailKey}>{k}</span>
            {typeof v === 'object' && v.val !== undefined
              ? <span style={{ ...S.detailVal, color: v.color }}>{v.val}</span>
              : <span style={S.detailVal}>{v}</span>}
          </div>
        ))}

        {sig.flow_data && (
          <div style={{ marginTop:10, paddingTop:8, borderTop:'1px solid rgba(255,255,255,0.06)' }}>
            <div style={{ fontSize:9, color:'rgba(255,255,255,0.35)', marginBottom:6, letterSpacing:'0.1em' }}>OPTIONS FLOW</div>
            <div style={{ display:'flex', gap:10 }}>
              <div style={{ flex:1, background:'rgba(0,255,136,0.08)', borderRadius:4, padding:'6px 10px', textAlign:'center' }}>
                <div style={{ fontSize:14, fontWeight:700, color:'#00ff88' }}>{(sig.flow_data.call_ratio*100).toFixed(0)}%</div>
                <div style={{ fontSize:8, color:'rgba(255,255,255,0.4)' }}>CALLS</div>
              </div>
              <div style={{ flex:1, background:'rgba(255,80,80,0.08)', borderRadius:4, padding:'6px 10px', textAlign:'center' }}>
                <div style={{ fontSize:14, fontWeight:700, color:'#ff5050' }}>{((1-sig.flow_data.call_ratio)*100).toFixed(0)}%</div>
                <div style={{ fontSize:8, color:'rgba(255,255,255,0.4)' }}>PUTS</div>
              </div>
              <div style={{ flex:1, background:'rgba(255,200,0,0.08)', borderRadius:4, padding:'6px 10px', textAlign:'center' }}>
                <div style={{ fontSize:14, fontWeight:700, color:'#ffc800' }}>{sig.flow_data.top_vol_oi_ratio}×</div>
                <div style={{ fontSize:8, color:'rgba(255,255,255,0.4)' }}>VOL/OI</div>
              </div>
            </div>
          </div>
        )}

        <div style={{ marginTop:12, display:'flex', gap:8 }}>
          <button style={S.btn('primary')} onClick={() => addLog(`📋 Trade queued: ${sig.ticker} ${sig.direction} @ $${sig.entry}`)}>
            ▶ Execute Trade
          </button>
          <button style={S.btn('ghost')} onClick={() => setSelectedSignal(null)}>Dismiss</button>
        </div>
      </div>
    );
  };

  // ── Tab: Signals ──────────────────────────────────────────────────────────
  const TabSignals = () => (
    <div>
      {selectedSignal && <SignalDetail sig={selectedSignal} />}
      <div style={{ marginBottom:10, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <div style={{ fontSize:10, color:'rgba(255,255,255,0.35)' }}>{signals.length} active signals</div>
        <button style={{ ...S.btn('ghost'), fontSize:10 }} onClick={handleScan}>
          {scanning ? '⟳ Scanning...' : '⟳ Rescan Now'}
        </button>
      </div>
      {signals.map((sig, i) => (
        <div key={i} style={S.signalCard(selectedSignal?.ticker === sig.ticker)} onClick={() => setSelectedSignal(selectedSignal?.ticker === sig.ticker ? null : sig)}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
            <div style={{ display:'flex', alignItems:'center', gap:8 }}>
              <span style={{ fontSize:15, fontWeight:700, color:'#fff' }}>{sig.ticker}</span>
              <Badge label={sig.direction} />
              <Badge label={sig.strategy} />
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:10 }}>
              <span style={{ fontSize:9, color:'rgba(255,255,255,0.3)' }}>{timeAgo(sig.timestamp)}</span>
              <ConfBar val={sig.confidence} />
            </div>
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr 1fr', gap:8 }}>
            {[['Entry', `$${sig.entry}`, '#fff'], ['Target', `$${sig.target}`, '#00ff88'], ['Stop', `$${sig.stop_loss}`, '#ff5050'], ['R/R', `1:${sig.risk_reward}`, sig.risk_reward >= 2 ? '#00ff88' : '#ffc800']].map(([lbl, val, col]) => (
              <div key={lbl}>
                <div style={{ fontSize:8, color:'rgba(255,255,255,0.3)', marginBottom:2 }}>{lbl}</div>
                <div style={{ fontSize:12, fontWeight:700, color:col, fontFamily:'monospace' }}>{val}</div>
              </div>
            ))}
          </div>
          {sig.indicators && (
            <div style={{ marginTop:8, display:'flex', gap:12, flexWrap:'wrap' }}>
              {Object.entries(sig.indicators).slice(0,4).map(([k,v]) => (
                <span key={k} style={{ fontSize:9, color:'rgba(255,255,255,0.3)' }}>
                  {k.toUpperCase()} <span style={{ color:'rgba(255,255,255,0.6)' }}>{typeof v === 'number' ? v.toFixed(2) : v}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );

  // ── Tab: Positions ────────────────────────────────────────────────────────
  const TabPositions = () => (
    <div>
      <div style={{ marginBottom:10, fontSize:10, color:'rgba(255,255,255,0.35)' }}>
        {positions.length} open position{positions.length !== 1 ? 's' : ''} · Unrealized: <span style={{ color: unrealized >= 0 ? '#00ff88' : '#ff5050', fontWeight:700 }}>{fmtUSD(unrealized)}</span>
      </div>
      {positions.length === 0 && <div style={{ color:'rgba(255,255,255,0.25)', textAlign:'center', padding:'40px 0', fontSize:11 }}>No open positions</div>}
      {positions.map((pos, i) => {
        const pnl = pos.unrealized_pnl;
        const pnlPct = ((pos.current_price - pos.entry) / pos.entry * 100).toFixed(2);
        const dist_target = ((pos.target - pos.current_price) / pos.target * 100).toFixed(1);
        const dist_stop = ((pos.current_price - pos.stop_loss) / pos.current_price * 100).toFixed(1);
        return (
          <div key={i} style={S.posCard(pnl)}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <span style={{ fontSize:16, fontWeight:700, color:'#fff' }}>{pos.ticker}</span>
                <Badge label={pos.direction} />
                <Badge label={pos.strategy} />
              </div>
              <div style={{ textAlign:'right' }}>
                <div style={{ fontSize:16, fontWeight:700, color: pnl >= 0 ? '#00ff88' : '#ff5050' }}>{fmtUSD(pnl)}</div>
                <div style={{ fontSize:9, color: pnl >= 0 ? '#00cc55' : '#cc3333' }}>{pnl >= 0 ? '▲' : '▼'} {Math.abs(pnlPct)}%</div>
              </div>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(5,1fr)', gap:8, marginBottom:10 }}>
              {[['Entry', `$${pos.entry}`], ['Current', `$${pos.current_price}`], ['Target', `$${pos.target}`], ['Stop', `$${pos.stop_loss}`], ['Shares', pos.shares]].map(([k,v]) => (
                <div key={k}>
                  <div style={{ fontSize:8, color:'rgba(255,255,255,0.3)', marginBottom:1 }}>{k}</div>
                  <div style={{ fontSize:11, fontWeight:700, fontFamily:'monospace' }}>{v}</div>
                </div>
              ))}
            </div>
            {/* Progress bar: stop → current → target */}
            <div style={{ marginBottom:10 }}>
              <div style={{ display:'flex', justifyContent:'space-between', fontSize:8, color:'rgba(255,255,255,0.3)', marginBottom:3 }}>
                <span>STOP ${pos.stop_loss}</span>
                <span>TARGET ${pos.target}</span>
              </div>
              <div style={{ height:5, background:'rgba(255,255,255,0.08)', borderRadius:3, overflow:'hidden', position:'relative' }}>
                {(() => {
                  const range = pos.target - pos.stop_loss;
                  const pct = Math.max(0, Math.min(100, (pos.current_price - pos.stop_loss) / range * 100));
                  return <div style={{ width:`${pct}%`, height:'100%', background: pct > 70 ? '#00ff88' : pct > 40 ? '#ffc800' : '#ff5050', borderRadius:3 }} />;
                })()}
              </div>
            </div>
            <div style={{ display:'flex', gap:8, alignItems:'center', justifyContent:'space-between' }}>
              <div style={{ fontSize:9, color:'rgba(255,255,255,0.3)' }}>Expiry: {pos.expiry} · Open {timeAgo(pos.timestamp)}</div>
              <button style={S.btn('danger')} onClick={() => closePosition(pos.ticker)}>✕ Close</button>
            </div>
          </div>
        );
      })}
    </div>
  );

  // ── Tab: History ──────────────────────────────────────────────────────────
  const TabHistory = () => (
    <div>
      <div style={{ marginBottom:10, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <span style={{ fontSize:10, color:'rgba(255,255,255,0.35)' }}>{history.length} closed trades</span>
        <div style={{ fontSize:10, color:'rgba(255,255,255,0.35)' }}>
          Win rate: <span style={{ color:'#00ff88', fontWeight:700 }}>{fmtPct(winRate)}</span>
          {' '}· Total P&L: <span style={{ color: totalPnl >= 0 ? '#00ff88' : '#ff5050', fontWeight:700 }}>{fmtUSD(totalPnl)}</span>
        </div>
      </div>
      <table style={S.table}>
        <thead>
          <tr>{['Ticker','Direction','Strategy','Entry','Exit','P&L','Time'].map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {history.map((t, i) => (
            <tr key={i} style={S.row(false)}>
              <td style={S.td}><span style={{ fontWeight:700, color:'#fff' }}>{t.ticker}</span></td>
              <td style={S.td}><Badge label={t.direction} /></td>
              <td style={S.td}><Badge label={t.strategy} /></td>
              <td style={{ ...S.td, fontFamily:'monospace' }}>${t.entry}</td>
              <td style={{ ...S.td, fontFamily:'monospace' }}>${t.exit_price}</td>
              <td style={{ ...S.td, fontFamily:'monospace', color: t.pnl >= 0 ? '#00ff88' : '#ff5050', fontWeight:700 }}>{fmtUSD(t.pnl)}</td>
              <td style={{ ...S.td, color:'rgba(255,255,255,0.3)', fontSize:10 }}>{timeAgo(t.timestamp)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  // ── Tab: Analytics ────────────────────────────────────────────────────────
  const TabAnalytics = () => {
    const byStrat = {};
    history.forEach(t => {
      if (!byStrat[t.strategy]) byStrat[t.strategy] = { trades:0, wins:0, pnl:0 };
      byStrat[t.strategy].trades++;
      if (t.pnl > 0) byStrat[t.strategy].wins++;
      byStrat[t.strategy].pnl += t.pnl;
    });

    return (
      <div>
        <div style={{ marginBottom:16 }}>
          <div style={{ fontSize:10, color:'rgba(255,255,255,0.35)', marginBottom:8, letterSpacing:'0.1em', textTransform:'uppercase' }}>7-Day P&L Curve</div>
          <div style={{ background:'rgba(255,255,255,0.02)', border:'1px solid rgba(255,255,255,0.06)', borderRadius:6, padding:'12px 8px' }}>
            <PnlChart data={PNL_CHART_DATA} />
          </div>
        </div>

        <div style={{ marginBottom:16 }}>
          <div style={{ fontSize:10, color:'rgba(255,255,255,0.35)', marginBottom:8, letterSpacing:'0.1em', textTransform:'uppercase' }}>Strategy Performance</div>
          {Object.entries(byStrat).map(([strat, s]) => (
            <div key={strat} style={{ background:'rgba(255,255,255,0.02)', border:'1px solid rgba(255,255,255,0.06)', borderRadius:6, padding:'10px 14px', marginBottom:6 }}>
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:6 }}>
                <Badge label={strat} />
                <span style={{ color: s.pnl >= 0 ? '#00ff88' : '#ff5050', fontWeight:700, fontFamily:'monospace' }}>{fmtUSD(s.pnl)}</span>
              </div>
              <div style={{ display:'flex', gap:16, fontSize:10, color:'rgba(255,255,255,0.5)' }}>
                <span>Trades: <b style={{ color:'#fff' }}>{s.trades}</b></span>
                <span>Win rate: <b style={{ color:'#00ff88' }}>{(s.wins/s.trades*100).toFixed(0)}%</b></span>
                <span>Avg: <b style={{ color: s.pnl/s.trades >= 0 ? '#00ff88' : '#ff5050' }}>{fmtUSD(s.pnl/s.trades)}</b></span>
              </div>
            </div>
          ))}
        </div>

        <div>
          <div style={{ fontSize:10, color:'rgba(255,255,255,0.35)', marginBottom:8, letterSpacing:'0.1em', textTransform:'uppercase' }}>Risk Metrics</div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
            {[
              ['Win Rate', fmtPct(winRate), winRate >= 0.5 ? '#00ff88' : '#ff5050'],
              ['Avg Win', fmtUSD(wins.reduce((s,t) => s+t.pnl,0)/wins.length||0), '#00ff88'],
              ['Avg Loss', fmtUSD(history.filter(t=>t.pnl<0).reduce((s,t)=>s+t.pnl,0)/(history.filter(t=>t.pnl<0).length||1)), '#ff5050'],
              ['Daily Loss Used', `${(dailyLoss/maxDailyLoss*100).toFixed(0)}%`, '#ffc800'],
              ['Max Risk/Trade', '2.0%', '#64a0ff'],
              ['Sizing Method', 'Fixed Frac.', '#aaa'],
            ].map(([k,v,c]) => (
              <div key={k} style={{ background:'rgba(255,255,255,0.02)', border:'1px solid rgba(255,255,255,0.06)', borderRadius:6, padding:'10px 12px' }}>
                <div style={{ fontSize:8, color:'rgba(255,255,255,0.3)', marginBottom:4, textTransform:'uppercase', letterSpacing:'0.1em' }}>{k}</div>
                <div style={{ fontSize:14, fontWeight:700, color: c || '#fff', fontFamily:'monospace' }}>{v}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  const tabContent = { signals: <TabSignals />, positions: <TabPositions />, history: <TabHistory />, analytics: <TabAnalytics /> };

  return (
    <div style={S.root}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 4px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: rgba(0,255,136,0.2); border-radius: 2px; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        .blink { animation: blink 1.2s infinite; }
      `}</style>

      {/* Header */}
      <div style={S.header}>
        <div style={S.logo}>
          <div style={S.logoIcon}>⚡</div>
          <div>
            <div style={S.title}>APEX TRADING ENGINE</div>
            <div style={S.subtitle}>Day Trading Strategy System · v1.0</div>
          </div>
        </div>
        <div style={S.headerRight}>
          <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:10, color:'rgba(255,255,255,0.4)' }}>
            <div style={S.statusDot(isMarket)} />
            <span style={{ color: isMarket ? '#00ff88' : 'rgba(255,255,255,0.4)' }}>{isMarket ? 'MARKET OPEN' : 'AFTER HOURS'}</span>
          </div>
          <div style={{ width:1, height:20, background:'rgba(255,255,255,0.1)' }} />
          <button style={S.btn(engineOn ? 'danger' : 'primary')} onClick={handleEngine}>
            {engineOn ? '⛔ Stop Engine' : '▶ Start Engine'}
          </button>
          <button style={S.btn('ghost')} onClick={handleScan}>
            {scanning ? <span style={{ display:'inline-block', animation:'spin 1s linear infinite' }}>⟳</span> : '⟳'} Scan
          </button>
        </div>
      </div>

      {/* Ticker tape */}
      <TickerTape positions={positions} signals={signals} />

      {/* Stat cards */}
      <div style={S.grid}>
        {[
          { label:'Total P&L (Closed)', val: fmtUSD(totalPnl), pos: totalPnl > 0, sub: `${history.length} trades closed` },
          { label:'Unrealized P&L', val: fmtUSD(unrealized), pos: unrealized > 0, sub: `${positions.length} open positions` },
          { label:'Win Rate', val: fmtPct(winRate), pos: winRate >= 0.5, sub: `${wins.length}W / ${history.length - wins.length}L` },
          { label:'Daily Loss Used', val: `${(dailyLoss/maxDailyLoss*100).toFixed(0)}% / 5%`, pos: null, sub: `Limit: $${maxDailyLoss.toLocaleString()}` },
        ].map(s => (
          <div key={s.label} style={S.statCard}>
            <div style={S.statLabel}>{s.label}</div>
            <div style={S.statVal(s.pos)}>{s.val}</div>
            <div style={S.statSub}>{s.sub}</div>
          </div>
        ))}
      </div>

      {/* Tabs + Content */}
      <div style={S.tabs}>
        {[['signals',`Signals (${signals.length})`],['positions',`Positions (${positions.length})`],['history','History'],['analytics','Analytics']].map(([id,label]) => (
          <button key={id} style={S.tab(tab===id)} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      <div style={S.main}>
        <div style={S.content}>{tabContent[tab]}</div>

        {/* Sidebar: engine log */}
        <div style={S.sidebar}>
          <div style={S.sidebarHdr}>
            <span>Engine Log</span>
            <span style={{ float:'right', color: engineOn ? '#00ff88' : 'rgba(255,255,255,0.3)', fontSize:9 }} className={engineOn ? 'blink' : ''}>
              {engineOn ? '● LIVE' : '○ IDLE'}
            </span>
          </div>
          <div style={S.logWrap} ref={logRef}>
            {log.map((line, i) => {
              const isSignal = line.includes('SIGNAL');
              const isError = line.includes('ERROR') || line.includes('⛔');
              const isGood = line.includes('🚀') || line.includes('🟢');
              const color = isSignal ? '#00ff88' : isError ? '#ff5050' : isGood ? '#64a0ff' : 'rgba(255,255,255,0.45)';
              return <div key={i} style={{ color, marginBottom:1 }}>{line}</div>;
            })}
            <div style={{ color:'rgba(0,255,136,0.5)' }} className="blink">▊</div>
          </div>
          <div style={{ padding:'10px 14px', borderTop:'1px solid rgba(255,255,255,0.06)', fontSize:10, color:'rgba(255,255,255,0.3)' }}>
            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
              <span>Broker</span><span style={{ color:'#fff' }}>Paper Trading</span>
            </div>
            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
              <span>Scan interval</span><span style={{ color:'#fff' }}>60s</span>
            </div>
            <div style={{ display:'flex', justifyContent:'space-between' }}>
              <span>Account</span><span style={{ color:'#00ff88' }}>$25,000</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
