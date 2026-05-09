Tu conhece as competições de tinha de Backend?
Sr. Raposo — 13:43
Conheço sim
Mpraes — 13:43
Esse ano estão fazendo uma de busca vetorial
Exatamente o que precisamos aprender hehehe
Vou participar
Tem que criar uma API de busca vetorial num ambiente de 1cpu e 350mb ram
Aí tem gente usando knn
O que tu sugere se algoritmo pra busca vetorial nessas condições?
Sr. Raposo — 13:46
Depende de como seria a vetorizacao. Se forem vetores qualquer knn vai clusterizar vetores parecidos (ai você vai escolher uma métrica sei lá, tipo uma norma qualquer)
Se for vetores textuais, o embedding importa
Mpraes — 13:47
Ver número
Os dados estão num gzip
Vetor é numeros
Aí tem que buscar top algum coisa de vetores similares
Sr. Raposo — 13:47
E eu vi esse desafio aí. Os caras que proporam tem um grupo de dados que discutem o quanto eu sou infantil. Então você participar vai ser perfeito
Mpraes — 13:48
Opa
Vou comprar essa briga aí
Sr. Raposo — 13:48
Então, mas vetores similares a que? Tipo se for vetores aleatorios, eu teria que entender o que é o similar, aí clusterizar e comparar centroide faz sentido mesmo
Mas é complicado pensar nesse sentido de “similar” sem contexto
Mpraes — 13:49
Perai
O tema tem a ver com frade
Fraude
Se a transação que vem é ok ou não
Aí busca vetorial valores
Sr. Raposo — 13:50
Sendo vetores quaisquer, temos alguns passos pra escolher (e é foda porque não sei nem como será a avaliação disso). O primeiro é definir sua norma. Euclidiana seria a mais sensata aqui. Depois pensar em como agrupar vetores parecidos
Mpraes — 13:51
Calma aí
Sr. Raposo — 13:52
Pra fraude, você precisa entender o que é fraude e o que não é? Se for buscar os vetores que parecem fraude, knn acaba sendo estranho, a menos que você não tenha um fóruns truth pra comparar. Daí sim, seria algo não supervisionado
Mpraes — 13:53
https://github.com/mpraes/rinha-de-backend-2026/blob/main/docs%2Fbr%2FBUSCA_VETORIAL.md
GitHub
rinha-de-backend-2026/docs/br/BUSCA_VETORIAL.md at main · mpraes/r...
Rinha de Backend - Quarta Edição: Detecção de Fraude com Busca Vetorial - mpraes/rinha-de-backend-2026

Aqui tá completo
Para cada transação recebida, você transforma o payload em um vetor, busca no dataset de referência as transações mais parecidas e decide se aprova ou nega.
O dataset referência já existe lá
O foco aqui é mais software do que data science
E vejo que muito do pessoal que participa não manja muito danparta de DS
Sr. Raposo — 14:04
Dei uma lida inicial aqui. Bom se a limitação é memória e cada requisição deve rodar em uma instância com um core de cpu, você não pode paralelizar nada. 

Pensando que é um problema de comparar a distância do centroide, você precisa pensar no tamanho da tua base já que você precisa armazenar isso.
Mpraes — 14:05
Imagem
Esses são os dados pra comparação na requisição
Sr. Raposo — 14:06
Vai ter que salvar em arquivo se for usar alguma técnica de indexação prévia então em teoria pode rodar um processo inicial pra criar esse arquivo ou criar antes. Olha, no exemplo que ele deu, ele compara a distância de cada vetor certo? Primeira ideia que tenho, usar o cálculo do centroide e salvar apenas os centroides para comparação, você vai comparar bem menos vetores
Mpraes — 14:07
https://github.com/mpraes/rinha-de-backend-2026/blob/main/docs%2Fbr%2FDATASET.md
GitHub
rinha-de-backend-2026/docs/br/DATASET.md at main · mpraes/rinha-de...
Rinha de Backend - Quarta Edição: Detecção de Fraude com Busca Vetorial - mpraes/rinha-de-backend-2026
Rinha de Backend - Quarta Edição: Detecção de Fraude com Busca Vetorial - mpraes/rinha-de-backend-2026
Aqui é sobre o dataset
Importante. Os três arquivos não mudam durante o teste, então você pode pré-processá-los à vontade — descomprimir, indexar, converter para outro formato, etc.
Exemplo de requisição e resposta:

POST /fraud-score

Request:
{
  "id": "tx-123",
  "transaction": { "amount": 384.88, "installments": 3, "requested_at": "..." },
  "customer":    { "avg_amount": 769.76, "tx_count_24h": 3, "known_merchants": [...] },
  "merchant":    { "id": "MERC-001", "mcc": "5912", "avg_amount": 298.95 },
  "terminal":    { "is_online": false, "card_present": true, "km_from_home": 13.7 },
  "last_transaction": { "timestamp": "...", "km_from_current": 18.8 }
}

Response:
{ "approved": false, "fraud_score": 0.8 }
Sr. Raposo — 14:11
Se você tem a classificação do dataset, eu clusterizaria previamente via KNN (sei lá o cara deu uma viajada sobre KNN ali acredito). Daí você define tipo 4 ou 5 centroides pra cada tipo (visualiza em gráfico antes pra ter ideia da distribuição )
Se você medir a distância do centroide, se o cluster não for grande, você tem a mesma acurácia (ou quase) do que medir toda a base
Isso é uma forma de indexar
Mpraes — 14:12
Então, o pessoal tá muito focado no software somente
E não no algoritmo de busca vetorial
Entendo que dependendo do algoritmo aplicado já deve ajudar e muito na performance naom
?
Tipo, focado em linguagem e tal
Sr. Raposo — 14:14
Então, o algoritmo aí não tem muito o que pensar. É mais pensar na estratégia mesmo. E nesse caso, indexar é a melhor pedida
Mpraes — 14:14
A discussão lá
Imagem
Sr. Raposo — 14:16
XGBoost pra isso não sei vale não. Até porque o cara treina e classifica na hora rodando o aplicativo. A inferência do XGBoost vai te tomar uns ms mas pode ser uma ideia
Mpraes — 14:19
Dataset de referência:

[
  { "vector": [0.0100, 0.0833, 0.05], "label": "legit" },
  { "vector": [0.5796, 0.9167, 1.00], "label": "fraud" },
  { "vector": [0.0035, 0.1667, 0.05], "label": "legit" },
  { "vector": [0.9708, 1.0000, 1.00], "label": "fraud" },
  { "vector": [0.4082, 1.0000, 1.00], "label": "fraud" },
  { "vector": [0.0092, 0.0833, 0.05], "label": "legit" }
]
Mpraes — 14:35
Eu vou fazer esses passos aí mas com linguagens diferentes