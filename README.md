# E-Commerce Híbrido (Django)

Esse projeto junta três frentes num domínio só de catálogo/pedidos: uma landing page pública, um admin customizado, e uma API REST pra integração externa. Foi feito como desafio técnico, então abaixo vai o passo a passo de como rodar, como eu tratei a parte mais sensível (concorrência no estoque) e as credenciais pra já entrar testando.

- **Landing page pública** (Django Templates + Tailwind via CDN) em `/` — com carrinho, busca e filtro por categoria.
- **Painel administrativo** customizado (Django Admin) em `/admin/`.
- **API REST** (DRF) em `/api/v1/` pra integrações externas.

## Estrutura dos apps

| App          | Responsabilidade                                                                 |
|--------------|----------------------------------------------------------------------------------|
| `users`      | `AUTH_USER_MODEL` customizado (`users.User`, extends `AbstractUser`) — ponto de extensão pra campos de perfil no futuro. |
| `catalog`    | Modelos `Category`/`Product`, admin do catálogo, API pública de produtos.        |
| `orders`     | Modelos `Order`/`OrderItem`, admin de pedidos, API autenticada, **serviço de criação de pedidos** (`orders/services.py`). |
| `storefront` | Templates (home, detalhe do produto, carrinho, "meus pedidos", login/logout).    |
| `main`       | Health check em `GET /api/v1/status/`.                                          |

A lógica de criação de pedido mora num lugar só — `orders/services.py::create_order` — e é usada tanto pela API quanto pelo carrinho/botão "Comprar agora" do site. Assim a garantia de estoque vale pros dois caminhos, sem duplicar regra.

## Endpoints principais

| Método | Rota                                   | Auth        | Descrição                                       |
|--------|----------------------------------------|-------------|-------------------------------------------------|
| GET    | `/`                                    | pública     | Landing page: categorias, busca e produtos ativos. |
| GET    | `/produto/<slug>/`                     | pública     | Detalhe do produto.                             |
| POST   | `/produto/<slug>/adicionar-ao-carrinho/` | logado    | Adiciona N unidades ao carrinho (sessão).       |
| GET    | `/carrinho/`                           | logado      | Ver/editar o carrinho.                          |
| POST   | `/carrinho/finalizar/`                 | logado      | Fecha o pedido com tudo que tá no carrinho.     |
| GET    | `/meus-pedidos/`                       | logado      | Histórico de pedidos do usuário.                |
| GET    | `/api/v1/status/`                      | pública     | Health check (`{"status": "ok"}`).              |
| GET    | `/api/v1/produtos/`                    | pública     | Lista paginada de produtos, filtrável por categoria. |
| POST   | `/api/v1/pedidos/`                     | JWT         | Cria um pedido a partir de uma lista de itens.  |
| GET    | `/api/v1/pedidos/`                     | JWT         | Lista os pedidos do usuário autenticado.        |
| GET    | `/api/v1/pedidos/<id>/`                | JWT         | Detalhe de um pedido do próprio usuário.        |
| POST   | `/api/v1/token/`                       | pública     | Emite `access`/`refresh` JWT via usuário/senha. |
| POST   | `/api/v1/token/refresh/`               | pública     | Troca um `refresh` válido por novo `access`.    |

Filtro de produtos por categoria: `?categoria=<id>` ou `?categoria_slug=<slug>`.

---

## Passo a passo pra rodar via Docker

É só isso, sem segredo:

```bash
docker-compose up
```

Isso já builda a imagem (na primeira vez), sobe o container e roda o `migrate` sozinho. O código do host fica montado dentro do container, então qualquer alteração recarrega na hora (hot reload) — não precisa ficar reiniciando toda hora, só quando mexer em dependência mesmo (aí sim precisa `docker-compose up --build`).

A aplicação fica em **http://127.0.0.1:8000/**.

Se quiser simular o ambiente de produção (sem hot reload, servido por `gunicorn`, `DEBUG=False`):

```bash
docker-compose -f docker-compose.prod.yml up --build
```

### Rodando os testes via Docker

```bash
docker-compose run --rm web python manage.py test
```

Com cobertura (mínimo exigido é 80%, a suíte cobre principalmente as regras de estoque/concorrência):

```bash
docker-compose run --rm web sh -c "coverage run manage.py test && coverage report"
```

### O banco já vem populado

O `db.sqlite3` desse repositório **já está populado** — categorias, produtos (com imagem) e o usuário admin abaixo já existem, não precisa rodar nenhum comando de seed antes de testar. Se quiser popular do zero mesmo assim (ou testar num banco limpo), dá pra criar tudo na mão:

```bash
docker-compose run --rm web python manage.py createsuperuser
```

e cadastrar categoria/produto direto pelo `/admin/`.

---

## Credenciais de acesso

