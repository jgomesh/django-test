# E-Commerce Híbrido (Django)

Landing page pública, admin customizado e API REST sobre um domínio único de catálogo/pedidos.

## Rodando via Docker

```bash
docker-compose up
```

Builda a imagem, sobe o container e roda `migrate` automaticamente. Código montado como volume (hot reload). Aplicação em **http://127.0.0.1:8000/**.

Ambiente de produção (sem hot reload, `gunicorn`, `DEBUG=False`):

```bash
docker-compose -f docker-compose.prod.yml up --build
```

Testes com cobertura:

```bash
docker-compose run --rm web sh -c "coverage run manage.py test && coverage report"
```

O `db.sqlite3` do repositório já vem populado (categorias, produtos com imagem, usuário admin) — não é necessário rodar seed.

## Credenciais

- **Usuário:** `admin`
- **Senha:** `admin123!@#`

Válidas no Django Admin (`/admin/`), no login do site e em `POST /api/v1/token/` (JWT).

## Concorrência no estoque

Dois pedidos concorrentes pelo último item em estoque não podem gerar estoque negativo. A garantia está em `orders/services.py::create_order`, ponto único de criação de pedido (usado pela API e pelo carrinho/"Comprar agora"):

1. `transaction.atomic()` envolve toda a operação — qualquer erro no meio desfaz tudo.
2. Antes de checar estoque, as linhas dos produtos são travadas com `select_for_update()`, sempre na mesma ordem (`id` crescente) — evita deadlock quando o pedido tem mais de um produto.
3. A validação `quantidade <= estoque` só acontece depois da trava. Se faltar estoque, `InsufficientStockError` é levantado e a transação sofre rollback (400 na API, mensagem de erro no site).
4. Com a linha travada, `save()` simples já é seguro para decrementar o estoque.
5. `Order`/`OrderItem` são criados com o preço unitário "congelado" no momento da compra.

No SQLite, `select_for_update()` não trava linha individual — a consistência real vem de `transaction_mode: "IMMEDIATE"` (configurado em `DATABASES`), que serializa as transações no nível do arquivo inteiro. Em Postgres o mesmo código passaria a usar lock de linha de verdade, sem mudança na lógica.

`orders/tests.py::ConcurrencyTests` sobe duas threads reais disputando a última unidade e confere que só um pedido é criado e o estoque nunca fica negativo.

## Endpoints

| Método | Rota                        | Auth    | Descrição                              |
|--------|-----------------------------|---------|-----------------------------------------|
| GET    | `/`                         | pública | Home: categorias, busca, produtos ativos |
| GET    | `/produto/<slug>/`          | pública | Detalhe do produto                      |
| POST   | `/produto/<slug>/comprar/`  | logado  | Compra direta (1 unidade)               |
| GET    | `/carrinho/`                | logado  | Ver/editar carrinho                     |
| POST   | `/carrinho/finalizar/`      | logado  | Fecha pedido com os itens do carrinho   |
| GET    | `/api/v1/produtos/`         | pública | Lista paginada, filtrável por categoria |
| POST   | `/api/v1/pedidos/`          | JWT     | Cria pedido a partir de uma lista de itens |
| GET    | `/api/v1/pedidos/`          | JWT     | Pedidos do usuário autenticado          |
| POST   | `/api/v1/token/`            | pública | Emite `access`/`refresh` JWT            |

Filtro de produtos: `?categoria=<id>` ou `?categoria_slug=<slug>`.

## Segurança

- **IDOR:** toda consulta/escrita de `Order` filtra por `request.user`; o dono nunca vem do payload.
- **SQL Injection:** apenas ORM em todo o projeto, sem `.raw()`/`.extra()`.
- **Autenticação:** JWT (`djangorestframework-simplejwt`) — stateless, `access` expira em 5 min, renovável via `refresh`.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "<senha>"}'

curl -X POST http://127.0.0.1:8000/api/v1/pedidos/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"itens": [{"sku": "DEMO-FONEBLUETOOT", "quantidade": 2}]}'
```
