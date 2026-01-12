import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import json

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="BIST100 PRO", layout="wide", page_icon="📈")

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
    
    .up { color: #00C853; }
    .down { color: #FF3D00; }
    
    /* ÖZEL RENKLER */
    .gold-border { border-left-color: #FFD700 !important; }
    .silver-border { border-left-color: #C0C0C0 !important; }
    
    /* PORTFÖY KARTI */
    .portfolio-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
        color: white;
        box-shadow: 0 8px 16px rgba(0,0,0,0.4);
    }
    
    .portfolio-title { font-size: 14px; opacity: 0.9; margin-bottom: 5px; }
    .portfolio-value { font-size: 28px; font-weight: bold; }
    .portfolio-change { font-size: 16px; margin-top: 8px; }
    
    /* UYARI KUTUSU */
    .alert-box {
        background-color: #1a1a2e;
        border-left: 4px solid #FF6B6B;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }
    
    /* BAŞARI MESAJI */
    .success-box {
        background-color: #1a1a2e;
        border-left: 4px solid #00C853;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

st.title("📈 BIST100 PRO TRADER")
st.markdown("**Gelişmiş Teknik Analiz | Portföy Yönetimi | Akıllı Sinyaller**")

# --- SESSION STATE BAŞLATMA ---
if 'portfolio' not in st.session_state:
    st.session_state['portfolio'] = {}
if 'data' not in st.session_state:
    st.session_state['data'] = None
if 'last_alerts' not in st.session_state:
    st.session_state['last_alerts'] = {}

# --- PİYASA VERİLERİ ---
@st.cache_data(ttl=300)
def piyasa_verilerini_cek():
    semboller = ["XU100.IS", "TRY=X", "EURTRY=X", "GC=F", "SI=F"]
    data = {}
    
    try:
        df = yf.download(semboller, period="2d", progress=False)
        
        if isinstance(df.columns, pd.MultiIndex):
            close = df['Close']
        else:
            close = df
            
        def get_data(ticker, label, is_calc_gram=False, usd_val=None, prev_usd=None):
            try:
                if ticker not in close.columns: 
                    return
                
                last = close[ticker].iloc[-1]
                prev = close[ticker].iloc[-2]
                
                if pd.isna(last) or pd.isna(prev): 
                    return
                
                if is_calc_gram and usd_val and prev_usd:
                    val_now = (last * usd_val) / 31.1035
                    val_prev = (prev * prev_usd) / 31.1035
                else:
                    val_now = last
                    val_prev = prev
                    
                degisim = (val_now / val_prev - 1) * 100
                data[label] = (val_now, degisim)
            except:
                pass

        get_data("XU100.IS", "BIST 100")
        get_data("TRY=X", "USD/TRY")
        get_data("EURTRY=X", "EUR/TRY")
        
        if "USD/TRY" in data:
            usd_now = data["USD/TRY"][0]
            usd_prev = close["TRY=X"].iloc[-2]
            
            get_data("GC=F", "Gram Altın", is_calc_gram=True, usd_val=usd_now, prev_usd=usd_prev)
            get_data("SI=F", "Gram Gümüş", is_calc_gram=True, usd_val=usd_now, prev_usd=usd_prev)
            
        return data
    except Exception as e:
        st.error(f"Piyasa verileri alınamadı: {str(e)}")
        return None

# --- PORTFÖY YÖNETİMİ ---
def portfoy_hesapla():
    """Portföy toplam değerini hesapla"""
    toplam_deger = 0
    toplam_maliyet = 0
    
    for hisse, bilgi in st.session_state['portfolio'].items():
        try:
            ticker = f"{hisse}.IS"
            df = yf.download(ticker, period="1d", progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            if not df.empty:
                guncel_fiyat = df['Close'].iloc[-1]
                adet = bilgi['adet']
                alis_fiyati = bilgi['alis_fiyati']
                
                toplam_deger += guncel_fiyat * adet
                toplam_maliyet += alis_fiyati * adet
        except:
            continue
    
    kar_zarar = toplam_deger - toplam_maliyet
    kar_zarar_pct = (kar_zarar / toplam_maliyet * 100) if toplam_maliyet > 0 else 0
    
    return toplam_deger, toplam_maliyet, kar_zarar, kar_zarar_pct

def portfoy_ekle(hisse, adet, alis_fiyati):
    """Portföye hisse ekle"""
    if hisse in st.session_state['portfolio']:
        mevcut = st.session_state['portfolio'][hisse]
        toplam_adet = mevcut['adet'] + adet
        ortalama_fiyat = ((mevcut['alis_fiyati'] * mevcut['adet']) + (alis_fiyati * adet)) / toplam_adet
        st.session_state['portfolio'][hisse] = {
            'adet': toplam_adet,
            'alis_fiyati': ortalama_fiyat,
            'tarih': datetime.now().strftime("%Y-%m-%d %H:%M")
        }
    else:
        st.session_state['portfolio'][hisse] = {
            'adet': adet,
            'alis_fiyati': alis_fiyati,
            'tarih': datetime.now().strftime("%Y-%m-%d %H:%M")
        }

# --- YAN PANEL ---
st.sidebar.header("📊 Piyasa Özeti")

piyasa_data = piyasa_verilerini_cek()

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
            
            st.sidebar.markdown(f"""
            <div class="market-card {extra_class}">
                <div class="market-label">{key}</div>
                <div class="market-value">{fiyat:,.2f}</div>
                <div class="market-delta {renk}">{icon} %{abs(degisim):.2f}</div>
            </div>
            """, unsafe_allow_html=True)
else:
    st.sidebar.warning("Veriler yükleniyor...")

st.sidebar.divider()

# --- PORTFÖY BÖLÜMÜ ---
st.sidebar.header("💼 Portföyüm")

if st.session_state['portfolio']:
    try:
        toplam_deger, toplam_maliyet, kar_zarar, kar_zarar_pct = portfoy_hesapla()
        
        st.sidebar.markdown(f"""
        <div class="portfolio-card">
            <div class="portfolio-title">TOPLAM PORTFÖY</div>
            <div class="portfolio-value">{toplam_deger:,.2f} ₺</div>
            <div class="portfolio-change {'up' if kar_zarar >= 0 else 'down'}">
                {'▲' if kar_zarar >= 0 else '▼'} {kar_zarar:,.2f} ₺ ({kar_zarar_pct:+.2f}%)
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        with st.sidebar.expander("📋 Portföy Detayları", expanded=False):
            for hisse, bilgi in st.session_state['portfolio'].items():
                try:
                    ticker = f"{hisse}.IS"
                    df = yf.download(ticker, period="1d", progress=False)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    
                    if not df.empty:
                        guncel = df['Close'].iloc[-1]
                        adet = bilgi['adet']
                        alis = bilgi['alis_fiyati']
                        kar = (guncel - alis) * adet
                        kar_pct = ((guncel - alis) / alis) * 100
                        
                        st.markdown(f"""
                        **{hisse}**  
                        🔵 {adet} adet × {guncel:.2f} ₺  
                        💰 K/Z: {kar:,.2f} ₺ ({kar_pct:+.2f}%)
                        """)
                        
                        if st.button(f"❌ {hisse} Sil", key=f"del_{hisse}", use_container_width=True):
                            del st.session_state['portfolio'][hisse]
                            st.rerun()
                        st.divider()
                except:
                    continue
    except Exception as e:
        st.sidebar.error("Portföy hesaplanamadı")
else:
    st.sidebar.info("Portföyünüz boş. Analiz sonuçlarından hisse ekleyin.")

st.sidebar.divider()

# --- AYARLAR ---
st.sidebar.header("⚙️ Ayarlar")

# BIST100 TAM LİSTESİ (100 HİSSE)
varsayilan_hisseler = [
    "AEFES.IS", "AGHOL.IS", "AKBNK.IS", "AKSA.IS", "AKSEN.IS", "ALARK.IS", "ALTNY.IS", 
    "ANSGR.IS", "ARCLK.IS", "ASELS.IS", "ASTOR.IS", "BALSU.IS", "BIMAS.IS", "BINHO.IS",
    "BRMEN.IS", "BRSAN.IS", "BRYAT.IS", "BSOKE.IS", "BTCIM.IS", "CANTE.IS", "CCOLA.IS",
    "CIMSA.IS", "DOAS.IS", "DOHOL.IS", "ECILC.IS", "ECZYT.IS", "EGEEN.IS", "EKGYO.IS",
    "ENERY.IS", "ENJSA.IS", "ENKAI.IS", "ERBOS.IS", "EREGL.IS", "EUREN.IS", "FROTO.IS",
    "GARAN.IS", "GENIL.IS", "GENTS.IS", "GESAN.IS", "GLYHO.IS", "GOLTS.IS", "GOZDE.IS",
    "GSDHO.IS", "GUBRF.IS", "GWIND.IS", "HALKB.IS", "HEKTS.IS", "IEYHO.IS", "IMASM.IS",
    "INDES.IS", "IPEKE.IS", "ISCTR.IS", "ISDMR.IS", "ISGYO.IS", "ISMEN.IS", "KARSN.IS",
    "KARTN.IS", "KCHOL.IS", "KLSER.IS", "KONTR.IS", "KONYA.IS", "KOZAA.IS", "KOZAL.IS",
    "KRDMD.IS", "MAVI.IS", "METUR.IS", "MGROS.IS", "MIATK.IS", "ODAS.IS", "OTKAR.IS",
    "OYAKC.IS", "OYYAT.IS", "PAMEL.IS", "PARSN.IS", "PETKM.IS", "PGSUS.IS", "PSGYO.IS",
    "QUAGR.IS", "REEDR.IS", "SAHOL.IS", "SASA.IS", "SAYAS.IS", "SELEC.IS", "SISE.IS",
    "SKBNK.IS", "SMART.IS", "SMRTG.IS", "SNGYO.IS", "SOKM.IS", "SRVGY.IS", "TAVHL.IS",
    "TCELL.IS", "THYAO.IS", "TKFEN.IS", "TKNSA.IS", "TOASO.IS", "TRGYO.IS", "TSKB.IS",
    "TTKOM.IS", "TTRAK.IS", "TUKAS.IS", "TUPRS.IS", "ULKER.IS", "VAKBN.IS", "VESTL.IS",
    "YEOTK.IS", "YKBNK.IS", "YYLGD.IS", "ZOREN.IS"
]

secilen_hisseler = st.sidebar.multiselect(
    "📊 Taranacak Hisseler (100 adet)", 
    varsayilan_hisseler, 
    default=varsayilan_hisseler,  # TÜM HİSSELER VARSAYILAN
    help="BIST100'deki tüm hisseler. Varsayılan olarak HEPSİ seçili."
)

st.sidebar.markdown("**İndikatör Ayarları**")
rsi_alt = st.sidebar.slider("RSI Alım (<)", 20, 40, 30)
rsi_ust = st.sidebar.slider("RSI Satış (>)", 60, 90, 70)
atr_mult = st.sidebar.slider("Stop-Loss (ATR x)", 1.5, 3.0, 2.0)
bb_length = st.sidebar.slider("Bollinger Bands", 10, 30, 20)

# Hızlı seçim butonları
st.sidebar.markdown("**Hızlı Seçim**")
col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("✅ Tümünü Seç", use_container_width=True):
        st.session_state['secilen_hisseler_temp'] = varsayilan_hisseler
        st.rerun()
with col2:
    if st.button("❌ Temizle", use_container_width=True):
        st.session_state['secilen_hisseler_temp'] = []
        st.rerun()

# --- GELİŞMİŞ ANALİZ MOTORU ---
def karar_ver(rsi, macd_al, skor, bb_signal, stoch_signal):
    """Gelişmiş karar mekanizması"""
    if rsi > 75 and skor < 0: 
        return "🔴 GÜÇLÜ SAT"
    elif rsi > 70: 
        return "🔴 SAT"
    elif skor >= 6 and bb_signal == "AL": 
        return "🚀 GÜÇLÜ AL"
    elif skor >= 4 and macd_al: 
        return "🚀 AL"
    elif skor >= 2 and (bb_signal == "AL" or stoch_signal == "AL"): 
        return "🟢 AL"
    elif rsi < 25 and not macd_al: 
        return "👀 DİP BÖLGE"
    elif skor <= -2: 
        return "⛔ UZAK DUR"
    else: 
        return "🟡 İZLE"

def yapay_zeka_yorumu(rsi, macd_al, golden_cross, trend_guclu, mum_formasyonu, bb_signal, 
                      stoch_signal, volume_signal):
    """Geliştirilmiş AI yorumu"""
    yorumlar = []
    
    if rsi < 25: 
        yorumlar.append(f"⚠️ Aşırı satış (RSI:{rsi:.1f})")
    elif rsi < 30: 
        yorumlar.append(f"📉 Oversold (RSI:{rsi:.1f})")
    elif rsi > 75: 
        yorumlar.append(f"🔥 Aşırı alım! (RSI:{rsi:.1f})")
    elif rsi > 70: 
        yorumlar.append(f"📈 Overbought (RSI:{rsi:.1f})")
    
    if macd_al: 
        yorumlar.append("✅ MACD pozitif")
    
    if trend_guclu: 
        yorumlar.append("💪 Güçlü trend")
    else: 
        yorumlar.append("💤 Yatay piyasa")
    
    if golden_cross: 
        yorumlar.append("⭐ Golden Cross!")
    if mum_formasyonu: 
        yorumlar.append(f"🕯️ {mum_formasyonu}")
    if bb_signal: 
        yorumlar.append(f"📊 BB: {bb_signal}")
    if stoch_signal: 
        yorumlar.append(f"📉 Stoch: {stoch_signal}")
    if volume_signal: 
        yorumlar.append(f"📊 {volume_signal}")
    
    return " | ".join(yorumlar) if yorumlar else "Normal piyasa koşulları"

def verileri_getir(hisse_listesi):
    """Ana analiz motoru"""
    sonuclar = []
    bar = st.progress(0)
    status = st.empty()
    
    for i, symbol in enumerate(hisse_listesi):
        bar.progress((i + 1) / len(hisse_listesi))
        status.caption(f"🔍 Analiz: {symbol} ({i+1}/{len(hisse_listesi)})")
        
        try:
            df = yf.download(symbol, period="1y", interval="1d", progress=False)
            if isinstance(df.columns, pd.MultiIndex): 
                df.columns = df.columns.get_level_values(0)
            if df.empty or len(df) < 100: 
                continue
            
            # --- TEMEL İNDİKATÖRLER ---
            df['RSI'] = df.ta.rsi(length=14)
            
            macd = df.ta.macd(fast=12, slow=26, signal=9)
            if macd is not None: 
                df = pd.concat([df, macd], axis=1)
            
            df['SMA_50'] = df.ta.sma(length=50)
            df['SMA_200'] = df.ta.sma(length=200)
            
            adx = df.ta.adx(length=14)
            if adx is not None: 
                df = pd.concat([df, adx], axis=1)
            
            df['ATR'] = df.ta.atr(length=14)
            
            # --- GELİŞMİŞ İNDİKATÖRLER ---
            bb = df.ta.bbands(length=bb_length, std=2)
            if bb is not None:
                df = pd.concat([df, bb], axis=1)
            
            stoch = df.ta.stoch(k=14, d=3, smooth_k=3)
            if stoch is not None:
                df = pd.concat([df, stoch], axis=1)
            
            df['OBV'] = df.ta.obv()
            df['Volume_SMA'] = df['Volume'].rolling(window=20).mean()
            
            try:
                engulf = df.ta.cdl_engulfing()
                doji = df.ta.cdl_doji()
                hammer = df.ta.cdl_hammer()
                if engulf is not None: 
                    df = pd.concat([df, engulf], axis=1)
                if doji is not None: 
                    df = pd.concat([df, doji], axis=1)
                if hammer is not None: 
                    df = pd.concat([df, hammer], axis=1)
            except: 
                pass
            
            # --- SİNYAL ÜRETİMİ ---
            son = df.iloc[-1]
            onceki = df.iloc[-2]
            
            fiyat = round(son['Close'], 2)
            rsi = round(son['RSI'], 2) if not pd.isna(son['RSI']) else 50
            atr_val = son['ATR'] if not pd.isna(son['ATR']) else 0
            stop_loss = round(fiyat - (atr_val * atr_mult), 2)
            
            sinyaller_listesi = []
            skor = 0
            
            # RSI
            if rsi < rsi_alt: 
                sinyaller_listesi.append("🟢 RSI DİP")
                skor += 2
            elif rsi > rsi_ust: 
                sinyaller_listesi.append("🔴 RSI ZİRVE")
                skor -= 2
            
            # MACD
            macd_al = False
            try:
                macd_line = [col for col in df.columns if col.startswith('MACD_')][0]
                signal_line = [col for col in df.columns if col.startswith('MACDs_')][0]
                if son[macd_line] > son[signal_line] and onceki[macd_line] < onceki[signal_line]:
                    macd_al = True
                    sinyaller_listesi.append("🚀 MACD AL")
                    skor += 3
            except: 
                pass
            
            # Golden Cross
            golden_cross = False
            if son['SMA_50'] > son['SMA_200'] and onceki['SMA_50'] < onceki['SMA_200']:
                golden_cross = True
                sinyaller_listesi.append("⭐ GOLDEN CROSS")
                skor += 5
            
            # Trend
            trend_guclu = False
            try:
                adx_col = [col for col in df.columns if col.startswith('ADX_')][0]
                if son[adx_col] > 25: 
                    trend_guclu = True
                    sinyaller_listesi.append("💪 GÜÇLÜ TREND")
                    skor += 1
                elif son[adx_col] < 20: 
                    sinyaller_listesi.append("💤 ZAYIF TREND")
            except: 
                pass
            
            # Bollinger Bands
            bb_signal = None
            try:
                bb_lower = [col for col in df.columns if 'BBL_' in col][0]
                bb_upper = [col for col in df.columns if 'BBU_' in col][0]
                
                if son['Close'] < son[bb_lower]:
                    bb_signal = "AL"
                    sinyaller_listesi.append("📊 BB DİP")
                    skor += 2
                elif son['Close'] > son[bb_upper]:
                    bb_signal = "SAT"
                    sinyaller_listesi.append("📊 BB ZİRVE")
                    skor -= 2
            except: 
                pass
            
            # Stochastic
            stoch_signal = None
            try:
                stoch_k = [col for col in df.columns if 'STOCHk_' in col][0]
                stoch_d = [col for col in df.columns if 'STOCHd_' in col][0]
                
                if son[stoch_k] < 20 and son[stoch_k] > son[stoch_d]:
                    stoch_signal = "AL"
                    sinyaller_listesi.append("📈 STOCH AL")
                    skor += 2
                elif son[stoch_k] > 80:
                    stoch_signal = "SAT"
                    sinyaller_listesi.append("📉 STOCH SAT")
                    skor -= 1
            except: 
                pass
            
            # Volume
            volume_signal = None
            if son['Volume'] > son['Volume_SMA'] * 1.5:
                volume_signal = "YÜKSEK HACİM"
                sinyaller_listesi.append("📊 YÜKSEK HACİM")
                skor += 1
            
            # OBV
            try:
                obv_sma = df['OBV'].rolling(window=20).mean()
                if son['OBV'] > obv_sma.iloc[-1]:
                    sinyaller_listesi.append("💰 PARA GİRİŞİ")
                    skor += 1
            except: 
                pass
            
            # Mum formasyonları
            mum_formasyonu = ""
            try:
                engulf_col = [col for col in df.columns if 'CDL_ENGULFING' in col][0]
                if son[engulf_col] == 100:
                    mum_formasyonu = "Yutan Boğa"
                    sinyaller_listesi.append("🔥 YUTAN BOĞA")
                    skor += 2
                    
                hammer_col = [col for col in df.columns if 'CDL_HAMMER' in col][0]
                if son[hammer_col] == 100:
                    mum_formasyonu = "Çekiç"
                    sinyaller_listesi.append("🔨 ÇEKİÇ")
                    skor += 2
            except: 
                pass
            
            # Portföy kontrolü
            hisse_adi = symbol.replace(".IS", "")
            if hisse_adi in st.session_state['portfolio']:
                sinyaller_listesi.append("💼 PORTFÖYDE")
            
            # Karar
            karar = karar_ver(rsi, macd_al, skor, bb_signal, stoch_signal)
            ai_yorum = yapay_zeka_yorumu(rsi, macd_al, golden_cross, trend_guclu, 
                                        mum_formasyonu, bb_signal, stoch_signal, volume_signal)
            
            # Hedefler
            risk = max(0, fiyat - stop_loss)
            hedef_1 = fiyat + (risk * 2)
            hedef_2 = fiyat + (risk * 3)
            
            if len(sinyaller_listesi) > 0 or hisse_adi in st.session_state['portfolio']:
                sonuclar.append({
                    "Hisse": hisse_adi,
                    "Fiyat": fiyat,
                    "RSI": rsi,
                    "Skor": skor,
                    "Sinyaller": " | ".join(sinyaller_listesi),
                    "AI Yorum": ai_yorum,
                    "Karar": karar,
                    "Stop-Loss": stop_loss,
                    "Hedef 1:2": hedef_1,
                    "Hedef 1:3": hedef_2,
                })
                        
        except Exception as e:
            continue
    
    bar.empty()
    status.empty()
    return pd.DataFrame(sonuclar)

# --- ANA ARAYÜZ ---
col1, col2, col3 = st.columns([2, 3, 1])

with col1:
    start = st.button("🚀 TARAMAYI BAŞLAT", type="primary", use_container_width=True)

with col2:
    st.info(f"📊 {len(secilen_hisseler)} hisse taranacak | BIST100 Tam Liste")

with col3:
    if st.button("🔄 Yenile", use_container_width=True):
        st.rerun()

# Bilgilendirme
st.caption(f"💡 **Toplam {len(varsayilan_hisseler)} BIST100 hissesi mevcut** | Seçili: {len(secilen_hisseler)} hisse")

# --- TARAMA ---
if start:
    if len(secilen_hisseler) == 0:
        st.warning("⚠️ Lütfen en az bir hisse seçin!")
    else:
        with st.spinner(f"🔍 {len(secilen_hisseler)} hisse taranıyor..."):
            st.session_state['data'] = verileri_getir(secilen_hisseler)
            st.success("✅ Tarama tamamlandı!")

# --- SONUÇLAR ---
if st.session_state['data'] is not None and not st.session_state['data'].empty:
    df_final = st.session_state['data'].sort_values(by="Skor", ascending=False)
    
    # Metrikler
    col1, col2, col3, col4 = st.columns(4)
    
    guclu_al = len(df_final[df_final['Karar'].str.contains("GÜÇLÜ AL")])
    al = len(df_final[df_final['Karar'].str.contains("AL")])
    sat = len(df_final[df_final['Karar'].str.contains("SAT")])
    izle = len(df_final[df_final['Karar'].str.contains("İZLE")])
    
    col1.metric("🚀 Güçlü Alım", guclu_al)
    col2.metric("🟢 Alım", al)
    col3.metric("🔴 Satım", sat)
    col4.metric("🟡 İzleme", izle)
    
    st.divider()
    
    # Alarm
    if guclu_al > 0:
        st.markdown(f"""
        <div class="alert-box">
            <h3 style="margin:0; color: #FF6B6B;">🔔 ALARM: {guclu_al} adet güçlü alım fırsatı tespit edildi!</h3>
        </div>
        """, unsafe_allow_html=True)
    
    # Tablo
    st.dataframe(
        df_final,
        column_order=("Hisse", "Fiyat", "RSI", "Skor", "Sinyaller", "Karar", "AI Yorum", 
                     "Stop-Loss", "Hedef 1:2", "Hedef 1:3"),
        column_config={
            "Karar": st.column_config.TextColumn("📢 Karar", width="small"),
            "Skor": st.column_config.ProgressColumn("💪 Güç", format="%d", min_value=-10, max_value=15),
            "AI Yorum": st.column_config.TextColumn("🤖 AI Analiz", width="large"),
            "Fiyat": st.column_config.NumberColumn("💰 Fiyat", format="%.2f ₺"),
            "Stop-Loss": st.column_config.NumberColumn("🛑 Stop", format="%.2f ₺"),
            "Hedef 1:2": st.column_config.NumberColumn("🎯 Hedef 1", format="%.2f ₺"),
            "Hedef 1:3": st.column_config.NumberColumn("🎯 Hedef 2", format="%.2f ₺"),
        },
        use_container_width=True,
        height=400
    )
    
    # Portföye ekle
    st.divider()
    st.subheader("💼 Portföye Ekle")
    
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        secili_hisse = st.selectbox("Hisse Seç:", df_final['Hisse'].unique(), key="add_stock")
    with col2:
        adet = st.number_input("Adet:", min_value=1, value=100, key="add_amount")
    with col3:
        alis_fiyati = st.number_input(
            "Alış Fiyatı:", 
            value=float(df_final[df_final['Hisse']==secili_hisse]['Fiyat'].iloc[0]),
            format="%.2f", 
            key="add_price"
        )
    with col4:
        if st.button("➕ EKLE", type="primary", use_container_width=True):
            portfoy_ekle(secili_hisse, adet, alis_fiyati)
            st.success(f"✅ {secili_hisse} portföye eklendi!")
            st.rerun()
    
    st.divider()
    
    # --- GRAFİK ---
    st.subheader("📊 Detaylı Grafik Analizi")
    
    vade_map = {"1 Hafta": "5d", "1 Ay": "1mo", "3 Ay": "3mo", "6 Ay": "6mo", "1 Yıl": "1y"}
    
    col_sel, col_radio = st.columns([1, 2])
    with col_sel:
        selected = st.selectbox("İncelenecek Hisse:", df_final['Hisse'].unique(), key="chart_stock")
    with col_radio:
        secilen_vade_ad = st.radio("Vade:", list(vade_map.keys()), horizontal=True, index=2)
    
    if selected:
        period_val = vade_map[secilen_vade_ad]
        interval_val = "60m" if period_val == "5d" else "1d"
        
        with st.spinner("📈 Grafik yükleniyor..."):
            df_chart = yf.download(selected+".IS", period=period_val, interval=interval_val, progress=False)
            if isinstance(df_chart.columns, pd.MultiIndex):
                df_chart.columns = df_chart.columns.get_level_values(0)
            
            df_chart['SMA_20'] = df_chart['Close'].rolling(window=20).mean()
            df_chart['SMA_50'] = df_chart['Close'].rolling(window=50).mean()
            
            bb = df_chart.ta.bbands(length=20, std=2)
            if bb is not None:
                df_chart = pd.concat([df_chart, bb], axis=1)
            
            df_chart['RSI'] = df_chart.ta.rsi(length=14)
            
            # Grafik
            fig = make_subplots(
                rows=3, cols=1, 
                shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=[0.6, 0.2, 0.2],
                subplot_titles=(f"{selected} - Fiyat", "Hacim", "RSI")
            )
            
            # Mum
            fig.add_trace(go.Candlestick(
                x=df_chart.index,
                open=df_chart['Open'],
                high=df_chart['High'],
                low=df_chart['Low'],
                close=df_chart['Close'],
                name=selected,
                increasing_line_color='#26a69a',
                increasing_fillcolor='#26a69a',
                decreasing_line_color='#ef5350',
                decreasing_fillcolor='#ef5350'
            ), row=1, col=1)
            
            # SMA
            fig.add_trace(go.Scatter(
                x=df_chart.index, y=df_chart['SMA_20'],
                name='SMA 20', line=dict(color='yellow', width=1)
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(
                x=df_chart.index, y=df_chart['SMA_50'],
                name='SMA 50', line=dict(color='orange', width=1)
            ), row=1, col=1)
            
            # BB
            try:
                bb_upper = [col for col in df_chart.columns if 'BBU_' in col][0]
                bb_lower = [col for col in df_chart.columns if 'BBL_' in col][0]
                
                fig.add_trace(go.Scatter(
                    x=df_chart.index, y=df_chart[bb_upper],
                    name='BB Üst', line=dict(color='rgba(250,250,250,0.3)', width=1)
                ), row=1, col=1)
                
                fig.add_trace(go.Scatter(
                    x=df_chart.index, y=df_chart[bb_lower],
                    name='BB Alt', line=dict(color='rgba(250,250,250,0.3)', width=1),
                    fill='tonexty', fillcolor='rgba(250,250,250,0.1)'
                ), row=1, col=1)
            except:
                pass
            
            # Stop/Hedef
            row_data = df_final[df_final['Hisse'] == selected].iloc[0]
            stop_level = row_data['Stop-Loss']
            hedef1 = row_data['Hedef 1:2']
            hedef2 = row_data['Hedef 1:3']
            
            fig.add_shape(
                type="line",
                x0=df_chart.index[0], x1=df_chart.index[-1],
                y0=stop_level, y1=stop_level,
                line=dict(color="red", width=2, dash="dash"),
                row=1, col=1
            )
            
            fig.add_shape(
                type="line",
                x0=df_chart.index[0], x1=df_chart.index[-1],
                y0=hedef1, y1=hedef1,
                line=dict(color="green", width=1, dash="dot"),
                row=1, col=1
            )
            
            fig.add_shape(
                type="line",
                x0=df_chart.index[0], x1=df_chart.index[-1],
                y0=hedef2, y1=hedef2,
                line=dict(color="lime", width=1, dash="dot"),
                row=1, col=1
            )
            
            # Hacim
            colors = ['#26a69a' if c >= o else '#ef5350' 
                     for c, o in zip(df_chart['Close'], df_chart['Open'])]
            fig.add_trace(go.Bar(
                x=df_chart.index, y=df_chart['Volume'],
                name='Hacim', marker_color=colors, opacity=0.6
            ), row=2, col=1)
            
            # RSI
            fig.add_trace(go.Scatter(
                x=df_chart.index, y=df_chart['RSI'],
                name='RSI', line=dict(color='purple', width=2)
            ), row=3, col=1)
            
            fig.add_shape(
                type="line",
                x0=df_chart.index[0], x1=df_chart.index[-1],
                y0=70, y1=70,
                line=dict(color="red", width=1, dash="dash"),
                row=3, col=1
            )
            
            fig.add_shape(
                type="line",
                x0=df_chart.index[0], x1=df_chart.index[-1],
                y0=30, y1=30,
                line=dict(color="green", width=1, dash="dash"),
                row=3, col=1
            )
            
            # Layout
            fig.update_layout(
                template='plotly_dark',
                paper_bgcolor='#131722',
                plot_bgcolor='#131722',
                height=800,
                margin=dict(l=10, r=10, t=40, b=10),
                hovermode='x unified',
                showlegend=True,
                legend=dict(x=0, y=1, bgcolor='rgba(0,0,0,0.5)'),
                xaxis_rangeslider_visible=False
            )
            
            fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='#2a2e39')
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#2a2e39')
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Risk tablosu
            st.divider()
            st.subheader("📊 Risk/Ödül Analizi")
            
            curr_price = row_data['Fiyat']
            risk_amount = max(0, curr_price - stop_level)
            
            profit_1 = hedef1 - curr_price
            profit_2 = hedef2 - curr_price
            
            profit_pct_1 = (profit_1 / curr_price) * 100
            profit_pct_2 = (profit_2 / curr_price) * 100
            loss_pct = (risk_amount / curr_price) * 100
            
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("💰 FİYAT", f"{curr_price:.2f} ₺")
            c2.metric("🛑 STOP", f"{stop_level:.2f} ₺", f"-{loss_pct:.1f}%", delta_color="inverse")
            c3.metric("🎯 HEDEF 1 (1:2)", f"{hedef1:.2f} ₺", f"+{profit_pct_1:.1f}%")
            c4.metric("🎯 HEDEF 2 (1:3)", f"{hedef2:.2f} ₺", f"+{profit_pct_2:.1f}%")
            c5.metric("⚖️ RİSK", f"{risk_amount:.2f} ₺")
            
            # Portföy kontrolü
            if selected in st.session_state['portfolio']:
                portfoy_bilgi = st.session_state['portfolio'][selected]
                portfoy_kar = (curr_price - portfoy_bilgi['alis_fiyati']) * portfoy_bilgi['adet']
                portfoy_kar_pct = ((curr_price - portfoy_bilgi['alis_fiyati']) / portfoy_bilgi['alis_fiyati']) * 100
                
                if portfoy_kar > 0:
                    st.markdown(f"""
                    <div class="success-box">
                        <h4 style="margin:0;">✅ Portföyde Kâr: {portfoy_kar:,.2f} ₺ ({portfoy_kar_pct:+.2f}%)</h4>
                        <p style="margin:5px 0 0 0;">Alış: {portfoy_bilgi['alis_fiyati']:.2f} ₺ | Adet: {portfoy_bilgi['adet']} | Güncel: {curr_price:.2f} ₺</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="alert-box">
                        <h4 style="margin:0;">⚠️ Portföyde Zarar: {portfoy_kar:,.2f} ₺ ({portfoy_kar_pct:+.2f}%)</h4>
                        <p style="margin:5px 0 0 0;">Alış: {portfoy_bilgi['alis_fiyati']:.2f} ₺ | Adet: {portfoy_bilgi['adet']} | Güncel: {curr_price:.2f} ₺</p>
                    </div>
                    """, unsafe_allow_html=True)

else:
    if st.session_state['data'] is not None:
        st.warning("⚠️ Sonuç bulunamadı. Filtre ayarlarını değiştirin.")
    else:
        st.info("👆 Taramaya başlamak için yukarıdaki butona tıklayın.")

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: #666; padding: 20px;'>
    <p><strong>BIST100 PRO TRADER</strong> | Gelişmiş Teknik Analiz & Portföy Yönetimi</p>
    <p style='font-size: 12px;'>⚠️ Bu uygulama yatırım tavsiyesi değildir. Kararlar kendi sorumluluğunuzdadır.</p>
    <p style='font-size: 11px; margin-top: 10px;'>📊 BIST100 Tam Liste: {len(varsayilan_hisseler)} Hisse</p>
</div>
""", unsafe_allow_html=True)
