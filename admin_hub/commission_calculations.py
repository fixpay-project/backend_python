# import json
# import re
# from django.db import connections, transaction
# from django.utils.timezone import now
# from .db_model_for_raw_query import *
# from .models import (
#     PortalUserCharges, AdHSNSAC, AdServiceProvider, 
#     WalletTrn, PortalUserWallet, GlTrn, PortalUser, AdService, BBPSBillerCategory, PortalUserDetails
# )

# def calculate_financial_details(data, service_nature, remaining_rate):
#     """
#     Calculate payable amount, TDS amount, and tax amount based on provided data.
#     """

#     # Extract data
#     rate = float(data.get('rate'))
#     rate_type = data.get('rate_type')
#     actual_amount = float(data.get('amount'))
#     commission_type = data.get('commission_type')
#     gst_rate = float(data.get('tax_rate'))
#     tds_rate = float(data.get('tds_rate'))
#     if service_nature == 'CHARGE':
#         # Calculate the effective rate
#         if not remaining_rate == 0.00:
#             effective_rate = remaining_rate - rate
#         else:
#             effective_rate = rate
#     else:
#         # Calculate the effective rate
#         effective_rate = rate - remaining_rate
#     effective_rate = round(effective_rate, 3)
#     remaining_rate = rate  # Update remaining_rate to the current rate

#     # Calculate amount to use based on rate type
#     amount_to_use = actual_amount * (effective_rate / 100) if rate_type == 'is_percent' else effective_rate

#     # Initialize amounts
#     effective_amount = 0.0
#     tds_amount = 0.0
#     tax_amount = 0.0

#     # Calculate amounts based on commission type
#     if commission_type == 'CHARGE WITH GST':
#         tax_amount = float(amount_to_use) - (float(amount_to_use)/(1+(float(gst_rate)/100)))
#         effective_amount = amount_to_use
#     elif commission_type == 'COMMISSION WITHOUT GST':
#         tds_amount = (float(amount_to_use) * float(tds_rate)) / 100
#         effective_amount = amount_to_use - tds_amount
#     elif commission_type == 'COMMISSION WITH GST':
#         tax_amount = float(amount_to_use) - (float(amount_to_use)/(1+(float(gst_rate)/100)))
#         amount_after_tax = amount_to_use - tax_amount
#         tds_amount = (float(amount_after_tax) * float(tds_rate)) / 100
#         effective_amount = amount_after_tax - tds_amount + tax_amount

#     # Round results to 3 decimal places
#     effective_amount = round(effective_amount, 3)
#     tds_amount = round(tds_amount, 3)
#     tax_amount = round(tax_amount, 3)
    
#     return effective_amount, tds_amount, tax_amount, remaining_rate


# def log_wallet_transaction(user, action_id, action_type, label, amount, effective_wallet, effective_type, current_balance):
#     """Create a wallet transaction entry."""
#     WalletTrn.objects.create(
#         action_id=action_id,
#         action_type=action_type,
#         pu=user,
#         wl_label=label,
#         effectvie_wallet=effective_wallet,
#         effectvie_amt=amount,
#         effective_type=effective_type,
#         current_balance=current_balance,
#         wl_trn_dt=now()
#     )


# def update_user_wallet(user, amount, charge_type, wallet_type):
#     """Update the user wallet dynamically based on the effective wallet type."""
#     wallet = PortalUserWallet.objects.get(pu=user)
    
#     current_balance = float(getattr(wallet, wallet_type))
    
#     if charge_type == 'CR':  # Credit
#         updated_balance = current_balance + amount
#     elif charge_type == 'DR':  # Debit
#         updated_balance = current_balance - amount
#     else:
#         return None  # Handle invalid charge_type
    
#     setattr(wallet, wallet_type, updated_balance)
#     wallet.updated_at = now()
#     wallet.save()
    
#     return updated_balance  # Return the updated balance


# def get_matching_charge(order_amount, charges_data):
    
#     """
#     Select the appropriate charge dictionary from the list based on order amount.
#     If min and max are 0, return the first dictionary.
#     If not, find the one where the order amount fits in the range.
#     """
#     for charge in charges_data:
#         min_value = float(charge.get('minimum', 0))
#         max_value = float(charge.get('maximum', 0))

