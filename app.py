import io
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ============================================================
# OBSERVATÓRIO DE VIOLÊNCIA CONTRA A MULHER - SÃO PAULO
# Bases CSV e Excel, incluindo SSP-SP
# ============================================================

st.set_page_config(
    page_title="Observatório de Violência contra a Mulher - SP",
    page_icon="⚖️",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent
PASTAS_DADOS = [
    BASE_DIR / "data" / "raw",
    BASE_DIR / "data" / "processed",
    BASE_DIR / "data" / "processed" / "excel_externo",
    BASE_DIR,  # permite também deixar o CSV ao lado do app.py
]
EXTENSOES = {".csv", ".xlsx", ".xls"}

st.title("⚖️ Observatório de Violência contra a Mulher — São Paulo")
st.caption(
    "Exploração de bases policiais, judiciais e de pesquisas. "
    "Os indicadores são calculados a partir dos arquivos efetivamente carregados."
)


def normalizar_texto(valor):
    texto = str(valor).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def normalizar_colunas(df):
    df = df.copy()
    novas = []
    usados = {}
    for col in df.columns:
        nome = " ".join(str(col).replace("\n", " ").replace("\r", " ").split())
        if not nome:
            nome = "coluna_sem_nome"
        usados[nome] = usados.get(nome, 0) + 1
        if usados[nome] > 1:
            nome = f"{nome}_{usados[nome]}"
        novas.append(nome)
    df.columns = novas
    return df


def ler_csv_seguro(caminho):
    erros = []
    for encoding in ["utf-8-sig", "cp1252", "latin1", "utf-8"]:
        for sep in [None, ";", ",", "\t", "|"]:
            try:
                kwargs = {
                    "filepath_or_buffer": caminho,
                    "encoding": encoding,
                    "sep": sep,
                    "on_bad_lines": "error",
                    "low_memory": False,
                }
                if sep is None:
                    kwargs["engine"] = "python"
                df = pd.read_csv(**kwargs)
                if len(df.columns) > 1 or sep == "|":
                    return normalizar_colunas(df)
            except Exception as exc:
                erros.append(str(exc))
    raise ValueError(
        f"Não foi possível ler {caminho.name}. "
        f"Último erro: {erros[-1] if erros else 'erro desconhecido'}"
    )


def identificar_fonte(nome):
    n = normalizar_texto(nome)
    if any(x in n for x in ["datasenado", "data_senado", "senado"]):
        return "DataSenado"
    if any(x in n for x in ["tcmsp", "tcm_sp", "tribunal_de_contas"]):
        return "TCMSP"
    if any(x in n for x in ["datajud", "cnj", "violenciadomestica_cnj"]):
        return "DataJud / CNJ"
    if any(x in n for x in [
        "ssp", "seguranca_publica", "seguranca", "feminicidio",
        "feminicidios", "homicidio_mulheres", "homicidios_mulheres"
    ]):
        return "SSP-SP / Segurança Pública"
    return "Outras bases / origem a confirmar"


def descobrir_arquivos():
    achados = []
    vistos = set()
    for pasta in PASTAS_DADOS:
        if not pasta.exists():
            continue
        for arquivo in pasta.rglob("*"):
            if not arquivo.is_file() or arquivo.suffix.lower() not in EXTENSOES:
                continue
            if arquivo.name.startswith("~$") or arquivo.name.startswith("."):
                continue
            # Evita reler cópias internas da pasta de saída.
            try:
                resolvido = arquivo.resolve()
            except Exception:
                resolvido = arquivo
            if resolvido in vistos:
                continue
            vistos.add(resolvido)
            achados.append(arquivo)
    return sorted(achados, key=lambda p: str(p).lower())


def ler_arquivo(arquivo):
    tabelas = []
    if arquivo.suffix.lower() == ".csv":
        df = ler_csv_seguro(arquivo)
        tabelas.append({
            "nome": arquivo.stem, "arquivo": arquivo.name, "aba": "CSV",
            "caminho": str(arquivo), "fonte": identificar_fonte(arquivo.name),
            "dados": df
        })
    else:
        engine = "openpyxl" if arquivo.suffix.lower() == ".xlsx" else "xlrd"
        abas = pd.read_excel(arquivo, sheet_name=None, engine=engine)
        for aba, df in abas.items():
            tabelas.append({
                "nome": f"{arquivo.stem} - {aba}", "arquivo": arquivo.name,
                "aba": str(aba), "caminho": str(arquivo),
                "fonte": identificar_fonte(arquivo.name),
                "dados": normalizar_colunas(df)
            })
    return tabelas


@st.cache_data(show_spinner="Carregando as bases...")
def carregar_bases():
    tabelas, erros = [], []
    for arquivo in descobrir_arquivos():
        try:
            tabelas.extend(ler_arquivo(arquivo))
        except Exception as exc:
            erros.append({"Arquivo": arquivo.name, "Erro": str(exc)})
    return tabelas, erros


def converter_numero_br(serie):
    """Converte números no formato brasileiro, como 2.884, para número."""
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce")
    s = serie.astype("string").str.strip()
    s = s.replace({
        "": pd.NA, "-": pd.NA, "—": pd.NA, "NA": pd.NA,
        "N/A": pd.NA, "null": pd.NA, "None": pd.NA
    })
    # Para as colunas numéricas brasileiras da SSP: ponto é milhar.
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def preparar_ssp(df):
    """Prepara a base SSP sem alterar o arquivo original."""
    df = df.copy()
    mapa = {normalizar_texto(c): c for c in df.columns}

    # Remove linhas de cabeçalho repetidas, se existirem.
    if "Ano" in df.columns:
        df = df[df["Ano"].astype(str).str.strip().str.lower() != "ano"].copy()

    # Converte colunas de contagem conhecidas.
    for col in ["Capital", "Demacro", "Interior", "Total"]:
        if col in df.columns:
            df[col] = converter_numero_br(df[col])

    if "Ano" in df.columns:
        df["Ano"] = pd.to_numeric(df["Ano"], errors="coerce").astype("Int64")

    if "Mês" in df.columns:
        df["Mês"] = df["Mês"].astype("string").str.strip()

    if "Tipo de Ocorrência" in df.columns:
        df["Tipo de Ocorrência"] = (
            df["Tipo de Ocorrência"].astype("string").str.strip()
        )

    return df


def exportar_csv(df):
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


def exportar_excel(df, nome_aba="Dados"):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=nome_aba[:31])
    buffer.seek(0)
    return buffer.getvalue()


