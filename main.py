# main.py
from src.database import salvar_no_postgresql
from src.extractor import buscar_dados_violencia_domestica
from src.processor import processar_dados_processuais


def main():
    # 1. Requisição
    print("Iniciando extração do DataJud...")
    response = buscar_dados_violencia_domestica()

    # 2. Validação
    if response.status_code == 200:
        print("Sucesso! Processando dados...")
        dados_json = response.json()

        # 3. Conversão/Tratamento
        df = processar_dados_processuais(dados_json)

        # 4. Exportação Local (CSV na pasta data/processed/)
        caminho_csv = "data/processed/violencia_mulher_sp.csv"
        df.to_csv(caminho_csv, index=False, encoding="utf-8-sig")
        print(f"Arquivo CSV salvo em: {caminho_csv}")

            # 5. Inserção no MySQL
        string_db = "mysql+pymysql://root:bru1520*@localhost:3306/meu_banco_dados"


        salvar_no_postgresql(df, string_db)
    else:
        print(f"Erro ao acessar API. Status: {response.status_code}")


if __name__ == "__main__":
    main()