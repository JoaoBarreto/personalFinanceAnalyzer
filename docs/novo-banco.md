# Adicionar um banco novo (ex.: ActiveBank) e contas de outros utilizadores

Princípio: **nunca adivinhar o formato**. Cada banco tem um parser ESTRITO que só aceita o modelo exato do export original; qualquer desvio é recusado e nada é gravado. Extratos reais não entram no repositório nem são lidos por quem desenvolve: só se partilha a estrutura mascarada.

## Ferramentas (em `scripts/`)

| Script | Para quê |
|---|---|
| `mask_statement.py [--mostrar-rotulos] ficheiro` | Mostra a estrutura de um `.xls`, `.xlsx` ou `.csv` com letras→`x` e dígitos→`9`: folhas, linha do cabeçalho, tipos e formatos de célula, forma de datas e números por coluna, codificação e separador do CSV. Só mostra sem máscara vocabulário genérico (data, valor, montante, saldo…). |
| `check_statement.py <banco> ficheiro` | Corre o parser registado e diz ACEITE/RECUSADO, nº de movimentos, período, ordem, se os saldos reconciliam e quebras, sem valores nem descrições. |
| `check_xls.py ficheiro` | Atalho para `check_statement.py bankinter`. |

Correm na máquina do utilizador com `backend/.venv/bin/python scripts/...` (para `.xlsx`: `backend/.venv/bin/pip install openpyxl`). PDF não é suportado: pedir ao banco o extrato em `.xls`/`.xlsx`/`.csv`.

## Passos para um banco novo

1. **Exportar** o extrato no formato original do banco (de preferência Excel/CSV, com saldo por linha) e **não o abrir nem guardar noutra aplicação**: isso muda formatos (ex.: `-889.50` lido como `-88950`).
2. **Mascarar**: `mask_statement.py ficheiro` e colar a saída na conversa. Se os nomes das colunas aparecerem como `xxxx`, confirmar que a linha do cabeçalho não tem dados pessoais e repetir com `--mostrar-rotulos`. Rever a saída antes de a colar.
3. **Definir o modelo estrito** (a partir da estrutura): colunas e ordem, onde fica o cabeçalho, formato de datas, separador decimal e de milhares, sinal (um só montante com sinal ou colunas débito/crédito), moeda, ordem das linhas, presença de saldo por linha e de preâmbulo/rodapé. Decisões de ambiguidade são do utilizador.
4. **Implementar** em `backend/app/parsers/banks/<banco>/`: um parser com `can_parse` e `parse` (contrato em `parsers/base.py`), reutilizando a reconciliação por cadeia de saldos (`parsers/reconcile.py`). Dinheiro sempre em `Decimal` a partir do texto ou de cêntimos inteiros, nunca de float. Registar o `parser_id` em `parsers/registry.py`.
5. **Testes sintéticos**: um gerador de ficheiros no `conftest.py` (como `build_csv`/`build_xls`) com valores escritos à mão e variantes inválidas de propósito (data errada, casas decimais a mais, coluna renomeada, outra folha). Os testes recusam desvios e aceitam o modelo exato. Nunca usar o ficheiro real nos testes versionados.
6. **Validar no ficheiro real**: o utilizador corre `check_statement.py <banco> ficheiro` e cola o resultado. Se for recusado, ajusta-se pela mensagem agregada, sem relaxar a regra.
7. **Conta**: criar o utilizador (`make create-user`) se ainda não existir, depois a conta em «Contas» com o banco certo. Importar, rever o preview (avisos de continuidade e duplicados) e confirmar.
8. **Conferir**: o saldo da conta tem de bater com o banco, e o aviso de cobertura não pode mostrar buracos. Só depois categorizar.
9. **Commit**: apenas código, testes sintéticos e esta documentação. Nada de ficheiros reais, capturas com dados reais ou a saída mascarada completa se tiver informação identificável.

## Outros utilizadores

- Qualquer utilizador novo é igual aos outros: o administrador cria-o (`make create-user`), ele entra e cria as suas contas e importa os seus extratos. Nada é partilhado: cada utilizador só vê as suas contas, movimentos, regras e categorias (recebe a sua cópia das categorias iniciais).
- Cada conta pertence a um banco (`banco`) e a um parser; a deduplicação é por conta. Um banco novo, depois de ter parser, fica disponível para todos os utilizadores.
- O isolamento é feito pela aplicação; quem administra o servidor tem acesso à base de dados.
