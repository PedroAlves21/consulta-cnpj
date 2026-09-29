"""Lê um CSV com CNPJs, consulta cada um na BrasilAPI e grava as colunas pedidas.

Uso:
    python consulta_cnpj.py empresas.csv -c RAZAO_SOCIAL,SITUACAO          # -> empresas_cnpj.csv
    python consulta_cnpj.py empresas.csv -c RAZAO_SOCIAL=Empresa,UF=Estado  # com o nome de coluna que quiser
    python consulta_cnpj.py empresas.csv -c SITUACAO -o saida/resultado.csv # grava onde quiser
    python consulta_cnpj.py empresas.csv -c SITUACAO --sobrescrever         # grava no próprio empresas.csv
    python consulta_cnpj.py 00.000.000/0001-91 11222333000181              # CNPJs direto, resultado na tela
    python consulta_cnpj.py --colunas-disponiveis

Entrada: .csv (também aceita .xlsx e .txt com um CNPJ por linha). Usa a coluna cujo nome
contém "CNPJ" (ou a indicada em --coluna-cnpj). Aceita CNPJ com ou sem pontuação e sem os
zeros à esquerda. O separador e a codificação do CSV são detectados e mantidos na saída.

Saída: o mesmo arquivo com as colunas pedidas acrescentadas no fim (sem -c, todas). Se uma
coluna de destino já existe, ela é preenchida em vez de duplicada. Linhas cujo CNPJ falhou
ficam com o valor que já tinham, e o motivo vai para a coluna ERRO_CNPJ.

Fonte: https://brasilapi.com.br/api/cnpj/v1/{cnpj} (gratuita, sem chave, dados da Receita
Federal). As respostas ficam em ~/.cache/consulta_cnpj/cache.jsonl, então rodar de novo
continua de onde parou e não repete consulta; --atualizar ignora o cache.
"""
import argparse
import csv
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
    """Devolve (dataframe, separador, codificação). Tudo lido como texto, vazio continua vazio."""
    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(caminho, dtype=str).fillna(""), None, None
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            with open(caminho, encoding=encoding) as f:
                amostra = f.read(8192)
            break
        except UnicodeDecodeError:
            continue
    if ext == ".txt":
        with open(caminho, encoding=encoding) as f:
            linhas = [l.strip() for l in f if l.strip()]
        return pd.DataFrame({"CNPJ": linhas}), ",", encoding
    try:
        sep = csv.Sniffer().sniff(amostra, delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ","
    df = pd.read_csv(caminho, dtype=str, sep=sep, encoding=encoding, keep_default_na=False)
    return df, sep, encoding


def le_colunas(texto):
    """'RAZAO_SOCIAL=Empresa,UF' -> [('RAZAO_SOCIAL', 'Empresa'), ('UF', 'UF')]."""
    pares = []
    for item in filter(None, (i.strip() for i in texto.split(","))):
        campo, _, destino = item.partition("=")
        pares.append((campo.strip().upper(), destino.strip() or campo.strip().upper()))
    return pares


def main():
    ap = argparse.ArgumentParser(description="Consulta CNPJs na BrasilAPI e grava as colunas pedidas.")
    ap.add_argument("entrada", nargs="*", help="arquivo .csv/.xlsx/.txt com CNPJs, ou os próprios CNPJs")
    ap.add_argument("-c", "--colunas", help="CAMPO ou CAMPO=NOME_DA_COLUNA, separados por vírgula (padrão: todos)")
    ap.add_argument("-o", "--saida", help="onde gravar (.csv ou .xlsx); padrão: <entrada>_cnpj.<ext>")
    ap.add_argument("--sobrescrever", action="store_true", help="grava no próprio arquivo de entrada")
    ap.add_argument("--coluna-cnpj", help="nome da coluna com o CNPJ (padrão: a que tem 'CNPJ' no nome)")
    ap.add_argument("--atualizar", action="store_true", help="ignora o cache e consulta tudo de novo")
    ap.add_argument("--colunas-disponiveis", action="store_true", help="lista os campos e sai")
    args = ap.parse_args()

    if args.colunas_disponiveis:
        print("\n".join(COLUNAS))
        return
    if not args.entrada:
        ap.error("informe um arquivo com CNPJs ou os CNPJs")
    if args.sobrescrever and args.saida:
        ap.error("use -o ou --sobrescrever, não os dois")

    campos = le_colunas(args.colunas) if args.colunas else [(c, c) for c in COLUNAS if c not in ("CNPJ", "ERRO")]
    invalidos = [c for c, _ in campos if c not in COLUNAS]
    if invalidos:
        ap.error(f"campos inexistentes: {', '.join(invalidos)} (veja --colunas-disponiveis)")

    # CNPJs direto na linha de comando: resultado na tela
    if not os.path.isfile(args.entrada[0]):
        resultado = consulta_todos([limpa_cnpj(c) for c in args.entrada], args.atualizar)
        for cnpj, dados in resultado.items():
            print(f"\n{'CNPJ':>18}: {cnpj}")
            for campo, destino in campos + [("ERRO", "ERRO")]:
                if dados.get(campo) not in (None, ""):
                    print(f"{destino:>18}: {dados[campo]}")
        return

    entrada = args.entrada[0]
    df, sep, encoding = le_entrada(entrada)
    col_cnpj = args.coluna_cnpj or next((c for c in df.columns if "CNPJ" in str(c).upper()), None)
    if col_cnpj not in df.columns:
        ap.error(f"coluna de CNPJ não encontrada; colunas do arquivo: {', '.join(map(str, df.columns))} (use --coluna-cnpj)")

    cnpjs = [limpa_cnpj(v) for v in df[col_cnpj]]
    resultado = consulta_todos(cnpjs, args.atualizar)
    dados = pd.DataFrame([resultado[c] for c in cnpjs], columns=COLUNAS, dtype=object)
    ok = dados["ERRO"].isna().to_numpy()

    for campo, destino in campos:
        novos = dados[campo].where(dados[campo].notna(), "").astype(str).to_numpy()
        if destino in df.columns:
            df.loc[ok, destino] = novos[ok]  # coluna já existe: só troca onde a consulta deu certo
        else:
            df[destino] = novos
    if not ok.all():
        df["ERRO_CNPJ"] = dados["ERRO"].fillna("").to_numpy()

    if args.sobrescrever:
        destino_arquivo = entrada
    else:
        base, ext = os.path.splitext(entrada)
        destino_arquivo = args.saida or f"{base}_cnpj{'.csv' if ext.lower() == '.txt' else ext}"
    pasta = os.path.dirname(destino_arquivo)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    if destino_arquivo.lower().endswith((".xlsx", ".xls")):
        df.to_excel(destino_arquivo, index=False)
    else:
        df.to_csv(destino_arquivo, index=False, sep=sep or ",", encoding=encoding or "utf-8-sig")
    print(f"\nsalvo em {destino_arquivo} ({len(df)} linhas, {(~ok).sum()} com erro)", file=sys.stderr)


if __name__ == "__main__":
    main()
