# Avaliacao reproduzivel de anomalias

Execute na raiz do projeto, no ambiente com o extra `ml`:

```powershell
.\.venv\Scripts\python.exe -m lucops.ml.evaluation
```

O comando imprime JSON no terminal e nao grava modelos. A CLI principal e os
comandos `lucops.ml train/analyze` permanecem inalterados.

## Protocolo

- Seed sintetica 42; fluxos aleatorios separados para treino e avaliacao.
- Treino: 1000 valores tipicos de uma distribuicao lognormal (media logaritmica
  5 e desvio logaritmico 0.35).
- Avaliacao: 200 novas amostras tipicas da mesma distribuicao, 10 extremos
  baixos entre 1 e 5 e 10 altos entre 1500 e 3000; ordem embaralhada.
- Valores positivos com duas casas decimais e IDs distintos entre conjuntos.
- Rotulos indicam a origem sintetica: extremo controlado ou amostra tipica.
- Isolation Forest existente: 100 arvores, random_state=42, contamination=auto.
- Referencia estatistica: quantis 1% e 99%, com interpolacao linear, calculados
  somente no treino. Valores fora do intervalo geram alertas.
- Parametros e quantis fixados antes de avaliar, sem busca ou ajuste no teste.

`evaluate_detector(training, evaluation, labels=None)` pode receber dados
preparados pelas entregas anteriores. Rejeita IDs repetidos ou compartilhados
entre conjuntos. Registros inelegiveis sao excluidos e contabilizados.
A verificacao de IDs ajuda a detectar sobreposicao, mas o chamador tambem deve
garantir a separacao real dos dados; renomear IDs nao elimina vazamento.

Rotulos opcionais devem mapear exatamente os IDs elegiveis da avaliacao para
booleanos. Sem rotulos, Precision/Recall/F1 nao sao calculados. Com rotulos,
o relatorio inclui matriz de confusao e quantidade de positivos. Divisoes
indefinidas recebem zero, convencao explicita no campo zero_division; ausencia
de positivos nao demonstra capacidade de deteccao.

Taxa de alertas e uma fracao entre 0 e 1. A distribuicao das pontuacoes inclui
minimo, p05, mediana, p95, maximo, media e desvio padrao populacional.
Pontuacao positiva gera alerta. No Isolation Forest usa-se -decision_function;
na referencia, max(limite_inferior - valor, valor - limite_superior).
As escalas sao diferentes e suas magnitudes nao devem ser comparadas.

## Resultado observado

Ambiente: Scikit-learn 1.9.1, NumPy 2.5.4. A reproducao exata requer as mesmas
versoes e configuracoes; o JSON registra versoes e parametros.

| Metodo | Alertas / 220 | Taxa | Verdadeiros positivos | Falsos positivos | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Isolation Forest | 79 | 35.91% | 20 | 59 | 25.32% | 100% | 40.40% |
| Quantis | 24 | 10.91% | 20 | 4 | 83.33% | 100% | 90.91% |

Limites da referencia: 68.7887 e 326.1401.

| Metodo | Minimo | p05 | Mediana | p95 | Maximo |
|---|---:|---:|---:|---:|---:|
| Isolation Forest | -0.066725 | -0.061090 | -0.024356 | 0.268620 | 0.279065 |
| Quantis | -128.4901 | -120.7271 | -59.6413 | 67.1402 | 2494.0699 |

## Interpretacao e limites

Ambos os metodos detectaram os 20 extremos controlados. O Isolation Forest
tambem marcou 59 amostras tipicas, enquanto a referencia marcou 4.
Neste experimento univariado a referencia teve melhor precisao e F1.
Nao ha evidencia aqui de superioridade do Isolation Forest nem motivo para
ajustar seus parametros usando este conjunto de avaliacao.

Os extremos sao deliberadamente faceis de separar. Uma amostra tipica pode
naturalmente cair na cauda e gerar alerta. Os rotulos sinteticos permitem
testar metricas, mas nao representam revisao humana de transacoes reais.
A prevalencia de extremos influencia a precisao e foi escolhida artificialmente.

Um unico atributo nao identifica comportamento por cliente, sazonalidade,
mudancas de distribuicao ou anomalias contextuais. O modelo tambem nao mede
a gravidade proporcional de valores muito alem da faixa de treino.
Anomalias nao confirmam fraude e nao alteram as validacoes tradicionais.

Antes de uso operacional: avaliar historico representativo com rotulos
revisados e separacao temporal. Se houver ajuste de parametros ou limiar,
usar validacao separada e reservar outro teste final intocado.
