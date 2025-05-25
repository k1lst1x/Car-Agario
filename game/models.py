from django.db import models
from django.utils.translation import gettext_lazy as _


class GameSession(models.Model):
    """
    Локальная «комната». При деплое можно будет хранить активные игры в Redis,
    а здесь оставим в БД для наглядности.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)


class Car(models.Model):
    session = models.ForeignKey(
        GameSession, on_delete=models.CASCADE, related_name="cars"
    )
    # псевдоним гостя
    nickname = models.CharField(max_length=24, default="Guest")
    # базовые статы
    hp = models.PositiveIntegerField(default=800)
    speed = models.FloatField(default=220)  # км/ч
    damage = models.PositiveIntegerField(default=40)
    fire_rate = models.FloatField(default=2.0)  # выстр/сек

    # позиция и угол (обновляется клиентом)
    x = models.FloatField(default=0)
    y = models.FloatField(default=0)
    angle = models.FloatField(default=0)

    gold = models.PositiveIntegerField(default=0)
    xp = models.PositiveIntegerField(default=0)

    def upgrade_cost(self, stat, n_already):
        """
        cost × 1.35ⁿ  — n_already берём из таблицы апов
        """
        base = {
            "hp": 100,
            "speed": 100,
            "damage": 100,
            "fire_rate": 100,
        }[stat]
        return int(base * (1.35**n_already))


class Upgrade(models.Model):
    class Stat(models.TextChoices):
        HP = "hp", _("HP")
        SPEED = "speed", _("Speed")
        DAMAGE = "damage", _("Gun Damage")
        FIRE_RATE = "fire_rate", _("Fire Rate")

    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="upgrades")
    stat = models.CharField(max_length=12, choices=Stat.choices)
    level = models.PositiveIntegerField(default=1)
    bought_at = models.DateTimeField(auto_now_add=True)


class Orb(models.Model):
    class Type(models.TextChoices):
        GOLD = "gold", _("Gold")
        DAMAGE = "damage", _("Damage x2 (6s)")
        VELOCITY = "velocity", _("Speed +40% (6s)")
        VANISH = "vanish", _("Invisible (4s)")
        REGEN = "regen", _("Fast regen (6s)")
        XP = "xp", _("+1 XP")

    session = models.ForeignKey(
        GameSession, on_delete=models.CASCADE, related_name="orbs"
    )
    kind = models.CharField(max_length=10, choices=Type.choices)
    x = models.FloatField()
    y = models.FloatField()
    spawned_at = models.DateTimeField(auto_now_add=True)
