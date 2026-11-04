#!/usr/bin/env bash
# Remove, de forma segura, UMA instância das Finanças Pessoais (a da pasta onde corre): contentores, rede, volumes
# (a base de dados!) e imagens do SEU projeto Compose. Nunca toca em contentores, volumes ou imagens de outros projetos.
#
# Pensado para refazer um teste de instalação sem comandos à mão. Antes de apagar mostra exatamente o que vai
# remover e pede que escreva o nome do projeto para confirmar. Não apaga backups (~/backup-*.sql) nem o .env de
# outras pastas.
#
# Uso:  scripts/uninstall.sh [opções]          (corre na pasta da instância a remover)
#   --dry-run          só mostra o que seria removido
#   --yes              não pede confirmação (as verificações de segurança mantêm-se)
#   --keep-images      não remove as imagens construídas
#   --delete-folder    no fim, apaga também a pasta desta instância (com verificações extra)
#   --project NOME     nome do projeto Compose (omissão: COMPOSE_PROJECT_NAME do .env desta pasta)
#   --orphan           o projeto pertence a uma pasta que já não existe (precisa de --project)
#   -h, --help
#
# Segurança: recusa se o projeto tiver contentores que pertencem a OUTRA pasta (por exemplo, a versão antiga), se
# o nome do projeto não estiver definido ou se não encontrar nada que seja desse projeto.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$(pwd)"

if [[ -t 1 ]]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'; else B=; G=; Y=; R=; N=; fi
say()  { printf '%s\n' "${B}==>${N} $*"; }
ok()   { printf '%s\n' "${G}✓${N} $*"; }
warn() { printf '%s\n' "${Y}!${N} $*" >&2; }
die()  { printf '%s\n' "${R}✗ $*${N}" >&2; exit 1; }

DRY=0 YES=0 KEEP_IMAGES=0 DELETE_FOLDER=0 ORPHAN=0 PROJECT="" PROJECT_FLAG=""
usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --yes) YES=1 ;;
    --keep-images) KEEP_IMAGES=1 ;;
    --delete-folder) DELETE_FOLDER=1 ;;
    --orphan) ORPHAN=1 ;;
    --project) PROJECT="${2:-}"; PROJECT_FLAG="$PROJECT"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Opção desconhecida: $1 (use --help)" ;;
  esac
  shift
done
[[ -t 0 ]] || YES=1   # sem terminal não há a quem perguntar (o nome do projeto continua obrigatório via --project/.env)

env_get() { [[ -f .env ]] && sed -n "s/^$1=//p" .env | tail -n1 || true; }

# ---------- motor ----------
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then ENGINE=docker
elif command -v podman >/dev/null 2>&1; then ENGINE=podman
else die "Não encontrei docker nem podman."; fi

