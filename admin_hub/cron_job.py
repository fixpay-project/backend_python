

# from .views import *
# import os
# import datetime as dt_module
# from decimal import Decimal
# from django.db import transaction
# from admin_hub.bbps_service import TransactionStatusAPIView

# # -------------------------
# # Logger setup
# # -------------------------
# def create_logger(file_path):
#     os.makedirs(os.path.dirname(file_path), exist_ok=True)
#     def log(message):
#         with open(file_path, "a") as f:
#             f.write(f"{dt_module.datetime.now()} - {message}\n")
#         print(f"{dt_module.datetime.now()} - {message}")
#     return log

# main_log_file = "/var/www/QAAPI/fixpay_backEnd/ssepl_backend/bbps_main_log.txt"
# status_log_file = "/var/www/QAAPI/fixpay_backEnd/ssepl_backend/bbps_status_log.txt"
# success_log_file = "/var/www/QAAPI/fixpay_backEnd/ssepl_backend/bbps_success_log.txt"
# failure_log_file = "/var/www/QAAPI/fixpay_backEnd/ssepl_backend/bbps_failure_log.txt"

# log_main = create_logger(main_log_file)
# log_status = create_logger(status_log_file)
# log_success = create_logger(success_log_file)
# log_failure = create_logger(failure_log_file)

# # -------------------------
# # BBPS API Status Check
# # -------------------------
# def check_bbps_transaction_status(request_id: str, retries=3) -> str:
#     for attempt in range(retries):
#         try:
#             log_status(f"[INFO] Checking BBPS transaction status for request_id: {request_id}, attempt {attempt+1}")
#             response = TransactionStatusAPIView().post(
#                 type("obj", (object,), {"data": {"requestId": request_id}})()
#             )
#             txn_resp = response.data.get("data", {}).get("transactionStatusResp", {})
#             response_reason = txn_resp.get("responseReason", "").upper()
#             txn_status = txn_resp.get("txnList", {}).get("txnStatus", "").upper()

#             if response_reason == "SUCCESS" and txn_status == "SUCCESS":
#                 log_status(f"[INFO] Transaction {request_id} confirmed SUCCESS")
#                 return "SUCCESS"
#             log_status(f"[INFO] Transaction {request_id} FAILED (Reason: {response_reason}, TxnStatus: {txn_status})")
#             return "FAILED"
#         except Exception as e:
#             log_status(f"[WARN] BBPS API error for {request_id} attempt {attempt+1}: {str(e)}")
#     log_status(f"[INFO] Transaction {request_id} defaulting to FAILED after {retries} attempts")
#     return "FAILED"

# # -------------------------
# # Handle SUCCESS
# # -------------------------
# # -------------------------
# def handle_success_bbps(biller, sp_id, blr_id, contact_no, formatted_amount):
#     log_success(f"[INFO] Handling SUCCESS for BBPS transaction: {biller.bbps_request_id}")

#     category = BBPSBiller.objects.filter(bbps_blr_id=blr_id).first()
#     service_provider = AdServiceProvider.objects.get(sp_id=sp_id)

#     gst_rate = Decimal(str(service_provider.hsn_sac.tax_rate))
#     admin_rate = Decimal(str(category.bbps_category.to_us_charges.get("rate_value")))
#     admin_rate_type = category.bbps_category.to_us_charges.get("rate_type")
#     admin_charges_type = category.bbps_category.to_us_charges.get("charge_type")

#     # Calculate admin charges and tax
#     char_comm_amt = (
#         formatted_amount * (admin_rate / Decimal("100"))
#         if admin_rate_type == "is_percent"
#         else admin_rate
#     )
#     admin_tax_amt = char_comm_amt - (char_comm_amt / (Decimal("1") + (gst_rate / Decimal("100"))))

#     portal_user_details = PortalUserDetails.objects.get(pu_id=biller.created_by)

#     # Use select_for_update to avoid race conditions
#     rtl_wallet = PortalUserWallet.objects.select_for_update().get(pu_id=biller.created_by)
#     admin_wallet = PortalUserWallet.objects.select_for_update().get(pu_id=1)