Usuário admin (staff + superuser), já existente no `db.sqlite3` entregue:

- **Usuário:** `admin`
- **Senha:** `admin123!@#`

Usa essas credenciais tanto no Django Admin (`/admin/`) quanto no login do site (pra testar carrinho/"Comprar") e na API (`POST /api/v1/token/` pra pegar o JWT).

---

## Como tratei a concorrência no estoque (a parte que mais importa)

Beleza, essa é a parte central do desafio então vou tentar explicar com calma como resolvi.

Se dois clientes clicam "comprar" quase ao mesmo tempo no último item do estoque, o sistema não pode deixar os dois passarem — senão o estoque vira negativo e você vendeu uma coisa que não tinha. A solução clássica (e que usei aqui) é lock pessimista: `transaction.atomic()` + `select_for_update()`.

O fluxo inteiro fica em `orders/services.py::create_order`, e funciona mais ou menos assim:

1. Abre uma transação atômica pra tudo (se algo no meio der erro, desfaz tudo, não fica pedido pela metade).
2. Antes de checar o estoque, já trava as linhas dos produtos envolvidos com `select_for_update()` e trava numa ordem fixa (por `id` crescente), isso é importante pra evitar deadlock quando o carrinho tem mais de um produto (imagina duas compras concorrentes que travam os mesmos dois produtos só que em ordem invertida, aí trava tudo esperando um o outro pra sempre travando sempre na mesma ordem isso não acontece).
3. Só depois de conseguir a trava é que valida se `quantidade pedida <= estoque disponível`. Se não tiver, estoura `InsufficientStockError` e a transação inteira sofre rollback (na API vira um 400, no site vira uma mensagem de erro e volta pro carrinho).
4. Se passou, decrementa o estoque e salva. Como a linha já tá travada o tempo todo entre o "ler" e o "escrever", um `save()` simples já resolve, nem precisei usar `F()` pra isso.
5. Cria o `Order` e os `OrderItem`s, "congelando" o preço unitário no momento da compra (pra não ficar refém se o preço mudar depois), e calcula o total.

Essa função é a **única** porta de entrada pra criar pedido, seja pela API ou pelo carrinho/botão do site. Não tem duas implementações de "descontar estoque" pra manter sincronizadas, é uma só.

### E o que o usuário vê quando ele perde a corrida?

Essa pergunta é boa porque é bem a real: a tela do produto que o usuário tá olhando foi renderizada **antes** da corrida acontecer, então pra ele parece que tinha estoque sim — ele clicou achando que ia dar certo. O que acontece:

1. Ele clica em "Comprar agora" (ou "Finalizar compra" no carrinho) numa página que ainda mostrava "Em estoque", só que entre o carregamento da página e o clique, outro comprador já fechou o pedido e zerou o estoque.
2. O request dele chega, `create_order` tenta travar a linha do produto, espera a transação do outro comprador terminar, e quando finalmente lê o estoque, já tá em zero — não é o valor "velho" que a tela dele mostrava.
3. Estoura `InsufficientStockError`, nenhum `Order` é criado pra ele, nada é debitado, e a view captura isso com um `except OrderError` e redireciona de volta.
4. Ele volta pra página do produto (se clicou "Comprar agora") ou pro carrinho (se veio do "Finalizar compra"), e aparece um alerta vermelho no topo da página com a mensagem `Estoque insuficiente para 'Fone Bluetooth Pro': solicitado 1, disponível 0.` — e como a página recarrega com dado fresco do banco, o produto já aparece como "Esgotado" ali do lado, então dá pra entender na hora o que rolou.

Na API é a mesma lógica só que sem redirect: o cliente recebe um `HTTP 400` com `{"detail": "Estoque insuficiente para '...': solicitado X, disponível Y."}` no corpo, cabe ao consumidor da API decidir o que fazer com isso (mostrar erro, tentar de novo, etc).

Ou seja: não conta com o estoque que a tela mostrou há uns segundos atrás, o backend sempre reconfere no exato momento da trava — é isso que garante a consistência mesmo com a interface potencialmente desatualizada.

### Detalhe chato do SQLite 

Uma coisa que descobri fazendo isso: o SQLite não tem lock de linha de verdade que nem o Postgres tem. Na prática, `select_for_update()` roda mas não trava nada sozinho no SQLite. Então a garantia real aqui vem de outro lugar: eu configurei o SQLite pra abrir cada transação com `BEGIN IMMEDIATE` (em vez do padrão), que faz ele pegar o lock de escrita do banco inteiro já no começo da transação, não só na hora de escrever. Isso é meio "grosso" comparado a travar só a linha do produto, mas resolve o problema — o segundo comprador fica esperando (até um timeout configurado) e quando a vez dele chega, ele lê o estoque **já atualizado** (zero) e recebe o erro limpo, em vez de um erro cru de "database is locked".

