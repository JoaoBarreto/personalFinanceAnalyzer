# PRD: WebApp de Análise de Extratos Bancários com Regras Locais

> **Versão:** 2.2 (contradições resolvidas e esquema da Fase 1 fechado; ver secções 4 e 10)
> **Estado:** MVP implementado e em uso; a versão 0.2.0 (ramo `multiutilizador`) diverge desta especificação nos pontos do quadro seguinte.
> **Âmbito:** Uso pessoal ou familiar (vários utilizadores, cada um com os seus dados), self-hosted em Docker num mini-PC, com acesso remoto via Tailscale e sem dependência de APIs pagas.
> **Banco no MVP:** Bankinter Portugal.

---

## Alterações face a esta especificação (v0.2.0, 2026-11)

Esta especificação descreve o desenho inicial. O que está implementado diverge nos pontos abaixo; quando houver conflito, **vale esta lista** (e o `CLAUDE.md`, que tem os detalhes técnicos).

| Tema | Na especificação | O que está implementado |
|---|---|---|
| Utilizadores (3.1.1, tabela de decisões 2) | 2 logins, dados **partilhados**, sem papéis | **Multiutilizador isolado**: cada utilizador só vê as suas contas, movimentos, regras e categorias (`dono_id`, migração 0006). Qualquer pessoa é um utilizador normal; o isolamento é na aplicação (o administrador do servidor vê a BD). |
| Titular e conta conjunta (secção 4, decisão 14) | `contas.titular_id`, NULL = conjunta | **Removidos.** Cada conta tem um dono; não há contas conjuntas nem filtro de titular. |
| Categorias (3.7) | Seed global | **Por utilizador**: cada utilizador recebe a sua cópia do seed ao ser criado (inclui «Poupança/Investimento», do tipo transferência). Regras e histórico de categorização também são por utilizador. |
| Transferências nos totais (3.9, secção 5) | Excluídas por omissão, com seletor «incluir transferências» | **Contam como movimentos normais** (sem seletor). A **taxa de poupança** usa receitas e despesas sem transferências, por isso o dinheiro enviado para poupança/investimento conta como poupado. |
| Dashboard (3.9) | Receitas, despesas, poupança, categorias, evolução | Acrescenta **reserva (meses)**, **taxa de poupança acumulada e média de 6 meses**, **investido/poupado fora da conta**, escala do eixo Y com marcas redondas e o mês em curso fora das taxas e da poupança mensal. |
| Bancos (3.3, decisão 1) | Só Bankinter no MVP; novos bancos = novo parser | **Qualquer banco** com extrato tabular (.xls, .xlsx, .csv) **com coluna de saldo**: o assistente «Adicionar conta» deteta o formato, verifica-o pela cadeia de saldos e pede confirmação ao utilizador (parser genérico por modelo guardado em `contas.config_importacao`). O Bankinter mantém o parser dedicado. PDF continua fora. |
| Formato de importação (3.2) | CSV/XLSX | O `.xls` original do Bankinter é o formato principal; o `.xlsx` só é aceite no parser genérico. |
| Criação de utilizadores | Criados pelo administrador na CLI | **Registo no ecrã de login** (o primeiro utilizador sempre; depois `ALLOW_REGISTRATION`, com limite por IP). `make create-user` continua como ferramenta de administração. |
| Instalação (secção 6) | `docker compose up` manual | `scripts/install.sh` interativo (instalação ao lado de outra instância, backup/restauro, tailscale opcional). |

---

## 1. Visão Geral

WebApp containerizada (Docker Compose) para importar movimentos bancários (**Excel/CSV exportado do homebanking** como via principal no MVP, **PDF do extrato mensal** a partir da Fase 1b), extrair e validar os movimentos, guardá-los num histórico em PostgreSQL e apresentar um **dashboard interativo**.

A categorização é feita por um **motor de regras local** gerido pelo utilizador, com **aprendizagem local** a partir das categorizações manuais. Não existem custos com APIs de IA e nenhum dado financeiro sai da máquina do utilizador.

### 1.1. Objetivos
- Importar um extrato mensal em menos de 1 minuto, incluindo revisão.
- Ter ≥ 90% dos movimentos categorizados automaticamente após 2–3 meses de uso.
- Garantir que os totais importados batem **ao cêntimo** com o extrato original.
- Manter os dados 100% locais e privados.

### 1.2. Fora de âmbito (por agora)
- Ligação direta aos bancos (Open Banking / PSD2).
- Multiutilizador com dados separados por pessoa, papéis ou permissões. Há 2 logins (dois utilizadores do mesmo agregado), mas **os dados são partilhados**.
- Cartões de crédito (não existem).
- App móvel nativa.
- OCR de extratos digitalizados (fica para a Fase 3).

---

## 2. Arquitetura & Stack

Tudo corre via `docker-compose.yml` com três serviços: `frontend`, `backend` e `db`.

| Camada | Escolha | Justificação |
|---|---|---|
| Frontend | **React + Vite + TypeScript** | SPA simples; não precisa de SSR. Servida por nginx. (Next.js também serve, mas acrescenta complexidade sem ganhos aqui.) |
| UI / Gráficos | Tailwind + shadcn/ui, **Recharts** ou ECharts, **TanStack Table** | Componentes modernos, tabelas com filtros/ordenação/paginação. |
| Backend | **Python 3.12 + FastAPI** | Excelente para parsing de ficheiros. |
| ORM / Migrações | **SQLAlchemy 2.0 + Alembic** | O esquema vai evoluir; as migrações são obrigatórias desde o dia 1. |
| Validação | Pydantic v2 | Contratos da API tipados. |
| Base de dados | **PostgreSQL 16** | Volume persistente nomeado. |
| Parsing PDF | **pdfplumber** (principal), `pypdf` para metadados | `PyPDF2` está descontinuado; o pdfplumber permite extrair tabelas e coordenadas. |
| Matching | `rapidfuzz`, `unidecode`, (opcional) `scikit-learn` | Normalização e fuzzy matching locais, sem custos. |

