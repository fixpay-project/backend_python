# Local Application Imports
from django.db import models
from admin_hub.models import PortalUser


class Banners(models.TextChoices):
    web_banner = 'WEB BANNER', 'WEB BANNER'
    mobile_banner = 'MOBILE BANNER', 'MOBILE BANNER'
    login_page_banner = 'LOGIN PAGE BANNER', 'LOGIN PAGE BANNER'


class ContactEnquiryStatus(models.TextChoices):
    new = 'NEW', 'NEW'
    processing = 'PROCESSING', 'PROCESSING'
    resolved = 'RESOLVED', 'RESOLVED'


class ContactEnquiryType(models.TextChoices):
    contact_enquiry = 'CONTACT ENQUIRY', 'CONTACT ENQUIRY'
    become_a_partner = 'BECOME A PARTNER', 'BECOME A PARTNER'


class Banner(models.Model):
    banner_id = models.AutoField(primary_key=True)
    banner_title = models.CharField(max_length=200)
    banner_type = models.CharField(max_length=50, choices=Banners.choices)
    banner_image = models.JSONField()
    banner_description = models.TextField()
    is_deactive = models.BooleanField(default=False)
    banner_is_delete = models.BooleanField(default=False)
    created_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='banner_created_by', db_column='created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='banner_updated_by', db_column='updated_by')
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ad_web_banner'
        app_label = 'admin_hub'


class Partners(models.Model):
    partners_id = models.AutoField(primary_key=True)
    partners_name = models.CharField(max_length=200)
    partners_logo_image = models.JSONField()
    partners_description = models.TextField()
    is_deactive = models.BooleanField(default=False)
    partners_is_delete = models.BooleanField(default=False)
    created_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='partners_created_by', db_column='created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='partners_updated_by', db_column='updated_by')
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ad_web_partners'
        app_label = 'admin_hub'


class NewsLatter(models.Model):
    news_id = models.AutoField(primary_key=True)
    news_supplier_name = models.CharField(max_length=200)
    news_email_id = models.EmailField(unique=True)
    is_deactive = models.BooleanField(default=False)
    news_is_delete = models.BooleanField(default=False)
    created_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='newslatter_created_by', db_column='created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='newslatter_updated_by', db_column='updated_by')
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ad_web_news_latter'
        app_label = 'admin_hub'


class AboutUs(models.Model):
    about_id = models.AutoField(primary_key=True)
    about_description = models.TextField()
    about_our_focus = models.TextField(null=True, blank=True)
    about_our_mission = models.TextField(null=True, blank=True)
    about_our_vision = models.TextField(null=True, blank=True)
    about_is_delete = models.BooleanField(default=False)
    created_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='aboutus_created_by', db_column='created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='aboutus_updated_by', db_column='updated_by')
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ad_web_about_us'
        app_label = 'admin_hub'


class ServiceGroup(models.Model):
    service_group_id = models.AutoField(primary_key=True)
    service_group_title = models.CharField(max_length=500)
    service_group_description = models.TextField()
    is_deactive = models.BooleanField(default=False)
    service_group_is_delete = models.BooleanField(default=False)
    created_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='servicegroup_created_by', db_column='created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='servicegroup_updated_by', db_column='updated_by')
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ad_web_service_group'
        app_label = 'admin_hub'


class Services(models.Model):
    service_id = models.AutoField(primary_key=True)
    service_title = models.CharField(max_length=200)
    services_group = models.ForeignKey(ServiceGroup, on_delete=models.PROTECT, related_name='services', null=True, blank=True)
    service_image = models.JSONField()
    service_description = models.TextField()
    is_deactive = models.BooleanField(default=False)
    service_is_delete = models.BooleanField(default=False)
    created_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='services_created_by', db_column='created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='services_updated_by', db_column='updated_by')
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ad_web_services'
        app_label = 'admin_hub'


class RandomStuff(models.Model):
    random_stuff_id = models.AutoField(primary_key=True)
    random_privacy_policy = models.TextField(null=True, blank=True)
    random_terms_conditions = models.TextField(null=True, blank=True)
    random_return_cancellation = models.TextField(null=True, blank=True)
    random_is_delete = models.BooleanField(default=False)
    created_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='randomstuff_created_by', db_column='created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='randomstuff_updated_by', db_column='updated_by')
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ad_web_random_stuff'
        app_label = 'admin_hub'


class LeadDetails(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    contact_number = models.CharField(max_length=20, null=True, blank=True)
    subject = models.CharField(max_length=200, null=True, blank=True)
    type = models.CharField(max_length=50, choices=ContactEnquiryType, null=True, blank=True)
    shop_name = models.CharField(max_length=500, null=True, blank=True)
    message = models.TextField(null=True, blank=True)
    is_deactive = models.BooleanField(default=False)
    status = models.CharField(max_length=50, choices=ContactEnquiryStatus, default='NEW')
    is_delete = models.BooleanField(default=False)
    created_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='contactenquiry_created_by', db_column='created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True, related_name='contactenquiry_updated_by', db_column='updated_by')
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ad_web_lead_details'
        app_label = 'admin_hub'