Se essa aplicação fosse rodar em produção de verdade eu trocaria por Postgres, e aí sim `select_for_update()` passa a travar de verdade só a linha necessária — o código não muda nada, só a config do banco.

Tem um teste (`orders/tests.py::ConcurrencyTests`) que sobe duas threads reais brigando pelo último item e confere que só um pedido é criado e o estoque nunca fica negativo. Rodei isso várias vezes pra ter certeza que não era coincidência.

---

## Segurança

- **IDOR:** tudo que retorna ou mexe num `Order` específico filtra sempre por `request.user`. O dono do pedido vem sempre de `request.user`, nunca do payload que o cliente manda — então dá pra tentar forjar o campo "usuario" no JSON que não adianta, o backend ignora e usa quem tá autenticado.
- **SQL Injection:** só ORM em todo o projeto (`filter`/`get` com kwargs, `F()`/`Q()`, `FilterSet` do django-filter). Nenhum `.raw()`, `.extra()` ou string SQL montada na mão.
- **Autenticação da API:** JWT via `djangorestframework-simplejwt`. `POST /api/v1/pedidos/` exige estar autenticado. O `access` token expira rápido (5 min, padrão da lib); usa o `refresh` pra renovar sem precisar mandar usuário/senha de novo.

### Por que JWT em vez de Token

O enunciado aceitava "Token ou JWT" — optei por JWT porque é stateless (não fica token salvo em tabela) e já vem com expiração de fábrica, o que é uma prática melhor pro cenário de integração com parceiro externo que o desafio descreve.

### Exemplo de uso da API

```bash
# 1. Login, pega o par access/refresh
curl -X POST http://127.0.0.1:8000/api/v1/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "<sua_senha>"}'
# -> {"refresh": "...", "access": "..."}

# 2. Cria um pedido (por SKU ou id do produto, aceita vários itens de uma vez)
curl -X POST http://127.0.0.1:8000/api/v1/pedidos/ \
  -H "Authorization: Bearer <SEU_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"itens": [{"sku": "DEMO-FONEBLUETOOT", "quantidade": 2}]}'

# 3. Renova o access quando expirar
curl -X POST http://127.0.0.1:8000/api/v1/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "<SEU_REFRESH_TOKEN>"}'
```

---

## Rodando sem Docker (setup local)

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows (Git Bash). Linux/Mac: source .venv/bin/activate
poetry install --no-root
pre-commit install

python manage.py migrate
python manage.py runserver
```

O `db.sqlite3` que vem no repo já tem tudo populado, então não precisa criar superusuário nem cadastrar nada — só subir e usar as credenciais lá em cima.

## Comandos make

Atalho pros comandos acima (precisa ter `make` instalado):

| Comando             | Equivale a                                                  |
|----------------------|--------------------------------------------------------------|
| `make setup`         | cria o `.venv`, `poetry install --no-root`, `pre-commit install` |
| `make migrations`    | `python manage.py makemigrations`                            |
| `make migrate`       | `python manage.py migrate`                                   |
| `make run`           | `python manage.py runserver`                                 |
| `make superuser`     | `python manage.py createsuperuser`                            |
| `make shell`         | `python manage.py shell` (shell do Django)                   |
| `make dbshell`       | `python manage.py dbshell` (shell do SQLite)                  |
| `make tests`         | `python manage.py test`                                       |
| `make coverage`      | `coverage run manage.py test && coverage report`              |
| `make lint`          | `pre-commit run --all-files`                                   |
| `make up`            | `docker-compose up --build` (dev, hot reload)                 |
| `make up-prod`       | `docker-compose -f docker-compose.prod.yml up --build`         |
| `make down`          | `docker-compose down`                                          |
| `make test-docker`   | roda os testes com cobertura dentro do container               |
| `make clean`         | remove `__pycache__` e `.coverage`                              |

## Health check

```bash
curl http://127.0.0.1:8000/api/v1/status/
```

Resposta esperada:

```json
{"status": "ok"}
```

## Linters

Rodam sozinhos antes de cada commit (via `pre-commit install`), mas dá pra rodar na mão também:

```bash
pre-commit run --all-files
```

## Convenção de commits e release automático

Commits seguem [Conventional Commits](https://www.conventionalcommits.org/): `tipo(escopo): descrição` (ex: `feat(auth): ...`, `fix(estoque): ...`).

O `CHANGELOG.md`, a tag (`vX.Y.Z`) e a versão em `pyproject.toml` saem automaticamente desses commits via [python-semantic-release](https://python-semantic-release.readthedocs.io/), rodando em `.github/workflows/release.yml` a cada push na `main`. Pra simular local sem alterar nada: `semantic-release version --print`.