#     # -------- RETAILER WALLET --------
#     if not GlTrn.objects.filter(service_trn_id=biller.pk, pu_id=rtl_wallet.pu_id).exists():
#         rtl_gl = GlTrn.objects.create(
#             service_trn_id=biller.pk,
#             pu_id=rtl_wallet.pu_id,
#             gl_trn_amt=formatted_amount,
#             effectvie_wallet="main_wallet",
#             effectvie_amt=formatted_amount,
#             service_trn_table="ad_bbps_service_transaction",
#             effective_type="DR",
#             gl_trn_dt=dt_module.datetime.now(),
#         )
#         WalletTrn.objects.create(
#             action_id=rtl_gl.pk,
#             action_type="Service",
#             pu_id=rtl_wallet.pu_id,
#             wl_label=f"BBPS debit of {formatted_amount} with tx_id {biller.bbps_request_id}",
#             effectvie_wallet="main_wallet",
#             effectvie_amt=formatted_amount,
#             effective_type="DR",
#             current_balance=rtl_wallet.main_wallet - formatted_amount,
#             wl_trn_dt=dt_module.datetime.now(),
#         )
#         rtl_wallet.main_wallet -= formatted_amount
#         rtl_wallet.updated_at = dt_module.datetime.now()
#         rtl_wallet.save(update_fields=["main_wallet", "updated_at"])

#     # -------- ADMIN WALLET --------
#     # Deduct service amount if not already done
#     if not GlTrn.objects.filter(service_trn_id=biller.pk, pu_id=1, action_type="Service").exists():
#         admin_gl = GlTrn.objects.create(
#             service_trn_id=biller.pk,
#             pu_id=1,
#             gl_trn_amt=formatted_amount,
#             effectvie_wallet="main_wallet",
#             effectvie_amt=formatted_amount,
#             service_trn_table="ad_bbps_service_transaction",
#             effective_type="DR",
#             gl_trn_dt=dt_module.datetime.now(),
#         )
#         WalletTrn.objects.create(
#             action_id=admin_gl.pk,
#             action_type="Service",
#             pu_id=1,
#             wl_label=f"BBPS_by_{portal_user_details.pud_unique_id}_of_amount_{formatted_amount}_with_tx_id_{biller.bbps_request_id}",
#             effectvie_wallet="main_wallet",
#             effectvie_amt=formatted_amount,
#             effective_type="DR",
#             current_balance=admin_wallet.main_wallet - formatted_amount,
#             wl_trn_dt=dt_module.datetime.now(),
#         )
#         admin_wallet.main_wallet -= formatted_amount
#         admin_wallet.updated_at = dt_module.datetime.now()
#         admin_wallet.save(update_fields=["main_wallet", "updated_at"])

#     # -------- ADMIN COMMISSION (ALWAYS RUN) --------
#     # Check if commission already applied
#     if not GlTrn.objects.filter(service_trn_id=biller.pk, pu_id=1, effective_type=admin_charges_type, gl_trn_amt=char_comm_amt).exists():
#         admin_gl_comm = GlTrn.objects.create(
#             service_trn_id=biller.pk,
#             pu_id=1,
#             gl_tax_rate=float(gst_rate),
#             gl_tax_amt=admin_tax_amt,
#             gl_trn_amt=formatted_amount,
#             effectvie_wallet="main_wallet",
#             effectvie_amt=char_comm_amt,
#             service_trn_table="ad_bbps_service_transaction",
#             effective_type=admin_charges_type,
#             gl_trn_dt=dt_module.datetime.now(),
#         )
#         # Update admin wallet
#         if admin_charges_type == "CR":
#             admin_wallet.main_wallet += char_comm_amt
#         else:
#             admin_wallet.main_wallet -= char_comm_amt
#         admin_wallet.updated_at = dt_module.datetime.now()
#         admin_wallet.save(update_fields=["main_wallet", "updated_at"])

#         WalletTrn.objects.create(
#             action_id=biller.pk,
#             action_type="Service",
#             pu_id=1,
#             wl_label=f"BBPS_commission_by_{portal_user_details.pud_unique_id}_of_amount_{char_comm_amt}_with_tx_id_{biller.bbps_request_id}",
#             effectvie_wallet="main_wallet",
#             effectvie_amt=char_comm_amt,
#             effective_type=admin_charges_type,
#             current_balance=admin_wallet.main_wallet,
#             wl_trn_dt=dt_module.datetime.now(),
#         )