def tabela_completa(df, chave):
    st.caption(f"{len(df):,} registros | {len(df.columns):,} colunas")
    termo = st.text_input(
        "Pesquisar em todas as colunas",
        key=f"pesquisa_{chave}",
        placeholder="Digite um ano, município, ocorrência ou valor..."
    )
    exibicao = df.copy()
    if termo.strip():
        texto = termo.casefold()
        mascara = exibicao.astype("string").apply(
            lambda c: c.str.casefold().str.contains(texto, regex=False, na=False)
        )
        exibicao = exibicao[mascara.any(axis=1)]
    st.write(f"Registros após pesquisa: {len(exibicao):,}")
    st.dataframe(exibicao, use_container_width=True, height=560)
    c1, c2 = st.columns(2)
    c1.download_button(
        "⬇️ Baixar CSV completo/exibido",
        data=exportar_csv(exibicao),
        file_name=f"{chave}.csv",
        mime="text/csv",
        key=f"baixar_csv_{chave}"
    )
    try:
        excel = exportar_excel(exibicao)
        c2.download_button(
            "⬇️ Baixar Excel completo/exibido",
            data=excel,
            file_name=f"{chave}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"baixar_excel_{chave}"
        )
    except Exception as exc:
        st.warning(f"Não foi possível gerar Excel: {exc}")