#         # If both min and max are 0, return the first dictionary
#         if min_value == 0 and max_value == 0:
#             return charge

#         # Check if the order_amount fits within the min-max range
#         if min_value <= float(order_amount) <= max_value:
#             return charge

#     # If no match found, raise an error (optional)
#     raise ValueError("No valid charge entry found for the given order amount.")


# @transaction.atomic
# def after_tx_cal(request, data):
#     try:
#         # Extract data from request
#         order_amount = data.get('order_amount')
#         user_id = data.get('id')
#         sp_id = data.get('sp_id')
#         service_trn = data.get('service_trn')
#         label = data.get('label')
#         category = data.get('category', None)
#         trn_response = data.get('trn_response')
#         table_name = data.get('table_name')
#         charge_level = data.get('charge_level')

#         # Fetch user's charges and parent data
#         sp_obj = AdServiceProvider.objects.get(sp_id=sp_id)
#         service_obj = AdService.objects.get(service_id=sp_obj.service_id)
#         is_global = service_obj.is_global
#         is_table_config = service_obj.is_table_config
#         service_name = service_obj.service_name

#         service_nature = sp_obj.service_nature
        
#         tax_rate = AdHSNSAC.objects.get(hsnsac_id=sp_obj.hsn_sac_id).tax_rate

#         tds_rate = sp_obj.tds_rate

#         # Recursive Query to fetch all users in the hierarchy
#         if is_global and is_table_config:
#             users_lst = fetch_user_hierarchy(user_id)
#         else:
#             users_lst = fetch_user_charges_hierarchy(user_id, sp_id)

#         remaining_rate = 0.00

#         # print("&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&")
#         # print(users_lst)
#         # print(len(users_lst))
#         for res in users_lst:
#             # print('*********************************************************')
#             # print(res)
#             # print(len(res))
#             if len(res) == 2 and service_name == 'BBPS':
#                 bbps_cat = BBPSBillerCategory.objects.get(bbps_id=category)
#                 pu_id = res['user_id']
#                 dh_id = res['dh_id']
                
#                 if dh_id is None:
#                     puc_charges = json.dumps(bbps_cat.rt_charges)
#                 elif dh_id == 3:
#                     puc_charges = json.dumps(bbps_cat.dt_charges)
#                 elif dh_id == 2:
#                     puc_charges = json.dumps(bbps_cat.md_charges)
#                 elif dh_id == 1:
#                     puc_charges = json.dumps(bbps_cat.sd_charges)
#                 else:
#                     raise Exception(f"Invalid category: {dh_id}")
                
#             elif len(res) == 2 and service_name == 'Recharge':
#                 oprators_cat = Oprators.objects.get(operator_id=category)
#                 pu_id = res['user_id']
#                 dh_id = res['dh_id']
#                 if dh_id is None:
#                     puc_charges = json.dumps(oprators_cat.rt_charges)
#                 elif dh_id == 3:
#                     puc_charges = json.dumps(oprators_cat.dt_charges)
#                 elif dh_id == 2:
#                     puc_charges = json.dumps(oprators_cat.md_charges)
#                 elif dh_id == 1:
#                     puc_charges = json.dumps(oprators_cat.sd_charges)
#                 else:
#                     raise Exception(f"Invalid category: {dh_id}")
#             else:
#                 pu_id = res['pu_id']
#                 parent_id = res['parent_id']
#                 puc_charges = res['puc_charges']
#                 charge_type = res['charge_type']
#                 sp_id = res['sp_id']
#                 dh_id = res['dh_id']

                
                
#             if isinstance(puc_charges, list):
#                 charges_data = puc_charges
#             else:
#                 try:
#                     charges_data = json.loads(puc_charges)
#                 except json.JSONDecodeError as e:
#                     raise ValueError(f"Invalid JSON format in puc_charges: {puc_charges}. Error: {str(e)}")
#             # try:
#             #     charges_data = json.loads(puc_charges)

                
#             # except json.JSONDecodeError as e:
#             #     raise ValueError(f"Invalid JSON format in puc_charges: {puc_charges}. Error: {str(e)}")
            
