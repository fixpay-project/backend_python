
from rest_framework import serializers
from ssepl_backend import settings
from .models import *
from django.utils.crypto import get_random_string
from control_panel.models import *
from django.utils import timezone


class ContactNoSerializer(serializers.Serializer):
    contact_no = serializers.CharField(max_length=10)


class CodeSerializer(serializers.Serializer):
    # email = serializers.EmailField()
    code = serializers.CharField(max_length=6)


class GenerateCredentialsSerializer(serializers.Serializer):
    password = serializers.CharField(required=True)


class PortalUserWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortalUserWallet
        # fields = ['main_wallet', 'cashin_wallet']
        fields = "__all__"


class PortalUserSerializer(serializers.ModelSerializer):
    """
    Serializer for the PortalUser model.
    """

    class Meta:
        model = PortalUser
        fields = ['id', 'pu_name', 'pu_email', 'pu_contact_no', 'pu_role', 'username']
        # read_only_fields = ['password']


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ['city_name']


class StateSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = ['state_name']


class PortalUserDetailsSerializers(serializers.ModelSerializer):
    city = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()
    doc_images = serializers.SerializerMethodField()

    class Meta:
        model = PortalUserDetails
        exclude = ['created_at', 'updated_at', 'pu']

    def get_doc_images(self, obj):
        request = self.context.get('request')
        scheme = "https" if request.is_secure() else "http"

        docs_files_json = obj.doc_images

        if docs_files_json:
            for k, v in docs_files_json.items():
                file_path = v.replace('\\', '/')
                docs_files_json[k] = f"{scheme}://{request.get_host()}{settings.MEDIA_URL}{file_path}"
        return docs_files_json

    def get_city(self, obj):
        try:
            city = City.objects.get(city_id=obj.city_id)
            serializer = CitySerializer(city)
            return serializer.data
        except City.DoesNotExist:
            return None

    def get_state(self, obj):
        try:
            state = State.objects.get(state_id=obj.state_id)
            serializer = StateSerializer(state)
            return serializer.data
        except State.DoesNotExist:
            return None


class HSNSACSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdHSNSAC
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdService
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ServiceProviderSerializer(serializers.ModelSerializer):
    rupay_mdr = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    mastercard_mdr = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    visa_mdr = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    gst_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    class Meta:
        model = AdServiceProvider
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdCharges
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class DistributorHierarchySerializer(serializers.ModelSerializer):
    # Define parent_category_name as a SerializerMethodField
    parent_category_name = serializers.SerializerMethodField()
    hc_charges = serializers.SerializerMethodField()

    class Meta:
        model = DistributorHierarchy
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_parent_category_name(self, obj):
        # Check if `dh_parent_id` exists and return its name
        if obj.dh_parent_id:
            parent_category_name = DistributorHierarchy.objects.get(dh_id=obj.dh_parent_id).dh_name
        else:
            parent_category_name = None
        return parent_category_name

    def get_hc_charges(self, obj):
        # Check if `dh_parent_id` exists and return its name
        sp_id = self.context.get('request').data.get('sp_id')

        if obj.dh_id:
            try:
                hirerchy_charges_data = HierarchyCharges.objects.get(dh=obj.dh_id, sp=sp_id).hc_charges
            except:
                hirerchy_charges_data = []
        else:
            hirerchy_charges_data = []

        return hirerchy_charges_data


class HierarchyChargesSerializer(serializers.ModelSerializer):
    class Meta:
        model = HierarchyCharges
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        exclude_fields = self.context.get('exclude_fields', [])

        for field in exclude_fields:
            representation.pop(field, None)

        return representation


class BankDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankDetails
        exclude = ["deposite_category", "created_at", "updated_at", "updated_by", "created_by", "is_deactive",
                   "is_delete"]


