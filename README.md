# Rinha de Backend 2026 - Python Fraud Detection API

[English](#english) | [Português](#português)

---

<a name="english"></a>
## English

A high-performance fraud detection API built for **Rinha de Backend 2026**, implementing vector search for real-time credit card transaction analysis.

### Overview

This solution implements a fraud detection system that:
- Transforms transaction payloads into 14-dimensional vectors
- Uses IVF (Inverted File Index) for efficient nearest neighbor search
- Returns approval decisions with fraud scores in under 1ms (target)

### Tech Stack

- **Python 3.12** - Runtime environment
- **NumPy** - Vectorized operations for fast distance calculations
- **Nginx** - Load balancer with keep-alive connection pooling
- **Docker** - Containerized deployment

### Architecture

```
Client → Nginx (port 9999) → API Instance 1 (round-robin)
                             → API Instance 2 (round-robin)
```

**Resource Constraints:**
- Total CPU: 1 core (split: 0.45 + 0.45 + 0.1)
- Total Memory: 350 MB (split: 140M + 140M + 70M)
- 2 API instances + 1 load balancer

### How It Works

1. **Vectorization**: Each transaction is converted to a 14-dimensional normalized vector
2. **Clustering**: Reference vectors are pre-clustered using k-means (20 legit, 12 fraud centroids)
3. **Search**: Find nearest centroid, then search only within that cluster (50 candidates)
4. **Decision**: Among 5 nearest neighbors, count frauds → `fraud_score = frauds / 5`
5. **Response**: `approved = fraud_score < 0.6`

### Key Optimizations

- **RAM-loaded vectors**: All vectors loaded into memory at startup (not memmap)
- **Vectorized distance computation**: NumPy array operations instead of Python loops
- **O(N) selection**: `np.argpartition` instead of O(N log N) sort
- **Reduced candidates**: Only 50 candidates per class instead of full scan
- **HTTP keep-alive**: Persistent connections between nginx and API instances

### Running Locally

```bash
# Build and run
docker compose up --build

# Test endpoints
curl http://localhost:9999/ready
curl -X POST http://localhost:9999/fraud-score \
  -H "Content-Type: application/json" \
  -d '{"id":"test","transaction":{"amount":100,"installments":1,"requested_at":"2026-03-11T20:23:35Z"},"customer":{"avg_amount":100,"tx_count_24h":1,"known_merchants":[]},"merchant":{"id":"MERC-001","mcc":"5912","avg_amount":100},"terminal":{"is_online":false,"card_present":true,"km_from_home":10},"last_transaction":null}'
```

### Project Structure

```
├── src/
│   ├── server.py       # HTTP server with fraud detection logic
│   └── pack.py         # Index generation from reference data
├── resources/          # Reference data (mcc_risk.json, normalization.json)
├── Dockerfile          # Multi-stage build
├── docker-compose.yml  # Service orchestration
└── nginx.conf          # Load balancer configuration
```

---

<a name="português"></a>
## Português

Uma API de detecção de fraude de alta performance desenvolvida para a **Rinha de Backend 2026**, implementando busca vetorial para análise de transações de cartão de crédito em tempo real.

### Visão Geral

Esta solução implementa um sistema de detecção de fraude que:
- Transforma payloads de transações em vetores de 14 dimensões
- Utiliza IVF (Inverted File Index) para busca eficiente de vizinhos mais próximos
- Retorna decisões de aprovação com pontuações de fraude em menos de 1ms (alvo)

### Stack Tecnológica

- **Python 3.12** - Ambiente de execução
- **NumPy** - Operações vetorizadas para cálculos de distância rápidos
- **Nginx** - Load balancer com pooling de conexões keep-alive
- **Docker** - Implantação containerizada

### Arquitetura

```
Cliente → Nginx (porta 9999) → Instância API 1 (round-robin)
                                → Instância API 2 (round-robin)
```

**Restrições de Recursos:**
- CPU Total: 1 núcleo (divisão: 0.45 + 0.45 + 0.1)
- Memória Total: 350 MB (divisão: 140M + 140M + 70M)
- 2 instâncias API + 1 load balancer

### Como Funciona

1. **Vetorização**: Cada transação é convertida em um vetor normalizado de 14 dimensões
2. **Clustering**: Vetores de referência são pré-agrupados usando k-means (20 centróides legítimos, 12 de fraude)
3. **Busca**: Encontra o centróide mais próximo, depois busca apenas naquele cluster (50 candidatos)
4. **Decisão**: Entre os 5 vizinhos mais próximos, conta fraudes → `fraud_score = fraudes / 5`
5. **Resposta**: `approved = fraud_score < 0.6`

### Otimizações Chave

- **Vetores carregados na RAM**: Todos os vetores carregados na memória na inicialização (não memmap)
- **Computação de distância vetorizada**: Operações de array NumPy ao invés de loops Python
- **Seleção O(N)**: `np.argpartition` ao invés de ordenação O(N log N)
- **Candidatos reduzidos**: Apenas 50 candidatos por classe ao invés de escaneamento completo
- **HTTP keep-alive**: Conexões persistentes entre nginx e instâncias API

### Executando Localmente

```bash
# Construir e executar
docker compose up --build

# Testar endpoints
curl http://localhost:9999/ready
curl -X POST http://localhost:9999/fraud-score \
  -H "Content-Type: application/json" \
  -d '{"id":"test","transaction":{"amount":100,"installments":1,"requested_at":"2026-03-11T20:23:35Z"},"customer":{"avg_amount":100,"tx_count_24h":1,"known_merchants":[]},"merchant":{"id":"MERC-001","mcc":"5912","avg_amount":100},"terminal":{"is_online":false,"card_present":true,"km_from_home":10},"last_transaction":null}'
```

### Estrutura do Projeto

```
├── src/
│   ├── server.py       # Servidor HTTP com lógica de detecção de fraude
│   └── pack.py         # Geração de índice a partir dos dados de referência
├── resources/          # Dados de referência (mcc_risk.json, normalization.json)
├── Dockerfile          # Build multi-stage
├── docker-compose.yml  # Orquestração de serviços
└── nginx.conf          # Configuração do load balancer
```

---

## Author / Autor

**Renan de Moraes**
- GitHub: [@mpraes](https://github.com/mpraes)
- Open to work: Yes ✅

## License

MIT License - See [LICENSE](LICENSE) for details.
