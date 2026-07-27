#CONTROL PANEL
from django.db import models

# Create your models here.

class State(models.Model):
    state_id = models.AutoField(primary_key=True)
    state_name = models.CharField(max_length=100, unique=True)
    short_name = models.CharField(max_length=20, unique=True, null=True, blank=True)
    code = models.CharField(null=True, max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    create_by = models.IntegerField(null=True)
    update_at = models.DateTimeField(null=True)
    update_by = models.IntegerField(null=True)

    def __str__(self):
        return self.state_name

    class Meta:
        db_table = 'sa_state'

class City(models.Model):
    city_id = models.AutoField(primary_key=True)
    state = models.ForeignKey(State, on_delete=models.CASCADE)
    city_name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    create_by = models.IntegerField(null=True)
    update_at = models.DateTimeField(null=True)
    update_by = models.IntegerField(null=True)

    def __str__(self):
        return self.city_name

    class Meta:
        db_table = 'sa_city'
        constraints = [
            models.UniqueConstraint(fields=['city_name', 'state_id'], name='unique_city_name_state_id')
        ]