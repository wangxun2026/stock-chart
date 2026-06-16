#!/usr/bin/env python3
"""
Fetches UGRO + FLZH data from Yahoo Finance across multiple timeframes
and generates a self-contained index.html with interactive charts.
Run locally or via GitHub Actions daily.
"""

import json, time, urllib.request, datetime, sys

# ── Helpers ────────────────────────────────────────────────────────

def ts_to_et(ts):
    """Unix timestamp → US Eastern time string (DST-aware)."""
    dt = datetime.datetime.utcfromtimestamp(ts)
    y = dt.year
    mar1 = datetime.datetime(y, 3, 1)
    dst_start = mar1 + datetime.timedelta(days=(6 - mar1.weekday() + 7) % 7 + 7)
    nov1 = datetime.datetime(y, 11, 1)
    dst_end = nov1 + datetime.timedelta(days=(6 - nov1.weekday()) % 7)
    offset = -4 if dst_start <= dt < dst_end else -5
    local = datetime.datetime.utcfromtimestamp(ts + offset * 3600)
    return local.strftime("%Y-%m-%d %H:%M")

def fetch(ticker, interval="1d", range_="10y"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?interval={interval}&range={range_}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = json.loads(r.read())
    except Exception as e:
        print(f"  WARN {ticker} {interval}: {e}", file=sys.stderr)
        return []
    try:
        res = raw["chart"]["result"][0]
    except (KeyError, TypeError, IndexError):
        return []

    timestamps = res.get("timestamp", [])
    q = res["indicators"]["quote"][0]
    vols = q.get("volume") or [0] * len(timestamps)
    is_daily = interval in ("1d", "1wk", "1mo")
    rows = []
    for i, ts in enumerate(timestamps):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        date_str = (time.strftime("%Y-%m-%d", time.gmtime(ts)) if is_daily
                    else ts_to_et(ts))
        rows.append({
            "date":   date_str,
            "open":   round(o, 4), "high": round(h, 4),
            "low":    round(l, 4), "close": round(c, 4),
            "volume": int(vols[i] or 0),
        })
    return rows

# ── Fetch daily ────────────────────────────────────────────────────

print("→ UGRO daily (10y)"); ugro_d = fetch("UGRO", "1d", "10y")
print(f"  {len(ugro_d)} rows, {ugro_d[0]['date'] if ugro_d else 'N/A'} → {ugro_d[-1]['date'] if ugro_d else 'N/A'}")

print("→ FLZH daily (2y)");  flzh_d = fetch("FLZH", "1d", "2y")
print(f"  {len(flzh_d)} rows" + (f", {flzh_d[0]['date']} → {flzh_d[-1]['date']}" if flzh_d else ""))

cutover  = flzh_d[0]["date"] if flzh_d else None
daily    = [r for r in ugro_d if not cutover or r["date"] < cutover] + flzh_d
ugro_end = ([r for r in ugro_d if not cutover or r["date"] < cutover] or ugro_d)[-1]["date"]
print(f"  combined {len(daily)} rows, cutover={cutover}")

# ── Fetch intraday ─────────────────────────────────────────────────

# Intraday: merge UGRO (traded through June 15 2026) + FLZH (June 16 onward)
# Use date-based dedup so UGRO bars are only kept on days FLZH has no data.
def fetch_intra(label, interval, ugro_range, flzh_range):
    print(f"→ {label}: UGRO({ugro_range}) + FLZH({flzh_range})")
    u = fetch("UGRO", interval, ugro_range)
    f = fetch("FLZH", interval, flzh_range)
    f_dates = {r["date"][:10] for r in f}
    u_ok = [r for r in u if r["date"][:10] not in f_dates]
    merged = sorted(u_ok + f, key=lambda r: r["date"])
    print(f"  {len(u_ok)} UGRO + {len(f)} FLZH = {len(merged)} rows" +
          (f", {merged[0]['date']} → {merged[-1]['date']}" if merged else ""))
    return merged

h1  = fetch_intra("1h",  "60m", "730d", "730d")  # Yahoo max 730d for 60m
m30 = fetch_intra("30m", "30m", "60d",  "60d")   # Yahoo max 60d for 30m
m15 = fetch_intra("15m", "15m", "60d",  "60d")
m5  = fetch_intra("5m",  "5m",  "60d",  "60d")
m1  = fetch_intra("1m",  "1m",  "7d",   "7d")    # Yahoo max 7d for 1m

# ── Assemble & generate ────────────────────────────────────────────

updated = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
data_js = json.dumps({
    "d": daily, "h1": h1, "m30": m30, "m15": m15, "m5": m5, "m1": m1,
    "ugro_end": ugro_end, "updated": updated,
}, separators=(",", ":"))

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>UGRO → FLZH 技术分析</title>
<script src="https://cdn.bootcdn.net/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#0d1117;color:#e6edf3;height:100vh;display:flex;flex-direction:column;overflow:hidden}
.hdr{padding:8px 14px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:10px;flex-wrap:wrap;flex-shrink:0}
.hdr h1{font-size:15px;font-weight:600}
.badge{background:#1f6feb;color:#fff;font-size:10px;padding:2px 7px;border-radius:10px}
.upd{font-size:11px;color:#8b949e;margin-left:auto}
.leg{display:flex;gap:10px;font-size:11px;color:#8b949e;align-items:center}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:3px}
.row{display:flex;align-items:center;gap:5px;padding:5px 14px;border-bottom:1px solid #21262d;flex-wrap:wrap;flex-shrink:0}
.btn{padding:3px 11px;border:1px solid #30363d;background:#161b22;color:#8b949e;border-radius:5px;cursor:pointer;font-size:12px;transition:all .12s;white-space:nowrap}
.btn:hover,.btn.on{background:#1f6feb;border-color:#1f6feb;color:#fff}
.sep{width:1px;height:16px;background:#30363d;margin:0 2px;flex-shrink:0}
#chart-wrap{position:relative;flex:1;min-height:0}
#chart{width:100%;height:100%}
.pol{position:absolute;left:76px;font-size:11px;pointer-events:none;line-height:1.4;padding-top:2px;white-space:nowrap}
</style>
</head>
<body>
<div class="hdr">
  <h1>UGRO → FLZH 技术分析 <span class="badge">数据合并</span></h1>
  <span class="leg">
    <span><span class="dot" style="background:#58a6ff"></span>UGRO</span>
    <span><span class="dot" style="background:#3fb950"></span>FLZH</span>
  </span>
  <span class="upd" id="updLabel"></span>
</div>

<!-- Row 1: timeframe | chart type | indicators -->
<div class="row" id="row1">
  <button class="btn" id="tf_m1"  onclick="switchTF('m1')">1分</button>
  <button class="btn" id="tf_m5"  onclick="switchTF('m5')">5分</button>
  <button class="btn" id="tf_m15" onclick="switchTF('m15')">15分</button>
  <button class="btn" id="tf_m30" onclick="switchTF('m30')">30分</button>
  <button class="btn" id="tf_h1"  onclick="switchTF('h1')">1时</button>
  <button class="btn on" id="tf_d" onclick="switchTF('d')">日</button>
  <button class="btn" id="tf_w"   onclick="switchTF('w')">周</button>
  <button class="btn" id="tf_mo"  onclick="switchTF('mo')">月</button>
  <button class="btn" id="tf_y"   onclick="switchTF('y')">年</button>
  <div class="sep"></div>
  <button class="btn on" id="btnK" onclick="setType('candle')">K线</button>
  <button class="btn"    id="btnL" onclick="setType('line')">分时图</button>
  <div class="sep"></div>
  <button class="btn on" id="iMA"   onclick="toggleInd('MA')">均线</button>
  <button class="btn on" id="iMACD" onclick="toggleInd('MACD')">MACD</button>
  <button class="btn on" id="iKDJ"  onclick="toggleInd('KDJ')">KDJ</button>
  <button class="btn on" id="iOBV"  onclick="toggleInd('OBV')">OBV</button>
  <button class="btn on" id="iVOL"  onclick="toggleInd('VOL')">成交量</button>
</div>

<!-- Row 2: range buttons (dynamic) -->
<div class="row" id="rangeRow"></div>

<div id="chart-wrap"><div id="chart"></div></div>

<script>
// ── Embedded data ─────────────────────────────────────────────────
const DATA = $DATA_JS;
const UGRO_END = DATA.ugro_end;
document.getElementById('updLabel').textContent = '更新于 ' + DATA.updated;

// ── Timeframe config ──────────────────────────────────────────────
const TF_RANGES = {
  m1:  [{l:'1小时',n:60},{l:'4小时',n:240},{l:'1天',n:390},{l:'全部',n:0}],
  m5:  [{l:'4小时',n:48},{l:'1天',n:78},{l:'5天',n:390},{l:'1个月',n:1560},{l:'全部',n:0}],
  m15: [{l:'4小时',n:16},{l:'1天',n:26},{l:'5天',n:130},{l:'1个月',n:520},{l:'全部',n:0}],
  m30: [{l:'4小时',n:8}, {l:'1天',n:13},{l:'5天',n:65}, {l:'1个月',n:260},{l:'全部',n:0}],
  h1:  [{l:'1天',n:7},   {l:'1周',n:35},{l:'1月',n:150},{l:'3月',n:450}, {l:'全部',n:0}],
  d:   [{l:'1月',n:21},  {l:'3月',n:63},{l:'6月',n:126},{l:'1年',n:252}, {l:'2年',n:504},{l:'5年',n:1260},{l:'全部',n:0}],
  w:   [{l:'3月',n:13},  {l:'6月',n:26},{l:'1年',n:52}, {l:'2年',n:104}, {l:'5年',n:260},{l:'全部',n:0}],
  mo:  [{l:'6月',n:6},   {l:'1年',n:12},{l:'2年',n:24}, {l:'5年',n:60},  {l:'全部',n:0}],
  y:   [{l:'全部',n:0}],
};
const TF_DEFAULT_RANGE = {m1:390, m5:390, m15:130, m30:65, h1:150, d:252, w:52, mo:24, y:0};

// ── State ─────────────────────────────────────────────────────────
let activeTF = 'd', activeRange = TF_DEFAULT_RANGE.d;
let chartType = 'candle';
let show = {MA:true, MACD:true, KDJ:true, OBV:true, VOL:true};

// ── Aggregation ───────────────────────────────────────────────────
function weekStart(s) {
  const d = new Date(s + 'T12:00:00Z'), day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 1 - day);
  return d.toISOString().slice(0,10);
}
function aggregate(data, by) {
  const fn = {week:r=>weekStart(r.date), month:r=>r.date.slice(0,7), year:r=>r.date.slice(0,4)}[by];
  const groups = {}, order = [];
  data.forEach(r => { const k=fn(r); if(!groups[k]){groups[k]=[];order.push(k);} groups[k].push(r); });
  return order.map(k => {
    const g = groups[k];
    return {date:k, open:g[0].open, high:Math.max(...g.map(r=>r.high)),
            low:Math.min(...g.map(r=>r.low)), close:g[g.length-1].close,
            volume:g.reduce((s,r)=>s+r.volume,0)};
  });
}

// ── Data cache ────────────────────────────────────────────────────
const tfData = {m1:DATA.m1, m5:DATA.m5, m15:DATA.m15, m30:DATA.m30, h1:DATA.h1, d:DATA.d};
function getDataForTF(tf) {
  if (tfData[tf]) return tfData[tf];
  if (tf==='w')  return tfData.w  = aggregate(DATA.d,'week');
  if (tf==='mo') return tfData.mo = aggregate(DATA.d,'month');
  if (tf==='y')  return tfData.y  = aggregate(DATA.d,'year');
  return [];
}

// ── Indicators ────────────────────────────────────────────────────
function sma(arr, n) {
  return arr.map((_,i) => {
    if (i<n-1) return null;
    let s=0; for(let j=i-n+1;j<=i;j++) s+=arr[j];
    return +(s/n).toFixed(4);
  });
}
function ema(arr, n) {
  const k=2/(n+1); let prev=null; const out=[];
  arr.forEach(v => {
    if (v==null){out.push(null);return;}
    prev = prev==null ? v : v*k+prev*(1-k);
    out.push(+prev.toFixed(4));
  });
  return out;
}
function calcMACD(closes) {
  const e12=ema(closes,12), e26=ema(closes,26);
  const dif=closes.map((_,i)=>e12[i]!=null&&e26[i]!=null?+(e12[i]-e26[i]).toFixed(4):null);
  const dea=ema(dif,9).map(v=>v!=null?+v.toFixed(4):null);
  const bar=dif.map((v,i)=>v!=null&&dea[i]!=null?+(2*(v-dea[i])).toFixed(4):null);
  return {dif,dea,bar};
}
function calcKDJ(data, n=9) {
  let pk=50, pd=50; const K=[],D=[],J=[];
  data.forEach((_,i) => {
    const sl=data.slice(Math.max(0,i-n+1),i+1);
    const lo=Math.min(...sl.map(r=>r.low)), hi=Math.max(...sl.map(r=>r.high));
    const rsv=hi===lo?50:(data[i].close-lo)/(hi-lo)*100;
    const k=+(2/3*pk+1/3*rsv).toFixed(4);
    const d=+(2/3*pd+1/3*k).toFixed(4);
    K.push(k); D.push(d); J.push(+(3*k-2*d).toFixed(4));
    pk=k; pd=d;
  });
  return {K,D,J};
}
function calcOBV(data) {
  let v=0;
  return data.map((r,i) => {
    if(i===0){v=r.volume;return v;}
    if(r.close>data[i-1].close) v+=r.volume;
    else if(r.close<data[i-1].close) v-=r.volume;
    return v;
  });
}
const indCache = {};
function getIndicators(tf) {
  if (indCache[tf]) return indCache[tf];
  const data=getDataForTF(tf), closes=data.map(r=>r.close);
  return indCache[tf] = {
    MA5:sma(closes,5), MA10:sma(closes,10), MA30:sma(closes,30),
    MA60:sma(closes,60), MA120:sma(closes,120),
    ...calcMACD(closes), ...calcKDJ(data), OBV:calcOBV(data),
  };
}

// ── Chart ─────────────────────────────────────────────────────────
const chart = echarts.init(document.getElementById('chart'),null,{renderer:'canvas'});
window.addEventListener('resize', ()=>chart.resize());

function isUGRO(date) { return date.slice(0,10) <= UGRO_END; }

function fmtVol(v) {
  const a=Math.abs(v);
  if(a>=1e9) return (v/1e9).toFixed(1)+'B';
  if(a>=1e6) return (v/1e6).toFixed(1)+'M';
  if(a>=1e3) return (v/1e3).toFixed(0)+'K';
  return v.toFixed(0);
}

// Module-level state shared between buildOption and event handlers
let curD=[], curS=0, curInd={}, panelTops={};

function buildOption() {
  const data = getDataForTF(activeTF);
  const ind  = getIndicators(activeTF);
  const n    = data.length;
  const s    = activeRange===0 ? 0 : Math.max(0, n-activeRange);
  const d    = data.slice(s);
  const sl   = arr => arr.slice(s);

  const dates   = d.map(r=>r.date);
  const candles = d.map(r=>[r.open,r.close,r.low,r.high]);
  const closes  = d.map(r=>r.close);
  const vols    = d.map(r=>r.volume);

  // Sliced indicators
  const ma5=sl(ind.MA5), ma10=sl(ind.MA10), ma30=sl(ind.MA30),
        ma60=sl(ind.MA60), ma120=sl(ind.MA120),
        dif=sl(ind.dif), dea=sl(ind.dea), macdB=sl(ind.bar),
        K=sl(ind.K), Dl=sl(ind.D), J=sl(ind.J), obv=sl(ind.OBV);

  // Grid layout
  const grids=[],xAxes=[],yAxes=[],series=[];
  let top=6, gi=0;
  const subH=12;
  const panels=[show.VOL,show.MACD,show.KDJ,show.OBV].filter(Boolean).length;
  const mainH=Math.max(87-top-panels*(subH+1.5),25);

  panelTops = {};
  const addGrid=(h,label,role)=>{
    if(role) panelTops[role]=top;
    grids.push({left:72,right:12,top:`${top}%`,height:`${h}%`});
    xAxes.push({type:'category',data:dates,gridIndex:gi,
      axisLabel:{color:'#8b949e',fontSize:10,hideOverlap:true,show:false},
      axisLine:{lineStyle:{color:'#30363d'}},
      splitLine:{lineStyle:{color:'#21262d',type:'dashed'}},
      axisPointer:{label:{show:false}}});
    yAxes.push({scale:true,gridIndex:gi,
      axisLabel:{color:'#8b949e',fontSize:10},
      splitLine:{lineStyle:{color:'#21262d',type:'dashed'}},
      name:'',nameTextStyle:{color:'#8b949e',fontSize:9},nameLocation:'start'});
    top+=h+1.5; return gi++;
  };

  const mGi=addGrid(mainH,'','main');
  let vGi=-1,mcGi=-1,kGi=-1,oGi=-1;
  if(show.VOL)  vGi =addGrid(subH,'成交量','vol');
  if(show.MACD) mcGi=addGrid(subH,'MACD',  'macd');
  if(show.KDJ)  kGi =addGrid(subH,'KDJ(9)','kdj');
  if(show.OBV)  oGi =addGrid(subH,'OBV',   'obv');

  // Expose current slice for overlay updates
  curD=d; curS=s; curInd=ind;

  if(vGi>=0)  yAxes[vGi].axisLabel  = {color:'#8b949e',fontSize:10,formatter:fmtVol};
  if(oGi>=0)  yAxes[oGi].axisLabel  = {color:'#8b949e',fontSize:10,formatter:fmtVol};

  xAxes[xAxes.length-1].axisLabel.show=true;
  const allGi=[...Array(gi).keys()];

  // Main candle/line
  if(chartType==='candle') {
    series.push({type:'candlestick',data:candles,xAxisIndex:mGi,yAxisIndex:mGi,
      itemStyle:{color:'#f85149',color0:'#3fb950',borderColor:'#f85149',borderColor0:'#3fb950'}});
  } else {
    series.push({type:'line',data:closes,xAxisIndex:mGi,yAxisIndex:mGi,showSymbol:false,
      lineStyle:{width:1.5,color:'#58a6ff'},
      areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,
        colorStops:[{offset:0,color:'rgba(88,166,255,0.15)'},{offset:1,color:'rgba(88,166,255,0)'}]}}});
  }

  // MA lines
  if(show.MA) {
    [[ma5,'#f0e040','MA5'],[ma10,'#ff9900','MA10'],[ma30,'#e040fb','MA30'],
     [ma60,'#00bcd4','MA60'],[ma120,'#ff6b6b','MA120']].forEach(([dat,clr,nm])=>{
      series.push({type:'line',data:dat,xAxisIndex:mGi,yAxisIndex:mGi,
        showSymbol:false,lineStyle:{width:1,color:clr},name:nm,emphasis:{disabled:true}});
    });
  }

  // Volume
  if(show.VOL) series.push({type:'bar',xAxisIndex:vGi,yAxisIndex:vGi,name:'成交量',
    data:vols.map((v,i)=>({value:v,itemStyle:{color:
      candles[i]&&candles[i][1]>=candles[i][0]?'rgba(248,81,73,0.55)':'rgba(63,185,80,0.55)'}}))});

  // MACD
  if(show.MACD) {
    series.push({type:'bar',xAxisIndex:mcGi,yAxisIndex:mcGi,name:'MACD',
      data:macdB.map(v=>({value:v,itemStyle:{color:v>=0?'rgba(248,81,73,0.8)':'rgba(63,185,80,0.8)'}}))});
    series.push({type:'line',data:dif,xAxisIndex:mcGi,yAxisIndex:mcGi,showSymbol:false,lineStyle:{width:1,color:'#58a6ff'},name:'DIF'});
    series.push({type:'line',data:dea,xAxisIndex:mcGi,yAxisIndex:mcGi,showSymbol:false,lineStyle:{width:1,color:'#f0e040'},name:'DEA'});
  }

  // KDJ
  if(show.KDJ) {
    [[K,'#f0e040','K'],[Dl,'#58a6ff','D'],[J,'#ff6b6b','J']].forEach(([dat,clr,nm])=>{
      series.push({type:'line',data:dat,xAxisIndex:kGi,yAxisIndex:kGi,showSymbol:false,lineStyle:{width:1,color:clr},name:nm});
    });
  }

  // OBV
  if(show.OBV) series.push({type:'line',data:obv,xAxisIndex:oGi,yAxisIndex:oGi,showSymbol:false,
    lineStyle:{width:1,color:'#3fb950'},areaStyle:{color:'rgba(63,185,80,0.08)'},name:'OBV'});

  return {
    backgroundColor:'#0d1117', animation:false,
    tooltip:{
      trigger:'axis',
      axisPointer:{type:'cross',link:{xAxisIndex:'all'}},
      backgroundColor:'#161b22',borderColor:'#30363d',
      textStyle:{color:'#e6edf3',fontSize:11},
      formatter(params) {
        if(!params.length) return '';
        const i=params[0].dataIndex;
        const row=curD[i]; if(!row) return '';
        const dd=row.date;
        const tk=isUGRO(dd)?'UGRO':'FLZH', tc=isUGRO(dd)?'#58a6ff':'#3fb950';
        const prevClose=i>0?curD[i-1].close:row.open;
        const chg=((row.close-prevClose)/prevClose*100).toFixed(2);
        const cc=row.close>=prevClose?'#f85149':'#3fb950';
        let html=`<b style="color:${tc}">${tk}</b> ${dd}<br/>`;
        if(chartType==='candle')
          html+=`开:<b>${row.open}</b> 高:<b>${row.high}</b> 低:<b>${row.low}</b> 收:<b>${row.close}</b><br/>`;
        else
          html+=`收:<b>${row.close}</b><br/>`;
        html+=`昨收:<b>${prevClose}</b> 涨跌幅:<b style="color:${cc}">${chg}%</b>`;
        return html;
      }
    },
    axisPointer:{link:[{xAxisIndex:'all'}]},
    grid:grids, xAxis:xAxes, yAxis:yAxes,
    dataZoom:[
      {type:'inside',xAxisIndex:allGi},
      {type:'slider',xAxisIndex:allGi,bottom:2,height:20,
        borderColor:'#30363d',backgroundColor:'#161b22',
        fillerColor:'rgba(31,111,235,0.15)',
        handleStyle:{color:'#1f6feb'},textStyle:{color:'#8b949e',fontSize:10}}
    ],
    series
  };
}

function createOverlays() {
  const wrap = document.getElementById('chart-wrap');
  wrap.querySelectorAll('.pol').forEach(el=>el.remove());
  Object.entries(panelTops).forEach(([role, topPct])=>{
    const div=document.createElement('div');
    div.className='pol'; div.id='pol-'+role;
    div.style.top=topPct+'%';
    wrap.appendChild(div);
  });
}

function updateOverlayContent(i) {
  if(i<0||i>=curD.length) return;
  const row=curD[i], si=curS+i;

  const mel=document.getElementById('pol-main');
  if(mel) {
    const MA_DEF=[['MA5','#f0e040'],['MA10','#ff9900'],['MA30','#e040fb'],['MA60','#00bcd4'],['MA120','#ff6b6b']];
    mel.innerHTML = show.MA
      ? MA_DEF.map(([nm,clr])=>{
          const v=curInd[nm]?.[si];
          return `<span style="color:${clr};margin-right:10px">${nm}:${v!=null?v:'—'}</span>`;
        }).join('')
      : '';
  }

  const vel=document.getElementById('pol-vol');
  if(vel) {
    const cc=row.close>=row.open?'rgba(248,81,73,0.9)':'rgba(63,185,80,0.9)';
    vel.innerHTML=`<span style="color:#8b949e;margin-right:6px">成交量</span><span style="color:${cc}">${fmtVol(row.volume)}</span>`;
  }

  const mcel=document.getElementById('pol-macd');
  if(mcel) {
    const bar=curInd.bar?.[si], dif=curInd.dif?.[si], dea=curInd.dea?.[si];
    const bc=bar!=null&&bar>=0?'#f85149':'#3fb950';
    mcel.innerHTML=
      `<span style="color:${bc};margin-right:10px">MACD:${bar!=null?bar:'—'}</span>`+
      `<span style="color:#58a6ff;margin-right:10px">DIF:${dif!=null?dif:'—'}</span>`+
      `<span style="color:#f0e040">DEA:${dea!=null?dea:'—'}</span>`;
  }

  const kdel=document.getElementById('pol-kdj');
  if(kdel) {
    const K=curInd.K?.[si], D=curInd.D?.[si], J=curInd.J?.[si];
    kdel.innerHTML=
      `<span style="color:#f0e040;margin-right:10px">K:${K!=null?K:'—'}</span>`+
      `<span style="color:#58a6ff;margin-right:10px">D:${D!=null?D:'—'}</span>`+
      `<span style="color:#ff6b6b">J:${J!=null?J:'—'}</span>`;
  }

  const oel=document.getElementById('pol-obv');
  if(oel) {
    const v=curInd.OBV?.[si];
    oel.innerHTML=`<span style="color:#8b949e;margin-right:4px">OBV:</span><span style="color:#3fb950">${v!=null?fmtVol(v):'—'}</span>`;
  }
}

chart.on('updateAxisPointer', function(event) {
  const xInfo=event.axesInfo&&event.axesInfo.find(a=>a.axisDim==='x');
  if(xInfo) updateOverlayContent(xInfo.value);
});

function redraw() {
  chart.setOption(buildOption(),{replaceMerge:['series','grid','xAxis','yAxis','dataZoom']});
  createOverlays();
  // Show last bar's values by default
  if(curD.length) updateOverlayContent(curD.length-1);
}

// ── Controls ──────────────────────────────────────────────────────
function renderRangeButtons() {
  const ranges = TF_RANGES[activeTF] || TF_RANGES.d;
  const data = getDataForTF(activeTF);
  const isIntra = ['m1','m5','m15','m30','h1'].includes(activeTF);
  let warn = '';
  if (isIntra && data.length < 20) {
    const days = data.length > 0 ? data[0].date.slice(0,10) : '—';
    warn = `<span style="color:#e3b341;font-size:11px;margin-left:8px">⚠ FLZH 上市时间较短，日内数据仅从 ${days} 起，将随时间累积</span>`;
  }
  document.getElementById('rangeRow').innerHTML =
    ranges.map(r =>
      `<button class="btn${activeRange===r.n?' on':''}" onclick="setRange(${r.n})">${r.l}</button>`
    ).join('') + warn;
}

function setRange(n) {
  activeRange=n;
  document.querySelectorAll('#rangeRow .btn').forEach(b=>b.classList.remove('on'));
  event.target.classList.add('on');
  redraw();
}

function switchTF(tf) {
  activeTF=tf; activeRange=TF_DEFAULT_RANGE[tf]??0;
  document.querySelectorAll('#row1 .btn[id^="tf_"]').forEach(b=>b.classList.remove('on'));
  document.getElementById('tf_'+tf).classList.add('on');
  renderRangeButtons();
  redraw();
}

function setType(t) {
  chartType=t;
  document.getElementById('btnK').classList.toggle('on',t==='candle');
  document.getElementById('btnL').classList.toggle('on',t==='line');
  if(t==='line') {
    show.MA=false;
    document.getElementById('iMA').classList.remove('on');
    switchTF('m1');
  } else {
    show.MA=true;
    document.getElementById('iMA').classList.add('on');
    redraw();
  }
}

function toggleInd(ind) {
  show[ind]=!show[ind];
  document.getElementById('i'+ind).classList.toggle('on',show[ind]);
  redraw();
}

// ── Init ──────────────────────────────────────────────────────────
renderRangeButtons();
redraw();
</script>
</body>
</html>"""

html = TEMPLATE.replace("$DATA_JS", data_js)  # no brace-escaping needed

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"Written index.html ({len(html)//1024} KB)")
