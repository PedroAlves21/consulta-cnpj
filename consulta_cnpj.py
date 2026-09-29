"""Consulta uma lista de CNPJs na BrasilAPI e devolve os dados das empresas.

Uso:
    python consulta_cnpj.py lista.xlsx                          # todas as colunas -> lista_cnpj.xlsx
    python consulta_cnpj.py lista.csv -o resultado.csv          # escolhe o arquivo de saída
    python consulta_cnpj.py lista.txt -c RAZAO_SOCIAL,SITUACAO  # só as colunas pedidas
    python consulta_cnpj.py 00.000.000/0001-91 11222333000181   # CNPJs direto, resultado na tela
    python consulta_cnpj.py --colunas-disponiveis

Entrada: .txt (um CNPJ por linha), .csv ou .xlsx. Em .csv/.xlsx usa a coluna cujo nome
contém "CNPJ" (ou a primeira coluna); as demais colunas da planilha são mantidas.
Aceita CNPJ com ou sem pontuação e sem os zeros à esquerda.

Saída: .xlsx ou .csv (pela extensão de -o), uma linha por CNPJ da entrada, na mesma ordem.

Fonte: https://brasilapi.com.br/api/cnpj/v1/{cnpj} (gratuita, sem chave, dados da Receita
Federal). As respostas ficam em ~/.cache/consulta_cnpj/cache.jsonl, então rodar de novo
continua de onde parou e não repete consulta; --atualizar ignora o cache.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

import pandas as pd

URL = "https://brasilapi.com.br/api/cnpj/v1/{}"
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "consulta_cnpj", "cache.jsonl")
PAUSA = 0.5  # segundos entre consultas, pra não levar bloqueio (HTTP 429)
TENTATIVAS = 5

COLUNAS = [
    "CNPJ", "RAZAO_SOCIAL", "NOME_FANTASIA", "SITUACAO", "DATA_SITUACAO", "MATRIZ_FILIAL",
    "DATA_ABERTURA", "CNAE", "CNAE_DESCRICAO", "CNAES_SECUNDARIOS", "NATUREZA_JURIDICA", "PORTE",
    "CAPITAL_SOCIAL", "SIMPLES", "MEI", "LOGRADOURO", "NUMERO", "COMPLEMENTO", "BAIRRO", "CEP",
    "MUNICIPIO", "UF", "TELEFONE", "EMAIL", "QTD_SOCIOS", "SOCIOS", "ERRO",
]


def limpa_cnpj(valor):
    digitos = re.sub(r"\D", "", str(valor))
    return digitos.zfill(14) if 0 < len(digitos) <= 14 else None


def consulta(cnpj):
    """Devolve o JSON da BrasilAPI, ou {"erro": ...} quando o CNPJ não existe/é inválido."""
    req = urllib.request.Request(URL.format(cnpj), headers={"User-Agent": "consulta-cnpj"})
    for tentativa in range(TENTATIVAS):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 400:
                return {"erro": "CNPJ inválido"}
            if e.code == 404:
                return {"erro": "CNPJ não encontrado"}
            espera = 2 ** tentativa * (5 if e.code == 429 else 1)
        except (urllib.error.URLError, TimeoutError):
            espera = 2 ** tentativa
        print(f"  {cnpj}: falhou, tentando de novo em {espera}s", file=sys.stderr)
        time.sleep(espera)
    return {"erro": "sem resposta da API"}


def extrai(cnpj, d):
    """Achata a resposta nas colunas de COLUNAS."""
    if "erro" in d:
        return {"CNPJ": cnpj, "ERRO": d["erro"]}
    socios = d.get("qsa") or []
    return {
        "CNPJ": cnpj,
        "RAZAO_SOCIAL": d.get("razao_social"),
        "NOME_FANTASIA": d.get("nome_fantasia"),
        "SITUACAO": d.get("descricao_situacao_cadastral"),
        "DATA_SITUACAO": d.get("data_situacao_cadastral"),
        "MATRIZ_FILIAL": d.get("descricao_identificador_matriz_filial"),
        "DATA_ABERTURA": d.get("data_inicio_atividade"),
        "CNAE": d.get("cnae_fiscal"),
        "CNAE_DESCRICAO": d.get("cnae_fiscal_descricao"),
        "CNAES_SECUNDARIOS": ", ".join(str(c["codigo"]) for c in d.get("cnaes_secundarios") or [] if c.get("codigo")),
        "NATUREZA_JURIDICA": d.get("natureza_juridica"),
        "PORTE": d.get("porte"),
        "CAPITAL_SOCIAL": d.get("capital_social"),
        "SIMPLES": "SIM" if d.get("opcao_pelo_simples") else "NAO",
        "MEI": "SIM" if d.get("opcao_pelo_mei") else "NAO",
        "LOGRADOURO": " ".join(filter(None, [d.get("descricao_tipo_de_logradouro"), d.get("logradouro")])),
        "NUMERO": d.get("numero"),
        "COMPLEMENTO": d.get("complemento"),
        "BAIRRO": d.get("bairro"),
        "CEP": d.get("cep"),
        "MUNICIPIO": d.get("municipio"),
        "UF": d.get("uf"),
        "TELEFONE": d.get("ddd_telefone_1") or d.get("ddd_telefone_2"),
        "EMAIL": d.get("email"),
        "QTD_SOCIOS": len(socios),
        "SOCIOS": " | ".join(s["nome_socio"] for s in socios),
        "ERRO": None,
    }


def carrega_cache():
    if not os.path.exists(CACHE):
        return {}
    with open(CACHE, encoding="utf-8") as f:
        return {r["cnpj"]: r["dados"] for r in map(json.loads, f)}


def consulta_todos(cnpjs, atualizar=False):
    cache = {} if atualizar else carrega_cache()
    faltam = list(dict.fromkeys(c for c in cnpjs if c and c not in cache))
    print(f"{len(set(cnpjs))} CNPJs, {len(faltam)} para consultar", file=sys.stderr)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "a", encoding="utf-8") as f:
        for i, cnpj in enumerate(faltam, 1):
            dados = consulta(cnpj)
            cache[cnpj] = dados
            f.write(json.dumps({"cnpj": cnpj, "dados": dados}, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{i}/{len(faltam)}] {cnpj} {dados.get('razao_social') or dados.get('erro')}", file=sys.stderr)
            time.sleep(PAUSA)
    return {c: extrai(c, cache[c]) if c else {"ERRO": "CNPJ vazio/ilegível"} for c in cnpjs}


def le_entrada(caminho):
    """Devolve (planilha original, nome da coluna de CNPJ)."""
    ext = os.path.splitext(caminho)[1].lower()
    if ext == ".txt":
        with open(caminho, encoding="utf-8") as f:
            linhas = [l.strip() for l in f if l.strip()]
        return pd.DataFrame({"CNPJ_ENTRADA": linhas}), "CNPJ_ENTRADA"
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(caminho, dtype=str)
    else:
        df = pd.read_csv(caminho, dtype=str, sep=None, engine="python")
    col = next((c for c in df.columns if "CNPJ" in str(c).upper()), df.columns[0])
    return df, col


def main():
    ap = argparse.ArgumentParser(description="Consulta CNPJs na BrasilAPI.")
    ap.add_argument("entrada", nargs="*", help="arquivo .txt/.csv/.xlsx com CNPJs, ou os próprios CNPJs")
    ap.add_argument("-o", "--saida", help="arquivo de saída (.xlsx ou .csv)")
    ap.add_argument("-c", "--colunas", help="colunas separadas por vírgula (padrão: todas)")
    ap.add_argument("--atualizar", action="store_true", help="ignora o cache e consulta tudo de novo")
    ap.add_argument("--colunas-disponiveis", action="store_true", help="lista as colunas e sai")
    args = ap.parse_args()

    if args.colunas_disponiveis:
        print("\n".join(COLUNAS))
        return
    if not args.entrada:
        ap.error("informe um arquivo com CNPJs ou os CNPJs")

    colunas = COLUNAS
    if args.colunas:
        colunas = [c.strip().upper() for c in args.colunas.split(",")]
        invalidas = [c for c in colunas if c not in COLUNAS]
        if invalidas:
            ap.error(f"colunas inexistentes: {', '.join(invalidas)} (veja --colunas-disponiveis)")
        colunas = list(dict.fromkeys(["CNPJ", *colunas, "ERRO"]))

    # CNPJs direto na linha de comando: resultado na tela
    if not os.path.isfile(args.entrada[0]):
        resultado = consulta_todos([limpa_cnpj(c) for c in args.entrada], args.atualizar)
        for dados in resultado.values():
            print("\n" + "\n".join(f"{k:>18}: {dados[k]}" for k in colunas if dados.get(k) not in (None, "")))
        return

    df, col = le_entrada(args.entrada[0])
    cnpjs = [limpa_cnpj(v) if pd.notna(v) else None for v in df[col]]
    resultado = consulta_todos(cnpjs, args.atualizar)
    dados = pd.DataFrame([resultado[c] for c in cnpjs], columns=colunas)
    dados = dados.rename(columns={"CNPJ": "CNPJ_CONSULTADO"})
    saida = pd.concat([df.reset_index(drop=True), dados], axis=1)

    destino = args.saida or os.path.splitext(args.entrada[0])[0] + "_cnpj.xlsx"
    if destino.lower().endswith(".csv"):
        saida.to_csv(destino, index=False)
    else:
        saida.to_excel(destino, index=False)
    erros = dados["ERRO"].notna().sum()
    print(f"\nsalvo em {destino} ({len(saida)} linhas, {erros} com erro)", file=sys.stderr)


if __name__ == "__main__":
    main()
