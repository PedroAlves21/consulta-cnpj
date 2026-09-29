# consulta-cnpj

Lê um CSV com CPFs e CNPJs, identifica o tipo de cada documento, consulta só os CNPJs na [BrasilAPI](https://brasilapi.com.br/docs#tag/CNPJ) (gratuita, sem chave, dados da Receita Federal), um por um, e grava um **novo CSV** com tudo o que o arquivo já tinha mais as informações das empresas.

1. Acha a coluna do documento (nome com `CPF`, `CNPJ` ou `DOC`, ou a indicada em `--coluna-doc`).
2. Cria a coluna `TIPO_DOC`, logo depois dela: `CPF`, `CNPJ`, `CPF INVÁLIDO`, `CNPJ INVÁLIDO` ou `SEM DOCUMENTO` (pelo tamanho e pelo dígito verificador).
3. Consulta na API só as linhas `CNPJ`.
4. Acrescenta as colunas pedidas. Em linhas que não são CNPJ, elas ficam vazias.

## Instalação

```bash
git clone <url-do-repo> consulta-cnpj
cd consulta-cnpj
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

Você passa um CSV com uma coluna de CPF/CNPJ, diz quais informações quer e onde gravar:

```bash
# colunas padrão: PORTE, NUMERO, NOME_FANTASIA, MATRIZ_FILIAL -> cadastro_cnpj.csv
python consulta_cnpj.py cadastro.csv

# outras colunas
python consulta_cnpj.py cadastro.csv -c RAZAO_SOCIAL,SITUACAO

# escolhe o nome de cada coluna: CAMPO=NOME
python consulta_cnpj.py cadastro.csv -c "RAZAO_SOCIAL=Razão Social,UF=Estado,MEI"

# grava em outro lugar
python consulta_cnpj.py cadastro.csv -c SITUACAO -o resultados/cadastro_ok.csv

# grava no próprio arquivo de entrada
python consulta_cnpj.py cadastro.csv -c SITUACAO --sobrescrever

# documentos direto no terminal (resultado na tela)
python consulta_cnpj.py 00.000.000/0001-91 360305000104 -c RAZAO_SOCIAL,SITUACAO

# lista dos campos disponíveis
python consulta_cnpj.py --colunas-disponiveis
```

| Opção | O que faz |
|---|---|
| `-c` | campos a acrescentar, `CAMPO` ou `CAMPO=NOME_DA_COLUNA`, separados por vírgula. Sem `-c`: `PORTE`, `NUMERO`, `NOME_FANTASIA`, `MATRIZ_FILIAL` |
| `--todas` | acrescenta todos os campos disponíveis |
| `-o` | arquivo de saída (`.csv` ou `.xlsx`). Padrão: `<entrada>_cnpj.csv`, na mesma pasta |
| `--sobrescrever` | grava no próprio arquivo de entrada |
| `--coluna-doc` | nome da coluna com o CPF/CNPJ, se ela não tiver `CPF`, `CNPJ` ou `DOC` no nome |
| `--atualizar` | ignora o cache e consulta tudo de novo |

**Entrada:** `.csv` (também aceita `.xlsx` e `.txt` com um documento por linha). Separador (`,` `;` tab) e codificação (UTF-8 ou Latin-1) são detectados e mantidos na saída. O documento pode vir com ou sem pontuação. Se vier sem os zeros à esquerda (planilha que tratou como número), até 11 dígitos conta como CPF quando o dígito verificador de CPF bate; senão, como CNPJ.

**Saída:** por padrão, um novo arquivo `<entrada>_cnpj.csv`, com todas as colunas originais, `TIPO_DOC` e as colunas pedidas no fim. Se uma coluna de destino já existe, ela é preenchida em vez de duplicada. CNPJ inválido ou que falhou na consulta tem o motivo na coluna `ERRO_CNPJ`.

**Campos disponíveis:** `CNPJ`, `RAZAO_SOCIAL`, `NOME_FANTASIA`, `SITUACAO`, `DATA_SITUACAO`, `MATRIZ_FILIAL`, `DATA_ABERTURA`, `CNAE`, `CNAE_DESCRICAO`, `CNAES_SECUNDARIOS`, `NATUREZA_JURIDICA`, `PORTE`, `PORTE_RECEITA`, `CAPITAL_SOCIAL`, `SIMPLES`, `MEI`, `LOGRADOURO`, `NUMERO`, `COMPLEMENTO`, `BAIRRO`, `CEP`, `MUNICIPIO`, `UF`, `TELEFONE`, `EMAIL`, `QTD_SOCIOS`, `SOCIOS`, `ERRO`.

**Porte:** a Receita classifica por faturamento anual em só três faixas, convertidas assim:

| Receita (`PORTE_RECEITA`) | `PORTE` |
|---|---|
| Micro empresa (inclui MEI; até R$ 360 mil) | PEQUENO |
| Empresa de pequeno porte (até R$ 4,8 mi) | MÉDIO |
| Demais (acima de R$ 4,8 mi) | GRANDE |

A Receita não separa médio de grande, então `GRANDE` inclui também empresas médias.

**`NUMERO`** é o número do endereço. **`MATRIZ_FILIAL`** é `MATRIZ` ou `FILIAL`.

## Cache

Cada resposta fica guardada em `~/.cache/consulta_cnpj/cache.jsonl`. Se a execução for interrompida, é só rodar de novo: continua de onde parou e não consulta o mesmo CNPJ duas vezes. Para buscar dados atualizados, use `--atualizar`.

A API limita o número de consultas por minuto; o script faz uma pausa entre elas e, se for bloqueado (HTTP 429), espera e tenta de novo.