#             # Get the relevant charge dictionary based on order amount
#             print(charges_data)
#             print(order_amount)
#             selected_charge = get_matching_charge(order_amount, charges_data)
#             print(get_matching_charge(order_amount,charges_data))

#             if sp_id==1:
#                 rate = selected_charge["regular_rate"] if charge_level == 'REGULAR' else selected_charge["premium_rate"]
#             else:
#                 rate = selected_charge["rate"]
            
#             rate_type = selected_charge["rate_type"]
#             charge_type = selected_charge["charge_type"]
#             commission_type = selected_charge["commission_type"]
#             effective_wallet = selected_charge["effective_wallet"]
            
#             # Map charge type to its full form
#             charge_type_full = "credited" if charge_type == "CR" else "debited"
            
#             cfd_data = {
#                 'rate': rate,
#                 'rate_type': rate_type,
#                 'commission_type': commission_type,
#                 'amount': order_amount,
#                 'tax_rate': tax_rate,
#                 'tds_rate': tds_rate
#             }

#             effective_amount, tds_amount, tax_amount, remaining_rate = calculate_financial_details(cfd_data, service_nature, remaining_rate)
                
#             # Log GL transaction for each user
#             gl_trn = GlTrn.objects.create(
#                 service_trn_id=service_trn,
#                 pu_id=pu_id,
#                 gl_trn_amt=order_amount,
#                 gl_tds_rate=tds_rate,
#                 gl_tax_rate=tax_rate,
#                 gl_tds_amt=tds_amount,
#                 gl_tax_amt=tax_amount,
#                 effectvie_wallet=effective_wallet,
#                 effectvie_amt=effective_amount,
#                 effective_type=charge_type,
#                 service_trn_table=table_name,
#                 gl_trn_dt=now(),
#             )
            
#             # Update the user's wallet based on the effective wallet
#             commission_user = PortalUser.objects.get(id=pu_id)
#             puw_user = PortalUserWallet.objects.get(pu_id=pu_id)
#             portal_user_details = PortalUserDetails.objects.get(pu_id=pu_id)
            
#             current_balance = update_user_wallet(commission_user, effective_amount, charge_type, effective_wallet)
            
#             # Log the wallet transaction
#             log_wallet_transaction(
#                 user=commission_user,
#                 action_id=gl_trn.pk,
#                 action_type='Service',
#                 label=f"Using {label}, {portal_user_details.pud_unique_id} gets {effective_amount} Rs {commission_type} in {effective_wallet} as {charge_type_full}.",
#                 amount=effective_amount,
#                 effective_wallet=effective_wallet,
#                 current_balance=current_balance,
#                 effective_type=charge_type
#             )

#     except Exception as e:
#         raise Exception(f"Error distributing commissions: {str(e)}")


import json
import re
from django.db import connections, transaction
from django.utils.timezone import now
from .db_model_for_raw_query import *
from .models import (
    PortalUserCharges, AdHSNSAC, AdServiceProvider, 
    WalletTrn, PortalUserWallet, GlTrn, PortalUser, AdService, BBPSBillerCategory, PortalUserDetails,CommissionTransaction, CommissionSettlementStatus
)

