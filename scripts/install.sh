#!/usr/bin/env bash
# Instalador interativo das Finanças Pessoais (Docker ou Podman Compose).
#
# Corre a partir da pasta do repositório. Faz perguntas com valores por omissão sensatos, escreve o .env (modo 600),
# arranca a aplicação, espera que responda e, se quiser, cria o primeiro utilizador, restaura um backup e configura
# o tailscale serve. Seguro de repetir: nunca apaga volumes (não usa `down -v`) e pede confirmação antes de
# qualquer passo que altere dados.
#
# Cada instância precisa da SUA pasta (o .env é por pasta): para testar uma versão nova ao lado da atual, clone o
# repositório noutra pasta e corra este script lá, com outro nome de projeto e outra porta.
#
# Uso:  scripts/install.sh [opções]        (sem opções: interativo)
#   --yes                 aceita os valores por omissão e nunca pergunta (modo não interativo)
#   --project NOME        nome do projeto Compose (isola contentores e volumes; omissão: nome da pasta)
#   --port N              porta no host (só 127.0.0.1) do frontend
#   --pg-user U --pg-db D --pg-password P   (ou PFA_PG_PASSWORD no ambiente; omissão: gerada)
#   --cookie-secure auto|true|false
#   --lan-ip IP           expõe também na rede local (http, sem TLS): só em redes de confiança
#   --backup-from DIR     faz pg_dump da instância antiga que corre em DIR (só leitura) antes de instalar
#   --backup-project N    nome do projeto Compose da instância antiga (omissão: nome da pasta DIR)
#   --restore FICHEIRO    restaura um pg_dump na base de dados NOVA (tem de estar vazia), antes do backend arrancar
#   --create-user NOME    cria o utilizador NOME (password em PFA_USER_PASSWORD, ou pedida)
#   --tailscale-port N    corre `tailscale serve --https=N` para esta instância (nunca a 443 sem confirmar)
#   -h, --help
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$(pwd)"

# ---------- utilitários ----------
if [[ -t 1 ]]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'; else B=; G=; Y=; R=; N=; fi
say()  { printf '%s\n' "${B}==>${N} $*"; }
ok()   { printf '%s\n' "${G}✓${N} $*"; }
warn() { printf '%s\n' "${Y}!${N} $*" >&2; }
die()  { printf '%s\n' "${R}✗ $*${N}" >&2; exit 1; }

YES=0
PROJECT="" PORT="" PG_USER="" PG_DB="" PG_PASSWORD="${PFA_PG_PASSWORD:-}" COOKIE="" LAN_IP=""
BACKUP_FROM="" BACKUP_PROJECT="" RESTORE="" CREATE_USER="" TS_PORT=""

usage() { sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) YES=1 ;;
    --project) PROJECT="$2"; shift ;;
    --port) PORT="$2"; shift ;;
    --pg-user) PG_USER="$2"; shift ;;
    --pg-db) PG_DB="$2"; shift ;;
    --pg-password) PG_PASSWORD="$2"; shift ;;
    --cookie-secure) COOKIE="$2"; shift ;;
    --lan-ip) LAN_IP="$2"; shift ;;
    --backup-from) BACKUP_FROM="$2"; shift ;;
    --backup-project) BACKUP_PROJECT="$2"; shift ;;
    --restore) RESTORE="$2"; shift ;;
    --create-user) CREATE_USER="$2"; shift ;;
    --tailscale-port) TS_PORT="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Opção desconhecida: $1 (use --help)" ;;
  esac
  shift
done

[[ -t 0 ]] || YES=1   # sem terminal não há a quem perguntar