def analise_geral(df, chave):
    st.subheader("Indicadores de qualidade")
    a, b, c, d = st.columns(4)
    a.metric("Registros", f"{len(df):,}")
    b.metric("Colunas", f"{len(df.columns):,}")
    c.metric("Células vazias", f"{int(df.isna().sum().sum()):,}")
    d.metric("Linhas duplicadas", f"{int(df.duplicated().sum()):,}")

    estrutura = pd.DataFrame({
        "Coluna": df.columns.astype(str),
        "Tipo": [str(x) for x in df.dtypes],
        "Não nulos": [int(df[c].notna().sum()) for c in df.columns],
        "Nulos": [int(df[c].isna().sum()) for c in df.columns],
        "Valores distintos": [int(df[c].nunique(dropna=True)) for c in df.columns]
    })
    with st.expander("Ver estrutura e tipos de dados"):
        st.dataframe(estrutura, use_container_width=True)

    nulos = pd.DataFrame({
        "Coluna": df.columns.astype(str),
        "Quantidade nula": [int(df[c].isna().sum()) for c in df.columns],
        "Percentual nulo (%)": [
            round(float(df[c].isna().mean() * 100), 2) for c in df.columns
        ]
    }).sort_values("Quantidade nula", ascending=False)
    with st.expander("Ver análise de valores ausentes"):
        st.dataframe(nulos, use_container_width=True)

    numericas = df.select_dtypes(include=np.number)
    if not numericas.empty:
        with st.expander("Ver estatísticas descritivas numéricas"):
            st.dataframe(numericas.describe().T, use_container_width=True)
        if len(numericas.columns) >= 2:
            with st.expander("Ver matriz de correlação"):
                fig = px.imshow(
                    numericas.corr(), text_auto=".2f", aspect="auto",
                    title="Correlação entre variáveis numéricas",
                    color_continuous_scale="RdBu_r", zmin=-1, zmax=1
                )
                st.plotly_chart(fig, use_container_width=True)

    categoricas = [
        c for c in df.columns
        if df[c].dtype == "object" or pd.api.types.is_string_dtype(df[c])
    ]
    if categoricas:
        with st.expander("Analisar distribuição de uma coluna categórica"):
            coluna = st.selectbox("Coluna categórica", categoricas, key=f"cat_{chave}")
            contagem = (
                df[coluna].fillna("(Sem informação)").astype(str)
                .value_counts().head(25).rename_axis("Categoria")
                .reset_index(name="Quantidade")
            )
            fig = px.bar(
                contagem, x="Quantidade", y="Categoria", orientation="h",
                title=f"Distribuição de {coluna}", text="Quantidade"
            )
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(contagem, use_container_width=True)


tabelas, erros = carregar_bases()
if st.sidebar.button("🔄 Recarregar arquivos"):
    carregar_bases.clear()
    st.rerun()

st.sidebar.metric("Tabelas carregadas", len(tabelas))
st.sidebar.metric("Arquivos com erro", len(erros))

if not tabelas:
    st.error("Nenhum arquivo CSV ou Excel foi carregado.")
    st.write("Coloque os arquivos em data/raw, data/processed ou ao lado do app.py.")
    if erros:
        st.dataframe(pd.DataFrame(erros), use_container_width=True)
    st.stop()

fontes = sorted(set(t["fonte"] for t in tabelas))
aba_inicio, aba_ssp, aba_judicial, aba_pesquisas, aba_outras, aba_diag = st.tabs([
    "🏠 Visão geral", "🚔 SSP-SP", "⚖️ DataJud/CNJ",
    "📜 DataSenado/TCMSP", "📂 Outras bases", "🔬 Diagnóstico"
])

