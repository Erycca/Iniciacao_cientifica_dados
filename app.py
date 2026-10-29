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

# ============================================================
# FUNÇÕES PARA DIAGNÓSTICOS SOCIODEMOGRÁFICOS E TERRITORIAIS
# ============================================================

def localizar_coluna(df, termos):
    """Localiza colunas por nomes equivalentes, mesmo com acentos."""
    for coluna in df.columns:
        nome = normalizar_texto(coluna).replace("_", " ")
        if any(termo in nome for termo in termos):
            return coluna
    return None


def exibir_distribuicao(df, coluna, titulo, chave):
    """Exibe distribuição de uma variável categórica."""
    dados = df[coluna].dropna()

    if dados.empty:
        st.info(f"Não há dados disponíveis para {titulo}.")
        return

    contagem = (
        dados.astype(str)
        .value_counts()
        .rename_axis("Categoria")
        .reset_index(name="Quantidade")
    )
    contagem["Percentual (%)"] = (
        contagem["Quantidade"] / contagem["Quantidade"].sum() * 100
    ).round(2)

    fig = px.bar(
        contagem.sort_values("Quantidade"),
        x="Quantidade",
        y="Categoria",
        orientation="h",
        text="Quantidade",
        title=titulo
    )
    st.plotly_chart(fig, use_container_width=True, key=chave)
    st.dataframe(contagem, use_container_width=True)


def diagnostico_sociodemografico(tabelas):
    st.subheader("Perfil sociodemográfico")

    candidatas = []
    for i, tabela in enumerate(tabelas):
        df = tabela["dados"]
        colunas = {
            "idade": localizar_coluna(df, ["idade", "faixa etaria"]),
            "raca": localizar_coluna(df, ["raca", "cor"]),
            "escolaridade": localizar_coluna(df, ["escolaridade", "instrucao", "educacao"]),
            "classe": localizar_coluna(df, ["classe social", "renda", "faixa salarial", "rendimento"])
        }
        if any(colunas.values()):
            candidatas.append((i, tabela, colunas))

    if not candidatas:
        st.warning(
            "Não foram encontradas colunas de idade, raça/cor, escolaridade "
            "ou renda nas bases carregadas. Inclua uma planilha com essas variáveis."
        )
        return

    escolha = st.selectbox(
        "Selecione a base sociodemográfica",
        range(len(candidatas)),
        format_func=lambda x: candidatas[x][1]["nome"],
        key="socio_base"
    )

    _, tabela, colunas = candidatas[escolha]
    df = tabela["dados"].copy()

    st.caption(f"Fonte: {tabela['arquivo']} | Registros: {len(df):,}")

    disponiveis = [nome for nome, coluna in colunas.items() if coluna]
    st.write("Variáveis encontradas:", ", ".join(disponiveis))

    c1, c2 = st.columns(2)

    with c1:
        if colunas["idade"]:
            coluna = colunas["idade"]
            idade = converter_numero_br(df[coluna]).dropna()
            if not idade.empty:
                faixas = pd.cut(
                    idade,
                    bins=[0, 17, 24, 34, 44, 59, 120],
                    labels=[
                        "Até 17 anos", "18 a 24 anos", "25 a 34 anos",
                        "35 a 44 anos", "45 a 59 anos", "60 anos ou mais"
                    ],
                    include_lowest=True
                )
                faixa_df = faixas.value_counts().sort_index().reset_index()
                faixa_df.columns = ["Faixa etária", "Quantidade"]
                fig = px.bar(
                    faixa_df, x="Faixa etária", y="Quantidade",
                    text="Quantidade", title="Distribuição por faixa etária"
                )
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(faixa_df, use_container_width=True)
            else:
                exibir_distribuicao(df, coluna, "Faixa etária registrada", "idade_cat")

    with c2:
        if colunas["raca"]:
            exibir_distribuicao(
                df, colunas["raca"], "Distribuição por cor/raça", "raca_grafico"
            )

    c3, c4 = st.columns(2)

    with c3:
        if colunas["escolaridade"]:
            exibir_distribuicao(
                df, colunas["escolaridade"],
                "Distribuição por escolaridade", "escolaridade_grafico"
            )

    with c4:
        if colunas["classe"]:
            exibir_distribuicao(
                df, colunas["classe"],
                "Distribuição por renda ou classe social", "classe_grafico"
            )

    st.info(
        "Os percentuais representam a distribuição dos registros desta base. "
        "Não devem ser interpretados como perfil de todas as vítimas do Estado "
        "sem amostragem representativa e metodologia compatível."
    )


