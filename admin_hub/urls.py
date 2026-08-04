# Django Imports
from django.urls import path

# Project-Specific Imports
from .views import *
from .bbps_service import *
from .zoho_mail import *
from .daily_reminder import *



urlpatterns = [
    path('pos_test',post_test),
    path('check-ip/', verify_static_ip),
    
    path('current-location/',GeolocationGetApiView.as_view()),
    # POS Hooks Endpoints
    path('pos-transactions/', HooksView.as_view()),

    # Admin Create Endpoint
    path('admin/', admin),

    # START PROJECT URL =======>

    # LOGIN
    path('auth/user-login/', UserLoginAPIView.as_view()),

    # HSN/SAC Module Endpoint
    path('master/hsn-sac/', HsnSacAPIView.as_view()),

    # Service Module
    path('master/service/', ServiceAPIView.as_view()),

    # Service Provider Module
    path('master/service-provider/', ServiceProviderAPIView.as_view()),

    # DEVICE
    path('device/', DeviceAPIView.as_view()),

    # CRAETE PARTNERS CATEGORY
    path('partners/partner-category/', PartnerCategoryAPIView.as_view()),

    # CREATE PARTNERS
    path('users/user/', UserAPIView.as_view()),

    # Users/Service and Charges
    path('users/service-charges/', UserServicesChargesAPIView.as_view()),

    # Credential Forgot
    path('credential-forgot/', CredentialForgotAPIView.as_view()),

    # PARTNERS CREDENTIAL Forgot And Update Username Password
    path('change-password/', ChangePasswordAPIView.as_view()),

    path('change-mpin/', SetMpinAPIView.as_view()),


    # kyc verfied api
    # path('kyc/kyc-verified/', KYCVerifiedAPIView.as_view()),

    # User Profile Fatch
    path('profile/user-profile/', UserProfileAPIView.as_view()),

    # bank details
    path('banks/bank-details/', BankDetailsAPIView.as_view()),
    path('banks/verify-bank-details/', VerifyBankDetailsAPIView.as_view()),

    # Create and fetch Fund Request API
    path('users/fund-request/', FundRequestAPIView.as_view()),

    # Create and fetch Payout Request API
    path('users/payout-request/', PayoutRequestAPIView.as_view()),

    # Create and fetch Payout Request API for retailer
    path('retailer/payout/', RetailerPayoutAPiView.as_view()),

    

    #wallet to wallet
    path('wallet/wallet-transaction/', WalletAPIView.as_view()),

    # extra api add
    path('fetch/', FetchAPIView.as_view()),

    # USER status Changes
    path('users/status-change/', UserStatusChangeAPIView.as_view()),

    # service provider pined
    path('retailers/dynamic-service-provider/', RetailerDynamicServiceProviderAPIView.as_view()),

    # Pos device assigned Ret
    path('assigned/pos-device/', AssignedPosDeviceAPIView.as_view()),

    path('reteailer/pos-service/', PosServiceTrnAPIView.as_view()),

    path('global-trn/', GlobalTrnAPIView.as_view()),

    path('retailer/pos-terminal/', RetailerPosAPIView.as_view()),

    path('retailer/terminal-id/', RetailerTerminalAPIView.as_view()),

    path('admin/transaction-settlement/', TransactionSettlementAPIView.as_view()),

    #transaction is completed, after add retailer api #---> ADD
    path('admin/assign-pos-device/',AssignPosDeviceToRetailerAPIView.as_view()),

    path('retailer/transaction/', RetailerTransactionAPIView.as_view()),

    path('retailer/transaction-settlement/', RetailerTransactionSettlementAPIView.as_view()),

    # retailer dashboard API
    path('retailer/dashboard/', RetailerDashboardAPIView.as_view()),

    #BBPS SECTION ------------------------>
    path('bbps/biller/', BbpsBillerAPIView.as_view()),

    #Biller entry API
    path('bbps/biller/biller-info/entry/', BbpsBillerInfoEntryAPIView.as_view()),

    #BBPS Service Charge Update API
    path('user/service/sub-service/', UpdateServiceCategoryCharges.as_view()),

    #PG Service Data
    path('user/pg/service/sub-service/', PGServiceCategoryCharges.as_view()),
    path('user/pg/service/tid-service/', PGServiceCategoryChargesTid.as_view()),


    #BBPS FILE UPLOAD API
    path('biller_cetegory_file/',biller_cat_file),
    path('biller_file/',biller_file),


    path("pay/", initiate_payment, name="initiate_payment"),
    path("payment-success/", payment_success, name="payment_success"),
    path("payment-failed/", payment_failed, name="payment_failed"),

    path("admin_all_wallet_transaction/<int:user_id>/", AdminUserWalletTransactionsView.as_view()),
    path("admin-user-profile/<int:user_id>/", AdminUserProfileAPIView.as_view()),
    # path("admin-user-fund-request/<int:user_id>/", AdminFundRequestAPIView.as_view()),

    #change-mpin and password form profile
    path("profile-change-mpin/", ChangeMPINView.as_view(), name="profile-change-mpin"),
    path("profile-change-password/", ChangePasswordView.as_view(), name="profile-change-password"),
    #retailer-bank
    path("retailer-bank/", NewBankDetailsAPIView.as_view(), name="retailer-bank"),
    #validate-pin
    path("validate-mpin/", ValidateMpinApiView.as_view(), name="validate_mpin"),
    # export-payout-csv
    path('export_payout_csv/', export_payout_csv, name='export_payout_csv'),
    # payin-payout-all
    path('payin-payout/', UpdatedWalletInRetailer.as_view(), name='payin-payout'),
    #payout-action
    path('payout-action/', PayoutActionView.as_view(), name='payout_action'),
    # admin-homepage-data
    path('admin-all-homepage-data/', AdminHomePageRetailerDataApiView.as_view(), name='admin-all-homepage-data'),
    path('admin-all-homepage-data-with-graph/', AdminHomePageRetailerDataWithGraphApiView.as_view(), name='admin-all-homepage-data'),

    #retailer-wallet-transfer
    path('wallet/retailer-transfer/', RetailerTransferView.as_view(), name='retailer-transfer'),
    path('retailer/reset-mpin/', RetailerResetMpinApiView.as_view(), name='retailer-mpin-reset'),
    path('retailer-all-homepage-data-with-graph/', RetailerHomePageDataWithGraphApiView.as_view(), name='retailer-all-homepage-data'),


    # get bbps live balance ------------------------
    path('get-bbps-balance/',BbpsDepositBalanceApiView.as_view()),

    path('bbps-transaction-status/',TransactionStatusAPIView.as_view()),


    # retaielr register func------------------
    path('register/', StartingUserAPIView.as_view()),
    path('register/verify-business-details/',RetailerDetailsVerifyApiView.as_view(),name="retailer-business-details"),


    # manually calling from postman ---------------------
    path('airpay-payment-initiate/',manual_pg_transaction),

    # from admin transaction settled----------------
    path('settle-pg-transaction/',settle_pg_transaction),

    path('retailer/pg-terminal/', RetailerAirpayPgAPIView.as_view()),

    path('retailer/instant-pg-terminal/', RetailerInstantAirpayPgAPIView.as_view()),

    path('retailer/vegaah-pg-terminal/', RetailerVegaahPGAPIView.as_view()),

    path('retailer/vegaah-pg-terminal-new/', RetailerVegaahPG2APIView.as_view()),




    path('retailer/pg-transaction/', RetailerPGTransactionAPIView.as_view()),

    path('retailer/vegaah-pg-transaction/', RetailerVegaahPGTransactionAPIView.as_view()),

    path('retailer/vegaah-pg-transaction-new/', RetailerVegaahPG2TransactionAPIView.as_view()),


    
    # path('retailer/vegaah-pg-transaction/', RetailerVegaahPGTransactionAPIView.as_view()),



    path('airpay/',AirpayPG.as_view()),

    path('assign_charges/',assign_charges),



    # admin-user-level-charge
    path('users/commission/user-level-charge/', UserLevelChargeApiView.as_view()),


    #get all payment getways----------
    path("payment-gateways/", get_payment_gateways),

    #get all card------------
    path("card-types/", get_card_types),

    #base-charge-----------------
    path("pg-charge-config/", PGChargeConfigView.as_view()),


    #open base charge-for-frontend-------
    path('users/commission/base-charge/', BaseChargeApiView.as_view()),

    path('add-user-level-charge/',AddUserLevelChargeApiView.as_view()),
    path('edit-user-level-charge/',EditUserLevelChargeApiView.as_view()),
    path('delete-user-level-charge/',DeleteUserLevelChargeApiView.as_view()),

    path('check_service_provider_active/',check_service_provider_active),


    path('user-level-charge/',BuildUserHierarchyView.as_view()),

    path('send-email/', SendEmailView, name='send_email'),

    # dmt-sender-create
    path('dmt-create/',DmtSenderVerification.as_view()),

    path('dmt-get-recipient/',GetAllRecipientsView.as_view()),

    # checking parent in the register
    path('register/check-parent/',check_in_register_parent,name="check-parent"),

    #retailer document upload-------------
    path('upload-documents/',RetailerDocumentsUploadAPIView.as_view()),

    # retailer document status change ----
    path('update-doc-status/',UpdateUploadStatusAPIView.as_view()),


    path('admin-user-document/',AdminDocumentApiView.as_view(), name='admin-user-document'),

    #re-active retailer account by admin --------------
    path('retailer/account-activate/',MaintainRetailerStatusApiView.as_view()),

    #admin-master -> terminal section
    path('users/terminals/',TerminalsApiView.as_view()),

    # admin master -> bulk message 
    path('send-bulk-message/', BulkMessageView.as_view(), name='send_bulk_message'),

    # retailer-pay -> get credit card details ---
    path('fecth-card/',fetch_card_details,name='fetch_card_details'),

    path('check_ifsc/',check_ifsc,name="check_ifsc"),

    path('security-check/',ChequeNumberApiView.as_view()),

    #get the profile in the Distributor
    path("distributor-user-profile/<int:user_id>/", DistributorUserProfileAPIView.as_view()),

    # distributor-wallet-transfer
    path('wallet/retailer-distributor-transfer/', DistributorRetailerTransferView.as_view(), name='retailer-distributor-transfer'),

    # distributor - wallet-to-wallet-transfer
    path('wallet/distributor-ledger-transfer/',DistributorLedgerApiView.as_view(),name="distributor_ledger_transfer"),

    path('wallet/distributor-transfer/', DistributorTransferView.as_view(), name='distributor-transfer'),
    path('process-inprogress-bbps/', ProcessInprogressBBPSView.as_view(), name='process-inprogress-bbps'),



    path('vegaah-payment/', VegaahPG.as_view()),
    path('vegaah-webhook/', vegaah_webhook, name='vegaah_webhook'),
    path('vegaah-prod-webhook/', vegaah_prod_webhook, name='vegaah_prod_webhook'),

    path('vegaah-callback/', vegaah_callback, name='vegaah_callback'),
    path('retailer/vegaah-transactions/', RetailerVegaahPGAPIView.as_view()),
    path('get-pg-tid/', GetAuthProfiles.as_view(), name='get-pg-tid'),

    path('get-pg-tid-new/', GetAuthProfilesVeg2.as_view(), name='get-pg-tid'),


    path('admin/bbps-refund/', BBPSRefundAPIView.as_view(), name='bbps-refund'),

    path('check-transaction-status/', CheckTransactionStatus.as_view(), name='check-transaction-status'),


    path('vegaah-payment-new/', VegaahPG2.as_view()),
    path('vegaah-webhook-test-2', vegaah_webhook_2, name='vegaah_webhook_2'),

    path('commission/list/', CommissionListView.as_view(), name='commission-list'),

    path('commission/settle/', ManualCommissionSettlementView.as_view(), name='commission-settle'),

    path('api/cron/auto-settlement/', AutoCommissionSettlementCronView.as_view()),

    path('settlement-delays-config/', CommissionAutoSettlementConfigView.as_view()),

    path('api/admin/distributors/list/', DistributorListView.as_view(), name='distributor-list'),


    path('retailer/commissions/', RetailerCommissionListView.as_view(), name='retailer-commission-list'),

    path('api/service-providers/', ServiceProviderListView.as_view(), name='service-provider-list'),


    path('pg-transaction-details/<int:wl_trn_id>/', PgTransactionDetailsView.as_view(), name='pg_transaction_details'),


    path('cron/', CronListView.as_view(), name='crol_url'),

    path('distributor/commission-stats/', DistributorCommissionStatsView.as_view(), name='distributor-commission-stats'),



    path('distributor/commission-list/', 
         DistributorCommissionListView.as_view(), 
         name='distributor-commission-list'),
    
    path('distributor/commission-stats-page/', 
         DistributorCommissionPageStatsView.as_view(), 
         name='distributor-commission-stats'),
    
    path('distributor/commission-transactions/', 
         DistributorCommissionTransactionsView.as_view(), 
         name='distributor-commission-transactions'),


     path('api/send-daily-reminders/', DailyLoginReminderView.as_view(), name='send-daily-reminders'),



      path('wallet/service-account-request/', 
         ServiceAccountRequestAPIView.as_view(), 
         name='service-account-request'),

     path('admin/service-account-request/', 
         AdminServiceAccountRequestAPIView.as_view(), 
         name='admin-service-account-request'),

     path('retailer/instant-vegaah-pg-first-terminal/', RetailerInstantVegaahPGFirstAPIView.as_view()),


     path('retailer/instant-vegaah-pg-first-transaction/', RetailerVegaahPGFirstTransactionAPIView.as_view()),


     path('admin/pg-settlement-received/', AdminMarkRecievedAPIView.as_view(), name='pg_settlement_received'),


     path('retailer/user-service-finance/', UserServiceFinanceView.as_view(), name='user-service-finance'),

     path('retailer/instant-vegaah-pg-second-terminal/', RetailerInstantVegaahPGSecondAPIView.as_view()),

    path('retailer/instant-pg-transaction/', RetailerInstantAirpayTransactionAPIView.as_view()),

    path('retailer/instant-vegaah-pg-second-transaction/', RetailerVegaahPGSecondTransactionAPIView.as_view()),


    path('retailer/razorpay-pg-terminal/', RetailerRazorpayPGAPIView.as_view()),

    path('retailer/razorpay-pg-transaction/', RetailerRazorpayPGTransactionAPIView.as_view()),

    path('retailer/instant-razorpay-pg-transaction/', RetailerRazorpayPGInstantTransactionAPIView.as_view()),

    path('retailer/instant-razorpay-pg-terminal/', RetailerInstantRazorpayPGFirstAPIView.as_view()),

    path('get-razorpay-auth/', GetAuthRazorPay.as_view()),

    path('razorpay-payment/', RazorpayPG.as_view(), name='razorpay-payment'),
    path('razorpay-webhook/', razorpay_webhook, name='razorpay-webhook'),








    





]