# ------------------------------------------------------------
# VISÃO GERAL
# ------------------------------------------------------------
with aba_inicio:
    st.header("Inventário de dados")
    inventario = pd.DataFrame([{
        "Tabela": t["nome"], "Arquivo": t["arquivo"], "Aba": t["aba"],
        "Fonte estimada": t["fonte"], "Registros": len(t["dados"]),
        "Colunas": len(t["dados"].columns), "Caminho": t["caminho"]
    } for t in tabelas])
    c1, c2, c3 = st.columns(3)
    c1.metric("Tabelas", f"{len(tabelas):,}")
    c2.metric("Registros somados", f"{sum(len(t['dados']) for t in tabelas):,}")
    c3.metric("Fontes identificadas", f"{len(fontes):,}")
    st.warning(
        "A soma de registros de arquivos diferentes não equivale necessariamente "
        "ao número de ocorrências únicas. Fontes e unidades de análise são distintas."
    )
    st.dataframe(inventario, use_container_width=True)
    fig = px.bar(
        inventario.groupby("Fonte estimada", as_index=False)["Registros"].sum(),
        x="Fonte estimada", y="Registros", color="Fonte estimada",
        title="Registros por fonte estimada", text="Registros"
    )
    st.plotly_chart(fig, use_container_width=True)

    indice = st.selectbox(
        "Consultar uma tabela",
        range(len(tabelas)),
        format_func=lambda i: f"{tabelas[i]['nome']} ({len(tabelas[i]['dados']):,} registros)",
        key="geral_tabela"
    )
    tabela_completa(tabelas[indice]["dados"], f"geral_{indice}")

