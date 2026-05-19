Passo 1) Subir mudanças de código na branch main

git switch main
git pull --rebase origin main
git status
git add -A
git commit -m "feat: descreva a melhoria"
git push origin main
Passo 2) Gerar e publicar nova imagem linux/amd64

docker buildx build --platform linux/amd64 -t rmoraes4/rinha-2026-python1:latest --push .
docker buildx imagetools inspect rmoraes4/rinha-2026-python1:latest
No inspect, copie o digest sha256 da imagem publicada.

Passo 3) Atualizar branch submission (somente runtime)

git switch submission
git pull --rebase origin submission
editar docker-compose.yml e trocar o digest da imagem no campo image
git add docker-compose.yml
git commit -m "chore(submission): update image digest"
git push origin submission
Opcional: se mudou participante/social/stack, atualize também info.json na submission:

git add info.json
git commit -m "chore(submission): update info"
git push origin submission
Passo 4) Disparar novo teste oficial de prévia
No repositório oficial da Rinha (zanfranceschi/rinha-de-backend-2026), abra uma issue com:
Título: qualquer
Descrição: rinha/test seu-id-opcional

Exemplo de descrição:
rinha/test mpraes-python1

Se você usa GitHub CLI:

gh issue create -R zanfranceschi/rinha-de-backend-2026 -t "teste mpraes-python1" -b "rinha/test mpraes-python1"
Passo 5) Quando precisar registrar novo backend/repo
Só quando for uma nova submissão (novo id ou novo repositório), atualize seu arquivo em participants no repo oficial e abra PR.

Checklist rápido antes de abrir issue:

branch submission contém somente arquivos de execução
docker-compose.yml na raiz da submission
imagem pública acessível e compatível com linux/amd64
porta 9999 exposta via load balancer
limites de CPU/memória dentro das regras
Se quiser, eu te passo agora uma versão desses comandos já preenchida com seu id e com uma mensagem de commit padrão para cada etapa.