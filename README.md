# personalFinanceAnalyzer

WebApp self-hosted (Docker Compose) para importar extratos bancários do Bankinter, reconciliar saldos, categorizar movimentos com regras locais e ver um dashboard (receitas, despesas, poupança, reserva, investido). Todos os dados ficam na máquina do utilizador, sem APIs externas.

Especificação completa: [PersonalFinances.md](PersonalFinances.md). Notas de trabalho para desenvolvimento: [CLAUDE.md](CLAUDE.md).

## O que faz

- **Importar** o `.xls` original do Bankinter (também aceita o CSV do modelo exato). A importação é **estrita**: qualquer desvio ao formato do banco é recusado e nada é gravado. Não guarde o ficheiro noutra aplicação antes de o importar.
- **Reconciliar** pela cadeia de saldos do ficheiro, avisar de buracos entre extratos e evitar duplicados quando os períodos se sobrepõem.
- **Categorizar**: regras (contém, começa por, igual, regex), histórico e categorização em lote por comerciante. As escolhas manuais nunca são sobrescritas e sobrevivem a reimportações.
- **Dashboard**: receitas, despesas, poupança, taxa de poupança, reserva (meses), dinheiro investido/poupado fora da conta, evolução mensal, despesas por categoria.
- **Multiutilizador com isolamento**: cada utilizador só vê as suas contas, movimentos, regras e categorias (cada um recebe a sua cópia das categorias iniciais). Sessões no servidor, CSRF e limite de tentativas de login. O isolamento é na aplicação: quem administra o servidor tem acesso à base de dados.

## Stack

Frontend: React 19 + Vite + TypeScript (servido por nginx, que faz proxy de `/api`). Backend: Python 3.12 + FastAPI + SQLAlchemy + Alembic. Base de dados: PostgreSQL 16.

## Instalação limpa (servidor)

Requisitos: Docker com Compose (ou Podman com `podman-compose`) e git. Não é preciso Node nem Python no servidor.

```bash
git clone https://github.com/JoaoBarreto/personalFinanceAnalyzer.git
cd personalFinanceAnalyzer
scripts/install.sh
```

O instalador faz as perguntas necessárias (com valores por omissão sensatos), escreve o `.env` (modo 600, password da base de dados gerada), arranca a aplicação, espera que responda e cria o primeiro utilizador. Também sabe, se quiser:

- **instalar ao lado de uma instância existente** (outra pasta, outro nome de projeto e outra porta) sem lhe tocar, por exemplo para testar uma versão nova;
- **copiar os dados** de uma instância antiga: faz um backup só de leitura e restaura-o na instalação nova antes de o backend arrancar (o utilizador e o nome da base de dados têm de coincidir);
- **publicar por HTTPS** com `tailscale serve` numa porta própria e **expor na rede local** (opcional);
- correr **sem perguntas** (`--yes` e flags, ver `scripts/install.sh --help`).

É seguro repetir: reconhece uma instância existente, atualiza-a e mantém os dados. Recusa restaurar por cima de dados e nunca usa `down -v`.

Manualmente, o mesmo faz-se assim: `cp .env.example .env` (pôr uma `POSTGRES_PASSWORD` forte), `docker compose up -d --build` e `make create-user USERNAME=joao NOME="João"`. Abra `http://127.0.0.1:8080` (porta `FRONTEND_PORT`), importe o extrato em «Importar» e categorize em «Por categorizar».

### Acesso remoto (recomendado): Tailscale

Por omissão a app só escuta em `127.0.0.1`. Para a aceder de outros dispositivos com HTTPS, sem abrir portas no router:

```bash
tailscale serve --bg --https=443 http://127.0.0.1:8080
```

Com HTTPS (`tailscale serve`) o cookie de sessão fica `Secure` automaticamente (`COOKIE_SECURE=auto`).

### Acesso direto na rede de casa (opcional, sem TLS)

Só numa rede de casa de confiança: a proteção passa a ser apenas a palavra-passe. Reserve o IP do servidor no router, ponha `LAN_BIND_IP=<ip>` no `.env` e arranque com os dois ficheiros:

