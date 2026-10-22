# Investigação assistida por IA (Fase 6)

O comando independente usa o provedor determinístico por padrão:

```powershell
python -m lucops.agents investigate data/sample/transacoes_invalidas.csv --record-index 2 --no-ml
```

`--provider simulated` seleciona o mesmo modo explicitamente. O resultado
identifica `mode: simulated`; nenhuma chamada externa ocorre nesse modo.

O adaptador da OpenAI é opcional e usa a Responses API. Após a revisão do
código, a configuração de um limite de gastos e a autorização do primeiro teste,
instale o extra `agents` e configure **somente no ambiente do backend**:

| Variável | Função | Padrão |
| --- | --- | --- |
| `OPENAI_API_KEY` | Chave secreta; nunca deve ir ao navegador, CSV ou repositório | ausente |
| `LUCOPS_AGENT_OPENAI_MODEL` | Modelo da Responses API | `gpt-6-luna` |
| `LUCOPS_AGENT_OPENAI_MAX_CALLS` | Limite local de chamadas iniciadas por processo | `0` (desabilitado) |

Com autorização e as três configurações necessárias, a seleção é:

```powershell
python -m lucops.agents investigate data/sample/transacoes_invalidas.csv --record-index 2 --provider openai
```

A opção `--no-ml` continua disponível. O serviço aceita
`provider_mode="openai"`; sem seleção, mantém o modo simulado. Falhas da
OpenAI não acionam o provedor simulado. O SDK é importado somente ao executar o
modo OpenAI.

Na integração web, `POST /investigations` recebe um CSV, o índice do registro
(a partir de 1) e o provedor (`simulated` por padrão). O servidor reconstrói
qualidade, ML e evidências; não aceita scores enviados pelo navegador. CSV
inválido retorna HTTP 400, índice inexistente 404, parâmetros inválidos 422,
provedor indisponível 503, resposta inválida do provedor 502 e falha interna
500. As respostas de erro não incluem detalhes internos ou segredos.

No Streamlit, a seção **Investigação com IA** seleciona o registro pelo índice,
inclusive quando IDs estão vazios ou repetidos. A **Visão de negócio** mostra
registro, valor, qualidade, situação do ML, resumo fundamentado, evidências
principais, hipóteses não confirmadas, recomendações e limitações essenciais.
**Ver detalhes técnicos** mantém referências SHA-256 completas, scores,
origens, metadados e JSON para auditoria. Trocar CSV, registro ou provedor
limpa a investigação anterior. O modo `simulated` é identificado como resposta
determinística sem uso de LLM real.

Cada investigação envia no máximo uma requisição, sem tentativas automáticas,
com até 64 evidências e 12 KB de contexto serializado. A requisição limita
a saída a 1.200 tokens, usa timeout de 15 segundos, `reasoning.effort=none`,
`store=false` e não habilita ferramentas externas. O limite de chamadas é
por processo e reinicia quando o processo reinicia; **não substitui um teto de
gastos da conta/projeto OpenAI**. O custo depende dos tokens efetivamente usados
e dos preços vigentes. O endpoint não possui autenticação nesta fase; não
habilite chamadas pagas em uma API pública antes de definir controle de acesso
e limite de gastos externo ao processo.

Somente a transação selecionada, seus resultados de qualidade/ML e estatísticas
do CSV atual são transformados em um resumo mínimo. IDs pessoais, texto livre,
arquivo CSV completo e caminhos locais não são enviados. Os identificadores
SHA-256 das evidências permitem rastrear o CSV; não anonimizam o dataset.
O provedor devolve apenas hipóteses, recomendações e limitações. O serviço
reconstrói as evidências verificadas localmente e rejeita referências ausentes,
tipos inválidos e classificações diferentes de `unconfirmed`.

Um JSON válido e uma referência existente **não provam que a frase gerada é
verdadeira**. O prompt e a validação reduzem respostas sem suporte, mas uma
avaliação humana e testes adversariais ainda serão necessários antes de uso
empresarial. Scores de ML não são probabilidades nem confirmação de fraude.
Nenhuma correção automática é executada.