**Decisões importantes:**
- Os montantes guardam-se em `NUMERIC(12,2)` e `Decimal` em Python. **Nunca em float.**
- O processamento é síncrono no MVP (um PDF mensal demora segundos). Uma fila (Celery/RQ) só entra se for necessária.
- O Postgres **não expõe porta** para o host; só o backend lhe acede pela rede interna do Docker.
- A app faz bind a `127.0.0.1` por omissão.

---

## 3. Funcionalidades

### 3.1. Contas
- O utilizador cria uma ou mais contas bancárias (ex.: "Bankinter Ordenado", "Bankinter Poupança"). Só contas à ordem/poupança; não há cartões de crédito.
- Cada conta tem banco, IBAN mascarado (opcional), moeda, o **parser** associado e um **titular** opcional (para filtrar por titular; substituído entretanto pelo isolamento por dono, ver o quadro no topo).

### 3.1.1. Utilizadores
- **2 utilizadores** com login próprio. Ambos veem e editam os mesmos dados (contas, movimentos, regras, categorias).
- Sem papéis nem permissões no MVP: os dois utilizadores têm acesso total.
- Cada movimento e regra regista `criado_por`/`atualizado_por`, para se saber quem categorizou o quê.
- Os utilizadores são criados por comando CLI (`make create-user`). Não há registo público.

### 3.2. Importação de extratos

**Fluxo em 3 passos: Upload → Pré-visualização → Confirmação.**

1. **Upload**
   - Drag-and-drop de um ou vários ficheiros. **MVP: CSV e XLSX. PDF só a partir da Fase 1b.**
   - Validação do MIME type real (não só da extensão), limite de tamanho (ex.: 10 MB) e, na Fase 1b, rejeição de PDFs encriptados, com mensagem clara.
   - Deteção automática do banco/layout (ver 3.3). Se falhar, o utilizador escolhe manualmente.
2. **Pré-visualização**
   - Tabela com os movimentos extraídos, a categoria sugerida e indicadores de:
     - duplicados (já existentes na BD);
     - linhas com baixa confiança no parsing.
   - **Reconciliação de saldos:** `saldo_anterior + montante = saldo_apos` em cada linha e `saldo inicial + Σ movimentos = saldo final`. O saldo inicial e a ordem do ficheiro derivam-se da cadeia de saldos (ver 4.3). Se não bater, a importação fica em `preview` com a diferença visível e **não pode ser confirmada** até reconciliar (a reconciliação corre sobre todas as linhas do ficheiro após correções; excluir uma linha só evita a gravação).
   - Permite corrigir ou excluir linhas antes de gravar. As linhas ficam guardadas em `importacoes.staging` até à confirmação (ver 4.2).
3. **Confirmação**
   - O pedido traz as linhas excluídas e as correções; o servidor volta a reconciliar antes de gravar.
   - O registo de **Importação** guarda ficheiro, hash SHA-256, data, conta, nº de movimentos, nº de duplicados ignorados e estado.
   - **Uma importação pode ser revertida** (apaga os movimentos dessa importação), exceto se uma importação posterior sobreposta na mesma conta depender dela (ver 4.2).
   - O mesmo ficheiro (mesmo hash) não pode estar confirmado duas vezes; depois de revertido, pode ser reimportado.
   - Linhas já existentes na BD (períodos sobrepostos) são ignoradas segundo as regras de 4.1.

### 3.3. Motor de extração (parsers)

O parsing de PDFs bancários é **a parte mais difícil e frágil do projeto**: cada banco tem um layout diferente, que pode mudar sem aviso.

- **Arquitetura de plugins:** um parser por banco/layout, todos com a mesma interface:
  ```python
  class StatementParser(Protocol):
      bank_id: str
      def can_parse(self, pdf: PDFDocument) -> float: ...  # confiança 0..1
      def parse(self, pdf: PDFDocument) -> ParsedStatement: ...
  ```
- `ParsedStatement` contém: período, saldo inicial, saldo final e uma lista de movimentos (`data_movimento`, `data_valor`, `descricao_original`, `montante` com sinal, `saldo_apos` quando existir).
- **Formatos portugueses:** datas `dd-mm-aaaa`/`dd.mm`, números `1.234,56`, débito/crédito em colunas separadas ou com sinal, descrições que continuam na linha seguinte, cabeçalhos e rodapés repetidos em cada página.
- **Importador CSV/XLSX genérico** com mapeamento de colunas configurável e guardado por conta (`contas.config_importacao`). Quase todos os bancos portugueses exportam CSV/Excel, um formato muito mais fiável do que o PDF. Serve de *fallback* e é recomendado como alternativa.
- **Testes com fixtures:** cada parser tem ficheiros de exemplo (Excel/PDF) **anonimizados** e o resultado esperado em JSON. Uma alteração de layout tem de partir um teste, não corromper dados em silêncio.
- **MVP: só Bankinter.** Ver a estratégia em 3.3.1.

