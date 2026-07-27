from rest_framework import serializers
from .models import *


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        exclude = ['created_by', 'created_at', 'updated_by', 'updated_at']


class PartnersSerializer(serializers.ModelSerializer):
    class Meta:
        model = Partners
        exclude = ['created_by', 'created_at', 'updated_by', 'updated_at']


class NewsLatterSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsLatter
        exclude = ['created_by', 'created_at', 'updated_by', 'updated_at']


class AboutUsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AboutUs
        exclude = ['created_by', 'created_at', 'updated_by', 'updated_at']


class ServicesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Services

        exclude = ['created_by', 'created_at', 'updated_by', 'updated_at']


class ServiceGroupSerializer(serializers.ModelSerializer):
    services = ServicesSerializer(many=True, read_only=True).exclude = ['created_by', 'created_at', 'updated_by',
                                                                        'updated_at']

    class Meta:
        model = ServiceGroup
        fields = ['service_group_id', 'service_group_title', 'service_group_description', 'services']
        depth = 1


class ServicesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Services
        exclude = ['created_by', 'created_at', 'updated_by', 'updated_at']


class RandomStuffSerializer(serializers.ModelSerializer):
    class Meta:
        model = RandomStuff

        exclude = ['created_by', 'created_at', 'updated_by', 'updated_at']


class LeadDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadDetails
        exclude = ['created_by', 'created_at', 'updated_by', 'updated_at']

