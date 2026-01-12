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

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="BIST100", layout="wide", page_icon="📈")

# --- CSS ---
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
    .market-delta { font-size: 12px; margin-top: 2px; font-weight: 500;}
    .market-stale { font-size: 11px; color: #787b86; margin-top: 6px; }

    .up { color: #00C853; }
    .down { color: #FF3D00; }

    /* ÖZEL RENKLER */
    .gold-border { border-left-color: #FFD700 !important; }
    .silver-border { border-left-color: #C0C0C0 !important; }
</style>
""", unsafe_allow_html=True)

st.title("📈 BIST100")
st.markdown("Gelişmiş Teknik Analiz.")

# -----------------------------
# Yardımcılar
# -----------------------------
def safe_download(tickers, period, interval=None, group_by="column", tries=2):
    """
    yfinance bazen boş / kısmi döner. Basit retry + boş kontrol.
    """
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
        time.sleep(0.2)
    return None

def make_beep_wav(duration=0.18, freq=880, sr=22050, volume=0.35):
    n = int(duration * sr)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        for i in range(n):
            s = volume * math.sin(2 * math.pi * freq * (i / sr))
            val = int(max(-1.0, min(1.0, s)) * 32767)
            wf.writeframesraw(val.to_bytes(2, byteorder="little", signed=True))
    return buf.getvalue()

def play_beep():
    wav = make_beep_wav()
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
# Oto yenileme (harici paket olmadan)
# -----------------------------
st.sidebar.header("⏱️ Canlı Mod")
refresh_sec = st.sidebar.slider("Oto yenile (sn)", 0, 300, 20)
auto_scan = st.sidebar.checkbox("Oto tarama (yenilemede tarar)", value=False)

# Meta refresh (basit, stabil)
if refresh_sec > 0:
    st.markdown(f"<meta http-equiv='refresh' content='{refresh_sec}'>", unsafe_allow_html=True)

# -----------------------------
# Piyasa Özeti (cache + fallback)
# -----------------------------
@st.cache_data(ttl=60)
def piyasa_verilerini_cek_cached():
    semboller = ["XU100.IS", "TRY=X", "EURTRY=X", "GC=F", "SI=F"]
    df = safe_download(semboller, period="2d", interval=None, group_by="column", tries=2)
    if df is None or df.empty:
        return None

    # MultiIndex ise: df['Close'] -> (date x ticker)
    if isinstance(df.columns, pd.MultiIndex):
        close = df["Close"].copy()
    else:
        # tek-sembol gibi dönerse: Close kolonu var mı?
        if "Close" in df.columns:
            # Bu durumda tickers kolonu yok; tek seri gibi davran
            # Burada piyasa özeti için pratik çözüm: None dönüp fallback'e düşelim
            return None
        return None

    data = {}

    def get_close(ticker):
        if ticker not in close.columns:
            return None, None
        ser = close[ticker].dropna()
        if len(ser) < 2:
            return None, None
        return float(ser.iloc[-1]), float(ser.iloc[-2])

    # Temel
    last, prev = get_close("XU100.IS")
    if last is not None:
        data["BIST 100"] = (last, (last / prev - 1) * 100)

    last, prev = get_close("TRY=X")
    if last is not None:
        data["USD/TRY"] = (last, (last / prev - 1) * 100)

    last, prev = get_close("EURTRY=X")
    if last is not None:
        data["EUR/TRY"] = (last, (last / prev - 1) * 100)

    # Gram Altın/Gümüş (USD/TRY varsa)
    if "USD/TRY" in data:
        usd_now = data["USD/TRY"][0]
        usd_prev = get_close("TRY=X")[1]

        def ons_to_gram(ons_last, ons_prev):
            val_now = (ons_last * usd_now) / 31.1035
            val_prev = (ons_prev * usd_prev) / 31.1035
            return val_now, (val_now / val_prev - 1) * 100

        g_last, g_prev = get_close("GC=F")
        if g_last is not None:
            val, chg = ons_to_gram(g_last, g_prev)
            data["Gram Altın"] = (val, chg)

        s_last, s_prev = get_close("SI=F")
        if s_last is not None:
            val, chg = ons_to_gram(s_last, s_prev)
            data["Gram Gümüş"] = (val, chg)

    return data

# Sidebar: son iyi veriyi sakla
if "last_market" not in st.session_state:
    st.session_state["last_market"] = None
if "last_market_ts" not in st.session_state:
    st.session_state["last_market_ts"] = None

st.sidebar.divider()
st.sidebar.header("📊 Piyasa Özeti")

piyasa_data = piyasa_verilerini_cek_cached()
now_ts = datetime.now().strftime("%H:%M:%S")

if piyasa_data:
    st.session_state["last_market"] = piyasa_data
    st.session_state["last_market_ts"] = now_ts
    stale = False
else:
    piyasa_data = st.session_state["last_market"]
    stale = True

if piyasa_data:
    siralama = ["BIST 100", "USD/TRY", "EUR/TRY", "Gram Altın", "Gram Gümüş"]
    for key in siralama:
        if key in piyasa_data:
            fiyat, degisim = piyasa_data[key]
            renk = "up" if degisim >= 0 else "down"
            icon = "▲" if degisim >= 0 else "▼"

            extra_class = ""
            if "Altın" in key:
                extra_class = "gold-border"
            elif "Gümüş" in key:
                extra_class = "silver-border"

            stale_txt = ""
            if stale:
                stale_txt = f'<div class="market-stale">⏳ Son veri: {st.session_state["last_market_ts"] or "?"} (stale)</div>'

            st.sidebar.markdown(f"""
            <div class="market-card {extra_class}">
                <div class="market-label">{key}</div>
                <div class="market-value">{fiyat:,.2f}</div>
                <div class="market-delta {renk}">{icon} %{abs(degisim):.2f}</div>
                {stale_txt}
            </div>
            """, unsafe_allow_html=True)
else:
    st.sidebar.warning("Piyasa verisi alınamadı (yfinance).")

# -----------------------------
# Ayarlar
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

mode = st.sidebar.selectbox("Vade Modu", ["Kısa Vade (1s/1g)", "Orta Vade (1g)", "Klasik (Golden Cross)"])
rsi_alt = st.sidebar.slider("RSI Alım (<)", 20, 45, 32)
rsi_ust = st.sidebar.slider("RSI Satış (>)", 55, 90, 70)
atr_mult = st.sidebar.slider("Stop-Loss (ATR x)", 1.0, 4.0, 2.0)

st.sidebar.divider()
st.sidebar.header("🚨 Alarm Ayarları")
alarm_golden = st.sidebar.checkbox("Golden Cross (SMA50/200)", value=True)
alarm_mini = st.sidebar.checkbox("Mini Cross (EMA20/EMA50)", value=True)
alarm_macd = st.sidebar.checkbox("MACD AL", value=True)
alarm_sound = st.sidebar.checkbox("Sesli alarm", value=True)

# alarm belleği
if "alerted" not in st.session_state:
    st.session_state["alerted"] = set()
if "last_alarms" not in st.session_state:
    st.session_state["last_alarms"] = []

def karar_ver(rsi, macd_al, skor):
    if rsi > rsi_ust:
        return "🔴 SAT"
    elif skor >= 5:
        return "🚀 GÜÇLÜ AL"
    elif skor >= 2 and macd_al:
        return "🟢 AL"
    elif rsi < rsi_alt and not macd_al:
        return "👀 DİP (BEKLE)"
    elif skor <= 0:
        return "⛔ UZAK DUR"
    else:
        return "🟡 İZLE"

def yapay_zeka_yorumu(rsi, macd_al, golden_cross, trend_guclu, mini_cross, hisse_adi):
    yorumlar = []
    if rsi < rsi_alt: yorumlar.append(f"Aşırı ucuz (RSI:{rsi}).")
    elif rsi > rsi_ust: yorumlar.append(f"Aşırı şişkin (RSI:{rsi}).")
    if macd_al: yorumlar.append("Momentum pozitife döndü.")
    yorumlar.append("Güçlü trend var." if trend_guclu else "Piyasa yatay/zayıf.")
    if mini_cross: yorumlar.append("Mini Cross oluştu!")
    if golden_cross: yorumlar.append("Golden Cross oluştu!")
    return " ".join(yorumlar)

def timeframe_params(mode_name):
    # yfinance intraday limitlerini de düşünerek period/interval seçiyoruz
    if mode_name == "Kısa Vade (1s/1g)":
        return {"period": "60d", "interval": "60m"}  # 1 saatlik
    elif mode_name == "Orta Vade (1g)":
        return {"period": "1y", "interval": "1d"}
    else:
        return {"period": "2y", "interval": "1d"}

def bulk_download(hisseler, period, interval):
    df = safe_download(hisseler, period=period, interval=interval, group_by="ticker", tries=2)
    return df

def extract_ticker_df(bulk_df, ticker):
    # group_by="ticker" -> üstte ticker, altta OHLCV
    if bulk_df is None or bulk_df.empty:
        return None
    if isinstance(bulk_df.columns, pd.MultiIndex):
        if ticker in bulk_df.columns.get_level_values(0):
            out = bulk_df[ticker].copy()
            out.columns = [c if isinstance(c, str) else str(c) for c in out.columns]
            return out
    return None

def verileri_getir(hisse_listesi, mode_name):
    params = timeframe_params(mode_name)
    period = params["period"]
    interval = params["interval"]

    bulk = bulk_download(hisse_listesi, period=period, interval=interval)

    sonuclar = []
    bar = st.progress(0.0)
    status = st.empty()

    for i, symbol in enumerate(hisse_listesi):
        bar.progress((i + 1) / max(1, len(hisse_listesi)))
        status.caption(f"Analiz: {symbol}")

        df = extract_ticker_df(bulk, symbol)
        if df is None or df.empty or len(df) < 60:
            continue

        # indikatörler
        df["RSI"] = ta.rsi(df["Close"], length=14)
        macd = ta.macd(df["Close"], fast=12, slow=26, signal=9)
        if macd is not None:
            df = pd.concat([df, macd], axis=1)

        df["ATR"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)

        # Klasik golden cross (günlük mantık) – kısa vadede gecikmeli ama “önemli sinyal”
        df["SMA_50"] = ta.sma(df["Close"], length=50)
        df["SMA_200"] = ta.sma(df["Close"], length=200)

        # Kısa vade mini cross
        df["EMA_20"] = ta.ema(df["Close"], length=20)
        df["EMA_50"] = ta.ema(df["Close"], length=50)

        adx = ta.adx(df["High"], df["Low"], df["Close"], length=14)
        if adx is not None:
            df = pd.concat([df, adx], axis=1)

        df = df.dropna()
        if len(df) < 30:
            continue

        son = df.iloc[-1]
        onceki = df.iloc[-2]

        fiyat = round(float(son["Close"]), 2)
        rsi = round(float(son["RSI"]), 2) if not pd.isna(son["RSI"]) else 50.0
        atr_val = float(son["ATR"]) if not pd.isna(son["ATR"]) else 0.0
        stop_loss = round(fiyat - (atr_val * atr_mult), 2) if atr_val > 0 else None

        sinyaller_listesi = []
        skor = 0

        # RSI
        if rsi < rsi_alt:
            sinyaller_listesi.append("🟢 RSI DİP")
            skor += 2
        elif rsi > rsi_ust:
            sinyaller_listesi.append("🔴 RSI ZİRVE")
            skor -= 2

        # MACD AL
        macd_al = False
        try:
            macd_line = [c for c in df.columns if str(c).startswith("MACD_")][0]
            signal_line = [c for c in df.columns if str(c).startswith("MACDs_")][0]
            if son[macd_line] > son[signal_line] and onceki[macd_line] < onceki[signal_line]:
                macd_al = True
                sinyaller_listesi.append("🚀 MACD AL")
                skor += 3
        except:
            pass

        # Golden Cross
        golden_cross = False
        if not pd.isna(son.get("SMA_50")) and not pd.isna(son.get("SMA_200")):
            if son["SMA_50"] > son["SMA_200"] and onceki["SMA_50"] < onceki["SMA_200"]:
                golden_cross = True
                sinyaller_listesi.append("⭐ GOLDEN CROSS")
                skor += 5

        # Mini Cross (EMA20/50)
        mini_cross = False
        if not pd.isna(son.get("EMA_20")) and not pd.isna(son.get("EMA_50")):
            if son["EMA_20"] > son["EMA_50"] and onceki["EMA_20"] < onceki["EMA_50"]:
                mini_cross = True
                sinyaller_listesi.append("⚡ MINI CROSS")
                skor += 3

        # Trend gücü (ADX)
        trend_guclu = False
        try:
            adx_col = [c for c in df.columns if str(c).startswith("ADX_")][0]
            if float(son[adx_col]) > 25:
                trend_guclu = True
                sinyaller_listesi.append("💪 GÜÇLÜ TREND")
                skor += 1
            elif float(son[adx_col]) < 20:
                sinyaller_listesi.append("💤 ZAYIF TREND")
        except:
            pass

        hisse_adi = symbol.replace(".IS", "")
        karar = karar_ver(rsi, macd_al, skor)
        ai_yorum = yapay_zeka_yorumu(rsi, macd_al, golden_cross, trend_guclu, mini_cross, hisse_adi)

        # Alarm tetikleme (yeni oluştuysa)
        def fire_alarm(kind):
            key = f"{hisse_adi}:{kind}:{df.index[-1].date()}"
            if key not in st.session_state["alerted"]:
                st.session_state["alerted"].add(key)
                msg = f"🚨 {hisse_adi} -> {kind}"
                st.session_state["last_alarms"] = ([msg] + st.session_state["last_alarms"])[:8]
                st.toast(msg)
                if alarm_sound:
                    play_beep()

        if alarm_golden and golden_cross:
            fire_alarm("GOLDEN CROSS (SMA50/200)")
        if alarm_mini and mini_cross:
            fire_alarm("MINI CROSS (EMA20/50)")
        if alarm_macd and macd_al:
            fire_alarm("MACD AL")

        if len(sinyaller_listesi) > 0 or "ANSGR" in symbol:
            sonuclar.append({
                "Hisse": hisse_adi,
                "Fiyat": fiyat,
                "RSI": rsi,
                "Skor": skor,
                "Sinyaller": " + ".join(sinyaller_listesi),
                "AI Yorum": ai_yorum,
                "Karar": karar,
                "Stop-Loss": stop_loss if stop_loss is not None else "-"
            })

    bar.empty()
    status.empty()
    return pd.DataFrame(sonuclar), params

# -----------------------------
# Arayüz
# -----------------------------
col1, col2 = st.columns([1, 4])
with col1:
    start = st.button("TARAMAYI BAŞLAT 🕵️‍♂️", type="primary", use_container_width=True)
with col2:
    st.info("Piyasayı tarar, risk analizi yapar ve al/sat kararı üretir. (Alarm: yeni sinyal oluşunca)")

if "data" not in st.session_state:
    st.session_state["data"] = None
if "scan_params" not in st.session_state:
    st.session_state["scan_params"] = None

should_run = start or (auto_scan and refresh_sec > 0)

if should_run:
    with st.spinner("Analiz ediliyor..."):
        st.session_state["data"], st.session_state["scan_params"] = verileri_getir(secilen_hisseler, mode)

# Alarm paneli
if st.session_state["last_alarms"]:
    with st.expander("🚨 Son Alarmlar", expanded=True):
        for a in st.session_state["last_alarms"]:
            st.write(a)

df_out = st.session_state["data"]

if df_out is not None and not df_out.empty:
    df_final = df_out.sort_values(by="Skor", ascending=False)

    st.dataframe(
        df_final,
        column_order=("Hisse", "Fiyat", "RSI", "Skor", "Sinyaller", "AI Yorum", "Karar", "Stop-Loss"),
        column_config={
            "Karar": st.column_config.TextColumn("📢 Karar", width="small"),
            "Skor": st.column_config.ProgressColumn("Güç", format="%d", min_value=-5, max_value=12),
            "AI Yorum": st.column_config.TextColumn("🤖 Analiz Notu", width="large"),
        },
        use_container_width=True,
        height=520
    )

    st.divider()
    st.subheader("📊 Grafik")

    vade_map = {"1 Hafta": "5d", "1 Ay": "1mo", "3 Ay": "3mo", "6 Ay": "6mo", "1 Yıl": "1y"}
    col_sel, col_radio = st.columns([1, 2])
    with col_sel:
        selected = st.selectbox("İncelenecek Hisse:", df_final["Hisse"].unique())
    with col_radio:
        secilen_vade_ad = st.radio("Grafik Vadesi:", list(vade_map.keys()), horizontal=True, index=1)

    if selected:
        period_val = vade_map[secilen_vade_ad]
        interval_val = "60m" if period_val == "5d" else "1d"

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

                row_data = df_final[df_final["Hisse"] == selected].iloc[0]
                stop_level = row_data["Stop-Loss"]
                if stop_level != "-" and stop_level is not None:
                    fig.add_shape(
                        type="line",
                        x0=df_chart.index[0], x1=df_chart.index[-1],
                        y0=float(stop_level), y1=float(stop_level),
                        line=dict(color="orange", width=1.5, dash="dash"),
                        row=1, col=1
                    )

                fig.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="#131722", plot_bgcolor="#131722",
                    height=650, margin=dict(l=10, r=10, t=30, b=10),
                    hovermode="x unified", showlegend=False, dragmode="pan"
                )
                fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="#2a2e39", rangeslider_visible=False)
                fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#2a2e39")
                st.plotly_chart(fig, use_container_width=True)

                # Risk Masası
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
else:
    if st.session_state["data"] is not None:
        st.warning("Sonuç yok (seçilen vade/interval için veri gelmemiş olabilir).")