### 3.3.1. Estratégia Bankinter: Excel primeiro, PDF depois
Para análise, **o Excel/CSV exportado do homebanking é melhor do que o PDF**:

| | Excel/CSV (exportação de movimentos) | PDF (extrato mensal) |
|---|---|---|
| Fiabilidade da extração | Muito alta (colunas estruturadas) | Média (depende do layout, das quebras de página e das descrições que continuam na linha seguinte) |
| Esforço de desenvolvimento | Baixo | Alto |
| Robustez a mudanças do banco | Alta | Baixa |
| Período | Qualquer intervalo de datas | Mês fechado |
| Saldos para reconciliação | Normalmente traz o saldo após cada movimento | Saldo inicial e final oficiais |

**Decisão:**
1. **MVP:** parser `bankinter_xlsx` (e CSV, se o export o permitir) como via principal de importação. A reconciliação é feita pela coluna de saldo: `saldo_anterior + montante = saldo_apos` em cada linha.
2. **Fase 1b:** parser `bankinter_pdf` para extratos mensais e histórico antigo que só exista em PDF.
3. Os dois parsers produzem o mesmo `ParsedStatement`, e a deduplicação (4.1, sem depender da descrição) garante que importar o mesmo mês por Excel e por PDF não cria duplicados.

**Pressupostos do parser Bankinter, todos a validar com o fixture real** (não inventar antes de ver o ficheiro): nomes e ordem das colunas, formato das datas e dos números, se o ficheiro vem do mais recente para o mais antigo, se há linhas de cabeçalho/rodapé, qual a data comum ao Excel e ao PDF, e se o PDF traz saldo por linha.

**Input necessário:** 1 exportação Excel e 1 extrato PDF do Bankinter, **do mesmo mês**, anonimizados (nome, morada, IBAN). Assim dá para validar que os dois dão o mesmo resultado.

### 3.4. Normalização de descrições
Antes de aplicar regras, cada descrição é normalizada para `descricao_normalizada`:
- maiúsculas, sem acentos (`unidecode`), espaços colapsados;
- remoção de ruído: prefixos (`COMPRA`, `PAG.`, `TRF`, `DD`, `MB WAY`), números de cartão, referências, datas/horas embebidas, códigos de terminal.

Exemplo: `COMPRA 4532 FNAC CHIADO LISBOA 12/03 REF 88231` → `FNAC CHIADO LISBOA`.

A descrição original é sempre preservada.

### 3.5. Motor de regras
Cada regra tem:

| Campo | Descrição |
|---|---|
| `padrao` | Texto ou regex |
| `tipo_match` | `contem` · `comeca_por` · `igual` · `regex` |
| `categoria_id` | Categoria a atribuir |
| `direcao` | `debito` · `credito` · `ambos` |
| `montante_min/max` | Opcional (ex.: distinguir pagamentos pequenos e grandes no mesmo comerciante) |
| `conta_id` | Opcional (regra válida só para uma conta) |
| `prioridade` | Resolve conflitos. Desempate, por esta ordem: maior `prioridade`; tipo mais específico (`igual` > `comeca_por` > `contem` > `regex`); padrão mais longo; regra mais antiga (menor `id`). |
| `origem` | `manual` · `aprendida` |
| `ativa`, `n_aplicacoes` | Gestão e estatísticas |

**Pipeline de categorização** (pela ordem seguinte; a primeira que resultar ganha):
1. Regras do utilizador (por prioridade).
2. **Match exato** com uma descrição normalizada já categorizada no histórico.
3. **Fuzzy match** (`rapidfuzz`, limiar configurável, ex.: ≥ 90) contra o histórico → fica como *sugestão*, não como atribuição definitiva.
4. *(Opcional, Fase 2)* Classificador local (Naive Bayes / TF-IDF em scikit-learn) treinado com o histórico do próprio utilizador → *sugestão* com % de confiança.
5. Sem resultado → **"Por Categorizar"**.

Cada movimento guarda `categoria_origem` (`regra`, `historico`, `fuzzy`, `ml`, `manual`) e o `regra_id` aplicado, para se perceber *porque* foi categorizado assim.

**Regra de ouro:** uma categorização **manual nunca é sobrescrita** por regras (`categoria_origem = 'manual'`), seja na importação, na edição de regras ou na aplicação retroativa.

**Âmbito no MVP:** a UI só expõe `contem` e `comeca_por`; o esquema já inclui `igual`, `regex`, `direcao` e `montante_min/max` com defaults neutros para a Fase 2 não exigir migração. No MVP, os passos 1 e 2 do pipeline atribuem categoria; fuzzy e ML (passos 3 e 4) são Fase 2. "Por Categorizar" significa `categoria_id IS NULL` (não há categoria com esse nome).

### 3.6. Categorização manual & aprendizagem local
- Badge/notificação no dashboard com o nº de movimentos "Por Categorizar".
- Ecrã dedicado com:
  - **Agrupamento por descrição normalizada** (ex.: "12 movimentos LIDL"), para categorizar todos de uma vez;
  - atalhos de teclado para triagem rápida;
  - seleção múltipla e categorização em lote.
- **Aprendizagem com confirmação:** ao categorizar, a app *propõe* uma keyword extraída (ex.: `FNAC`, e não `FNAC CHIADO LISBOA 12/03`), que o utilizador pode editar antes de gravar. Guardar a descrição completa como keyword gera regras inúteis; uma keyword demasiado curta (ex.: `PAG`) gera falsos positivos.
  - Alerta quando a nova regra também apanharia movimentos já categorizados com outra categoria.