#     # -------- Hook for additional calculations --------
#     data = {
#         "order_amount": float(formatted_amount),
#         "id": biller.created_by,
#         "sp_id": sp_id,
#         "customer_contact_no": contact_no,
#         "customer_name": None,
#         "service_trn": biller.pk,
#         "category": category.bbps_category.bbps_id,
#         "table_name": "ad_bbps_service_transaction",
#     }
#     after_tx_cal(biller, data)
# # -------------------------


# # -------------------------
# # Handle REFUND / FAILED
# # -------------------------
# def refund_bbps_transaction(biller, refund_amount: Decimal):
#     rtl_wallet = PortalUserWallet.objects.select_for_update().get(pu_id=biller.created_by)
#     admin_wallet = PortalUserWallet.objects.select_for_update().get(pu_id=1)

#     # ---------------- RETAILER REFUND ----------------
#     if not WalletTrn.objects.filter(action_type="Refund", action_id=biller.pk, pu_id=rtl_wallet.pu_id).exists():
#         rtl_wallet.main_wallet += refund_amount
#         rtl_wallet.updated_at = dt_module.datetime.now()
#         rtl_wallet.save(update_fields=["main_wallet", "updated_at"])

#         GlTrn.objects.create(
#             service_trn_id=biller.pk,
#             pu_id=biller.created_by,
#             gl_trn_amt=refund_amount,
#             effectvie_wallet="main_wallet",
#             effectvie_amt=refund_amount,
#             service_trn_table="ad_bbps_service_transaction",
#             effective_type="CR",   # retailer ko paisa wapas
#             gl_trn_dt=dt_module.datetime.now(),
#         )

#         WalletTrn.objects.create(
#             action_id=biller.pk,
#             action_type="Refund",
#             pu_id=rtl_wallet.pu_id,
#             wl_label=f"Refund for BBPS transaction {biller.bbps_request_id}",
#             effectvie_wallet="main_wallet",
#             effectvie_amt=refund_amount,
#             effective_type="CR",
#             current_balance=rtl_wallet.main_wallet,
#             wl_trn_dt=dt_module.datetime.now(),
#         )

#     # ---------------- ADMIN REVERSE ----------------
#     # Saare admin ke GL entries (service + commission) reverse karo
#     admin_entries = GlTrn.objects.filter(service_trn_id=biller.pk, pu_id=1)

#     for entry in admin_entries:
#         # Skip if already reversed
#         if WalletTrn.objects.filter(
#             action_type="Refund_Admin", action_id=biller.pk, pu_id=1,
#             wl_label__contains=str(entry.pk)
#         ).exists():
#             continue

#         reverse_type = "CR" if entry.effective_type == "DR" else "DR"

#         # Wallet balance update
#         if reverse_type == "CR":
#             admin_wallet.main_wallet += entry.effectvie_amt
#         else:
#             admin_wallet.main_wallet -= entry.effectvie_amt

#         admin_wallet.updated_at = dt_module.datetime.now()
#         admin_wallet.save(update_fields=["main_wallet", "updated_at"])

#         # GL Entry
#         GlTrn.objects.create(
#             service_trn_id=biller.pk,
#             pu_id=1,
#             gl_trn_amt=entry.effectvie_amt,
#             effectvie_wallet="main_wallet",
#             effectvie_amt=entry.effectvie_amt,
#             service_trn_table="ad_bbps_service_transaction",
#             effective_type=reverse_type,
#             gl_trn_dt=dt_module.datetime.now(),
#         )

#         # WalletTrn Entry
#         WalletTrn.objects.create(
#             action_id=biller.pk,
#             action_type="Refund_Admin",
#             pu_id=1,
#             wl_label=f"Refund reverse for BBPS tx {biller.bbps_request_id} (GL {entry.pk})",
#             effectvie_wallet="main_wallet",
#             effectvie_amt=entry.effectvie_amt,
#             effective_type=reverse_type,
#             current_balance=admin_wallet.main_wallet,
#             wl_trn_dt=dt_module.datetime.now(),
#         )

#     # ---------------- UPDATE BILLER STATUS ----------------
#     biller.bbps_status = "FAILED"
#     biller.updated_at = dt_module.datetime.now()
#     biller.save(update_fields=["bbps_status", "updated_at"])


# # -------------------------
# # Cron Job Entry
# # -------------------------
# def process_inprogress_bbps():
#     inprogress_bills = BBPSBillPayment.objects.filter(bbps_status="INPROGRESS")