```bash
docker compose -f docker-compose.yml -f docker-compose.lan.yml up -d --build
# ou, para não repetir os -f, no .env: COMPOSE_FILE=docker-compose.yml:docker-compose.lan.yml
```

Em http o cookie não pode ser `Secure`: com `COOKIE_SECURE=auto` isto trata-se sozinho (o cookie só é `Secure` por HTTPS). Se o login por http falhar em silêncio, force `COOKIE_SECURE=false`.

## Configuração (`.env`)

| Variável | Por omissão | Para quê |
|---|---|---|
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `pfa`, `pfa`, `change-me` | Base de dados. **Mudar a password.** |
| `COOKIE_SECURE` | `auto` | `auto`: Secure só por HTTPS; `true`/`false` forçam. |
| `TRUSTED_PROXIES` | vazio | IPs de proxies de confiança para ler `X-Forwarded-For`. |
| `FRONTEND_PORT` | `8080` | Porta no host (só em 127.0.0.1) do nginx. |
| `LAN_BIND_IP` | vazio | IP da LAN, só com `docker-compose.lan.yml`. |

Opcionais, só no backend: `DATABASE_URL` (substitui as variáveis `POSTGRES_*`), `ENABLE_DOCS=true` (liga `/docs` e `/openapi.json`, desligados por omissão), `SESSION_TTL_DAYS` (14), `LOGIN_MAX_FAILURES` (5) e `LOGIN_WINDOW_SECONDS` (300).

## Operação

- **Atualizar**: `git pull && docker compose up -d --build`. As migrações correm no arranque do backend; os dados mantêm-se no volume `pgdata`.
- **Nunca** correr `docker compose down -v`: apaga o volume `pgdata` e todos os dados. `docker compose down` (sem `-v`) é seguro.
- **Repor movimentos** de UM utilizador (apaga os seus movimentos e importações, mantém categorias, regras, contas e utilizadores; as categorizações manuais voltam a aplicar-se ao reimportar): `make reset-data USERNAME=joao`.
- **Backup**: ainda não está automatizado. Por agora, copie a base de dados à mão e guarde a cópia fora da máquina:
  ```bash
  docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup-$(date +%F).sql
  ```
  Restaurar numa instalação limpa: arrancar só a BD (`docker compose up -d db`), aplicar o ficheiro com `psql` e só depois arrancar o resto. Os backups contêm os seus dados financeiros: não os ponha no repositório.

## Desenvolvimento

```bash
cp .env.example .env
python3 -m venv backend/.venv
backend/.venv/bin/pip install -e "backend[dev]"
make test                                 # pytest (salta os testes com BD)
make test-db                              # idem + testes com BD num Postgres descartável (Docker/Podman)
make lint                                 # ruff
make test-frontend                        # typecheck + vitest num contentor node
make up                                   # db + backend + frontend em http://127.0.0.1:8080
```

Migrações à mão: `cd backend && DATABASE_URL=postgresql+psycopg://... .venv/bin/alembic upgrade head`. O `docker-compose.yml` foi testado com `podman-compose` e com Docker.

## Outros bancos e outros utilizadores

Qualquer banco com extrato tabular (.xls, .xlsx ou .csv, com coluna de saldo) pode ser adicionado pelo próprio utilizador em «Adicionar conta»: a aplicação deteta o formato, verifica-o pela cadeia de saldos e pede confirmação com exemplos, sem código. Os detalhes e os limites estão em [docs/novo-banco.md](docs/novo-banco.md). Os scripts de suporte estão em `scripts/`: `mask_statement.py` (estrutura do ficheiro com valores mascarados) e `check_statement.py <banco> ficheiro` (o parser aceita-o?).

## Dados e privacidade

Extratos reais e ficheiros de dados nunca vão para o repositório (ver `.gitignore`; `dados.csv` e `backend/tests/fixtures/local/` estão ignorados). Os fixtures de teste são sintéticos ou anonimizados. Credenciais (palavra-passe da BD, tokens do GitHub) ficam só no `.env` ou fora da máquina; use tokens de curta duração e revogue-os depois de usar.