- **Aplicação retroativa:** ao criar ou editar uma regra, a app mostra quantos movimentos existentes seriam afetados e pergunta se a deve aplicar a esses movimentos. **Movimentos com `categoria_origem = 'manual'` são sempre ignorados** e não entram na contagem.

### 3.7. Categorias
- **Hierárquicas (2 níveis):** ex.: `Casa > Eletricidade`, `Alimentação > Supermercado`, `Alimentação > Restaurantes`.
- Seed inicial com categorias comuns em PT (editáveis).
- Tipos de categoria: `despesa`, `receita` e **`transferência`**.
  - **Transferências entre contas próprias** (ex.: à ordem → poupança, ou entre as contas do casal) **são excluídas dos totais**, para não haver contagem dupla. A única fonte de verdade é `categorias.tipo = 'transferencia'`. **MVP:** categorizadas por regra ou manualmente. **Fase 2:** deteção assistida (valor simétrico entre duas contas próprias em ±3 dias), que sugere o par e a categoria.
- Cor e ícone por categoria (usados nos gráficos).

### 3.8. Gestão de movimentos
- **MVP:** editar categoria e notas; pesquisa de texto livre.
- **Fase 2:** **tags** livres (ex.: `#ferias-2026`); marcar como reembolso/estorno (associar ao movimento original); **dividir movimento** (*split*), ex.: uma compra no hipermercado com parte alimentação e parte casa.
  - Os splits ficam numa tabela própria (`movimento_divisoes`), e não como movimentos-filho. Assim, as linhas de `movimentos` continuam a corresponder 1:1 ao extrato e a reconciliação e a deduplicação não são afetadas. Nas agregações, um movimento com divisões conta pelas suas divisões, nunca pelo total e pelas divisões.

### 3.9. Dashboard & Analytics
**Filtros globais:** período (mês, trimestre, ano, personalizado), conta(s), titular, incluir/excluir transferências.

**KPIs:**
- Total de despesas, total de receitas, saldo líquido.
- **Taxa de poupança** (`(receitas − despesas) / receitas`).
- Variação face ao mês anterior e à média dos últimos 6/12 meses.
- Nº de movimentos por categorizar.

**Gráficos** (MVP: despesas por categoria, evolução mensal e tabela; o resto é Fase 2):
- Despesas por categoria: **barras horizontais** como vista principal (mais legíveis que um donut com muitas fatias); o donut pode ficar como vista resumo, limitado ao top 6 + "Outros".
- Evolução mensal: receitas vs despesas (barras agrupadas) + linha de saldo líquido.
- Evolução de uma categoria ao longo do tempo (drill-down ao clicar) *(Fase 2)*.
- Top comerciantes por gasto *(Fase 2)*.
- **Despesas recorrentes detetadas** *(Fase 2)* (subscrições: mesmo comerciante e valor semelhante todos os meses).

**Tabela de movimentos:** filtros por data, conta, categoria, montante e texto (tags na Fase 2); ordenação; paginação no servidor.

### 3.10. Exportação & Backup
- *(Fase 2)* Exportar movimentos filtrados para CSV/XLSX.
- *(Fase 2)* Exportar e importar regras e categorias (JSON), para backup ou partilha.
- **MVP:** serviço/script de backup com `pg_dump` agendado, com cópia para fora do mini-PC (ver secção 6).

---

## 4. Modelo de Dados (Fase 1 — esquema final)

Convenções: PKs `BIGINT GENERATED ALWAYS AS IDENTITY`; todos os instantes em `timestamptz` (UTC); datas de movimento em `date`; montantes e saldos em `NUMERIC(12,2)`; enums como `TEXT` + `CHECK` (evita as dores de `ALTER TYPE` nas migrações); `criado_por`/`atualizado_por` são FKs para `utilizadores`.

