from django.db import models


class Guide(models.Model):
    class Level(models.TextChoices):
        NOVICE = "novice", "For beginners"
        PRO = "pro", "Going further"

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=120)
    summary = models.CharField(max_length=200)
    level = models.CharField(max_length=6, choices=Level.choices, default=Level.NOVICE)
    minutes = models.PositiveSmallIntegerField("minutes to read", default=3)
    order = models.PositiveSmallIntegerField(default=0)
    body = models.TextField("text (Markdown)")
    is_published = models.BooleanField("published", default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title
