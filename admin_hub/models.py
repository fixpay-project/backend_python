from django.db import models
from django.utils import timezone



class ServiceNatureChoice(models.TextChoices):
    charges = 'CHARGE'
    commission = 'COMMISSION'


class hooks_details(models.Model):
    id = models.AutoField(primary_key=True)
    txn_id = models.CharField(max_length=255, null=True, blank=True)
    response_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.id

    class Meta:
        db_table = "ad_hooks_details"
        app_label = 'admin_hub'


# ---->Onbording

class PgTrnChoice(models.TextChoices):
    PENDING = 'PENDING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    SETTLED = 'SETTLED'


class MrkTyChoice(models.TextChoices):
    CR = 'CR'
    DR = 'DR'


class RequestStatus(models.TextChoices):
    PENDING = 'PENDING'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'
    REVERSED = 'REVERSED'
    INACTIVE = 'INACTIVE'



class TransactionMode(models.TextChoices):
    IMPS = 'IMPS'
    RTGS = 'RTGS'
    NEFT = 'NEFT'


class AdHSNSAC(models.Model):
    hsnsac_id = models.AutoField(primary_key=True)
    hsnsac_code = models.CharField(max_length=255)
    tax_rate = models.DecimalField(max_digits=10, decimal_places=3)
    description = models.TextField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('PortalUser', on_delete=models.PROTECT, db_column='created_by', null=True)
    updated_at = models.DateTimeField(null=True)
    is_deactive = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return self.hsnsac_code

    class Meta:
        db_table = "ad_hsn_sac_code"
        app_label = 'admin_hub'

class AdMenu(models.Model):
    menu_id = models.AutoField(primary_key=True)
    menu_name = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    is_deactive = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return self.menu_name

    class Meta:
        db_table = "ad_portal_menu"
        app_label = 'admin_hub'



class AdService(models.Model):
    service_id = models.AutoField(primary_key=True)
    service_name = models.CharField(max_length=50)
    description = models.TextField(null=True)
    is_global = models.BooleanField(default=False)
    is_table_config = models.BooleanField(default=False)
    config_table_name = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('PortalUser', on_delete=models.PROTECT, db_column='created_by', null=True)
    updated_at = models.DateTimeField(null=True)
    is_deactive = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return self.service_name

    class Meta:
        db_table = "ad_service"
        app_label = 'admin_hub'


class AdServiceProvider(models.Model):
    sp_id = models.AutoField(primary_key=True)
    service = models.ForeignKey(AdService, on_delete=models.CASCADE)
    sp_name = models.CharField(max_length=150, null=True)
    label = models.CharField(max_length=255, null=True)
    tds_rate = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    created_by = models.ForeignKey('PortalUser', on_delete=models.PROTECT, db_column='created_by', null=True)
    hsn_sac = models.ForeignKey(AdHSNSAC, on_delete=models.PROTECT, null=True)
    parent_name = models.CharField(max_length=150, null=True, blank=True)
    credentials_json = models.JSONField(null=True, blank=True)
    service_nature = models.CharField(max_length=20, choices=ServiceNatureChoice.choices, null=True, blank=True)
    updated_at = models.DateTimeField(null=True)
    sa_provided = models.BooleanField(default=False)
    is_deactive = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    pg = models.ForeignKey('PaymentGateway', on_delete=models.PROTECT, null=True, blank=True)  
    rupay_mdr = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, default=0)
    mastercard_mdr = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, default=0)
    visa_mdr = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, default=0)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, default=0)
    menu = models.ForeignKey(AdMenu,on_delete=models.CASCADE, null=True, blank=True)
    is_instant = models.BooleanField(default=False)
    for_instant = models.ForeignKey("self",on_delete=models.SET_NULL,null=True,blank=True,related_name="instant_of",db_column="for_instant")


    def __str__(self):
        return self.sp_name

    class Meta:
        db_table = "ad_service_provider"
        app_label = 'admin_hub'


class AdCharges(models.Model):
    CHARGES_TYPE_CHOICES = [
        ('CR', 'Credit'),
        ('DR', 'Debit'),
    ]

    CHARGES_RATE_TYPE_CHOICES = [
        ('is_flat', 'Is_Flat'),
        ('is_percent', 'Is_Percent'),
    ]
    CHARGE_CATEGORY_CHOICES = [
        ('to_us', 'To Us'),
        ('to_provide', 'To Provide'),
    ]
    charges_id = models.AutoField(primary_key=True)
    service_provider = models.ForeignKey(AdServiceProvider, on_delete=models.CASCADE)
    charges_type = models.CharField(max_length=2, choices=CHARGES_TYPE_CHOICES)
    rate_type = models.CharField(max_length=20, choices=CHARGES_RATE_TYPE_CHOICES)
    minimum = models.DecimalField(max_digits=10, decimal_places=3, null=True)
    maximum = models.DecimalField(max_digits=10, decimal_places=3, null=True)
    rate = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    charge_category = models.CharField(max_length=20, choices=CHARGE_CATEGORY_CHOICES, default='to_us')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('PortalUser', on_delete=models.CASCADE, db_column='created_by', null=True,
                                   blank=True)
    updated_at = models.DateTimeField(null=True)
    is_deactive = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.charges_id} ({self.service_provider.sp_name})"

    class Meta:
        db_table = 'ad_charges'
        app_label = 'admin_hub'