```sql
-- Autenticação -----------------------------------------------------------
utilizadores (
  id, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,   -- argon2
  nome TEXT NOT NULL, ativo BOOL NOT NULL DEFAULT true,
  criado_em timestamptz NOT NULL DEFAULT now()
)

sessoes (                               -- sessões no servidor (revogáveis)
  token_hash CHAR(64) PRIMARY KEY,      -- sha256 do token do cookie; o token nunca é guardado
  utilizador_id → utilizadores ON DELETE CASCADE,
  csrf_token TEXT NOT NULL,
  criada_em, ultimo_uso_em, expira_em   -- timestamptz NOT NULL
)  -- INDEX (expira_em) para limpeza

-- Contas -----------------------------------------------------------------
contas (
  id, nome TEXT NOT NULL UNIQUE, banco TEXT NOT NULL,
  iban_mascarado TEXT NULL, moeda CHAR(3) NOT NULL DEFAULT 'EUR',
  parser_id TEXT NOT NULL,              -- ex.: 'bankinter_xlsx', 'csv_generic'
  config_importacao JSONB NOT NULL DEFAULT '{}',  -- mapeamento de colunas do CSV genérico, por conta
  titular_id → utilizadores NULL,       -- NULL = conta conjunta
  arquivada BOOL NOT NULL DEFAULT false, criada_em
)

-- Importações ------------------------------------------------------------
importacoes (
  id, conta_id → contas NOT NULL,
  ficheiro_nome TEXT NOT NULL, ficheiro_hash CHAR(64) NOT NULL,     -- SHA-256
  estado TEXT NOT NULL CHECK (estado IN ('preview','confirmada','revertida','erro')),
  periodo_inicio date NULL, periodo_fim date NULL,
  saldo_inicial NUMERIC(12,2) NULL,     -- derivado da cadeia de saldos (ver 3.2)
  saldo_final   NUMERIC(12,2) NULL,
  reconciliado BOOL NULL, diferenca NUMERIC(12,2) NULL,
  ordem_ficheiro TEXT NULL CHECK (ordem_ficheiro IN ('asc','desc')),  -- detetada pela cadeia
  n_linhas_ficheiro INT NOT NULL DEFAULT 0,
  n_movimentos INT NOT NULL DEFAULT 0,            -- gravados
  n_duplicados_ignorados INT NOT NULL DEFAULT 0,
  n_excluidos_utilizador INT NOT NULL DEFAULT 0,
  staging JSONB NULL,                   -- linhas parseadas entre preview e confirm; passa a NULL ao confirmar
  expira_em timestamptz NULL,           -- só em 'preview'; limpeza periódica
  erro_detalhe TEXT NULL,
  criada_por →, criada_em, confirmada_em NULL, revertida_em NULL, revertida_por → NULL
)
-- UNIQUE INDEX (conta_id, ficheiro_hash) WHERE estado = 'confirmada'
-- INDEX (conta_id, periodo_inicio, periodo_fim)

-- Categorias e regras ----------------------------------------------------
categorias (
  id, nome TEXT NOT NULL, parent_id → categorias NULL,   -- máx. 2 níveis (validado no serviço)
  tipo TEXT NOT NULL CHECK (tipo IN ('despesa','receita','transferencia')),
  cor TEXT, icone TEXT, ativa BOOL NOT NULL DEFAULT true
)
-- UNIQUE INDEX (COALESCE(parent_id, 0), nome); filho herda o tipo do pai (serviço)
-- "Por Categorizar" NÃO é uma categoria: é movimentos.categoria_id IS NULL

regras (
  id,
  padrao TEXT NOT NULL,                 -- guardado já normalizado (maiúsculas, sem acentos), comparado com descricao_normalizada
  tipo_match TEXT NOT NULL DEFAULT 'contem'
        CHECK (tipo_match IN ('contem','comeca_por','igual','regex')),
  categoria_id → categorias NOT NULL,
  direcao TEXT NOT NULL DEFAULT 'ambos' CHECK (direcao IN ('debito','credito','ambos')),
  montante_min NUMERIC(12,2) NULL, montante_max NUMERIC(12,2) NULL,   -- CHECK min <= max; sobre |montante|
  conta_id → contas NULL,
  prioridade INT NOT NULL DEFAULT 100,
  origem TEXT NOT NULL CHECK (origem IN ('manual','aprendida')),
  ativa BOOL NOT NULL DEFAULT true, n_aplicacoes INT NOT NULL DEFAULT 0,
  criado_por →, atualizado_por →, criada_em, atualizada_em
)
-- INDEX (ativa, prioridade DESC)
-- As colunas direcao / montante_* / regex existem desde já (com defaults neutros) para a Fase 2
-- não exigir migração; a UI do MVP só expõe 'contem' e 'comeca_por'.

-- Movimentos -------------------------------------------------------------
movimentos (
  id, conta_id → contas NOT NULL,
  importacao_id → importacoes NOT NULL ON DELETE RESTRICT,   -- a reversão apaga explicitamente
  data_movimento date NOT NULL, data_valor date NULL,
  ordem_no_dia SMALLINT NOT NULL,       -- ordem cronológica dentro do dia, derivada da cadeia de saldos
  descricao_original TEXT NOT NULL,
  descricao_normalizada TEXT NOT NULL,
  montante NUMERIC(12,2) NOT NULL CHECK (montante <> 0),     -- com sinal: débito < 0
  saldo_apos NUMERIC(12,2) NULL,
  categoria_id → categorias NULL,
  categoria_origem TEXT NULL CHECK (categoria_origem IN ('regra','historico','fuzzy','ml','manual')),
  regra_id → regras NULL ON DELETE SET NULL,
  notas TEXT NULL,
  criado_por →, atualizado_por →, criada_em, atualizada_em,
  CHECK ((categoria_id IS NULL) = (categoria_origem IS NULL))
)
-- Deduplicação (ver abaixo):
--   INDEX (conta_id, data_movimento, montante)   -- NÃO único: ver 4.1
-- INDEX (conta_id, data_movimento)          -- dashboard e tabela
-- INDEX (categoria_id)
-- INDEX (descricao_normalizada)             -- agrupamento e match por histórico
-- INDEX (data_movimento) WHERE categoria_id IS NULL     -- ecrã "Por Categorizar"
-- INDEX (importacao_id)
```

**Fora do esquema da Fase 1** (entram com migração na Fase 2): `tags`, `movimento_tags`, `movimento_divisoes` (splits), reembolsos (`reembolso_de_id`), `transferencia_par_id`.

### 4.1. Deduplicação (substitui o `hash_dedup`)
O `hash_dedup` anterior incluía a descrição normalizada e a ordem no dia. Falhava o objetivo "Excel e PDF do mesmo mês não duplicam": as descrições e a ordem das linhas diferem entre fontes, e qualquer alteração ao normalizador invalidava os hashes já gravados. **A descrição deixa de fazer parte da chave de deduplicação.**