#     for biller in inprogress_bills:
#         request_id = biller.bbps_request_id
#         sp_id = biller.bbps_sp.sp_id if biller.bbps_sp else None
#         blr_id = biller.bbps_blr_id
#         contact_no = biller.bbps_contact_no
#         amount = Decimal(str(biller.bbps_amount or 0))

#         log_main(f"[INFO] Processing biller: {request_id}")

#         try:
#             status_response = check_bbps_transaction_status(request_id)
#         except Exception as e:
#             log_status(f"[ERROR] Failed to check BBPS status for {request_id}: {str(e)}")
#             status_response = "FAILED"

#         try:
#             with transaction.atomic():
#                 if status_response == "SUCCESS":
#                     BBPSBillPayment.objects.filter(pk=biller.pk).update(
#                         bbps_status="SUCCESS",
#                         updated_at=dt_module.datetime.now()
#                     )
#                     log_success(f"[INFO] BBPS status FORCE-UPDATED to SUCCESS for {request_id}")


#                     try:
#                         handle_success_bbps(biller, sp_id, blr_id, contact_no, amount)
#                     except Exception as e:
                        
#                         log_success(f"[WARN] handle_success_bbps failed for {request_id}: {str(e)}")

#                 else:
#                     refund_bbps_transaction(biller, amount)
#                     log_failure(f"[INFO] BBPS transaction {request_id} refunded due to FAILED status")
#         except Exception as e:
#             log_failure(f"[ERROR] Exception processing biller {request_id}: {str(e)}")

from .views import *
import os
import datetime as dt_module
from decimal import Decimal
from django.db import transaction
from admin_hub.bbps_service import TransactionStatusAPIView

def create_logger(file_path):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    def log(message):
        with open(file_path, "a") as f:
            f.write(f"{dt_module.datetime.now()} - {message}\n")
        print(f"{dt_module.datetime.now()} - {message}")
    return log