# ask "pergunta" "omissão" -> escreve a resposta em REPLY
ask() {
  local q="$1" def="${2:-}"
  if [[ $YES -eq 1 ]]; then REPLY="$def"; return; fi
  read -r -p "$q${def:+ [$def]}: " REPLY || REPLY=""
  REPLY="${REPLY:-$def}"
}
# ask_yn "pergunta" s|n -> devolve 0 (sim) / 1 (não)
ask_yn() {
  local q="$1" def="${2:-n}" a
  if [[ $YES -eq 1 ]]; then [[ "$def" == s ]]; return; fi
  read -r -p "$q [$([[ $def == s ]] && echo S/n || echo s/N)]: " a || a=""
  a="${a:-$def}"; [[ "${a,,}" =~ ^(s|sim|y|yes)$ ]]
}
ask_secret() { # ask_secret "pergunta" -> REPLY (sem eco)
  if [[ $YES -eq 1 ]]; then REPLY=""; return; fi
  read -r -s -p "$1: " REPLY || REPLY=""; echo
}
gen_password() {
  if command -v openssl >/dev/null 2>&1; then openssl rand -base64 24 | tr -d '/+=\n' | head -c 24
  else LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24 || true; fi
}
env_get() { [[ -f .env ]] && sed -n "s/^$1=//p" .env | tail -n1 || true; }
port_busy() { command -v ss >/dev/null 2>&1 && ss -ltn "sport = :$1" 2>/dev/null | grep -q LISTEN; }

# ---------- motor de contentores ----------
if docker compose version >/dev/null 2>&1; then COMPOSE=(docker compose)
elif podman compose version >/dev/null 2>&1; then COMPOSE=(podman compose)
elif command -v podman-compose >/dev/null 2>&1; then COMPOSE=(podman-compose)
else die "Não encontrei docker compose, podman compose nem podman-compose."; fi
ok "Motor: ${COMPOSE[*]}"
compose() { "${COMPOSE[@]}" "$@"; }

