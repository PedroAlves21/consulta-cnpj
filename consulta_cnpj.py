"""Lê um CSV com CPFs e CNPJs, consulta os CNPJs na BrasilAPI e grava um novo CSV com os dados.

Passo a passo:
  1. lê o CSV e acha a coluna do documento (nome com "CPF", "CNPJ" ou "DOC", ou --coluna-doc);
  2. identifica se cada documento é CPF ou CNPJ (pelo tamanho e pelo dígito verificador) e
     grava isso na coluna TIPO_DOC: CPF, CNPJ, CPF INVÁLIDO, CNPJ INVÁLIDO ou SEM DOCUMENTO;
  3. consulta na API, um por um, só os CNPJs válidos;
  4. grava um novo CSV, cleandata-<cidade>.csv na pasta da entrada, com todas as colunas
     originais + TIPO_DOC + as colunas pedidas. Linhas de CPF ficam com essas colunas vazias;
     linhas de CNPJ inválido ou que falhou na consulta ficam com "ERRO_CNPJ" nelas.

Uso:
    python consulta_cnpj.py cadastro.csv                          # -> cleandata-<cidade>.csv com as colunas padrão
    python consulta_cnpj.py cadastro.csv --cidade "São Luís"      # -> cleandata-sao-luis.csv
    python consulta_cnpj.py cadastro.csv -c RAZAO_SOCIAL,SITUACAO  # outras colunas
    python consulta_cnpj.py cadastro.csv -c RAZAO_SOCIAL=Empresa   # com o nome de coluna que quiser
    python consulta_cnpj.py cadastro.csv -o saida/resultado.csv    # grava onde quiser
    python consulta_cnpj.py 00.000.000/0001-91 11222333000181     # documentos direto, resultado na tela
    python consulta_cnpj.py --colunas-disponiveis

Entrada: .csv (também aceita .xlsx e .txt com um documento por linha). Aceita documento com
ou sem pontuação e sem os zeros à esquerda. O separador e a codificação do CSV são detectados
e mantidos na saída. Se uma coluna de destino já existe, ela é preenchida em vez de duplicada.
A cidade do nome do arquivo é o município mais comum entre os CNPJs consultados.

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
import unicodedata
import urllib.error
import urllib.request

import pandas as pd

URL = "https://brasilapi.com.br/api/cnpj/v1/{}"
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "consulta_cnpj", "cache.jsonl")
PAUSA = 0.5  # segundos entre consultas, pra não levar bloqueio (HTTP 429)
TENTATIVAS = 5

# A BrasilAPI não devolve e-mail; ele vem da API aberta da CNPJá, que só aceita 5 consultas por minuto.
URL_EMAIL = "https://open.cnpja.com/office/{}"
CACHE_EMAIL = os.path.join(os.path.dirname(CACHE), "email.jsonl")
PAUSA_EMAIL = 12.5

COLUNAS = [
    "CNPJ", "RAZAO_SOCIAL", "NOME_FANTASIA", "SITUACAO", "DATA_SITUACAO", "MATRIZ_FILIAL",
    "DATA_ABERTURA", "CNAE", "CNAE_DESCRICAO",
    "CNAES_SECUNDARIOS", "NATUREZA_JURIDICA", "PORTE", "PORTE_RECEITA", "CAPITAL_SOCIAL", "SIMPLES",
    "MEI", "LOGRADOURO", "NUMERO", "COMPLEMENTO", "BAIRRO", "CEP", "MUNICIPIO", "UF", "TELEFONES",
    "EMAIL", "QTD_SOCIOS", "SOCIOS",
]
PADRAO = ["PORTE", "NUMERO", "NOME_FANTASIA", "MATRIZ_FILIAL", "TELEFONES", "EMAIL"]  # colunas quando -c não é informado

# A Receita só tem 3 faixas de porte (por faturamento anual): micro (inclui MEI, até R$ 360 mil),
# pequeno porte (até R$ 4,8 mi) e "demais" (acima disso). Aqui viram pequeno/médio/grande.
PORTE_CLASSE = {1: "PEQUENO", 3: "MÉDIO", 5: "GRANDE"}


def dv_ok(doc, pesos1):
    """Confere os 2 dígitos verificadores (mesma conta para CPF e CNPJ, muda só o peso)."""
    base = doc[:-2]
    for pesos in (pesos1, [pesos1[0] + 1] + pesos1):
        resto = sum(int(d) * p for d, p in zip(base, pesos)) % 11
        base += str(0 if resto < 2 else 11 - resto)
    return base == doc and len(set(doc)) > 1  # 111.111.111-11 etc. passam na conta mas não valem


PESOS_CPF = [10, 9, 8, 7, 6, 5, 4, 3, 2]
PESOS_CNPJ = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def tipo_documento(valor):
    """Devolve (TIPO_DOC, documento só com dígitos e zeros à esquerda).

    Até 11 dígitos é CPF, a menos que só faça sentido como CNPJ que perdeu os zeros à esquerda
    (planilha que tratou o número como número); 12 a 14 dígitos é CNPJ.
    """
    digitos = re.sub(r"\D", "", str(valor))
    if not digitos:
        return "SEM DOCUMENTO", None
    if len(digitos) <= 11:
        if dv_ok(digitos.zfill(11), PESOS_CPF):
            return "CPF", digitos.zfill(11)
        if dv_ok(digitos.zfill(14), PESOS_CNPJ):
            return "CNPJ", digitos.zfill(14)
        return "CPF INVÁLIDO", digitos.zfill(11)
    if len(digitos) <= 14:
        cnpj = digitos.zfill(14)
        return ("CNPJ" if dv_ok(cnpj, PESOS_CNPJ) else "CNPJ INVÁLIDO"), cnpj
    return "CNPJ INVÁLIDO", digitos


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


def formata_telefone(numero):
    """'9832140000' -> '(98) 3214-0000'; celular com 9 dígitos -> '(98) 99999-0000'."""
    digitos = re.sub(r"\D", "", numero or "")
    if len(digitos) < 10:
        return digitos or None
    ddd, resto = digitos[:2], digitos[2:]
    numero = f"{resto[:-4]}-{resto[-4:]}"
    return numero if ddd == "00" else f"({ddd}) {numero}"  # 00 = sem DDD (4004-xxxx, 0800)


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
        "PORTE": PORTE_CLASSE.get(d.get("codigo_porte"), "NÃO INFORMADO"),
        "PORTE_RECEITA": d.get("porte"),
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
        "TELEFONES": ", ".join(filter(None, map(formata_telefone, [d.get("ddd_telefone_1"), d.get("ddd_telefone_2")]))) or None,
        "EMAIL": None,  # preenchido em consulta_todos, via CNPJá
        "QTD_SOCIOS": len(socios),
        "SOCIOS": " | ".join(s["nome_socio"] for s in socios),
        "ERRO": None,
    }


def consulta_email(cnpj):
    """E-mails do CNPJ na CNPJá (lista, pode ser vazia), ou None se a API não respondeu."""
    req = urllib.request.Request(URL_EMAIL.format(cnpj), headers={"User-Agent": "consulta-cnpj"})
    for tentativa in range(10):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return [e["address"].lower() for e in json.load(resp).get("emails") or []]
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return []
            espera = 60 if e.code == 429 else 2 ** tentativa
        except (urllib.error.URLError, TimeoutError):
            espera = 2 ** tentativa
        time.sleep(espera)
    return None


def carrega_cache(caminho=CACHE):
    if not os.path.exists(caminho):
        return {}
    with open(caminho, encoding="utf-8") as f:
        return {r["cnpj"]: r["dados"] for r in map(json.loads, f)}


def busca_emails(cnpjs, atualizar):
    cache = carrega_cache(CACHE_EMAIL)
    faltam = list(dict.fromkeys(c for c in cnpjs if atualizar or c not in cache))
    if faltam:
        print(f"e-mails: {len(faltam)} CNPJs para consultar na CNPJá (~{len(faltam) * PAUSA_EMAIL / 60:.0f} min)", file=sys.stderr)
    with open(CACHE_EMAIL, "a", encoding="utf-8") as f:
        for i, cnpj in enumerate(faltam, 1):
            emails = consulta_email(cnpj)
            if emails is not None:  # sem resposta não vai pro cache, pra tentar de novo na próxima vez
                cache[cnpj] = emails
                f.write(json.dumps({"cnpj": cnpj, "dados": emails}) + "\n")
                f.flush()
            print(f"[e-mail {i}/{len(faltam)}] {cnpj} {', '.join(emails or []) or '-'}", file=sys.stderr)
            time.sleep(PAUSA_EMAIL)
    return cache


def busca(cnpjs, cache, atualizar):
    """Consulta na API os CNPJs que ainda não estão no cache (ou todos, com atualizar)."""
    faltam = list(dict.fromkeys(c for c in cnpjs if c and (atualizar or c not in cache)))
    print(f"{len(set(filter(None, cnpjs)))} CNPJs, {len(faltam)} para consultar", file=sys.stderr)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "a", encoding="utf-8") as f:
        for i, cnpj in enumerate(faltam, 1):
            dados = consulta(cnpj)
            cache[cnpj] = dados
            f.write(json.dumps({"cnpj": cnpj, "dados": dados}, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{i}/{len(faltam)}] {cnpj} {dados.get('razao_social') or dados.get('erro')}", file=sys.stderr)
            time.sleep(PAUSA)


def consulta_todos(cnpjs, atualizar=False, emails=False):
    """Consulta os CNPJs (já validados) e devolve {cnpj: linha com as colunas de COLUNAS}."""
    cache = carrega_cache()
    busca(cnpjs, cache, atualizar)
    linhas = {c: extrai(c, cache[c]) for c in cnpjs}
    if emails:
        achados = busca_emails([c for c in linhas if not linhas[c]["ERRO"]], atualizar)
        for c, linha in linhas.items():
            linha["EMAIL"] = ", ".join(achados.get(c) or []) or None
    return linhas


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
        return pd.DataFrame({"CPF/CNPJ": linhas}), ",", encoding
    try:
        sep = csv.Sniffer().sniff(amostra, delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ","
    df = pd.read_csv(caminho, dtype=str, sep=sep, encoding=encoding, keep_default_na=False)
    return df, sep, encoding


def slug(texto):
    """'São Luís' -> 'sao-luis'."""
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")


def le_colunas(texto):
    """'RAZAO_SOCIAL=Empresa,UF' -> [('RAZAO_SOCIAL', 'Empresa'), ('UF', 'UF')]."""
    pares = []
    for item in filter(None, (i.strip() for i in texto.split(","))):
        campo, _, destino = item.partition("=")
        pares.append((campo.strip().upper(), destino.strip() or campo.strip().upper()))
    return pares


def main():
    ap = argparse.ArgumentParser(description="Identifica CPF/CNPJ, consulta os CNPJs na BrasilAPI e grava um novo CSV.")
    ap.add_argument("entrada", nargs="*", help="arquivo .csv/.xlsx/.txt, ou os próprios documentos")
    ap.add_argument("-c", "--colunas", help=f"CAMPO ou CAMPO=NOME_DA_COLUNA, separados por vírgula (padrão: {','.join(PADRAO)})")
    ap.add_argument("--todas", action="store_true", help="acrescenta todos os campos disponíveis")
    ap.add_argument("-o", "--saida", help="onde gravar (.csv ou .xlsx); padrão: cleandata-<cidade>.csv na pasta da entrada")
    ap.add_argument("--cidade", help="cidade usada no nome do arquivo (padrão: a mais comum entre os CNPJs)")
    ap.add_argument("--sobrescrever", action="store_true", help="grava no próprio arquivo de entrada")
    ap.add_argument("--coluna-doc", "--coluna-cnpj", help="coluna com o CPF/CNPJ (padrão: a que tem CPF, CNPJ ou DOC no nome)")
    ap.add_argument("--sem-email", action="store_true", help="não busca e-mail (a busca é lenta: 5 CNPJs por minuto)")
    ap.add_argument("--atualizar", action="store_true", help="ignora o cache e consulta tudo de novo")
    ap.add_argument("--colunas-disponiveis", action="store_true", help="lista os campos e sai")
    args = ap.parse_args()

    if args.colunas_disponiveis:
        print("\n".join(COLUNAS))
        return
    if not args.entrada:
        ap.error("informe um arquivo ou os documentos")
    if args.sobrescrever and args.saida:
        ap.error("use -o ou --sobrescrever, não os dois")

    if args.todas:
        campos = [(c, c) for c in COLUNAS if c != "CNPJ"]
    else:
        campos = le_colunas(args.colunas) if args.colunas else [(c, c) for c in PADRAO]
    invalidos = [c for c, _ in campos if c not in COLUNAS]
    if invalidos:
        ap.error(f"campos inexistentes: {', '.join(invalidos)} (veja --colunas-disponiveis)")
    if args.sem_email:
        campos = [(c, d) for c, d in campos if c != "EMAIL"]
    emails = any(c == "EMAIL" for c, _ in campos)

    # documentos direto na linha de comando: resultado na tela
    if not os.path.isfile(args.entrada[0]):
        tipos = [tipo_documento(v) for v in args.entrada]
        resultado = consulta_todos([d for t, d in tipos if t == "CNPJ"], args.atualizar, emails)
        for tipo, doc in tipos:
            print(f"\n{tipo:>18}: {doc}")
            for campo, destino in campos + [("ERRO", "ERRO")] if tipo == "CNPJ" else []:
                if resultado[doc].get(campo) not in (None, ""):
                    print(f"{destino:>18}: {resultado[doc][campo]}")
        return

    entrada = args.entrada[0]
    df, sep, encoding = le_entrada(entrada)
    col_doc = args.coluna_doc or next(
        (c for c in df.columns if any(k in str(c).upper() for k in ("CNPJ", "CPF", "DOC"))), None)
    if col_doc not in df.columns:
        ap.error(f"coluna do documento não encontrada; colunas do arquivo: {', '.join(map(str, df.columns))} (use --coluna-doc)")

    # 1. CPF ou CNPJ
    tipos = [tipo_documento(v) for v in df[col_doc]]
    tipo_doc = [t for t, _ in tipos]
    if "TIPO_DOC" in df.columns:
        df["TIPO_DOC"] = tipo_doc
    else:
        df.insert(df.columns.get_loc(col_doc) + 1, "TIPO_DOC", tipo_doc)
    print(pd.Series(tipo_doc).value_counts().to_string(), file=sys.stderr)

    # 2. consulta só os CNPJs válidos
    cnpjs = [d if t == "CNPJ" else None for t, d in tipos]
    resultado = consulta_todos([c for c in cnpjs if c], args.atualizar, emails)
    dados = pd.DataFrame([resultado[c] if c else {} for c in cnpjs], columns=COLUNAS + ["ERRO"], dtype=object)
    dados.loc[pd.Series(tipo_doc) == "CNPJ INVÁLIDO", "ERRO"] = "dígito verificador inválido"
    ok = pd.Series(cnpjs).notna().to_numpy() & dados["ERRO"].isna().to_numpy()

    # 3. novas colunas
    for campo, destino in campos:
        novos = dados[campo].where(dados[campo].notna(), "").astype(str).to_numpy()
        if destino in df.columns:
            df.loc[ok, destino] = novos[ok]  # coluna já existe: só troca onde a consulta deu certo
        else:
            df[destino] = novos
    erros = dados["ERRO"].notna().to_numpy()
    for _, destino in campos:
        df.loc[erros, destino] = "ERRO_CNPJ"

    if args.sobrescrever:
        destino_arquivo = entrada
    else:
        cidade = args.cidade or dados.loc[ok, "MUNICIPIO"].mode().get(0) or os.path.splitext(os.path.basename(entrada))[0]
        destino_arquivo = args.saida or os.path.join(os.path.dirname(entrada), f"cleandata-{slug(cidade)}.csv")
    pasta = os.path.dirname(destino_arquivo)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    if destino_arquivo.lower().endswith((".xlsx", ".xls")):
        df.to_excel(destino_arquivo, index=False)
    else:
        df.to_csv(destino_arquivo, index=False, sep=sep or ",", encoding=encoding or "utf-8-sig")
    print(f"\nsalvo em {destino_arquivo} ({len(df)} linhas, {ok.sum()} CNPJs consultados, {erros.sum()} com erro)", file=sys.stderr)


if __name__ == "__main__":
    main()