class AdCommissionCharges(models.Model):
    CHARGES_TYPE_CHOICES = [
        ('CR', 'Credit'),
        ('DR', 'Debit'),
    ]

    CHARGES_RATE_TYPE_CHOICES = [
        ('is_flat', 'Is_Flat'),
        ('is_percent', 'Is_Percent'),
        ('is_slab', 'Is_Slab'),
    ]

    commission_charges_id = models.AutoField(primary_key=True)
    service_provider = models.ForeignKey(AdServiceProvider, on_delete=models.CASCADE)
    charges_type = models.CharField(max_length=2, choices=CHARGES_TYPE_CHOICES, blank=True, null=True)
    rate_type = models.CharField(max_length=20, choices=CHARGES_RATE_TYPE_CHOICES)
    minimum = models.DecimalField(max_digits=10, decimal_places=3, null=True)
    maximum = models.DecimalField(max_digits=10, decimal_places=3, null=True)
    rate = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    is_slab = models.BooleanField(default=False, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('PortalUser', on_delete=models.CASCADE, db_column='created_by', null=True,
                                   blank=True)
    updated_at = models.DateTimeField(null=True)
    is_deactive = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.commission_charges_id} ({self.service_provider.sp_name})"

    class Meta:
        db_table = 'ad_commission_charges'
        app_label = 'admin_hub'


#BIN CHECKER 
class BinChecker(models.Model):
    CARD_CHARGE_TYPES = [
        ('REGULAR', 'REGULAR'),
        ('PREMIUM', 'PREMIUM'),
    ]
    bnc_id = models.AutoField(primary_key=True)
    card_number = models.CharField(max_length=20, unique=True)  
    response_data = models.JSONField()
    charge_type = models.CharField(max_length=10, choices=CARD_CHARGE_TYPES,blank=True,null=True) 
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('PortalUser', on_delete=models.PROTECT, db_column='created_by', null=True)
    updated_at = models.DateTimeField(null=True)
    updated_by = models.IntegerField(null=True, db_column='updated_by')

    def __str__(self):
        return f"{self.charge_type}"
    
    class Meta:
        db_table = 'ad_bin_checker' 


class PortalUser(models.Model):
    PORTAL_USER_TYPE = [
        ('Admin', 'Admin'),
        ('Distributor', 'Distributor'),
        ('Retailer', 'Retailer'),
    ]
    id = models.AutoField(primary_key=True)
    pu_name = models.CharField(max_length=150)
    pu_email = models.CharField(max_length=100, unique=True)
    pu_contact_no = models.CharField(max_length=10, unique=True)
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128, null=True, blank=True)
    pu_role = models.CharField(max_length=20, choices=PORTAL_USER_TYPE)
    verify_code = models.CharField(max_length=128, blank=True, null=True)
    verify_code_expire_at = models.DateTimeField(blank=True, null=True)
    is_verify = models.BooleanField(default=False)
    is_kyc_verify = models.BooleanField(default=False)
    is_default_change = models.BooleanField(default=False)
    pu_status = models.CharField(choices=RequestStatus, default=RequestStatus.PENDING, max_length=100)
    pu_reason = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True)
    is_deactive = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    mpin = models.IntegerField(default=0)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    under_review = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.id} ({self.pu_role})"

    class Meta:
        db_table = 'ad_portal_user'
        app_label = 'admin_hub'

class BulkMessageLog(models.Model):
    MESSAGE_TYPE_CHOICES = [
        ('mail', 'Mail'),
        ('sms', 'SMS'),
    ]
    user = models.ForeignKey(PortalUser, on_delete=models.CASCADE)
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES)
    subject = models.CharField(max_length=255, blank=True, null=True)
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bulk_message'
        app_label = 'admin_hub'


class PortalUserLoginLogs(models.Model):
    id = models.AutoField(primary_key=True)
    pu_user = models.ForeignKey(PortalUser, on_delete=models.PROTECT)
    pu_user_role = models.CharField(max_length=50)
    pu_token = models.CharField(max_length=300, null=True, blank=True)
    is_expire = models.BooleanField(default=False, null=True, blank=True)
    expire_datetime = models.DateTimeField(null=True, blank=True)
    browser_type = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.id} ({self.pu_user})"

    class Meta:
        db_table = 'ad_portal_user_login_logs'
        app_label = 'admin_hub'