def diagnostico_institucional(tabelas):
    st.subheader("Identificação de gaps e deficiências institucionais")

    st.markdown(
        "Cruze uma base de ocorrências com uma base de serviços de proteção. "
        "As duas bases precisam possuir uma coluna territorial compatível, "
        "preferencialmente município ou código IBGE."
    )

    opcoes = [
        i for i, t in enumerate(tabelas)
        if localizar_coluna(t["dados"], ["municipio", "município", "cidade"])
        or localizar_coluna(t["dados"], ["regiao", "comarca"])
    ]

    if len(opcoes) < 2:
        st.warning(
            "Para realizar o cruzamento, carregue pelo menos duas bases com "
            "uma coluna territorial compatível: uma de ocorrências e outra "
            "de instituições de proteção. A base SSP atual possui Capital, "
            "Demacro e Interior, mas não identifica cada município."
        )
        return

    nomes = {
        i: tabelas[i]["nome"] for i in opcoes
    }

    crime_id = st.selectbox(
        "Base de ocorrências",
        opcoes,
        format_func=lambda i: nomes[i],
        key="gap_crimes"
    )

    servico_opcoes = [i for i in opcoes if i != crime_id]

    servico_id = st.selectbox(
        "Base de instituições/serviços",
        servico_opcoes,
        format_func=lambda i: nomes[i],
        key="gap_servicos"
    )

    crimes = tabelas[crime_id]["dados"].copy()
    servicos = tabelas[servico_id]["dados"].copy()

    col_crime = localizar_coluna(crimes, ["municipio", "cidade", "regiao", "comarca"])
    col_servico = localizar_coluna(servicos, ["municipio", "cidade", "regiao", "comarca"])

    if not col_crime or not col_servico:
        st.warning("Não foi possível identificar as colunas territoriais.")
        return

    col_quantidade = localizar_coluna(
        crimes, ["quantidade_casos", "total", "ocorrencias", "casos", "registros"]
    )

    if not col_quantidade:
        st.warning("Não foi encontrada uma coluna numérica de ocorrências.")
        return

    quantidade = converter_numero_br(crimes[col_quantidade])
    crimes["_territorio"] = (
        crimes[col_crime].astype("string").str.strip().str.upper()
    )
    crimes["_ocorrencias"] = quantidade

    servicos["_territorio"] = (
        servicos[col_servico].astype("string").str.strip().str.upper()
    )

    ocorrencias = (
        crimes.groupby("_territorio", as_index=False)["_ocorrencias"]
        .sum()
    )

    tipo_servico = localizar_coluna(
        servicos, ["tipo de unidade", "tipo de servico", "instituicao", "equipamento", "servico"]
    )

    if tipo_servico:
        resumo_servicos = (
            servicos.groupby("_territorio")[tipo_servico]
            .nunique()
            .reset_index(name="Quantidade de tipos de serviços")
        )
    else:
        resumo_servicos = (
            servicos.groupby("_territorio")
            .size()
            .reset_index(name="Quantidade de serviços")
        )

    cruzamento = ocorrencias.merge(
        resumo_servicos, on="_territorio", how="outer"
    )

    cruzamento = cruzamento.rename(columns={"_territorio": "Território"})
    cruzamento["Ocorrências"] = cruzamento["_ocorrencias"].fillna(0)
    cruzamento = cruzamento.drop(columns=["_ocorrencias"])

    coluna_servicos = (
        "Quantidade de tipos de serviços"
        if "Quantidade de tipos de serviços" in cruzamento.columns
        else "Quantidade de serviços"
    )

    cruzamento[coluna_servicos] = cruzamento[coluna_servicos].fillna(0)

    fig = px.scatter(
        cruzamento,
        x=coluna_servicos,
        y="Ocorrências",
        text="Território",
        size="Ocorrências",
        title="Ocorrências registradas versus oferta de serviços"
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(cruzamento, use_container_width=True)

    st.download_button(
        "Baixar cruzamento institucional",
        data=exportar_csv(cruzamento),
        file_name="diagnostico_gaps_institucionais.csv",
        mime="text/csv",
        key="baixar_gaps"
    )

    st.caption(
        "Este cruzamento é exploratório. A quantidade de unidades não mede, "
        "isoladamente, cobertura, capacidade de atendimento, distância ou qualidade "
        "do serviço. Também não constitui medida de impunidade."
    )


def diagnostico_vulnerabilidade(tabelas):
    st.subheader("Índice exploratório de vulnerabilidade")

    opcoes = [
        i for i, t in enumerate(tabelas)
        if len(t["dados"].select_dtypes(include=np.number).columns) >= 2
    ]

    if not opcoes:
        st.warning("Não há bases com pelo menos duas variáveis numéricas.")
        return

    i = st.selectbox(
        "Base para cálculo do índice",
        opcoes,
        format_func=lambda x: tabelas[x]["nome"],
        key="vuln_base"
    )

    df = tabelas[i]["dados"].copy()
    numericas = df.select_dtypes(include=np.number).columns.tolist()

    selecionadas = st.multiselect(
        "Selecione os indicadores que comporão o índice",
        numericas,
        key="vuln_indicadores"
    )

    if len(selecionadas) < 2:
        st.info("Selecione pelo menos dois indicadores numéricos.")
        return

    st.markdown(
        "Defina a direção de cada indicador. Por exemplo: maior desemprego "
        "pode representar maior vulnerabilidade; maior renda pode representar "
        "menor vulnerabilidade."
    )

    padronizados = pd.DataFrame(index=df.index)

    for coluna in selecionadas:
        direcao = st.selectbox(
            f"Como interpretar {coluna}?",
            ["Maior valor = maior vulnerabilidade",
             "Menor valor = maior vulnerabilidade"],
            key=f"direcao_{i}_{coluna}"
        )

        valores = pd.to_numeric(df[coluna], errors="coerce")
        minimo, maximo = valores.min(), valores.max()

        if pd.isna(minimo) or pd.isna(maximo):
            continue

        if maximo == minimo:
            padronizados[coluna] = 0.0
        else:
            escala = (valores - minimo) / (maximo - minimo)
            if direcao == "Menor valor = maior vulnerabilidade":
                escala = 1 - escala
            padronizados[coluna] = escala

    if padronizados.shape[1] < 2:
        st.warning("Não foi possível calcular o índice com os indicadores escolhidos.")
        return

    padronizados["Indice de vulnerabilidade"] = (
        padronizados.mean(axis=1) * 100
    )

    coluna_territorio = localizar_coluna(
        df, ["municipio", "cidade", "territorio", "regiao"]
    )

    if coluna_territorio:
        padronizados["Território"] = df[coluna_territorio].astype(str)
        ranking = padronizados[
            ["Território", "Indice de vulnerabilidade"]
        ].sort_values("Indice de vulnerabilidade", ascending=False)
        eixo = "Território"
    else:
        ranking = padronizados[["Indice de vulnerabilidade"]].copy()
        ranking["Registro"] = ranking.index.astype(str)
        eixo = "Registro"
        st.warning(
            "A base não possui município ou região identificável. "
            "O resultado será apresentado por registro, não por território."
        )

    fig = px.bar(
        ranking.head(30).sort_values("Indice de vulnerabilidade"),
        x="Indice de vulnerabilidade",
        y=eixo,
        orientation="h",
        title="Índice exploratório de vulnerabilidade (0 a 100)"
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(ranking, use_container_width=True)

    st.download_button(
        "Baixar índice de vulnerabilidade",
        data=exportar_csv(ranking),
        file_name="indice_vulnerabilidade_exploratorio.csv",
        mime="text/csv",
        key="baixar_vulnerabilidade"
    )

    st.warning(
        "Este índice é exploratório e depende dos indicadores e direções escolhidos. "
        "Não é um modelo validado, não identifica risco individual e não demonstra "
        "causalidade. Antes de uso em políticas públicas, requer justificativa teórica, "
        "tratamento de dados, análise de sensibilidade e validação independente."
    )


def diagnostico_associacoes(tabelas):
    st.subheader("Associações estatísticas e investigação de fatores")

    opcoes = [
        i for i, t in enumerate(tabelas)
        if len(t["dados"].select_dtypes(include=np.number).columns) >= 2
    ]

    if not opcoes:
        st.warning("Não existem bases com variáveis numéricas suficientes.")
        return

    i = st.selectbox(
        "Selecione uma base para investigar associações",
        opcoes,
        format_func=lambda x: tabelas[x]["nome"],
        key="assoc_base"
    )

    df = tabelas[i]["dados"].select_dtypes(include=np.number).copy()
    df = df.dropna(axis=1, how="all")

    if len(df.columns) < 2:
        st.info("São necessárias pelo menos duas variáveis numéricas.")
        return

    correlacao = df.corr(method="spearman", min_periods=3)

    fig = px.imshow(
        correlacao,
        text_auto=".2f",
        aspect="auto",
        zmin=-1,
        zmax=1,
        color_continuous_scale="RdBu_r",
        title="Matriz de correlação de Spearman"
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(correlacao, use_container_width=True)

    st.caption(
        "A correlação indica associação estatística, não causalidade. "
        "Resultados dependem do número de observações, qualidade dos dados, "
        "variáveis de controle e comparabilidade das unidades analisadas."
    )

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

#
# ------------------------------------------------------------
# DIAGNÓSTICOS, VULNERABILIDADE E GAPS INSTITUCIONAIS
# ------------------------------------------------------------
with aba_diag:
    st.header("🔬 Diagnósticos, Causalidade e Vulnerabilidade")
    st.caption(
        "Análises sociodemográficas, estatísticas, territoriais "
        "e institucionais com base nos arquivos carregados."
    )

    diag_socio, diag_gaps, diag_vuln, diag_assoc, diag_qualidade = st.tabs([
        "👩 Perfil sociodemográfico",
        "🏛️ Gaps institucionais",
        "📊 Vulnerabilidade",
        "🧠 Associações e causalidade",
        "🔎 Qualidade dos dados"
    ])

    with diag_socio:
        diagnostico_sociodemografico(tabelas)

    with diag_gaps:
        diagnostico_institucional(tabelas)

    with diag_vuln:
        diagnostico_vulnerabilidade(tabelas)

    with diag_assoc:
        diagnostico_associacoes(tabelas)

    with diag_qualidade:
        st.subheader("Inventário e qualidade das bases")

        inventario = pd.DataFrame([{
            "Tabela": t["nome"],
            "Arquivo": t["arquivo"],
            "Fonte estimada": t["fonte"],
            "Registros": len(t["dados"]),
            "Colunas": len(t["dados"].columns),
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
                    "Tabela": t["nome"],
                    "Arquivo": t["arquivo"],
                    "Fonte estimada": t["fonte"],
                    "Coluna": str(c),
                    "Tipo de dado": str(t["dados"][c].dtype),
                    "Valores preenchidos": int(t["dados"][c].notna().sum()),
                    "Valores ausentes": int(t["dados"][c].isna().sum())
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
