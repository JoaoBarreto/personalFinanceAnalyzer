# Adicionar um banco novo (ex.: ActiveBank) e contas de outros utilizadores

Princípio: **nunca adivinhar o formato**. Cada conta importa com um modelo ESTRITO (o parser dedicado do Bankinter, ou o modelo detetado e **confirmado pelo utilizador** nos outros bancos); qualquer desvio é recusado e nada é gravado. Extratos reais não entram no repositório nem são lidos por quem desenvolve: se for preciso partilhar um formato, só se partilha a estrutura mascarada.

## Ferramentas de linha de comandos (em `scripts/`)

Uteis para investigar um formato fora da app (o assistente já faz isto por si, ver a secção seguinte).

| Script | Para quê |
|---|---|
| `mask_statement.py [--mostrar-rotulos] ficheiro` | Mostra a estrutura de um `.xls`, `.xlsx` ou `.csv` com letras→`x` e dígitos→`9`: folhas, linha do cabeçalho, tipos e formatos de célula, forma de datas e números por coluna, codificação e separador do CSV. Só mostra sem máscara vocabulário genérico (data, valor, montante, saldo…). |
| `check_statement.py <banco> ficheiro` | Corre o parser registado e diz ACEITE/RECUSADO, nº de movimentos, período, ordem, se os saldos reconciliam e quebras, sem valores nem descrições. |
| `check_xls.py ficheiro` | Atalho para `check_statement.py bankinter`. |

Correm na máquina do utilizador com `backend/.venv/bin/python scripts/...` (para `.xlsx`: `backend/.venv/bin/pip install openpyxl`). PDF não é suportado: pedir ao banco o extrato em `.xls`/`.xlsx`/`.csv`.

## Pela aplicação (qualquer utilizador): sem código

Em «Adicionar conta» (menu Trabalho, ou no dashboard vazio): escolher o banco, dar nome à conta e, para um banco que ainda não existe na lista («Outro banco…»), **carregar o extrato** (.xls, .xlsx ou .csv, com coluna de saldo). A aplicação:

1. **Deteta** o formato (linha de cabeçalho, coluna da data e o seu formato, montante ou débito/crédito, saldo, separadores decimal e de milhares, codificação do CSV) e **verifica-o**: só propõe um modelo se a cadeia de saldos `saldo anterior + montante = saldo` fechar em todas as linhas; é isso que distingue o montante do saldo.
2. **Pergunta** quando há ambiguidade (dia/mês: dd/mm contra mm/dd; várias combinações de colunas que fecham as contas). Nunca escolhe por si.
3. Mostra o **texto original ao lado do valor lido** («1.234,50» → 1 234,50 €) e as contas a fechar. O utilizador confirma. Isto protege do erro de escala (um valor «-889.50» lido como -88950), que a reconciliação de saldos não apanha.
4. Cria a conta com o modelo (`parser_id="generico"`, guardado em `contas.config_importacao`) e abre a pré-visualização da importação. O ficheiro nunca é gravado antes da pré-visualização.

O parser genérico é tão estrito como o do Bankinter: cabeçalho igual ao do modelo (nome e ordem), datas só no formato do modelo, montantes com exatamente 2 casas e os separadores do modelo, uma só folha, nada com data depois do fim dos movimentos, datas em ordem. Qualquer desvio recusa o ficheiro inteiro. Se o banco mudar o formato do extrato, as importações são recusadas até a conta ser configurada de novo.

**Limites:** exige coluna de saldo por movimento (sem saldo não há cadeia para reconciliar: o serviço de importação recusa linhas sem saldo); uma só folha; sem PDF. Se a deteção falhar, a conta pode ser criada «por suportar» (`parser_id="pendente"`) e a app mostra a estrutura do extrato com valores mascarados, para pedir suporte.

Código: `parsers/generic/` (`template.py` valida o modelo contra valores fixos, `parser.py`, `detector.py`, `reader.py`); endpoints `GET /api/banks`, `POST /api/banks/detect`, `/verify` e `/structure` (estrutura mascarada).

## Passos para um banco com parser dedicado (desenvolvimento)

Só faz falta para extratos que o parser genérico não consegue ler (PDF, várias folhas, sem saldo, layouts invulgares).

1. **Exportar** o extrato no formato original do banco (de preferência Excel/CSV, com saldo por linha) e **não o abrir nem guardar noutra aplicação**: isso muda formatos (ex.: `-889.50` lido como `-88950`).
2. **Mascarar**: `mask_statement.py ficheiro` e colar a saída na conversa. Se os nomes das colunas aparecerem como `xxxx`, confirmar que a linha do cabeçalho não tem dados pessoais e repetir com `--mostrar-rotulos`. Rever a saída antes de a colar.
3. **Definir o modelo estrito** (a partir da estrutura): colunas e ordem, onde fica o cabeçalho, formato de datas, separador decimal e de milhares, sinal (um só montante com sinal ou colunas débito/crédito), moeda, ordem das linhas, presença de saldo por linha e de preâmbulo/rodapé. Decisões de ambiguidade são do utilizador.
4. **Implementar** em `backend/app/parsers/banks/<banco>/`: um parser com `can_parse` e `parse` (contrato em `parsers/base.py`), reutilizando a reconciliação por cadeia de saldos (`parsers/reconcile.py`). Dinheiro sempre em `Decimal` a partir do texto ou de cêntimos inteiros, nunca de float. Registar o `parser_id` em `parsers/registry.py` (`PARSERS` e a lista `BANKS`, que alimenta o assistente).
5. **Testes sintéticos**: um gerador de ficheiros no `conftest.py` (como `build_csv`/`build_xls`) com valores escritos à mão e variantes inválidas de propósito (data errada, casas decimais a mais, coluna renomeada, outra folha). Os testes recusam desvios e aceitam o modelo exato. Nunca usar o ficheiro real nos testes versionados.
6. **Validar no ficheiro real**: o utilizador corre `check_statement.py <banco> ficheiro` e cola o resultado. Se for recusado, ajusta-se pela mensagem agregada, sem relaxar a regra.
7. **Conta**: criar o utilizador (`make create-user`) se ainda não existir, depois a conta em «Contas» com o banco certo. Importar, rever o preview (avisos de continuidade e duplicados) e confirmar.
8. **Conferir**: o saldo da conta tem de bater com o banco, e o aviso de cobertura não pode mostrar buracos. Só depois categorizar.
9. **Commit**: apenas código, testes sintéticos e esta documentação. Nada de ficheiros reais, capturas com dados reais ou a saída mascarada completa se tiver informação identificável.

## Outros utilizadores

- Qualquer utilizador novo é igual aos outros: o administrador cria-o (`make create-user`), ele entra e cria as suas contas e importa os seus extratos. Nada é partilhado: cada utilizador só vê as suas contas, movimentos, regras e categorias (recebe a sua cópia das categorias iniciais).
- Cada conta pertence a um banco (`banco`) e a um parser; a deduplicação é por conta. Um banco novo, depois de ter parser, fica disponível para todos os utilizadores.
- O isolamento é feito pela aplicação; quem administra o servidor tem acesso à base de dados.