def calculate_financial_details(data, service_nature, remaining_rate):
    """
    Calculate payable amount, TDS amount, and tax amount based on provided data.
    """

    # Extract data
    rate = float(data.get('rate'))
    rate_type = data.get('rate_type')
    actual_amount = float(data.get('amount'))
    commission_type = data.get('commission_type')
    gst_rate = float(data.get('tax_rate'))
    tds_rate = float(data.get('tds_rate'))
    if service_nature == 'CHARGE':
        # Calculate the effective rate
        if not remaining_rate == 0.00:
            effective_rate = remaining_rate - rate
        else:
            effective_rate = rate
    else:
        # Calculate the effective rate
        effective_rate = rate - remaining_rate
    effective_rate = round(effective_rate, 3)
    remaining_rate = rate  # Update remaining_rate to the current rate

    # Calculate amount to use based on rate type
    amount_to_use = actual_amount * (effective_rate / 100) if rate_type == 'is_percent' else effective_rate

    # Initialize amounts
    effective_amount = 0.0
    tds_amount = 0.0
    tax_amount = 0.0

    # Calculate amounts based on commission type
    if commission_type == 'CHARGE WITH GST':
        tax_amount = float(amount_to_use) - (float(amount_to_use)/(1+(float(gst_rate)/100)))
        effective_amount = amount_to_use
    elif commission_type == 'COMMISSION WITHOUT GST':
        tds_amount = (float(amount_to_use) * float(tds_rate)) / 100
        effective_amount = amount_to_use - tds_amount
    elif commission_type == 'COMMISSION WITH GST':
        tax_amount = float(amount_to_use) - (float(amount_to_use)/(1+(float(gst_rate)/100)))
        amount_after_tax = amount_to_use - tax_amount
        tds_amount = (float(amount_after_tax) * float(tds_rate)) / 100
        effective_amount = amount_after_tax - tds_amount + tax_amount

    # Round results to 3 decimal places
    effective_amount = round(effective_amount, 3)
    tds_amount = round(tds_amount, 3)
    tax_amount = round(tax_amount, 3)
    
    return effective_amount, tds_amount, tax_amount, remaining_rate


def log_wallet_transaction(user, action_id, action_type, label, amount, effective_wallet, effective_type, current_balance):
    """Create a wallet transaction entry."""
    WalletTrn.objects.create(
        action_id=action_id,
        action_type=action_type,
        pu=user,
        wl_label=label,
        effectvie_wallet=effective_wallet,
        effectvie_amt=amount,
        effective_type=effective_type,
        current_balance=current_balance,
        wl_trn_dt=now()
    )


def update_user_wallet(user, amount, charge_type, wallet_type):
    """Update the user wallet dynamically based on the effective wallet type."""
    wallet = PortalUserWallet.objects.get(pu=user)
    
    current_balance = float(getattr(wallet, wallet_type))
    
    if charge_type == 'CR':  # Credit
        updated_balance = current_balance + amount
    elif charge_type == 'DR':  # Debit
        updated_balance = current_balance - amount
    else:
        return None  # Handle invalid charge_type
    
    setattr(wallet, wallet_type, updated_balance)
    wallet.updated_at = now()
    wallet.save()
    
    return updated_balance  # Return the updated balance


def get_matching_charge(order_amount, charges_data):
    
    """
    Select the appropriate charge dictionary from the list based on order amount.
    If min and max are 0, return the first dictionary.
    If not, find the one where the order amount fits in the range.
    """
    for charge in charges_data:
        min_value = float(charge.get('minimum', 0))
        max_value = float(charge.get('maximum', 0))

        # If both min and max are 0, return the first dictionary
        if min_value == 0 and max_value == 0:
            return charge

        # Check if the order_amount fits within the min-max range
        if min_value <= float(order_amount) <= max_value:
            return charge

    # If no match found, raise an error (optional)
    raise ValueError("No valid charge entry found for the given order amount.")


