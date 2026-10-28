import os
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine

# -------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Observatório de Violência contra a Mulher - SP",
    page_icon="⚖️",
    layout="wide",
)

# -------------------------------------------------------------------
# DEFINIÇÃO DOS CAMINHOS DOS ARQUIVOS LOCAIS
# -------------------------------------------------------------------
PATH_PROCESSED = os.path.join("data", "processed", "excel_externo")
PATH_RAW = os.path.join("data", "raw")

# Arquivos na pasta processed/excel_externo
FILE_VIOLENCIA_CSV = os.path.join(PATH_PROCESSED, "violencia_mulher_sp.csv")
FILE_SSP_XLSX = os.path.join(PATH_PROCESSED, "Dados_feminicidio_SSP.xlsx")

# Conexão com banco PostgreSQL (se disponível)
STRING_CONEXAO = "postgresql://postgres:suasenha@localhost:5432/meu_banco_dados"


# -------------------------------------------------------------------
# FUNÇÕES DE CARREGAMENTO DE DADOS COM TRATAMENTO DE ERRO
# -------------------------------------------------------------------
@st.cache_data
def carregar_dados_datajud():
    """Lê o arquivo CSV processado do DataJud."""
    path_csv = os.path.join("data", "processed", "excel_externo", "violencia_mulher_sp.csv")
    if os.path.exists(path_csv):
        return pd.read_csv(path_csv)
    
    # Fallback para o arquivo Excel em raw, se necessário
    path_excel = os.path.join("data", "raw", "ViolenciaDomestica_cnj_SP.xlsx")
    if os.path.exists(path_excel):
        return pd.read_excel(path_excel, engine="openpyxl")
        
    raise FileNotFoundError("Nenhum arquivo do DataJud foi encontrado em 'processed' ou 'raw'.")


@st.cache_data
def carregar_dados_ssp():
    """Tenta carregar os dados da SSP a partir da planilha Excel."""
    try:
        engine = create_engine(STRING_CONEXAO)
        return pd.read_sql("SELECT * FROM tb_ssp_violencia_mulher", engine)
    except Exception:
        if os.path.exists(FILE_SSP_XLSX):
            return pd.read_excel(FILE_SSP_XLSX)
        raise FileNotFoundError(f"Planilha da SSP não encontrada em: {FILE_SSP_XLSX}")


@st.cache_data
def carregar_dados_datasenado_tcmsp():
    """Carrega os arquivos CSV do DataSenado / TCMSP presentes na pasta data/raw/."""
    dfs = []
    
    # Procura arquivos do DataSenado ou TCMSP na pasta raw
    if os.path.exists(PATH_RAW):
        for arquivo in os.listdir(PATH_RAW):
            if ("datasenado" in arquivo.lower() or "tcmsp" in arquivo.lower()) and (arquivo.endswith(".csv") or arquivo.endswith(".xlsx")):
                caminho_completo = os.path.join(PATH_RAW, arquivo)
                if arquivo.endswith(".csv"):
                    df_temp = pd.read_csv(caminho_completo)
                else:
                    df_temp = pd.read_excel(caminho_completo)
                df_temp["fonte_arquivo"] = arquivo
                dfs.append(df_temp)
                
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    
    # Tentativa via PostgreSQL caso não ache arquivos em data/raw/
    try:
        engine = create_engine(STRING_CONEXAO)
        return pd.read_sql("SELECT * FROM tb_datasenado_tcmsp", engine)
    except Exception:
        raise FileNotFoundError("Nenhum arquivo do DataSenado/TCMSP encontrado na pasta 'data/raw/' nem no banco SQL.")


# -------------------------------------------------------------------
# CABEÇALHO DA APLICAÇÃO
# -------------------------------------------------------------------
st.title("⚖️ Observatório de Violência contra a Mulher (São Paulo)")
st.markdown("Esta plataforma integra e analisa dados sobre a violência contra a mulher no Estado de São Paulo.")

# Abas por fonte
aba_datajud, aba_ssp, aba_datasenado, aba_comparativo = st.tabs(
    [
        "🏛️ DataJud (CNJ / TJSP)",
        "📊 SSP-SP (Segurança Pública)",
        "📜 DataSenado & TCMSP",
        "📋 Visão Geral Integrada",
    ]
)

