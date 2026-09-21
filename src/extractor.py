# src/extractor.py
import json
import requests
from src.config import API_KEY, DATAJUD_URL


def buscar_dados_violencia_domestica():
        
        headers = {
        "Authorization": f"ApiKey {API_KEY}",  # Adicionado o prefixo ApiKey com um espaço
        "Content-Type": "application/json",
    }
    # Query em Elasticsearch filtrando o assunto Violência Doméstica

        payload = {
        "size": 100,  # Quantidade de registros por página
        "query": {
            "bool": {
                "must": [
                    {
                        "match": {
                            "assuntos.nome": "Violência Doméstica Contra A Mulher"
                        }
                    }
                ]
            }
        },
    }

        response = requests.post(
    DATAJUD_URL, headers=headers, data=json.dumps(payload), allow_redirects=False
)
        return response
if __name__ == "__main__":
    print("Iniciando a busca de dados...")
    # Executa a função e guarda o resultado na variável response
    response = buscar_dados_violencia_domestica()

    # Verifica se a requisição deu certo
    if response.status_code == 200:
        print("Requisição bem-sucedida (Status 200)!")
        dados_brutos = response.json()
        print(dados_brutos)  # Linha opcional para você ver os dados no terminal
    else:
        print(f"Erro na requisição: {response.status_code} - {response.text}")