@transaction.atomic
def after_tx_cal(request, data):
    try:
        order_amount = data.get('order_amount')
        user_id = data.get('id')
        sp_id = data.get('sp_id')
        service_trn = data.get('service_trn')
        label = data.get('label')
        category = data.get('category', None)
        table_name = data.get('table_name')
        charge_level = data.get('charge_level')

        sp_obj = AdServiceProvider.objects.get(sp_id=sp_id)
        service_obj = AdService.objects.get(service_id=sp_obj.service_id)
        service_name = service_obj.service_name
        is_global = service_obj.is_global
        is_table_config = service_obj.is_table_config
        service_nature = sp_obj.service_nature
        tax_rate = AdHSNSAC.objects.get(hsnsac_id=sp_obj.hsn_sac_id).tax_rate
        tds_rate = sp_obj.tds_rate

        if is_global and is_table_config:
            users_lst = fetch_user_hierarchy(user_id)
        else:
            users_lst = fetch_user_charges_hierarchy(user_id, sp_id)

        remaining_rate = 0.00

        for res in users_lst:
            if len(res) == 2 and service_name == 'BBPS':
                bbps_cat = BBPSBillerCategory.objects.get(bbps_id=category)
                pu_id = res['user_id']
                dh_id = res['dh_id']
                if dh_id is None:
                    puc_charges = json.dumps(bbps_cat.rt_charges)
                elif dh_id == 3:
                    puc_charges = json.dumps(bbps_cat.dt_charges)
                elif dh_id == 2:
                    puc_charges = json.dumps(bbps_cat.md_charges)
                elif dh_id == 1:
                    puc_charges = json.dumps(bbps_cat.sd_charges)
                else:
                    raise Exception(f"Invalid category: {dh_id}")

            elif len(res) == 2 and service_name == 'Recharge':
                oprators_cat = Oprators.objects.get(operator_id=category)
                pu_id = res['user_id']
                dh_id = res['dh_id']
                if dh_id is None:
                    puc_charges = json.dumps(oprators_cat.rt_charges)
                elif dh_id == 3:
                    puc_charges = json.dumps(oprators_cat.dt_charges)
                elif dh_id == 2:
                    puc_charges = json.dumps(oprators_cat.md_charges)
                elif dh_id == 1:
                    puc_charges = json.dumps(oprators_cat.sd_charges)
                else:
                    raise Exception(f"Invalid category: {dh_id}")
            else:
                pu_id = res['pu_id']
                parent_id = res['parent_id']
                puc_charges = res['puc_charges']
                charge_type = res['charge_type']
                sp_id = res['sp_id']
                dh_id = res['dh_id']

            charges_data = json.loads(puc_charges) if not isinstance(puc_charges, list) else puc_charges

            selected_charge = get_matching_charge(order_amount, charges_data)
            rate = selected_charge["regular_rate"] if (sp_id == 1 and charge_level == 'REGULAR') else selected_charge.get("rate", selected_charge.get("premium_rate"))
            rate_type = selected_charge["rate_type"]
            charge_type = selected_charge["charge_type"]
            commission_type = selected_charge["commission_type"]
            effective_wallet = selected_charge["effective_wallet"]
            charge_type_full = "credited" if charge_type == "CR" else "debited"

            cfd_data = {
                'rate': rate,
                'rate_type': rate_type,
                'commission_type': commission_type,
                'amount': order_amount,
                'tax_rate': tax_rate,
                'tds_rate': tds_rate
            }

            effective_amount, tds_amount, tax_amount, remaining_rate = calculate_financial_details(
                cfd_data, service_nature, remaining_rate
            )

            gl_trn = GlTrn.objects.create(
                service_trn_id=service_trn,
                pu_id=pu_id,
                gl_trn_amt=order_amount,
                gl_tds_rate=tds_rate,
                gl_tax_rate=tax_rate,
                gl_tds_amt=tds_amount,
                gl_tax_amt=tax_amount,
                effectvie_wallet=effective_wallet,
                effectvie_amt=effective_amount,
                effective_type=charge_type,
                service_trn_table=table_name,
                gl_trn_dt=now(),
            )

            if dh_id is not None:
                CommissionTransaction.objects.create(
                    transaction_id=str(service_trn),  
                    distributor_id=pu_id,             
                    retailer_id=user_id,              
                    service_provider=sp_obj,
                    amount=effective_amount,
                    settlement_status=CommissionSettlementStatus.UNSETTLED,
                    settlement_mode=None,
                    settlement_date=None  
                )

            if dh_id is None:
                commission_user = PortalUser.objects.get(id=pu_id)
                current_balance = update_user_wallet(
                    commission_user, effective_amount, charge_type, effective_wallet
                )
                portal_user_details = PortalUserDetails.objects.get(pu_id=pu_id)
                log_wallet_transaction(
                    user=commission_user,
                    action_id=gl_trn.pk,
                    action_type='Service',
                    label=f"Using {label}, {portal_user_details.pud_unique_id} gets {effective_amount} Rs {commission_type} in {effective_wallet} as {charge_type_full}.",
                    amount=effective_amount,
                    effective_wallet=effective_wallet,
                    current_balance=current_balance,
                    effective_type=charge_type
                )

    except Exception as e:
        raise Exception(f"Error distributing commissions: {str(e)}")