# E-Commerce Híbrido (Django)

Aplicação Django que reúne três frentes sobre o mesmo domínio de catálogo/pedidos:

- **Landing page pública** (Django Templates + Tailwind via CDN) em `/`.
- **Painel administrativo** customizado (Django Admin) em `/admin/`.
- **API REST** (DRF) em `/api/v1/` para integrações externas.

## Estrutura dos apps

| App          | Responsabilidade                                                                 |
|--------------|----------------------------------------------------------------------------------|
| `users`      | `AUTH_USER_MODEL` customizado (`users.User`, extends `AbstractUser`) — ponto de extensão para campos de perfil futuros. |
| `catalog`    | Modelos `Category`/`Product`, admin do catálogo, API pública de produtos.        |
| `orders`     | Modelos `Order`/`OrderItem`, admin de pedidos, API autenticada de pedidos, **serviço de criação de pedidos** (`orders/services.py`). |
| `storefront` | Views de template (home, detalhe do produto, botão "Comprar", login/logout).     |
| `main`       | Health check já existente em `GET /api/v1/status/`.                              |

A lógica de criação de pedido vive num único lugar — `orders/services.py::create_order` — e é reutilizada tanto pela API quanto pelo botão "Comprar" da loja.

## Endpoints principais

| Método | Rota                                   | Auth        | Descrição                                       |
|--------|----------------------------------------|-------------|-------------------------------------------------|
| GET    | `/`                                    | pública     | Landing page: categorias + produtos ativos.     |
| GET    | `/produto/<slug>/`                     | pública     | Detalhe do produto (botão "Comprar" exige login).|
| POST   | `/produto/<slug>/comprar/`             | logado      | Cria um pedido de 1 unidade do produto.         |
| GET    | `/api/v1/status/`                      | pública     | Health check (`{"status": "ok"}`).              |
| GET    | `/api/v1/produtos/`                    | pública     | Lista paginada de produtos, filtrável por categoria. |
| POST   | `/api/v1/pedidos/`                     | JWT         | Cria um pedido a partir de uma lista de itens.  |
| GET    | `/api/v1/pedidos/`                     | JWT         | Lista os pedidos **do usuário autenticado**.    |
| GET    | `/api/v1/pedidos/<id>/`                | JWT         | Detalhe de um pedido do próprio usuário.        |
| POST   | `/api/v1/token/`                       | pública     | Emite um par de tokens JWT (`access` + `refresh`) via usuário/senha. |
| POST   | `/api/v1/token/refresh/`               | pública     | Troca um `refresh` token válido por um novo `access` token. |

Filtro de produtos por categoria: `?categoria=<id>` ou `?categoria_slug=<slug>`.

---

## Rodando via Docker (recomendado)

### Dev (com hot reload)

Sobe o projeto com `runserver`. O código do host é montado no container (hot reload), e na subida o container roda `migrate`:

```bash
docker-compose up
```

O banco começa vazio — crie categorias/produtos e um usuário admin manualmente (veja a seção seguinte).

### Prod (sem hot reload)

Sobe o projeto com `gunicorn` a partir da imagem buildada — sem volume, sem reload, `DEBUG=False`:

```bash
docker-compose -f docker-compose.prod.yml up --build
```

A aplicação fica disponível em http://127.0.0.1:8000/ em ambos os casos.

### Rodando os testes via Docker

```bash
docker-compose run --rm web python manage.py test
# com cobertura:
docker-compose run --rm web sh -c "coverage run manage.py test && coverage report"
```

---

## Populando os dados

Não há comando de seed — categorias, produtos e o usuário admin são criados manualmente, pelo `/admin/` ou pelo shell:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Depois é só logar em `/admin/` com o superusuário criado e cadastrar as categorias/produtos por lá.

---

## Tratamento de concorrência / race condition de estoque

O ponto crítico é: **dois clientes comprando o último item ao mesmo tempo nunca podem deixar o estoque negativo.**

A criação de pedido (`orders/services.py::create_order`) faz:

1. Roda tudo dentro de `transaction.atomic()`.
2. Trava as linhas dos produtos com `Product.objects.select_for_update()` **antes** de checar o estoque, em ordem estável (ordenadas por `id`) para evitar deadlocks quando há vários produtos no mesmo pedido.
3. Valida `quantidade solicitada <= estoque disponível`; se faltar, levanta `InsufficientStockError` (traduzido para HTTP 400 na API e para uma mensagem de erro na loja) e a transação inteira sofre rollback.
4. Decrementa o estoque na instância já travada e faz `save()`. Como a linha está travada durante todo o "checar-e-decrementar", um `save()` simples é suficiente — não é preciso `F()`.
5. Cria o `Order` e os `OrderItem`s, **congelando `preco_unitario`** no momento da compra, e calcula `valor_total`.

### Ressalva honesta sobre o SQLite

O SQLite **não** tem travamento de linha (row-level lock) como o PostgreSQL — na prática `select_for_update()` é um no-op no SQLite. A garantia de consistência aqui vem do modelo de transação do próprio SQLite, que serializa os escritores no nível do banco inteiro.

Para que essa serialização seja **limpa**, o projeto configura o SQLite com `transaction_mode = "IMMEDIATE"` (ver `DATABASES["default"]["OPTIONS"]` em `config/settings.py`). Assim, todo bloco `atomic()` começa com `BEGIN IMMEDIATE`, adquirindo o lock de escrita já no início da transação. O resultado no cenário do "último item":

