# services/document-parser/src/integrations/database/adapter.py
"""Complete database adapter with all 18 storage methods and UUID-based IDs."""

import asyncpg
import uuid
import random
import asyncio
from datetime import datetime, date
from typing import Any, Optional
from loguru import logger

from models.underwriting_entities import (
    ExtractedDocumentPackage, EngagementTerm, PowerOfAttorney, PaymentGatewayAgreement,
    FinancialAnalysis, DebtSchedule, FCRAConsumerReportConsent, Disclosure,
    HighInterestCreditorDisclosure, ProgramDisclosure, CancellationNotice,
    PaymentGatewayServiceFees, PaymentGatewayBankInfo, PaymentGatewayDepositSchedule,
    LegalPlanAgreement, AttorneyPrivilegedClientInfo, ClixsignCertificateSender, ClixsignCertificateSigner
)


class UnderwritingDatabaseAdapter:
    """Complete database adapter with UUID-based IDs and professional logging."""
    
    def __init__(self, config_instance=None):
        if config_instance:
            self.config = config_instance
        else:
            from config import config
            self.config = config
            
        self.connection_string = self.config.database_url
        self.schema = "underwriting"
        self.pool = None
        
        # ID generation strategy for collision-free IDs
        self.id_counter = random.randint(1, 1000000)
    
    def _generate_unique_id(self, file_id: int, entity_type: str = "") -> int:
        """Generate a truly unique ID using UUID strategy."""
        unique_uuid = uuid.uuid4()
        id_value = abs(hash(str(unique_uuid))) % (2**63 - 1)
        return id_value if id_value != 0 else 1
    

    
    async def initialize(self):
        """Initialize database connection pool with timeout."""
        try:
            # Add timeout to pool creation (critical for production)
            self.pool = await asyncio.wait_for(
                asyncpg.create_pool(
                    self.connection_string,
                    min_size=max(1, self.config.database_pool_size // 5),
                    max_size=self.config.database_pool_size,
                    max_inactive_connection_lifetime=300,
                    command_timeout=self.config.database_timeout,
                    timeout=30,  # Connection timeout per connection attempt
                    server_settings={
                        'application_name': f'{self.config.service_name}-{self.config.environment}',
                        'timezone': 'UTC'
                    }
                ),
                timeout=60  # Total pool initialization timeout
            )
            logger.info("db.pool_initialized")
        except asyncio.TimeoutError:
            logger.error("db.pool_timeout timeout=60s")
            raise
        except Exception as e:
            error_detail = str(e)[:200]
            logger.bind(error=type(e).__name__, detail=error_detail).error("db.pool_failed")
            raise
    
    async def close(self):
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            logger.bind(service="document-parser").info("db.pool_closed")

    def _enrich_payment_gateway_agreement(self, package: ExtractedDocumentPackage) -> None:
        """Fill obvious missing PGA fields from other entities (best-effort)."""
        pga = package.payment_gateway_agreement
        if not pga:
            return
        # Prefer values from attorney_privileged_client_info then engagement_term
        sources = [package.attorney_privileged_client_info, package.engagement_term]
        for src in sources:
            if not src:
                continue
            try:
                if getattr(pga, 'client_address', None) is None:
                    # Combine street/city/state/zip if available
                    street = getattr(src, 'client_street', None) or getattr(src, 'client_address', None)
                    city = getattr(src, 'client_city', None)
                    state = getattr(src, 'client_state', None)
                    zipcode = getattr(src, 'client_zipcode', None)
                    if street and city and state and zipcode:
                        pga.client_address = f"{street}, {city}, {state} {zipcode}"
                    elif street:
                        pga.client_address = street
                if getattr(pga, 'client_city', None) is None and getattr(src, 'client_city', None):
                    pga.client_city = src.client_city
                if getattr(pga, 'client_state', None) is None and getattr(src, 'client_state', None):
                    pga.client_state = src.client_state
                if getattr(pga, 'client_zipcode', None) is None and getattr(src, 'client_zipcode', None):
                    pga.client_zipcode = src.client_zipcode
                if getattr(pga, 'client_phone', None) is None and getattr(src, 'client_home_phone', None):
                    pga.client_phone = src.client_home_phone
                if getattr(pga, 'client_email', None) is None and getattr(src, 'client_email', None):
                    pga.client_email = src.client_email
                if getattr(pga, 'client_first_name', None) is None and getattr(src, 'client_name', None):
                    # Split name if possible
                    parts = str(src.client_name).split()
                    if len(parts) >= 1:
                        pga.client_first_name = parts[0]
                    if len(parts) >= 2:
                        pga.client_last_name = parts[-1]
            except Exception:
                # Best-effort enrichment only
                pass
    
    def _generate_composite_file_id(self, doc_id: str, contact_id: str) -> int:
        """Generate composite file_id from doc_id + contact_id hash for per-contact uniqueness."""
        import hashlib
        
        if not contact_id or not doc_id:
            raise ValueError(f"Both doc_id and contact_id required for composite file_id: doc_id={doc_id}, contact_id={contact_id}")
        
        composite_key = f"{doc_id}_{contact_id}"
        stable_hash = hashlib.sha256(composite_key.encode()).hexdigest()
        # Convert first 8 hex chars to int to stay within PostgreSQL int range
        return int(stable_hash[:8], 16)

    async def _check_document_exists(self, connection, file_id: int) -> bool:
        """Check if document was already processed."""
        result = await connection.fetchval("""
            SELECT EXISTS(
                SELECT 1 FROM underwriting.engagement_term WHERE file_id = $1
                UNION
                SELECT 1 FROM underwriting.financial_analysis WHERE file_id = $1
                UNION
                SELECT 1 FROM underwriting.payment_gateway_agreement WHERE file_id = $1
            )
        """, file_id)
        return result
    
    async def store_document_package(self, package: ExtractedDocumentPackage) -> bool:
        """Store complete document package with duplicate checking and UUID-based IDs."""
        try:
            # Validate required fields
            if not package.file_id or package.file_id <= 0:
                logger.bind(file_id=package.file_id).error("db.package_failed invalid_file_id=true")
                return False
            
            # Always process - no duplicate checking (overwrite mode)
            logger.bind(file_id=package.file_id).info("db.package_processing")
            
            # Log package summary before storage for debugging
            entity_summary = []
            list_summary = []
            
            # Count single entities
            single_entities = ['engagement_term', 'power_of_attorney', 'payment_gateway_agreement', 
                             'financial_analysis', 'fcra_consent', 'disclosure', 'high_interest_disclosure',
                             'program_disclosure', 'cancellation_notice', 'payment_bank_info', 
                             'legal_plan_agreement', 'attorney_privileged_client_info', 'clixsign_sender']
            for entity_name in single_entities:
                if getattr(package, entity_name, None):
                    entity_summary.append(entity_name)
            
            # Count list entities
            list_entities = [
                ('debt_schedule', package.debt_schedule),
                ('payment_service_fees', package.payment_service_fees),
                ('payment_deposit_schedule', package.payment_deposit_schedule),
                ('clixsign_signers', package.clixsign_signers)
            ]
            for name, lst in list_entities:
                if lst and len(lst) > 0:
                    list_summary.append(f"{name}={len(lst)}")
            
            logger.bind(
                file_id=package.file_id,
                entities=entity_summary,
                lists=list_summary
            ).info("db.package_summary")

            # Store all entities in one transaction (keeping original behavior)
            stored_count = 0
            transaction_success = False
            async with self.pool.acquire() as connection:
                # Set a longer timeout for this specific transaction
                await connection.execute("SET statement_timeout = '600s'")  # 10 minutes
                async with connection.transaction():
                    stored_count = 0
                    
                    # Store core entities 
                    if package.engagement_term:
                        try:
                            logger.bind(file_id=package.file_id).info("db.storing_engagement_term")
                            await self._store_engagement_term(connection, package.engagement_term)
                            stored_count += 1
                            logger.bind(file_id=package.file_id).info("db.engagement_term_complete")
                        except Exception as e:
                            error_msg = str(e)[:300]  # Get full error detail
                            logger.bind(file_id=package.file_id, table="engagement_term", error=type(e).__name__, detail=error_msg).error("db.table_failed")
                            raise
                        
                    if package.power_of_attorney:
                        try:
                            logger.bind(file_id=package.file_id).info("db.storing_power_of_attorney")
                            await self._store_power_of_attorney(connection, package.power_of_attorney)
                            stored_count += 1
                            logger.bind(file_id=package.file_id).info("db.power_of_attorney_complete")
                        except Exception as e:
                            error_msg = str(e)[:300]
                            logger.bind(file_id=package.file_id, table="power_of_attorney", error=type(e).__name__, detail=error_msg).error("db.table_failed")
                            raise
                        
                    if package.payment_gateway_agreement:
                        try:
                            # Enrich missing fields from other entities before storing
                            try:
                                self._enrich_payment_gateway_agreement(package)
                            except Exception as enrich_error:
                                logger.bind(file_id=package.file_id, error=str(enrich_error)[:200]).debug("db.payment_gateway_enrich_skipped")
                            logger.bind(file_id=package.file_id).info("db.storing_payment_gateway_agreement")
                            await self._store_payment_gateway_agreement(connection, package.payment_gateway_agreement)
                            stored_count += 1
                            logger.bind(file_id=package.file_id).info("db.payment_gateway_agreement_complete")
                        except Exception as e:
                            error_msg = str(e)[:300]
                            logger.bind(file_id=package.file_id, table="payment_gateway_agreement", error=type(e).__name__, detail=error_msg).error("db.table_failed")
                            raise
                        
                    if package.financial_analysis:
                        try:
                            logger.bind(file_id=package.file_id).info("db.storing_financial_analysis")
                            await self._store_financial_analysis(connection, package.financial_analysis)
                            stored_count += 1
                            logger.bind(file_id=package.file_id).info("db.financial_analysis_complete")
                        except Exception as e:
                            error_msg = str(e)[:300]
                            logger.bind(file_id=package.file_id, table="financial_analysis", error=type(e).__name__, detail=error_msg).error("db.table_failed")
                            raise
                    
                    if package.fcra_consent:
                        try:
                            logger.bind(file_id=package.file_id).info("db.storing_fcra_consent")
                            await self._store_fcra_consent(connection, package.fcra_consent)
                            stored_count += 1
                            logger.bind(file_id=package.file_id).info("db.fcra_consent_complete")
                        except Exception as e:
                            error_msg = str(e)[:300]
                            logger.bind(file_id=package.file_id, table="fcra_consent", error=type(e).__name__, detail=error_msg).error("db.table_failed")
                            raise
                        
                    if package.disclosure:
                        try:
                            logger.bind(file_id=package.file_id).info("db.storing_disclosure")
                            await self._store_disclosure(connection, package.disclosure)
                            stored_count += 1
                            logger.bind(file_id=package.file_id).info("db.disclosure_complete")
                        except Exception as e:
                            error_msg = str(e)[:300]
                            logger.bind(file_id=package.file_id, table="disclosure", error=type(e).__name__, detail=error_msg).error("db.table_failed")
                            raise
                        
                    if package.high_interest_disclosure:
                        try:
                            logger.bind(file_id=package.file_id).info("db.storing_high_interest_disclosure")
                            await self._store_high_interest_disclosure(connection, package.high_interest_disclosure)
                            stored_count += 1
                            logger.bind(file_id=package.file_id).info("db.high_interest_disclosure_complete")
                        except Exception as e:
                            error_msg = str(e)[:300]
                            logger.bind(file_id=package.file_id, table="high_interest_disclosure", error=type(e).__name__, detail=error_msg).error("db.table_failed")
                            raise
                        
                    if package.program_disclosure:
                        try:
                            logger.bind(file_id=package.file_id).info("db.storing_program_disclosure")
                            await self._store_program_disclosure(connection, package.program_disclosure)
                            stored_count += 1
                            logger.bind(file_id=package.file_id).info("db.program_disclosure_complete")
                        except Exception as e:
                            error_msg = str(e)[:300]
                            logger.bind(file_id=package.file_id, table="program_disclosure", error=type(e).__name__, detail=error_msg).error("db.table_failed")
                            raise
                        
                    if package.cancellation_notice:
                        try:
                            logger.bind(file_id=package.file_id).info("db.storing_cancellation_notice")
                            await self._store_cancellation_notice(connection, package.cancellation_notice)
                            stored_count += 1
                            logger.bind(file_id=package.file_id).info("db.cancellation_notice_complete")
                        except Exception as e:
                            error_msg = str(e)[:300]
                            logger.bind(file_id=package.file_id, table="cancellation_notice", error=type(e).__name__, detail=error_msg).error("db.table_failed")
                            raise
                        
                    if package.payment_bank_info:
                        try:
                            logger.bind(file_id=package.file_id).info("db.storing_payment_bank_info")
                            await self._store_payment_bank_info(connection, package.payment_bank_info)
                            stored_count += 1
                            logger.bind(file_id=package.file_id).info("db.payment_bank_info_complete")
                        except Exception as e:
                            error_msg = str(e)[:300]
                            logger.bind(file_id=package.file_id, table="payment_bank_info", error=type(e).__name__, detail=error_msg).error("db.table_failed")
                            raise
                            
                        
                    if package.legal_plan_agreement:
                        try:
                            logger.bind(file_id=package.file_id).info("db.storing_legal_plan_agreement")
                            await self._store_legal_plan_agreement(connection, package.legal_plan_agreement)
                            stored_count += 1
                            logger.bind(file_id=package.file_id).info("db.legal_plan_agreement_complete")
                        except Exception as e:
                            error_msg = str(e)[:300]
                            logger.bind(file_id=package.file_id, table="legal_plan_agreement", error=type(e).__name__, detail=error_msg).error("db.table_failed")
                            raise
                        
                    if package.attorney_privileged_client_info:
                        try:
                            logger.bind(file_id=package.file_id).info("db.storing_attorney_privileged_client_info")
                            await self._store_attorney_privileged_client_info(connection, package.attorney_privileged_client_info)
                            stored_count += 1
                            logger.bind(file_id=package.file_id).info("db.attorney_privileged_client_info_complete")
                        except Exception as e:
                            error_msg = str(e)[:300]
                            logger.bind(file_id=package.file_id, table="attorney_privileged_client_info", error=type(e).__name__, detail=error_msg).error("db.table_failed")
                            raise
                        
                    if package.clixsign_sender:
                        try:
                            logger.bind(file_id=package.file_id).info("db.storing_clixsign_sender")
                            await self._store_clixsign_sender(connection, package.clixsign_sender)
                            stored_count += 1
                            logger.bind(file_id=package.file_id).info("db.clixsign_sender_complete")
                        except Exception as e:
                            error_msg = str(e)[:300]
                            logger.bind(file_id=package.file_id, table="clixsign_sender", error=type(e).__name__, detail=error_msg).error("db.table_failed")
                            raise
                    
                    # Store list entities with UUID-based IDs
                    if package.debt_schedule:
                        try:
                            # Verify transaction health before starting
                            await connection.fetchval("SELECT 1")
                            logger.bind(file_id=package.file_id, count=len(package.debt_schedule)).info("db.storing_debt_schedule")
                            for idx, debt in enumerate(package.debt_schedule, 1):
                                logger.bind(file_id=package.file_id, item=idx).debug("db.debt_schedule_item")
                                await self._store_debt_schedule(connection, debt)
                            stored_count += len(package.debt_schedule)
                            logger.bind(file_id=package.file_id).info("db.debt_schedule_complete")
                        except Exception as e:
                            error_detail = str(e)[:500]
                            logger.bind(file_id=package.file_id, table="debt_schedule", error=type(e).__name__, detail=error_detail).error("db.table_failed")
                            raise
                    
                    # Critical checkpoint: Verify transaction is still valid
                    try:
                        await connection.fetchval("SELECT 1")
                        logger.bind(file_id=package.file_id).debug("db.checkpoint_after_debt_schedule")
                    except Exception as checkpoint_error:
                        logger.bind(
                            file_id=package.file_id,
                            location="after_debt_schedule",
                            error=type(checkpoint_error).__name__,
                            detail=str(checkpoint_error)[:300]
                        ).error("db.transaction_aborted_checkpoint")
                        raise
                        
                    if package.payment_service_fees:
                        try:
                            logger.bind(file_id=package.file_id, count=len(package.payment_service_fees)).info("db.storing_service_fees")
                            for idx, fee in enumerate(package.payment_service_fees, 1):
                                try:
                                    logger.bind(file_id=package.file_id, item=idx, service_name=fee.service_name, service_type=fee.service_type).debug("db.service_fee_item")
                                    await self._store_payment_service_fees(connection, fee)
                                except Exception as item_error:
                                    error_msg = str(item_error)[:500]
                                    logger.bind(
                                        file_id=package.file_id,
                                        item=idx,
                                        service_name=getattr(fee, 'service_name', None),
                                        service_type=getattr(fee, 'service_type', None),
                                        error=type(item_error).__name__,
                                        detail=error_msg
                                    ).error("db.service_fee_item_failed")
                                    raise
                            stored_count += len(package.payment_service_fees)
                            logger.bind(file_id=package.file_id).info("db.service_fees_complete")
                        except Exception as e:
                            error_detail = str(e)[:500]
                            logger.bind(file_id=package.file_id, table="payment_service_fees", error=type(e).__name__, detail=error_detail).error("db.table_failed")
                            raise

                    # Checkpoint after service fees
                    try:
                        await connection.fetchval("SELECT 1")
                        logger.bind(file_id=package.file_id).debug("db.checkpoint_after_service_fees")
                    except Exception as checkpoint_error:
                        logger.bind(
                            file_id=package.file_id,
                            location="after_service_fees",
                            error=type(checkpoint_error).__name__,
                            detail=str(checkpoint_error)[:300]
                        ).error("db.transaction_aborted_checkpoint")
                        raise
                        
                    if package.payment_deposit_schedule:
                        try:
                            logger.bind(file_id=package.file_id, count=len(package.payment_deposit_schedule)).info("db.storing_deposit_schedule")
                            stored_deposits = 0
                            for idx, deposit in enumerate(package.payment_deposit_schedule, 1):
                                try:
                                    # Skip items with null payment_no to avoid NOT NULL constraint violations
                                    if deposit.payment_no is None:
                                        logger.bind(file_id=package.file_id, item=idx).warning("db.deposit_item_skipped reason=null_payment_no")
                                        continue
                                    
                                    logger.bind(file_id=package.file_id, item=idx, payment_no=deposit.payment_no).debug("db.deposit_schedule_item")
                                    await self._store_payment_deposit_schedule(connection, deposit)
                                    stored_deposits += 1
                                except Exception as item_error:
                                    # Log which specific item failed but don't abort entire transaction
                                    error_msg = str(item_error)[:500]
                                    logger.bind(
                                        file_id=package.file_id, 
                                        item=idx,
                                        payment_no=deposit.payment_no,
                                        error=type(item_error).__name__,
                                        detail=error_msg
                                    ).error("db.deposit_item_failed")
                                    # Continue processing other items instead of raising
                            stored_count += stored_deposits
                            logger.bind(file_id=package.file_id, stored=stored_deposits, total=len(package.payment_deposit_schedule)).info("db.deposit_schedule_complete")
                        except Exception as e:
                            error_detail = str(e)[:500]
                            logger.bind(file_id=package.file_id, table="payment_deposit_schedule", error=type(e).__name__, detail=error_detail).error("db.table_failed")
                            raise
                        
                    if package.clixsign_signers:
                        try:
                            logger.bind(file_id=package.file_id, count=len(package.clixsign_signers)).debug("db.storing_clixsign_signers")
                            for signer in package.clixsign_signers:
                                await self._store_clixsign_signer(connection, signer)
                            stored_count += len(package.clixsign_signers)
                            logger.bind(file_id=package.file_id).debug("db.clixsign_signers_complete")
                        except Exception as e:
                            logger.bind(file_id=package.file_id, table="clixsign_signers", error=type(e).__name__, detail=str(e)).error("db.table_failed")
                            raise
                    
                    # Transaction completed successfully
                    transaction_success = True
                    
            # Log success only after transaction commits
            if transaction_success:
                logger.bind(
                    file_id=package.file_id,
                    entities_stored=stored_count
                ).info("db.package_stored")
                return True
            else:
                # Transaction failed but no exception was raised
                logger.bind(file_id=package.file_id).error("db.package_failed transaction_failed=true")
                return False
                    
        except asyncpg.UndefinedColumnError as e:
            logger.bind(
                file_id=package.file_id,
                error="UndefinedColumnError",
                column_name=getattr(e, 'column_name', 'unknown'),
                table_name=getattr(e, 'table_name', 'unknown'),
                sqlstate=getattr(e, 'sqlstate', 'unknown'),
                detail=str(e)
            ).error("db.package_failed schema_mismatch=true")
            return False
        except asyncpg.NotNullViolationError as e:
            logger.bind(
                file_id=package.file_id,
                error="NotNullViolationError",
                column_name=getattr(e, 'column_name', 'unknown'),
                table_name=getattr(e, 'table_name', 'unknown'),
                constraint_name=getattr(e, 'constraint_name', 'unknown'),
                sqlstate=getattr(e, 'sqlstate', 'unknown'),
                detail=str(e)
            ).error("db.package_failed null_constraint_violation=true")
            return False
        except Exception as e:
            logger.bind(
                file_id=package.file_id,
                error=type(e).__name__,
                detail=str(e)
            ).error("db.package_failed")
            return False
    
    async def _store_engagement_term(self, connection, entity: EngagementTerm):
        """Store engagement term data."""
        try:
            await connection.execute("""
            INSERT INTO underwriting.engagement_term 
            (file_id, company_name, company_address, company_phone, company_type,
             settlement_fee, settlement_fee_percentage, monthly_payment, client_name, client_address,
             client_signature, client_signature_date, coclient_name, coclient_signature,
             coclient_signature_date, client_initials, client_initials_count, coclient_initials,
             coclient_initials_count, page_count, identified_debts_ack_client_signature,
             identified_debts_ack_coclient_signature, privacy_policy_client_initials,
             privacy_policy_coclient_initials, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25)
            ON CONFLICT (file_id) DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, engagement_term.company_name),
                company_address = COALESCE(EXCLUDED.company_address, engagement_term.company_address),
                company_phone = COALESCE(EXCLUDED.company_phone, engagement_term.company_phone),
                company_type = COALESCE(EXCLUDED.company_type, engagement_term.company_type),
                settlement_fee = COALESCE(EXCLUDED.settlement_fee, engagement_term.settlement_fee),
                settlement_fee_percentage = COALESCE(EXCLUDED.settlement_fee_percentage, engagement_term.settlement_fee_percentage),
                monthly_payment = COALESCE(EXCLUDED.monthly_payment, engagement_term.monthly_payment),
                client_name = COALESCE(EXCLUDED.client_name, engagement_term.client_name),
                client_address = COALESCE(EXCLUDED.client_address, engagement_term.client_address),
                client_signature = COALESCE(EXCLUDED.client_signature, engagement_term.client_signature),
                client_signature_date = COALESCE(EXCLUDED.client_signature_date, engagement_term.client_signature_date),
                coclient_name = COALESCE(EXCLUDED.coclient_name, engagement_term.coclient_name),
                coclient_signature = COALESCE(EXCLUDED.coclient_signature, engagement_term.coclient_signature),
                coclient_signature_date = COALESCE(EXCLUDED.coclient_signature_date, engagement_term.coclient_signature_date),
                client_initials = COALESCE(EXCLUDED.client_initials, engagement_term.client_initials),
                client_initials_count = COALESCE(EXCLUDED.client_initials_count, engagement_term.client_initials_count),
                coclient_initials = COALESCE(EXCLUDED.coclient_initials, engagement_term.coclient_initials),
                coclient_initials_count = COALESCE(EXCLUDED.coclient_initials_count, engagement_term.coclient_initials_count),
                page_count = COALESCE(EXCLUDED.page_count, engagement_term.page_count),
                identified_debts_ack_client_signature = COALESCE(EXCLUDED.identified_debts_ack_client_signature, engagement_term.identified_debts_ack_client_signature),
                identified_debts_ack_coclient_signature = COALESCE(EXCLUDED.identified_debts_ack_coclient_signature, engagement_term.identified_debts_ack_coclient_signature),
                privacy_policy_client_initials = COALESCE(EXCLUDED.privacy_policy_client_initials, engagement_term.privacy_policy_client_initials),
                privacy_policy_coclient_initials = COALESCE(EXCLUDED.privacy_policy_coclient_initials, engagement_term.privacy_policy_coclient_initials),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.company_name, entity.company_address, entity.company_phone,
            entity.company_type, entity.settlement_fee, entity.settlement_fee_percentage,
            entity.monthly_payment, entity.client_name, entity.client_address, entity.client_signature,
            entity.client_signature_date, entity.coclient_name, entity.coclient_signature,
            entity.coclient_signature_date, entity.client_initials, entity.client_initials_count,
            entity.coclient_initials, entity.coclient_initials_count,
            entity.page_count, entity.identified_debts_ack_client_signature,
            entity.identified_debts_ack_coclient_signature, entity.privacy_policy_client_initials,
            entity.privacy_policy_coclient_initials, datetime.now())
        except asyncpg.InvalidColumnReferenceError as e:
            logger.bind(file_id=entity.file_id, table="engagement_term").error("db.constraint_missing")
            # Fallback to simple insert
            await connection.execute("""
                INSERT INTO underwriting.engagement_term 
                (file_id, company_name, company_address, company_phone, company_type,
                 settlement_fee, settlement_fee_percentage, monthly_payment, client_name, client_address,
                 client_signature, client_signature_date, coclient_name, coclient_signature,
                 coclient_signature_date, client_initials, client_initials_count, coclient_initials,
                 coclient_initials_count, page_count, identified_debts_ack_client_signature,
                 identified_debts_ack_coclient_signature, privacy_policy_client_initials,
                 privacy_policy_coclient_initials, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25)
            """, entity.file_id, entity.company_name, entity.company_address, entity.company_phone,
                entity.company_type, entity.settlement_fee, entity.settlement_fee_percentage,
                entity.monthly_payment, entity.client_name, entity.client_address, entity.client_signature,
                entity.client_signature_date, entity.coclient_name, entity.coclient_signature,
                entity.coclient_signature_date, entity.client_initials, entity.client_initials_count,
                entity.coclient_initials, entity.coclient_initials_count,
                entity.page_count, entity.identified_debts_ack_client_signature,
                entity.identified_debts_ack_coclient_signature, entity.privacy_policy_client_initials,
                entity.privacy_policy_coclient_initials, datetime.now())
    
    async def _store_power_of_attorney(self, connection, entity: PowerOfAttorney):
        """Store power of attorney data."""
        await connection.execute("""
            INSERT INTO underwriting.power_of_attorney 
            (file_id, company_name, attorney_name, attorney_address, attorney_phone,
             client_name, client_ssn, client_dob, client_signature, client_signature_date,
             coclient_name, coclient_ssn, coclient_dob, coclient_signature, coclient_signature_date, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            ON CONFLICT (file_id) DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, power_of_attorney.company_name),
                attorney_name = COALESCE(EXCLUDED.attorney_name, power_of_attorney.attorney_name),
                attorney_address = COALESCE(EXCLUDED.attorney_address, power_of_attorney.attorney_address),
                attorney_phone = COALESCE(EXCLUDED.attorney_phone, power_of_attorney.attorney_phone),
                client_name = COALESCE(EXCLUDED.client_name, power_of_attorney.client_name),
                client_ssn = COALESCE(EXCLUDED.client_ssn, power_of_attorney.client_ssn),
                client_dob = COALESCE(EXCLUDED.client_dob, power_of_attorney.client_dob),
                client_signature = COALESCE(EXCLUDED.client_signature, power_of_attorney.client_signature),
                client_signature_date = COALESCE(EXCLUDED.client_signature_date, power_of_attorney.client_signature_date),
                coclient_name = COALESCE(EXCLUDED.coclient_name, power_of_attorney.coclient_name),
                coclient_ssn = COALESCE(EXCLUDED.coclient_ssn, power_of_attorney.coclient_ssn),
                coclient_dob = COALESCE(EXCLUDED.coclient_dob, power_of_attorney.coclient_dob),
                coclient_signature = COALESCE(EXCLUDED.coclient_signature, power_of_attorney.coclient_signature),
                coclient_signature_date = COALESCE(EXCLUDED.coclient_signature_date, power_of_attorney.coclient_signature_date),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.company_name, entity.attorney_name, entity.attorney_address,
            entity.attorney_phone, entity.client_name, entity.client_ssn, entity.client_dob,
            entity.client_signature, entity.client_signature_date, entity.coclient_name,
            entity.coclient_ssn, entity.coclient_dob, entity.coclient_signature,
            entity.coclient_signature_date, datetime.now())
    
    async def _store_financial_analysis(self, connection, entity: FinancialAnalysis):
        """Store financial analysis data."""
        # Ensure estimated_program_length is properly cast to int
        estimated_program_length_value = None
        if entity.estimated_program_length is not None:
            try:
                estimated_program_length_value = int(entity.estimated_program_length)
            except (ValueError, TypeError):
                estimated_program_length_value = None
        
        await connection.execute("""
            INSERT INTO underwriting.financial_analysis 
            (file_id, applicant_name, applicant_email, coapplicant_name, coapplicant_email,
             draft_type, fixed_income, day_phone, evening_phone, cell_phone,
             program_start_date, estimated_program_start_date, lump_sum,
             applicant_monthly_income, coapplicant_monthly_income, applicant_expenses,
             coapplicant_expenses, applicant_total_net_income, coapplicant_total_net_income,
             total_enrolled_debt, estimated_program_length, monthly_program_deposit,
             estimated_program_settle_amount, fee_method, total_program_fees,
             estimated_program_savings, estimated_total_cost, hardship_details,
             client_signature, client_signature_date, coclient_signature, coclient_signature_date,
             client_initials, coclient_initials, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32, $33, $34, $35)
            ON CONFLICT (file_id) DO UPDATE SET
                applicant_name = COALESCE(EXCLUDED.applicant_name, financial_analysis.applicant_name),
                applicant_email = COALESCE(EXCLUDED.applicant_email, financial_analysis.applicant_email),
                coapplicant_name = COALESCE(EXCLUDED.coapplicant_name, financial_analysis.coapplicant_name),
                coapplicant_email = COALESCE(EXCLUDED.coapplicant_email, financial_analysis.coapplicant_email),
                draft_type = COALESCE(EXCLUDED.draft_type, financial_analysis.draft_type),
                fixed_income = COALESCE(EXCLUDED.fixed_income, financial_analysis.fixed_income),
                day_phone = COALESCE(EXCLUDED.day_phone, financial_analysis.day_phone),
                evening_phone = COALESCE(EXCLUDED.evening_phone, financial_analysis.evening_phone),
                cell_phone = COALESCE(EXCLUDED.cell_phone, financial_analysis.cell_phone),
                program_start_date = COALESCE(EXCLUDED.program_start_date, financial_analysis.program_start_date),
                estimated_program_start_date = COALESCE(EXCLUDED.estimated_program_start_date, financial_analysis.estimated_program_start_date),
                lump_sum = COALESCE(EXCLUDED.lump_sum, financial_analysis.lump_sum),
                applicant_monthly_income = COALESCE(EXCLUDED.applicant_monthly_income, financial_analysis.applicant_monthly_income),
                coapplicant_monthly_income = COALESCE(EXCLUDED.coapplicant_monthly_income, financial_analysis.coapplicant_monthly_income),
                applicant_expenses = COALESCE(EXCLUDED.applicant_expenses, financial_analysis.applicant_expenses),
                coapplicant_expenses = COALESCE(EXCLUDED.coapplicant_expenses, financial_analysis.coapplicant_expenses),
                applicant_total_net_income = COALESCE(EXCLUDED.applicant_total_net_income, financial_analysis.applicant_total_net_income),
                coapplicant_total_net_income = COALESCE(EXCLUDED.coapplicant_total_net_income, financial_analysis.coapplicant_total_net_income),
                total_enrolled_debt = COALESCE(EXCLUDED.total_enrolled_debt, financial_analysis.total_enrolled_debt),
                estimated_program_length = COALESCE(EXCLUDED.estimated_program_length, financial_analysis.estimated_program_length),
                monthly_program_deposit = COALESCE(EXCLUDED.monthly_program_deposit, financial_analysis.monthly_program_deposit),
                estimated_program_settle_amount = COALESCE(EXCLUDED.estimated_program_settle_amount, financial_analysis.estimated_program_settle_amount),
                fee_method = COALESCE(EXCLUDED.fee_method, financial_analysis.fee_method),
                total_program_fees = COALESCE(EXCLUDED.total_program_fees, financial_analysis.total_program_fees),
                estimated_program_savings = COALESCE(EXCLUDED.estimated_program_savings, financial_analysis.estimated_program_savings),
                estimated_total_cost = COALESCE(EXCLUDED.estimated_total_cost, financial_analysis.estimated_total_cost),
                hardship_details = COALESCE(EXCLUDED.hardship_details, financial_analysis.hardship_details),
                client_signature = COALESCE(EXCLUDED.client_signature, financial_analysis.client_signature),
                client_signature_date = COALESCE(EXCLUDED.client_signature_date, financial_analysis.client_signature_date),
                coclient_signature = COALESCE(EXCLUDED.coclient_signature, financial_analysis.coclient_signature),
                coclient_signature_date = COALESCE(EXCLUDED.coclient_signature_date, financial_analysis.coclient_signature_date),
                client_initials = COALESCE(EXCLUDED.client_initials, financial_analysis.client_initials),
                coclient_initials = COALESCE(EXCLUDED.coclient_initials, financial_analysis.coclient_initials),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.applicant_name, entity.applicant_email, entity.coapplicant_name,
            entity.coapplicant_email, entity.draft_type, entity.fixed_income, entity.day_phone,
            entity.evening_phone, entity.cell_phone, entity.program_start_date,
            entity.estimated_program_start_date, entity.lump_sum, entity.applicant_monthly_income,
            entity.coapplicant_monthly_income, entity.applicant_expenses, entity.coapplicant_expenses,
            entity.applicant_total_net_income, entity.coapplicant_total_net_income,
            entity.total_enrolled_debt, estimated_program_length_value,
            entity.monthly_program_deposit, entity.estimated_program_settle_amount,
            entity.fee_method, entity.total_program_fees, entity.estimated_program_savings,
            entity.estimated_total_cost, entity.hardship_details, entity.client_signature,
            entity.client_signature_date, entity.coclient_signature, entity.coclient_signature_date,
            entity.client_initials, entity.coclient_initials, datetime.now())
    
    async def _store_debt_schedule(self, connection, entity: DebtSchedule):
        """Store debt schedule entry with duplicate prevention."""
        try:
            # First, check if this exact debt already exists
            existing_id = await connection.fetchval("""
                SELECT id FROM underwriting.debt_schedule 
                WHERE file_id = $1 AND creditor_name = $2 AND name_on_account = $3 AND account_number = $4
            """, entity.file_id, entity.creditor_name, entity.name_on_account, entity.account_number)
        except Exception as select_error:
            # SELECT query failed - log and re-raise
            logger.bind(
                file_id=entity.file_id,
                creditor=entity.creditor_name,
                error=type(select_error).__name__,
                detail=str(select_error)[:300]
            ).error("db.debt_select_failed")
            raise
        
        if existing_id:
            # Update existing record with latest data
            await connection.execute("""
                UPDATE underwriting.debt_schedule 
                SET current_balance = $5, debt_type = $6, client_name = $7, client_signature = $8,
                    client_signature_date = $9, coclient_name = $10, coclient_signature = $11,
                    coclient_signature_date = $12, updated_at = $13
                WHERE id = $1 AND file_id = $2 AND creditor_name = $3 AND name_on_account = $4
            """, existing_id, entity.file_id, entity.creditor_name, entity.name_on_account,
                entity.current_balance, entity.debt_type, entity.client_name, entity.client_signature,
                entity.client_signature_date, entity.coclient_name, entity.coclient_signature,
                entity.coclient_signature_date, datetime.now())
            
            logger.bind(
                file_id=entity.file_id,
                existing_id=existing_id,
                creditor=entity.creditor_name
            ).debug("db.debt_updated")
            return
        
        # No existing record found, insert new one
        unique_id = self._generate_unique_id(entity.file_id, "debt")
        
        try:
            await connection.execute("""
                INSERT INTO underwriting.debt_schedule 
                (id, file_id, creditor_name, name_on_account, account_number, current_balance, debt_type,
                 client_name, client_signature, client_signature_date, coclient_name, 
                 coclient_signature, coclient_signature_date, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            """, unique_id, entity.file_id, entity.creditor_name, entity.name_on_account, 
                entity.account_number, entity.current_balance, entity.debt_type,
                entity.client_name, entity.client_signature, entity.client_signature_date,
                entity.coclient_name, entity.coclient_signature, entity.coclient_signature_date, datetime.now())
            
            logger.bind(
                file_id=entity.file_id,
                creditor=entity.creditor_name
            ).debug("db.debt_inserted")
            
        except asyncpg.UniqueViolationError as e:
            # Race condition - another process inserted the same debt
            logger.bind(
                file_id=entity.file_id,
                creditor=entity.creditor_name
            ).debug("db.debt_race_condition")
        except Exception as insert_error:
            # Any other database error during INSERT - log and re-raise
            logger.bind(
                file_id=entity.file_id,
                creditor=entity.creditor_name,
                error=type(insert_error).__name__,
                detail=str(insert_error)[:300]
            ).error("db.debt_insert_failed")
            raise
    
    async def _store_payment_gateway_agreement(self, connection, entity: PaymentGatewayAgreement):
        """Store payment gateway agreement data."""
        # Normalize inputs to avoid type issues
        def _coerce_client_initials(v: Any) -> Optional[str]:
            try:
                if isinstance(v, (date, datetime)):
                    return None
            except Exception:
                pass
            if v is None:
                return None
            s = str(v)
            # Keep only letters, cap length to 10
            import re
            s = ''.join(re.findall(r'[A-Za-z]', s))[:10]
            return s or None

        def _coerce_middle_initial(v: Any) -> Optional[str]:
            """Coerce middle initial to single character."""
            if v is None:
                return None
            s = str(v).strip()
            if not s:
                return None
            # Take only the first character and ensure it's a letter
            first_chars = s[:4]
            return first_chars if first_chars.isalpha() else None

        def _coerce_state(v: Any) -> Optional[str]:
            """Coerce state to 2-character code."""
            if v is None:
                return None
            s = str(v).strip().upper()
            if not s:
                return None
            # Take up to 2 characters and ensure they're letters
            state_code = s[:2]
            return state_code if state_code.isalpha() else None

        client_initials_value = _coerce_client_initials(entity.client_initials)
        client_middle_initial = _coerce_middle_initial(entity.client_middle_initial)
        coclient_middle_initial = _coerce_middle_initial(entity.coclient_middle_initial)
        client_state_value = _coerce_state(entity.client_state)
        pages_count_value = None
        if entity.pages_count is not None:
            try:
                pages_count_value = int(entity.pages_count)
            except Exception:
                pages_count_value = None
                
        await connection.execute("""
            INSERT INTO underwriting.payment_gateway_agreement 
            (file_id, account_id, client_first_name, client_last_name, client_middle_initial,
             client_ssn, client_dob, client_address, client_city, client_state, client_zipcode,
             client_phone, client_email, coclient_first_name, coclient_last_name,
             coclient_middle_initial, coclient_ssn, coclient_dob, client_initials, coclient_initials,
             client_signature, client_signature_date, coclient_signature, coclient_signature_date,
             pages_count, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26)
            ON CONFLICT (file_id) DO UPDATE SET
                account_id = COALESCE(EXCLUDED.account_id, payment_gateway_agreement.account_id),
                client_first_name = COALESCE(EXCLUDED.client_first_name, payment_gateway_agreement.client_first_name),
                client_last_name = COALESCE(EXCLUDED.client_last_name, payment_gateway_agreement.client_last_name),
                client_middle_initial = COALESCE(EXCLUDED.client_middle_initial, payment_gateway_agreement.client_middle_initial),
                client_ssn = COALESCE(EXCLUDED.client_ssn, payment_gateway_agreement.client_ssn),
                client_dob = COALESCE(EXCLUDED.client_dob, payment_gateway_agreement.client_dob),
                client_address = COALESCE(EXCLUDED.client_address, payment_gateway_agreement.client_address),
                client_city = COALESCE(EXCLUDED.client_city, payment_gateway_agreement.client_city),
                client_state = COALESCE(EXCLUDED.client_state, payment_gateway_agreement.client_state),
                client_zipcode = COALESCE(EXCLUDED.client_zipcode, payment_gateway_agreement.client_zipcode),
                client_phone = COALESCE(EXCLUDED.client_phone, payment_gateway_agreement.client_phone),
                client_email = COALESCE(EXCLUDED.client_email, payment_gateway_agreement.client_email),
                coclient_first_name = COALESCE(EXCLUDED.coclient_first_name, payment_gateway_agreement.coclient_first_name),
                coclient_last_name = COALESCE(EXCLUDED.coclient_last_name, payment_gateway_agreement.coclient_last_name),
                coclient_middle_initial = COALESCE(EXCLUDED.coclient_middle_initial, payment_gateway_agreement.coclient_middle_initial),
                coclient_ssn = COALESCE(EXCLUDED.coclient_ssn, payment_gateway_agreement.coclient_ssn),
                coclient_dob = COALESCE(EXCLUDED.coclient_dob, payment_gateway_agreement.coclient_dob),
                client_initials = COALESCE(EXCLUDED.client_initials, payment_gateway_agreement.client_initials),
                coclient_initials = COALESCE(EXCLUDED.coclient_initials, payment_gateway_agreement.coclient_initials),
                client_signature = COALESCE(EXCLUDED.client_signature, payment_gateway_agreement.client_signature),
                client_signature_date = COALESCE(EXCLUDED.client_signature_date, payment_gateway_agreement.client_signature_date),
                coclient_signature = COALESCE(EXCLUDED.coclient_signature, payment_gateway_agreement.coclient_signature),
                coclient_signature_date = COALESCE(EXCLUDED.coclient_signature_date, payment_gateway_agreement.coclient_signature_date),
                pages_count = COALESCE(EXCLUDED.pages_count, payment_gateway_agreement.pages_count),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.account_id, entity.client_first_name, entity.client_last_name,
            client_middle_initial, entity.client_ssn, entity.client_dob, entity.client_address,
            entity.client_city, client_state_value, entity.client_zipcode, entity.client_phone,
            entity.client_email, entity.coclient_first_name, entity.coclient_last_name,
            coclient_middle_initial, entity.coclient_ssn, entity.coclient_dob,
            client_initials_value, entity.coclient_initials, entity.client_signature, entity.client_signature_date,
            entity.coclient_signature, entity.coclient_signature_date, pages_count_value,
            datetime.now())
    
    async def _store_fcra_consent(self, connection, entity: FCRAConsumerReportConsent):
        """Store FCRA consent data."""
        await connection.execute("""
            INSERT INTO underwriting.fcra_consumer_report_consent 
            (file_id, company_name, client_name, client_signature, client_signature_date, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (file_id) DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, fcra_consumer_report_consent.company_name),
                client_name = COALESCE(EXCLUDED.client_name, fcra_consumer_report_consent.client_name),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.company_name, entity.client_name,
            entity.client_signature, entity.client_signature_date, datetime.now())
    
    async def _store_disclosure(self, connection, entity: Disclosure):
        """Store disclosure data."""
        await connection.execute("""
            INSERT INTO underwriting.disclosure 
            (file_id, client_signature, client_signature_date, coclient_signature, coclient_signature_date,
             additional_disclosure_client_signature, additional_disclosure_client_signature_date,
             additional_disclosure_coclient_signature, additional_disclosure_coclient_signature_date, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (file_id) DO UPDATE SET
                client_signature = COALESCE(EXCLUDED.client_signature, disclosure.client_signature),
                client_signature_date = COALESCE(EXCLUDED.client_signature_date, disclosure.client_signature_date),
                coclient_signature = COALESCE(EXCLUDED.coclient_signature, disclosure.coclient_signature),
                coclient_signature_date = COALESCE(EXCLUDED.coclient_signature_date, disclosure.coclient_signature_date),
                additional_disclosure_client_signature = COALESCE(EXCLUDED.additional_disclosure_client_signature, disclosure.additional_disclosure_client_signature),
                additional_disclosure_client_signature_date = COALESCE(EXCLUDED.additional_disclosure_client_signature_date, disclosure.additional_disclosure_client_signature_date),
                additional_disclosure_coclient_signature = COALESCE(EXCLUDED.additional_disclosure_coclient_signature, disclosure.additional_disclosure_coclient_signature),
                additional_disclosure_coclient_signature_date = COALESCE(EXCLUDED.additional_disclosure_coclient_signature_date, disclosure.additional_disclosure_coclient_signature_date),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.client_signature, entity.client_signature_date,
            entity.coclient_signature, entity.coclient_signature_date,
            entity.additional_disclosure_client_signature, entity.additional_disclosure_client_signature_date,
            entity.additional_disclosure_coclient_signature, entity.additional_disclosure_coclient_signature_date, datetime.now())
    
    async def _store_high_interest_disclosure(self, connection, entity: HighInterestCreditorDisclosure):
        """Store high interest creditor disclosure data."""
        await connection.execute("""
            INSERT INTO underwriting.high_interest_creditor_disclosure 
            (file_id, company_name, client_name, client_signature, client_signature_date,
             coclient_name, coclient_signature, coclient_signature_date, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (file_id) DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, high_interest_creditor_disclosure.company_name),
                client_name = COALESCE(EXCLUDED.client_name, high_interest_creditor_disclosure.client_name),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.company_name, entity.client_name, entity.client_signature,
            entity.client_signature_date, entity.coclient_name, entity.coclient_signature,
            entity.coclient_signature_date, datetime.now())
    
    async def _store_program_disclosure(self, connection, entity: ProgramDisclosure):
        """Store program disclosure data."""
        await connection.execute("""
            INSERT INTO underwriting.program_disclosure 
            (file_id, company_name, settlement_fee_percent, client_initials, coclient_initials, client_initials_count, coclient_initials_count, is_all_initials_present, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (file_id) DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, program_disclosure.company_name),
                settlement_fee_percent = COALESCE(EXCLUDED.settlement_fee_percent, program_disclosure.settlement_fee_percent),
                client_initials = COALESCE(EXCLUDED.client_initials, program_disclosure.client_initials),
                coclient_initials = COALESCE(EXCLUDED.coclient_initials, program_disclosure.coclient_initials),
                client_initials_count = COALESCE(EXCLUDED.client_initials_count, program_disclosure.client_initials_count),
                coclient_initials_count = COALESCE(EXCLUDED.coclient_initials_count, program_disclosure.coclient_initials_count),
                is_all_initials_present = COALESCE(EXCLUDED.is_all_initials_present, program_disclosure.is_all_initials_present),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.company_name, entity.settlement_fee_percent,
            entity.client_initials, entity.coclient_initials, entity.client_initials_count, entity.coclient_initials_count, entity.is_all_initials_present, datetime.now())
    
    async def _store_cancellation_notice(self, connection, entity: CancellationNotice):
        """Store cancellation notice data."""
        await connection.execute("""
            INSERT INTO underwriting.cancellation_notice 
            (file_id, cancellation_deadline, cancellation_date, client_signature, client_signature_date, coclient_signature, coclient_signature_date, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (file_id) DO UPDATE SET
                cancellation_deadline = COALESCE(EXCLUDED.cancellation_deadline, cancellation_notice.cancellation_deadline),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.cancellation_deadline, entity.cancellation_date,
            entity.client_signature, entity.client_signature_date, entity.coclient_signature, entity.coclient_signature_date, datetime.now())
    
    async def _store_payment_service_fees(self, connection, entity: PaymentGatewayServiceFees):
        """Store payment gateway service fees."""
        # Use per-item savepoint so a conflict doesn't abort the outer transaction
        try:
            async with connection.transaction():
                await connection.execute("""
                    INSERT INTO underwriting.payment_gateway_service_fees 
                    (file_id, service_type, service_name, service_amount, updated_at)
                    VALUES ($1, $2, $3, $4, $5)
                """, entity.file_id, entity.service_type, entity.service_name,
                    entity.service_amount, datetime.now())
                return
        except asyncpg.UniqueViolationError:
            # Savepoint rolled back; fall through to update in outer tx
            pass
        except Exception as e:
            # Bubble up other errors
            raise

        # Conflict path: perform UPDATE in the outer transaction
        await connection.execute("""
            UPDATE underwriting.payment_gateway_service_fees 
            SET service_amount = $4, updated_at = $5
            WHERE file_id = $1 AND service_type = $2 AND service_name = $3
        """, entity.file_id, entity.service_type, entity.service_name,
            entity.service_amount, datetime.now())
    
    async def _store_payment_bank_info(self, connection, entity: PaymentGatewayBankInfo):
        """Store payment gateway bank info."""
        logger.bind(
            file_id=entity.file_id,
            bank_name=entity.bank_name,
            account_number=entity.account_number,
            routing_number=entity.routing_number,
            recurring_debit_authorization=entity.recurring_debit_authorization
        ).debug("db.payment_bank_info_details")
        
        # Coerce state to 2-character code
        def _coerce_state(v: Any) -> Optional[str]:
            if v is None:
                return None
            s = str(v).strip().upper()
            if not s:
                return None
            state_code = s[:2]
            return state_code if state_code.isalpha() else None
        
        client_state_value = _coerce_state(entity.client_state)
        
        await connection.execute("""
            INSERT INTO underwriting.payment_gateway_bank_info 
            (file_id, authorizing_person_name, bank_name, account_number, routing_number,
             account_type, client_address, client_city, client_state, client_zipcode, 
             recurring_debit_authorization, first_debit_date,
             client_signature, client_signature_date, coclient_signature, coclient_signature_date, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
            ON CONFLICT (file_id) DO UPDATE SET
                authorizing_person_name = COALESCE(EXCLUDED.authorizing_person_name, payment_gateway_bank_info.authorizing_person_name),
                bank_name = COALESCE(EXCLUDED.bank_name, payment_gateway_bank_info.bank_name),
                account_number = COALESCE(EXCLUDED.account_number, payment_gateway_bank_info.account_number),
                routing_number = COALESCE(EXCLUDED.routing_number, payment_gateway_bank_info.routing_number),
                account_type = COALESCE(EXCLUDED.account_type, payment_gateway_bank_info.account_type),
                client_address = COALESCE(EXCLUDED.client_address, payment_gateway_bank_info.client_address),
                client_city = COALESCE(EXCLUDED.client_city, payment_gateway_bank_info.client_city),
                client_state = COALESCE(EXCLUDED.client_state, payment_gateway_bank_info.client_state),
                client_zipcode = COALESCE(EXCLUDED.client_zipcode, payment_gateway_bank_info.client_zipcode),
                recurring_debit_authorization = COALESCE(EXCLUDED.recurring_debit_authorization, payment_gateway_bank_info.recurring_debit_authorization),
                first_debit_date = COALESCE(EXCLUDED.first_debit_date, payment_gateway_bank_info.first_debit_date),
                client_signature = COALESCE(EXCLUDED.client_signature, payment_gateway_bank_info.client_signature),
                client_signature_date = COALESCE(EXCLUDED.client_signature_date, payment_gateway_bank_info.client_signature_date),
                coclient_signature = COALESCE(EXCLUDED.coclient_signature, payment_gateway_bank_info.coclient_signature),
                coclient_signature_date = COALESCE(EXCLUDED.coclient_signature_date, payment_gateway_bank_info.coclient_signature_date),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.authorizing_person_name, entity.bank_name, entity.account_number,
            entity.routing_number, entity.account_type, entity.client_address, entity.client_city, client_state_value, entity.client_zipcode, entity.recurring_debit_authorization,
            entity.first_debit_date, entity.client_signature, entity.client_signature_date,
            entity.coclient_signature, entity.coclient_signature_date, datetime.now())
    
    async def _store_payment_deposit_schedule(self, connection, entity: PaymentGatewayDepositSchedule):
        """Store payment gateway deposit schedule."""
        # Use per-item savepoint for safe upsert without aborting outer transaction
        try:
            async with connection.transaction():
                await connection.execute("""
                    INSERT INTO underwriting.payment_gateway_deposit_schedule 
                    (file_id, payment_no, process_date, amount, updated_at)
                    VALUES ($1, $2, $3, $4, $5)
                """, entity.file_id, entity.payment_no, entity.process_date,
                    entity.amount, datetime.now())
                return
        except asyncpg.UniqueViolationError:
            pass
        except Exception as e:
            raise

        await connection.execute("""
            UPDATE underwriting.payment_gateway_deposit_schedule 
            SET process_date = $3, amount = $4, updated_at = $5
            WHERE file_id = $1 AND payment_no = $2
        """, entity.file_id, entity.payment_no, entity.process_date,
            entity.amount, datetime.now())
    
    async def _store_legal_plan_agreement(self, connection, entity: LegalPlanAgreement):
        """Store legal plan agreement data."""
        pages_count_value = None
        if entity.pages_count is not None:
            try:
                pages_count_value = int(entity.pages_count)
            except Exception:
                pages_count_value = None
        initials_count_value = None
        if entity.initials_count is not None:
            try:
                initials_count_value = int(entity.initials_count)
            except Exception:
                initials_count_value = None
                
        await connection.execute("""
            INSERT INTO underwriting.legal_plan_agreement 
            (file_id, legal_plan_provider, member_name, member_ssn, member_dob,
             coapplicant_name, coapplicant_ssn, coapplicant_dob, address, city, state, zipcode,
             phone1, phone2, email, referring_company, first_payment_date, first_payment_amount,
             monthly_recurring_date, monthly_payment_amount, debt_relief_program_duration,
             members_accumulation_amount, payment_processor_name, credit_card_number,
             bank_account_number, credit_card_expiration_date, bank_routing_number,
             credit_card_name, bank_institution_name, credit_card_billing_address,
             account_holder_name, initials_count, is_all_initials_present, client_signature, signature_date,
             pages_count, member_agreement_client_signature, member_agreement_signature_date,
             member_acknowledge_client_initials, member_acknowledge_client_initials_count,
             member_acknowledge_client_signature, member_acknowledge_signature_date,
             member_info_client_signature, member_info_signature_date, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32, $33, $34, $35, $36, $37, $38, $39, $40, $41, $42, $43, $44, $45)
            ON CONFLICT (file_id) DO UPDATE SET
                legal_plan_provider = COALESCE(EXCLUDED.legal_plan_provider, legal_plan_agreement.legal_plan_provider),
                member_name = COALESCE(EXCLUDED.member_name, legal_plan_agreement.member_name),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.legal_plan_provider, entity.member_name, entity.member_ssn,
            entity.member_dob, entity.coapplicant_name, entity.coapplicant_ssn, entity.coapplicant_dob,
            entity.address, entity.city, entity.state, entity.zipcode, entity.phone1, entity.phone2,
            entity.email, entity.referring_company, entity.first_payment_date, entity.first_payment_amount,
            entity.monthly_recurring_date, entity.monthly_payment_amount, entity.debt_relief_program_duration,
            entity.members_accumulation_amount, entity.payment_processor_name, entity.credit_card_number,
            entity.bank_account_number, entity.credit_card_expiration_date, entity.bank_routing_number,
            entity.credit_card_name, entity.bank_institution_name, entity.credit_card_billing_address,
            entity.account_holder_name, initials_count_value, entity.is_all_initials_present, 
            entity.client_signature, entity.signature_date, pages_count_value,
            entity.member_agreement_client_signature, entity.member_agreement_signature_date,
            entity.member_acknowledge_client_initials, entity.member_acknowledge_client_initials_count,
            entity.member_acknowledge_client_signature, entity.member_acknowledge_signature_date,
            entity.member_info_client_signature, entity.member_info_signature_date, datetime.now())
    
    async def _store_attorney_privileged_client_info(self, connection, entity: AttorneyPrivilegedClientInfo):
        """Store attorney privileged client info data."""
        await connection.execute("""
            INSERT INTO underwriting.attorney_privileged_client_info 
            (file_id, client_name, client_ssn, client_dob, client_employer, client_title,
             client_classification, client_email, client_street, client_city, client_state,
             client_zipcode, client_home_phone, client_cell_phone, coclient_name, coclient_ssn,
             coclient_dob, coclient_employer, coclient_title, coclient_classification,
             coclient_email, is_married_to_coclient, has_security_clearance, is_in_bankruptcy,
             is_enrolled_in_credit_counseling, client_signature, client_signature_date,
             coclient_signature, coclient_signature_date, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30)
            ON CONFLICT (file_id) DO UPDATE SET
                client_name = COALESCE(EXCLUDED.client_name, attorney_privileged_client_info.client_name),
                client_ssn = COALESCE(EXCLUDED.client_ssn, attorney_privileged_client_info.client_ssn),
                client_dob = COALESCE(EXCLUDED.client_dob, attorney_privileged_client_info.client_dob),
                client_employer = COALESCE(EXCLUDED.client_employer, attorney_privileged_client_info.client_employer),
                client_title = COALESCE(EXCLUDED.client_title, attorney_privileged_client_info.client_title),
                client_classification = COALESCE(EXCLUDED.client_classification, attorney_privileged_client_info.client_classification),
                client_email = COALESCE(EXCLUDED.client_email, attorney_privileged_client_info.client_email),
                client_street = COALESCE(EXCLUDED.client_street, attorney_privileged_client_info.client_street),
                client_city = COALESCE(EXCLUDED.client_city, attorney_privileged_client_info.client_city),
                client_state = COALESCE(EXCLUDED.client_state, attorney_privileged_client_info.client_state),
                client_zipcode = COALESCE(EXCLUDED.client_zipcode, attorney_privileged_client_info.client_zipcode),
                client_home_phone = COALESCE(EXCLUDED.client_home_phone, attorney_privileged_client_info.client_home_phone),
                client_cell_phone = COALESCE(EXCLUDED.client_cell_phone, attorney_privileged_client_info.client_cell_phone),
                coclient_name = COALESCE(EXCLUDED.coclient_name, attorney_privileged_client_info.coclient_name),
                coclient_ssn = COALESCE(EXCLUDED.coclient_ssn, attorney_privileged_client_info.coclient_ssn),
                coclient_dob = COALESCE(EXCLUDED.coclient_dob, attorney_privileged_client_info.coclient_dob),
                coclient_employer = COALESCE(EXCLUDED.coclient_employer, attorney_privileged_client_info.coclient_employer),
                coclient_title = COALESCE(EXCLUDED.coclient_title, attorney_privileged_client_info.coclient_title),
                coclient_classification = COALESCE(EXCLUDED.coclient_classification, attorney_privileged_client_info.coclient_classification),
                coclient_email = COALESCE(EXCLUDED.coclient_email, attorney_privileged_client_info.coclient_email),
                is_married_to_coclient = COALESCE(EXCLUDED.is_married_to_coclient, attorney_privileged_client_info.is_married_to_coclient),
                has_security_clearance = COALESCE(EXCLUDED.has_security_clearance, attorney_privileged_client_info.has_security_clearance),
                is_in_bankruptcy = COALESCE(EXCLUDED.is_in_bankruptcy, attorney_privileged_client_info.is_in_bankruptcy),
                is_enrolled_in_credit_counseling = COALESCE(EXCLUDED.is_enrolled_in_credit_counseling, attorney_privileged_client_info.is_enrolled_in_credit_counseling),
                client_signature = COALESCE(EXCLUDED.client_signature, attorney_privileged_client_info.client_signature),
                client_signature_date = COALESCE(EXCLUDED.client_signature_date, attorney_privileged_client_info.client_signature_date),
                coclient_signature = COALESCE(EXCLUDED.coclient_signature, attorney_privileged_client_info.coclient_signature),
                coclient_signature_date = COALESCE(EXCLUDED.coclient_signature_date, attorney_privileged_client_info.coclient_signature_date),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.client_name, entity.client_ssn, entity.client_dob,
            entity.client_employer, entity.client_title, entity.client_classification, entity.client_email,
            entity.client_street, entity.client_city, entity.client_state, entity.client_zipcode,
            entity.client_home_phone, entity.client_cell_phone, entity.coclient_name, entity.coclient_ssn,
            entity.coclient_dob, entity.coclient_employer, entity.coclient_title, entity.coclient_classification,
            entity.coclient_email, entity.is_married_to_coclient, entity.has_security_clearance,
            entity.is_in_bankruptcy, entity.is_enrolled_in_credit_counseling, entity.client_signature,
            entity.client_signature_date, entity.coclient_signature, entity.coclient_signature_date, datetime.now())
    
    async def _store_clixsign_sender(self, connection, entity: ClixsignCertificateSender):
        """Store clixsign certificate sender data."""
        await connection.execute("""
            INSERT INTO underwriting.clixsign_certificate_sender 
            (file_id, package_id, package_title, final_status, final_status_date,
             sending_entity, sender_name, sender_email_address, sender_ip_address,
             signers_count, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (file_id) DO UPDATE SET
                package_id = EXCLUDED.package_id,
                final_status = EXCLUDED.final_status,
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.package_id, entity.package_title, entity.final_status,
            entity.final_status_date, entity.sending_entity, entity.sender_name,
            entity.sender_email_address, entity.sender_ip_address, entity.signers_count, datetime.now())
    
    async def _store_clixsign_signer(self, connection, entity: ClixsignCertificateSigner):
        """Store clixsign certificate signer data."""
        # Use composite key for better uniqueness
        unique_key = f"{entity.file_id}_{entity.signer_email_address or entity.signer_name}"
        unique_id = abs(hash(unique_key)) % (2**63 - 1)
        
        await connection.execute("""
            INSERT INTO underwriting.clixsign_certificate_signer 
            (id, file_id, package_id, signer_name, signer_email_address, signer_ip_address,
             signer_user_agent, package_opened_at, signature_adopted_at, package_signed_at,
             package_declined_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (id) DO UPDATE SET
                package_id = COALESCE(EXCLUDED.package_id, clixsign_certificate_signer.package_id),
                signer_name = COALESCE(EXCLUDED.signer_name, clixsign_certificate_signer.signer_name),
                signer_email_address = COALESCE(EXCLUDED.signer_email_address, clixsign_certificate_signer.signer_email_address),
                signer_ip_address = COALESCE(EXCLUDED.signer_ip_address, clixsign_certificate_signer.signer_ip_address),
                signer_user_agent = COALESCE(EXCLUDED.signer_user_agent, clixsign_certificate_signer.signer_user_agent),
                package_opened_at = COALESCE(EXCLUDED.package_opened_at, clixsign_certificate_signer.package_opened_at),
                signature_adopted_at = COALESCE(EXCLUDED.signature_adopted_at, clixsign_certificate_signer.signature_adopted_at),
                package_signed_at = COALESCE(EXCLUDED.package_signed_at, clixsign_certificate_signer.package_signed_at),
                package_declined_at = COALESCE(EXCLUDED.package_declined_at, clixsign_certificate_signer.package_declined_at),
                updated_at = EXCLUDED.updated_at
        """, unique_id, entity.file_id, entity.package_id, entity.signer_name, 
            entity.signer_email_address, entity.signer_ip_address, entity.signer_user_agent,
            entity.package_opened_at, entity.signature_adopted_at, entity.package_signed_at,
            entity.package_declined_at, datetime.now())


# Backward compatibility alias
DatabaseAdapter = UnderwritingDatabaseAdapter