class PortalUserDetails(models.Model):
    pud_id = models.AutoField(primary_key=True)
    dh = models.ForeignKey("DistributorHierarchy", on_delete=models.PROTECT, null=True)
    pu = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True)
    pud_unique_id = models.CharField(max_length=100, null=True, blank=True)
    aadhaar_card = models.CharField(max_length=12, null=True, blank=True)
    pan_card = models.CharField(max_length=10, null=True, blank=True)
    pan_response = models.TextField(null=True, blank=True)
    dst_rtl_image = models.ImageField(upload_to='Retailer', null=True, blank=True)
    dst_rtl_location = models.JSONField(null=True, blank=True)
    shop_name = models.CharField(max_length=255, null=True, blank=True)
    shop_address = models.TextField(null=True, blank=True)
    shop_state = models.IntegerField(null=True, blank=True)
    shop_city = models.IntegerField(null=True, blank=True)
    shop_zip_code = models.CharField(max_length=6, null=True, blank=True)
    doc_images = models.JSONField(null=True, blank=True)
    shop_location = models.JSONField(null=True, blank=True)
    shop_gst_number = models.CharField(max_length=15, null=True, blank=True)
    busniess_type = models.CharField(max_length=10, null=True, blank=True)
    alternate_contact_no = models.CharField(max_length=10, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    kyc_current_location = models.JSONField(null=True, blank=True)
    state_id = models.IntegerField(null=True, blank=True)
    city_id = models.IntegerField(null=True, blank=True)
    zip_code = models.CharField(max_length=6, null=True, blank=True)
    created_by = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    onboarding_cheque_uploaded_at = models.DateTimeField(null=True, blank=True)
    security_cheque_uploaded_at = models.DateTimeField(null=True, blank=True)
    declaration_pdf_uploaded_at = models.DateTimeField(null=True, blank=True)
    upload_status = models.CharField(max_length=20, null=True, blank=True)
    security_upload_status = models.CharField(max_length=20, null=True, blank=True)
    pdf_upload_status = models.CharField(max_length=20, null=True, blank=True)
    onboarding_cheque_comment = models.TextField(null=True, blank=True)
    security_cheque_comment = models.TextField(null=True, blank=True)
    declaration_pdf_comment = models.TextField(null=True, blank=True)
    onboarding_check_num = models.CharField(null=True, blank=True,max_length=15)
    security_check_num = models.CharField(null=True, blank=True,max_length=15)

    def __str__(self) -> str:
        return f"{self.pud_id}"

    class Meta:
        db_table = 'ad_portal_user_details'
        app_label = 'admin_hub'


class PortalUserWallet(models.Model):
    puw_id = models.AutoField(primary_key=True)
    pu = models.ForeignKey(PortalUser, on_delete=models.PROTECT, unique=True)
    main_wallet = models.DecimalField(max_digits=19, decimal_places=3, default=0.00)
    cashin_wallet = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    pg_wallet = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True)
    updated_by = models.IntegerField(null=True, db_column='updated_by')

    def __str__(self):
        return f"{self.puw_id}"

    class Meta:
        db_table = 'ad_portal_user_wallet'
        app_label = 'admin_hub'


class DistributorHierarchy(models.Model):  ####
    dh_id = models.AutoField(primary_key=True)
    dh_name = models.CharField(max_length=150, unique=True)
    dh_parent_id = models.IntegerField(null=True, blank=True)
    dh_description = models.TextField()
    dh_prefix = models.CharField(max_length=6, null=True, blank=True)
    is_used = models.BooleanField(default=False)
    is_deactive = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, db_column='created_by', null=True)
    updated_at = models.DateTimeField(null=True)
    updated_by = models.IntegerField(null=True, db_column='updated_by')

    def __str__(self) -> str:
        return super().__str__()

    class Meta:
        db_table = 'ad_distributor_hierarchy'
        app_label = 'admin_hub'


class HierarchyCharges(models.Model):
    hc_id = models.AutoField(primary_key=True)
    dh = models.ForeignKey(DistributorHierarchy, on_delete=models.PROTECT, null=True)
    sp = models.ForeignKey(AdServiceProvider, on_delete=models.PROTECT, null=True)
    mark_type = models.CharField(max_length=10, choices=MrkTyChoice.choices, null=True)
    hc_charges = models.JSONField(null=True)
    is_deactive = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, db_column='created_by', null=True)
    updated_at = models.DateTimeField(null=True)
    updated_by = models.IntegerField(null=True, db_column='updated_by')

    def __str__(self) -> str:
        return super().__str__()

    class Meta:
        db_table = 'ad_hierarchy_charges'
        app_label = 'admin_hub'


class PortalUserCharges(models.Model):  #####
    puc_id = models.AutoField(primary_key=True)
    sp = models.ForeignKey(AdServiceProvider, on_delete=models.PROTECT, null=True)
    dh = models.ForeignKey(DistributorHierarchy, on_delete=models.PROTECT, null=True)
    pu_id = models.IntegerField(null=True)
    parent_id = models.IntegerField(null=True)
    mark_type = models.CharField(max_length=10, choices=MrkTyChoice.choices, null=True)
    puc_charges = models.JSONField(null=True)
    is_pinned = models.BooleanField(default=False)
    is_deactive = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, db_column='created_by', null=True)
    updated_at = models.DateTimeField(null=True)
    updated_by = models.IntegerField(null=True, db_column='updated_by')

    def __str__(self) -> str:
        return super().__str__()

    class Meta:
        db_table = 'ad_portal_user_charges'
        app_label = 'admin_hub'


'''
Payout Module End
'''


class UserActivity(models.Model):
    ua_id = models.AutoField(primary_key=True)
    table_id = models.IntegerField()
    table_name = models.CharField(max_length=100)
    ua_action = models.CharField(max_length=100)
    ua_description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(PortalUser, on_delete=models.SET_NULL, null=True, db_column='created_by')
    request_data = models.TextField(null=True)
    response_data = models.TextField(null=True)

    def __str__(self):
        return f"{self.ua_action} on {self.table_name} at {self.created_at}"

    class Meta:
        db_table = "ad_user_activity"
        app_label = 'admin_hub'


class UserCodeVerification(models.Model):
    ucv_id = models.AutoField(primary_key=True)
    ucv_data = models.CharField(max_length=100)
    verify_code = models.CharField(max_length=128, blank=True, null=True)
    verify_code_expire_at = models.DateTimeField(blank=True, null=True)
    is_verify = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return super().__str__()

    class Meta:
        db_table = 'ad_user_code_verification'
        app_label = 'admin_hub'


