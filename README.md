# LucOps AI

Intelligent Data Quality & Reliability Platform

Plataforma de qualidade e confiabilidade de dados,
integrando Engenharia de Dados, Data Analytics,
Machine Learning, Inteligência Artificial e Cloud.

## Objetivo

Automatizar a validação de dados, identificar
inconsistências e anomalias e apoiar a investigação
de problemas por meio de inteligência artificial.

## Status

Em desenvolvimento.


## Visão geral

O LucOps AI é uma plataforma modular de qualidade e
monitoramento de dados empresariais.

Seu objetivo é automatizar a identificação de
inconsistências, gerar indicadores de qualidade
e fornecer informações para apoiar análises.

O projeto está em desenvolvimento e terá futuras
integrações com APIs, Machine Learning, agentes de IA
e serviços Cloud.

## Funcionalidades implementadas

- Leitura e validação de arquivos CSV.
- Verificação de campos obrigatórios.
- Validação de valores financeiros.
- Identificação de registros duplicados.
- Cálculo de indicadores de qualidade.
- Classificação do status da análise.
- Geração e salvamento de relatórios TXT.
- Interface de linha de comando (CLI).
- Testes automatizados com Pytest.
- Verificação de código com Ruff.

## Tecnologias

- Python
- Pytest
- Ruff
- Git e GitHub

## Arquitetura

O projeto utiliza uma arquitetura modular, com
responsabilidades separadas:

- `ingestion.py`: leitura de arquivos CSV.
- `core.py`: validação dos registros.
- `rules.py`: regras de negócio.
- `pipeline.py`: processamento e validações.
- `summary.py`: indicadores de qualidade.
- `status.py`: classificação da análise.
- `reporting.py`: geração e salvamento de relatórios.
- `application.py`: coordenação da análise completa.
- `__main__.py`: interface de linha de comando.

## Como executar

### 1. Preparar o ambiente

No PowerShell, na raiz do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 2. Executar uma análise

```powershell
.\.venv\Scripts\python.exe -m lucops data/sample/transacoes_invalidas.csv
```

O comando processa o CSV e gera um relatório em:

`reports/quality_report.txt`

Para escolher outro local de saída:

```powershell
.\.venv\Scripts\python.exe -m lucops data/sample/transacoes_invalidas.csv --output reports/minha_analise.txt
```

A CLI utiliza atualmente o esquema de transações
financeiras, com os campos obrigatórios:

- `id_transacao`
- `cliente_id`
- `valor`

A regra financeira exige valores positivos, com
no máximo duas casas decimais, e o identificador
da transação deve ser único.

## Testes automatizados

Executar todos os testes:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Verificar a qualidade do código:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
```

## Próximas evoluções

- API REST com FastAPI.
- Integração com bancos de dados.
- Dashboards e visualizações.
- Detecção de anomalias com Machine Learning.
- Agentes de IA para investigação de inconsistências.
- Integração com serviços Cloud.

