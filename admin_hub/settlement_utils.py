import logging
from django.utils.timezone import now
from datetime import timedelta
from django.db import transaction
from decimal import Decimal
import logging
from logging import FileHandler, Formatter
from django.utils.timezone import now
from admin_hub.models import CommissionAutoSettlementConfig
from admin_hub.models import CommissionSettlementLog
from admin_hub.models import (
        CommissionTransaction, CommissionSettlementStatus,
        PortalUser, PortalUserWallet, WalletTrn
    )
logger = logging.getLogger('commission_audit')
logger.setLevel(logging.INFO)

if not logger.handlers:
    fh = FileHandler('commission_audit.log')  
    fh.setLevel(logging.INFO)
    formatter = Formatter('%(levelname)s %(asctime)s %(module)s %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

def get_settlement_delay_for_distributor(distributor):
    print(f"Checking auto-settlement delay for distributor: {distributor}")

    config = CommissionAutoSettlementConfig.objects.filter(
        distributor=distributor,
        is_active=True
    ).first()
    if config:
        print(f"Found active distributor-specific config: {config.auto_settlement_delay_days} days")
        return config.auto_settlement_delay_days
    else:
        print("No active distributor-specific config found")

    global_config = CommissionAutoSettlementConfig.objects.filter(
        distributor__isnull=True,
        is_active=True
    ).first()
    if global_config:
        print(f"Using active global config: {global_config.auto_settlement_delay_days} days")
        return global_config.auto_settlement_delay_days
    else:
        print("No active global config found")

    print("Falling back to default: 7 days")
    return 1



def log_commission_settlement_audit(distributor, commission_ids, total_amount, mode, performed_by=None):
    
    
    settlement_log = CommissionSettlementLog.objects.create(
        distributor=distributor,
        reference_commissions=commission_ids,
        total_amount=total_amount,
        mode=mode,
        performed_by=performed_by
    )

    performed_by_str = performed_by.username if performed_by else "SYSTEM"
    logger.info(
        f"Commission Settlement | Performed By: {performed_by_str} | "
        f"Distributor ID: {distributor.id} | Commission IDs: {commission_ids} | "
        f"Total Amount: {total_amount} | Mode: {mode} | Timestamp: {now()}"
    )

    return settlement_log


def settle_commissions(commission_ids=None, performed_by=None, mode='MANUAL'):
    
    
    if mode not in ['MANUAL', 'AUTO']:
        raise ValueError("mode must be either 'MANUAL' or 'AUTO'")

    if commission_ids:
        commissions = CommissionTransaction.objects.filter(
            id__in=commission_ids,
            settlement_status=CommissionSettlementStatus.UNSETTLED
        )
    else:
        commissions = CommissionTransaction.objects.filter(
            settlement_status=CommissionSettlementStatus.UNSETTLED
        )

    if not commissions.exists():
        return []

    grouped_commissions = {}
    for comm in commissions:
        grouped_commissions.setdefault(comm.distributor_id, []).append(comm)

    results = []

    for distributor_id, comm_list in grouped_commissions.items():
        with transaction.atomic():
            total_amount = sum([Decimal(c.amount) for c in comm_list])
            distributor = PortalUser.objects.get(id=distributor_id)

            distributor_wallet = PortalUserWallet.objects.get(pu=distributor)
            if distributor_wallet.pg_wallet is None:
                distributor_wallet.pg_wallet = Decimal('0.00')

            distributor_wallet.pg_wallet += total_amount
            distributor_wallet.updated_at = now()
            distributor_wallet.save()

            settlement_log = log_commission_settlement_audit(
                distributor=distributor,
                commission_ids=[c.id for c in comm_list],
                total_amount=total_amount,
                mode=mode,
                performed_by=performed_by
            )

            settlement_status = (
                CommissionSettlementStatus.MANUAL_SETTLED if mode == 'MANUAL'
                else CommissionSettlementStatus.AUTO_SETTLED
            )
            
            CommissionTransaction.objects.filter(
                id__in=[c.id for c in comm_list]
            ).update(
                settlement_status=settlement_status,
                settlement_mode=mode,
                settlement_date=now()
            )

            WalletTrn.objects.create(
                action_id=settlement_log.id,
                action_type='Commission Settlement',
                pu=distributor,
                wl_label=f'{mode.capitalize()} Commission Settlement #CS{settlement_log.id}',
                effectvie_wallet='pg_wallet',
                effectvie_amt=total_amount,
                effective_type='CR',
                current_balance=distributor_wallet.pg_wallet,
                wl_trn_dt=now()
            )

            results.append({
                'distributor': distributor.username,
                'distributor_id': distributor.id,
                'settlement_id': settlement_log.id,
                'total_amount': str(total_amount),
                'commission_count': len(comm_list)
            })

    return results


from django.utils.timezone import now, make_aware
from django.utils.timezone import now, make_aware, is_naive
from datetime import timedelta
from admin_hub.models import (
    CommissionTransaction, CommissionSettlementStatus,
    CommissionAutoSettlementConfig
)

def get_settlement_delay_for_distributor(distributor):
    print(f"Checking auto-settlement delay for distributor: {distributor}")

    config = CommissionAutoSettlementConfig.objects.filter(
        distributor=distributor,
        is_active=True
    ).first()
    if config:
        print(f"Found active distributor-specific config: {config.auto_settlement_delay_days} days")
        return config.auto_settlement_delay_days
    else:
        print("No active distributor-specific config found")

    global_config = CommissionAutoSettlementConfig.objects.filter(
        distributor__isnull=True,
        is_active=True
    ).first()
    if global_config:
        print(f"Using active global config: {global_config.auto_settlement_delay_days} days")
        return global_config.auto_settlement_delay_days
    else:
        print("No active global config found")

    print("Falling back to default: 7 days")
    return 1


def get_eligible_commissions_for_auto_settlement():
    current_date = now()
    eligible_commissions = []

    unsettled_commissions = CommissionTransaction.objects.filter(
        settlement_status=CommissionSettlementStatus.UNSETTLED
    ).select_related('distributor')

    distributor_commissions = {}
    for comm in unsettled_commissions:
        distributor_commissions.setdefault(comm.distributor_id, []).append(comm)

    for distributor_id, commissions in distributor_commissions.items():
        distributor = commissions[0].distributor
        delay_days = get_settlement_delay_for_distributor(distributor)

        is_enabled = False
        distributor_config = CommissionAutoSettlementConfig.objects.filter(
            distributor=distributor
        ).first()
        if distributor_config:
            is_enabled = distributor_config.is_active
        else:
            global_config = CommissionAutoSettlementConfig.objects.filter(
                distributor__isnull=True
            ).first()
            if global_config:
                is_enabled = global_config.is_active

        if not is_enabled:
            print(f"Auto-settlement disabled for distributor {distributor.username}")
            continue

        cutoff_date = current_date - timedelta(days=delay_days)

        for comm in commissions:
            comm_created = comm.created_at
            if is_naive(comm_created):
                comm_created = make_aware(comm_created)

            if comm_created <= cutoff_date:
                eligible_commissions.append(comm.id)

    print(f"Eligible commissions for auto-settlement: {eligible_commissions}")
    return eligible_commissions