class BankDetails(models.Model):
    bd_id = models.AutoField(primary_key=True)
    deposite_category = models.JSONField()
    bank_name = models.CharField(max_length=128, blank=True, null=True)
    ifsc_code = models.CharField(max_length=128, blank=True, null=True)
    branch_name = models.CharField(max_length=128, blank=True, null=True)
    account_type = models.CharField(max_length=128, blank=True, null=True)
    account_number = models.CharField(max_length=128, blank=True, null=True)
    is_deactive = models.BooleanField(default=False)
    is_delete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, db_column='created_by', null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.IntegerField(null=True, blank=True, db_column='updated_by')

    def __str__(self) -> str:
        return super().__str__()

    class Meta:
        db_table = 'ad_bank_detail'
        app_label = 'admin_hub'



class BankDetailsUser(models.Model):
    bd_id = models.AutoField(primary_key=True)
    bank_name = models.CharField(max_length=128, blank=True, null=True)
    ifsc_code = models.CharField(max_length=128, blank=True, null=True)
    account_holder_name = models.CharField(max_length=128, blank=True, null=True)
    account_number = models.CharField(max_length=128, blank=True, null=True)
    is_deactive = models.BooleanField(default=False)
    is_delete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(PortalUser, on_delete=models.PROTECT, db_column='created_by', null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.IntegerField(null=True, blank=True, db_column='updated_by')
    bank_branch = models.CharField(max_length=500, blank=True, null=True)

    def __str__(self) -> str:
        return super().__str__()

    class Meta:
        db_table = 'ad_bank_detail_user'
        app_label = 'admin_hub'


class FundRequest(models.Model):
    fr_id = models.AutoField(primary_key=True)
    deposite_category = models.JSONField()
    deposite_bank = models.ForeignKey(BankDetails, on_delete=models.PROTECT)
    deposite_amount = models.DecimalField(max_digits=19, decimal_places=3, null=True)
    transaction_id = models.CharField(max_length=128, unique=True, blank=True, null=True)
    utr_number = models.CharField(max_length=128, unique=True, blank=True, null=True)
    transaction_mode = models.CharField(choices=TransactionMode, max_length=128, blank=True, null=True)
    payment_proof = models.JSONField()
    remark = models.TextField(null=True, blank=True)
    is_deactive = models.BooleanField(default=False)
    is_delete = models.BooleanField(default=False)
    request_status = models.CharField(choices=RequestStatus, default=RequestStatus.PENDING, max_length=100)
    reasons = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        PortalUser, on_delete=models.PROTECT, db_column='created_by', null=True)
    updated_at = models.DateTimeField(null=True)
    updated_by = models.IntegerField(null=True, db_column='updated_by')

    def __str__(self) -> str:
        return super().__str__()

    class Meta:
        db_table = 'ad_fund_request'
        app_label = 'admin_hub'


class PosDevice(models.Model):
    pos_d_id = models.AutoField(primary_key=True)
    pu = models.ForeignKey(PortalUser, on_delete=models.PROTECT, null=True, blank=True)
    terminal = models.CharField(max_length=225, null=True, blank=True)
    sp = models.ForeignKey(AdServiceProvider, on_delete=models.PROTECT, null=True)
    created_by = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_deactive = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    is_expires_at = models.CharField(max_length=25, null=True, blank=True)


    def __str__(self):
        return f'{self.pos_d_id}'

    class Meta:
        db_table = "ad_pos_device"
        app_label = 'admin_hub'


class TerminalRetailerHistory(models.Model):
    ACTION_CHOICES = [
        ('assigned', 'Assigned'),
        ('activated', 'Activated'),
        ('deactivated', 'Deactivated'),
        ('reassigned', 'Reassigned'),
        ('expiry_updated', 'Expiry Updated'),  
    ]
    terminal_h_id = models.AutoField(primary_key=True)
    terminal = models.ForeignKey(PosDevice, on_delete=models.CASCADE)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(PortalUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='performed_actions')
    timestamp = models.DateTimeField(auto_now_add=True)
    remarks = models.TextField(blank=True, null=True)

    def __str__(self):
        return f'{self.terminal_h_id} - {self.action}'

    class Meta:
        db_table = "ad_pos_device_history"
        app_label = 'admin_hub'

# RAZOPPAY POS
class PosServiceTrn(models.Model):
    pos_trn_id = models.AutoField(primary_key=True)
    terminal_id = models.CharField(max_length=225, null=True, blank=True)
    sp = models.ForeignKey(AdServiceProvider, on_delete=models.PROTECT, null=True)
    trn_unique_id = models.CharField(max_length=255, unique=True)
    trn_amount = models.DecimalField(max_digits=10, decimal_places=3)
    customer_name = models.CharField(max_length=255, null=True, blank=True)
    trn_response = models.JSONField()
    is_settled = models.BooleanField(default=False)
    trn_status = models.CharField(max_length=20, choices=RequestStatus, default=RequestStatus.PENDING)
    pos_charge_type = models.CharField(max_length=20, null=True, blank=True)
    # trn_settlement_status = models.CharField(max_length=20)# REMOVE THIS 09-01
    pos_trn_dt = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.pos_trn_id}"

    class Meta:
        db_table = 'ad_pos_service_transaction'
        app_label = 'admin_hub'