# ---------- perguntas ----------
say "Configuração (Enter aceita o valor entre parênteses retos)"
DEF_PROJECT="$(env_get COMPOSE_PROJECT_NAME)"; DEF_PROJECT="${DEF_PROJECT:-$(basename "$ROOT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g')}"
[[ -n "$PROJECT" ]] || { ask "Nome do projeto Compose (isola contentores e volumes de outras instâncias)" "$DEF_PROJECT"; PROJECT="$REPLY"; }
[[ "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "Nome de projeto inválido (use minúsculas, números, - e _)."

EXISTING=0
if [[ -n "$(compose -p "$PROJECT" ps -q 2>/dev/null || true)" ]]; then
  EXISTING=1
  warn "O projeto «$PROJECT» já tem contentores: vou ATUALIZAR esta instância (os dados mantêm-se no volume)."
fi

if [[ -z "$PORT" ]]; then
  DEF_PORT="$(env_get FRONTEND_PORT)"; DEF_PORT="${DEF_PORT:-8080}"
  if [[ $EXISTING -eq 0 ]] && port_busy "$DEF_PORT"; then
    for p in 8081 8082 8083 8090; do port_busy "$p" || { DEF_PORT="$p"; break; }; done
    warn "A porta 8080 está ocupada (outra instância?); sugiro $DEF_PORT."
  fi
  ask "Porta no host (só 127.0.0.1)" "$DEF_PORT"; PORT="$REPLY"
fi
[[ "$PORT" =~ ^[0-9]+$ ]] && (( PORT > 0 && PORT < 65536 )) || die "Porta inválida: $PORT"
if [[ $EXISTING -eq 0 ]] && port_busy "$PORT"; then die "A porta $PORT já está ocupada. Escolha outra (--port)."; fi

DEF_PGUSER="$(env_get POSTGRES_USER)"; DEF_PGUSER="${DEF_PGUSER:-pfa}"
DEF_PGDB="$(env_get POSTGRES_DB)"; DEF_PGDB="${DEF_PGDB:-pfa}"
[[ -n "$PG_USER" ]] || { ask "Utilizador da base de dados" "$DEF_PGUSER"; PG_USER="$REPLY"; }
[[ -n "$PG_DB" ]]   || { ask "Nome da base de dados" "$DEF_PGDB"; PG_DB="$REPLY"; }
if [[ -z "$PG_PASSWORD" ]]; then
  PG_PASSWORD="$(env_get POSTGRES_PASSWORD)"
  if [[ -z "$PG_PASSWORD" || "$PG_PASSWORD" == change-me ]]; then
    PG_PASSWORD="$(gen_password)"; ok "Gerei uma password forte para a base de dados (fica só no .env)."
  else
    ok "Mantenho a password da base de dados já definida no .env."
  fi
fi
[[ -n "$COOKIE" ]] || { ask "Cookie de sessão seguro: auto (só por HTTPS), true ou false" "$(env_get COOKIE_SECURE)"; COOKIE="${REPLY:-auto}"; }
[[ "$COOKIE" =~ ^(auto|true|false)$ ]] || die "--cookie-secure deve ser auto, true ou false."
if [[ -z "$LAN_IP" && $YES -eq 0 ]]; then
  if ask_yn "Expor também na rede local (http, sem TLS; só em redes de confiança)?" n; then
    ask "IP deste computador na rede local" ""; LAN_IP="$REPLY"
  fi
fi

# ---------- backup da instância antiga (opcional, só leitura) ----------
if [[ -z "$BACKUP_FROM" && $YES -eq 0 && $EXISTING -eq 0 ]]; then
  if ask_yn "Quer copiar os dados de uma instância antiga que está a correr (faz um backup só de leitura)?" n; then
    ask "Pasta da instância antiga" ""; BACKUP_FROM="$REPLY"
  fi
fi
if [[ -n "$BACKUP_FROM" ]]; then
  [[ -d "$BACKUP_FROM" ]] || die "A pasta $BACKUP_FROM não existe."
  OLD_PROJECT="${BACKUP_PROJECT:-$(basename "$(cd "$BACKUP_FROM" && pwd)" | tr '[:upper:]' '[:lower:]')}"
  RESTORE_OUT="$HOME/backup-$(date +%Y%m%d-%H%M%S).sql"
  say "Backup de «$OLD_PROJECT» (só leitura) para $RESTORE_OUT"
  ( umask 077; cd "$BACKUP_FROM" && "${COMPOSE[@]}" -p "$OLD_PROJECT" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$RESTORE_OUT" ) \
    || { rm -f "$RESTORE_OUT"; die "Não consegui fazer o backup (a instância antiga está a correr? nome do projeto: $OLD_PROJECT; use --backup-project)."; }
  [[ -s "$RESTORE_OUT" ]] || { rm -f "$RESTORE_OUT"; die "O backup ficou vazio."; }
  ok "Backup feito ($(du -h "$RESTORE_OUT" | cut -f1)). Guarde-o fora desta máquina também."
  RESTORE="${RESTORE:-$RESTORE_OUT}"
  warn "Para o restauro funcionar, o utilizador e o nome da base de dados têm de ser iguais aos da instância antiga."
fi
if [[ -n "$RESTORE" ]]; then
  [[ -s "$RESTORE" ]] || die "O ficheiro de restauro $RESTORE não existe ou está vazio."
  [[ $EXISTING -eq 0 ]] || die "Só se restaura numa instância NOVA (esta já tem contentores): use outro --project e outra pasta."
fi

# ---------- escrever o .env (modo 600) ----------
if [[ -f .env ]] && [[ $YES -eq 0 ]] && ! ask_yn "Já existe um .env: substituir pelas respostas acima?" s; then
  die "Cancelado. Nada foi alterado."
fi
if [[ -f .env ]]; then cp -p .env ".env.bak.$(date +%Y%m%d-%H%M%S)"; fi
( umask 077
  {
    echo "# Gerado por scripts/install.sh. Nunca faça commit deste ficheiro."
    echo "COMPOSE_PROJECT_NAME=$PROJECT"
    echo "POSTGRES_DB=$PG_DB"
    echo "POSTGRES_USER=$PG_USER"
    echo "POSTGRES_PASSWORD=$PG_PASSWORD"
    echo "COOKIE_SECURE=$COOKIE"
    echo "TRUSTED_PROXIES=$(env_get TRUSTED_PROXIES)"
    echo "FRONTEND_PORT=$PORT"
    echo "LAN_BIND_IP=$LAN_IP"
    if [[ -n "$LAN_IP" ]]; then echo "COMPOSE_FILE=docker-compose.yml:docker-compose.lan.yml"; fi
  } > .env.new )
chmod 600 .env.new && mv .env.new .env
ok ".env escrito (modo 600; password não mostrada)."

# ---------- restauro (antes de o backend arrancar) ----------
if [[ -n "$RESTORE" ]]; then
  say "A restaurar $RESTORE na base de dados nova"
  compose up -d db
  for _ in $(seq 1 40); do compose exec -T db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1 && break; sleep 2; done
  n="$(compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*) from information_schema.tables where table_schema='"'"'public'"'"'"' | tr -d '[:space:]')"
  [[ "$n" == 0 ]] || die "A base de dados nova já tem $n tabelas: não restauro por cima. Use um projeto novo."
  compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$RESTORE" >/dev/null \
    || die "O restauro falhou. A instância antiga não foi tocada; apague este projeto (docker compose -p $PROJECT down -v NESTA pasta) e tente de novo."
  ok "Dados restaurados. O backend vai aplicar as migrações novas ao arrancar."
fi

# ---------- arrancar ----------
say "A construir e arrancar (pode demorar alguns minutos na primeira vez)"
compose up -d --build
URL="http://127.0.0.1:$PORT"
say "A esperar que a aplicação responda em $URL"
up=0
for _ in $(seq 1 60); do
  if command -v curl >/dev/null 2>&1 && [[ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/api/health" || true)" == 200 ]]; then up=1; break; fi
  command -v curl >/dev/null 2>&1 || { warn "curl não existe: não consigo verificar; veja os logs com «${COMPOSE[*]} logs backend»."; up=1; break; }
  sleep 2
done
[[ $up -eq 1 ]] || { compose logs --tail 30 backend || true; die "A aplicação não respondeu a tempo (logs acima)."; }
ok "A aplicação está a responder."

# ---------- primeiro utilizador ----------
if [[ -z "$CREATE_USER" && $YES -eq 0 ]]; then
  if ask_yn "Criar um utilizador agora?" s; then ask "Nome de utilizador (login)" ""; CREATE_USER="$REPLY"; fi
fi
if [[ -n "$CREATE_USER" ]]; then
  UPW="${PFA_USER_PASSWORD:-}"
  while [[ -z "$UPW" ]]; do
    ask_secret "Password para $CREATE_USER (mín. 10 caracteres)"; UPW="$REPLY"
    [[ $YES -eq 0 ]] || die "Defina PFA_USER_PASSWORD para criar o utilizador sem interação."
    ask_secret "Repita a password"; [[ "$REPLY" == "$UPW" ]] || { warn "Não coincidem."; UPW=""; continue; }
    (( ${#UPW} >= 10 )) || { warn "Mínimo 10 caracteres."; UPW=""; }
  done
  ask "Nome a mostrar" "$CREATE_USER"; DISPLAY_NAME="$REPLY"
  printf '%s\n' "$UPW" | compose exec -T backend python -m app.cli create-user "$CREATE_USER" --nome "$DISPLAY_NAME" --password-stdin \
    && ok "Utilizador «$CREATE_USER» criado." || warn "Não criei o utilizador (já existe?)."
fi

# ---------- tailscale (opcional) ----------
if [[ -z "$TS_PORT" && $YES -eq 0 ]] && command -v tailscale >/dev/null 2>&1; then
  if ask_yn "Publicar por HTTPS com o tailscale serve?" n; then
    ask "Porta HTTPS do tailscale (NÃO use 443 se já a usa para outra instância)" "8443"; TS_PORT="$REPLY"
  fi
fi
if [[ -n "$TS_PORT" ]]; then
  command -v tailscale >/dev/null 2>&1 || die "O tailscale não está instalado."
  if [[ "$TS_PORT" == 443 ]] && ! ask_yn "A porta 443 pode estar a servir outra instância. Substituir mesmo?" n; then die "Cancelado (tailscale)."; fi
  say "tailscale serve --bg --https=$TS_PORT $URL"
  tailscale serve --bg --https="$TS_PORT" "$URL" && ok "Publicado. Veja o endereço com «tailscale serve status»." \
    || warn "O tailscale serve falhou (a sintaxe muda entre versões): veja «tailscale serve --help»."
fi

# ---------- resumo ----------
cat <<EOF

${B}Pronto.${N}
  Endereço:        $URL${LAN_IP:+   e   http://$LAN_IP:$PORT}
  Projeto Compose: $PROJECT   (nesta pasta basta «${COMPOSE[*]} ...», o nome está no .env)
  Atualizar:       git pull && ${COMPOSE[*]} up -d --build
  Logs:            ${COMPOSE[*]} logs -f backend
  Criar utilizador: make create-user USERNAME=nome NOME="Nome"
  ${Y}Nunca use «down -v»: apaga a base de dados.${N}
EOF
