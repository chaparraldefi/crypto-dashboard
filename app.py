import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuração da página
st.set_page_config(
    page_title="Dashboard Crypto - DeFiLlama",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# URLs base da API DeFiLlama
BASE_URL = "https://api.llama.fi"
STABLECOINS_URL = "https://stablecoins.llama.fi"

# Cache de requisições para reduzir chamadas à API
@st.cache_data(ttl=3600)
def fetch_data(url, params=None, max_retries=3):
    """Faz requisições à API com retry e tratamento de erros."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout na requisição {url} (tentativa {attempt + 1}/{max_retries})")
            time.sleep(2 ** attempt)
        except requests.exceptions.HTTPError as e:
            logger.error(f"Erro HTTP {e.response.status_code} ao acessar {url}")
            if e.response.status_code in [400, 404, 500, 502, 503, 504]:
                time.sleep(2 ** attempt)
            else:
                break
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de conexão: {e}")
            time.sleep(2 ** attempt)
    return None

def safe_get(data, key, default=None):
    """Obtém valor de dicionário de forma segura."""
    if isinstance(data, dict):
        return data.get(key, default)
    return default

def process_tvl_data(data):
    """Processa dados de TVL de protocolos."""
    if not data or not isinstance(data, list):
        return pd.DataFrame()
    
    records = []
    for protocol in data:
        if not isinstance(protocol, dict):
            continue
        tvl = safe_get(protocol, 'tvl', 0) or 0
        mcap = safe_get(protocol, 'mcap', 0) or 0
        records.append({
            'Protocolo': safe_get(protocol, 'name', 'Desconhecido'),
            'Categoria': safe_get(protocol, 'category', 'Outro'),
            'Cadeia': safe_get(protocol, 'chain', 'Desconhecida'),
            'TVL': float(tvl),
            'Market Cap': float(mcap),
            'MCAP/TVL': float(mcap / tvl) if tvl > 0 else 0,
            'Slug': safe_get(protocol, 'slug', '')
        })
    
    df = pd.DataFrame(records)
    return df.sort_values('TVL', ascending=False).reset_index(drop=True)

def process_stablecoins_data(data):
    """Processa dados de stablecoins."""
    if not data or not isinstance(data, dict):
        return pd.DataFrame()
    
    pegged_assets = safe_get(data, 'peggedAssets', [])
    if not isinstance(pegged_assets, list):
        return pd.DataFrame()
    
    records = []
    for stable in pegged_assets:
        if not isinstance(stable, dict):
            continue
        circ = safe_get(stable, 'circulating', {})
        if not isinstance(circ, dict):
            circ = {}
        total = sum(float(v) for v in circ.values() if isinstance(v, (int, float, str)) and v not in [None, ''])
        
        records.append({
            'Stablecoin': safe_get(stable, 'name', 'Desconhecida'),
            'Símbolo': safe_get(stable, 'symbol', ''),
            'Peg': safe_get(stable, 'peg', 'USD'),
            'Fornecimento Total': float(safe_get(stable, 'circulating', {}).get('peggedUSD', 0) or 0),
            'Cadeia Principal': safe_get(stable, 'chain', 'Desconhecida'),
            'Cadeias': len(safe_get(stable, 'chainBalances', {})) if isinstance(safe_get(stable, 'chainBalances'), dict) else 0
        })
    
    df = pd.DataFrame(records)
    return df.sort_values('Fornecimento Total', ascending=False).reset_index(drop=True)

def process_protocols_revenue(data):
    """Processa dados de receita de protocolos (usando fees/revenue)."""
    if not data or not isinstance(data, dict):
        return pd.DataFrame()
    
    protocols = safe_get(data, 'protocols', [])
    if not isinstance(protocols, list):
        return pd.DataFrame()
    
    records = []
    for protocol in protocols:
        if not isinstance(protocol, dict):
            continue
        total_revenue = 0.0
        total_fees = 0.0
        
        revenue_data = safe_get(protocol, 'totalRevenue', [])
        if isinstance(revenue_data, list) and revenue_data:
            try:
                total_revenue = float(revenue_data[-1]) if revenue_data[-1] not in [None, ''] else 0.0
            except (ValueError, TypeError):
                total_revenue = 0.0
        
        fees_data = safe_get(protocol, 'totalFees', [])
        if isinstance(fees_data, list) and fees_data:
            try:
                total_fees = float(fees_data[-1]) if fees_data[-1] not in [None, ''] else 0.0
            except (ValueError, TypeError):
                total_fees = 0.0
        
        records.append({
            'Protocolo': safe_get(protocol, 'name', 'Desconhecido'),
            'Categoria': safe_get(protocol, 'category', 'Outro'),
            'Cadeia': safe_get(protocol, 'chain', 'Desconhecida'),
            'Total Fees (30d)': total_fees,
            'Total Revenue (30d)': total_revenue
        })
    
    df = pd.DataFrame(records)
    return df.sort_values('Total Revenue (30d)', ascending=False).reset_index(drop=True)

def process_sectors_data(data):
    """Processa dados de setores/categorias."""
    if not data or not isinstance(data, dict):
        return pd.DataFrame()
    
    categories = safe_get(data, 'categories', {})
    if not isinstance(categories, dict):
        categories = data
    
    records = []
    for cat_name, cat_data in categories.items():
        if not isinstance(cat_data, dict):
            continue
        tvl = safe_get(cat_data, 'tvl', 0) or 0
        protocol_count = safe_get(cat_data, 'protocols', 0) or 0
        records.append({
            'Setor': cat_name,
            'TVL': float(tvl),
            'Protocolos': int(protocol_count)
        })
    
    df = pd.DataFrame(records)
    return df.sort_values('TVL', ascending=False).reset_index(drop=True)

def process_global_tvl_chart(data):
    """Processa dados históricos de TVL global para gráfico."""
    if not data or not isinstance(data, list):
        return pd.DataFrame()
    
    records = []
    for item in data:
        if isinstance(item, dict):
            date = safe_get(item, 'date', 0)
            tvl = safe_get(item, 'totalLiquidityUSD', 0) or 0
            if date:
                records.append({
                    'Data': datetime.fromtimestamp(date).strftime('%Y-%m-%d'),
                    'TVL Global': float(tvl)
                })
    
    df = pd.DataFrame(records)
    return df.sort_values('Data').reset_index(drop=True)

def generate_insights(tvl_df, stable_df, revenue_df, sectors_df, global_tvl_df):
    """Gera insights automáticos baseados nos dados."""
    insights = []
    
    try:
        if not tvl_df.empty:
            top_protocol = tvl_df.iloc[0]
            insights.append(f"🏆 **{top_protocol['Protocolo']}** lidera o TVL total com **${top_protocol['TVL']:,.0f}** na categoria {top_protocol['Categoria']}.")
            
            total_tvl = tvl_df['TVL'].sum()
            insights.append(f"💰 TVL agregado dos protocolos analisados: **${total_tvl:,.0f}**.")
        
        if not stable_df.empty:
            top_stable = stable_df.iloc[0]
            insights.append(f"🔒 **{top_stable['Stablecoin']}** é a stablecoin dominante com fornecimento de **${top_stable['Fornecimento Total']:,.0f}**.")
            
            total_stable = stable_df['Fornecimento Total'].sum()
            insights.append(f"💵 Fornecimento total de stablecoins: **${total_stable:,.0f}**.")
        
        if not revenue_df.empty:
            top_revenue = revenue_df.iloc[0]
            insights.append(f"📈 **{top_revenue['Protocolo']}** registra a maior receita com **${top_revenue['Total Revenue (30d)']:,.0f}**.")
        
        if not sectors_df.empty:
            top_sector = sectors_df.iloc[0]
            insights.append(f"🏭 O setor **{top_sector['Setor']}** concentra o maior TVL: **${top_sector['TVL']:,.0f}**.")
        
        if not global_tvl_df.empty and len(global_tvl_df) > 1:
            current_tvl = global_tvl_df['TVL Global'].iloc[-1]
            prev_tvl = global_tvl_df['TVL Global'].iloc[-30] if len(global_tvl_df) >= 30 else global_tvl_df['TVL Global'].iloc[0]
            change = ((current_tvl - prev_tvl) / prev_tvl) * 100 if prev_tvl > 0 else 0
            direction = "📉" if change < 0 else "📈"
            insights.append(f"{direction} TVL global variou **{change:.2f}%** no período analisado.")
    
    except Exception as e:
        logger.error(f"Erro ao gerar insights: {e}")
        insights.append("⚠️ Não foi possível gerar todos os insights devido a erro nos dados.")
    
    return insights

# ======================== STREAMLIT UI ========================

def main():
    st.title("📊 Dashboard Crypto - DeFiLlama")
    st.markdown("Análise de TVL, Stablecoins, Receitas, Setores e Insights do ecossistema DeFi.")
    
    # Sidebar
    st.sidebar.header("⚙️ Configurações")
    st.sidebar.markdown("---")
    
    refresh = st.sidebar.button("🔄 Atualizar Dados")
    
    if refresh:
        st.cache_data.clear()
        st.rerun()
    
    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Visão Geral", 
        "💰 TVL & Protocolos", 
        "💵 Stablecoins", 
        "📊 Receitas", 
        "🏭 Setores & Insights"
    ])
    
    # Loading state
    with st.spinner("Carregando dados da DeFiLlama..."):
        
        # Requisições à API
        protocols_data = fetch_data(f"{BASE_URL}/protocols")
        stablecoins_data = fetch_data(f"{STABLECOINS_URL}/stablecoins")
        revenue_data = fetch_data(f"{BASE_URL}/overview/fees")
        sectors_data = fetch_data(f"{BASE_URL}/categories")
        global_tvl_data = fetch_data(f"{BASE_URL}/charts")
    
    # Verificação de dados
    data_available = {
        'protocols': protocols_data is not None,
        'stablecoins': stablecoins_data is not None,
        'revenue': revenue_data is not None,
        'sectors': sectors_data is not None,
        'global_tvl': global_tvl_data is not None
    }
    
    # Processamento
    tvl_df = process_tvl_data(protocols_data) if data_available['protocols'] else pd.DataFrame()
    stable_df = process_stablecoins_data(stablecoins_data) if data_available['stablecoins'] else pd.DataFrame()
    revenue_df = process_protocols_revenue(revenue_data) if data_available['revenue'] else pd.DataFrame()
    sectors_df = process_sectors_data(sectors_data) if data_available['sectors'] else pd.DataFrame()
    global_tvl_df = process_global_tvl_chart(global_tvl_data) if data_available['global_tvl'] else pd.DataFrame()
    
    # ================= TAB 1: VISÃO GERAL =================
    with tab1:
        st.header("Visão Geral do Mercado DeFi")
        
        # Métricas
        col1, col2, col3, col4 = st.columns(4)
        
        total_tvl = tvl_df['TVL'].sum() if not tvl_df.empty else 0
        total_stable = stable_df['Fornecimento Total'].sum() if not stable_df.empty else 0
        total_revenue = revenue_df['Total Revenue (30d)'].sum() if not revenue_df.empty else 0
        total_protocols = len(tvl_df) if not tvl_df.empty else 0
        
        col1.metric("TVL Total", f"${total_tvl:,.0f}")
        col2.metric("Stablecoins", f"${total_stable:,.0f}")
        col3.metric("Receita 30d", f"${total_revenue:,.0f}")
        col4.metric("Protocolos", f"{total_protocols:,}")
        
        st.markdown("---")
        
        # Gráfico TVL global
        if not global_tvl_df.empty:
            st.subheader("Evolução do TVL Global")
            fig = px.line(
                global_tvl_df, 
                x='Data', 
                y='TVL Global',
                title='TVL Global ao Longo do Tempo',
                labels={'TVL Global': 'TVL (USD)'}
            )
            fig.update_layout(height=500, xaxis_title='Data', yaxis_title='TVL (USD)')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Dados históricos de TVL global não disponíveis.")
        
        # Insights
        st.subheader("💡 Insights Automáticos")
        insights = generate_insights(tvl_df, stable_df, revenue_df, sectors_df, global_tvl_df)
        for insight in insights:
            st.info(insight)
    
    # ================= TAB 2: TVL & PROTOCOLOS =================
    with tab2:
        st.header("TVL e Protocolos")
        
        if not tvl_df.empty:
            col1, col2 = st.columns(2)
            
            # Top protocolos por TVL
            with col1:
                st.subheader("Top 15 Protocolos por TVL")
                top_tvl = tvl_df.head(15).copy()
                fig = px.bar(
                    top_tvl, 
                    x='TVL', 
                    y='Protocolo', 
                    orientation='h',
                    color='Categoria',
                    title='Top 15 Protocolos por TVL',
                    labels={'TVL': 'TVL (USD)'}
                )
                fig.update_layout(height=500, yaxis={'categoryorder': 'total ascending'})
                st.plotly_chart(fig, use_container_width=True)
            
            # TVL por cadeia
            with col2:
                st.subheader("TVL por Cadeia")
                chain_tvl = tvl_df.groupby('Cadeia')['TVL'].sum().sort_values(ascending=False).head(15).reset_index()
                fig = px.pie(
                    chain_tvl, 
                    values='TVL', 
                    names='Cadeia',
                    title='Distribuição de TVL por Cadeia'
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)
            
            # Tabela completa
            st.subheader("Dados Detalhados de Protocolos")
            st.dataframe(
                tvl_df.style.format({
                    'TVL': '${:,.0f}',
                    'Market Cap': '${:,.0f}',
                    'MCAP/TVL': '{:.2f}'
                }),
                use_container_width=True,
                height=500
            )
            
            # Download
            csv = tvl_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download CSV - Protocolos",
                data=csv,
                file_name='protocolos_tvl.csv',
                mime='text/csv'
            )
        else:
            st.error("Não foi possível carregar os dados de TVL dos protocolos.")
    
    # ================= TAB 3: STABLECOINS =================
    with tab3:
        st.header("Stablecoins")
        
        if not stable_df.empty:
            col1, col2 = st.columns(2)
            
            # Top stablecoins
            with col1:
                st.subheader("Top Stablecoins por Fornecimento")
                top_stable = stable_df.head(15).copy()
                fig = px.bar(
                    top_stable,
                    x='Fornecimento Total',
                    y='Stablecoin',
                    orientation='h',
                    color='Peg',
                    title='Top 15 Stablecoins',
                    labels={'Fornecimento Total': 'Fornecimento (USD)'}
                )
                fig.update_layout(height=500, yaxis={'categoryorder': 'total ascending'})
                st.plotly_chart(fig, use_container_width=True)
            
            # Stablecoins por cadeia
            with col2:
                st.subheader("Stablecoins por Cadeia Principal")
                chain_stable = stable_df.groupby('Cadeia Principal')['Fornecimento Total'].sum().sort_values(ascending=False).head(15).reset_index()
                fig = px.pie(
                    chain_stable,
                    values='Fornecimento Total',
                    names='Cadeia Principal',
                    title='Distribuição por Cadeia Principal'
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)
            
            # Tabela
            st.subheader("Dados Detalhados de Stablecoins")
            st.dataframe(
                stable_df.style.format({'Fornecimento Total': '${:,.0f}'}),
                use_container_width=True,
                height=500
            )
            
            csv = stable_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download CSV - Stablecoins",
                data=csv,
                file_name='stablecoins.csv',
                mime='text/csv'
            )
        else:
            st.error("Não foi possível carregar os dados de stablecoins.")
    
    # ================= TAB 4: RECEITAS =================
    with tab4:
        st.header("Receitas de Protocolos")
        
        if not revenue_df.empty:
            col1, col2 = st.columns(2)
            
            # Top protocolos por receita
            with col1:
                st.subheader("Top 15 Protocolos por Receita (30d)")
                top_revenue = revenue_df.head(15).copy()
                fig = px.bar(
                    top_revenue,
                    x='Total Revenue (30d)',
                    y='Protocolo',
                    orientation='h',
                    color='Categoria',
                    title='Top 15 por Receita',
                    labels={'Total Revenue (30d)': 'Receita (USD)'}
                )
                fig.update_layout(height=500, yaxis={'categoryorder': 'total ascending'})
                st.plotly_chart(fig, use_container_width=True)
            
            # Fees vs Revenue
            with col2:
                st.subheader("Fees vs Receita")
                top_fees = revenue_df.head(15).copy()
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=top_fees['Protocolo'],
                    y=top_fees['Total Fees (30d)'],
                    name='Fees',
                    marker_color='lightblue'
                ))
                fig.add_trace(go.Bar(
                    x=top_fees['Protocolo'],
                    y=top_fees['Total Revenue (30d)'],
                    name='Receita',
                    marker_color='darkblue'
                ))
                fig.update_layout(
                    barmode='group',
                    title='Fees vs Receita (Top 15)',
                    xaxis_tickangle=-45,
                    height=500
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Tabela
            st.subheader("Dados Detalhados de Receitas")
            st.dataframe(
                revenue_df.style.format({
                    'Total Fees (30d)': '${:,.0f}',
                    'Total Revenue (30d)': '${:,.0f}'
                }),
                use_container_width=True,
                height=500
            )
            
            csv = revenue_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download CSV - Receitas",
                data=csv,
                file_name='receitas.csv',
                mime='text/csv'
            )
        else:
            st.error("Não foi possível carregar os dados de receitas.")
    
    # ================= TAB 5: SETORES & INSIGHTS =================
    with tab5:
        st.header("Setores e Insights")
        
        if not sectors_df.empty:
            st.subheader("TVL por Setor")
            fig = px.bar(
                sectors_df.head(20),
                x='Setor',
                y='TVL',
                color='Protocolos',
                title='TVL por Setor/Categoria',
                labels={'TVL': 'TVL (USD)', 'Protocolos': 'Nº de Protocolos'}
            )
            fig.update_layout(height=500, xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
            
            st.subheader("Dados de Setores")
            st.dataframe(
                sectors_df.style.format({'TVL': '${:,.0f}'}),
                use_container_width=True,
                height=400
            )
            
            csv = sectors_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download CSV - Setores",
                data=csv,
                file_name='setores.csv',
                mime='text/csv'
            )
        else:
            st.error("Não foi possível carregar os dados de setores.")
        
        st.markdown("---")
        st.subheader("💡 Painel de Insights")
        insights = generate_insights(tvl_df, stable_df, revenue_df, sectors_df, global_tvl_df)
        for i, insight in enumerate(insights, 1):
            st.markdown(f"**{i}.** {insight}")
    
    # Footer
    st.markdown("---")
    st.markdown(
        "<<div style='text-align: center; color: gray;'>Dados fornecidos pela DeFiLlama API | Dashboard construído com Streamlit</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
