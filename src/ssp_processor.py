import os
import pandas as pd
from sqlalchemy import create_engine


def carregar_e_tratar_ssp(caminho_arquivo):
    """Lê e trata arquivos de microdados baixados da SSP-SP (CSV ou Excel)."""
    if not os.path.exists(caminho_arquivo):
        raise FileNotFoundError(
            f"O arquivo '{caminho_arquivo}' não foi encontrado!"
        )

    print(f"Lendo arquivo da SSP-SP: {caminho_arquivo}...")

    # 1. Leitura condicional por extensão (geralmente arquivos da SSP vêm como CSV ou XLSX)
    if caminho_arquivo.endswith(".csv"):
        try:
            df = pd.read_csv(
                caminho_arquivo, sep=";", encoding="utf-8", low_memory=False
            )
        except UnicodeDecodeError:
            # Caso o encoding padrão da SSP seja latin-1 (ANSI)
            df = pd.read_csv(
                caminho_arquivo, sep=";", encoding="latin-1", low_memory=False
            )
    else:
        df = pd.read_excel(caminho_arquivo)

    # 2. Padronização do nome das colunas (converte para minúsculas e remove espaços)
    df.columns = df.columns.str.strip().str.upper()

    # 3. Mapeamento de colunas típicas da SSP-SP para o padrão do projeto
    # Ajuste os nomes das chaves (lado esquerdo) se a sua planilha usar cabeçalhos ligeiramente diferentes
    mapeamento_colunas = {
        "NATUREZA_APURADA": "tipo_violencia",
        "RUBRICA": "tipo_violencia",
        "IDADE_PESSOA": "idade",
        "IDADE": "idade",
        "ESCOLARIDADE_PESSOA": "escolaridade",
        "ESCOLARIDADE": "escolaridade",
        "CIDADE": "regiao_municipio",
        "MUNICIPIO": "regiao_municipio",
        "COR_PELE": "raca_cor",
        "SEXO_PESSOA": "sexo",
    }

    # Renomeia apenas as colunas que efetivamente existem no arquivo
    df_renomeado = df.rename(
        columns={k: v for k, v in mapeamento_colunas.items() if k in df.columns}
    )

    # 4. Filtro opcional: Mantém apenas casos do sexo feminino (se a coluna existir)
    if "sexo" in df_renomeado.columns:
        df_renomeado = df_renomeado[
            df_renomeado["sexo"].astype(str).str.upper().str.contains("FEM")
        ]

    # 5. Adiciona coluna identificadora de estado e quantidade
    df_renomeado["estado"] = "SP"
    df_renomeado["quantidade_casos"] = 1

    print(
        f"Tratamento concluído! Total de registros processados: {len(df_renomeado)}"
    )
    return df_renomeado


def salvar_ssp_no_postgres(df, string_conexao):
    """Envia os dados tratados da SSP para a tabela 'tb_ssp_violencia_mulher' do PostgreSQL."""
    engine = create_engine(string_conexao)
    df.to_sql(
        "tb_ssp_violencia_mulher", engine, if_exists="replace", index=False
    )
    print(
        "Dados inseridos com sucesso na tabela 'tb_ssp_violencia_mulher' do PostgreSQL!"
    )


# ==========================================
# EXECUTÁVEL DE TESTE INDIVIDUAL
# ==========================================
if __name__ == "__main__":
    # Substitua pelo nome exato do arquivo que você colocou em data/raw/excel_externo/
    ARQUIVO_SSP = "data/processed/excel_externo/Dados_feminicidio_SSP.xlsx"
    STRING_BANCO = (
         "mysql+pymysql://root:bru1520*@localhost:3306/meu_banco_dados"
    )

    try:
        df_tratado = carregar_e_tratar_ssp(ARQUIVO_SSP)

        # Exibe as primeiras linhas do resultado tratado no terminal
        print("\n--- Primeiras linhas dos dados tratados ---")
        print(df_tratado.head())

        # Descomente a linha abaixo quando quiser salvar direto no seu PostgreSQL:
        # salvar_ssp_no_postgres(df_tratado, STRING_BANCO)

    except Exception as erro:
        print(f"Erro ao processar a planilha da SSP-SP: {erro}")