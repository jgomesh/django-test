from django.db import models


class Category(models.Model):
    """Categoria de produtos."""

    nome = models.CharField("nome", max_length=120)
    slug = models.SlugField("slug", max_length=140, unique=True)
    descricao = models.TextField("descrição", blank=True)

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class Product(models.Model):
    """Produto disponível para venda."""

    nome = models.CharField("nome", max_length=200)
    sku = models.CharField("SKU", max_length=64, unique=True)
    preco = models.DecimalField("preço", max_digits=10, decimal_places=2)
    quantidade_estoque = models.PositiveIntegerField("quantidade em estoque", default=0)
    imagem = models.ImageField("imagem", upload_to="produtos/", blank=True, null=True)
    categoria = models.ForeignKey(
        Category,
        verbose_name="categoria",
        on_delete=models.PROTECT,
        related_name="produtos",
    )
    ativo = models.BooleanField("ativo", default=True)
    slug = models.SlugField("slug", max_length=220, unique=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome

    @property
    def em_estoque(self) -> bool:
        return self.quantidade_estoque > 0
