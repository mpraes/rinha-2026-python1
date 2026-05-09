# Rinha 2026 Python

Submissao para a Rinha de Backend 2026 com CPython no entrypoint, scripts e testes, e Cython no caminho quente do `POST /fraud-score`.

## Runtime

```sh
docker compose up --build
```

Topologia:

- `lb:9999`: HAProxy, apenas balanceamento round-robin.
- `api1` e `api2`: servidor HTTP proprio em CPython.
- `GET /ready`: `204 No Content`.
- `POST /fraud-score`: le bytes crus, chama `app.native.rinha_native` quando compilado e devolve JSON em bytes.

O servidor evita erros HTTP no caminho de fraude: falhas de parse, metodo ou rota retornam `HTTP 200` com resposta segura.

## Desenvolvimento

```sh
make test
make pack
make bench
```

`make test` usa apenas `unittest` da stdlib. O import de desenvolvimento cai para `app.native.fallback` quando a extensao Cython ainda nao foi compilada; a imagem Docker instala o pacote e importa a extensao nativa.

## Indice

`scripts/pack.py` gera `data/rinha.idx` com:

- header binario;
- vetores `int16[16]`;
- labels;
- centroides IVF;
- offsets de listas;
- indices dos pontos por cluster.

Arquivos `data/*.idx` ficam fora do Git.

## Estrategia

O runtime usa uma estrategia unica: busca IVF com um centroide sondado e indice em `data/rinha.idx`. O empacotador usa 32 centroides por padrao.