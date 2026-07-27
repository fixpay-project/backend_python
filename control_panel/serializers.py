from rest_framework import serializers
from .models import *


class StateSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = '__all__'

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        exclude_fields = self.context.get('exclude_fields', [])
        for field in exclude_fields:
            representation.pop(field, None)
        return representation


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = '__all__'

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        exclude_fields = self.context.get('exclude_fields', [])
        for field in exclude_fields:
            representation.pop(field, None)
        return representation