class FundRequestSerializer(serializers.ModelSerializer):
    bank_detail = serializers.SerializerMethodField()
    payment_proof = serializers.SerializerMethodField()

    class Meta:
        model = FundRequest
        # fields = '__all__'
        exclude = ["created_at", "updated_at", "updated_by", "created_by", "is_delete"]

    def get_bank_detail(self, obj):
        try:
            get_bank_detail = BankDetails.objects.get(bd_id=obj.deposite_bank.bd_id)
            serializer = BankDetailsSerializer(get_bank_detail)
            return serializer.data
        except BankDetails.DoesNotExist:
            return None

    def get_payment_proof(self, instance):
        request = self.context.get('request')
        scheme = "https" if request.is_secure() else "http"

        payment_proof = instance.payment_proof

        if payment_proof:
            file_path = payment_proof.get('payment_proof').replace('\\', '/')
            return f"{scheme}://{request.get_host()}/media/{file_path}"

        return None


class GlTrnSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlTrn
        fields = ['pu', 'gl_trn_id', 'service_trn_id', 'gl_trn_amt', 'gl_trn_dt']
        # fields = '__all__'


class PosServiceTrnSerializer(serializers.ModelSerializer):
    class Meta:
        model = PosServiceTrn
        exclude = ["created_at"]

class PgServiceTrnSerializer(serializers.ModelSerializer):
    class Meta:
        model = PgServiceTrn
        fields = "__all__"


class WalletTrnSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTrn
        exclude = ['created_at']

class PGBaseChargeSerializer(serializers.ModelSerializer):
    pg_name = serializers.CharField(source='pg.name', read_only=True)
    card_type_name = serializers.CharField(source='card_type.name', read_only=True)

    class Meta:
        model = PGBaseCharge
        fields = '__all__'  # Or list them explicitly
        # This now includes 'pg_name' and 'card_type_name'


class UserLevelChargeSerializer(serializers.ModelSerializer):
    pg_name = serializers.CharField(source='pg.name', read_only=True)
    card_type_name = serializers.CharField(source='card_type.name', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)  



    class Meta:
        model = UserCharge
        fields = '__all__'  # Or list them explicitly
        # This now includes 'pg_name' and 'card_type_name'


class PaymentGetwayAuthenticationDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentGetwayAuthenticationDetails
        exclude = ["created_at"]
#BBPS Biller ------->
class BBPSBillerCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BBPSBillerCategory
        exclude = ["created_at", "updated_at"]


class BBPSBillerSerializer(serializers.ModelSerializer):
    class Meta:
        model = BBPSBiller
        exclude = ["created_at", "updated_at"]


class BBPSBillerResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = BBPSBillResponse
        exclude = ["created_at"]


class BBPSBillerPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = BBPSBillPayment
        exclude = ["updated_at"]


class ServiceAccountRequestSerializer(serializers.ModelSerializer):
    pu_name = serializers.CharField(source='pu.username', read_only=True)
    pu_contact = serializers.CharField(source='pu.pu_contact_no', read_only=True)
    pu_unique_id = serializers.CharField(source='pu.portaluserdetails.pud_unique_id', read_only=True)
    
    class Meta:
        model = ServiceAccountRequest
        fields = [
            'sar_id',
            'pu',
            'pu_name',
            'pu_contact',
            'pu_unique_id',
            'from_wallet',
            'to_wallet',
            'amount',
            'description',
            'request_status',
            'reasons',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['sar_id', 'created_at', 'updated_at']



class UserServiceFinanceSerializer(serializers.ModelSerializer):
    created_at = serializers.SerializerMethodField()
    user_id = serializers.IntegerField(source='user.id', read_only=True)


    def get_created_at(self, obj):
        if obj.created_at and timezone.is_naive(obj.created_at):
            return timezone.make_aware(obj.created_at)
        return obj.created_at

    class Meta:
        model = UserServiceFinance
        fields = [
            'id',
            'user_id',
            'instant_charge',
            'od_limit',
            'available_limit',
            'usage_limit',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'available_limit', 'usage_limit']
