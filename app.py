import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine

# -------------------------------------------------------------------
# CONFIGURAÇÃO DE PÁGINA
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Painel Integrado: Violência contra a Mulher - SP",
    page_icon="📊",
    layout="wide",
)

# -------------------------------------------------------------------
# CONEXÃO COM O POSTGRESQL E CACHE DE DADOS
# -------------------------------------------------------------------
string_conexao = "mysql+pymysql://root:bru1520*@localhost:3306/meu_banco_dados"
engine = create_engine(string_conexao)


@st.cache_data
def carregar_dados_datajud():
    # Lê o arquivo CSV gerado pelo seu extrator
    return pd.read_csv("data/processed/violencia_mulher_sp.csv")

@st.cache_data
def carregar_dados_ssp():
    # Lê a planilha Excel da SSP que corrigimos no passo anterior
    return pd.read_excel("data/processed/excel_externo/Dados_feminicidio_SSP.xlsx")


# -------------------------------------------------------------------
# CABEÇALHO DA LANDING PAGE
# -------------------------------------------------------------------
st.title("⚖️ Observatório de Violência contra a Mulher (São Paulo)")
st.markdown("""
Esta plataforma reúne e analisa dados provenientes de duas origens complementares:
1. **DataJud (CNJ / TJSP):** Dados sobre o volume de processos judiciais e comarcas.
2. **SSP-SP & Pesquisa de Campo (Excel):** Perfil sociodemográfico (idade, escolaridade e município).
""")

st.divider()

# -------------------------------------------------------------------
# ORGANIZAÇÃO EM BLOCOS/ABAS NO MESMO NAVEGADOR
# -------------------------------------------------------------------
aba_datajud, aba_ssp, aba_comparativo = st.tabs(
    [
        "🏛️ Processos Judiciais (DataJud / TJSP)",
        "📊 Perfil Sociodemográfico (SSP-SP / Excel)",
        "📋 Visão Geral Integrada",
    ]
)

# ===================================================================
# BLOCO 1: ANÁLISE DO DATAJUD (API)
# ===================================================================
with aba_datajud:
    st.header("Análise do Contencioso Judicial (DataJud)")

    try:
        df_tj = carregar_dados_datajud()

        # Métricas em destaque
        c1, c2, c3 = st.columns(3)
        c1.metric("Total de Processos Mapeados", df_tj["quantidade_casos"].sum())
        c2.metric("Comarcas Atendidas", df_tj["regiao_comarca"].nunique())
        c3.metric(
            "Tipos de Violência Catalogados", df_tj["tipo_violencia"].nunique()
        )

        st.markdown("---")

        # Gráfico por Comarca/Região
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            df_comarca = (
                df_tj.groupby("regiao_comarca")["quantidade_casos"]
                .sum()
                .reset_index()
                .sort_values(by="quantidade_casos", ascending=False)
                .head(10)
            )
            fig_comarca = px.bar(
                df_comarca,
                x="quantidade_casos",
                y="regiao_comarca",
                orientation="h",
                title="Top 10 Comarcas em Volume de Processos",
            )
            st.plotly_chart(fig_comarca, use_container_width=True)

        with col_g2:
            st.dataframe(df_tj, use_container_width=True, height=400)

    except Exception as e:
        st.warning(
            f"Não foi possível carregar os dados do DataJud. Verifique a conexão com o banco. Erro: {e}"
        )

# ===================================================================
# BLOCO 2: ANÁLISE DA SSP-SP (EXCEL)
# ===================================================================
with aba_ssp:
    st.header("Perfil Sociodemográfico das Vítimas (SSP-SP / Planilhas)")

    try:
        df_ssp = carregar_dados_ssp()

        m1, m2 = st.columns(2)
        m1.metric("Registros em Planilha", len(df_ssp))
        if "idade" in df_ssp.columns:
            m2.metric("Média de Idade", f"{df_ssp['idade'].mean():.1f} anos")

        st.markdown("---")

        col_ssp1, col_ssp2 = st.columns(2)

        # Gráfico por Idade (se houver a coluna)
        with col_ssp1:
            if "idade" in df_ssp.columns:
                fig_idade = px.histogram(
                    df_ssp,
                    x="idade",
                    nbins=12,
                    title="Distribuição por Faixa Etária",
                    color_discrete_sequence=["#e74c3c"],
                )
                st.plotly_chart(fig_idade, use_container_width=True)

        # Gráfico por Escolaridade (se houver a coluna)
        with col_ssp2:
            if "escolaridade" in df_ssp.columns:
                df_esc = df_ssp["escolaridade"].value_counts().reset_index()
                fig_esc = px.bar(
                    df_esc,
                    x="escolaridade",
                    y="count",
                    title="Ocorrências por Escolaridade",
                    color_discrete_sequence=["#3498db"],
                )
                st.plotly_chart(fig_esc, use_container_width=True)

    except Exception as e:
        st.info(
            f"Carregue os dados da SSP no banco de dados para ativar este bloco. Mensagem: {e}"
        )

# ===================================================================
# BLOCO 3: RELATÓRIO E RESUMO COMBINADO
# ===================================================================
with aba_comparativo:
    st.header("Resumo Executivo do Estudo")
    st.markdown("""
    * **Fonte Judiciária (DataJud):** Utilizada para dimensionar a resposta das Varas e Juizados de Violência Doméstica.
    * **Fonte Policial e Demográfica (SSP-SP/DataSenado):** Utilizada para compreender os fatores socioeconômicos e o perfil etário das pessoas atingidas.
    """)