- A primeira transação adquire o lock, lê estoque = 1, decrementa para 0 e faz commit.
- A segunda bloqueia no `BEGIN IMMEDIATE` (respeitando o `timeout`), e quando prossegue **lê dados frescos** (estoque = 0) e levanta um `InsufficientStockError` limpo — em vez de um erro cru de "database is locked".

Num banco como o PostgreSQL, o mesmo código passa a usar `SELECT ... FOR UPDATE` de verdade, com travamento por linha e concorrência mais fina, sem qualquer mudança na lógica.

O teste `orders/tests.py::ConcurrencyTests` exercita esse cenário com duas threads reais disputando um produto com `quantidade_estoque = 1` e verifica a invariante crítica: **apenas um pedido é criado e o estoque final é exatamente `0` (nunca negativo)**. O perdedor recebe um erro e nenhum pedido é criado por ele.

> Nota sobre o banco de teste: o Django roda os testes num SQLite **em memória com cache compartilhado**, cujo *busy handler* não é acionado para locks de cache. Por isso, no teste, o perdedor pode falhar imediatamente com "database is locked" em vez de bloquear e receber o `InsufficientStockError` limpo. A garantia de não vender a mais vale nos dois casos (a transação do perdedor nem chega a iniciar). O caminho do erro de estoque "limpo" é coberto de forma determinística pelo teste single-thread `test_insufficient_stock_raises_and_rolls_back`.

---

## Segurança

- **IDOR:** endpoints que retornam/mutam um `Order` específico filtram sempre por `request.user` (`Order.objects.filter(usuario=request.user)`); o dono do pedido vem sempre de `request.user`, nunca do payload. Um usuário não consegue ler nem forjar o pedido de outro.
- **SQL Injection:** uso exclusivo do ORM (`filter`/`get` com kwargs, `F()`/`Q()`, `FilterSet` do django-filter). Sem `.raw()`, `.extra()` ou SQL interpolado.
- **Autenticação da API:** JWT via `djangorestframework-simplejwt`. `POST /api/v1/pedidos/` exige `IsAuthenticated`. O `access` token expira (padrão da lib, 5 min); use `refresh` para renovar sem pedir a senha de novo.

### Por que JWT (e não Token)

O desafio aceitava "Token ou JWT". A implementação original usava `TokenAuthentication` do próprio DRF (`rest_framework.authtoken`); trocamos para **JWT** (`djangorestframework-simplejwt`), substituindo por completo o mecanismo original:

- `rest_framework.authtoken` saiu do `INSTALLED_APPS`; `rest_framework_simplejwt` entrou no lugar, junto com `JWTAuthentication` em `DEFAULT_AUTHENTICATION_CLASSES`.
- `POST /api/v1/token/` deixou de usar `obtain_auth_token` (que devolvia um token opaco de vida infinita salvo no banco) e passou a usar `TokenObtainPairView`, devolvendo um par `access`/`refresh` assinado (stateless, com expiração).
- Adicionamos `POST /api/v1/token/refresh/` para renovar o `access` sem reautenticar com usuário/senha.
- O header de autorização mudou de `Authorization: Token <key>` para `Authorization: Bearer <access>`.

### Exemplo de uso da API

```bash
# 1. Obter o par access/refresh
curl -X POST http://127.0.0.1:8000/api/v1/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "<seu_usuario>", "password": "<sua_senha>"}'
# -> {"refresh": "...", "access": "..."}

# 2. Criar um pedido (por SKU ou por id do produto)
curl -X POST http://127.0.0.1:8000/api/v1/pedidos/ \
  -H "Authorization: Bearer <SEU_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"itens": [{"sku": "ELE-001", "quantidade": 2}]}'

# 3. Renovar o access token quando expirar
curl -X POST http://127.0.0.1:8000/api/v1/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "<SEU_REFRESH_TOKEN>"}'
```

---

## Setup local (sem Docker)

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows (Git Bash). Linux/Mac: source .venv/bin/activate
poetry install --no-root
pre-commit install

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Comandos make

Atalhos pros comandos acima (equivalente ao Makefile, precisa de `make` instalado):

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

## Testar o health check

```bash
curl http://127.0.0.1:8000/api/v1/status/
```

Resposta esperada:

```json
{"status": "ok"}
```

## Linters

Rodam automaticamente antes de cada commit (via `pre-commit install`), mas também dá pra rodar manualmente:

```bash
pre-commit run --all-files
```

## Testes

```bash
python manage.py test
```

### Cobertura de testes

Mínimo exigido: 80%. A suíte cobre principalmente as regras de estoque e concorrência.

```bash
coverage run manage.py test
coverage report
```

## Convenção de commits e release automático

Commits seguem [Conventional Commits](https://www.conventionalcommits.org/): `tipo(escopo): descrição` (ex: `feat(auth): ...`, `fix(estoque): ...`). Tipos usados: `feat`, `fix`, `perf`, `refactor`, `docs`, `style`, `test`, `build`, `ci`, `chore`.

O `CHANGELOG.md`, a tag (`vX.Y.Z`) e a versão em `pyproject.toml` são gerados automaticamente a partir desses commits pelo [python-semantic-release](https://python-semantic-release.readthedocs.io/), rodando em `.github/workflows/release.yml` a cada push na `main`:

- `feat` → sobe a versão **minor**
- `fix`/`perf` → sobe a versão **patch**
- `BREAKING CHANGE:` no corpo do commit → sobe a versão **major**

Pra simular localmente sem alterar nada:

```bash
semantic-release version --print
```