Um único algoritmo (multiset), em `import_service`, sem constraint de unicidade na BD. Uma restrição `UNIQUE` rejeitaria movimentos legítimos: p. ex. compra de −10 (saldo 90), reembolso de +10 (saldo 100) e nova compra de −10 (saldo 90) no mesmo dia têm a mesma chave `(conta, data, −10, 90)`.

1. **Chave base:** `(conta_id, data_movimento, montante)`. Para cada chave, o ficheiro tem *n* linhas e a BD já tem *m*; entram *n − m* (se *n ≤ m*, nenhuma).
2. **Refinamento por saldo:** quando a linha do ficheiro **e** a linha gravada têm `saldo_apos`, só são consideradas a mesma linha se o saldo coincidir. Se uma das duas não tiver saldo (ex.: PDF sem saldo por linha importado antes do Excel), cai-se na chave base, de modo que importar o mesmo mês por fontes diferentes não duplica.
3. Casos ambíguos (contagens ou saldos que não batem) ficam marcados "possível duplicado" na pré-visualização para o utilizador decidir.
4. Uma linha duplicada **fica com o dono original** (a importação que a gravou primeiro) e conta em `n_duplicados_ignorados`.
5. **A validar com os fixtures emparelhados (Excel + PDF do mesmo mês):** qual das datas (movimento ou valor) é comum às duas fontes e se o PDF traz saldo por linha. A chave pode ter de usar `data_valor`.

### 4.2. Ciclo de vida de uma importação
`preview → confirmada → revertida`, ou `preview → erro` (e `preview` expirado é apagado).
- **Preview:** cria a linha `importacoes` com `estado='preview'`, guarda as linhas em `staging` e define `expira_em` (ex.: 24 h).
- **Confirm:** o corpo traz as linhas excluídas e as correções. O **servidor volta a reconciliar sobre todas as linhas do ficheiro, já com as correções**; as exclusões só impedem a gravação da linha e não quebram a cadeia de saldos. Se não reconciliar, o confirm é recusado e a importação **continua em `preview`** com `reconciliado=false` e `diferenca`, para o utilizador corrigir. Ao gravar, `staging` passa a NULL.
- **`erro`** é só para ficheiros que não conseguem ser lidos (formato inválido, parser sem confiança); fica registado em `erro_detalhe`.
- **Hash:** `ficheiro_hash` só é único entre importações `confirmada`. Depois de revertida (ou em `erro`/`preview`), o mesmo ficheiro pode ser reimportado.
- **Reversão:** apaga os movimentos da importação e passa-a a `revertida`. **É bloqueada** se existir uma importação `confirmada` posterior na mesma conta cujo período se sobreponha (as linhas duplicadas desta pertencem à primeira); tem de se reverter pela ordem inversa. A interface avisa que as categorizações manuais desses movimentos se perdem.

### 4.3. Saldo inicial e ordem do ficheiro
O export de movimentos normalmente não traz saldo inicial. Deriva-se da cadeia de saldos: `saldo_inicial = saldo_apos(primeiro cronológico) − montante`. A **ordem do ficheiro** (asc/desc) deteta-se pelo sentido em que `saldo_anterior + montante = saldo_apos` reconcilia, e a mesma cadeia define `ordem_no_dia`. Numa importação com sobreposição, verifica-se ainda a **continuidade** com o último saldo já gravado da conta (aviso, não bloqueio). *(Nomes das colunas, formato das datas e ordem das linhas do Excel do Bankinter: a validar com o fixture real.)*

### 4.4. Transferências e totais
A única fonte de verdade para excluir um movimento dos totais é `categorias.tipo = 'transferencia'`. No MVP a categorização é por regra ou manual; o emparelhamento automático (`transferencia_par_id`, ±3 dias) é Fase 2.

---

## 5. API (principais endpoints)

```text
POST   /api/auth/login | /api/auth/logout    GET /api/auth/me   (login limitado por rate limit)
POST   /api/imports/preview          → upload + parsing; cria importação em estado 'preview' com staging
                                       e devolve o seu id e a pré-visualização (não grava movimentos)
POST   /api/imports/{id}/confirm     → corpo: {linhas_excluidas, correcoes}; reconcilia de novo e grava
DELETE /api/imports/{id}             → reverte (409 se houver importação posterior sobreposta)
GET    /api/transactions             → filtros, paginação
PATCH  /api/transactions/{id}        → categoria, notas
POST   /api/transactions/bulk-categorize
GET    /api/transactions/uncategorized?group_by=description
CRUD   /api/categories, /api/rules, /api/accounts
POST   /api/rules/{id}/preview-impact → quantos movimentos seriam afetados
POST   /api/rules/apply               → aplicação retroativa
GET    /api/analytics/summary | by-category | monthly      (merchants | recurring: Fase 2)
GET    /api/export/transactions.csv                        (Fase 2)
GET    /api/health
```

Todos os endpoints, exceto `/api/health` e `/api/auth/login`, exigem sessão válida; os pedidos que alteram estado exigem também o cabeçalho `X-CSRF-Token`. Tags, splits e reembolsos (`/api/transactions/{id}/split`, etc.) entram na Fase 2.

Documentação automática via OpenAPI (`/docs`).

---

## 6. Requisitos Não Funcionais

