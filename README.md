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

Você passa um CSV com uma coluna de CNPJ, diz quais informações quer e onde gravar:

```bash
# colunas padrão: PORTE, NUMERO, NOME_FANTASIA, MATRIZ_FILIAL -> empresas_cnpj.csv
python consulta_cnpj.py empresas.csv

# outras colunas
python consulta_cnpj.py empresas.csv -c RAZAO_SOCIAL,SITUACAO

# escolhe o nome de cada coluna: CAMPO=NOME
python consulta_cnpj.py empresas.csv -c "RAZAO_SOCIAL=Razão Social,UF=Estado,MEI"

# grava em outro lugar
python consulta_cnpj.py empresas.csv -c SITUACAO -o resultados/empresas_ok.csv

# grava no próprio arquivo de entrada
python consulta_cnpj.py empresas.csv -c SITUACAO --sobrescrever

# CNPJs direto no terminal (resultado na tela)
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
| `--coluna-cnpj` | nome da coluna com o CNPJ, se ela não tiver "CNPJ" no nome |
| `--atualizar` | ignora o cache e consulta tudo de novo |

**Entrada:** `.csv` (também aceita `.xlsx` e `.txt` com um CNPJ por linha). Separador (`,` `;` tab) e codificação (UTF-8 ou Latin-1) são detectados e mantidos na saída. O CNPJ pode vir com ou sem pontuação e sem os zeros à esquerda.

**Saída:** o mesmo arquivo, com as colunas pedidas acrescentadas no fim. Se uma coluna de destino já existe no CSV, ela é preenchida em vez de duplicada, e as linhas cujo CNPJ falhou mantêm o valor que já tinham. Se algum CNPJ for inválido, não encontrado ou estiver vazio, o motivo aparece na coluna `ERRO_CNPJ`.

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