class WalletTrn(models.Model):
    wl_trn_id = models.AutoField(primary_key=True)
    action_id = models.IntegerField(null=True, blank=True)
    action_type = models.CharField(max_length=100)
    pu = models.ForeignKey(PortalUser, on_delete=models.PROTECT)
    wl_label = models.CharField(max_length=100)
    effectvie_wallet = models.CharField(max_length=20, null=True, blank=True)
    effectvie_amt = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    effective_type = models.CharField(max_length=10, choices=MrkTyChoice.choices)
    wl_trn_des = models.CharField(max_length=500, null=True, blank=True)
    wl_trn_dt = models.DateTimeField(null=True, blank=True)
    current_balance = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # for ad reason
    wl_reason = models.TextField(null=True)


    def __str__(self):
        return f"{self.wl_trn_id}"

    class Meta:
        db_table = 'ad_wallet_transaction'
        app_label = 'admin_hub'


class GlTrn(models.Model):
    gl_trn_id = models.AutoField(primary_key=True)
    service_trn_id = models.IntegerField(null=True, blank=True)
    service_trn_table = models.CharField(max_length=255, null=True, blank=True)
    pu = models.ForeignKey(PortalUser, on_delete=models.PROTECT)
    gl_trn_amt = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    gl_tds_rate = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    gl_tax_rate = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    gl_tds_amt = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    gl_tax_amt = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    effectvie_wallet = models.CharField(max_length=20, null=True, blank=True)
    effectvie_amt = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    effective_type = models.CharField(max_length=10, choices=MrkTyChoice.choices)
    gl_trn_dt = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.gl_trn_id}"

    class Meta:
        db_table = 'ad_global_transaction'
        app_label = 'admin_hub'


#BBPS Biller -------
class BBPSBillerCategory(models.Model):
    bbps_id = models.AutoField(primary_key=True)
    category_name = models.CharField(max_length=50, null=True, blank=True)
    sd_charges = models.JSONField(null=True, blank=True)
    md_charges = models.JSONField(null=True, blank=True)
    dt_charges = models.JSONField(null=True, blank=True)
    rt_charges = models.JSONField(null=True, blank=True)
    to_us_charges = models.JSONField(null=True, blank=True)
    sa_provided = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=True)
    is_deactive = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        db_table = 'bbps_biller_category'
        app_label = 'admin_hub'


class BBPSBiller(models.Model):
    bbps_biller_id = models.AutoField(primary_key=True)
    bbps_blr_id = models.CharField(max_length=50, null=True, blank=True)
    bbps_blr_name = models.CharField(max_length=255, null=True, blank=True)
    bbps_category = models.ForeignKey(BBPSBillerCategory, on_delete=models.PROTECT, null=True, blank=True)
    is_deleted = models.BooleanField(default=False, null=True, blank=True)
    is_deactive = models.BooleanField(default=False, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        db_table = 'bbps_biller'
        app_label = 'admin_hub'


class BBPSBillResponse(models.Model):
    bbps_id = models.AutoField(primary_key=True)
    bbps_biller_id = models.CharField(max_length=255, null=True, blank=True)
    bbps_biller_response = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bbps_biller_info'
        app_label = 'admin_hub'


class BBPSBillPayment(models.Model):
    bbps_id = models.AutoField(primary_key=True)
    bbps_blr_id = models.CharField(max_length=255, null=True, blank=True)
    bbps_sp = models.ForeignKey(AdServiceProvider, on_delete=models.PROTECT, null=True, blank=True)
    bbps_contact_no = models.CharField(max_length=10, null=True, blank=True)
    bbps_request_id = models.CharField(max_length=255, null=True, blank=True)
    bbps_bill_fetch_response = models.JSONField(null=True, blank=True)
    bbps_payment_response = models.JSONField(null=True, blank=True)
    bbps_amount = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    bbps_status = models.CharField(max_length=15, null=True, blank=True , default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.IntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        db_table = 'ad_bbps_bill_payment'
        app_label = 'admin_hub'

# new add 12-12-24
#
# class WalletTrn(models.Model):
#     wl_trn_id = models.AutoField(primary_key=True)
#     action_id = models.IntegerField(null=True, blank=True)
#     action_type = models.CharField(max_length=100)
#     pu = models.ForeignKey(PortalUser, on_delete=models.PROTECT)
#     wl_label = models.CharField(max_length=100)
#     effectvie_wallet = models.CharField(max_length=20, null=True, blank=True)
#     effectvie_amt = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
#     effective_type = models.CharField(max_length=10, choices=MrkTyChoice.choices)
#     wl_trn_des = models.CharField(max_length=500, null=True, blank=True)
#     wl_trn_dt = models.DateTimeField(null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#
#     def __str__(self):
#         return f"{self.wl_trn_id}"
#
#     class Meta:
#         db_table = 'ad_wallet_transaction'
#         app_label = 'admin_hub'
#
# '''
# Transaction Module (Service wise Transaction Model, Global Transaction Model, Wallet Transaction Model)
# '''
# class PyOtServiceTrn(models.Model):
#     service_trn_id = models.AutoField(primary_key=True)
#     sp = models.ForeignKey(AdServiceProvider, on_delete=models.PROTECT)
#     trn_unique_id = models.CharField(max_length=55)
#     trn_amount = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
#     trn_response = models.JSONField(null=True, blank=True)
#     customer_name = models.CharField(max_length=50, null=True, blank=True)
#     customer_aadhaar_no = models.CharField(max_length=12, null=True, blank=True)
#     customer_contact_no = models.CharField(max_length=10, null=True, blank=True)
#     trn_status = models.CharField(max_length=15, null=True, blank=True)
#     service_trn_dt = models.DateTimeField(auto_now_add=True, null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#
#
#     def __str__(self):
#         return f"{self.service_trn_id}"
#
#     class Meta:
#         db_table = 'ad_payot_service_transaction'
#         app_label = 'admin_hub'
#
# class GlTrn(models.Model):
#     gl_trn_id = models.AutoField(primary_key=True)
#     service_trn_id = models.IntegerField(null=True, blank=True)
#     pu = models.ForeignKey(PortalUser, on_delete=models.PROTECT)
#     gl_trn_amt = models.DecimalField(max_digits=19, decimal_places=3 ,null=True, blank=True)
#     gl_tds_rate = models.DecimalField(max_digits=19, decimal_places=3 ,null=True, blank=True)
#     gl_tax_rate = models.DecimalField(max_digits=19, decimal_places=3 ,null=True, blank=True)
#     gl_tds_amt = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
#     gl_tax_amt = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
#     effectvie_wallet = models.CharField(max_length=20, null=True, blank=True)
#     effectvie_amt = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
#     effective_type = models.CharField(max_length=10, choices=MrkTyChoice.choices)
#     gl_trn_dt = models.DateTimeField(null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#
#     def __str__(self):
#         return f"{self.gl_trn_id}"
#
#     class Meta:
#         db_table = 'ad_global_transaction'
#         app_label = 'admin_hub'




class PayoutRequest(models.Model):
    pr_id = models.AutoField(primary_key=True)
    bank = models.ForeignKey(BankDetailsUser, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=19, decimal_places=2, null=True)
    is_deactive = models.BooleanField(default=False)
    is_delete = models.BooleanField(default=False)
    request_status = models.CharField(choices=RequestStatus, default=RequestStatus.PENDING, max_length=100)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        PortalUser, on_delete=models.PROTECT, db_column='created_by', null=True)
    updated_at = models.DateTimeField(null=True)
    updated_by = models.IntegerField(null=True, db_column='updated_by')

    def __str__(self) -> str:
        return super().__str__()

    class Meta:
        db_table = 'ad_payout_request'
        app_label = 'admin_hub'









class Api_Req_Response(models.Model):
    api_id = models.AutoField(primary_key=True)
    api_type = models.CharField(max_length=100)
    api_request = models.JSONField()
    api_response = models.JSONField()
    txn_dt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.api_id}"

    class Meta:
        db_table = 'ad_api_request_response'
        app_label = 'admin_hub'


