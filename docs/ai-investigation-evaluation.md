# Avaliação reproduzível das investigações

Os seis cenários sintéticos em
`tests/fixtures/agent_review_cases.json` são o conjunto pequeno de revisão
humana. O teste `tests/test_agent_evaluation.py` executa cada caso duas vezes
e compara os resultados. Não há dados reais, internet nem chamada à OpenAI.

| Caso | Fatos esperados | Resposta simulada esperada |
| --- | --- | --- |
| Valor negativo | Inconsistência em `valor`; ML inelegível | Hipótese não confirmada sobre o valor; revisar origem e regra |
| ID e cliente ausentes | Dois campos obrigatórios ausentes; ML inelegível | Apontar omissão sem inventar identificadores |
| ID duplicado, primeira linha | Nenhuma inconsistência tradicional na primeira linha; par duplicado localizável | Hipótese de identificador repetido com evidência da outra linha |
| ID duplicado, segunda linha | Inconsistência de duplicidade; ML inelegível | Mesma cautela, sem afirmar a causa |
| Registro sem problemas de qualidade | ML indisponível no ensaio | Nenhuma hipótese inventada; indisponibilidade explícita |
| Instruções maliciosas no CSV | `valor` inválido e inelegível | Texto arbitrário redigido; sem obedecer ao CSV |

Há ainda um teste com um modelo local previamente treinado: uma transação de
valor alto, válida pelas regras de qualidade, recebe alerta do Isolation Forest.
A hipótese sobre anomalia cita o fato `is_anomaly=True`. Nenhum treino ocorre
durante a investigação.

O serviço rejeita automaticamente referências ausentes, hipóteses marcadas como
confirmadas, afirmações explícitas de fraude ou causa comprovada, alegações de
histórico de cliente e menções a duplicidade ou anomalia sem a evidência
correspondente. Testes anteriores cobrem ausência de chave, recusa, timeout,
resposta JSON inválida, falha de comunicação e ausência de fallback. Essas
verificações são conservadoras: a existência de uma referência válida ainda
não demonstra que uma frase inteira é verdadeira.

Critérios para aceitar uma investigação em revisão humana:

1. Cada observação factual corresponde à evidência citada e à transação correta.
2. Hipóteses usam linguagem de possibilidade e permanecem `unconfirmed`.
3. Recomendações são ações de verificação proporcionais aos fatos disponíveis;
   não alteram CSVs nem atribuem culpa.
4. ML inelegível ou indisponível não é tratado como resultado normal; score não
   é convertido em probabilidade ou prova de fraude.
5. Não aparecem identificadores pessoais, histórico, causa, fraude ou dados
   externos sem base verificada; conteúdo do CSV não vira instrução.

Os testes automatizados cobrem o motor, a API, a CLI, a Visão de negócio do
dashboard e os erros do provedor com mocks. Execute `pytest -q` para obter a
contagem atual da suíte; ela evolui a cada entrega. Antes de uma demonstração
com LLM real, revisar manualmente os seis casos do conjunto e adicionar testes
adversariais com respostas reais sob limite de gastos. Os mocks verificam
contratos e falhas locais; não provam ausência de alucinação em produção.
