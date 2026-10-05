# consulta-cnpj

Lê um CSV com CPFs e CNPJs, identifica o tipo de cada documento, consulta só os CNPJs na [BrasilAPI](https://brasilapi.com.br/docs#tag/CNPJ) (gratuita, sem chave, dados da Receita Federal), um por um, e grava um **novo CSV**, `cleandata-<cidade>.csv`, com tudo o que o arquivo já tinha mais as informações das empresas.


> **Sobre este projeto:** este script foi desenvolvido para um trabalho de análise de cadastro municipal, em que era preciso enriquecer uma lista de contribuintes com os dados públicos das empresas na Receita Federal. Ficou genérico o bastante para servir a qualquer lista de CNPJs, por isso está publicado aqui. Nenhum dado do trabalho original faz parte do repositório: as listas de entrada e os resultados ficam só na máquina de quem usa (ver `.gitignore`).

1. Acha a coluna do documento (nome com `CPF`, `CNPJ` ou `DOC`, ou a indicada em `--coluna-doc`).
2. Cria a coluna `TIPO_DOC`, logo depois dela: `CPF`, `CNPJ`, `CPF INVÁLIDO`, `CNPJ INVÁLIDO` ou `SEM DOCUMENTO` (pelo tamanho e pelo dígito verificador).
3. Consulta na API só as linhas `CNPJ`.
4. Acrescenta as colunas pedidas. Em linhas que não são CNPJ, elas ficam vazias; em CNPJ inválido ou que falhou na consulta, ficam com `ERRO_CNPJ`.

## Usar sem instalar nada

As APIs são online, então dá para usar sem baixar nada na máquina:

- **Um CNPJ por vez, no navegador:** cole na barra de endereços
  `https://brasilapi.com.br/api/cnpj/v1/{cnpj}` (só números). Ex.:
  <https://brasilapi.com.br/api/cnpj/v1/00000000000191>. Detalhes em [Endpoints](#endpoints).
- **Um CSV inteiro, no Google Colab** (Python no navegador, já vem com `pandas` e `openpyxl`):
  1. Abra <https://colab.research.google.com> → **Novo notebook**.
  2. No ícone de pasta (à esquerda), envie `consulta_cnpj.py` e o seu CSV.
  3. Rode numa célula:
     ```
     !python consulta_cnpj.py cadastro.csv
     ```
  4. Baixe o `cleandata-<cidade>.csv` gerado pelo mesmo painel de arquivos.

  Os arquivos do Colab somem quando a sessão fecha — baixe o resultado antes.
  O cache também se perde, então uma consulta interrompida recomeça do zero.

## Instalação

```bash
git clone https://github.com/PedroAlves21/consulta-cnpj.git
cd consulta-cnpj
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

Você passa um CSV com uma coluna de CPF/CNPJ, diz quais informações quer e onde gravar:

```bash
# colunas padrão -> cleandata-<cidade>.csv (cidade mais comum entre os CNPJs)
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
| `-c` | campos a acrescentar, `CAMPO` ou `CAMPO=NOME_DA_COLUNA`, separados por vírgula. Sem `-c`: `PORTE`, `NUMERO`, `NOME_FANTASIA`, `MATRIZ_FILIAL`, `TELEFONES`, `EMAIL` |
| `--todas` | acrescenta todos os campos disponíveis |
| `-o` | arquivo de saída (`.csv` ou `.xlsx`). Padrão: `cleandata-<cidade>.csv`, na pasta da entrada |
| `--cidade` | cidade do nome do arquivo (padrão: o município mais comum entre os CNPJs consultados) |
| `--sem-email` | não busca e-mail (é a parte lenta, ver abaixo) |
| `--sobrescrever` | grava no próprio arquivo de entrada |
| `--coluna-doc` | nome da coluna com o CPF/CNPJ, se ela não tiver `CPF`, `CNPJ` ou `DOC` no nome |
| `--atualizar` | ignora o cache e consulta tudo de novo |

**Entrada:** `.csv` (também aceita `.xlsx` e `.txt` com um documento por linha). Separador (`,` `;` tab) e codificação (UTF-8 ou Latin-1) são detectados e mantidos na saída. O documento pode vir com ou sem pontuação. Se vier sem os zeros à esquerda (planilha que tratou como número), até 11 dígitos conta como CPF quando o dígito verificador de CPF bate; senão, como CNPJ.

**Saída:** por padrão, um novo arquivo `cleandata-<cidade>.csv` (ex.: `cleandata-pinheiro.csv`) na pasta da entrada, com todas as colunas originais, `TIPO_DOC` e as colunas pedidas no fim. As colunas originais nunca são alteradas: se uma coluna nova tem o mesmo nome de uma que já existe (ex.: `NUMERO`), ela ganha o sufixo `_EMPRESA` (`NUMERO_EMPRESA`). Linhas de CNPJ inválido ou que falhou na consulta ficam com `ERRO_CNPJ` em todas as colunas geradas.

**Campos disponíveis:** `CNPJ`, `RAZAO_SOCIAL`, `NOME_FANTASIA`, `SITUACAO`, `DATA_SITUACAO`, `MATRIZ_FILIAL`, `DATA_ABERTURA`, `CNAE`, `CNAE_DESCRICAO`, `CNAES_SECUNDARIOS`, `NATUREZA_JURIDICA`, `PORTE`, `CAPITAL_SOCIAL`, `SIMPLES`, `MEI`, `LOGRADOURO`, `NUMERO`, `COMPLEMENTO`, `BAIRRO`, `CEP`, `MUNICIPIO`, `UF`, `TELEFONES`, `EMAIL`, `QTD_SOCIOS`, `SOCIOS`.

**`PORTE`:** como vem da Receita Federal, que classifica pelo faturamento anual: `MICRO EMPRESA` (inclui MEI; até R$ 360 mil), `EMPRESA DE PEQUENO PORTE` (até R$ 4,8 mi) ou `DEMAIS` (acima disso).

**`NUMERO`** é o número do endereço. **`TELEFONES`** traz todos os telefones da empresa separados por vírgula. **`MATRIZ_FILIAL`** é `MATRIZ` ou `FILIAL`.

**`EMAIL`:** a BrasilAPI não informa e-mail, então ele vem da [API aberta da CNPJá](https://cnpja.com/api/open), que aceita só 5 consultas por minuto: cerca de 12 s por CNPJ (500 CNPJs ≈ 1h45). Use `--sem-email` para pular essa etapa.

## Endpoints

O script usa duas APIs públicas, **gratuitas e sem chave**. As duas são `GET`, recebem o CNPJ **só com números** (14 dígitos, sem `.`, `/` ou `-`) no fim da URL e respondem em JSON. O script manda o cabeçalho `User-Agent: consulta-cnpj` e espera até 30 s por resposta.

### 1. BrasilAPI — dados cadastrais

```
GET https://brasilapi.com.br/api/cnpj/v1/{cnpj}
```

Exemplo (cole no navegador): <https://brasilapi.com.br/api/cnpj/v1/00000000000191>

```bash
curl https://brasilapi.com.br/api/cnpj/v1/00000000000191
```

| Resposta | O que o script faz |
|---|---|
| `200` | usa o JSON |
| `400` | CNPJ inválido → `ERRO_CNPJ` |
| `404` | CNPJ não encontrado → `ERRO_CNPJ` |
| `429` (muitas consultas) | espera 5, 10, 20… s (dobra a cada vez) e tenta de novo |
| outro erro / sem conexão | espera 1, 2, 4… s e tenta de novo |

São até 5 tentativas; se todas falharem, a linha fica com `ERRO_CNPJ`. Entre uma consulta e outra há uma pausa de 0,5 s. Documentação oficial: <https://brasilapi.com.br/docs#tag/CNPJ>.

**Resposta `200`** (trecho de `00000000000191`; campos que o script usa):

```json
{
  "cnpj": "00000000000191",
  "razao_social": "BANCO DO BRASIL SA",
  "nome_fantasia": "DIRECAO GERAL",
  "descricao_situacao_cadastral": "ATIVA",
  "data_situacao_cadastral": "2005-11-03",
  "descricao_identificador_matriz_filial": "MATRIZ",
  "data_inicio_atividade": "1966-08-01",
  "cnae_fiscal": 6422100,
  "cnae_fiscal_descricao": "Bancos múltiplos, com carteira comercial",
  "cnaes_secundarios": [{"codigo": 6499999, "descricao": "Outras atividades de serviços financeiros não especificadas anteriormente"}],
  "natureza_juridica": "Sociedade de Economia Mista",
  "porte": "DEMAIS",
  "capital_social": 120000000000,
  "opcao_pelo_simples": false,
  "opcao_pelo_mei": false,
  "descricao_tipo_de_logradouro": "QUADRA",
  "logradouro": "SAUN QUADRA 5 BLOCO B TORRE I, II, III",
  "numero": "SN",
  "complemento": "ANDAR T I SL S101 A S1602 ...",
  "bairro": "ASA NORTE",
  "cep": "70040912",
  "municipio": "BRASILIA",
  "uf": "DF",
  "ddd_telefone_1": "6134939002",
  "ddd_telefone_2": "",
  "qsa": [
    {"nome_socio": "ALAN CARLOS GUEDES DE OLIVEIRA", "qualificacao_socio": "Diretor", "cnpj_cpf_do_socio": "***550179**", "data_entrada_sociedade": "2023-05-17"}
  ]
}
```

A resposta completa tem outros campos (`codigo_porte`, `regime_tributario`, `motivo_situacao_cadastral`, …) que o script ignora. O campo `email` da BrasilAPI costuma vir `null`, por isso o e-mail vem da CNPJá.

**Resposta `400`** (dígito verificador errado):

```json
{"message": "CNPJ 00.000.000/0001-00 inválido.", "type": "bad_request", "name": "BadRequestError"}
```

**Resposta `404`** (CNPJ válido, mas não existe na Receita):

```json
{"message": "CNPJ 98.765.432/0001-98 não encontrado.", "type": "not_found", "name": "NotFoundError"}
```

De onde vem cada coluna (campo do JSON):

| Coluna | Campo na BrasilAPI |
|---|---|
| `RAZAO_SOCIAL` | `razao_social` |
| `NOME_FANTASIA` | `nome_fantasia` |
| `SITUACAO` / `DATA_SITUACAO` | `descricao_situacao_cadastral` / `data_situacao_cadastral` |
| `MATRIZ_FILIAL` | `descricao_identificador_matriz_filial` |
| `DATA_ABERTURA` | `data_inicio_atividade` |
| `CNAE` / `CNAE_DESCRICAO` | `cnae_fiscal` / `cnae_fiscal_descricao` |
| `CNAES_SECUNDARIOS` | `cnaes_secundarios[].codigo` |
| `NATUREZA_JURIDICA` | `natureza_juridica` |
| `PORTE` | `porte` |
| `CAPITAL_SOCIAL` | `capital_social` |
| `SIMPLES` / `MEI` | `opcao_pelo_simples` / `opcao_pelo_mei` |
| `LOGRADOURO` | `descricao_tipo_de_logradouro` + `logradouro` |
| `NUMERO`, `COMPLEMENTO`, `BAIRRO`, `CEP`, `MUNICIPIO`, `UF` | `numero`, `complemento`, `bairro`, `cep`, `municipio`, `uf` |
| `TELEFONES` | `ddd_telefone_1`, `ddd_telefone_2` |
| `SOCIOS` / `QTD_SOCIOS` | `qsa[].nome_socio` / tamanho de `qsa` |

### 2. CNPJá (API aberta) — e-mail

```
GET https://open.cnpja.com/office/{cnpj}
```

Exemplo: <https://open.cnpja.com/office/00000000000191>

Usada só para a coluna `EMAIL`, que a BrasilAPI não tem. O script lê `emails[].address` (em minúsculas, separados por vírgula).

| Resposta | O que o script faz |
|---|---|
| `200` | usa os e-mails (lista vazia = sem e-mail) |
| `400` / `404` | sem e-mail |
| `429` (muitas consultas) | espera 60 s e tenta de novo |
| outro erro / sem conexão | espera 1, 2, 4… s e tenta de novo |

Aceita só **5 consultas por minuto**, por isso o script espera 12,5 s entre elas. São até 10 tentativas por CNPJ. Documentação oficial: <https://cnpja.com/api/open>.

**Resposta `200`** (trecho de `00000000000191`; o script lê só `emails[].address`):

```json
{
  "taxId": "00000000000191",
  "alias": "Direcao Geral",
  "company": {"name": "BANCO DO BRASIL SA", "size": {"acronym": "DEMAIS"}, "...": "..."},
  "status": {"id": 2, "text": "Ativa"},
  "address": {"street": "Quadra Saun Quadra 5 Bloco B Torre I, II, III", "city": "Brasília", "state": "DF", "zip": "70040912"},
  "phones": [{"type": "LANDLINE", "area": "61", "number": "34939002"}],
  "emails": [{"ownership": "CORPORATE", "address": "secex@bb.com.br", "domain": "bb.com.br"}]
}
```

Resultado na coluna `EMAIL`: `secex@bb.com.br`. Se `emails` vier `[]`, a coluna fica vazia.

**Resposta `400`** (CNPJ inválido):

```json
{"code": 400, "message": "request validation failed", "constraints": ["taxId must be a string that obeys cnpj verification algorithm"]}
```

### Consultar pelo navegador (console)

Abra o console (F12 → **Console**) e rode:

```js
fetch('https://brasilapi.com.br/api/cnpj/v1/00000000000191')
  .then(r => r.json())
  .then(console.log)
```

> As duas APIs aceitam só **CNPJ**. CPF não tem consulta pública (LGPD); o script apenas marca `TIPO_DOC = CPF` e não consulta.

## Cache

Cada resposta fica guardada em `~/.cache/consulta_cnpj/` (`cache.jsonl` e `email.jsonl`). Se a execução for interrompida, é só rodar de novo: continua de onde parou e não consulta o mesmo CNPJ duas vezes. Para buscar dados atualizados, use `--atualizar`.

A API limita o número de consultas por minuto; o script faz uma pausa entre elas e, se for bloqueado (HTTP 429), espera e tenta de novo.

## Dados pessoais (LGPD)

O script só consulta dados públicos de **CNPJ** (Receita Federal). CPFs são apenas classificados (`TIPO_DOC`), nunca enviados a nenhuma API. Ainda assim, as listas de entrada e os CSVs gerados podem conter dados pessoais (nomes de sócios, telefones, e-mails): não os versione nem publique. O `.gitignore` já ignora `*.csv`, `*.xlsx` e `*.txt`.

## Licença

[MIT](LICENSE) — use, modifique e distribua à vontade, mantendo o aviso de copyright.
