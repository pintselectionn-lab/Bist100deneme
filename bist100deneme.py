import time
import math
import io
import base64
import wave
from datetime import datetime

import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# -----------------------------
# SAYFA AYARLARI
# -----------------------------
st.set_page_config(page_title="BIST100", layout="wide", page_icon="📈")

st.markdown("""
<style>
    .stMetric { background-color: #131722; padding: 10px; border-radius: 5px; border: 1px solid #2a2e39; color: white; }
    .stDataFrame { font-size: 14px; }
    .js-plotly-plot .plotly .main-svg { background-color: rgba(0,0,0,0) !important; }
    div[data-testid="stColumn"] { text-align: center; }

    /* PİYASA KARTLARI */
    .market-card {
        background-color: #131722;
        padding: 12px;
        border-radius: 6px;
        margin-bottom: 8px;
        border-left: 4px solid #2962FF;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .market-label { font-size: 11px; color: #787b86; text-transform: uppercase; letter-spacing: 1px;}
    .market-value { font-size: 16px; font-weight: bold; color: #d1d4dc; margin-top: 4px;}
    .market-delta { font-size: 12px; margin-top: 2px; font-weight: 600;}
    .market-stale { font-size: 11px; color: #787b86; margin-top: 6px; }

    .up { color: #00C853; }
    .down { color: #FF3D00; }

    .gold-border { border-left-color: #FFD700 !important; }
    .silver-border { border-left-color: #C0C0C0 !important; }

    .pill {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 12px;
        border: 1px solid #2a2e39;
        background: #0f172a;
        color: #d1d4dc;
        margin-right: 6px;
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 BIST100")
st.caption("Manuel tarama + alarm. Otomatik sayfa yenileme KAPALI.")

# -----------------------------
# YARDIMCILAR
# -----------------------------
def safe_download(tickers, period, interval=None, group_by="column", tries=2):
    """yfinance bazen boş/kısmi döner. Basit retry + boş kontrol."""
    last_err = None
    for _ in range(tries):
        try:
            df = yf.download(
                tickers=tickers,
                period=period,
                interval=interval,
                group_by=group_by,
                threads=True,
                progress=False,
            )
            if df is not None and not df.empty:
                return df
        except Exception as e:
            last_err = e
        time.sleep(0.25)
    return None

def _write_wav_mono(samples, sr=22050):
    """samples: [-1,1] float list -> mono 16-bit WAV bytes"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        for s in samples:
            s = max(-1.0, min(1.0, float(s)))
            val = int(s * 32767)
            wf.writeframesraw(val.to_bytes(2, byteorder="little", signed=True))
    return buf.getvalue()

def make_alarm_wav(kind="8-bit", sr=22050, volume=0.35):
    """
    kind: "8-bit" | "Çan"
    8-bit: square wave chiptune arpeggio
    Çan : decaying sine + harmonics (bell-like)
    """
    samples = []

    def square(freq, dur, vol=1.0):
        n = int(dur * sr)
        for i in range(n):
            t = i / sr
            v = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
            samples.append(v * vol)

    def bell(freq, dur, vol=1.0):
        n = int(dur * sr)
        for i in range(n):
            t = i / sr
            # exponential decay
            env = math.exp(-4.5 * t / max(dur, 1e-6))
            # fundamentals + harmonics
            s = (
                math.sin(2 * math.pi * freq * t) * 1.0 +
                math.sin(2 * math.pi * (freq * 2.01) * t) * 0.35 +
                math.sin(2 * math.pi * (freq * 3.12) * t) * 0.22 +
                math.sin(2 * math.pi * (freq * 4.23) * t) * 0.12
            )
            samples.append(s * env * vol)

    def silence(dur):
        n = int(dur * sr)
        samples.extend([0.0] * n)

    if kind == "8-bit":
        # kısa, net, retro alarm
        seq = [
            (988, 0.08),  # B5
            (1175, 0.08), # D6
            (1480, 0.10), # F#6
            (1175, 0.08),
            (988, 0.12),
        ]
        for f, d in seq:
            square(f, d, vol=1.0)
            silence(0.02)
    else:
        # çan gibi: tek vuruş + küçük tekrar
        bell(880, 0.35, vol=1.0)
        silence(0.06)
        bell(1320, 0.18, vol=0.7)

    # normalize + volume
    peak = max(0.001, max(abs(x) for x in samples))
    samples = [(x / peak) * volume for x in samples]
    return _write_wav_mono(samples, sr=sr)

def play_alarm(kind):
    wav = make_alarm_wav(kind=kind)
    b64 = base64.b64encode(wav).decode("utf-8")
    st.markdown(
        f"""
        <audio autoplay>
            <source src="data:audio/wav;base64,{b64}" type="audio/wav">
        </audio>
        """,
        unsafe_allow_html=True,
    )

# -----------------------------
# SIDEBAR: PİYASA ÖZETİ (MANUEL)
# -----------------------------
st.sidebar.header("📊 Piyasa Özeti")

if "market_cache_bust" not in st.session_state:
    st.session_state["market_cache_bust"] = 0
if "last_market" not in st.session_state:
    st.session_state["last_market"] = None
if "last_market_ts" not in st.session_state:
    st.session_state["last_market_ts"] = None

@st.cache_data(ttl=90)
def fetch_market(cache_bust: int):
    symbols = ["XU100.IS", "TRY=X", "EURTRY=X", "GC=F", "SI=F"]
    df = safe_download(symbols, period="2d", interval=None, group_by="column", tries=2)
    if df is None or df.empty:
        return None

    if not isinstance(df.columns, pd.MultiIndex):
        return None

    close = df["Close"].copy()

    def get_last_prev(ticker):
        if ticker not in close.columns:
            return None, None
        ser = close[ticker].dropna()
        if len(ser) < 2:
            return None, None
        return float(ser.iloc[-1]), float(ser.iloc[-2])

    out = {}

    last, prev = get_last_prev("XU100.IS")
    if last is not None:
        out["BIST 100"] = (last, (last / prev - 1) * 100)

    last, prev = get_last_prev("TRY=X")
    if last is not None:
        out["USD/TRY"] = (last, (last / prev - 1) * 100)
        usd_now, usd_prev = last, prev
    else:
        usd_now, usd_prev = None, None

    last, prev = get_last_prev("EURTRY=X")
    if last is not None:
        out["EUR/TRY"] = (last, (last / prev - 1) * 100)

    # Gram hesap (USD/TRY varsa)
    if usd_now and usd_prev:
        def ons_to_gram(ons_last, ons_prev):
            val_now = (ons_last * usd_now) / 31.1035
            val_prev = (ons_prev * usd_prev) / 31.1035
            return val_now, (val_now / val_prev - 1) * 100

        g_last, g_prev = get_last_prev("GC=F")
        if g_last is not None:
            val, chg = ons_to_gram(g_last, g_prev)
            out["Gram Altın"] = (val, chg)

        s_last, s_prev = get_last_prev("SI=F")
        if s_last is not None:
            val, chg = ons_to_gram(s_last, s_prev)
            out["Gram Gümüş"] = (val, chg)

    return out

colm1, colm2 = st.sidebar.columns([1,1])
with colm1:
    if st.button("🔄 Güncelle", use_container_width=True):
        st.session_state["market_cache_bust"] += 1
with colm2:
    st.caption("Oto-yenileme yok.")

market = fetch_market(st.session_state["market_cache_bust"])
ts_now = datetime.now().strftime("%H:%M:%S")

stale = False
if market:
    st.session_state["last_market"] = market
    st.session_state["last_market_ts"] = ts_now
else:
    market = st.session_state["last_market"]
    stale = True

if market:
    order = ["BIST 100", "USD/TRY", "EUR/TRY", "Gram Altın", "Gram Gümüş"]
    for key in order:
        if key not in market:
            continue
        price, chg = market[key]
        up = chg >= 0
        renk = "up" if up else "down"
        icon = "▲" if up else "▼"
        extra = "gold-border" if "Altın" in key else ("silver-border" if "Gümüş" in key else "")
        stale_txt = ""
        if stale:
            stale_txt = f'<div class="market-stale">⏳ Son veri: {st.session_state["last_market_ts"] or "?"} (stale)</div>'
        st.sidebar.markdown(f"""
        <div class="market-card {extra}">
            <div class="market-label">{key}</div>
            <div class="market-value">{price:,.2f}</div>
            <div class="market-delta {renk}">{icon} %{abs(chg):.2f}</div>
            {stale_txt}
        </div>
        """, unsafe_allow_html=True)
else:
    st.sidebar.warning("Piyasa verisi alınamadı (yfinance).")

# -----------------------------
# SIDEBAR: TARAMA + ALARM AYARLARI
# -----------------------------
st.sidebar.divider()
st.sidebar.header("⚙️ Tarama Ayarları")

varsayilan_hisseler = [
    "AEFES.IS","AGHOL.IS","AHGAZ.IS","AKBNK.IS","AKCNS.IS","AKFGY.IS","AKFYE.IS","AKSA.IS","AKSEN.IS","ALARK.IS",
    "ALBRK.IS","ALFAS.IS","ARCLK.IS","ASELS.IS","ASGYO.IS","ASTOR.IS","BERA.IS","BIENY.IS","BIMAS.IS","BIOEN.IS",
    "BOBET.IS","BRSAN.IS","BRYAT.IS","BUCIM.IS","CANTE.IS","CCOLA.IS","CIMSA.IS","CWENE.IS","DOAS.IS","DOHOL.IS",
    "ECILC.IS","ECZYT.IS","EGEEN.IS","EKGYO.IS","ENERY.IS","ENJSA.IS","ENKAI.IS","EREGL.IS","EUPWR.IS","EUREN.IS",
    "FROTO.IS","GARAN.IS","GENIL.IS","GESAN.IS","GLYHO.IS","GUBRF.IS","GWIND.IS","HALKB.IS","HEKTS.IS","IMASM.IS",
    "IPEKE.IS","ISCTR.IS","ISDMR.IS","ISGYO.IS","ISMEN.IS","IZMDC.IS","KARSN.IS","KAYSE.IS","KCAER.IS","KCHOL.IS",
    "KLSER.IS","KONTR.IS","KONYA.IS","KOZAA.IS","KOZAL.IS","KRDMD.IS","KZBGY.IS","MAVI.IS","MGROS.IS","MIATK.IS",
    "ODAS.IS","OTKAR.IS","OYAKC.IS","PENTA.IS","PETKM.IS","PGSUS.IS","PSGYO.IS","QUAGR.IS","REEDR.IS","SAHOL.IS",
    "SASA.IS","SDTTR.IS","SISE.IS","SKBNK.IS","SMRTG.IS","SNGYO.IS","SOKM.IS","TABGD.IS","TAVHL.IS","TCELL.IS",
    "THYAO.IS","TKFEN.IS","TOASO.IS","TSKB.IS","TTKOM.IS","TTRAK.IS","TUKAS.IS","TUPRS.IS","ULKER.IS","VAKBN.IS",
    "VESBE.IS","VESTL.IS","YEOTK.IS","YKBNK.IS","YYLGD.IS","ZOREN.IS","ANSGR.IS"
]

secilen_hisseler = st.sidebar.multiselect("Hisseler", varsayilan_hisseler, default=varsayilan_hisseler)

mode = st.sidebar.selectbox("Vade Modu", ["Kısa Vade (1s)", "Orta Vade (1g)", "Klasik (Golden Cross)"])

rsi_alt = st.sidebar.slider("RSI Dip (<)", 20, 45, 32)
rsi_ust = st.sidebar.slider("RSI Tepe (>)", 55, 90, 70)
atr_mult = st.sidebar.slider("Stop-Loss (ATR x)", 1.0, 4.0, 2.0)

st.sidebar.divider()
st.sidebar.header("🚨 Alarm Ayarları")

alarm_golden = st.sidebar.checkbox("Golden Cross (SMA50/200)", value=True)
alarm_mini = st.sidebar.checkbox("Mini Cross (EMA20/EMA50)", value=True)
alarm_macd = st.sidebar.checkbox("MACD AL", value=True)

alarm_sound_kind = st.sidebar.selectbox("Alarm Sesi", ["8-bit", "Çan", "Kapalı"], index=0)
alarm_sound_on = (alarm_sound_kind != "Kapalı")

# alarm tekrarını engelle
if "alerted" not in st.session_state:
    st.session_state["alerted"] = set()
if "last_alarms" not in st.session_state:
    st.session_state["last_alarms"] = []

def timeframe_params(mode_name):
    if mode_name == "Kısa Vade (1s)":
        return {"period": "60d", "interval": "60m"}
    elif mode_name == "Orta Vade (1g)":
        return {"period": "1y", "interval": "1d"}
    else:
        return {"period": "2y", "interval": "1d"}

def bulk_download(hisseler, period, interval):
    return safe_download(hisseler, period=period, interval=interval, group_by="ticker", tries=2)

def extract_ticker_df(bulk_df, ticker):
    if bulk_df is None or bulk_df.empty:
        return None
    if isinstance(bulk_df.columns, pd.MultiIndex):
        if ticker in bulk_df.columns.get_level_values(0):
            out = bulk_df[ticker].copy()
            out.columns = [c if isinstance(c, str) else str(c) for c in out.columns]
            return out
    return None

def karar_ver(rsi, macd_al, skor):
    if rsi > rsi_ust:
        return "🔴 SAT"
    if skor >= 6:
        return "🚀 GÜÇLÜ AL"
    if skor >= 3 and macd_al:
        return "🟢 AL"
    if skor <= 0:
        return "⛔ UZAK DUR"
    return "🟡 İZLE"

def yapay_zeka_yorumu(rsi, macd_al, golden_cross, trend_guclu, mini_cross):
    yorum = []
    if rsi < rsi_alt:
        yorum.append(f"RSI dip ({rsi}).")
    elif rsi > rsi_ust:
        yorum.append(f"RSI tepe ({rsi}).")
    if macd_al:
        yorum.append("MACD pozitife döndü.")
    if trend_guclu:
        yorum.append("Trend güçlü.")
    else:
        yorum.append("Trend zayıf/yatay.")
    if mini_cross:
        yorum.append("Mini Cross!")
    if golden_cross:
        yorum.append("Golden Cross!")
    return " ".join(yorum)

def fire_alarm(hisse, kind, ts_key):
    """
    Aynı sinyal tekrar tekrar çalmasın diye anahtar basıyoruz.
    ts_key: bar zamanı / tarih gibi bir şey
    """
    key = f"{hisse}:{kind}:{ts_key}"
    if key in st.session_state["alerted"]:
        return
    st.session_state["alerted"].add(key)

    msg = f"🚨 {hisse} -> {kind}"
    st.session_state["last_alarms"] = ([msg] + st.session_state["last_alarms"])[:10]
    st.toast(msg)

    if alarm_sound_on:
        play_alarm(alarm_sound_kind)

def run_scan(hisse_listesi, mode_name):
    params = timeframe_params(mode_name)
    period, interval = params["period"], params["interval"]

    bulk = bulk_download(hisse_listesi, period=period, interval=interval)

    results = []
    bar = st.progress(0.0)
    status = st.empty()

    for i, symbol in enumerate(hisse_listesi):
        bar.progress((i + 1) / max(1, len(hisse_listesi)))
        status.caption(f"Analiz: {symbol}")

        df = extract_ticker_df(bulk, symbol)
        if df is None or df.empty:
            continue

        # Kısa vadede 60m -> yeterli bar yoksa atlama
        if len(df) < 80:
            continue

        # indikatörler
        df["RSI"] = ta.rsi(df["Close"], length=14)

        macd = ta.macd(df["Close"], fast=12, slow=26, signal=9)
        if macd is not None:
            df = pd.concat([df, macd], axis=1)

        df["ATR"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)

        # Golden Cross (klasik)
        df["SMA_50"] = ta.sma(df["Close"], length=50)
        df["SMA_200"] = ta.sma(df["Close"], length=200)

        # Mini Cross (kısa vade)
        df["EMA_20"] = ta.ema(df["Close"], length=20)
        df["EMA_50"] = ta.ema(df["Close"], length=50)

        # Trend gücü: ADX
        adx = ta.adx(df["High"], df["Low"], df["Close"], length=14)
        if adx is not None:
            df = pd.concat([df, adx], axis=1)

        df = df.dropna()
        if len(df) < 40:
            continue

        last = df.iloc[-1]
        prev = df.iloc[-2]

        fiyat = float(last["Close"])
        rsi = float(last["RSI"]) if not pd.isna(last["RSI"]) else 50.0

        atr_val = float(last["ATR"]) if not pd.isna(last["ATR"]) else 0.0
        stop_loss = (fiyat - atr_val * atr_mult) if atr_val > 0 else None

        sinyaller = []
        skor = 0

        # RSI
        if rsi < rsi_alt:
            sinyaller.append("🟢 RSI DİP")
            skor += 2
        elif rsi > rsi_ust:
            sinyaller.append("🔴 RSI TEPE")
            skor -= 2

        # MACD cross
        macd_al = False
        try:
            macd_line = [c for c in df.columns if str(c).startswith("MACD_")][0]
            signal_line = [c for c in df.columns if str(c).startswith("MACDs_")][0]
            if last[macd_line] > last[signal_line] and prev[macd_line] < prev[signal_line]:
                macd_al = True
                sinyaller.append("🚀 MACD AL")
                skor += 3
        except:
            pass

        # Golden Cross
        golden_cross = False
        if not pd.isna(last.get("SMA_50")) and not pd.isna(last.get("SMA_200")):
            if last["SMA_50"] > last["SMA_200"] and prev["SMA_50"] < prev["SMA_200"]:
                golden_cross = True
                sinyaller.append("⭐ GOLDEN CROSS")
                skor += 5

        # Mini Cross EMA20/50
        mini_cross = False
        if not pd.isna(last.get("EMA_20")) and not pd.isna(last.get("EMA_50")):
            if last["EMA_20"] > last["EMA_50"] and prev["EMA_20"] < prev["EMA_50"]:
                mini_cross = True
                sinyaller.append("⚡ MINI CROSS")
                skor += 3

        # ADX
        trend_guclu = False
        try:
            adx_col = [c for c in df.columns if str(c).startswith("ADX_")][0]
            adx_val = float(last[adx_col])
            if adx_val >= 25:
                trend_guclu = True
                sinyaller.append("💪 GÜÇLÜ TREND")
                skor += 1
            elif adx_val <= 18:
                sinyaller.append("💤 ZAYIF TREND")
        except:
            pass

        hisse = symbol.replace(".IS", "")

        # Alarmlar (Sadece yeni oluştuysa)
        ts_key = str(df.index[-1])  # bar zamanı
        if alarm_golden and golden_cross:
            fire_alarm(hisse, "GOLDEN CROSS (SMA50/200)", ts_key)
        if alarm_mini and mini_cross:
            fire_alarm(hisse, "MINI CROSS (EMA20/EMA50)", ts_key)
        if alarm_macd and macd_al:
            fire_alarm(hisse, "MACD AL", ts_key)

        karar = karar_ver(rsi, macd_al, skor)
        yorum = yapay_zeka_yorumu(round(rsi, 2), macd_al, golden_cross, trend_guclu, mini_cross)

        # listede her şeyi görmek istersen filtresiz ekle; şimdilik sinyal olanları öne alıyoruz
        if sinyaller or skor >= 3:
            results.append({
                "Hisse": hisse,
                "Fiyat": round(fiyat, 2),
                "RSI": round(rsi, 2),
                "Skor": int(skor),
                "Sinyaller": " + ".join(sinyaller) if sinyaller else "",
                "Analiz Notu": yorum,
                "Karar": karar,
                "Stop-Loss": (round(stop_loss, 2) if stop_loss is not None else "-")
            })

    bar.empty()
    status.empty()
    return pd.DataFrame(results), params

# -----------------------------
# ÜST BUTONLAR (MANUEL)
# -----------------------------
c1, c2 = st.columns([1, 4])
with c1:
    start = st.button("TARAMAYI BAŞLAT 🕵️‍♂️", type="primary", use_container_width=True)
with c2:
    st.info("Oto-yenileme kapalı. Tarama ve alarmlar sadece butona basınca çalışır.")

if "scan_df" not in st.session_state:
    st.session_state["scan_df"] = None
if "scan_params" not in st.session_state:
    st.session_state["scan_params"] = None

if start:
    with st.spinner("Analiz ediliyor..."):
        st.session_state["scan_df"], st.session_state["scan_params"] = run_scan(secilen_hisseler, mode)

# Alarm paneli
if st.session_state["last_alarms"]:
    with st.expander("🚨 Son Alarmlar", expanded=True):
        for a in st.session_state["last_alarms"]:
            st.write(a)

df_out = st.session_state["scan_df"]

# -----------------------------
# SONUÇ TABLOSU
# -----------------------------
if df_out is not None and not df_out.empty:
    df_final = df_out.sort_values(by="Skor", ascending=False)

    st.dataframe(
        df_final,
        column_order=("Hisse", "Fiyat", "RSI", "Skor", "Sinyaller", "Analiz Notu", "Karar", "Stop-Loss"),
        column_config={
            "Karar": st.column_config.TextColumn("📢 Karar", width="small"),
            "Skor": st.column_config.ProgressColumn("Güç", format="%d", min_value=-5, max_value=12),
            "Analiz Notu": st.column_config.TextColumn("🧠 Not", width="large"),
        },
        use_container_width=True,
        height=520
    )

    # -----------------------------
    # GRAFİK
    # -----------------------------
    st.divider()
    st.subheader("📊 Grafik")

    vade_map = {"5 Gün (1s)": ("5d", "60m"), "1 Ay": ("1mo", "1d"), "3 Ay": ("3mo", "1d"), "6 Ay": ("6mo", "1d"), "1 Yıl": ("1y", "1d")}
    col_sel, col_radio = st.columns([1, 2])

    with col_sel:
        selected = st.selectbox("İncelenecek Hisse:", df_final["Hisse"].unique())

    with col_radio:
        secilen_vade_ad = st.radio("Grafik Vadesi:", list(vade_map.keys()), horizontal=True, index=1)

    if selected:
        period_val, interval_val = vade_map[secilen_vade_ad]

        with st.spinner("Grafik yükleniyor..."):
            df_chart = safe_download([selected + ".IS"], period=period_val, interval=interval_val, group_by="column", tries=2)

            if df_chart is None or df_chart.empty:
                st.warning("Grafik verisi alınamadı (yfinance).")
            else:
                if isinstance(df_chart.columns, pd.MultiIndex):
                    df_chart = df_chart.droplevel(1, axis=1)

                fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                    vertical_spacing=0.05, row_heights=[0.75, 0.25])

                fig.add_trace(go.Candlestick(
                    x=df_chart.index,
                    open=df_chart["Open"], high=df_chart["High"],
                    low=df_chart["Low"], close=df_chart["Close"],
                    name=selected,
                    increasing_line_color="#26a69a",
                    increasing_fillcolor="#26a69a",
                    decreasing_line_color="#ef5350",
                    decreasing_fillcolor="#ef5350",
                    text=df_chart.index.strftime("%d.%m.%Y"),
                    hovertemplate="<b>T:</b> %{text}<br><b>A:</b> %{open:.2f}<br><b>Y:</b> %{high:.2f}<br><b>D:</b> %{low:.2f}<br><b>K:</b> %{close:.2f}<extra></extra>"
                ), row=1, col=1)

                colors = ["#26a69a" if c >= o else "#ef5350" for c, o in zip(df_chart["Close"], df_chart["Open"])]
                fig.add_trace(go.Bar(
                    x=df_chart.index, y=df_chart["Volume"],
                    name="Hacim", marker_color=colors, opacity=0.6
                ), row=2, col=1)

                # Stop çizgisi (tablodan)
                row_data = df_final[df_final["Hisse"] == selected].iloc[0]
                stop_level = row_data["Stop-Loss"]
                if stop_level != "-" and stop_level is not None:
                    try:
                        stop_level_f = float(stop_level)
                        fig.add_shape(
                            type="line",
                            x0=df_chart.index[0], x1=df_chart.index[-1],
                            y0=stop_level_f, y1=stop_level_f,
                            line=dict(color="orange", width=1.5, dash="dash"),
                            row=1, col=1
                        )
                    except:
                        pass

                fig.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="#131722", plot_bgcolor="#131722",
                    height=650, margin=dict(l=10, r=10, t=30, b=10),
                    hovermode="x unified", showlegend=False, dragmode="pan"
                )
                fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#2a2e39", rangeslider_visible=False)
                fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#2a2e39")

                st.plotly_chart(fig, use_container_width=True)

                # Risk kutuları
                try:
                    curr_price = float(row_data["Fiyat"])
                    if stop_level != "-" and stop_level is not None:
                        stop_level_f = float(stop_level)
                        risk_amount = max(0.0, curr_price - stop_level_f)
                        target_price = curr_price + (risk_amount * 3.0) if risk_amount > 0 else curr_price
                        profit_pct = ((target_price - curr_price) / curr_price) * 100 if curr_price else 0
                        loss_pct = ((curr_price - stop_level_f) / curr_price) * 100 if curr_price else 0

                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("🔵 FİYAT", f"{curr_price:.2f} TL")
                        c2.metric("🟢 HEDEF (1:3)", f"{target_price:.2f}", f"%{profit_pct:.1f}")
                        c3.metric("🔴 STOP (ATR)", f"{stop_level_f:.2f}", f"-%{loss_pct:.1f}")
                        c4.metric("💰 RİSK", f"{risk_amount:.2f} TL")
                except:
                    pass

else:
    st.warning("Henüz tarama yapılmadı veya sonuç üretilemedi. 'TARAMAYI BAŞLAT' ile başla.")