class Pg_Master_Charge(models.Model):
    charge_id = models.AutoField(primary_key=True)
    charge = models.DecimalField(max_digits=10, decimal_places=2)
    charge_type = models.CharField(max_length=500)
    charge_created_dt = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"{self.charge_id}"
    
    class Meta:
        db_table = 'ad_pg_master_charge'
        app_label = 'admin_hub'


class PaymentGateway(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return f"{self.id}"
    
    class Meta:
        db_table = 'ad_payment_gateway'
        app_label = 'admin_hub'


class CardType(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)



    def __str__(self):
        return f"{self.id}"
    
    class Meta:
        db_table = 'ad_card_type'
        app_label = 'admin_hub'


class PGBaseCharge(models.Model):
    PORTAL_USER_TYPE = [
        ('Admin', 'Admin'),
        ('Super Distributor', 'Super Distributor'),
        ('Master Distributor', 'Master Distributor'),
        ('Distributor', 'Distributor'),
        ('Retailer', 'Retailer'),
    ]
    role = models.CharField(max_length=20, choices=PORTAL_USER_TYPE)
    pg = models.ForeignKey(PaymentGateway, on_delete=models.CASCADE)
    card_type = models.ForeignKey(CardType, on_delete=models.CASCADE)
    charge_percent = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)


    def __str__(self):
        return f"{self.id}"
    
    class Meta:
        db_table = 'ad_pg_base_charge'
        app_label = 'admin_hub'
        unique_together = ('pg', 'role', 'card_type')


class UserCharge(models.Model):
    charge_id = models.AutoField(primary_key=True)
    pg = models.ForeignKey(PaymentGateway, on_delete=models.CASCADE)
    card_type = models.ForeignKey(CardType, on_delete=models.CASCADE)
    charge_percent = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    user = models.ForeignKey(PortalUser,on_delete=models.CASCADE,null=True,blank=True)


    def __str__(self):
        return f"{self.charge_id}"
    
    class Meta:
        db_table = 'ad_user_charge'
        app_label = 'admin_hub'