### Implementação: mini-PC + Tailscale
- A app corre no mini-PC com `docker compose`, com `restart: unless-stopped`.
- **Sem portas abertas no router nem exposição pública.** O acesso remoto é feito só pela tailnet.
- O frontend (nginx) faz bind a `127.0.0.1`. O acesso via tailnet usa **`tailscale serve`**, que dá HTTPS automático com certificado válido em `https://<minipc>.<tailnet>.ts.net`. Assim não é preciso Caddy nem Traefik.
- **Não usar `tailscale funnel`**: isso expõe a app à internet pública.
- Cada pessoa acede adicionando o seu dispositivo à tailnet (ou partilhando o nó com ela) e usa o seu login na app.
- Opcional: ACLs da tailnet a restringir o acesso a este serviço aos dispositivos dos dois utilizadores.

### Segurança & Privacidade
Os extratos bancários são dados muito sensíveis.
- **Autenticação obrigatória na app**, mesmo com Tailscale (defesa em profundidade, caso um dispositivo da tailnet fique comprometido ou seja partilhado): utilizador e password com hash *argon2*, sessão no servidor (tabela `sessoes`, só se guarda o hash do token) com cookie opaco `HttpOnly` + `Secure` + `SameSite=Lax`, **proteção CSRF** por token no cabeçalho `X-CSRF-Token` nos pedidos que alteram estado, e rate limiting no login. Atrás do nginx/`tailscale serve`, o IP do cliente lê-se do cabeçalho `X-Forwarded-For` só de proxies de confiança.
- Segredos via `.env` (nunca no repositório); `.env.example` incluído.
- Os ficheiros importados (PDF/XLSX/CSV) **não são guardados por omissão**; guarda-se apenas o hash. Se o utilizador quiser guardá-los, vão para um volume dedicado.
- Logs sem descrições nem montantes de movimentos.
- Containers a correr como utilizador não-root; imagens slim; healthchecks.
- Limites de upload e timeouts no parsing (proteção contra PDFs maliciosos ou enormes).
- **Backups:** `pg_dump` diário com rotação (ex.: 7 diários + 4 semanais), copiado **para fora do mini-PC** (NAS, disco externo ou outro nó da tailnet). Se o disco do mini-PC morrer, os dados não se perdem.

### Qualidade
- Testes: `pytest` para parsers (fixtures), normalização, motor de regras e reconciliação; testes de API com BD de teste.
- Lint/format: `ruff` (lint e `ruff format`) para Python, `eslint` + `prettier` para TS.
- Dependências de leitura de ficheiros: `openpyxl` (XLSX; `xlrd` só se o Bankinter exportar `.xls` legado, a validar) e `argon2-cffi`.
- CI simples (GitHub Actions): lint + testes + build das imagens.

### Desempenho
- Importar um extrato com 300 movimentos em < 5 s.
- Dashboard com 5 anos de histórico em < 1 s (agregações em SQL, não em Python).

### UX
- Interface em português (PT-PT), formato de moeda `1 234,56 €`.
- Modo claro/escuro; responsivo (consulta no telemóvel).

---

## 7. Estrutura do Repositório

```text
personalFinanceAnalyzer/
├── docker-compose.yml
├── docker-compose.dev.yml          # hot-reload, porta do Postgres exposta só em dev
├── .env.example
├── Makefile                        # make up / test / migrate / backup
├── README.md
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/versions/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models/                 # SQLAlchemy
│   │   ├── schemas/                # Pydantic
│   │   ├── api/routers/            # imports, transactions, rules, categories, analytics
│   │   ├── services/
│   │   │   ├── import_service.py   # preview, confirm, reconcile, dedup
│   │   │   ├── normalizer.py
│   │   │   ├── categorizer.py      # regras → histórico (MVP); fuzzy → ml (Fase 2)
│   │   │   └── transfers.py        # Fase 2
│   │   ├── parsers/
│   │   │   ├── base.py             # Protocol + ParsedStatement
│   │   │   ├── registry.py         # deteção automática do banco
│   │   │   ├── csv_generic.py
│   │   │   └── banks/
│   │   │       └── bankinter/
│   │   │           ├── xlsx.py     # MVP
│   │   │           └── pdf.py      # Fase 1b
│   │   └── seed/categories_pt.json
│   └── tests/
│       ├── fixtures/bankinter/     # .xlsx/.pdf anonimizados + expected.json
│       └── ...
├── frontend/
│   ├── Dockerfile                  # build multi-stage → nginx
│   ├── nginx.conf                  # serve SPA + proxy /api → backend
│   ├── package.json
│   └── src/
│       ├── pages/                  # Dashboard, Import, Transactions, Review, Rules, Settings
│       ├── components/
│       ├── api/                    # cliente tipado (gerado a partir do OpenAPI)
│       └── lib/format.ts           # moeda/datas PT
└── scripts/
    └── backup.sh
```

---

## 8. Roadmap

### Fase 1 — MVP
- Docker Compose no mini-PC + `tailscale serve`, 2 utilizadores, migrações.
- Contas (com titular e `config_importacao`), categorias hierárquicas (seed PT), sessões e CSRF.
- **Parser Bankinter Excel/CSV** + importador CSV genérico.
- Pré-visualização, reconciliação de saldos, deduplicação, reversão de importação.
- Normalização + regras (`contem`/`comeca_por`) + match por histórico.
- Ecrã "Por Categorizar" agrupado, com aprendizagem por keyword confirmada.
- Dashboard: KPIs, despesas por categoria, evolução mensal, tabela com filtros.
- Backup diário com cópia para fora do mini-PC.

### Fase 1b
- Parser Bankinter PDF (extrato mensal), validado contra o Excel do mesmo mês.
- Importação do histórico antigo.

