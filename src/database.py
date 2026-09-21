# src/database.py
from sqlalchemy import create_engine


def salvar_no_postgresql(df, string_conexao):
    engine = create_engine(string_conexao)
    # Salva na tabela tb_violencia_mulher_sp do PostgreSQL
    df.to_sql(
        "tb_violencia_mulher_sp", engine, if_exists="append", index=False
    )
    print("Dados armazenados com sucesso no banco de dados MySQL!")
    