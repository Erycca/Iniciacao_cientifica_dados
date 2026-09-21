# src/processor.py
import pandas as pd


def processar_dados_processuais(dados_json):
    lista_processos = []
    hits = dados_json.get("hits", {}).get("hits", [])

    for hit in hits:
        source = hit.get("_source", {})

        # Tipo de Violência / Assunto
        assuntos = [a.get("nome") for a in source.get("assuntos", [])]
        tipo_violencia = ", ".join(assuntos) if assuntos else "Não especificado"

        # Região / Comarca (Órgão Julgador)
        orgao = source.get("orgaoJulgador", {})
        regiao_comarca = orgao.get("nome", "Não Informado")

        lista_processos.append(
            {
                "numero_processo": source.get("numeroProcesso"),
                "data_ajuizamento": source.get("dataAjuizamento"),
                "tipo_violencia": tipo_violencia,
                "regiao_comarca": regiao_comarca,
                "estado": "SP",
                "quantidade_casos": 1,
            }
        )

    df = pd.DataFrame(lista_processos)
    return df