# ===================================================================
# ABA 1: DATAJUD
# ===================================================================
with aba_datajud:
    st.header("🏛️ Contencioso Judicial e Processos (DataJud / TJSP)")

    try:
        df_tj = carregar_dados_datajud()
        df_tj.columns = [c.lower() for c in df_tj.columns]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total de Registros / Processos", f"{len(df_tj):,}")

        if "regiao_comarca" in df_tj.columns:
            c2.metric("Comarcas Atendidas", df_tj["regiao_comarca"].nunique())
        elif "comarca" in df_tj.columns:
            c2.metric("Comarcas Atendidas", df_tj["comarca"].nunique())

        if "tipo_violencia" in df_tj.columns:
            c3.metric("Tipos de Violência", df_tj["tipo_violencia"].nunique())

        st.markdown("---")

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            col_comarca = "regiao_comarca" if "regiao_comarca" in df_tj.columns else ("comarca" if "comarca" in df_tj.columns else None)
            col_qtd = "quantidade_casos" if "quantidade_casos" in df_tj.columns else None

            if col_comarca and col_qtd:
                df_comarca = (
                    df_tj.groupby(col_comarca)[col_qtd]
                    .sum()
                    .reset_index()
                    .sort_values(by=col_qtd, ascending=False)
                    .head(10)
                )
                fig_comarca = px.bar(
                    df_comarca,
                    x=col_qtd,
                    y=col_comarca,
                    orientation="h",
                    title="Top 10 Comarcas em Volume de Processos",
                )
                st.plotly_chart(fig_comarca, use_container_width=True)
            else:
                st.info("Visualização gráfica indisponível para o formato atual das colunas.")

        with col_g2:
            st.subheader("Visualização da Tabela")
            st.dataframe(df_tj.head(100), use_container_width=True, height=400)

    except Exception as e:
        st.error(f"Erro na aba DataJud: {e}")

# ===================================================================
# ABA 2: SSP-SP
# ===================================================================
with aba_ssp:
    st.header("📊 Ocorrências Policiais e Perfil Sociodemográfico (SSP-SP)")

    try:
        df_ssp = carregar_dados_ssp()
        df_ssp.columns = [c.lower() for c in df_ssp.columns]

        m1, m2 = st.columns(2)
        m1.metric("Total de Registros (SSP)", f"{len(df_ssp):,}")

        col_idade = [c for c in df_ssp.columns if "idade" in c]
        if col_idade:
            col_id = col_idade[0]
            media_idade = pd.to_numeric(df_ssp[col_id], errors="coerce").mean()
            if not pd.isna(media_idade):
                m2.metric("Média de Idade das Vítimas", f"{media_idade:.1f} anos")

        st.markdown("---")
        col_ssp1, col_ssp2 = st.columns(2)

        with col_ssp1:
            if col_idade:
                fig_idade = px.histogram(
                    df_ssp,
                    x=col_idade[0],
                    nbins=15,
                    title="Distribuição por Idade",
                    color_discrete_sequence=["#e74c3c"],
                )
                st.plotly_chart(fig_idade, use_container_width=True)

        with col_ssp2:
            st.subheader("Base SSP-SP")
            st.dataframe(df_ssp.head(100), use_container_width=True, height=400)

    except Exception as e:
        st.error(f"Erro na aba SSP-SP: {e}")

# ===================================================================
# ABA 3: DATASENADO & TCMSP
# ===================================================================
with aba_datasenado:
    st.header("📜 Pesquisas de Percepção (DataSenado & TCMSP)")

    try:
        df_ds = carregar_dados_datasenado_tcmsp()
        st.success(f"Carregado com sucesso! Total de registros: {len(df_ds)}")
        st.dataframe(df_ds, use_container_width=True, height=400)
    except Exception as e:
        st.warning(f"Aviso DataSenado/TCMSP: {e}")

# ===================================================================
# ABA 4: VISÃO GERAL
# ===================================================================
with aba_comparativo:
    st.header("📋 Síntese Diagnóstica")
    st.success("Módulos de dados configurados para leitura automática das pastas 'processed' e 'raw'.")