class PgServiceTrn(models.Model):
    pg_trn_id = models.AutoField(primary_key=True)
    trn_unique_id = models.CharField(max_length=255, unique=True)
    trn_amount = models.DecimalField(max_digits=10, decimal_places=2)
    trn_response = models.JSONField()
    is_settled = models.BooleanField(default=False)
    trn_status = models.CharField(max_length=20, choices=RequestStatus, default=RequestStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.IntegerField(null=True, blank=True)
    buyer_email = models.EmailField(null=True, blank=True)
    buyer_phone = models.BigIntegerField(null=True, blank=True)
    buyer_firstname = models.CharField(max_length=50,null=True, blank=True)
    buyer_lastname = models.CharField(max_length=50,null=True, blank=True)
    buyer_address = models.CharField(max_length=50,null=True, blank=True)
    buyer_city = models.CharField(max_length=50,null=True, blank=True)
    buyer_state = models.CharField(max_length=50,null=True, blank=True)
    buyer_country = models.CharField(max_length=50,null=True, blank=True)
    buyer_pincode = models.IntegerField(null=True, blank=True)
    retailer_charge_percent = models.DecimalField(max_digits=5, decimal_places=3)  
    total_charge_amount = models.DecimalField(max_digits=19, decimal_places=3)  
    net_credit_to_user = models.DecimalField(max_digits=19, decimal_places=3) 
    pg = models.ForeignKey(PaymentGateway, on_delete=models.CASCADE)  
    card_type = models.ForeignKey(CardType, on_delete=models.CASCADE)
    credit_card_num = models.CharField(max_length=16, null=True, blank=True)
    sp_mdr_amount = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    sp_gst_amount = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    sp_receivable_amount = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    is_instant = models.BooleanField(default=False)
    is_received = models.BooleanField(default=False)
    payment_gateway_reference = models.CharField(max_length=255, null=True, blank=True)




    def __str__(self):
        return f"{self.pg_trn_id}"

    class Meta:
        db_table = 'ad_pg_service_transaction'
        app_label = 'admin_hub'

class CommissionLog(models.Model):
    commission_id = models.AutoField(primary_key=True)
    pg_service_trn = models.ForeignKey(PgServiceTrn, on_delete=models.CASCADE, null=True, blank=True)
    pos_service_trn = models.ForeignKey(PosServiceTrn, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(PortalUser, on_delete=models.CASCADE)
    commission_amount = models.DecimalField(max_digits=19, decimal_places=3, null=True, blank=True)
    level = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.commission_id}"

    class Meta:
        db_table = 'ad_commission_logs'
        app_label = 'admin_hub'


class PaymentGetwayAuthenticationDetails(models.Model):
    pg_auth_id = models.AutoField(primary_key=True)
    client_key = models.CharField(max_length=1000, null=True, blank=True)
    client_secret_key = models.CharField(max_length=1000, null=True, blank=True)
    mid = models.CharField(max_length=500, null=True, blank=True)
    username = models.CharField(max_length=500, null=True, blank=True)
    password = models.CharField(max_length=500, null=True, blank=True)
    json_data = models.JSONField(null=True, blank=True)
    is_deactive = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    unique_name = models.CharField(
        max_length=500, 
        null=True, 
        blank=True,
        unique=True,
        db_index=True
    )
    sp_id = models.IntegerField(null=True,blank=True)

    min_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=50.00,
        help_text='Minimum transaction amount'
    )
    max_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=39990.00,
        help_text='Maximum transaction amount'
    )



    def __str__(self):
        return f"{self.pg_auth_id}"

    class Meta:
        db_table = 'ad_pg_auth_details'
        app_label = 'admin_hub'



class SenderDmt(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('blocked', 'Blocked'),
    ]

    id = models.AutoField(primary_key=True)
    mobile_number = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=7, choices=STATUS_CHOICES, default='active')

    def __str__(self):
        return f"{self.id}"
    
    class Meta:
        db_table = 'ad_dmt_senders'
        app_label = 'admin_hub'
    

class BeneficiaryDmt(models.Model):
    STATUS_CHOICES = (
        ('Verified', 'Verified'),
        ('Unverified', 'Unverified'),
        ('Deleted', 'Deleted'),
    )

    id = models.AutoField(primary_key=True)
    sender = models.ForeignKey(SenderDmt,on_delete=models.CASCADE)
    mobile_number = models.CharField(max_length=10)
    account_number = models.CharField(max_length=30)
    bank_name = models.CharField(max_length=100)
    ifsc_code = models.CharField(max_length=20)
    verified_name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.id}"
    
    class Meta:
        db_table = 'ad_dmt_beneficiaries'
        app_label = 'admin_hub'


from django.db import models
from django.utils.timezone import now


class CommissionSettlementStatus(models.TextChoices):
    UNSETTLED = 'UNSETTLED', 'Unsettled'
    MANUAL_SETTLED = 'MANUAL_SETTLED', 'Manual Settled'
    AUTO_SETTLED = 'AUTO_SETTLED', 'Auto Settled'


class CommissionSettlementMode(models.TextChoices):
    MANUAL = 'MANUAL', 'Manual'
    AUTO = 'AUTO', 'Auto'





