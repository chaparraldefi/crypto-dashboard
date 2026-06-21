import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# Configuração inicial da página
st.set_page_config(page_title="Dashboard DeFi - DeFiLlama", layout="wide")

st.title("📊 Dashboard DeFi - Dados do DeFiLlama")


@st.cache_data(ttl=3600)
def get_protocols():
    url = "https://api.llama.fi/protocols"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=3600)
def get_global_tvl_chart():
    url = "https://api.llama.fi/v2/historicalChainTvl"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=3600)
def get_chain_tvl_chart(chain_slug):
    url = f"https://api.llama.fi/v2/historicalChainTvl/{chain_slug}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def process_global_tvl_chart(data):
    """Processa dados do histórico global de TVL com tratamento de erro robusto."""
    records = []
    for item in data:
        try:
            raw_timestamp = item.get("date")
            if raw_timestamp is None:
                continue
            # Converte explicitamente para int para evitar TypeError no fromtimestamp
            timestamp = int(raw_timestamp)
            dt = datetime.fromtimestamp(timestamp)
            records.append({
                "date": dt,
                "tvl": item.get("tvl")
            })
        except (TypeError, ValueError, OverflowError, OSError):
            # Ignora registros com timestamp inválido ou fora de alcance
            continue
    return pd.DataFrame(records)


def process_chain_tvl_chart(data):
    """Processa dados do histórico de TVL por chain."""
    records = []
    for item in data:
        try:
            timestamp = int(item.get("date"))
            dt = datetime.fromtimestamp(timestamp)
            records.append({
                "date": dt,
                "tvl": item.get("tvl")
            })
        except (TypeError, ValueError, OverflowError, OSError):
            continue
    return pd.DataFrame(records)


def main():
    try:
        protocols = get_protocols()
    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao buscar protocolos: {e}")
        return

    # Sidebar: filtros
    st.sidebar.header("Filtros")

    chains = sorted({p.get("chain", "Desconhecida") for p in protocols})
    selected_chain = st.sidebar.selectbox("Chain", ["Todas"] + chains)

    categories = sorted({p.get("category", "Desconhecida") for p in protocols})
    selected_category = st.sidebar.selectbox("Categoria", ["Todas"] + categories)

    min_tvl = st.sidebar.number_input("TVL mínima (USD)", min_value=0.0, value=0.0, step=1_000_000.0)

    # Filtragem
    filtered_protocols = []
    for p in protocols:
        tvl = p.get("tvl", 0) or 0
        chain_match = selected_chain == "Todas" or p.get("chain") == selected_chain
        category_match = selected_category == "Todas" or p.get("category") == selected_category
        tvl_match = tvl >= min_tvl
        if chain_match and category_match and tvl_match:
            filtered_protocols.append(p)

    st.subheader(f"Protocolos filtrados: {len(filtered_protocols)}")

    if filtered_protocols:
        df_protocols = pd.DataFrame([
            {
                "Nome": p.get("name"),
                "Chain": p.get("chain"),
                "Categoria": p.get("category"),
                "TVL (USD)": p.get("tvl", 0),
                "Mudança 1d (%)": p.get("change_1d", 0),
                "Mudança 7d (%)": p.get("change_7d", 0)
            }
            for p in filtered_protocols
        ])
        st.dataframe(df_protocols, use_container_width=True)
    else:
        st.info("Nenhum protocolo encontrado com os filtros selecionados.")

    # Gráfico global de TVL
    st.subheader("Histórico Global de TVL")
    try:
        global_tvl_data = get_global_tvl_chart()
        df_global_tvl = process_global_tvl_chart(global_tvl_data)

        if not df_global_tvl.empty:
            df_global_tvl = df_global_tvl.sort_values("date").reset_index(drop=True)
            st.line_chart(df_global_tvl.set_index("date")["tvl"])
        else:
            st.info("Nenhum dado histórico de TVL disponível.")
    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao buscar histórico global de TVL: {e}")
    except Exception as e:
        st.error(f"Erro inesperado ao processar histórico global de TVL: {e}")

    # Gráfico de TVL por chain
    st.subheader("Histórico de TVL por Chain")
    chain_slugs = sorted({p.get("chain", "").lower().replace(" ", "-") for p in protocols if p.get("chain")})
    selected_chain_slug = st.selectbox("Selecione a chain", chain_slugs)

    if selected_chain_slug:
        try:
            chain_tvl_data = get_chain_tvl_chart(selected_chain_slug)
            df_chain_tvl = process_chain_tvl_chart(chain_tvl_data)

            if not df_chain_tvl.empty:
                df_chain_tvl = df_chain_tvl.sort_values("date").reset_index(drop=True)
                st.line_chart(df_chain_tvl.set_index("date")["tvl"])
            else:
                st.info("Nenhum dado histórico de TVL para esta chain.")
        except requests.exceptions.RequestException as e:
            st.error(f"Erro ao buscar histórico de TVL da chain: {e}")
        except Exception as e:
            st.error(f"Erro inesperado ao processar histórico de TVL da chain: {e}")


if __name__ == "__main__":
    main()
