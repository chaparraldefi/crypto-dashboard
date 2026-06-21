import streamlit as st
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone

st.set_page_config(page_title="DeFi Dashboard", layout="wide")

# ---------- helpers ----------

def safe_fromtimestamp(ts, unit='s'):
    """Converte timestamp numérico para datetime, evitando TypeError."""
    if ts is None or pd.isna(ts):
        return pd.NaT
    try:
        ts = int(float(ts))
        if unit == 'ms':
            ts = ts / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return pd.NaT


def get_defillama_protocols():
    url = "https://api.defillama.com/protocols"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def get_global_tvl():
    url = "https://api.defillama.com/charts"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data)
    df['date'] = df['date'].apply(lambda x: safe_fromtimestamp(x, 's'))
    df = df.dropna(subset=['date'])
    df = df.sort_values('date')
    return df


def get_stablecoins():
    url = "https://stablecoins.llama.fi/stablecoins?includePrices=true"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data.get('peggedAssets', []))
    return df


def get_protocol_fees_revenue(protocol_slug):
    url = f"https://api.defillama.com/summary/fees/{protocol_slug}"
    r = requests.get(url, timeout=30)
    if r.status_code == 200:
        return r.json()
    return None


def aggregate_sectors(protocols):
    df = pd.DataFrame(protocols)
    df['tvl'] = pd.to_numeric(df.get('tvl', 0), errors='coerce').fillna(0)
    df['category'] = df.get('category', 'Outro').fillna('Outro')
    sector = df.groupby('category', as_index=False)['tvl'].sum().sort_values('tvl', ascending=False)
    return sector


# ---------- UI ----------

st.title("🏦 DeFi Dashboard")

abas = st.tabs(["Visão Geral", "TVL", "Stablecoins", "Receitas", "Setores"])

# ---------- Aba 1: Visão Geral ----------
with abas[0]:
    st.header("Visão Geral")
    st.markdown("Painel resumido com os principais indicadores do mercado DeFi.")

    try:
        protocols = get_defillama_protocols()
        tvl_df = get_global_tvl()
        stables_df = get_stablecoins()

        total_tvl = tvl_df['totalLiquidityUSD'].iloc[-1] if not tvl_df.empty else 0
        total_protocols = len(protocols)
        total_stable = pd.to_numeric(stables_df.get('circulating', 0), errors='coerce').sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("TVL Total (USD)", f"${total_tvl:,.0f}")
        c2.metric("Protocolos Rastreados", f"{total_protocols}")
        c3.metric("Stablecoins em Circulação", f"${total_stable:,.0f}")

        fig = px.line(
            tvl_df,
            x='date',
            y='totalLiquidityUSD',
            title="Evolução do TVL Global",
            labels={'totalLiquidityUSD': 'TVL (USD)', 'date': 'Data'}
        )
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erro ao carregar Visão Geral: {e}")

# ---------- Aba 2: TVL ----------
with abas[1]:
    st.header("TVL")
    st.markdown("Análise detalhada do Total Value Locked global e por protocolo.")

    try:
        tvl_df = get_global_tvl()
        protocols = get_defillama_protocols()

        fig = px.area(
            tvl_df,
            x='date',
            y='totalLiquidityUSD',
            title="TVL Global ao Longo do Tempo",
            labels={'totalLiquidityUSD': 'TVL (USD)', 'date': 'Data'}
        )
        st.plotly_chart(fig, use_container_width=True)

        top_df = pd.DataFrame(protocols)
        top_df['tvl'] = pd.to_numeric(top_df.get('tvl', 0), errors='coerce').fillna(0)
        top_df = top_df.sort_values('tvl', ascending=False).head(15)

        fig2 = px.bar(
            top_df,
            x='tvl',
            y='name',
            orientation='h',
            title="Top 15 Protocolos por TVL",
            labels={'tvl': 'TVL (USD)', 'name': 'Protocolo'}
        )
        fig2.update_layout(yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig2, use_container_width=True)

    except Exception as e:
        st.error(f"Erro ao carregar TVL: {e}")

# ---------- Aba 3: Stablecoins ----------
with abas[2]:
    st.header("Stablecoins")
    st.markdown("Dados de stablecoins por capitalização de mercado e dominância.")

    try:
        stables_df = get_stablecoins()
        stables_df['circulating'] = pd.to_numeric(stables_df.get('circulating', 0), errors='coerce').fillna(0)
        stables_df = stables_df.sort_values('circulating', ascending=False).head(15)

        fig = px.pie(
            stables_df,
            names='name',
            values='circulating',
            title="Market Share das Stablecoins",
            hole=0.4
        )
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.bar(
            stables_df,
            x='name',
            y='circulating',
            title="Capitalização das Top Stablecoins",
            labels={'circulating': 'Circulante (USD)', 'name': 'Stablecoin'}
        )
        st.plotly_chart(fig2, use_container_width=True)

    except Exception as e:
        st.error(f"Erro ao carregar Stablecoins: {e}")

# ---------- Aba 4: Receitas (Fees vs Receita) ----------
with abas[3]:
    st.header("Receitas")
    st.markdown("Comparativo entre Fees geradas e Receita capturada pelos protocolos.")

    protocol_slug = st.text_input("Slug do protocolo no DeFiLlama (ex: uniswap, aave, lido)", value="uniswap")

    if protocol_slug:
        try:
            data = get_protocol_fees_revenue(protocol_slug)
            if not data or 'totalDataChart' not in data:
                st.warning("Dados de fees/receita não encontrados para este protocolo.")
            else:
                chart = data['totalDataChart']
                df = pd.DataFrame(chart, columns=['date', 'fees', 'revenue'])
                df['date'] = df['date'].apply(lambda x: safe_fromtimestamp(x, 's'))
                df = df.dropna(subset=['date'])
                df['fees'] = pd.to_numeric(df.get('fees', 0), errors='coerce').fillna(0)
                df['revenue'] = pd.to_numeric(df.get('revenue', 0), errors='coerce').fillna(0)

                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df['date'], y=df['fees'], mode='lines', name='Fees', stackgroup='one'))
                fig.add_trace(go.Scatter(x=df['date'], y=df['revenue'], mode='lines', name='Receita', stackgroup='one'))
                fig.update_layout(
                    title=f"Fees vs Receita: {protocol_slug.title()}",
                    xaxis_title="Data",
                    yaxis_title="USD",
                    hovermode="x unified"
                )
                st.plotly_chart(fig, use_container_width=True)

                c1, c2 = st.columns(2)
                c1.metric("Fees Totais", f"${df['fees'].sum():,.0f}")
                c2.metric("Receita Total", f"${df['revenue'].sum():,.0f}")

        except Exception as e:
            st.error(f"Erro ao carregar Receitas: {e}")

# ---------- Aba 5: Setores ----------
with abas[4]:
    st.header("Setores")
    st.markdown("Distribuição do TVL por categoria/setor do mercado DeFi.")

    try:
        protocols = get_defillama_protocols()
        sector_df = aggregate_sectors(protocols)

        fig = px.treemap(
            sector_df,
            path=['category'],
            values='tvl',
            title="TVL por Setor",
            color='tvl',
            color_continuous_scale='Blues'
        )
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.bar(
            sector_df.head(15),
            x='category',
            y='tvl',
            title="Top Setores por TVL",
            labels={'tvl': 'TVL (USD)', 'category': 'Setor'}
        )
        st.plotly_chart(fig2, use_container_width=True)

    except Exception as e:
        st.error(f"Erro ao carregar Setores: {e}")