# ---------- projeto ----------
[[ -n "$PROJECT" ]] || PROJECT="$(env_get COMPOSE_PROJECT_NAME)"
[[ -n "$PROJECT" ]] || die "Não sei qual é o projeto: esta pasta não tem COMPOSE_PROJECT_NAME no .env. Use --project NOME."
[[ "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "Nome de projeto inválido: «$PROJECT»."
[[ $ORPHAN -eq 0 || -n "$PROJECT_FLAG" ]] || die "--orphan exige --project NOME (o nome do projeto de que a pasta já não existe)."
LABEL="com.docker.compose.project=$PROJECT"

# ---------- o que existe ----------
mapfile -t CONTAINERS < <("$ENGINE" ps -a --filter "label=$LABEL" --format '{{.ID}} {{.Names}}' 2>/dev/null || true)
mapfile -t NETWORKS < <("$ENGINE" network ls --filter "label=$LABEL" --format '{{.Name}}' 2>/dev/null || true)
mapfile -t VOLUMES < <("$ENGINE" volume ls --filter "label=$LABEL" --format '{{.Name}}' 2>/dev/null || true)
# podman-compose pode não etiquetar volumes/redes: aceitam-se também os nomes exatos «<projeto>_<nome>»
while IFS= read -r v; do
  [[ -n "$v" && "$v" == "${PROJECT}_"* ]] && [[ ! " ${VOLUMES[*]:-} " == *" $v "* ]] && VOLUMES+=("$v")
done < <("$ENGINE" volume ls --format '{{.Name}}' 2>/dev/null || true)
while IFS= read -r n; do
  [[ -n "$n" && "$n" == "${PROJECT}_"* ]] && [[ ! " ${NETWORKS[*]:-} " == *" $n "* ]] && NETWORKS+=("$n")
done < <("$ENGINE" network ls --format '{{.Name}}' 2>/dev/null || true)

IMAGES=()
if [[ $KEEP_IMAGES -eq 0 ]]; then
  while IFS= read -r img; do
    base="${img#localhost/}"; base="${base%%:*}"
    for svc in backend frontend; do
      if [[ "$base" == "$PROJECT-$svc" || "$base" == "${PROJECT}_$svc" ]]; then IMAGES+=("$img"); fi
    done
  done < <("$ENGINE" images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null || true)
fi

[[ ${#CONTAINERS[@]} -gt 0 || ${#VOLUMES[@]} -gt 0 || ${#NETWORKS[@]} -gt 0 || ${#IMAGES[@]} -gt 0 ]] || {
  ok "Não encontrei nada do projeto «$PROJECT» (contentores, volumes, redes ou imagens). Nada a fazer."
  [[ $DELETE_FOLDER -eq 1 ]] || exit 0
}

# ---------- verificações de segurança ----------
for line in "${CONTAINERS[@]:-}"; do
  [[ -n "$line" ]] || continue
  cid="${line%% *}"
  wd="$("$ENGINE" inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$cid" 2>/dev/null || true)"
  if [[ -z "$wd" ]]; then
    die "Não consigo confirmar a que pasta pertence o contentor ${line#* }. Por segurança não removo nada."
  elif [[ "$wd" != "$ROOT" ]]; then
    if [[ $ORPHAN -eq 1 && ! -d "$wd" ]]; then :
    else die "O projeto «$PROJECT» pertence a OUTRA pasta ($wd), não a esta ($ROOT). Corra este script nessa pasta (ou, se essa pasta já não existe, use --orphan --project $PROJECT). Nada foi removido."; fi
  fi
done

# ---------- plano ----------
say "Instância a remover: projeto «$PROJECT» (pasta $ROOT)"
printf '  Contentores: %s\n' "${CONTAINERS[*]:+$(printf '%s; ' "${CONTAINERS[@]#* }")}"
printf '  Volumes (BASE DE DADOS): %s\n' "${VOLUMES[*]:-nenhum}"
printf '  Redes:       %s\n' "${NETWORKS[*]:-nenhuma}"
printf '  Imagens:     %s\n' "${IMAGES[*]:-nenhuma}"
TS_PORT="$(env_get TAILSCALE_HTTPS_PORT)"
[[ -z "$TS_PORT" ]] || printf '  Tailscale:   publicação HTTPS na porta %s\n' "$TS_PORT"
[[ $DELETE_FOLDER -eq 0 ]] || printf '  Pasta:       %s (será apagada)\n' "$ROOT"
echo "  ${Y}Não toca${N} em outros projetos, nem em backups (~/backup-*.sql)."
"$ENGINE" ps --format '{{.Names}}' 2>/dev/null | grep -v "^${PROJECT}[-_]" | sed 's/^/  Fica intacto:  /' || true

[[ $DRY -eq 0 ]] || { ok "(--dry-run) Nada foi removido."; exit 0; }

if [[ $YES -eq 0 ]]; then
  read -r -p "Para confirmar, escreva o nome do projeto ($PROJECT): " typed || typed=""
  [[ "$typed" == "$PROJECT" ]] || die "Cancelado. Nada foi removido."
fi

# ---------- remover (só o que foi listado) ----------
say "A remover"
exists() { "$ENGINE" inspect "$1" >/dev/null 2>&1; }
# Contentores em várias passagens: uns dependem de outros (frontend → backend → base de dados) e o motor recusa
# remover um contentor de que outro ainda depende. Repete-se até não sobrar nenhum (ou 5 passagens).
for pass in 1 2 3 4 5; do
  left=0
  for line in "${CONTAINERS[@]:-}"; do
    [[ -n "$line" ]] || continue
    cid="${line%% *}"
    exists "$cid" || continue
    if "$ENGINE" rm -f "$cid" >/dev/null 2>&1; then ok "contentor ${line#* }"; else left=1; fi
  done
  [[ $left -eq 0 ]] && break
done
for n in "${NETWORKS[@]:-}"; do [[ -n "$n" ]] && { "$ENGINE" network rm "$n" >/dev/null 2>&1 && ok "rede $n" || warn "rede $n não removida (em uso?)"; }; done
for v in "${VOLUMES[@]:-}"; do [[ -n "$v" ]] && { "$ENGINE" volume rm "$v" >/dev/null 2>&1 && ok "volume $v" || warn "volume $v não removido (em uso?)"; }; done
for i in "${IMAGES[@]:-}"; do [[ -n "$i" ]] && { "$ENGINE" image rm "$i" >/dev/null 2>&1 && ok "imagem $i" || warn "imagem $i não removida (em uso?)"; }; done

# Verificação: só se diz «removida» se mesmo não sobrar nada do projeto
REMAINING=0
for line in "${CONTAINERS[@]:-}"; do [[ -n "$line" ]] && exists "${line%% *}" && { warn "ainda existe o contentor ${line#* }"; REMAINING=1; }; done
for v in "${VOLUMES[@]:-}"; do [[ -n "$v" ]] && "$ENGINE" volume inspect "$v" >/dev/null 2>&1 && { warn "ainda existe o volume $v"; REMAINING=1; }; done
for n in "${NETWORKS[@]:-}"; do [[ -n "$n" ]] && "$ENGINE" network inspect "$n" >/dev/null 2>&1 && { warn "ainda existe a rede $n"; REMAINING=1; }; done
[[ $REMAINING -eq 0 ]] || die "Ficaram coisas por remover (acima). Volte a correr este script: retoma onde parou."

if [[ -n "$TS_PORT" ]] && command -v tailscale >/dev/null 2>&1; then
  if [[ $YES -eq 1 ]] || { read -r -p "Remover a publicação do tailscale na porta $TS_PORT? [S/n]: " a && [[ ! "${a,,}" =~ ^(n|nao|não|no)$ ]]; }; then
    [[ "$TS_PORT" != 443 ]] || warn "A porta é a 443: pode ser de outra instância; remova-a à mão se for mesmo esta."
    [[ "$TS_PORT" == 443 ]] || { tailscale serve --https="$TS_PORT" off >/dev/null 2>&1 && ok "tailscale serve --https=$TS_PORT off" || warn "Não consegui remover a publicação do tailscale (veja «tailscale serve status»)."; }
  fi
fi

if [[ $DELETE_FOLDER -eq 1 ]]; then
  # a pasta só se apaga se parecer MESMO uma instância das Finanças Pessoais e não for algo perigoso
  depth="$(awk -F/ '{print NF-1}' <<<"$ROOT")"
  [[ -f "$ROOT/scripts/install.sh" && -f "$ROOT/docker-compose.yml" && -d "$ROOT/.git" ]] || die "A pasta $ROOT não parece uma instância (falta install.sh, docker-compose.yml ou .git): não a apago."
  [[ "$ROOT" != "/" && "$ROOT" != "$HOME" && "$depth" -ge 3 ]] || die "Recuso apagar $ROOT (caminho demasiado perto da raiz ou da sua pasta pessoal)."
  if [[ $YES -eq 0 ]]; then
    read -r -p "Apagar também a pasta $ROOT? Escreva o nome do projeto para confirmar ($PROJECT): " typed2 || typed2=""
    [[ "$typed2" == "$PROJECT" ]] || { warn "Pasta mantida."; DELETE_FOLDER=0; }
  fi
  if [[ $DELETE_FOLDER -eq 1 ]]; then cd / && rm -rf -- "$ROOT" && ok "pasta $ROOT apagada"; fi
fi

ok "Instância «$PROJECT» removida."
echo "  Os backups (~/backup-*.sql) ficaram: contêm dados financeiros, apague-os quando já não precisar deles."