# ------------------------------------------------------------
# SSP-SP
# ------------------------------------------------------------
with aba_ssp:
    st.header("🚔 SSP-SP — Estatísticas de Segurança Pública")
    lista_ssp = [t for t in tabelas if t["fonte"] == "SSP-SP / Segurança Pública"]

    if not lista_ssp:
        st.warning(
            "Nenhum arquivo foi classificado como SSP-SP pelo nome. "
            "Confira o nome do arquivo e a aba Outras Bases."
        )
    else:
        st.dataframe(pd.DataFrame([{
            "Arquivo": t["arquivo"], "Aba": t["aba"],
            "Registros": len(t["dados"]), "Colunas": len(t["dados"].columns)
        } for t in lista_ssp]), use_container_width=True)

        i = st.selectbox(
            "Escolha a base SSP-SP",
            range(len(lista_ssp)),
            format_func=lambda j: f"{lista_ssp[j]['nome']} ({len(lista_ssp[j]['dados']):,} registros)",
            key="ssp_escolha"
        )
        tabela = lista_ssp[i]
        df_original = tabela["dados"].copy()
        df = preparar_ssp(df_original)

        st.caption(f"Arquivo: {tabela['arquivo']} | Aba: {tabela['aba']}")

        # KPIs específicos quando a tabela tem as colunas esperadas.
        if {"Ano", "Tipo de Ocorrência", "Total"}.issubset(df.columns):
            feminicidio = df[
                df["Tipo de Ocorrência"].astype(str).str.contains("FEMINICÍDIO", case=False, na=False)
                & ~df["Tipo de Ocorrência"].astype(str).str.contains("exclui", case=False, na=False)
            ]
            total_fem = feminicidio["Total"].sum(min_count=1)
            anos = df["Ano"].dropna()
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Registros da tabela", f"{len(df):,}")
            k2.metric("Ano inicial", str(int(anos.min())) if not anos.empty else "N/D")
            k3.metric("Ano final", str(int(anos.max())) if not anos.empty else "N/D")
            k4.metric(
                "Total acumulado de feminicídios",
                f"{total_fem:,.0f}" if pd.notna(total_fem) else "N/D"
            )

            st.subheader("📈 Evolução anual por tipo de ocorrência")
            tipos = sorted(df["Tipo de Ocorrência"].dropna().astype(str).unique())
            padrao_fem = next((x for x in tipos if normalizar_texto(x) == "feminicidio"), None)
            tipo_default = [padrao_fem] if padrao_fem else tipos[:1]
            tipos_selecionados = st.multiselect(
                "Selecione os tipos de ocorrência",
                tipos, default=tipo_default, key="ssp_tipos_ano"
            )
            if tipos_selecionados:
                anual = df[df["Tipo de Ocorrência"].isin(tipos_selecionados)].groupby(
                    ["Ano", "Tipo de Ocorrência"], as_index=False
                )["Total"].sum(min_count=1)
                fig_anual = px.line(
                    anual, x="Ano", y="Total", color="Tipo de Ocorrência",
                    markers=True, title="Evolução anual dos registros"
                )
                st.plotly_chart(fig_anual, use_container_width=True)
                st.dataframe(anual, use_container_width=True)

            st.subheader("🗺️ Distribuição territorial")
            regioes = [c for c in ["Capital", "Demacro", "Interior"] if c in df.columns]
            if regioes:
                tipo_territorio = st.selectbox(
                    "Tipo de ocorrência para comparação territorial",
                    tipos, index=tipos.index(padrao_fem) if padrao_fem in tipos else 0,
                    key="ssp_tipo_territorio"
                )
                df_reg = df[df["Tipo de Ocorrência"] == tipo_territorio]
                territorial = df_reg[regioes].sum(min_count=1).rename_axis("Região").reset_index(name="Registros")
                fig_reg = px.bar(
                    territorial, x="Região", y="Registros", color="Região",
                    text="Registros", title=f"Registros por região — {tipo_territorio}"
                )
                st.plotly_chart(fig_reg, use_container_width=True)
                st.dataframe(territorial, use_container_width=True)

            if "Mês" in df.columns:
                st.subheader("📅 Distribuição mensal")
                ordem_meses = [
                    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
                ]
                tipo_mes = st.selectbox(
                    "Tipo de ocorrência para análise mensal",
                    tipos, index=tipos.index(padrao_fem) if padrao_fem in tipos else 0,
                    key="ssp_tipo_mes"
                )
                df_mes = df[df["Tipo de Ocorrência"] == tipo_mes].copy()
                mensal = df_mes.groupby("Mês", as_index=False)["Total"].sum(min_count=1)
                mensal["ordem"] = mensal["Mês"].map({m: n for n, m in enumerate(ordem_meses)})
                mensal = mensal.sort_values("ordem")
                fig_mes = px.bar(
                    mensal, x="Mês", y="Total", title=f"Distribuição mensal — {tipo_mes}",
                    text="Total"
                )
                st.plotly_chart(fig_mes, use_container_width=True)
                st.dataframe(mensal.drop(columns=["ordem"]), use_container_width=True)

            with st.expander("📊 Análise de qualidade e estatística da base SSP"):
                analise_geral(df, f"ssp_analise_{i}")

        else:
            st.info(
                "A tabela não possui todas as colunas esperadas para as análises específicas "
                "(Ano, Tipo de Ocorrência e Total). A tabela completa continua disponível."
            )
            with st.expander("Análise geral da tabela"):
                analise_geral(df, f"ssp_analise_generica_{i}")

        st.subheader("📋 Todos os dados da tabela SSP-SP")
        st.caption("A grade apresenta todos os registros. Use a pesquisa ou baixe a base completa.")
        tabela_completa(df_original, f"ssp_todos_{i}")

        with st.expander("Consolidar todas as tabelas classificadas como SSP-SP"):
            st.warning(
                "A consolidação pode combinar períodos ou estruturas diferentes. "
                "Verifique a compatibilidade antes de somar os resultados."
            )
            if st.button("Gerar consolidação SSP-SP", key="ssp_consolidar"):
                partes = []
                for item in lista_ssp:
                    parte = item["dados"].copy()
                    parte["_arquivo_origem"] = item["arquivo"]
                    parte["_aba_origem"] = item["aba"]
                    partes.append(parte)
                consolidado = pd.concat(partes, ignore_index=True, sort=False)
                st.dataframe(consolidado, use_container_width=True, height=500)
                st.download_button(
                    "Baixar consolidação SSP-SP",
                    data=exportar_csv(consolidado),
                    file_name="ssp_sp_consolidado.csv",
                    mime="text/csv",
                    key="ssp_consolidado_download"
                )