class CommissionTransaction(models.Model):
    id = models.AutoField(primary_key=True)
    transaction_id = models.CharField(max_length=255, db_index=True, help_text="Related transaction unique ID")
    distributor = models.ForeignKey(
        'PortalUser', 
        on_delete=models.PROTECT, 
        related_name='commissions_earned',
        db_index=True
    )
    retailer = models.ForeignKey(
        'PortalUser', 
        on_delete=models.PROTECT, 
        related_name='commissions_generated',
        db_index=True
    )
    service_provider = models.ForeignKey(
        'AdServiceProvider',
        on_delete=models.PROTECT,
        related_name='commissions',
        db_index=True,
        help_text="Service Provider (Veg PG-1, Razorpay, etc.)"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    settlement_status = models.CharField(
        max_length=20, 
        choices=CommissionSettlementStatus.choices,
        default=CommissionSettlementStatus.UNSETTLED,
        db_index=True
    )
    settlement_mode = models.CharField(
        max_length=10, 
        choices=CommissionSettlementMode.choices,
        null=True, 
        blank=True
    )
    settlement_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ad_commission_transactions'
        app_label = 'admin_hub'
        indexes = [
            models.Index(fields=['distributor', 'settlement_status', 'created_at']),
            models.Index(fields=['retailer', 'settlement_status', 'created_at']),
            models.Index(fields=['service_provider', 'settlement_status']),
        ]

    def __str__(self):
        return f"Commission {self.id} - {self.distributor.username} - {self.amount}"


class CommissionSettlementLog(models.Model):
    id = models.AutoField(primary_key=True)
    
    distributor = models.ForeignKey(
        'PortalUser', 
        on_delete=models.PROTECT,
        related_name='settlement_logs'
    )
    
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    mode = models.CharField(
        max_length=10, 
        choices=CommissionSettlementMode.choices
    )
    
    reference_commissions = models.JSONField(help_text="List of commission IDs included in this settlement")
    
    performed_by = models.ForeignKey(
    'PortalUser',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='settlements_performed',
    help_text="Admin user who performed manual settlement, NULL for auto settlement"
)


    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ad_commission_settlement_log'
        app_label = 'admin_hub'

    def __str__(self):
        return f"Settlement {self.id} - {self.distributor.username} - {self.total_amount} - {self.mode}"
    


class CommissionAutoSettlementConfig(models.Model):
    id = models.AutoField(primary_key=True)
    distributor = models.OneToOneField(
        'PortalUser',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='settlement_config',
        help_text="NULL means global default config"
    )
    auto_settlement_delay_days = models.IntegerField(
        default=1,
        help_text="Number of days after commission creation to auto-settle"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Enable/disable auto-settlement for this distributor"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'PortalUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='settlement_configs_created'
    )

    class Meta:
        db_table = 'ad_commission_auto_settlement_config'
        app_label = 'admin_hub'
        indexes = [
            models.Index(fields=['distributor', 'is_active']),
        ]

    def __str__(self):
        if self.distributor:
            return f"Config for {self.distributor.username} - {self.auto_settlement_delay_days} days"
        return f"Global Config - {self.auto_settlement_delay_days} days"
    

class CronJobConfiguration(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Cron job name (e.g., 'auto_settlement')"
    )
    cron_url = models.URLField(
        max_length=500,
        help_text="Full URL that cron job will call"
    )
    description = models.TextField(
        null=True,
        blank=True,
        help_text="Description of what this cron job does"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Enable/disable this cron job"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        db_table = 'ad_cron_job_configuration'
        app_label = 'admin_hub'
        indexes = [
            models.Index(fields=['name', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} - {self.cron_url}"
    

class VegaahPgLogs(models.Model):
    logs_id = models.AutoField(primary_key=True)
    order_id = models.CharField(max_length=255)
    request = models.JSONField()
    response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"{self.logs_id}"

    class Meta:
        db_table = 'ad_vegaah_logs'
        app_label = 'admin_hub'

class ServiceAccountRequest(models.Model):
    sar_id = models.AutoField(primary_key=True)
    pu = models.ForeignKey(PortalUser, on_delete=models.PROTECT, db_column='pu_id')
    from_wallet = models.CharField(max_length=50, default='pg_wallet')
    to_wallet = models.CharField(max_length=50, default='main_wallet')
    amount = models.DecimalField(max_digits=19, decimal_places=3)
    description = models.TextField(null=True, blank=True)
    request_status = models.CharField(
        choices=PgTrnChoice.choices, 
        default=PgTrnChoice.COMPLETED, 
        max_length=100
    )
    reasons = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.IntegerField(null=True, blank=True, db_column='updated_by')

    def __str__(self):
        return f"{self.sar_id} - {self.pu.pu_name} - {self.amount}"

    class Meta:
        db_table = 'ad_service_account_request'
        app_label = 'admin_hub'



class UserServiceFinance(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey("PortalUser", on_delete=models.CASCADE)
    instant_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    od_limit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    available_limit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    usage_limit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "user_service_finance"
        app_label = "admin_hub"

    def save(self, *args, **kwargs):
        if self.created_at and timezone.is_naive(self.created_at):
            self.created_at = timezone.make_aware(self.created_at)
        super().save(*args, **kwargs)




class RazorpayPgLogs(models.Model):
    logs_id = models.AutoField(primary_key=True)
    order_id = models.CharField(max_length=255, db_index=True)  
    payment_link_id = models.CharField(max_length=255, null=True, blank=True)  
    payment_id = models.CharField(max_length=255, null=True, blank=True)  
    event_type = models.CharField(max_length=100, null=True, blank=True)  
    request = models.JSONField(null=True, blank=True)  
    response = models.JSONField(null=True, blank=True)  
    status = models.CharField(max_length=50, default='PENDING')  
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Log {self.logs_id} - {self.order_id} - {self.status}"

    class Meta:
        db_table = 'ad_razorpay_logs'
        app_label = 'admin_hub'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_id']),
            models.Index(fields=['payment_link_id']),
            models.Index(fields=['status']),
        ]