from django.conf import settings
LOG_DIR = getattr(settings, 'BASE_DIR', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
main_log_file = os.path.join(LOG_DIR, "bbps_main_log.txt")
status_log_file = os.path.join(LOG_DIR, "bbps_status_log.txt")
success_log_file = os.path.join(LOG_DIR, "bbps_success_log.txt")
failure_log_file = os.path.join(LOG_DIR, "bbps_failure_log.txt")

log_main = create_logger(main_log_file)
log_status = create_logger(status_log_file)
log_success = create_logger(success_log_file)
log_failure = create_logger(failure_log_file)


def check_bbps_transaction_status(request_id: str, retries=3) -> dict:
    for attempt in range(retries):
        try:
            log_status(f"[INFO] Checking BBPS transaction status for request_id: {request_id}, attempt {attempt+1}")
            
            mock_request = type("obj", (object,), {"data": {"requestId": request_id}})()
            response = TransactionStatusAPIView().post(mock_request)
            
            if response.status_code != 200:
                log_status(f"[WARN] BBPS API returned status {response.status_code} for {request_id}")
                continue
            
            response_data = response.data.get("data", {})
            txn_resp = response_data.get("transactionStatusResp", {})
            
            response_code = txn_resp.get("responseCode", "")
            response_reason = txn_resp.get("responseReason", "").upper()
            
            txn_list = txn_resp.get("txnList", {})
            if isinstance(txn_list, list) and len(txn_list) > 0:
                txn_list = txn_list[0]
            
            txn_status = txn_list.get("txnStatus", "").upper() if isinstance(txn_list, dict) else ""
            
            log_status(f"[INFO] Response for {request_id} - Code: {response_code}, Reason: {response_reason}, TxnStatus: {txn_status}")
            
            if response_code == "000" and response_reason == "SUCCESS" and txn_status == "SUCCESS":
                log_status(f"[INFO] Transaction {request_id} confirmed SUCCESS (responseReason: SUCCESS, txnStatus: SUCCESS)")
                return {
                    "status": "SUCCESS",
                    "response_code": response_code,
                    "response_reason": response_reason,
                    "txn_status": txn_status
                }
            
            elif response_code == "000" and response_reason == "FAILURE":
                log_status(f"[INFO] Transaction {request_id} confirmed FAILED (responseReason: FAILURE, txnStatus: {txn_status})")
                return {
                    "status": "FAILED",
                    "response_code": response_code,
                    "response_reason": response_reason,
                    "txn_status": txn_status
                }
            
            elif response_code == "000":
                log_status(f"[INFO] Transaction {request_id} status unclear (responseReason: {response_reason}, txnStatus: {txn_status})")
                return {
                    "status": "PENDING",
                    "response_code": response_code,
                    "response_reason": response_reason,
                    "txn_status": txn_status
                }
            
            elif response_code in ["205", "V4008"]:  
                log_status(f"[WARN] Invalid request for {request_id} - Code: {response_code}")
                return {
                    "status": "PENDING",  
                    "response_code": response_code,
                    "response_reason": response_reason,
                    "txn_status": txn_status
                }
            
            else:
                log_status(f"[WARN] Unknown status for {request_id} - Code: {response_code}, Reason: {response_reason}, Status: {txn_status}")
                return {
                    "status": "PENDING",
                    "response_code": response_code,
                    "response_reason": response_reason,
                    "txn_status": txn_status
                }
                
        except Exception as e:
            log_status(f"[WARN] BBPS API error for {request_id} attempt {attempt+1}: {str(e)}")
    
    log_status(f"[ERROR] All {retries} attempts failed for {request_id}, marking as ERROR")
    return {
        "status": "ERROR",
        "response_code": "",
        "response_reason": "API_ERROR",
        "txn_status": ""
    }


def handle_success_bbps(biller, sp_id, blr_id, contact_no, formatted_amount):
    log_success(f"[INFO] Handling SUCCESS for BBPS transaction: {biller.bbps_request_id}")

    category = BBPSBiller.objects.filter(bbps_blr_id=blr_id).first()
    service_provider = AdServiceProvider.objects.get(sp_id=sp_id)

    gst_rate = Decimal(str(service_provider.hsn_sac.tax_rate))
    admin_rate = Decimal(str(category.bbps_category.to_us_charges.get("rate_value")))
    admin_rate_type = category.bbps_category.to_us_charges.get("rate_type")
    admin_charges_type = category.bbps_category.to_us_charges.get("charge_type")

    char_comm_amt = (
        formatted_amount * (admin_rate / Decimal("100"))
        if admin_rate_type == "is_percent"
        else admin_rate
    )
    admin_tax_amt = char_comm_amt - (char_comm_amt / (Decimal("1") + (gst_rate / Decimal("100"))))

    portal_user_details = PortalUserDetails.objects.get(pu_id=biller.created_by)

    rtl_wallet = PortalUserWallet.objects.select_for_update().get(pu_id=biller.created_by)
    admin_wallet = PortalUserWallet.objects.select_for_update().get(pu_id=1)

    if not GlTrn.objects.filter(service_trn_id=biller.pk, pu_id=rtl_wallet.pu_id).exists():
        rtl_gl = GlTrn.objects.create(
            service_trn_id=biller.pk,
            pu_id=rtl_wallet.pu_id,
            gl_trn_amt=formatted_amount,
            effectvie_wallet="main_wallet",
            effectvie_amt=formatted_amount,
            service_trn_table="ad_bbps_service_transaction",
            effective_type="DR",
            gl_trn_dt=dt_module.datetime.now(),
        )
        WalletTrn.objects.create(
            action_id=rtl_gl.pk,
            action_type="Service",
            pu_id=rtl_wallet.pu_id,
            wl_label=f"BBPS debit of {formatted_amount} with tx_id {biller.bbps_request_id}",
            effectvie_wallet="main_wallet",
            effectvie_amt=formatted_amount,
            effective_type="DR",
            current_balance=rtl_wallet.main_wallet - formatted_amount,
            wl_trn_dt=dt_module.datetime.now(),
        )
        rtl_wallet.main_wallet -= formatted_amount
        rtl_wallet.updated_at = dt_module.datetime.now()
        rtl_wallet.save(update_fields=["main_wallet", "updated_at"])

    if not GlTrn.objects.filter(service_trn_id=biller.pk, pu_id=1, action_type="Service").exists():
        admin_gl = GlTrn.objects.create(
            service_trn_id=biller.pk,
            pu_id=1,
            gl_trn_amt=formatted_amount,
            effectvie_wallet="main_wallet",
            effectvie_amt=formatted_amount,
            service_trn_table="ad_bbps_service_transaction",
            effective_type="DR",
            gl_trn_dt=dt_module.datetime.now(),
        )
        WalletTrn.objects.create(
            action_id=admin_gl.pk,
            action_type="Service",
            pu_id=1,
            wl_label=f"BBPS_by_{portal_user_details.pud_unique_id}_of_amount_{formatted_amount}_with_tx_id_{biller.bbps_request_id}",
            effectvie_wallet="main_wallet",
            effectvie_amt=formatted_amount,
            effective_type="DR",
            current_balance=admin_wallet.main_wallet - formatted_amount,
            wl_trn_dt=dt_module.datetime.now(),
        )
        admin_wallet.main_wallet -= formatted_amount
        admin_wallet.updated_at = dt_module.datetime.now()
        admin_wallet.save(update_fields=["main_wallet", "updated_at"])

    if not GlTrn.objects.filter(service_trn_id=biller.pk, pu_id=1, effective_type=admin_charges_type, gl_trn_amt=char_comm_amt).exists():
        admin_gl_comm = GlTrn.objects.create(
            service_trn_id=biller.pk,
            pu_id=1,
            gl_tax_rate=float(gst_rate),
            gl_tax_amt=admin_tax_amt,
            gl_trn_amt=formatted_amount,
            effectvie_wallet="main_wallet",
            effectvie_amt=char_comm_amt,
            service_trn_table="ad_bbps_service_transaction",
            effective_type=admin_charges_type,
            gl_trn_dt=dt_module.datetime.now(),
        )
        if admin_charges_type == "CR":
            admin_wallet.main_wallet += char_comm_amt
        else:
            admin_wallet.main_wallet -= char_comm_amt
        admin_wallet.updated_at = dt_module.datetime.now()
        admin_wallet.save(update_fields=["main_wallet", "updated_at"])

        WalletTrn.objects.create(
            action_id=biller.pk,
            action_type="Service",
            pu_id=1,
            wl_label=f"BBPS_commission_by_{portal_user_details.pud_unique_id}_of_amount_{char_comm_amt}_with_tx_id_{biller.bbps_request_id}",
            effectvie_wallet="main_wallet",
            effectvie_amt=char_comm_amt,
            effective_type=admin_charges_type,
            current_balance=admin_wallet.main_wallet,
            wl_trn_dt=dt_module.datetime.now(),
        )

    data = {
        "order_amount": float(formatted_amount),
        "id": biller.created_by,
        "sp_id": sp_id,
        "customer_contact_no": contact_no,
        "customer_name": None,
        "service_trn": biller.pk,
        "category": category.bbps_category.bbps_id,
        "table_name": "ad_bbps_service_transaction",
    }
    after_tx_cal(biller, data)



def refund_bbps_transaction(biller, refund_amount: Decimal):
    log_failure(f"[INFO] Processing refund for {biller.bbps_request_id}, amount: {refund_amount}")
    
    rtl_wallet = PortalUserWallet.objects.select_for_update().get(pu_id=biller.created_by)
    admin_wallet = PortalUserWallet.objects.select_for_update().get(pu_id=1)

    if not WalletTrn.objects.filter(action_type="Refund", action_id=biller.pk, pu_id=rtl_wallet.pu_id).exists():
        rtl_wallet.main_wallet += refund_amount
        rtl_wallet.updated_at = dt_module.datetime.now()
        rtl_wallet.save(update_fields=["main_wallet", "updated_at"])

        GlTrn.objects.create(
            service_trn_id=biller.pk,
            pu_id=biller.created_by,
            gl_trn_amt=refund_amount,
            effectvie_wallet="main_wallet",
            effectvie_amt=refund_amount,
            service_trn_table="ad_bbps_service_transaction",
            effective_type="CR",
            gl_trn_dt=dt_module.datetime.now(),
        )

        WalletTrn.objects.create(
            action_id=biller.pk,
            action_type="Refund",
            pu_id=rtl_wallet.pu_id,
            wl_label=f"Refund for BBPS transaction {biller.bbps_request_id}",
            effectvie_wallet="main_wallet",
            effectvie_amt=refund_amount,
            effective_type="CR",
            current_balance=rtl_wallet.main_wallet,
            wl_trn_dt=dt_module.datetime.now(),
        )
        log_failure(f"[INFO] Retailer refund processed: {refund_amount}")

    admin_entries = GlTrn.objects.filter(service_trn_id=biller.pk, pu_id=1)

    for entry in admin_entries:
        if WalletTrn.objects.filter(
            action_type="Refund_Admin", action_id=biller.pk, pu_id=1,
            wl_label__contains=str(entry.pk)
        ).exists():
            continue

        reverse_type = "CR" if entry.effective_type == "DR" else "DR"

        if reverse_type == "CR":
            admin_wallet.main_wallet += entry.effectvie_amt
        else:
            admin_wallet.main_wallet -= entry.effectvie_amt

        admin_wallet.updated_at = dt_module.datetime.now()
        admin_wallet.save(update_fields=["main_wallet", "updated_at"])

        GlTrn.objects.create(
            service_trn_id=biller.pk,
            pu_id=1,
            gl_trn_amt=entry.effectvie_amt,
            effectvie_wallet="main_wallet",
            effectvie_amt=entry.effectvie_amt,
            service_trn_table="ad_bbps_service_transaction",
            effective_type=reverse_type,
            gl_trn_dt=dt_module.datetime.now(),
        )

        WalletTrn.objects.create(
            action_id=biller.pk,
            action_type="Refund_Admin",
            pu_id=1,
            wl_label=f"Refund reverse for BBPS tx {biller.bbps_request_id} (GL {entry.pk})",
            effectvie_wallet="main_wallet",
            effectvie_amt=entry.effectvie_amt,
            effective_type=reverse_type,
            current_balance=admin_wallet.main_wallet,
            wl_trn_dt=dt_module.datetime.now(),
        )

    biller.bbps_status = "FAILED"
    biller.updated_at = dt_module.datetime.now()
    biller.save(update_fields=["bbps_status", "updated_at"])
    log_failure(f"[INFO] Transaction {biller.bbps_request_id} marked as FAILED")



def process_inprogress_bbps():

    cutoff_time = dt_module.datetime.now() - dt_module.timedelta(minutes=10)
    
    inprogress_bills = BBPSBillPayment.objects.filter(
        bbps_status="INPROGRESS",
        created_at__lte=cutoff_time  
    )
    

    for biller in inprogress_bills:
        request_id = biller.bbps_request_id
        sp_id = biller.bbps_sp.sp_id if biller.bbps_sp else None
        blr_id = biller.bbps_blr_id
        contact_no = biller.bbps_contact_no
        amount = Decimal(str(biller.bbps_amount or 0))

        log_main(f"[INFO] Processing biller: {request_id}, amount: {amount}")

        try:
            status_result = check_bbps_transaction_status(request_id)
            final_status = status_result.get("status")
            
            log_main(f"[INFO] Status check result for {request_id}: {final_status}")

            with transaction.atomic():
                biller = BBPSBillPayment.objects.select_for_update().get(pk=biller.pk)
                
                if biller.bbps_status != "INPROGRESS":
                    log_main(f"[INFO] Biller {request_id} already processed, skipping")
                    continue
                
                if final_status == "SUCCESS":
                    biller.bbps_status = "SUCCESS"
                    biller.updated_at = dt_module.datetime.now()
                    biller.save(update_fields=["bbps_status", "updated_at"])
                    log_success(f"[INFO] BBPS status updated to SUCCESS for {request_id}")

                    try:
                        handle_success_bbps(biller, sp_id, blr_id, contact_no, amount)
                        log_success(f"[INFO] SUCCESS processing completed for {request_id}")
                    except Exception as e:
                        log_success(f"[ERROR] handle_success_bbps failed for {request_id}: {str(e)}")
                
                elif final_status == "FAILED":
                    log_failure(f"[INFO] Transaction {request_id} confirmed FAILED, processing refund")
                    refund_bbps_transaction(biller, amount)
                    log_failure(f"[INFO] Refund completed for {request_id}")
                
                elif final_status == "PENDING":
                    log_main(f"[INFO] Transaction {request_id} still PENDING, keeping as INPROGRESS")
                    # No action needed, biller stays INPROGRESS
                
                elif final_status == "ERROR":
                    log_main(f"[WARN] API error for {request_id}, keeping as INPROGRESS for retry")
                
        except Exception as e:
            log_failure(f"[ERROR] Exception processing biller {request_id}: {str(e)}")
            continue
    
    log_main(f"[INFO] BBPS cron job completed")