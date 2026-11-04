# Segurança

## Reportar uma vulnerabilidade

Se encontrar uma falha de segurança (por exemplo, um utilizador conseguir ver dados de outro, contornar o login ou injetar código), **não abra um issue público**. Use o separador **Security → Report a vulnerability** deste repositório no GitHub, para o relato ficar privado. Indique os passos para reproduzir e a versão (`frontend/src/lib/about.ts`).

## O que a aplicação protege (e o que não)

- Login com palavra-passe (argon2), sessões no servidor, proteção CSRF e limite de tentativas de login.
- **Isolamento por utilizador na aplicação**: cada utilizador só vê as suas contas, movimentos, regras e categorias (`backend/tests/test_isolation.py`).
- Por omissão a app só escuta em `127.0.0.1`; para acesso remoto use HTTPS (por exemplo `tailscale serve`). Expor na rede local (`docker-compose.lan.yml`) é opcional e sem TLS: só em redes de confiança.
- **Quem administra o servidor tem acesso à base de dados** e, por isso, a todos os dados. Não há cifragem por utilizador.
- Os extratos importados e os backups contêm dados financeiros: guarde-os fora do repositório e do controlo de versões.

## Boas práticas ao instalar

- Use uma `POSTGRES_PASSWORD` forte (o `scripts/install.sh` gera uma).
- Nunca faça commit do `.env` nem de extratos reais (o `.gitignore` já os exclui).
- Mantenha a aplicação atualizada (`git pull && docker compose up -d --build`).
