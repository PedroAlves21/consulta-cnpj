# consulta-cnpj

Consulta uma lista de CNPJs na [BrasilAPI](https://brasilapi.com.br/docs#tag/CNPJ) (gratuita, sem chave, dados da Receita Federal) e devolve uma planilha com os dados de cada empresa.

## Instalação

```bash
git clone <url-do-repo> consulta-cnpj
cd consulta-cnpj
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

```bash
# planilha com uma coluna "CNPJ" -> lista_cnpj.xlsx com todas as colunas
python consulta_cnpj.py lista.xlsx

# só as colunas que interessam, saída em CSV
python consulta_cnpj.py lista.xlsx -c RAZAO_SOCIAL,SITUACAO,MUNICIPIO,UF,MEI -o resultado.csv

# CNPJs direto no terminal (resultado na tela)
python consulta_cnpj.py 00.000.000/0001-91 360305000104

# lista das colunas disponíveis
python consulta_cnpj.py --colunas-disponiveis
```

**Entrada:** `.xlsx`, `.csv` ou `.txt` (um CNPJ por linha). Em planilha, usa a coluna que tem "CNPJ" no nome (ou a primeira) e mantém as outras colunas no resultado. O CNPJ pode vir com ou sem pontuação e sem os zeros à esquerda.

**Saída:** uma linha por CNPJ da entrada, na mesma ordem. CNPJ inválido, não encontrado ou vazio fica marcado na coluna `ERRO`.

**Colunas:** `CNPJ`, `RAZAO_SOCIAL`, `NOME_FANTASIA`, `SITUACAO`, `DATA_SITUACAO`, `MATRIZ_FILIAL`, `DATA_ABERTURA`, `CNAE`, `CNAE_DESCRICAO`, `CNAES_SECUNDARIOS`, `NATUREZA_JURIDICA`, `PORTE`, `CAPITAL_SOCIAL`, `SIMPLES`, `MEI`, `LOGRADOURO`, `NUMERO`, `COMPLEMENTO`, `BAIRRO`, `CEP`, `MUNICIPIO`, `UF`, `TELEFONE`, `EMAIL`, `QTD_SOCIOS`, `SOCIOS`, `ERRO`.

## Cache

Cada resposta fica guardada em `~/.cache/consulta_cnpj/cache.jsonl`. Se a execução for interrompida, é só rodar de novo: continua de onde parou e não consulta o mesmo CNPJ duas vezes. Para buscar dados atualizados, use `--atualizar`.

A API limita o número de consultas por minuto; o script faz uma pausa entre elas e, se for bloqueado (HTTP 429), espera e tenta de novo.