# ------------------------------------------------------------
# DATAJUD
# ------------------------------------------------------------
with aba_judicial:
    st.header("⚖️ DataJud / CNJ")
    lista = [t for t in tabelas if t["fonte"] == "DataJud / CNJ"]
    if not lista:
        st.info("Nenhuma base DataJud/CNJ foi identificada pelo nome.")
    else:
        i = st.selectbox(
            "Selecione uma tabela judicial", range(len(lista)),
            format_func=lambda j: lista[j]["nome"], key="jud_escolha"
        )
        tabela_completa(lista[i]["dados"], f"judicial_{i}")
        with st.expander("Análise da base"):
            analise_geral(lista[i]["dados"], f"judicial_analise_{i}")

# ------------------------------------------------------------
# DATASENADO / TCMSP
# ------------------------------------------------------------
with aba_pesquisas:
    st.header("📜 DataSenado / TCMSP")
    lista = [t for t in tabelas if t["fonte"] in ["DataSenado", "TCMSP"]]
    if not lista:
        st.info("Nenhuma base DataSenado/TCMSP foi identificada pelo nome.")
    else:
        i = st.selectbox(
            "Selecione uma tabela", range(len(lista)),
            format_func=lambda j: f"{lista[j]['nome']} — {lista[j]['fonte']}",
            key="pesquisa_escolha"
        )
        tabela_completa(lista[i]["dados"], f"pesquisa_{i}")
        with st.expander("Análise da base"):
            analise_geral(lista[i]["dados"], f"pesquisa_analise_{i}")

# ------------------------------------------------------------
# OUTRAS BASES
# ------------------------------------------------------------
with aba_outras:
    st.header("📂 Outras bases / origem a confirmar")
    lista = [t for t in tabelas if t["fonte"] == "Outras bases / origem a confirmar"]
    if not lista:
        st.success("Nenhuma outra base identificada.")
    else:
        i = st.selectbox(
            "Selecione uma tabela", range(len(lista)),
            format_func=lambda j: f"{lista[j]['nome']} — {lista[j]['arquivo']}",
            key="outras_escolha"
        )
        tabela_completa(lista[i]["dados"], f"outras_{i}")
        with st.expander("Análise da base"):
            analise_geral(lista[i]["dados"], f"outras_analise_{i}")

# ------------------------------------------------------------
# DIAGNÓSTICO
# ------------------------------------------------------------
with aba_diag:
    st.header("🔬 Diagnóstico de arquivos e qualidade")
    inventario = pd.DataFrame([{
        "Tabela": t["nome"], "Arquivo": t["arquivo"], "Fonte estimada": t["fonte"],
        "Registros": len(t["dados"]), "Colunas": len(t["dados"].columns),
        "Valores nulos": int(t["dados"].isna().sum().sum()),
        "Linhas duplicadas": int(t["dados"].duplicated().sum()),
        "Caminho": t["caminho"]
    } for t in tabelas])
    st.dataframe(inventario, use_container_width=True)
    st.download_button(
        "Baixar inventário de bases",
        data=exportar_csv(inventario),
        file_name="inventario_bases.csv",
        mime="text/csv",
        key="diag_inventario"
    )
    st.subheader("Arquivos com erro")
    if erros:
        st.dataframe(pd.DataFrame(erros), use_container_width=True)
    else:
        st.success("Nenhum erro de leitura foi identificado.")
    st.subheader("Inventário de colunas")
    colunas = []
    for t in tabelas:
        for c in t["dados"].columns:
            colunas.append({
                "Tabela": t["nome"], "Arquivo": t["arquivo"],
                "Fonte estimada": t["fonte"], "Coluna": str(c),
                "Tipo de dado": str(t["dados"][c].dtype)
            })
    df_colunas = pd.DataFrame(colunas)
    st.dataframe(df_colunas, use_container_width=True)
    st.download_button(
        "Baixar inventário de colunas",
        data=exportar_csv(df_colunas),
        file_name="inventario_colunas.csv",
        mime="text/csv",
        key="diag_colunas"
    )

st.markdown("---")
st.caption(
    "Observatório de Violência contra a Mulher — São Paulo. "
    "A classificação da fonte é estimada pelo nome do arquivo e deve ser validada. "
    "Resultados dependem da qualidade, cobertura e documentação das bases."
)