### Fase 2
- Parsers de outros bancos (se necessário); regras com regex, montante e direção; prioridades.
- Fuzzy matching e classificador local como sugestões.
- Deteção de transferências entre contas e de despesas recorrentes.
- Splits (`movimento_divisoes`), tags, reembolsos e `transferencia_par_id` (migrações novas).
- Exportações CSV/XLSX e de regras.

### Fase 3
- **Orçamentos por categoria** com alertas de desvio.
- OCR para extratos digitalizados (`ocrmypdf` + Tesseract `por`).
- Multimoeda.
- Relatório anual (ex.: apoio ao IRS, com despesas de saúde, educação, habitação).

---

## 9. Critérios de Aceitação (MVP)
- [ ] `docker compose up` arranca tudo do zero, com migrações e seed automáticos.
- [ ] Importar uma exportação Excel real do Bankinter produz movimentos em que cada linha reconcilia com a coluna de saldo.
- [ ] A app está acessível em `https://<minipc>.<tailnet>.ts.net` a partir de um dispositivo da tailnet e **inacessível** fora dela.
- [ ] Os dois utilizadores fazem login, veem os mesmos dados, e fica registado quem categorizou cada movimento.
- [ ] O backup diário é copiado para fora do mini-PC e consegue ser restaurado numa instância limpa.
- [ ] Reimportar o mesmo ficheiro é bloqueado; importar um extrato com períodos sobrepostos não cria duplicados.
- [ ] Categorizar manualmente um comerciante cria uma regra, e o mês seguinte categoriza-o automaticamente.
- [ ] Uma categorização manual nunca é alterada por regras.
- [ ] Movimentos categorizados numa categoria do tipo `transferencia` (por regra ou manualmente) não aparecem como despesa nem como receita. A deteção automática de pares é Fase 2.
- [ ] Reverter uma importação é bloqueado enquanto outra importação posterior sobreposta existir; depois de revertida, o mesmo ficheiro pode ser reimportado.
- [ ] Os KPIs do dashboard batem com uma soma manual dos movimentos do período.
- [ ] Sem autenticação não há acesso a nenhum endpoint (exceto `/api/health`).

### Critério da Fase 1b
- [ ] Importar o mesmo mês por Excel e por PDF não cria duplicados.

---

## 10. Decisões de Âmbito

| # | Questão | Decisão | Impacto no PRD |
|---|---|---|---|
| 1 | Bancos no MVP | **Bankinter.** Excel/CSV como via principal; PDF na Fase 1b | 3.3.1, roadmap, estrutura de parsers |
| 2 | Utilizadores | **2 logins** (dois utilizadores do mesmo agregado), dados partilhados, sem papéis | 3.1.1, modelo de dados (`utilizadores`, `criado_por`, `titular`) |
| 3 | Implementação | **Mini-PC local, acesso via Tailscale** (`tailscale serve`, sem funnel) | Secção 6 (Implementação, Segurança, Backups) |
| 4 | Cartões de crédito | **Não existem** | Removidos do âmbito; mantém-se a deteção de transferências entre contas próprias |
| 5 | Chave de deduplicação | **Multiset `(conta, data_movimento, montante)`** refinado por `saldo_apos` só quando ambos os lados o têm; **sem** índice único na BD (rejeitaria movimentos legítimos). A descrição normalizada **sai** da chave | 4.1; remove `hash_dedup`. Resolve a contradição Excel+PDF |
| 6 | Ciclo de vida da importação | Estados `preview/confirmada/revertida/erro`; linhas em `staging` JSONB; hash único só entre `confirmada` | 3.2, 4.2, API |
| 7 | Reversão com sobreposição | Bloqueada se existir importação posterior sobreposta; reverter por ordem inversa | 4.2 |
| 8 | Saldo inicial e ordem | Derivados da cadeia de saldos; `ordem_no_dia` guardado | 4.3 |
| 9 | Splits | **Fase 2**, tabela `movimento_divisoes` (sem auto-FK) | 3.8, 4 |
| 10 | Transferências | Fonte de verdade: `categorias.tipo='transferencia'`; emparelhamento automático na Fase 2 | 3.7, 4.4, §9 |
| 11 | Upload no MVP | Só CSV/XLSX; PDF na Fase 1b | 3.2 |
| 12 | Sessões | Tabela `sessoes` no servidor + CSRF por cabeçalho | 4, 5, 6 |
| 13 | Desempate de regras | prioridade → tipo_match → padrão mais longo → mais antiga | 3.5 |
| 14 | Titular da conta | `contas.titular_id` (FK a utilizadores); NULL = conjunta | 4 |
| 15 | Formatação Python | `ruff format` em vez de `black` | 6 |

### Próximos passos / input necessário
- [ ] Exportação **Excel** de movimentos do Bankinter (1–3 meses), anonimizada.
- [ ] Extrato **PDF** do Bankinter **do mesmo mês** de um dos Excel, anonimizado.
- [ ] Confirmar se as contas do segundo utilizador também são Bankinter. Se forem de outro banco, entra na Fase 2.
- [ ] Indicar o destino do backup fora do mini-PC (NAS, disco USB, outro nó).

### Questões menores (podem ser decididas durante o desenvolvimento)
- Que hardware e SO tem o mini-PC (arquitetura x86/ARM, RAM)? Afeta só as imagens Docker.
- Lista inicial de categorias: usar o seed PT proposto ou partir de uma lista vossa?
